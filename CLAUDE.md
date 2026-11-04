# CLAUDE.md

## What this repo is

An Isabelle/HOL port of nearai/putnambench-deepseek built to answer one question: does
forcing a `sorry`-skeleton + server-side `fill_sorries` workflow (Isabelle Pool Server LSP
MCP) beat per-goal sledgehammer? Plain Python 3.11, no build system; `.venv/` holds `mcp<2`,
`requests`, `httpx`, `pyyaml` and the Pool Server client (`pip install -e
~/GitHub/Isabelle-Pool-Server/client`). The benchmarks live in `benchmarks/` (gitignored
clones), results in `runs/` (gitignored). README.md has the setup and run commands;
docs/experiment-design.md the design and open decisions.

## Architecture

- `agentlib.py` -- vendored upstream, do not refactor. Two additions marked `[nearAI_Isabelle]`
  (`apikey_file`, `USAGE_LOG`).
- `run_isabelle_solver.py` -- the harness. One attempt = stage (`ib.cmd_stage`) -> start the LSP
  MCP through `harness/mcp_bridge.MCPBridge` -> `isabelle_open` -> register tools
  (`read_file`/`write_file`, the arm's MCP tools with `file_path` injected, `completed`,
  `disproved`/`write_disproof`) -> `agent.run` with `should_continue` nudging -> re-verify ->
  append `runs/results.jsonl`. The solver rule lives in `extract_solver_calls` /
  `sanctioned_from_output`; the skeleton arm's automatic fill in `_auto_fill`.
- `harness/arms.py` -- the only place arms differ: `mcp_tools`, `auto_fill`, `strategy`.
- `harness/ib.py` -- manifest (`prepare`), staging (proof stripping via `sorryfy`, PutnamBench
  answer inlining via `inline_solution`), the verifier (`textual_checks` + `build_check`),
  `select`, the flock TSV queue. `ib.py selftest` covers the textual checks; run it after any
  change there.
- `scripts/statement_probe.py` -- HTTP-only (no MCP) pass: parse + sledgehammer-only baseline.

## Conventions

- Keep upstream's style: long *why* comments, `# ---- section ----` banners.
- Never print or copy API keys; `config/model.json` points at a key file.
- Do not commit without the owner's review.
- The Pool Server must have the heaps the problems import (`isabelle build -b HOL-Number_Theory`
  inside the container; HOL-Analysis for PutnamBench). Without them `isabelle_open` times out.
- Known upstream defects skipped by `prepare`: `putnam_1991_a4` (no `end`), `putnam_2023_a6`
  (theory named Scratch).
