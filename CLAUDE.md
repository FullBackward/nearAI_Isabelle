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

- `agentlib.py` -- vendored upstream, do not refactor. Additions marked `[nearAI_Isabelle]`:
  `apikey_file`, `USAGE_LOG`, and the `CHAT_SINK`/`TOOL_SINK` hooks (`_stream_chat` wraps
  `_stream_chat_inner`) that the harness points at each attempt's `transcript.jsonl`.
- `run_isabelle_solver.py` -- the harness. One attempt = stage (`ib.cmd_stage`) -> start the LSP
  MCP through `harness/mcp_bridge.MCPBridge` -> `isabelle_open` -> register tools
  (`read_file`/`write_file`, the arm's MCP tools with `file_path` injected, `completed`,
  `disproved`/`write_disproof`) -> `agent.run` with `should_continue` nudging -> re-verify ->
  write `transcript.jsonl` + `transcript.md` into the bench dir (`_Transcript`,
  `_render_transcript_md`) and append `runs/results.jsonl`. `_Attempt.mcp` absorbs server capacity
  refusals (release idle scratch sessions, wait, retry); results and tool descriptions that name the hidden
  memory/heap tools are rewritten. `_Attempt.diagnostics` asks `isabelle_sync` first: a session check
  that hit its budget (`IB_LOAD_TIMEOUT`) is an error naming the running line, and `completed()`
  refuses to build such a file; a build service that does not answer is a `verifier unavailable`
  outage, not a failed completion. A passing `completed()` writes `verified.thy` and freezes
  `write_file`; `_final_verify` (run before the session is closed) judges those bytes, and never
  builds a file the session is still running. Every MCP call the harness makes is an `mcp`
  record in `transcript.jsonl`. The solver rule deliberately does NOT bind a sledgehammer
  result to the goal it was found for (owner decision, 2026-11-05: metis transplants are a finding,
  see docs/experiment-design.md). The solver rule lives in `extract_solver_calls` /
  `sanctioned_from_output`; the skeleton arm's automatic fill in `_auto_fill`.
- `harness/arms.py` -- the only place arms differ: `mcp_tools`, `auto_fill`, `strategy`,
  `filler_only`. The `skeleton_forced` arm adds the leaf rule (`harness/leaves.py`): the model
  never writes a closing method; `write_file` accepts only `sorry` or a leaf the filler wrote,
  verbatim, keyed by statement and the chain of enclosing goals (`_Attempt.filler_keys`, seeded
  from the staged file, extended from every fill result). `leaves.py selftest` after any change.
- `harness/ib.py` -- manifest (`prepare`), staging (proof stripping via `sorryfy` /
  `sorryfy_all`, PutnamBench answer inlining via `inline_solution`), the verifier
  (`textual_checks` + `build_check`; `_multi_target_checks` for files in `MULTI_TARGET_SOURCES`
  where every definition block and every theorem is frozen), `select`, the flock TSV queue.
  `ib.py selftest` covers the textual checks; run it after any change there.
- `problems/imo2026/isabelle/` -- the six IMO 2026 statements (source `imo2026`), hand-translated
  from the AxiomMath/IMO2026 Lean files kept beside them in `problems/imo2026/lean/`; the README
  there records every Lean->Isabelle deviation. Keep them faithful to the Lean files: other
  harnesses are scored on exactly these statements. For a strict comparison the files carry no
  informal problem text (the Lean files have none), only the Lean docstrings as `text` blocks,
  and `prepare` sets `informal_statement` to None for this source.
- `scripts/statement_probe.py` -- HTTP-only (no MCP) pass: parse + sledgehammer-only baseline.
- `scripts/bigstep_check.py` -- does a statement file build (bigstep only, `quick_and_dirty`
  injected into the copy it sends). Use this, not sessions, to validate statement files.

## Conventions

- Keep upstream's style: long *why* comments, `# ---- section ----` banners.
- Never print or copy API keys; `config/model.json` points at a key file.
- Do not commit without the owner's review.
- The Pool Server must have the heaps the problems import (`isabelle build -b HOL-Number_Theory`
  inside the container; HOL-Analysis for PutnamBench and IMO 2026 P2; HOL-Library for P4).
  As of 2026-11-04 the server has HOL-Computational_Algebra, HOL-Number_Theory, HOL-Library
  and HOL-Analysis (HOL-Algebra and HOL-Combinatorics still missing).
  Without them `isabelle_open` times out and bigstep builds the parent session from source.
- The IPS checkout must have the MCP's `FIELD_FROM_IMPORTS` feature (committed in IPS main;
  `scripts/ips-field-from-imports.patch` is the same change for older checkouts).
  `docs/server-runbook.md` is the remote-server procedure.
- Anything that spends money (a model call on the owner's DeepSeek key) needs the owner's
  explicit go-ahead for that run first. Tests, selftest, probe and bigstep checks are free.
- Known upstream defects skipped by `prepare`: `putnam_1991_a4` (no `end`), `putnam_2023_a6`
  (theory named Scratch).
