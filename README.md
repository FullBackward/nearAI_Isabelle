# nearAI_Isabelle

An Isabelle/HOL port of [nearai/putnambench-deepseek](https://github.com/nearai/putnambench-deepseek):
the same single-tool-loop agent harness (`agentlib.py`, vendored), the same
"only the verifier can end the run" rule, but the agent proves **Isabelle**
theorems through the [Isabelle Pool Server](https://github.com/Deep-LCF/Isabelle-Pool-Server)
LSP MCP instead of running Lean in bash.

The purpose of the repository is one controlled experiment:

> Does forcing the agent to work **skeleton-first** -- write an Isar skeleton
> with `sorry` at every leaf, let the server's `fill_sorries` run sledgehammer
> on all of them at once, iterate on the survivors -- prove more theorems (or
> the same theorems cheaper) than letting it call sledgehammer one goal at a
> time?

Two arms, identical in everything but how sledgehammer is reached
(`harness/arms.py`):

| arm | sledgehammer access | automatic? |
|---|---|---|
| `plain` | `isabelle_sledgehammer(line, subgoal)` on one open goal | no |
| `skeleton` | `fill_sorries` on every `sorry` in the file; no per-goal tool | yes: every `write_file` that parses cleanly and still has `sorry`s is filled and written back |
| `skeleton_forced` | as `skeleton`, plus the **leaf rule** (`harness/leaves.py`): the model never writes a closing method; every leaf is `sorry` until the filler proves it, and only filler-written lines (verbatim, same statement, same enclosing goals) are accepted | yes |
| `fill_optional` (extra) | both | no |

`skeleton_forced` exists because the first Q1 plain run (2026-11-05) proved the
problem with 338 hand-written closers and zero sledgehammer calls: nothing in
`skeleton` stops a model from writing `by simp` everywhere and never leaving a
`sorry` for the filler. In the forced arm `write_file` rejects any `by`, `.`,
`..`, `apply`, `qed <method>` or goal-closing `proof <method>` the filler did
not produce for that statement, so the treatment cannot be skipped. The
results row carries `leaf_rejections`.

In every arm the harness **enforces** the solver rule: `write_file` rejects a
`metis` / `smt` / `meson` / `moura` call that did not come out of a
sledgehammer or fill result during the attempt. The model cannot shortcut the
comparison by hand-writing ATP proofs.

See [docs/experiment-design.md](docs/experiment-design.md) for the design,
the benchmark choice and the open decisions.

## Layout

| path | what |
|---|---|
| `agentlib.py` | vendored upstream agent loop (+ `apikey_file`, token-usage capture; marked `[nearAI_Isabelle]`) |
| `run_isabelle_solver.py` | the harness: stages a problem, starts the LSP MCP, registers the tools of the arm, runs the agent, re-verifies, appends `runs/results.jsonl` |
| `harness/ib.py` | benchmark side (the `pb.py` port): manifest, staging, **verifier**, subset selection, flock queue |
| `harness/arms.py` | the arms: tool allow-lists, auto-fill flag, strategy prompts |
| `harness/mcp_bridge.py` | sync wrapper over one MCP stdio server (agentlib is synchronous) |
| `scripts/statement_probe.py` | LLM-free pass: does the statement parse under Isabelle2026, does bare sledgehammer already close it |
| `scripts/bigstep_check.py` | LLM-free, session-free: does a statement file build through the server's bigstep endpoint (quick_and_dirty injected so `sorry` is tolerated) |
| `scripts/transcript_view.py` | readable, live view of an attempt's `transcript.jsonl` (`--summary`, `--last N`, `--follow`, `--full`) |
| `problems/imo2026/` | the six IMO 2026 problems: `isabelle/` our Isabelle/HOL statements (see its README), `lean/` the AxiomMath Lean statements they translate |
| `analyze.py` | per-arm / per-category tables, paired per-problem comparison with McNemar |
| `benchmarks/` | (gitignored) miniF2F and PutnamBench checkouts |
| `runs/` | (gitignored) bench dirs with per-attempt `transcript.jsonl` (every model request and reply, every tool call) and `transcript.md`, `results.jsonl`, `defects/` |
| `scripts/ips-field-from-imports.patch` | the IPS change the harness relies on (`FIELD_FROM_IMPORTS`), kept for checkouts that predate its commit |
| `docs/server-runbook.md` | running the whole thing on a remote (SSH-only) server |

## Setup

```bash
# 1. the prover: Isabelle Pool Server running on :8000 with the heaps the
#    benchmark needs (miniF2F: HOL-Number_Theory covers everything;
#    PutnamBench also needs HOL-Analysis, HOL-Algebra, HOL-Combinatorics)
cd ~/GitHub/Isabelle-Pool-Server && docker compose up -d
docker compose exec -T isabelle-pool-server isabelle build -b HOL-Number_Theory

# 2. this repo
cd ~/GitHub/nearAI_Isabelle
python3 -m venv .venv && .venv/bin/pip install "mcp>=1.2,<2" requests pyyaml httpx \
    -e ~/GitHub/Isabelle-Pool-Server/client
cp config/model.example.json config/model.json     # DeepSeek via apikey_file (or paste "apikey")

# 3. benchmarks + manifest
git clone --depth 1 --filter=blob:none --sparse https://github.com/facebookresearch/miniF2F benchmarks/minif2f
( cd benchmarks/minif2f && git sparse-checkout set isabelle )
git clone --depth 1 --filter=blob:none --sparse https://github.com/trishullab/PutnamBench benchmarks/putnambench
( cd benchmarks/putnambench && git sparse-checkout set isabelle informal )
.venv/bin/python harness/ib.py prepare --source minif2f --root benchmarks/minif2f/isabelle --split test
.venv/bin/python harness/ib.py prepare --source putnambench --root benchmarks/putnambench/isabelle
.venv/bin/python harness/ib.py prepare --source imo2026 --root problems/imo2026/isabelle   # ships with the repo
.venv/bin/python harness/ib.py selftest
.venv/bin/python scripts/bigstep_check.py problems/imo2026/isabelle/*.thy         # statements build? (P2 needs HOL-Analysis)
```

## Run

```bash
# probe (no LLM): parse check + sledgehammer-only baseline, writes probe.json
.venv/bin/python scripts/statement_probe.py --source minif2f --split test --sh-timeout 60

# pick the pilot subset: 60 miniF2F-test problems, stratified by category,
# dropping the ones sledgehammer closes alone and the ones that do not parse
.venv/bin/python harness/ib.py select --source minif2f --probe probe.json \
    --exclude-unparsed --exclude-sh-trivial --n 60 --stratify category --out subsets/pilot.txt

# one problem, one arm
.venv/bin/python run_isabelle_solver.py --problem mathd_algebra_276 --arm skeleton

# the experiment: queue every (problem, arm) pair, run 2 workers
.venv/bin/python harness/ib.py queue-init --subset subsets/pilot.txt --arm plain skeleton --repeats 1
for i in 1 2; do nohup .venv/bin/python run_isabelle_solver.py --loop 0 > runs/worker$i.log 2>&1 & done
.venv/bin/python harness/ib.py queue-status

# results
.venv/bin/python analyze.py --pair plain skeleton

# the IMO 2026 tier: all six problems, both arms, 3 repeats each
.venv/bin/python harness/ib.py queue-init --source imo2026 --arm plain skeleton --repeats 3
```

Budgets follow upstream: no step cap, wall clock only (`--timeout 14400`, 4 h per
attempt; `--max-steps N` adds a turn cap if you want one). Two inner limits
matter: the session's check of a written file (`IB_LOAD_TIMEOUT`, 600 s; a check
that expires is reported as an error naming the running line, and `completed()`
will not build such a file) and the verifier's build (`IB_BUILD_TIMEOUT`,
1800 s; a build service that does not answer is reported as an outage, not as a
failed proof). Two workers is the practical ceiling on a 16 GB host: each
attempt holds one Isabelle session (1.5-4 GB) plus the sledgehammer provers.

## What counts as solved

`completed()` (and the harness again after the run) passes only when, for the
final `.thy`:

1. no `sorry`/`oops` outside comments and no escape hatch (`axiomatization`,
   `ML*`, `setup`, `oracle`, `declare [[...]]`, `notation`/`syntax`, `hide_*`,
   `consts`, ...);
2. the theory header and the theorem statement are the frozen ones (comments
   stripped, whitespace normalized) and the theorem keeps its name;
   multi-target files (IMO 2026: P1 states five theorems, P3 six) freeze
   every definition block and every theorem statement, and all of them must
   be proved -- the same rule as the Lean harnesses' `verify.py`;
3. no helper definition reuses a name that occurs in the statement (Isabelle
   lets a local `definition prime` shadow the imported one), and no ML inside a
   proof method (`tactic`/`raw_tactic`);
4. the whole theory builds (`isabelle build`, through the Pool Server's
   bigstep endpoint).

The bytes that passed are kept as `verified.thy` in the bench dir, the file is
frozen from that moment on (the model may still write its report, not the
file), and the harness's own final verdict is taken on those bytes. A run that
ends by timeout is judged on the working file, but only built when the session
finished checking it. `disproved()` is accepted only after `write_disproof`
reported a passing build.

PutnamBench's factored answers follow upstream: `wsolution` inlines the
reference answer (leaderboard setting), `full` leaves `undefined` for the agent
to replace with the type frozen.
