# Experiment design: skeleton-first `fill_sorries` vs per-goal sledgehammer

*Status: draft for review, 2026-11-04. Nothing has been run beyond smoke tests.*

## Question

The Isabelle Pool Server (IPS) LSP MCP offers `isabelle_fill_sorries`: the agent
writes an Isar proof with `sorry` at every goal it cannot close, the server runs
sledgehammer on all of them, and returns the patched text. Is that workflow --
when the agent is made to use it -- better than the ordinary one where the agent
calls `isabelle_sledgehammer` on one open goal at a time?

"Better" is measured as (primary) problems solved, and (secondary) steps, wall
time, output tokens and tool time per solved problem.

## Harness

A port of nearai/putnambench-deepseek. Same loop (agentlib: streaming
tool-calling, SQLite trajectories, compaction at 80% of context), same rule
that only `completed()` passing the verifier ends a run (otherwise the model is
nudged to continue), same `disproved()` escape for defective formalizations.
Differences forced by Isabelle:

- no bash: one `.thy`, `read_file` / `write_file`, and the LSP MCP's read-only
  query tools (file_path injected by the harness);
- the verifier is `harness/ib.py`: textual rules + `isabelle build` through
  IPS's bigstep endpoint (see README "What counts as solved");
- finite default budgets (150 steps, 60 min) because this is a paired
  comparison on a 16 GB machine, not a leaderboard submission.

## Arms

| | plain | skeleton | fill_optional |
|---|---|---|---|
| per-goal `isabelle_sledgehammer` | yes | **no** | yes |
| `isabelle_fill_sorries` / status / cancel | no | yes | yes |
| `write_file` auto-fills a clean file with sorries and writes the patch back | no | **yes** | no |
| prompt strategy | sledgehammer stuck goals | skeleton first, iterate on survivors | neutral |

Everything else (model, temperature, system prompt skeleton, query tools,
verifier, budgets, solver rule) is identical. The arms are interleaved in the
queue so a partial run is still paired per problem.

**Solver rule, enforced.** `write_file` rejects any `metis`/`smt`/`meson`/
`moura` call that did not appear in a sledgehammer or fill result during the
attempt (whitespace-normalized method call match). Prior IPS comparison logs
showed agents writing `metis` by hand dozens of times when the rule was only
worded; here hand-written ATP proofs are impossible in both arms, so the
difference between arms is only *how* sledgehammer is reached.

**Why `skeleton` hides the per-goal tool.** "Forcing" has to mean something
testable: with `isabelle_sledgehammer` available, a model that ignores the
instructions reverts to the plain workflow and the arm measures prompt
compliance, not the feature. The `fill_optional` arm exists to measure that
voluntary uptake separately, if wanted.

## Benchmark (recommendation)

PutnamBench-Isabelle (640 statements; the paper's best Isabelle result was a
handful solved) is too hard and too slow to be the *comparison* benchmark on
one laptop-class server: most attempts would end as paired failures, which
carry no information about the arms. The recommendation is:

1. **Pilot: miniF2F-test Isabelle, 60 problems.** Standard Isabelle benchmark
   with well-known sledgehammer baselines (~20% solo, ~39% DSP). Steps:
   - `scripts/statement_probe.py` over all 244: which statements parse under
     Isabelle2026 (the files target Isabelle2021/22; 71 of the 244 ship with
     proofs, which `prepare` strips), and which bare statements plain
     sledgehammer already closes in 60 s (**sledgehammer-trivial**).
   - `ib.py select --exclude-unparsed --exclude-sh-trivial --n 60 --stratify
     category`: a seeded, category-proportional sample of the non-trivial,
     parseable problems. Excluding the trivial ones removes the problems both
     arms get for free and concentrates the budget where the arms can differ.
   - 1 repeat per arm first (120 attempts, roughly 10-15 h with 2 workers);
     then 2 more repeats on the discordant problems if the McNemar count is
     close.
2. **Hard tier (optional, after the pilot): 30 PutnamBench-Isabelle problems**,
   `wsolution` variant, stratified by year, probed the same way. Needs the
   HOL-Analysis heap built on the server (1-2 h) and a bigger step/time budget.

Statistics: pass@1 per arm; per-problem paired outcome with the exact McNemar
test on discordant pairs (`analyze.py --pair plain skeleton`); category
breakdown; effort metrics on the problems both arms solved.

## IMO 2026 tier (added 2026-11-04)

The owner wants the harness scored on the six IMO 2026 problems, because the
published IMO 2026 harnesses (AxiomProver, MechMath, humanfia, …) are all scored on
the same formal statements -- AxiomMath/IMO2026's `problem.lean` files -- and a
partial set would not be comparable. `problems/imo2026/isabelle/` holds Isabelle/HOL
translations of all six (P1 is the pre-existing verified file from
`isabelle-humanize`; P2–P6 are new, deviations listed in the folder README);
`problems/imo2026/lean/` keeps the Lean originals. To keep the comparison strict
the Isabelle files carry exactly what the Lean files carry: the formal statement
and the per-definition docstrings, no informal problem text, and the prompt's
informal-statement slot is empty for this source.

What differs from miniF2F/PutnamBench files:

- **Multi-target.** P1 states five theorems and P3 six (sanity statements plus
  the main one), with auxiliary definitions. As in the Lean `verify.py`, a
  problem is solved only when *every* `sorry` is gone, every definition block
  and every statement is unchanged, and the whole file builds. `ib.py` freezes
  all of them (`targets`, `sigs`, `frozen_blocks`, `pristine_defs` in the
  manifest entry; `_multi_target_checks` in the verifier).
- **Heaps.** P2 needs `HOL-Analysis`, P4 `HOL-Library`; the rest build on `HOL`
  or `HOL-Computational_Algebra`.
- **Statistics.** Six problems cannot separate the arms on pass rate; the tier
  is a showcase and a per-problem case study (steps, tokens, fills, wall time
  per arm, several repeats). The miniF2F pilot remains the statistical
  comparison.
- **Expected difficulty.** P1 was solved by DeepSeek V4 Pro in `isabelle-humanize`
  (1059-line proof, ~$5). P5 is pure real algebra and within reach. P4 and P3
  are game/combinatorics arguments with real-valued encodings; P6 is a hard
  number-theory result; P2 is synthetic geometry on `real^2`, where
  sledgehammer is weak. A realistic outcome is P1 and P5 solved, the others
  not, in both arms.

Validation (2026-11-04): all six statement files build via
`scripts/bigstep_check.py` against the server (HOL-Analysis and HOL-Library
heaps built on the server for the purpose; see `runs/bigstep_check_imo2026.log`).

## Open decisions (for review)

1. Benchmark: miniF2F-test pilot (recommended) vs a PutnamBench slice first.
2. `skeleton` without per-goal sledgehammer (recommended, cleaner contrast)
   vs with it (closer to "IPS as shipped plus a prompt").
3. Budgets: 150 steps / 60 min per attempt; `fill_sorries` 30 s per sorry,
   600 s per job. Upstream ran unbounded.
4. Model: DeepSeek V4 Pro (as upstream's hard tier and the IPS comparison runs)
   vs V4 Flash for cost.
5. Imports frozen (current) vs allowing extra HOL-distribution imports
   (PutnamBench notes the stated imports may not suffice for a proof).
6. Statement freeze is textual + shadow guard (as upstream). A semantic check
   (re-stating the pristine theorem after the proof) is possible later.

## Known issues found while scaffolding

- The IPS LSP MCP acquires a file session with the file's imports but **no
  `field`**, so the session starts from the plain `HOL` image and loads
  `HOL-Computational_Algebra` & co. from source -- `isabelle_open` times out
  (120 s backend reset) on most miniF2F problems. Fix: derive the field from
  the imports (patch in IPS `mcp_servers/lsp/pool.py`, env
  `ISABELLE_MCP_LSP_FIELD_FROM_IMPORTS`) **and** have the heaps built in the
  container (`isabelle build -b HOL-Number_Theory`; the fresh container only
  had `HOL` and `Pure`).
- Upstream PutnamBench Isabelle files skipped by `prepare`: `putnam_1991_a4`
  (no closing `end`), `putnam_2023_a6` (theory named `Scratch`).
- 7 PutnamBench files import both `HOL-Algebra` and `HOL-Analysis`, which no
  single distribution heap contains; the probe will show whether they load.
- **Memory is the capacity limit, not the pool size.** The container is capped
  at 14 GB; the shared gateway JVM alone sits at ~5 GB RSS and one ML session
  process reached 5 GB (`--maxheap 9216`, the default since `.env` sets no
  `ISABELLE_ML_MAXHEAP_MB`). With one session plus a sledgehammer the server
  was already at the *warning* tier, and the first model smoke run lost its
  `completed()` builds to the gate's 503 until the harness learned to wait it
  out (`IB_BUILD_WAIT_S`) and to retry `isabelle_open`. Practical ceiling on
  this machine: **2 concurrent attempts**, and `ISABELLE_ML_MAXHEAP_MB=4096`
  (or lower) in the server's `.env` is advisable so one session cannot starve
  the other. `ISABELLE_POOL_SIZE=6` is aspirational here.
- A fresh `heap build` leaves the cgroup counting its page cache as used
  memory; a container restart clears it.
