# Rep 2 (the three unsolved problems, both arms): how the attempts stopped, and whether to remove the give-up exit

Winston Ren's project; this note by the harness author, 2026-11-11.
Data: `runs-server/rep2/` (rep-2 rows of `results.jsonl`, the six
`transcript.jsonl` files and final theories), read with
`scripts/analysis/giveup.py`; the uncapped pass-1 plain P3 run
(`runs-server/pass1/`) as the natural experiment for "no give-up".

My conclusion first. *The give-up exit records a stop; it does not cause one.*
Removing it would turn each give-up into a wall-clock timeout on the same
file: pass 1 ran exactly that experiment and bought nothing in 2.5 hours of
nudging. What the data do show is that a *fresh context* restarts real work
where a nudge no longer does, so the change worth making is not to delete the
exit but to replace "end the attempt" with "restart from the current file
while the wall remains". Section 4 says how.

## 1. The run

Rep 2 queued the three problems no arm had solved (P2, P3, P6), one attempt
per arm, 8 h wall each, the rep-1 fixes in place (prompt no-limits language,
clamped fill options, symbol-aware leaf rule). Outcome: 0 of 6 solved; five
`gave_up`, one `timeout`. The solve set over three reps is unchanged:
P1, P4, P5 on both arms, never P2, P3, P6.

| attempt | status | wall | model turns | tool calls | stops (nudges) | first stop at | sorries left |
|---|---|---|---|---|---|---|---|
| plain P2 | gave_up | 3.9 h | 339 | 314 | 25 | 2.3 h (turn 140) | 1 (`main_theorem`) |
| plain P3 | gave_up | 1.9 h | 241 | 238 | 30 | 1.2 h (turn 126) | 3 (the three main statements) |
| plain P6 | gave_up | 1.4 h | 153 | 144 | 9 | 1.0 h (turn 120) | 3 |
| forced P2 | timeout | 8.0 h | 382 | 379 | 3 | 4.4 h (turn 230) | 6 |
| forced P3 | gave_up | 4.8 h | 139 | 132 | 14 | 3.2 h (turn 101) | 9 |
| forced P6 | gave_up | 1.6 h | 100 | 81 | 19 | 1.0 h (turn 58) | 2 |

(plain P3's turn-2 stop is a `length` cut of the first reasoning turn, not a
give-up, and is excluded from its count.) The forced P2 attempt is the one
that behaved as the prompt asks: three stops in 8 h, 717 sorries sent to the
filler, 446 proved, still six open at the wall.

## 2. What a nudge buys, and when it stops buying

The nudge revives work at first and then stops working; the decay is the
same in every attempt. Measured from the first stop:

| attempt | after the first stop | tool calls | accepted writes | segments of 10+ calls | sorries: first stop -> end | distinct stop texts |
|---|---|---|---|---|---|---|
| plain P2 | 1.6 h | 175 | 15 | 6 | 1 -> 1 | 14 of 25 |
| plain P3 | 0.7 h | 94 | 14 | 2 | 3 -> 3 | 14 of 30 |
| plain P6 | 0.3 h | 25 | 4 | 0 | 1 -> 3 | 9 of 9 |
| forced P2 | 3.6 h | 150 | 18 | 1 | 6 -> 6 | 3 of 3 |
| forced P3 | 1.6 h | 25 | 2 | 0 | 6 -> 9 | 13 of 14 |
| forced P6 | 0.6 h | 24 | 1 | 0 | 1 -> 2 | 17 of 19 |

Three things to read off.

1. **Early nudges do revive work.** Plain P2's third nudge was followed by a
   62-call segment in which the model built and verified its algebraic core
   (`alg_core`, `alg_main`); its stop message after that segment reads "I have
   made significant progress". Plain P3 had two more segments of 10+ calls
   after its first stop. So a cap of one stop would have been too tight.
2. **The tail is empty.** After the last productive segment every attempt
   shows the same shape: one to six tool calls (a scratch run, a diagnostics
   call, a fill status), then a stop; the stop text shrinks to a sentence and
   then repeats verbatim. Plain P3 produced the identical sentence "I have not
   completed the proof. The file is clean with the three correctness theorems
   proved and the three main statements still containing `sorry`." sixteen
   times in a row across turns 186-241. Forced P6's last ten segments are one
   call each. The sorry count never fell after the first stop in any attempt;
   in three it rose (the model re-opened a skeleton and could not close it).
3. **The cap fires late, not early.** Three consecutive stops came 0.3 to
   3.6 h after the first stop, after 9 to 30 nudges. By then the model had
   been in the one-call-then-stop pattern for 5 to 14 cycles. What the exit
   cut off is the tail in row 2, not the work in row 1.

## 3. The uncapped experiment already exists: pass-1 plain P3

Pass 1 had no give-up exit. Plain P3 stopped first at 1.4 h (turn 115) and
was nudged 489 times until the 4 h wall (895 model turns). After the first
stop: 291 tool calls, of which 228 were `completed()` with a `sorry` still in
the file, 22 accepted writes, no change to the three open statements. The
pattern was "call `completed()`, be told it fails, stop, be nudged, call
`completed()`" for about 240 cycles. Note that this loop would not trip the
current exit either, since `completed()` is a tool call and resets the
counter; the exit caught the rep-2 attempts only because their tail stops
came in threes.

One event in that transcript is the useful one. At turn 880 the context was
compacted (prompt tokens fell from 598 k to 5 k) and the model, given a fresh
context with the same file, immediately did 15 real tool calls (eleven
scratch runs, a read, a query, a goal, a sledgehammer) before the wall ended
the attempt. A repeated sentence had not moved it for 2.5 hours; a reset
context moved it at once. That matches the literature rule the research note
records (fresh contexts over growing transcripts: Seed-Prover 1.5, Numina,
h1's "context rot"), and it is the one lever in our own data.

## 4. Answer to the question, and what I would change

**Can the harness force the model to solve the problem?** No. Nothing on the
harness side makes the model think; the prompt already says there is no
limit and no reason to stop, and the nudge repeats it. A mechanical force
exists (ask the API for a tool call on every turn) and pass-1 P3 shows what
it produces: a `completed()` per turn. The stops in rep 2 came when the model
judged the remaining core lemma beyond it (its own words: "the central
algebraic geometry step remains out of reach", "the core game-theoretic
lemmas", "the central stabilization lemma"), and three reps on both arms say
the judgement was right for this model: these are model problems, as the
rep-1 analysis concluded.

**Should the give-up exit be removed?** Not as a deletion. Removing it
converts five give-ups into five 8 h timeouts with the same final files, at
a cost of about 26 h of server wall that the queue could spend elsewhere
(five attempts at 8 h less the 13.6 h they used). Prompt tokens are nearly
all cached, so the token cost is small; the wall is the cost.

**What I would do instead**, in order of evidence:

1. *Restart instead of end.* When the exit trips and the wall has, say, more
   than an hour left, start a fresh model context on the current file: the
   verified lemmas are in the file, the leaf keys are reseeded from it, the
   transcript continues. Record `restarts` in the results row. This is the
   compaction event of Section 3 made deliberate, and it keeps the exit's
   function (stop paying for the empty tail) while spending the remaining
   wall on the one thing that re-engaged the model. It is a change to the
   harness only, identical for both arms, and it does not touch the
   prompt's wording.
2. *Count unproductive cycles, not consecutive stops.* The current counter
   resets on any tool call, so the pass-1 `completed()` loop evades it. A
   cycle that contains no accepted write and under N tool calls between two
   stops is the pattern in Section 2; three such cycles is a better trigger
   than three bare stops and would have fired 5 to 14 cycles earlier in rep
   2. This is a refinement of the detector, not a new mechanism.
3. *Do not* force a tool call per turn, and do not escalate the nudge text:
   the stop texts in Section 2 show the model answering the nudge's content
   ("I will not call `disproved()` because I believe the statement is true")
   and then stopping anyway.

If the owner wants the experiment to be "the model is never released until
the wall", item 1 gives that with a mechanism the data support; a bare
removal gives it with one the data say is empty.

## 5. Costs of rep 2, for the record

| attempt | prompt tokens | cached | completion | model calls | tool time |
|---|---|---|---|---|---|
| plain P2 | 120.4 M | 120.3 M | 514 k | 339 | 2.2 h |
| plain P3 | 74.6 M | 74.4 M | 431 k | 241 | 0.2 h |
| plain P6 | 32.7 M | 32.7 M | 296 k | 153 | 0.6 h |
| forced P2 | 90.6 M | 90.3 M | 878 k | 382 | 4.9 h |
| forced P3 | 39.8 M | 39.6 M | 378 k | 139 | 1.6 h |
| forced P6 | 22.8 M | 22.7 M | 306 k | 100 | 0.7 h |

Uncached prompt tokens are under 0.4 M per attempt; completion tokens are the
spend. No `length` cuts except the one on plain P3's first turn; no
compactions; symbols loaded from the server (439) in every row.
