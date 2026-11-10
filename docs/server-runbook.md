# Running the experiment on the Ubuntu server

*Written 2026-11-04. Target: the Ubuntu box that already hosts the Isabelle Pool
Server (IPS) natively (x86_64, 32 logical CPUs, ~126 GiB RAM, Isabelle2026 unpacked
in the home directory as `~/Isabelle2026`, no root install), reached over SSH as an ordinary user: no `sudo`, no
`systemctl`. IPS runs there as a user process the way its memory-scaling
experiments ran it (`python -m server.app.main` under `nohup`, see
`evaluation/memory_scaling/SERVER_GUIDE.md` in the IPS repo). The harness runs on
the same host, exactly like IPS's own `evaluation/MCP-comparison` runners.*

## 0. Topology: everything is local to the server

```
 laptop  --ssh-->  Ubuntu server
                    ├─ IPS (native, user process)      http://localhost:8000
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

- start the server and the workers with `setsid nohup ... &` so they survive a
  dropped connection (the box has neither `tmux` nor `screen` and no way to install
  them; this is also how the IPS guide runs its day-long matrices);
- read dashboards through a tunnel: `ssh -L 8000:localhost:8000 user@server`
  (and `:3000` / `:9090` if the monitoring stack is up).

Do not run the harness on the laptop against a tunnelled IPS: an attempt keeps a
session for up to an hour and the stdio MCP must sit next to the server anyway.

## 1. Server prerequisites (one-time)

### 1a0. Isabelle2026 in the home directory (no sudo)

The problems were checked on Isabelle2026 (final). Heaps and user settings are
per version, so the server's Isabelle must be that one. Unpacking the official
tarball in `$HOME` is enough; nothing needs root.

```bash
cd ~
curl -fLO https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/Isabelle2026_linux.tar.gz \
  || curl -fLO https://proofcraft.systems/isabelle/dist/Isabelle2026_linux.tar.gz
tar xzf Isabelle2026_linux.tar.gz          # -> ~/Isabelle2026 (x86_64 build)
export PATH=$HOME/Isabelle2026/bin:$PATH
isabelle version                           # Isabelle2026
echo 'export PATH=$HOME/Isabelle2026/bin:$PATH' >> ~/.bashrc
```

Then register IPS against it (user-level part of the native setup: REPL
component, Scala backend, ML heap cap under `~/.isabelle/Isabelle2026/`):

```bash
cd ~/Isabelle-Pool-Server
kill $(cat logs/server.pid) 2>/dev/null     # if a server is running on the old version
sed -i 's/^ISABELLE_VERSION=.*/ISABELLE_VERSION=Isabelle2026/' .env
./deploy/native_setup.sh                    # no flags: uses the isabelle on PATH
```

An older `~/Isabelle2026-RC2` can stay; nothing points at it once PATH is changed.

### 1a. IPS at a commit with the `FIELD_FROM_IMPORTS` feature

The harness starts every file session on the heap the file's imports name
(`ISABELLE_MCP_LSP_FIELD_FROM_IMPORTS=true`). The feature lives in
`mcp_servers/lsp/config.py` and `pool.py`; it is committed in IPS main.

Every new SSH shell on the box needs the IPS environment first (the IPS guide
says the same):

```bash
cd ~/Isabelle-Pool-Server && source .venv/bin/activate && export PATH=$HOME/Isabelle2026/bin:$PATH
```

Then update the checkout and make sure the feature is there:

```bash
git pull
grep -n FIELD_FROM_IMPORTS mcp_servers/lsp/config.py     # must print the config line
pip install -e ".[mcp]" -e ./client
```

Is IPS already running? `curl -s localhost:8000/healthz` answers `{"status":"alive"}`
if so, and `pgrep -af server.app.main` shows the process. If the pull changed
anything under `server/`, stop that process and start it again (below). If the
pull only touched `mcp_servers/`, nothing to restart: the MCP runs inside the
harness, not inside the server.

Start IPS as a user process (no systemd, no tmux), detached from the SSH session:

```bash
cd ~/Isabelle-Pool-Server && source .venv/bin/activate && export PATH=$HOME/Isabelle2026/bin:$PATH
set -a; . ./.env; set +a                       # nothing loads .env for you outside Docker
setsid nohup python -m server.app.main > logs/server.stdout.log 2>&1 < /dev/null &
echo $! > logs/server.pid
curl -s localhost:8000/healthz                 # alive after 1-2 min (gateway JVM start)
```

`setsid` puts the process in its own session so a closed SSH connection cannot
send it a hangup; `nohup` and the redirections cover the rest. You can log out
right after `echo $!`.

Check on it later with `pgrep -af server.app.main` and the health endpoint.
Stop it with `kill $(cat ~/Isabelle-Pool-Server/logs/server.pid)` and wait for
`pgrep -af 'server.app.main|poly'` to come back empty before starting again
(the server closes its sessions on SIGTERM; a leftover `poly` is a session that
did not). `systemd-run --user --scope` in front of the python command gives the
server its own cgroup, as the memory-scaling runs did, but it needs
`loginctl enable-linger $USER` once and is optional here.

(If the checkout predates the commit, `git apply ~/GitHub/nearAI_Isabelle/scripts/ips-field-from-imports.patch`
is the same change.)

### 1b. Heaps

Each problem file imports a distribution session; the heap for it must exist under
`~/.isabelle/Isabelle2026/heaps/<platform>/` of the user that runs IPS. Build
them as that user with the server idle (a HOL-Analysis build needs several GB and
the IPS guide measured about 45 min for it on this box):

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

All copies go through git: commit on the laptop, push, pull on the server.
`.gitignore` keeps `config/model.json`, `runs/`, `db.sql`, `.venv/` and
`benchmarks/` out, so a pull never touches the key, the results or the venv.

```bash
# laptop
git push origin main
# server, first time
git clone git@github.com:FullBackward/nearAI_Isabelle.git ~/nearAI_Isabelle
# server, every later update (agentlib.py / run_isabelle_solver.py changes need no reinstall)
cd ~/nearAI_Isabelle && git pull
```

On the server:

```bash
cd ~/GitHub/nearAI_Isabelle
python3 -m venv .venv && .venv/bin/pip install "mcp>=1.2,<2" requests pyyaml httpx pytest \
    -e ~/Isabelle-Pool-Server/client

# tell the harness where the IPS checkout is (default ~/GitHub/Isabelle-Pool-Server)
export ISABELLE_POOL_SERVER=~/Isabelle-Pool-Server      # put it in ~/.bashrc so every SSH shell has it

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

Paste it into the server's terminal with a silent prompt (`read -s` shows
nothing and keeps the key out of the shell history):

```bash
mkdir -p -m 700 ~/.secrets
read -rs -p "DeepSeek key: " K && printf '%s\n' "$K" > ~/.secrets/deepseek_api.txt && unset K
chmod 600 ~/.secrets/deepseek_api.txt
wc -c ~/.secrets/deepseek_api.txt        # a few dozen bytes; no need to ever cat it
```

Then `config/model.json` (gitignored, excluded from the rsync), pointing at that file:

```bash
cat > config/model.json <<EOF
{
  "host": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-v4-pro",
  "apikey_file": "$HOME/.secrets/deepseek_api.txt",
  "context_window": 1000000,
  "merge_reasoning": false,
  "compact_at": 0.8
}
EOF
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
| number of workers | shell loop below | each worker holds its file session (1.5-4 GB) plus up to 2 warm scratch sessions for `run_code`/`multi_attempt`, plus provers |
| `ISABELLE_POOL_SIZE` | IPS `.env` (default 3) | >= 3 x workers; a full pool makes the server refuse scratch sessions (the harness frees idle ones and retries, but each refusal costs a turn) |
| `ISABELLE_MEMORY_PRESSURE_THRESHOLD` | IPS `.env` (default 80 %) | percent of **host** RAM on a native install |

Start with 4 workers and `ISABELLE_POOL_SIZE=12` (edit `.env`, then stop and start
the IPS process as in 1a; the memory-scaling runs used 40 on this box). For the
single Q1 run, 3 is the minimum and 6 is comfortable. The IMO tier has only 36 rows, so more than 6 workers gains little; the
miniF2F pilot (60 problems x 2 arms) can use 6-8 on this box. Sledgehammer spawns
several provers per call; 32 cores cover 6 workers comfortably.

## 5. Running (paid from here on; owner approval per run)

### 5a. The first run: Q1, one attempt, plain arm

One SSH shell. The attempt is detached, so the shell can be closed once it has
started; it ends by itself (4 h wall clock at most, no step cap, as upstream).

```bash
cd ~/nearAI_Isabelle && source .venv/bin/activate
export ISABELLE_POOL_SERVER=~/Isabelle-Pool-Server
curl -s localhost:8000/healthz                                                        # IPS up?
.venv/bin/python scripts/bigstep_check.py problems/imo2026/isabelle/imo_2026_p1.thy   # PASS? (free)

mkdir -p runs
setsid nohup .venv/bin/python run_isabelle_solver.py --problem imo_2026_p1 --arm plain \
      --timeout 14400 > runs/q1_plain_rep0.log 2>&1 < /dev/null &
echo $!                                                                               # its PID
```

Watch it:

```bash
T=runs/plain/imo_2026_p1/rep0/transcript.jsonl
.venv/bin/python scripts/transcript_view.py $T --summary        # one line per model call / tool call so far
.venv/bin/python scripts/transcript_view.py $T --last 3         # the last few, with reasoning and tool results
.venv/bin/python scripts/transcript_view.py $T --follow         # keep printing as the attempt goes on (Ctrl-C to stop)
.venv/bin/python scripts/transcript_view.py $T --full | less    # everything, untruncated
cat runs/plain/imo_2026_p1/rep0/imo_2026_p1.thy                 # the file as the model has it right now
tail -f runs/q1_plain_rep0.log                                  # harness lines: opened, nudges, verdict
tail -1 runs/results.jsonl | python3 -m json.tool               # the result row, once it is over
```

What the attempt leaves in `runs/plain/imo_2026_p1/rep0/`:

| file | content |
|---|---|
| `transcript.jsonl` | one line per model call with the exact request (system prompt, every message, the tool schemas) and the full reply (content, reasoning, tool calls, finish reason, usage, seconds); one line per tool execution (arguments, result, seconds). Written as it happens, so a timeout loses nothing. |
| `transcript.md` | the same conversation rendered for reading, nothing truncated, with a per-call token table. Written when the attempt ends, including after a timeout. |
| `imo_2026_p1.thy` | the file as the model last wrote it; the verdict is our own re-check of it |

`--arm skeleton` runs the other arm; `--rep 1` a second attempt in a new
directory (`--rep 0` again overwrites the first).

# 5b. the IMO 2026 tier: 6 problems x 2 arms x 3 repeats = 36 rows
.venv/bin/python harness/ib.py queue-init --source imo2026 --arm plain skeleton --repeats 3
.venv/bin/python harness/ib.py queue-status

# 5c. workers, detached (survive logout); --loop 0 = run until the queue drains
for i in 1 2 3 4; do
  setsid nohup .venv/bin/python run_isabelle_solver.py --loop 0 --owner "w$i" \
        --timeout 14400 > runs/worker$i.log 2>&1 < /dev/null &
  echo $! >> runs/workers.pid
done
pgrep -af run_isabelle_solver        # four of them
```

`export ISABELLE_POOL_SERVER=...` must be in the shell that starts the workers (it
is inherited); the one-off attempt in 5a inherits it the same way.

Budgets: no step cap and 4 h wall clock per attempt; the skeleton arm's `fill_sorries` jobs
are capped at 30 s of sledgehammer per `sorry` and 600 s per job. Worst case for
the tier is 36 attempts x 4 h divided by the worker count.

Monitoring (any later SSH session):

```bash
.venv/bin/python harness/ib.py queue-status
tail -f runs/worker1.log
tail -f ~/Isabelle-Pool-Server/logs/server.log   # IPS log (gateway JVM: logs/gateway-jvm.log)
curl -s localhost:8000/                         # pool, memory, builds in flight
```

To stop the workers early: `kill $(cat runs/workers.pid)`; the attempt in flight
is recorded as failed and its queue row stays `claimed`.
A worker that dies leaves its rows `claimed`; put them back with
`harness/ib.py requeue claimed` (one row: `harness/ib.py release <problem> --arm A --rep R --status todo`)
and start the worker again.

### 5b. The rest of IMO 2026: one pass, then repeats

`scripts/imo2026_pass.py` drives the comparison in two stages on the server;
it only wraps the queue and the worker, so attempts are exactly as in 5a.

```bash
cd ~/nearAI_Isabelle && source .venv/bin/activate && export ISABELLE_POOL_SERVER=~/Isabelle-Pool-Server
git pull && .venv/bin/python -m pytest -q tests && .venv/bin/python harness/leaves.py
curl -s localhost:8000/healthz && pgrep -af 'run_isabelle_solver|poly' || echo "no leftovers"

# stage 1: every problem once on each arm (P1 rows are settled from results.jsonl, not re-run)
.venv/bin/python scripts/imo2026_pass.py init
.venv/bin/python scripts/imo2026_pass.py launch          # paid: one worker, --loop 0, 4 h per attempt
.venv/bin/python scripts/imo2026_pass.py status          # any time; the worker log is runs/imo-<stamp>.log
.venv/bin/python scripts/transcript_view.py runs/<arm>/<problem>/rep0/transcript.jsonl --follow --summary

# when the queue shows no todo/running rows:
.venv/bin/python scripts/imo2026_pass.py report          # table + recommendation + subsets/imo2026_repeat.txt

# stage 2 (if the report says so):
.venv/bin/python scripts/imo2026_pass.py repeat 3        # or `repeat 3 --all`
.venv/bin/python scripts/imo2026_pass.py launch
```

Ten attempts at one to two hours each: expect stage 1 to take most of a day.
If the worker dies (server reboot, OOM), `launch` again: the queue reaps the
dead claim and the worker continues from the next todo row. Kill with
`pkill -f run_isabelle_solver` and clean up `poly` as in 5a if a build was
in flight.

### 5c. Deploying a Pool Server change between attempts

The staged filler (2026-11-10) and the sledgehammer-budget fix (2026-11-09)
live in the IPS checkout and its Scala/ML backend; a restart drops live
sessions, so do it between attempts:

```bash
cd ~/nearAI_Isabelle && .venv/bin/python scripts/imo2026_pass.py stop     # worker finishes its row and exits
.venv/bin/python scripts/imo2026_pass.py status                            # wait for "worker: none running"
cd ~/Isabelle-Pool-Server && git pull && isabelle scala_build
pkill -f server.app.main; sleep 5; pgrep -af poly || echo "no stray prover"
setsid nohup python -m server.app.main > logs/server.stdout.log 2>&1 < /dev/null &
sleep 90; curl -s localhost:8000/healthz
cd ~/nearAI_Isabelle && git pull && .venv/bin/python -m pytest -q tests
# stage 1 rerun: the forced arm once more on all six, as rep 1
.venv/bin/python scripts/imo2026_pass.py --arms skeleton_forced repeat 2 --all
.venv/bin/python scripts/imo2026_pass.py launch
```

## 6. Results

```bash
.venv/bin/python analyze.py --pair plain skeleton --source imo2026
```

Results travel by git too. `runs/` is ignored on purpose (it holds every
attempt's working files), so put the pieces worth keeping on a results branch
with a forced add, and pull that branch on the laptop:

```bash
# server
git checkout -b results-$(date +%F)
git add -f runs/results.jsonl runs/*/imo_2026_p*/rep*/transcript.jsonl \
           runs/*/imo_2026_p*/rep*/transcript.md runs/*/imo_2026_p*/rep*/*.thy runs/*.log
git commit -m "results: IMO 2026 attempts $(date +%F)"
git push -u origin HEAD
git checkout main
# laptop
git fetch && git checkout results-<date>
```

Never add `config/model.json` or `db.sql`; the ignore rules refuse them without
`-f`, and the forced add above names only the result files.

`runs/results.jsonl` has one row per attempt (status, steps, tokens, fills, wall
time, verifier report, `transcript` path); `runs/<arm>/<problem>/rep<N>/` the final
theory, `transcript.jsonl` and `transcript.md`. `db.sql` (SQLite) holds the same
messages for every attempt of this checkout and is what `transcript.md` is
rendered from.

## 7. Go / no-go

- [ ] `grep FIELD_FROM_IMPORTS mcp_servers/lsp/config.py` finds the feature in the IPS checkout, and the running IPS was started from that checkout
- [ ] `curl localhost:8000/api/v1/heaps/available` lists HOL-Computational_Algebra, HOL-Library, HOL-Analysis (and HOL-Number_Theory for miniF2F)
- [ ] `curl -sI https://api.deepseek.com` answers
- [ ] `bigstep_check.py` prints six `PASS`; `selftest` and `pytest` pass
- [ ] `ISABELLE_POOL_SERVER` exported; `config/model.json` points at a mode-600 key file; model id confirmed
- [ ] `ISABELLE_POOL_SIZE` >= 3 x workers; server and workers started with `setsid nohup`, PIDs saved
- [ ] the owner has approved the spend for this run
