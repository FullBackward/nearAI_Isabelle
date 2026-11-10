# Two questions after pass 1: would a fixed hammer budget or a worked example help the forced arm, and what pipeline would the literature build?

Winston Ren's project, nearAI_Isabelle; this note by the harness author, 2026-11-10.
Evidence: pass 1 (`docs/pass1-analysis-2026-11-10.md`) and three literature
surveys commissioned for this note, kept as appendices in `docs/research/`
(systems [A], practice [B], frontier results [C]); every borrowed claim below
carries a bracketed pointer into them, and from there to the primary source.

My conclusions, stated first and argued below. (i) A longer fixed sledgehammer
timeout will not make the forced arm solve more; this is more probable than not
from our own data and consistent with everything published. (ii) A worked
example in the prompt would buy syntax conformance and little else; I regard a
gain in proving power as not much better than a guess, and the literature holds
no measurement for a frontier model in Isabelle. (iii) Every system that proves
IMO or Putnam problems in 2025-26 has the shape our forced arm has, with three
parts we lack: a natural-language plan before the skeleton, an LLM prover (not
only a hammer) on each unfilled leaf in a fresh context, and a disproof check on
every new statement. The pipeline I propose in Section 4 adds those three, keeps
the Pool Server as the verifier, and is sized for the six IMO problems first.

Roadmap. Section 6 is an addendum on the owner's framing and Prove2Me. Section 1 fixes terms and what the pass measured. Section 2 answers
question 1a and 1b. Section 3 distils the surveys into the design rules that
have evidence behind them. Section 4 proposes the pipeline and says what to
build first; Section 5 lists what would settle the open points. The surveys'
numbers are quoted with their budgets; anything self-reported or unverified is
marked so.

## 1. Terms and what pass 1 measured

A *leaf* is a terminal proof step (`by ...`, `.`, `..`, a `qed` with a method).
The *filler* is the server's `fill_sorries`: sledgehammer on every `sorry` of a
file, 30 s each, run inside one session. The *forced arm* lets the model write
only structure and `sorry`; the filler writes every leaf. The *plain arm* gives
the model a per-goal sledgehammer and no filler.

Pass 1 ran each IMO 2026 problem once per arm. Both arms solved P1, P4, P5 and
missed P2, P3, P6. The filler proved 1 011 of 1 393 sorries it tried (73 %);
the per-goal sledgehammer found 3 proofs in 67 calls and was not called at all
in the three plain solves. Two of the three plain misses were give-up loops
(the model stopped, the harness nudged, 489 and 425 times). One forced miss
overwrote its own file. These are harness facts, not facts about the arms, and
they are being fixed; the arguments below set them aside.

## 2. Question 1: two proposed improvements to the forced arm

### 2a. A fixed, longer sledgehammer timeout

*It would not help.* The evidence is of two kinds.

Our data. In the forced runs the model retried 35 sorries that had failed at
30 s with budgets of 60 to 300 s. One was proved (P3, at 180 s). Where a 60 s
round did prove many, 91 of 96 on P1, those were leaves the 30 s round had never
reached because its job cap expired, and they proved at the same rate (95 %)
the 30 s round achieved on its own leaves. Per problem, at 30 s the filler
proved 95 % (P1), 91 % (P4), 92 % (P5), 61 % (P6), 51 % (P3) and 37 % (P2) of
what it tried. The rate tracks the problem, not the budget.

The literature. Böhme and Nipkow's "Judgement Day" (IJCAR 2010) found that
three provers at 5 s equal the best single prover at 120 s, and that 240 s adds
0.4 points over 120 s [A §5]; Isabelle's 30 s default was set on that study
[B §A1]. The Sledgehammer manual's own diagnosis of a reconstruction that "runs
seemingly forever" is that the goal is too hard for metis, not that it needs
more time; its remedies are fewer facts, a simpler goal, or an Isar proof
[B §A1]. Every Isabelle LLM pipeline fixes its budget (10 s heuristics then
120 s in DSP and ProofAug; 30 s in HybridProver; 60 s in IsabeLLM) and none
reports a timeout ablation [B §D2]. Draft-Sketch-Prove's one hammer-side
ablation points the other way: running cheap tactics for 10 s *before*
sledgehammer doubled the hammer baseline, 10.4 to 20.9 % [A §5].

So the lever is not seconds but the goal. When a leaf survives one hammer
call, the published practice, and the practice that worked in our solved runs,
is to restate it: split it, add the facts it needs with `using`, or prove a
lemma above it. The forced P1 run did exactly this for its five survivors (0/5,
then 10/11, then 3/3). I would keep 30 s, and spend any extra prover time on
breadth: more sorries in parallel, and a cheap-tactics pass before the hammer
(Section 4, rule 5).

### 2b. A worked example in the prompt

*It would buy conformance, not proving power; the measurement that would
settle it does not exist.* Few-shot exemplars were found ineffective for GPT-4
proof generation (COPRA) and gave no gain for a model that already knows
Isabelle syntax (HybridProver: "the few-shot prompting provides no extra hints
to prove the theorem") [B §D1]. Random exemplars raised syntactic and lowered
semantic correctness in ProofBridge; models imitate the shape and hallucinate
the content [B §D1]. The one measured gain is from *retrieved similar proofs*
in the same development, IsabeLLM, 76 to 94 % on 16 lemmas [B §D1], which is
not our situation: an IMO proof has no near-identical neighbour. No frontier-
model agent of 2026 uses proof exemplars; they use rules, feedback and
retrieval (Numina, the minimal agent, Delta-Prover, the Trail of Bits and
lean4-skills skill files) [B §D1, §B3].

Our data agree on the cheap part. The leaf rule rejected one to five writes per
forced run, each a single turn, and the models complied at once; the rule's
cost is not where the forced arm lost. The forced arm lost time to scratch
tests of closers it could not write (29 min on P1), to a file used as a
scratchpad when the server's scratch runs timed out (P2), and to leaves no
hammer could close (P3, P6). An exemplar fixes none of these.

There is one thing an exemplar might teach that rules do not: *granularity*.
Aristotle restructures each informal proof into lemmas "each meant to have a
very short proof" and attributes its failures to lemmas too coarse for search
[B §C2]; Delta-Prover solved IMO 2019 P1 as 83 subproblems of about four calls
each after 1 024 monolithic attempts failed [A §4.2]. Our forced misses have
exactly the coarse-leaf signature (P3's late rounds: 0/3, 0/4, 1/9, 1/6). A
skeleton exemplar of the right grain could move that; I put it at "it might
well be", and it is cheap to test (Section 5). It is also a change to the arm,
so it belongs in a new arm or a flagged variant, not in `skeleton_forced` as
run, and the owner's standing decision against prompt hints about goal binding
is untouched by it: granularity is a different matter from binding.

## 3. What the literature has evidence for

I list only rules with a measurement or an author's stated ablation behind
them; rules that are merely common are left out. The surveys' section numbers
follow each rule.

1. **Natural-language plan first, then a skeleton of `sorry` lemmas, then
   per-lemma proving with verifier feedback.** This is the shape of every
   2025-26 system at IMO or Putnam level: Seed-Prover 1.5, Aristotle, Hilbert,
   Goedel-Architect, MechMath, Aleph [C §3]. The cleanest ablation is
   Goedel-Architect on DeepSeek-V4-Flash, the model family we use: direct
   proving 6.5 %, a tool-using single prover 54.5 %, the blueprint 75.6 %, the
   blueprint seeded by a natural-language proof 88.8 % of PutnamBench [C §3].
   Draft-Sketch-Prove measured the Isabelle version in 2022: forcing the model
   to write complete proofs instead of leaving gaps cost 9 to 10 points [A §1.2].
2. **Lemmas with very short proofs; shallow and wide, not deep.** Aristotle and
   Delta-Prover as above; Hilbert's gain is almost all at depth two (75 to
   98.4 %) and Seed-Prover 1.5 caps depth at four for contests [A §6(2)].
3. **Repair with placeholders beats regeneration at equal budget.** MechMath on
   Putnam 2025 A1-A4 at 128 calls each: discard-and-retry 0/4, whole-proof
   repair 3/4, "sorrify" the failing block and solve the holes 4/4, at a third
   of the cost [C §3]. Delta-Prover: 95.9 % against 49.1 % for best-of-N at the
   same 16 384 calls [A §4.2]. Goedel-Prover-V2: the compiler's error text is
   the repair input whose removal hurts most [B §C1].
4. **Disproof as a first-class signal.** Goedel-Architect found a false
   sub-lemma on 292 of 672 problems; Seed-Prover 1.5 routes a disproved lemma
   back to sketch revision; Aristotle's formalisation step caught quantifier
   errors in its own informal drafts [C §3]. In Isabelle this is `nitpick` and
   `quickcheck`, with "potentially spurious" treated as a hint [B §A3].
5. **A cheap-to-expensive automation ladder, and one hammer call per goal
   shape.** `try0`-class methods in seconds, heuristics at about 10 s, then one
   sledgehammer call; after that, change the goal [B §E rule 5, §D2; A §5].
6. **Refine the global blueprint, do not recurse on the failing lemma.**
   Goedel-Architect's stated reason: recursion "can inefficiently loop on
   dead-end strategies" [A §4.7].
7. **Fresh contexts and a cache of verified lemmas, not a growing
   transcript.** Seed-Prover 1.5 found 32 to 64 k-token trajectories net
   negative and re-injects proved lemmas on restart; Numina moved stuck lemmas
   into subagents because "very long contexts degrade instruction-following";
   h1 measured "context rot" (200-turn contexts drop Putnam100 from 69 to 60);
   the minimal agent's self-managed notes gave +7 % at -20 % cost [B §C4; C §4].
   Our plain P2 at 741 k tokens per call and the 1.3 GB P3 transcript are the
   same failure.
8. **Budget by LLM attempts adaptively, not by hammer seconds.** The only
   measured adaptive policy decides continue-versus-restart from the diversity
   of errors across failed attempts: 28.9 % less cost at equal accuracy
   [B §C5]. Stop a target when consecutive failures repeat the same error.
9. **Verify a frozen artifact cold; check statements, not only sorries.**
   Statement defects are now a first-class failure (Aleph's 15 counterexamples
   to PutnamBench statements; 398 certified benchmark defects in "Faults in Our
   Formal Benchmarking"; "Sorries Are Not the Hard Part") [C §2.3-2.4, §4].
   Our `verified.thy` plus cold rebuild already does the first half.
10. **Verifier throughput is engineering, not plumbing.** Kimina's import-keyed
    warm REPLs gave 1.94x; snapshotting removed the 60 s import per branch;
    Lean now checks slower than models write [C §4]. The Pool Server's warm
    sessions and `fill_sorries` are the Isabelle analogue; the pass showed the
    forced arm spending 60 to 70 % of its wall clock in them.
11. **Geometry needs a geometry engine.** Seed-Geometry and Yuclid solve in
    seconds what general provers spend hours on; Goedel-Architect calls IMO 2025
    P2 "out of reach for a general-purpose Lean prover" [C §3-4]. Our P2 imports
    HOL-Analysis and was the worst cell on both arms.
12. **No cross-problem lemma library.** LEGO-Prover's library showed no direct
    reuse and its gains vanish at equal compute; within-problem caching pays
    [B §C7].

Two findings bear on this project in particular. First, the counter-trend:
h1 (Meta FAIR, Oct 2026) matches or beats the enforced-decomposition systems
with a minimal harness, provided the verifier interface is tight (persistent
file, per-edit feedback, REPL, goal view, everything imported), and the
upstream of this repository reached 672/672 on PutnamBench with DeepSeek V4, a
bash tool and nudging, at $0.17 a problem [A §4.7; C §3]. A strong enough
model self-decomposes. The open question for DeepSeek on IMO problems is
whether it is strong enough, and pass 1 says: on P1, P4, P5 yes, on P2, P3,
P6 no, on either arm. Second, the Isabelle-specific gap: no published Isabelle
result exists on IMO 2025 or 2026, the per-goal sledgehammer has no competition
result above 3 of 640 on PutnamBench, and every Isabelle gain since 2022 has
come from sketches with hammers closing leaves [C §5]. Our plain arm is the
2022 shape; our forced arm is the 2025 shape minus its LLM prover.

That last clause is, in my opinion, the most useful thing the surveys say
about pass 1. In Seed-Prover, Hilbert and Goedel-Architect the thing that
closes a lemma is an LLM with tools, of which the hammer is one. In our forced
arm the only thing that may close a leaf is sledgehammer. The filler's
proof-rate profile (above 90 % on well-stated leaves, near zero on the leaves
that decided P2 and P3) is Draft-Sketch-Prove's 2022 observation that human
proofs "leave gaps too difficult for automated provers" [A §6(2)]. The
published fix is a prover below the filler, not a longer hammer.

## 4. A pipeline for hard problems in Isabelle, built on the Pool Server

Let me state the design as a sequence of stages, then the parallelism, then
the budgets, then the order in which to build it. The aim is a pipeline that
can be left running on the six IMO problems for a day and scaled to a Putnam
set by adding workers; everything is textual on the harness side, with the
prover untouched, as the owner requires.

**Stage 0, plan.** The model writes an informal proof as a numbered list of
lemmas, each stated so that it should have a short proof. No Isabelle yet.
(Rule 1; Goedel-Architect's 75.6 to 88.8 % is the gain from this stage alone.)

**Stage 1, blueprint.** The model turns the plan into a theory file: helper
lemma statements with `sorry`, the frozen targets with structured skeletons
whose leaves are `sorry`, dependencies implicit in order. The harness accepts
the write only if the file parses and every frozen statement is present (the
write-time check pass 1 showed we need). Every new statement is run through
`nitpick` and `quickcheck` in a scratch session; a genuine counterexample is
returned to the model as "this lemma is false", and the blueprint is revised
before any proof effort (rule 4).

**Stage 2, fill.** The filler runs once over all sorries, 30 s each, preceded
by a cheap-tactics pass (`try0`-class methods, a few seconds) so sledgehammer
is spent only on what they miss (rule 5). This is `fill_sorries` as it exists,
with the heuristics pass added on the server or in the harness. In pass 1 this
stage alone closed 90 % of leaves on the solved problems.

**Stage 3, prove the survivors, one per fresh context.** Each surviving
`sorry` becomes a self-contained lemma with its statement and the facts in
scope, handed to a *leaf prover*: a fresh model context with the scratch tools
(`isabelle_run_code`, `multi_attempt`, `find_theorems`, per-goal sledgehammer)
and a budget of, say, 20 turns, whose output is either a proof text that
passes in isolation or a decomposition into further `sorry` lemmas (rules 2, 3,
7). The leaf prover may write closers; the leaf rule applies to the blueprint
author, not to it. Depth is capped at three. Proofs that pass are written back
into the file; the main context never sees the leaf prover's transcript, only
its verdict and a one-line summary.

**Stage 4, revise the blueprint.** The main context receives the list of
proved and unproved lemmas with their error summaries, and revises the
blueprint globally: restate coarse lemmas, add helpers, drop a wrong strategy
(rule 6). Then Stages 2 to 4 repeat. Verified lemmas are kept verbatim across
revisions and re-injected after any context reset (rule 7).

**Stage 5, verify.** As now: `completed()` builds a frozen copy cold, checks
statements, sorries and escape hatches, and the result is `verified.thy`.
`disproved()` stays as the exit for a false formalisation.

*Parallelism.* Stage 3 is the fan-out: one leaf prover per surviving sorry,
each on its own scratch session, as many in flight as the server's session
pool allows (six today). Stage 2 already runs inside one session; a second
form of parallelism, several fill jobs on disjoint sorry sets, would need the
server to split a file, which I would defer. Across problems, one worker per
problem as now. The queue and driver stay as they are.

*Budgets and stopping.* Per problem: a wall clock and a token cap, with the
cap logged against outcome so the report gives cost per solve (rule 8, and the
surveys' $5.80 to $74 per Putnam problem as calibration [C §4]). Per leaf: 20
turns, then decomposition or surrender. Per attempt: three consecutive model
turns without a tool call end the attempt as `gave_up`; a blueprint revision
whose error summary repeats the previous one verbatim is a second trigger. The
nudge stays for a single stray stop, which upstream found valuable [A §4.7],
but it no longer runs to the wall.

*What to build, in order.* (i) The three defect fixes from pass 1: give-up
detection, write-time protection of frozen statements, the 90 s clamp and a
worded result on sledgehammer timeouts. Without these, nothing measured in the
next pass is clean. (ii) Stage 3, the leaf prover, as a harness-side
sub-attempt reusing the existing attempt machinery on a one-lemma theory. This
is the largest change and the one the literature backs most strongly. (iii)
Stage 0 as a required first turn, and Stage 1's `nitpick` check on new
statements. (iv) The cheap-tactics pass before the hammer, in the server's fill
job. (v) Context management: verified-lemma cache and reset. (vi) A geometry
path for P2 is beyond this project; I would record P2 as out of scope for a
general Isabelle pipeline, as Goedel-Architect did for its Lean counterpart.

*What this is not.* It is not a trained prover, a lemma pool across problems,
or test-time training; the surveys show those are what the IMO-grade systems
add on top, at 10 to 500 accelerator-days per problem [C §4], and nothing here
reaches for them. It is also not a bet against the minimal harness: if a
future model self-decomposes well enough, Stages 0, 1 and 4 collapse into the
model's own turns and the pipeline degrades to the plain arm with a leaf
prover. The design is chosen so that collapse costs nothing.

## 5. What would settle the open points

- **Timeout.** Already settled as far as our data can: 1 of 35 retries. A
  cheaper confirmation is to rerun the filler on the surviving sorries of the
  three forced misses at 30 s and 120 s from the final files; no model calls
  are needed.
- **Exemplar.** A controlled pair on the three solved problems and P3: the
  forced arm as run against the same arm with one worked skeleton of the right
  grain in the strategy text, three reps each; the outcome measures are fills
  proved on the first round and leaf-rule rejections. About 24 attempts.
- **Leaf prover.** Take the surviving sorries of P3 and P6 forced (five and
  six) as standalone lemmas and run a fresh-context prover on each with a
  20-turn budget. If none closes, Stage 3 is not where those problems are lost
  and the plan stage is; if several close, Stage 3 is the next build.
- **Give-up.** Reading the 490 stop turns of plain P3 would say whether an
  escalating nudge (new information, not repetition) could have restarted
  work; the MathArena result suggests error diversity, not count, is the
  signal to act on [B §C5].

## 6. Addendum (2026-11-10): the owner's framing, and Prove2Me

The owner's statement of the experiment, recorded here because it changes
what the arms are for. The question is what *automation at the proof-closing
step* buys a model: the human habit of writing the argument and calling
sledgehammer at the end, to save reasoning. The nearAI harness was chosen
because it is minimal, not because it is strong. Scaling is to be studied at
small scale, by decomposing a hard problem into Putnam-level pieces handed to
subagents ("students" with sledgehammer and the filler), with the
decomposition driven by rules drawn from verification practice, mathematics
and skill files rather than by free generation, so that it is less random and
more often correct. Putnam problems are the unit of the subagent task, not a
benchmark to beat. The three tasks: improve the filler; build and evaluate a
rule-based decomposition; formalise the scaling question.

Prove2Me (Chen, Marwaha, Lu, Yuen, Peng; arXiv 2608.28433, Aug 2026) is the
scaling reference the owner has in mind. What it says, read from the paper:

- *Naive sorry-filling does not scale* (their Section 4.1), for two reasons:
  every change to a lemma recompiles its downstream cone, and agents editing a
  shared file interfere, so the work cannot be atomised; centralised swarms
  pay for this with a serialised merge queue (Gloeckle et al.: about 30 000
  agents, $100 000, one textbook in a week).
- Their remedy is structural: a theorem is an immutable statement object
  (description, preamble, formal statement ending in `:= by sorry`); proofs
  are separate objects whose type must match; a *proof-sketch* is a proof that
  imports other, possibly still open, theorems, so the parent is verified
  exactly when its children are (their Property 1); a searchable corpus
  (Formalpedia); *milestones*, canonical lemma statements curated by a human
  captain, so that independent agents converge on one formulation instead of
  incompatible ones; disproof as a first-class submission; a discussion
  channel; a sub-agent "read-back" from Lean to prose for auditing.
- Their evidence is case studies, not a controlled experiment: four missions
  of 17 k to 151 k Lean lines by 3 to 9 agents on $200 to $600 of consumer
  subscriptions. They say plainly that model generation and harness are
  confounded in every row and that separating them "requires holding the model
  fixed and varying only the harness, which we leave to future work".

Three consequences for this project, in my opinion.

1. The statement-object model is the right unit for the subagent experiment,
   and Isabelle supports it directly: one theory file per lemma with its own
   imports, immutable once posted; a parent "sketch" theory that imports the
   children and proves the target from them; the glue check of Section 4
   becomes "the parent builds with every child `sorry`", and Property 1 holds
   because the final verifier refuses `sorry` anywhere in the cone. The Pool
   Server already gives one warm session per child.
2. Prove2Me's milestones are the social version of the rule-based
   decomposition the owner wants: canonical statements that stop agents
   diverging. Our templates would produce such statements mechanically, and
   their correctness is checkable before any proof is attempted. That is a
   claim Prove2Me cannot test and we can.
3. The controlled experiment Prove2Me leaves open, model fixed and harness
   varied, is exactly the shape of this project. At our scale the measurable
   quantities are the ones in Section 4's cost model: leaf closure by
   automation p, subagent success q, decomposition correctness r, and prover
   time per leaf; their swarm figures give the large-scale end of the curve.

## Appendices

- `docs/research/survey-A-systems-2026-11-10.md`: about 45 systems, 2022-2026,
  with per-system fields, synthesis and source URLs.
- `docs/research/survey-B-practice-2026-11-10.md`: Isabelle and Lean
  automation practice, agent-loop lessons, prompting evidence, 19 design rules,
  each with its source; section F lists what could not be verified.
- `docs/research/survey-C-frontier-2026-11-10.md`: IMO 2025-26 results,
  PutnamBench state, the authors' own accounts of what solved the hardest
  problems, costs, Isabelle-specific work; section 6 lists unverified claims.
