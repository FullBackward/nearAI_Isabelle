# The three solved problems (P1, P4, P5): plain against the two forced-arm runs

Winston Ren's project; this note by the harness author, 2026-11-11.
Data: the nine solved attempts, plain rep 0 and skeleton_forced rep 0 (pass 1,
2026-11-08/09, the original one-stage filler) and skeleton_forced rep 1
(2026-11-10/11, the staged filler: try0 -> nitpick -> sledgehammer -> isar
-> split). Produced by `scripts/analysis/solved_compare.py`. One attempt per
cell, so every number below is a single draw; the rep-0 to rep-1 spread
within the forced arm (1.7x on P1 wall, 2.1x on P4) is as large as any
between-arm gap, and I treat differences smaller than that as noise.

My reading, stated first. (i) The forced arm did not save reasoning: completion
tokens per solved problem are flat or higher on both filler versions. (ii) It
did not save wall: the filler's prover time is added on top of model time that
stays about the same. (iii) It changed the *shape* of the proof: on P1 the
proof is a third shorter in lines and half as many leaves, and in every forced
proof a fifth to a quarter of the leaves are ATP calls that the plain arm never
writes. (iv) The staged filler raised the filler's own closure rate (68 % to
85 % on P1, 87 % to 98 % on P4) and moved the closers from metis to blast,
force and auto, at no consistent wall or token gain.

## 1. The numbers

Wall, model and tool time in minutes; tokens in thousands (completion includes
DeepSeek's reasoning content); leaves are closing methods in the verified
theory; ATP is metis/smt/meson/moura among them; steps are have/show/obtain
lines.

| attempt | wall | model | tools | turns | completion k | uncached prompt k | writes | filler proved/tried | lines | leaves | ATP | steps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 plain r0 | 71 | 46 | 24 | 196 | 182 | 100 | 2 | - | 1210 | 307 | 0 | 299 |
| P1 forced r0 | 104 | 47 | 57 | 177 | 216 | 175 | 12 | 231/338 (5 calls) | 777 | 232 | 64 | 210 |
| P1 forced r1 | 178 | 83 | 95 | 192 | 310 | 163 | 25 | 431/505 (10) | 690 | 164 | 40 | 130 |
| P4 plain r0 | 39 | 32 | 8 | 55 | 152 | 38 | 7 | - | 736 | 248 | 0 | 245 |
| P4 forced r0 | 116 | 40 | 76 | 99 | 234 | 107 | 17 | 220/254 (6) | 1004 | 205 | 22 | 212 |
| P4 forced r1 | 54 | 25 | 29 | 113 | 144 | 52 | 4 | 189/193 (2) | 732 | 189 | 20 | 219 |
| P5 plain r0 | 31 | 27 | 4 | 80 | 175 | 65 | 4 | - | 692 | 226 | 0 | 259 |
| P5 forced r0 | 58 | 22 | 36 | 24 | 152 | 67 | 15 | 163/186 (6) | 498 | 154 | 28 | 166 |
| P5 forced r1 | 66 | 31 | 35 | 42 | 227 | 153 | 13 | 252/280 (5) | 750 | 242 | 50 | 252 |

Totals over the three problems: plain 141 min wall and 509 k completion
tokens; forced r0 278 min and 602 k; forced r1 298 min and 681 k.

The closing methods, most common first:

| attempt | methods in the verified proof |
|---|---|
| P1 plain r0 | simp 139, rule 60, auto 49, linarith 36, blast 15 |
| P1 forced r0 | metis 63, simp 52, presburger 31, linarith 26, blast 17, satx 15 |
| P1 forced r1 | blast 43, metis 32, force 21, auto 16, fast 11, fastforce 10 |
| P4 plain r0 | auto 84, simp 68, rule 47, linarith 41, blast 7 |
| P4 forced r0 | simp 42, satx 41, presburger 39, linarith 19, blast 15, auto 14 |
| P4 forced r1 | auto 51, blast 28, simp 22, force 20, fastforce 15, argo 14 |
| P5 plain r0 | simp 123, linarith 69, auto 18, rule 13 |
| P5 forced r0 | presburger 31, simp 29, smt 15, metis 13, linarith 13, argo 12 |
| P5 forced r1 | blast 40, fastforce 31, smt 24, force 24, argo 23, simp 22 |

## 2. Reasoning tokens: no saving

The hypothesis the arm was built to test is that a hammer at the end saves the
model reasoning. Per problem, completion tokens are plain 182 / 152 / 175 k
against forced r1 310 / 144 / 227 k and forced r0 216 / 234 / 152 k. The
forced arm wins one cell in six (P4 r1, by 5 %) and loses the rest by 20 to
70 %. Per model turn the reasoning volume is the same everywhere (median 350
to 700 completion tokens, 180 to 320 k characters of reasoning per attempt),
so the difference is in the number of turns the model spends, and the forced
arm spends them on reading fill results and reshaping skeletons. The uncached
prompt tokens, which are what the prompt side actually costs, are also higher
on the forced arm in every cell but one, because every fill result re-enters
the context.

Two forced P5 attempts each have one turn cut at the provider's 65 536-token
output ceiling; the plain attempts have none. It did not change the outcome
there, but it is a cost of the longer per-turn reasoning the skeleton work
invites.

## 3. Wall: the filler is added, not substituted

Model time is close across arms (P1 46 / 47 / 83, P4 32 / 40 / 25, P5 27 / 22
/ 31 min). The forced arm's extra wall is tool time: 57 to 95 min on P1, 29 to
76 on P4, 35 on P5, almost all in fill rounds (27 to 59 min of write+fill per
attempt) and scratch tests of closers the model may not write into the file
(29 and 43 min on P1). The plain arm's tool time is 4 to 24 min, nearly all
scratch runs; it called sledgehammer zero times in the three solves. So the
plain model proved these three by hand, with simp, auto and linarith, and the
forced model proved them by handing every leaf to the prover and waiting.

## 4. Proof shape: shorter on P1, mixed elsewhere, and a different kind

P1 is the clear case: 1210 lines and 307 leaves by hand against 777 / 232
(forced r0) and 690 / 164 (forced r1), with the intermediate steps falling
from 299 to 130. The hammer closes bigger steps than the model would state
for itself, so the skeleton needs fewer of them. On P4 the forced r0 proof is
longer (1004 lines) and r1 equal (732); on P5 r0 is shorter (498) and r1
longer (750). Averaged, the forced proofs are about 10 % shorter in lines and
15 % fewer leaves; I would not claim more than "not longer".

The kind of proof is different in every cell. Plain proofs contain no ATP
call; forced proofs contain 20 to 64, plus presburger and satx, which is to
say the steps a human would also delegate. The staged filler shifts this
further: on P1 metis falls from 63 to 32 and blast/force/auto take over,
because try0 runs before the hammer and its methods are kept when they close
the goal. Those proofs re-check faster and depend on fewer named facts, which
matters if the proofs are to be reused as lemmas (the AutoDecompose
statement-object plan).

## 5. The staged filler against the one-stage filler

| | P1 | P4 | P5 |
|---|---|---|---|
| filler closure, one-stage (r0) | 231/338 = 68 % | 220/254 = 87 % | 163/186 = 88 % |
| filler closure, staged (r1) | 431/505 = 85 % | 189/193 = 98 % | 252/280 = 90 % |
| wall r0 -> r1 | 104 -> 178 | 116 -> 54 | 58 -> 66 |
| completion k r0 -> r1 | 216 -> 310 | 234 -> 144 | 152 -> 227 |

The closure rate rose on all three. Wall and tokens moved both ways, and the
P1 r1 attempt is the outlier: ten fill calls over 505 sorries and 43 min of
scratch tests, a model that reshaped the skeleton many more times (25 writes,
5 leaf rejections) than r0 (12 writes). With one draw per cell I cannot
separate the filler's effect from the model's path on that attempt.

## 6. What this does and does not say

It says: on problems this model can solve by hand, forcing the hammer costs
wall and does not save reasoning; it buys a proof of a different kind, and on
the longest problem a shorter one. It does not say the forced arm is worse at
proving: the solve sets are identical and the misses are the same three
problems on both arms. The question the arms were built for, whether closing
automation lets a *bounded* model close more, needs a problem the plain arm
cannot do by hand and the forced arm can, and none of the six is that
problem. The research note's Section 4 and the decomposition plan are where
that question goes next: Putnam-level pieces, where the filler's 85 to 98 %
closure would be the whole proof.
