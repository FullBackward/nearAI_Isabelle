# IMO 2026 pass 1: six problems, two arms, one attempt each (2026-11-08/09)

Data: `runs-server/pass1/` (results.jsonl, worker logs, every attempt's final
theory, verified snapshot where it passed, and transcript). Analysis scripts:
the session scratchpad (`analyze_pass1.py`, `stalls.py`, `progress.py`); their
numbers are reproduced here. The P1 cells are the hand-launched runs of
2026-11-05 (the forced P1 ran with the fixed 600 s fill cap, before it scaled).

## Outcome

| problem | plain | skeleton_forced |
|---|---|---|
| P1 | SOLVED 71 min | SOLVED 104 min |
| P2 (HOL-Analysis) | timeout | timeout |
| P3 | timeout, 4/6 targets proved | timeout, 3/6 targets proved |
| P4 | SOLVED 39 min | SOLVED 116 min |
| P5 | SOLVED 31 min | SOLVED 58 min |
| P6 | timeout, 0/1 | timeout, 0/1 |

Same three problems solved by both arms, same three missed by both; no
discordant pair. All six solved files are byte-identical to their verified
snapshots, pass the textual checks, and rebuild on a second Pool Server (see
"Validity" below). Every solved plain proof has zero ATP calls (metis/smt);
every solved forced proof is 100 % filler-written leaves (64 / 22 / 28 ATP
calls in P1 / P4 / P5), so the leaf rule held on every write of the pass.

## Where the time and tokens went

| | plain (6 attempts) | skeleton_forced (6 attempts) |
|---|---|---|
| wall clock | 861 min | 998 min |
| model calls | 2245 | 758 |
| prompt tokens | 864 M (0.79 M uncached) | 146 M (0.61 M uncached) |
| completion tokens | 2.25 M | 1.56 M |
| nudges (model stopped without a tool call) | 931 | 45 |
| per-goal sledgehammer calls / found | 67 / 3 | -- |
| fill rounds, sorries proved / tried | -- | 1 011 / 1 393 (73 %) |

On the three problems both arms solved, plain took 47 min on average and
forced 93 min; the model time was the same (about 35 min each); the difference
is prover time: fill rounds and the model's scratch tests of closers it could
not write into the file.

## The three misses, arm by arm

**P3 plain: a give-up loop, 489 nudges.** The model proved 4 of 6 targets,
then at turn 350 wrote "I was unable to complete a full proof ... in the
available time" and stopped. The harness nudged ("You are not finished, so do
not stop ... Continue now, with a tool call"); the model called `completed()`
(230 times in all, each refused in 0.07 s for the two remaining `sorry`),
wrote the same apology, and stopped again. 490 stop turns in 200 min of model
time, at 600 k tokens of context per call: 1.3 GB of transcript, 588 k
completion tokens, no change to the file after turn 350.

**P6 plain: a give-up loop plus 114 min of sledgehammer.** 42 per-goal
sledgehammer calls, 2 found; the model escalated `timeout_s` to 300 and spent
114 of its 240 min inside them. 425 nudges. The final file shrank from 9 700 to
4 100 chars as the model discarded its attempts; 6 helper lemmas proved, the
main theorem `sorry`.

**P2 plain: still working at the wall, with a 741 k-token context.** No
give-up (17 nudges), 41 writes, 30 helper lemmas proved, the main theorem's
proof still open when time ran out. 13 sledgehammer calls, 0 found, 7 of them
the server's 150 s "Internal server error" (fixed in IPS on 2026-11-09). Model
calls took up to 176 s each at that context size; compaction never triggered
(`compact_at` 0.8 of a 1 M window).

**P2 forced: the file was destroyed.** HOL-Analysis scratch runs
(`isabelle_run_code`) timed out at the server's 30/60/120 s budget (three
`http_500 ... Backend call timed out`), so the model used `write_file` as its
scratchpad: 71 writes alternating the 4.4 k-char theory with 100-1 100-char
test lemmas, each tiny write triggering a one-sorry fill round. The filler
proved almost nothing on these goals (31 / 92 over 54 rounds). The attempt
ended with a 15-line file containing one broken scratch lemma and none of the
frozen targets. 83 min in run_code timeouts, 65 min in fill rounds.

**P3 forced: the filler stops at the hard leaves.** 3 / 6 targets proved,
fills 86 / 187; after the first three rounds (23/30, 16/21, 10/14) the
surviving sorries are the `lower_bound` / `upper_bound` leaves, which no
refinement brought within sledgehammer's reach (rounds of 0/3, 0/4, 1/9, 1/6).
Tool-bound: 118 min of fills and writes against 121 min of model time.

**P6 forced: tool-bound restart loop.** Fills proved 180 / 336, including
rounds of 40/54 on helper structure, but the main skeleton never closed; the
model restarted from smaller skeletons three times (write sizes 6 200 -> 1 000
-> 3 000 -> 1 800 chars) and the attempt ended inside a fill job, polling
`fill_status`. 169 of 240 min in tools.

## What the pass says

1. **Solve rate: tied, 3/6 each, same set.** One rep per cell; the arms
   separate on cost, not on outcome.
2. **Plain is cheaper in prover time and dearer in model tokens.** 6x the
   prompt volume, almost all cache hits, almost all from give-up loops; the
   uncached volume is similar (0.79 M vs 0.61 M).
3. **The per-goal sledgehammer never carried a plain proof.** 0 calls on the
   three solved problems; 67 calls / 3 found on the three misses. The arm's
   treatment is unused when it wins and useless when it loses.
4. **The filler carries the forced proofs, at a price.** 73 % of sorries
   proved overall, 90 %+ on well-stated leaves (P4 round 1: 89/98; P5: 123/131),
   near 0 % on the leaves that matter in the misses (P2: 31/92, P3 late rounds).
   Each round is 10-30 min of wall clock, which halves the model's turn budget
   under a 4 h wall.
5. **The misses are not close.** P2 and P6 have no target proved on either
   arm; P3 has 3-4 of 6 with the hard pair open. Repeating them as-is buys
   variance, not a solution: the P1 flip (fail, then solve) was a metis
   transplant plus a harness blind spot, not luck in the mathematics.

## Validity of the six solved attempts

Checked locally on 2026-11-10 from the copied files: final theory identical to
`verified.thy` (6/6); textual checks pass (6/6); full rebuild on the local
Pool Server passes (6/6): `PASS theory builds; statement frozen; no
sorry/escape hatches` for P1, P4, P5 on both arms. Target statements and
headers match the source files.

## Harness defects the pass exposed (for the next pass)

- **No give-up detection.** The nudge is static; a model that has stopped
  trying is nudged until the wall. 931 nudges cost 2 of the 3 plain misses
  their last 3 hours and most of the pass's tokens. Fix: after K consecutive
  stops without a tool call (K = 3), end the attempt as `gave_up`; the queue
  then moves on. Upstream had a step cap that bounded this; we removed it.
- **`write_file` does not protect the frozen targets.** A write that drops
  the header or a target statement is accepted and only `completed()` refuses
  it. P2 forced spent its last two hours on a file with no theorem in it. Fix:
  run the frozen-header / frozen-target textual checks at write time and
  reject with the reason (the rule already exists in the verifier).
- **Backend timeouts reached the model as `Internal server error`** (run_code
  30/60/120 s, sledgehammer 150 s). IPS fix of 2026-11-09 maps them to 504
  with the budget named; the harness should still clamp `timeout_s` on the
  sledgehammer tool (90 s) and word the result for the model.
- **Context growth.** Plain P2 at 741 k tokens per call: 3 min per model
  turn. `compact_at` should bite earlier (0.5), or the harness should trim
  old tool results.
- **Attempts ending inside a fill job** count the whole job against the
  wall. A fill round should not start when less than its cap remains.
