# Rep 1 of the forced arm: the staged filler on IMO 2026 (2026-11-10)

Data: `runs-server/rep1/` (results.jsonl with the pass-1 rows and the six new
rep-1 rows, the two worker logs `imo-1110-0558.log` and `imo-1110-0706.log`,
every attempt's final theory, the verified snapshot where it passed, and the
transcript). Scripts: `scripts/analysis/rep1_attempt.py`, `rep1_fills.py`,
`rep1_leaf_replay.py` (the last needs Isabelle's `etc/symbols`). Every number
below comes from them. The pass ran the harness at 3840bad: the staged filler
(try0, nitpick, isar retry, split, two sibling sessions), the give-up cap, the
restate advice; the prompt was the pass-1 prompt (no `prompt_sha` in the rows,
no no-limits section). Two workers, 4 h wall, DeepSeek V4 Pro.

## 1. Outcome

The solve set did not move: P1, P4, P5 solved, P2, P3, P6 not, the same three
as pass 1 on both arms. The filler did its part; the three misses are
mathematics the model never found.

| problem | rep 0 (fixed filler) | rep 1 (staged filler) | steps | wall | writes (rejected) | fills: proved/sorries | nudges |
|---|---|---|---|---|---|---|---|
| P1 | solved, 104 min | solved, 178 min | 192 | 10660 s | 25 (5 leaf) | 10: 431/505 | 0 |
| P2 | timeout | timeout | 139 | 14400 s | 17 (1 leaf, 1 frozen) | 28: 2/54 | 4 |
| P3 | timeout | gave up at 151 min | 174 | 9077 s | 25 (3 leaf) | 13: 151/249 | 13 |
| P4 | solved, 116 min | solved, 54 min | 113 | 3261 s | 4 (1 leaf) | 2: 189/193 | 0 |
| P5 | solved, 58 min | solved, 66 min | 42 | 3958 s | 13 (4 leaf) | 5: 252/280 | 0 |
| P6 | timeout | gave up at 213 min | 157 | 12781 s | 42 (8 leaf) | 29: 383/459 | 11 |

Tokens, all six attempts: 181.5 M prompt (rep 0: 146.1 M), 1.85 M completion
(rep 0: 1.56 M); wall 15.0 h (rep 0: 16.6 h, two of which were the 4 h
timeouts the give-up cap now cuts short).

## 2. What the staged filler did

Of 1740 sorries sent, 1408 were closed (81 %). By stage: try0 1141, sledgehammer
265, split 4 (leaves that closed after the mechanical `intro` split), and
nitpick marked 23 statements false (P3 14, P1 6, P2 3). *Four fifths of the
closed leaves never reached sledgehammer*: the cheap stage is where the
skeleton's steps go. Seconds of filler wall per closed leaf, counting the
harness's polling: P4 2, P1 7, P5 7, P6 15, P3 23, P2 1692 (two leaves closed in
51 min of filler: the geometry identities were never within reach).

The 23 nitpick verdicts are a result in themselves: on P3 the model wrote
fourteen intermediate claims that were false as stated, and the filler said so
within 10 s each instead of letting sledgehammer burn 30 s and report `none`.
The "WARNING ... FALSE as written" line was in the model's result every time.

Compared with rep 0 on the same problems: P4 took four writes instead of
seventeen and half the wall; P1 took longer because the model wrote a larger
skeleton (505 sorries against 338) and the fill rounds that go with it (three
writes of 10 to 13 min each, all of it filling); P6 closed 383 leaves against
181 and ended with one `sorry` instead of many. P2 went backwards (2/54 against
31/95) because the model chose a coordinate route whose leaves are
semialgebraic identities, not because the filler lost anything it had.

## 3. The three misses, one by one

**P2 (geometry, HOL-Analysis).** Model. The model reduced the problem to
coordinates and ran into one real-algebraic identity it could neither prove
nor split. It spent 93 min of the 4 h inside `isabelle_run_code`: 77 scratch
runs, 12 of them with a timeout of 300 to 600 s that ran out (74 min). It tested
`sos` in scratch, but `sos` closed only its own toy lemmas (`test_sos_simple`,
`test_sos_only`), never the identity; its closing note that "the leaf rule
prevents me from writing the only method (`sos`) that seems suited" is not
supported by its own scratch log. Three of its intermediate claims were
nitpick-false. The final file has the theorem with a bare `sorry` and no
skeleton. One write would have replaced the whole file with a 126-character
`sos_test` lemma; the frozen-parts guard refused it (in pass 1 the same move
destroyed P2's file).

**P3 (the cake game).** Model. The model proved every definitional fact it
stated (piece lengths, sums, membership) and never produced a skeleton for the
three game statements: `V_eq`, `lower_bound` and `upper_bound` stayed bare
`sorry` from the first write to the last. Fourteen of its helper claims were
false. It stopped at 151 min with 89 min left, after thirteen nudges; the
give-up cap ended the attempt. Nothing in the harness or the server was in its
way: no 5xx, no outage, the longest fill round 17 min.

**P6 (the greedy sequence).** Model, and the closest of the three. Over 42
writes the model built a 709-line development and reduced the problem to one
lemma, `two_terms_common_small_divisor` (any two terms share a divisor in
`(1, a 0]`), which it then tried to prove by induction; the induction step at
line 556 is exactly the lemma again, and that is where the single remaining
`sorry` sits. It stopped at 213 min after eleven nudges. The remaining step is
the problem's core, and the filler cannot be expected to close it.

Nothing in the three transcripts points at the harness or the server as the
cause: no 5xx, no "verifier unavailable", no traceback, no fill round that
ended in error, and every leaf rejection but four (Section 4, H4) was a closer
the model had written itself.

## 4. Harness defects found

Ordered by what they cost in this pass.

**H1. Out-of-range fill options reach the server and come back as `http_422`.**
The model asked for `try0_s` of 90 or 120 (cap 60), `timeout_s` of 600 (cap 300)
and `max_total_s` of 5734 (cap 3600); eight calls (P2 4, P3 1, P6 3) returned a
pydantic message instead of a fill. Each is a wasted model turn. The harness
clamps the model's sledgehammer `timeout_s` already; it should clamp these the
same way and say so in the result.

**H2. No cap on the scratch timeout.** `ATTEMPT_TIMEOUT_S` (180 s) is only the
MCP's default; the model passes `timeout` itself and got 300 and 600 s runs. P2
spent 74 min in twelve such calls, P6 16 min in one `multi_attempt` with four
`smt` candidates at 300 s each (944 s). The sledgehammer cap of 90 s exists for
the same reason (pass 1); `run_code` and `multi_attempt` need the same clamp.

**H3. A fill job the harness stops waiting for is reported as finished, with
its untried sorries labelled `skipped`.** `_collect_fill` polls for
`FILL_MAX_TOTAL_S + 120` s whatever `max_total_s` the model asked for. P3's
call with `max_total_s=3600` was cut off after 1023 s; the summary the model
read said `line 182: skipped`, `line 193: skipped` for the two main statements
and nothing about the job still running server-side. The wait should honour
the job's own budget (bounded by the wall), and a `continuing` result must say
so instead of printing the snapshot as a verdict.

**H4. Leaf keys compare Isabelle symbols literally.** The filler writes
sledgehammer's method text as rendered, with Unicode (`‹x ≤ a n›`); the model
re-types the same line as `‹x \<le> a n›`, which Isabelle reads identically,
and the leaf rule rejects it as "a method the filler did not produce". P6 lost
three consecutive turns on one such line (n548, n552, n560) and P5 one (n275).
Replaying all 22 rejections of the pass with the symbol table from
`etc/symbols` applied to both sides: 4 rejections vanish entirely, 5 of 75
rejected lines; the other 70 lines were closers the model wrote. The fix is a
symbol-normalising `_norm` in `harness/leaves.py` (the table has 440 entries;
the server has the same one in `unicode_normaliser.py`).

*Status 2026-11-11: H1 to H4 fixed in the harness (one commit, tests in `tests/test_harness.py`); the leaf rule takes the symbol table from the server's new `GET /api/v1/symbols`, never a copy.*

Verified as working, not defects: the frozen-parts guard (P2, above); the
give-up cap (P3 and P6 ended on the third consecutive stop, after 13 and 11
nudges in total, with 1.5 h and 0.5 h left); the leaf rule (71 of 75 rejected
lines were model-written closers, including a `by sos` on P2 and three
`metis` lines on P6 that fell to the solver rule first); the fill-budget guard
(the last P2 fill was cut to 328 s to fit the wall); the wall clock itself
(P2 was cut at 14400 s, right after a query, and its row says `timeout`).

Two model-side observations worth recording. P5's third turn and P6's ninth
each hit the 65536-token completion limit with empty content and 125 k
characters of reasoning: 701 s and 397 s bought nothing. And in every unsolved
attempt the first stop came long before the wall (P3 at turn 133 of 174, P6 at
turn 115 of 157), which is the behaviour the restored no-limits wording
(f59cf73, after this pass) is meant to move.

## 5. IPS defects found

**I1. A dead scratch session is handed out once before it is dropped.** Eleven
`run_code` calls answered `session_gone` or "prover process died" (P2 9, P3 2);
all but one came 5 to 100 s after the previous scratch call, so idle eviction
(30 min) and lease reaping (2 h) are not the cause, and leased sessions are
never evicted for memory. What the transcript shows is the pool holding a
session the server no longer has and giving it to the next caller; the
`scratch_session` bracket drops it only after the 404. The one case with a
cause on record is P3: a chunk timed out at line 28, the next call said the
ML process was gone, the one after that `session_gone`. My guess is prover
death on the HOL-Analysis scratch sessions (P2 is the only HOL-Analysis
problem and had nine of the eleven), after heavy real-arithmetic runs; the
server log decides it:
`grep -E "evict|prover_died|discard_dead|closing idle" logs/server.stdout.log`.
Whatever the cause, the MCP should retry a 404/410 on a scratch session once
with a fresh one; the caller never asked for that particular session.

**I2. Fill results are not symbol-normalised.** `ASCII_OUTPUT` normalises
goals, states and query output to `\<name>` notation, and the agents are told
to write that notation; the fill job's `method` and `patched_text` bypass the
serializer and carry Unicode. That inconsistency is the root of H4 and will
bite any client that compares text.

**I3. A running job's untried targets are labelled `skipped`.** The status
snapshot uses the same word for "not started yet" as the final result uses
for "max_total_s ran out before this one" (`reason` tells them apart, the
label does not). A `pending` outcome for the former would have made H3
visible to the model.

*Status 2026-11-11: I1 to I3 fixed in IPS (`ada6b6c`, `4b1af9c`; 878 tests, live check on the Docker server). The cause of the dead scratch sessions is still to be read from the server log.*

No 5xx, no 504, no `memory_pressure` refusal and no "verifier unavailable" in
the two worker logs; the sledgehammer-timeout fixes of 2026-11-09 held. Two
`scratch_exhausted` refusals on P6 were absorbed by the harness's release-and-
retry.

## 6. What this says for the next passes

The staged filler is a stage-1 result that can be reported as such: 81 % of
the skeleton's leaves closed, four fifths of them by the cheap stage, 23 false
claims caught before any prover ran, and P4 in a third of the writes. It did
not change the solve set, and on this evidence it will not: the three misses
are missing proofs, not missing closers. The rep-2 pass at 8 h with both arms
and the restored no-limits prompt tests the other hypothesis, that the model
stops too early; P6, which ended one honest lemma short after 3.5 h, is the
attempt to watch.

H1 to H4 are each a few lines and should go in before rep 2; I1 is the one
IPS change that costs the model turns today.

## 7. The three runs side by side

One attempt per problem; the latest row per (problem, arm, rep) in `runs-server/rep1/results.jsonl` (plain P1 is the hand-launched 2026-11-05 run that replaced an aborted first try). Prompt tokens count every call's full context; the bracketed figure is the part DeepSeek did not serve from cache, which is what the run cost.

| run | problem | status | wall min | model calls | writes (rejected) | sledgehammer found/calls | fills: proved/sorries | nudges | prompt tok M (uncached k) | completion tok k |
|---|---|---|---|---|---|---|---|---|---|---|
| plain r0 | P1 | solved | 71 | 196 | 2 (0) | 0/0 | - | 0 | 25.4 (100) | 182 |
| plain r0 | P2 | timeout | 240 | 345 | 42 (0) | 0/13 | - | 17 | 112.8 (169) | 701 |
| plain r0 | P3 | timeout | 240 | 895 | 30 (0) | 1/12 | - | 489 | 407.8 (209) | 589 |
| plain r0 | P4 | solved | 39 | 55 | 7 (0) | 0/0 | - | 0 | 5.2 (38) | 152 |
| plain r0 | P5 | solved | 31 | 80 | 4 (1) | 0/0 | - | 0 | 9.2 (65) | 175 |
| plain r0 | P6 | timeout | 240 | 674 | 56 (2) | 2/42 | - | 425 | 303.7 (213) | 451 |
| **plain r0** | **all** | **3/6** | **861** | **2245** | **141 (3)** | **3/67** | **-** | **931** | **864.1 (794)** | **2250** |
| forced r0 (fixed filler) | P1 | solved | 104 | 177 | 12 (1) | - | 5: 231/338 | 0 | 24.7 (175) | 216 |
| forced r0 (fixed filler) | P2 | timeout | 240 | 180 | 79 (7) | - | 54: 31/95 | 7 | 34.6 (80) | 245 |
| forced r0 (fixed filler) | P3 | timeout | 240 | 118 | 29 (4) | - | 22: 94/203 | 8 | 32.4 (118) | 392 |
| forced r0 (fixed filler) | P4 | solved | 116 | 99 | 17 (2) | - | 6: 220/254 | 0 | 15.5 (107) | 234 |
| forced r0 (fixed filler) | P5 | solved | 58 | 24 | 15 (1) | - | 6: 163/186 | 0 | 2.8 (67) | 152 |
| forced r0 (fixed filler) | P6 | timeout | 240 | 160 | 29 (5) | - | 21: 181/346 | 29 | 36.1 (67) | 316 |
| **forced r0 (fixed filler)** | **all** | **3/6** | **998** | **758** | **181 (20)** | **-** | **114: 920/1422** | **44** | **146.0 (613)** | **1555** |
| forced r1 (staged filler) | P1 | solved | 178 | 192 | 25 (5) | - | 10: 431/505 | 0 | 29.0 (163) | 310 |
| forced r1 (staged filler) | P2 | timeout | 240 | 139 | 17 (2) | - | 28: 2/54 | 4 | 25.6 (49) | 278 |
| forced r1 (staged filler) | P3 | gave up | 151 | 174 | 25 (3) | - | 13: 151/249 | 13 | 47.7 (157) | 340 |
| forced r1 (staged filler) | P4 | solved | 54 | 113 | 4 (1) | - | 2: 189/193 | 0 | 9.7 (52) | 144 |
| forced r1 (staged filler) | P5 | solved | 66 | 42 | 13 (4) | - | 5: 252/280 | 0 | 6.7 (153) | 227 |
| forced r1 (staged filler) | P6 | gave up | 213 | 157 | 42 (9) | - | 29: 383/459 | 11 | 62.8 (224) | 550 |
| **forced r1 (staged filler)** | **all** | **3/6** | **902** | **817** | **126 (24)** | **-** | **87: 1408/1740** | **28** | **181.5 (798)** | **1850** |
