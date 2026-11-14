# The Putnam pass (36 problems, rep 0): what the forced filler cost, and what the auto-fill component should become

Winston Ren's project; this note by the harness author, 2026-11-14.
Data: `runs-server/putnam/` (72 attempts of 2026-11-12/13, the 36-problem
draw `subsets/putnam36.txt`, arms `plain` and `skeleton_forced`, 2 h wall,
DeepSeek V4 Pro), read with `scripts/analysis/putnam_pass.py`. Four rows
(2021 A2 and 2023 A1, both arms) were rejudged `solved` on 2026-11-14 with
`scripts/rejudge_rows.py` after the build-service outage described in
Section 1; the counts below include them. One attempt
per cell, so every number is a single draw; the rep-to-rep spread seen on
the IMO set (up to 2x on wall) applies here too, and I treat a gap below that
as noise unless it repeats across problems.

The owner's hypothesis, which this note tests: the fill mechanism is too
strict and too naive, so the model spends its time on tries that cannot
succeed; and the harness withholds tools (a Python run of examples) that the
model needs. My reading, stated first.

(i) *The forced arm lost, and the loss is in the filler's blind spot, not in
the model.* Plain solved 23 of 36, forced 19; on five problems plain solved
and forced timed out, on one the reverse (and that one plain attempt was a
server capacity failure, not a model failure). The forced attempts that
timed out had the proof largely done: the filler had closed 82 % of the 4 316
leaves it was given, and what remained open were leaves of the kind
`isCont ln 2`, `det2 (x *R u) v = x * det2 u v`, `(1/2)^(j+3)^2 < (1/2)^(j+2)^2`,
which a human closes with `simp add: det2_def algebra_simps` or
`continuous_intros`. The filler's cheap stage runs `try0` with *no facts*
(`Try0.empty_facts` in the REPL), so it cannot unfold the model's own
definitions or reach an intro-rule family, and the leaf rule then forbids
the model from writing the one-line closer itself. That loop ("could not
close AS STATED, restate it") is the owner's "too strict" in mechanism.

(ii) *The second cost is scratch testing, not fill time.* Fill rounds took
12.7 h of prover time over 36 attempts; scratch runs (`isabelle_run_code`)
took 11.8 h, of which 8.2 h were calls that hit the 180 s cap, three quarters
of them the model testing a proof it was not allowed to write into the file.
Plain spent 5.2 h in scratch and 2.2 h in timeouts.

(iii) *The Python hypothesis is partly right and small in the data.*
Computation calls (`value`, `eval`, `nitpick`, `quickcheck`) were 158 in the
forced arm and 105 in plain, about 27 min each; one attempt (1970 A3, forced)
burned 64 min trying to compute digit lists through the code generator. A
cheap evaluation tool would have saved that attempt, not the pass. The model
did not say it needed Python: its stop messages ask for more wall, not more
tools.

(iv) *Six of the 36 statements were disproved, and five of the six disproofs
look right to me*: PutnamBench's Isabelle statements of 1962 B3, 1977 B6,
1992 B4, 1994 B1 and 2010 A4 are defective as formalised (a typo, a 0-based
list index checked at 1..length, a totalised derivative, truncated `nat`
subtraction, a polymorphic numeral). This is one sixth of the draw and a
finding to report upstream; it also means the solve ceiling was 30, not 36.
Two harness holes showed up alongside: a disproof is accepted on "builds",
not on "derives False from the statement", and a server memory refusal
failed a row instead of waiting.

(v) *What to change at the auto-fill component* (Section 7): give the probe
facts (the file's definitions, `algebra_simps`/`field_simps`, the
`*_intros` families; this is DSP's 2022 "Sledgehammer + heuristics", which
doubled Sledgehammer alone on miniF2F); let the model write a closer the
filler can verify in five seconds instead of forbidding all closers; stop
re-hammering an unchanged goal; cap code-generator evaluations; and measure
the filler on its own before the next model run. The existing `skeleton` arm
(filler plus the model may write closers) is the cheapest test of the owner's
hypothesis and should be the comparison in rep 1.

## 1. The run

Thirty-six problems, three per slot A1-B6, seed 1; two workers; 2 h wall;
staged filler (try0 5 s, nitpick 10 s, sledgehammer 30 s per leaf, isar
retry, split). The report (`imo2026_pass.py ... report`) gives the per-cell
table; the summary:

| arm | solved | disproved | timeout | gave up | failed | mean wall | wall total | completion tokens | uncached prompt |
|---|---|---|---|---|---|---|---|---|---|
| plain | 23 | 6 | 4 | 2 | 1 | 53 min | 31.7 h | 5.59 M | 2.61 M |
| skeleton_forced | 19 | 4 | 13 | 0 | 0 | 78 min | 46.9 h | 5.19 M | 3.35 M |

Both solved 18; plain only 5 (1963 A6, 1970 A3, 1981 B5, 2015 A3, 2016 B2);
forced only 1 (1968 B6, where plain's attempt never opened a session: the
Pool Server answered `memory_pressure` eight times in 92 s and the harness
recorded `failed`); both missed 12: the 6 disproofs (two of which, 2010 A4
and 2019 A5, the forced arm did not disprove in time) and 6 misses proper
(1968 A6, 1993 B3, 2007 B6, 2014 B4, 2019 B5, 2023 B1).

**The verifier outage, and the four rejudged rows.** From 2026-11-13 06:57
the Pool Server's build service was wedged: one bigstep build ran for 29 h
because a timed-out build was killed by its shell wrapper only, the JVM and
Poly/ML under it kept the pipes open, the handler never returned, and it
held the bigstep semaphore (size 1). Every `completed()` and final verify
after that moment came back "verifier unavailable: the theory was not
judged", and the harness wrote the row as `timeout`. Four rows were hit,
2021 A2 and 2023 A1 on both arms, each with a sorry-free file; the attempts
spent their remaining wall waiting on the dead verifier (the forced 2021 A2
attempt called `completed` three times). Built on 2026-11-14 after the
restart, all four PASS in 6 to 10 s and pass the harness's textual checks,
so they are counted `solved` here (`scripts/rejudge_rows.py` keeps the old
status in the row). The server fix is IPS c723e06 (kill the process group,
reap with a bound; `tests/test_kill_build_tree.py`). Their walls and token
counts stay in the tables as the attempts ran them.

By slot and era (solved, plain / forced, of 3 per slot): A1 3/3, A2 3/3,
A3 3/1, A4 2/2, A5 2/2, A6 2/1, B1 1/1, B2 3/2, B3 1/1, B4 1/1, B5 2/1, B6
0/1. The A-side (15/12 of 18) is easier than the B-side (8/7) on both arms,
as expected; the forced arm's losses are spread over A3, A6, B2, B5. By era:
1962-79 6/5 of 10, 1980-99 8/7 of 11, 2000-23 9/7 of 15. Problems importing
only `Complex_Main` went 18/15 of 20; every problem importing
`HOL-Computational_Algebra` or `HOL-Library` (6) was missed by both arms,
four of them disproved or defective.

**Benchmark defects.** The six disproved statements, with my judgement of
each disproof (the harness copies them to `runs-server/putnam/defects/`):

| problem | defect in the Isabelle statement | disproof | my judgement |
|---|---|---|---|
| 1962 B3 | upstream typo `Q$2 = k * Q$2` (should be `P$2`), known since 2026-11-12 | formal lemmas | genuine |
| 1977 B6 | the list condition checks `x!i` for `i ∈ {1..length x}` while `!` is 0-based, so the last index is out of range and the first element unconstrained | formal, builds a 3-element group | genuine |
| 1992 B4 | equates the iterated derivative of a totalised rational function with a quotient *pointwise on all of ℝ*, including the poles | formal obstruction lemmas | genuine, more probable than not |
| 1994 B1 | `¦n - m²¦` on `nat` truncates, so the set is infinite and its `card` is 0 | one lemma deriving False from the statement at n = 320 | genuine |
| 2010 A4 | the numeral `10` has a free type: the statement is over an arbitrary `normalization_semidom`, not `nat` | *informal only*: a `text` block and `end` | genuine defect (the forced attempt hit the same wall: "the frozen theorem statement leaves the outer base 10 as a free type variable"), but the filed disproof proves nothing |
| 2019 A5 | the model exhibits a `finite_3` instance satisfying the hypotheses with a different `GREATEST` | 27 lemmas, two `shows False` | plausible; needs a human reading |

Only 1994 B1's disproof is a lemma deriving `False` from the statement. The
harness's `disproved()` requires `write_disproof` to have built, nothing
more, and a theory of lemmas (or of prose) builds. Section 7, item 8.

## 2. Where the forced arm's wall went

Mean minutes per attempt, 36 attempts per arm (tool time by tool; the fill
column is the model's explicit `isabelle_fill_sorries` calls, the write column
is `write_file` *including the automatic fill round that follows every
accepted write*):

| arm | wall | model | tool | scratch runs | write + auto fill | explicit fill | sledgehammer | turns | writes | rejected writes |
|---|---|---|---|---|---|---|---|---|---|---|
| plain | 53 | 29 | 23 | 9 | 2 | 0 | 1.4 | 166 | 4.4 | 1.3 |
| skeleton_forced | 78 | 28 | 49 | 20 | 16 | 5 | 0 | 156 | 10.8 | 2.2 |

Model time is the same on both arms (17.2 h against 16.6 h in total; 5.6 M
against 5.2 M completion tokens). The forced arm's extra 15 h is all tool
time, and it splits two ways.

**Fill rounds: 12.7 h.** 210 rounds, 4 524 leaves sent, 3 569 proved.

| kind | rounds | leaves sent | proved | closure | prover time | median per round | seconds per leaf |
|---|---|---|---|---|---|---|---|
| automatic (after a write) | 180 | 4 316 | 3 527 | 82 % | 9.6 h | 122 s | 8 |
| explicit (model's call) | 30 | 208 | 42 | 20 % | 3.1 h | 246 s | 53 |

Of the proved leaves, try0 settled 2 875 and sledgehammer 711 (nitpick found
33 false leaves, split helped 11, isar once). So four fifths of what the
filler closes is `simp`/`auto`/`blast`/`force`-class, found in under five
seconds, and the hammer adds a fifth. Of the leaves not proved, 738 came back
`none` and 104 `timeout`. The explicit rounds are the model asking the
filler to try again on leaves it already failed, mostly unchanged: a fifth
succeed, at seven times the cost per leaf.

**Scratch runs: 11.8 h, of which 8.2 h in calls that hit the 180 s cap.**

| arm | scratch calls | time | timed-out calls | their time | median call | computation calls (value/eval/nitpick/quickcheck) |
|---|---|---|---|---|---|---|
| plain | 3 114 | 5.2 h | 47 | 2.2 h | 0.5 s | 105 (28 min) |
| skeleton_forced | 2 663 | 11.8 h | 197 | 8.2 h | 2.7 s | 158 (27 min) |

What the forced arm's 197 timed-out calls contained: 149 were proofs
(`lemma`/`have`/`show` text, 6.0 h), 17 definitions plus proofs (0.7 h), 25
other (1.3 h), 5 computations. The forced model tests in scratch what it
may not write into the file; when the test is a heavy `auto` on a hard goal
it runs to the cap. 1970 A3 is the extreme: 105 scratch calls, 21 at the
cap (64 min), trying to evaluate a `digits` function through the code
generator, plus five writes rejected because its helper definition shadowed
the statement's name `digits`; the first accepted write came at tool call
158 of 180.

**Rejected writes.** Forced: 44 leaf-rule rejections over 20 attempts, 17
"helper definitions shadow names used in the statement", 9 "forbidden
command", 2 solver-rule, 3 other. Plain: 20 shadowing, 7 forbidden command,
6 "no closing end", 3 statement changed, 7 other. The shadowing rule is the
frozen-statement check refusing a `definition digits` because the theorem
binds a variable `digits`; it cost both arms, and on 1970 A3 it cost the
forced arm the attempt.

## 3. What the filler could not close

The last fill result of each forced timeout lists the open goals. Reading
them (the full list is in `runs-server/putnam_fills.json`), they fall into
four kinds:

1. *Needs the model's own definition unfolded.* `det2 (x *R u) v = x * det2 u v`
   (1963 A6; three such, 17 of 61 leaves closed in the attempt), `0 < A k`
   and `A k * exp k * ... = A (Suc k) * ...` (2007 B6), `{r. 1 ≤ r ∧ r² ≤ k}
   = {1..sqroot k}` (2016 B2, 24 of 105 closed, 8 leaf rejections). try0
   with no facts cannot see `det2_def`; sledgehammer's relevance filter may
   pick it up, in 30 s, sometimes.
2. *Needs an intro-rule family or a named library fact.* `isCont ln 2`,
   `((+) 1 ⟶ 2) (at_left 1)` (1981 B5, 147 of 204 closed, two leaves left
   at the wall), `(λr. (x+1) powr (r+1) - x powr (r+1)) has_real_derivative
   ...` (2021 A2). These close by `(auto intro!: tendsto_eq_intros
   continuous_intros derivative_eq_intros)` and by nothing in try0. (The
   2021 A2 and 2023 A1 attempts went on to close every leaf by restating,
   and were solved once rejudged; their examples stand as leaves the filler
   refused at first sight.)
3. *Algebra the cheap methods do not normalise.* `n*(n+1)*(2n+1) + 6*(Suc n)²
   = Suc n * (Suc n + 1) * (2 * Suc n + 1)` (2023 A1), `(1/2)^(Suc j+2)^2 <
   (1/2)^(j+2)^2` (2014 B4), the `gcd a 2015 = 1 + 4*(if 5 dvd a ...)`
   case sums (2015 A3). `algebra`, `field_simps`, `power_strict_decreasing`
   territory.
4. *False or ill-stated leaves the model wrote.* `(1 + 1) * ln (1 + 1) - 1 *
   ln 1 = 0` (2021 A2; it is 2 ln 2); nitpick does not refute real-valued
   goals, so the model was told `none`, not `false`.

Kinds 1 to 3 are the leaves a human closes in one line and the plain model
did close: in the 21 plain proofs judged solved in the run the methods are
`simp` 1 547, `auto` 702, `rule` 353, `linarith` 178, with 32 `simp add:`
modifiers and 12.6 `unfolding` lines per proof and 21.8 references to a
`*_def`. The 17 forced proofs judged in the run have `force` 279, `blast`
255, `meson` 221, `auto` 216,
`fastforce` 183, `metis` 141, with 1.6 `simp add:` per proof. The forced
proofs are shorter (334 against 453 lines, 110 against 143 leaves) and of a
different kind, as on the IMO set; but the forced arm can only ever have a
leaf that a fact-less `try0` or a 30 s hammer finds, and the five lost
problems are the five where one leaf of kind 1 to 3 stood in the way.

The owner's phrase "meaningless tries" is, in the data, the NEXT loop: the
filler reports `none`, the summary says "you may not write their closers
yourself, restate them", the model restates (10.8 writes per attempt against
4.4) and tests in scratch (2 663 calls, 8.2 h of timeouts), and the restated
leaf meets the same fact-less probe. The 30 explicit re-fill calls at 20 %
closure are the same loop by another route.

## 4. The two hypotheses, judged

**"The fill mechanism is too strict."** Supported, with a precise meaning:
strictness is the *combination* of the leaf rule (the model writes no closer)
with a probe that has no facts. Either alone would have been survivable: the
IMO set, where every leaf was elementary, was closed at 85 to 98 %. On
Putnam the leaves need definitions and intro rules, and the pair fails. The
filler is "naive" in the sense that its cheap stage is Isabelle's `try0`
with empty facts and no shape-directed intro rules, and its hammer is a
30 s sledgehammer with default settings; this is below DSP's 2022 baseline
automation (Section 6).

**"The harness restricts tools such as Python."** Partly. The model can
compute inside Isabelle (`value`, `eval`, `normalization`, `nitpick`,
`quickcheck`) and did so 263 times across both arms, for under an hour in
total. It cannot run a script, and on 1970 A3 that cost an hour of
code-generator timeouts. I did not find a stop message asking for Python or
a numerical check; the model's complaints are the wall ("I'll continue next
turn"), the leaf rule, and the 2010 A4 type variable. A sandboxed evaluator
would be a cheap addition and a fair one for both arms, but it is not where
the 15 h went.

## 5. The cost of the defeat, for the record

- *Solve count*: 19 against 23, and on the 30 non-defective statements 19
  against 23 of 30. Pass@any over both arms: 24 of 36.
- *Wall*: 46.9 h against 31.7 h, a 48 % premium; on the 16 problems both
  solved and judged in the run (the two rejudged problems ran to the wall
  on both arms waiting on the dead verifier and are left out of this
  comparison), 816 against 497 min (1.6x), model time 329 against 263 min, tool
  time 486 against 233 min, completion tokens 1.82 M against 1.51 M. The
  forced arm did not save reasoning on the problems it solved, as on the
  IMO set; it added prover time.
- *Prover time*: 12.7 h of fill rounds (9.6 automatic at 8 s per leaf, 3.1
  explicit at 53 s per leaf) and 8.2 h of timed-out scratch runs, which is
  the number to cut first.
- *Tokens*: completion 5.19 M against 5.59 M; uncached prompt 3.35 M against
  2.61 M (fill results re-enter the context). No `length` cuts on either arm.
- *What the run also bought*: the six disproofs (five of them, in my
  judgement, genuine benchmark defects), and the list in Section 3 of what a
  Putnam-level leaf needs, which the IMO set did not show.

## 6. How other systems close the leaves of a sketch

The fill component is the oldest part of this design, and the literature has
settled several of its parameters. Read against the four kinds of Section 3:

| system | what fills a hole | relevant finding |
|---|---|---|
| Draft, Sketch, Prove (Jiang et al., ICLR 2023, §4.2, Table 1) | 11 heuristic tactics at 10 s each (`auto`, `simp`, `blast`, `fastforce`, `force`, `eval`, `presburger`, `sos`, `arith`, `linarith`, `auto simp: field_simps`), then Sledgehammer at 120 s | Sledgehammer alone 10.4 % of miniF2F-test, with the heuristics 20.9 %; removing the automated prover from DSP costs 9 points. Our try0 stage is this list minus `field_simps`, `sos`, `eval`, at 5 s. |
| HybridProver (Hu et al., 2025; EMNLP Findings 2026) | all tactics of a candidate proof replaced by `sorry`, the skeleton checked for sufficiency first, then a fine-tuned tactic model plus Sledgehammer with default ATPs and heuristic tactics per hole | 59.4 % then 73.8 % on miniF2F Isabelle; the paper credits the symbolic tools with the last increment. The sufficiency check before filling is what our arm does by construction. |
| ProofAug (Liu et al., ICML 2025) | on failure, replace the failing step by `sorry` at the finest granularity, call automation, then coarsen (the whole conjecture becomes one `sorry`) | 66 % of miniF2F with 2 100 model queries against 56 % with 16 384 for Subgoal-XL; the point is *granularity search*, not a stronger hammer. Our split stage is the fine direction only. |
| APOLLO (Ospanov et al., NeurIPS 2025) | Sorrifier replaces each failing sub-lemma by `sorry`; AutoSolver tries automation; the LLM is called on each remaining goal *with a low budget*; recombine, reverify | Goedel-Prover-SFT from 25 600 samples to a few hundred at 65.6 %; o4-mini from 3-7 % to over 40 %. The LLM is a leaf closer of last resort, not forbidden. |
| HILBERT (Varambally et al., ICLR 2026; `ml-hilbert` in the library) | each `have` of the sketch extracted into a standalone theorem with the preceding context (`EXTRACT_SUBGOALS_FROM_SKETCH_PROMPT`); a prover model first, then the reasoner with retrieved theorems; recursive decomposition on failure | 462 of 660 PutnamBench (70 %) in Lean; proofs average 1 454 lines. The retriever (Mathlib search) is what our kind-2 leaves lack. |
| Seed-Prover (ByteDance, 2025) | lemma-style whole proofs; a lemma pool across runs; heavy setting seeds a conjecture pool and promotes proved conjectures to lemmas | lemmas are the unit of reuse; a failed lemma is refined with compiler feedback, never forbidden to the model. |
| Aristotle (Harmonic, 2025) | lemma-based informal reasoning, each lemma formalised; Lean search replaces `sorry` by Monte Carlo graph search guided by a policy and value model | two failure causes named: flawed strategy and *insufficient lemma granularity*; the fix is re-splitting, which is our split stage made model-driven. |
| LeanHammer (Zhu et al., 2025) | neural premise selection, Aesop, Lean-auto, Zipperposition, Duper reconstruction | 33.3 % of Mathlib goals, 43 % with ground-truth premises, 37.6 % with MePo added: premise selection is the lever, and combining a symbolic and a neural selector beats either. |
| Draft-Sketch-Prove (ICLR 2026), ProofSketcher (2026), LEAP (2026) | refine only the failing subgoal and what follows; typed holes; an LLM reviewer filters unpromising decompositions before the checker runs | the common move is *local repair*: nothing re-hammers a goal that did not change. |
| Thor (Jiang et al., 2022) | language model proposes, Sledgehammer closes the step | Sledgehammer alone 25.7 % of PISA steps, the pair 57 %; 8.2 % of theorems need both. |

From the AutoDecompose library, three entries speak to the fill component
directly. `markdown-sorrify-at-failure-lean4-skills-430f389e` orders the
reasons a `sorry` resists filling, cheapest first: a missing library lemma
(search), a missing tactic, a missing intermediate `have`, a structural
split, a missing lemma statement; our filler stops at the second rung and
sends the model back to the fourth. `markdown-workflow-isabelle-pide-ai-cb5b2bef`
says "only sorry statements you are convinced are true" and "check that the
stubs suffice before proving them"; kind 4 of Section 3 is the first rule
broken, and nitpick does not catch it on the reals. `python-extract-have-ml-hilbert-30f55e92`
is the extraction prompt: each hole becomes a theorem with its context,
which is what a student agent in AutoDecompose would receive.

The pattern across all of them: the automation at a hole is given *facts*
(local definitions, premise selection, retrieved lemmas), is tried at
*several granularities*, and the model is the closer of last resort at a
small budget. Our arm gives the automation no facts, one granularity (plus
a syntactic split), and forbids the model.

## 7. Improvements at the auto-fill component, in order of evidence

Each item names the repository it lives in and the Section-3 kind it
addresses. Items 1, 3, 4 and 5 are server or harness changes that leave the
experimental arms as they are; item 2 changes an arm and is the owner's
decision.

1. **A probe with facts (IPS, kinds 1-3).** Before the hammer, run the cheap
   methods with the file's own definitions and the standard simp sets:
   `simp add: <every *_def declared in the file> algebra_simps`, then
   `(auto simp: field_simps)`, `(auto intro!: tendsto_eq_intros
   continuous_intros derivative_eq_intros)`, `algebra`, `(simp add:
   power_strict_decreasing ...)`; this is DSP's heuristic list plus the
   intro families real-analysis leaves need. The REPL already has the goal
   shape; the `*_def` names are a regex over the document. Cost: a few
   seconds per leaf, against 30 s of hammer. Expected effect: it is the
   closer the plain model wrote in 1 547 `simp` leaves; I would guess it
   closes half of the 738 `none` rows, which is a guess to be measured
   (item 6).
2. **Verify, do not forbid (harness, the arm's rule).** Let the model write a
   closing method and accept it when the filler's own probe (item 1, five
   seconds) proves the same leaf; reject ATP transplants (`metis`, `smt`
   with named facts) as the solver rule already does. The leaf rule's
   purpose, that the model never hand-closes what the hammer should close,
   is kept by the verification; its cost, the NEXT loop and 8.2 h of scratch
   timeouts, goes. The existing `skeleton` arm (auto fill on, leaf rule off)
   is this change without the verification step and can run tomorrow.
3. **Do not re-hammer an unchanged goal (IPS or harness, the explicit
   rounds).** Key each fill target by its goal text; a goal already `none`
   or `timeout` in this attempt is skipped with that verdict unless the
   leaf's statement or `using` facts changed. The 30 explicit rounds (3.1 h,
   20 % closure) become a few minutes.
4. **Cap evaluation and hard-automation scratch calls (harness, Section 2).**
   A scratch call whose chunk contains `value`/`eval`/`normalization` gets
   20 s, not 180; a call whose last command is a bare `auto`/`simp`/`force`
   on an open goal gets 60 s. 197 timed-out calls cost 8.2 h; a 60 s cap
   would have cost 3.3 h for the same information ("too hard as stated").
   Optionally a sandboxed evaluator tool (Python with `fractions`/`sympy`)
   for both arms; it answers the owner's hypothesis directly and is cheap
   to add, but Section 4 says it is not the main loss.
5. **Falsity on the reals (IPS, kind 4).** Nitpick finds 33 false leaves in
   4 524 and none of them over ℝ. Add `quickcheck[random]` with a small
   real-valued domain, or evaluate closed numerals by `approximation`, so
   that `2 ln 2 = 0` comes back `false` and not `none`. A false leaf reported
   as `none` sends the model to restate a true-looking lie.
6. **Measure the filler alone before the next model run (free).** The 738
   `none` goals are in the transcripts with their file state. Replay them
   through the server with item 1 on and off, no model call, and report
   closure by kind. This is the experiment that separates "the filler is
   weak" from "the model's leaves are bad", and it costs prover time only.
7. **Granularity both ways (IPS, after item 1).** ProofAug's coarsening: when
   a split's leaves all fail, also try the *enclosing* goal as one hammer
   target with the children as `using` facts. Our split stage only refines.
8. **Disproof gate (harness, Section 1).** `disproved()` should require, in
   DISPROOF.thy, a lemma whose assumption is the frozen statement and whose
   conclusion is `False`, or at least a `shows False` lemma that names the
   theorem; a text block must not count. 2010 A4's defect is real, its
   disproof is prose.
9. **Shadowing and capacity (harness, Section 2).** Let a helper
   `definition` reuse a name the theorem binds as a variable when the
   statement is unchanged (37 rejections), and make a worker wait on
   `memory_pressure` instead of failing the row (1968 B6, plain).

For AutoDecompose the same list is the specification of the student's leaf
closer: a hole becomes a theorem with its context (HILBERT's extraction), the
closer is item 1 then the hammer then a small model budget (APOLLO's ladder),
and a false hole is caught before anyone proves toward it (isabelle-pide-ai's
rule). The library's theorem-scale shape (child proofs of 3, 10 and 29 lines
at the quartiles) says the student's task is the size of the leaves in
Section 3, not the size of a Putnam problem.

## 8. What I would run next

The owner's constraint (2026-11-14): no 18-problem rerun yet; small tests
first, each one deciding whether the next is worth paying for.

1. *Done, free.* Judge the four unjudged files: all four PASS (above).
2. *Free, about 2 h of server time.* Item 6 of Section 7 as
   `scripts/replay_leaves.py`: every forced failure's final skeleton sent to
   the filler as-is and once more with the file's `*_def` facts handed to
   each leaf (`using f_def ... sorry`), closure compared per leaf. If the
   facts variant closes a fair share, item 1 of Section 7 is worth building;
   if the control also closes many, the pass lost those leaves to load and
   timeouts, not to the goals.
3. *Paid, three attempts, 2 h cap each.* `subsets/putnam-small3.txt`
   (1963 A6, 2015 A3, 1981 B5: plain solved in 0.7 to 1.0 h, forced timed
   out with 19, 18 and 14 open leaves) on the `skeleton` arm, which keeps the
   automatic filler and drops the leaf rule; this isolates the rule's cost
   from the filler's. Needs the owner's go.
4. *Paid, three attempts, only after 2 and 3.* The same three problems on
   `skeleton_forced` with the fact-aware probe (Section 7, item 1) in the
   server, against the plain rows and the item-3 rows.
5. Report the five benchmark defects to PutnamBench with the disproofs.
6. The 18-problem rep 1 (every problem not solved by both arms) only if 3
   or 4 shows a change worth its 20-odd hours of wall.

Limits of this note: one attempt per cell; a 2 h wall that cut thirteen
forced attempts while their fill closure was 60 to 95 %, so part of the
"loss" is the forced arm being slower rather than unable; and my reading of
the open goals (Section 3) is by eye, not by replay, which item 6 would
replace.
