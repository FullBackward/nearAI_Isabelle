# Running the experiment on the Ubuntu server

*Written 2026-11-04. Target: the Ubuntu box that already hosts the Isabelle Pool
Server (IPS) natively (x86_64, 32 logical CPUs, ~126 GiB RAM, systemd service,
Isabelle at `/opt/isabelle`), reached over SSH. The harness runs on the same
host, exactly like IPS's own `evaluation/MCP-comparison` runners.*

## 0. Topology: everything is local to the server

```
 laptop  --ssh-->  Ubuntu server
                    ├─ IPS (native, systemd)            http://localhost:8000
                    ├─ harness  run_isabelle_solver.py  (this repo, its own venv)
                    │    └─ MCP server  python -m mcp_servers.lsp.app   <- stdio child
                    │         └─ HTTP -> IPS :8000
                    └─ outbound HTTPS -> api.deepseek.com
```

- The MCP is **not** a network service. The harness starts `mcp_servers.lsp.app`
  from the IPS checkout as a child process and talks to it over **stdio**
  (`ISABELLE_MCP_LSP_TRANSPORT=stdio`, `PYTHONPATH=<IPS checkout>`), the same
  launch IPS's `run_isabelle_pool_server_lsp.py` uses. The child reaches IPS on
  `localhost:8000`.
- Verification (`bigstep`) and the sledgehammer probe call `localhost:8000` directly.
- The only path that leaves the machine is the model call to `api.deepseek.com`.

So SSH changes nothing about how the pieces connect. It changes two habits:

- start workers inside `tmux` so they survive a dropped connection;
- read dashboards through a tunnel: `ssh -L 8000:localhost:8000 user@server`
  (and `:3000` / `:9090` if the monitoring stack is up).

Do not run the harness on the laptop against a tunnelled IPS: an attempt keeps a
session for up to an hour and the stdio MCP must sit next to the server anyway.

## 1. Server prerequisites (one-time)

### 1a. IPS at a commit with the `FIELD_FROM_IMPORTS` feature

The harness starts every file session on the heap the file's imports name
(`ISABELLE_MCP_LSP_FIELD_FROM_IMPORTS=true`). The feature lives in
`mcp_servers/lsp/config.py` and `pool.py`; it is committed in IPS main.

```bash
cd ~/Isabelle-Pool-Server            # wherever the service's checkout is: systemctl cat isabelle-pool-server | grep WorkingDirectory
git pull
grep -n FIELD_FROM_IMPORTS mcp_servers/lsp/config.py     # must print the config line
source .venv/bin/activate && pip install -e ".[mcp]" -e ./client && deactivate
sudo systemctl restart isabelle-pool-server              # only if server/ code changed
curl -s localhost:8000/healthz                           # {"status":"alive"} after 1-2 min
```

(If the checkout predates the commit, `git apply ~/GitHub/nearAI_Isabelle/scripts/ips-field-from-imports.patch`
is the same change.)

### 1b. Heaps

Each problem file imports a distribution session; the heap for it must exist under
`~/.isabelle/Isabelle2026/heaps/<platform>/` of the user the service runs as.
Native path, server idle, same user as the service:

```bash
isabelle build -b HOL-Number_Theory HOL-Computational_Algebra HOL-Library
isabelle build -b -j 2 HOL-Analysis          # P2; several GB and 30-80 min
curl -s localhost:8000/api/v1/heaps/available
```

Needed per tier: IMO 2026 uses HOL-Computational_Algebra (P1), HOL-Analysis (P2),
HOL-Library (P4), plain HOL (P3, P5, P6). miniF2F needs HOL-Number_Theory;
PutnamBench additionally HOL-Analysis, HOL-Algebra, HOL-Combinatorics. A missing
heap does not fail the run, it makes every `isabelle_open` and `bigstep` build the
parent from source (minutes each; P4 took 790 s once on the laptop for that reason).

### 1c. Outbound HTTPS

```bash
curl -sI https://api.deepseek.com | head -1     # an HTTP status line, not a timeout
```

Without it nothing runs. (An `ssh -R` proxy is possible but fragile for day-long
campaigns; ask before relying on it.)

## 2. This repository on the server

Clone it once it is committed; until then rsync from the laptop:

```bash
rsync -av --exclude .venv --exclude runs --exclude benchmarks \
      --exclude 'config/model.json' --exclude db.sql --exclude '__pycache__' \
      ~/GitHub/nearAI_Isabelle/ user@server:~/GitHub/nearAI_Isabelle/
```

On the server:

```bash
cd ~/GitHub/nearAI_Isabelle
python3 -m venv .venv && .venv/bin/pip install "mcp>=1.2,<2" requests pyyaml httpx pytest \
    -e ~/Isabelle-Pool-Server/client

# tell the harness where the IPS checkout is (default ~/GitHub/Isabelle-Pool-Server)
export ISABELLE_POOL_SERVER=~/Isabelle-Pool-Server      # put it in ~/.bashrc or the tmux session

.venv/bin/python harness/ib.py prepare --source imo2026 --root problems/imo2026/isabelle
# miniF2F / PutnamBench tiers: clone + prepare as in README "Setup"
.venv/bin/python harness/ib.py selftest
.venv/bin/python -m pytest -q tests
.venv/bin/python scripts/bigstep_check.py --timeout 900 problems/imo2026/isabelle/*.thy
```

Six `PASS` lines before any model run. All of this is free.

The harness's python doubles as the MCP server's interpreter (`IPS_MCP_PYTHON`
defaults to it), which is why the venv needs `mcp` and the IPS `client` package.
Alternatively point `IPS_MCP_PYTHON` at `~/Isabelle-Pool-Server/.venv/bin/python`,
which already has both.

| variable | default | meaning |
|---|---|---|
| `ISABELLE_POOL_SERVER` | `~/GitHub/Isabelle-Pool-Server` | IPS checkout; `mcp_servers.lsp.app` is imported from here |
| `IPS_MCP_PYTHON` | the harness's own interpreter | python that runs the stdio MCP child |
| `IB_GYM_URL` | `http://localhost:8000` | IPS API |
| `IB_MANIFEST`, `IB_QUEUE`, `TRAJ_DB` | `harness/manifest.json`, queue TSV, `db.sql` | state files |

## 3. The DeepSeek key

IPS's own harness reads `DEEPSEEK_API_KEY` from the environment; this harness
reads a **file** named by `apikey_file` in `config/model.json` and never touches
the environment. Keep it that way: an env var shows up in `ps`/`proc` and in shell
history.

```bash
# laptop -> server
ssh user@server 'mkdir -p -m 700 ~/.secrets'
scp ~/GitHub/Isabelle-Pool-Server/evaluation/MCP-comparison/deepseek_api.txt user@server:~/.secrets/
ssh user@server 'chmod 600 ~/.secrets/deepseek_api.txt'
```

`config/model.json` on the server (gitignored, excluded from the rsync):

```json
{
  "host": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-v4-pro",
  "apikey_file": "/home/USER/.secrets/deepseek_api.txt",
  "context_window": 1000000,
  "merge_reasoning": false,
  "compact_at": 0.8
}
```

Token usage per call is summed into each `runs/results.jsonl` row (prompt,
completion, cached, calls), so spend is reconstructible afterwards. DeepSeek
reportedly retired `deepseek-v4-pro` on 2026-09-14 and reroutes to V4.1 Flash;
the results only record the configured name, so confirm the model id you want
scored before the campaign.

## 4. Sizing the workers

With ~126 GiB and IPS native, memory is not the limit the laptop had, but three
knobs must agree:

| knob | where | rule |
|---|---|---|
| number of workers | shell loop below | each worker holds one Isabelle session (1.5-4 GB) plus provers |
| `ISABELLE_POOL_SIZE` | IPS `.env` (default 3) | >= workers, or workers queue on the admission gate |
| `ISABELLE_MEMORY_PRESSURE_THRESHOLD` | IPS `.env` (default 80 %) | percent of **host** RAM on a native install |

Start with 4 workers and `ISABELLE_POOL_SIZE=6` (restart the service after editing
`.env`). The IMO tier has only 36 rows, so more than 6 workers gains little; the
miniF2F pilot (60 problems x 2 arms) can use 6-8 on this box. Sledgehammer spawns
several provers per call; 32 cores cover 6 workers comfortably.

## 5. Running (paid from here on; owner approval per run)

```bash
tmux new -s imo
cd ~/GitHub/nearAI_Isabelle && export ISABELLE_POOL_SERVER=~/Isabelle-Pool-Server

# 5a. one attempt end to end (P5 is the cheapest)
.venv/bin/python run_isabelle_solver.py --problem imo_2026_p5 --arm plain
tail -1 runs/results.jsonl | python3 -m json.tool | head -40

# 5b. the IMO 2026 tier: 6 problems x 2 arms x 3 repeats = 36 rows
.venv/bin/python harness/ib.py queue-init --source imo2026 --arm plain skeleton --repeats 3
.venv/bin/python harness/ib.py queue-status

# 5c. workers; --loop 0 = run until the queue drains
for i in 1 2 3 4; do
  nohup .venv/bin/python run_isabelle_solver.py --loop 0 --owner "w$i" \
        --max-steps 150 --timeout 3600 > runs/worker$i.log 2>&1 &
done
```

Budgets: 150 steps and 3600 s per attempt; the skeleton arm's `fill_sorries` jobs
are capped at 30 s of sledgehammer per `sorry` and 600 s per job. Worst case for
the tier is 36 attempt-hours divided by the worker count.

Monitoring (second tmux window or SSH session):

```bash
.venv/bin/python harness/ib.py queue-status
tail -f runs/worker1.log
journalctl -u isabelle-pool-server -f          # or tail -f ~/Isabelle-Pool-Server/logs/server.log
curl -s localhost:8000/                         # pool, memory, builds in flight
```

A worker that dies leaves its rows `claimed`; put them back with
`harness/ib.py requeue claimed` (one row: `harness/ib.py release <problem> --arm A --rep R --status todo`)
and start the worker again.

## 6. Results

```bash
.venv/bin/python analyze.py --pair plain skeleton --source imo2026
# laptop:
rsync -av user@server:~/GitHub/nearAI_Isabelle/runs/ ~/GitHub/nearAI_Isabelle/runs-server/
```

`runs/results.jsonl` has one row per attempt (status, steps, tokens, fills, wall
time, verifier report); `runs/<arm>/<problem>/rep<N>/` the final theory and transcript.

## 7. Go / no-go

- [ ] `grep FIELD_FROM_IMPORTS mcp_servers/lsp/config.py` finds the feature in the service's checkout
- [ ] `curl localhost:8000/api/v1/heaps/available` lists HOL-Computational_Algebra, HOL-Library, HOL-Analysis (and HOL-Number_Theory for miniF2F)
- [ ] `curl -sI https://api.deepseek.com` answers
- [ ] `bigstep_check.py` prints six `PASS`; `selftest` and `pytest` pass
- [ ] `ISABELLE_POOL_SERVER` exported; `config/model.json` points at a mode-600 key file; model id confirmed
- [ ] `ISABELLE_POOL_SIZE` >= workers; workers started inside `tmux`
- [ ] the owner has approved the spend for this run
