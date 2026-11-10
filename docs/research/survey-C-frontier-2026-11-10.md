# C. The frontier: AI on IMO 2025/2026, formal benchmarks, methods, cost, and Isabelle (as of 2026-11-10)

Compiled 2026-11-10 from web search (extended) and primary-source fetches. Every claim carries its
source URL. "Self-reported" means the only source is the system's own repo/blog/press; "unverified"
means I could not reach a primary source at all. Dollar and time figures are as published, with no
normalisation across systems (budgets, models and verification protocols differ).

Working data saved beside this file: `dl/pb_results.json` + `dl/pb_table.txt` (the official PutnamBench
leaderboard JSON, condensed), `dl/pdf/seedprover.txt`, `dl/pdf/aristotle.txt` (pdftotext of the two papers).

---

## 1. AI results on IMO 2025 and IMO 2026

### 1.1 IMO 2025 (Sunshine Coast, July 2025) -- the reference year

| System | Score | Modality | Grading | Time / compute | Method publication |
|---|---|---|---|---|---|
| Google DeepMind, Gemini Deep Think (advanced version) | 35/42, P1-P5 | Natural language, end-to-end from official statements | Official IMO coordinators ("clear, precise and most of them easy to follow" -- IMO President Gregor Dolinar) | Within the 4.5 h sessions | Blog 2025-07-21: parallel thinking, RL on multi-step reasoning/theorem-proving data, curated solutions corpus, hints in the prompt. https://deepmind.google/discover/blog/advanced-version-of-gemini-with-deep-think-officially-achieves-gold-medal-standard-at-the-international-mathematical-olympiad/ |
| OpenAI experimental reasoning model | 35/42, P1-P5 | Natural language, no tools | Three former IMO medalists, unanimous consensus; not official IMO grading | Two 4.5 h sessions | No paper. Wei/Brown: "general-purpose RL and test-time compute scaling"; "lighter scaffold than last year, it only decided which samples to submit"; "this result cost millions of dollars" (Brown). https://x.com/polynoamial/status/1946478249187377206 , https://x.com/polynoamial/status/1954966402756133337 , https://x.com/polynoamial/status/2097375837670785447 |
| ByteDance Seed-Prover + Seed-Geometry | Official: 30/42 (2/7/7/7/7/0), silver; P1 completed 4 days after the deadline (~4,000 lines) -> 5/6 formally | Lean 4, human-formalised statements; answers for "determine" problems proposed by Seed1.6-Thinking | IMO Committee confirmed the 30; ByteDance was officially invited | 3-day window; P2 by Seed-Geometry in <2 s; P5 medium setting; P3, P4 heavy setting; P1 after deadline | arXiv 2507.23726 (2025-07-31). Blog https://seed.bytedance.com/en/blog/bytedance-seed-prover-achieves-silver-medal-score-in-imo-2025 |
| Harmonic Aristotle | 5/6 formally (all but P6) | Lean 4, human-formalised statements only; all lemma statements autoformalised | Self-reported, machine-checked; announced 2025-07-28 | Not published as hours; "model with over 200B parameters", "many parallel instances", "multiple iterations", test-time training | arXiv 2510.01346 (2025-10-01). https://arxiv.org/abs/2510.01346 |
| DeepSeekMath-V2 (open weights) | 5/6 "gold-level" (post hoc) | Natural language with self-verification | Self-graded (paper) | n/a | arXiv 2511.22570 (Nov 2025); Putnam 2024 118/120. https://arxiv.org/abs/2511.22570 |

Nobody solved P6 in 2025.

### 1.2 IMO 2026 (Shanghai, 15-16 July 2026; 666 contestants; 7 human perfect scores; gold cut-off 29)

The IMO has published no AI-results page that I could find; "officially graded" below rests on company
statements relayed by AFP/China Daily. Three classes of result:

**(a) Natural-language entries graded by IMO graders (company-reported)**

| System | Score | Notes | Sources |
|---|---|---|---|
| Xiaohongshu / RedNote dots-note-3.0 (internal beta) | 42/42 | Problems received as organisers' LaTeX after humans finished; fixed submission window; "any form of human intervention strictly prohibited"; agent system = natural-language reasoning + Python execution + self-critique loops; no formal proofs. Open-sourcing promised. | AFP via TechXplore 2026-07-23 https://techxplore.com/news/2026-07-ai-humans-score-math-contest.html ; China Daily 2026-07-24 https://global.chinadaily.com.cn/a/202607/24/WS6a62b7eda310986e2b4670a1.html |
| Huawei Celia | 42/42 | Same channel claimed; no method details found. | TechXplore above |
| NVIDIA Nemotron 3 Ultra (open weights, 550B/55B-active MoE) | 30/42 official (7,7,1,7,7,1); a late P6 proof found after 8 h 25 m got 4/7 from independent graders (unofficial 33) | Natural language, no tools/internet, contest time limit; "graded by the IMO team". | arXiv 2609.10712 (2026-09-09) https://arxiv.org/abs/2609.10712 ; https://x.com/NVIDIAAI/status/2079642933058244704 |

**(b) Natural-language runs with LLM graders (Deedy Das harness, runs 17-23 July 2026, 150-min cap per problem, network blocked, Claude-based grader agents; "strong but not authoritative")** -- https://github.com/deedy/imo-2026

| Model | Final | First pass | Wall time | Cost |
|---|---|---|---|---|
| Claude Fable 5 (high) | 42 | 42 (no repair) | 2.5 h (1.8 h excl. infra retries) | $51.05 |
| GPT-5.6 Sol (xhigh) | 42 | 39 (P2 = 4) | 3.8 h | ~$20.54 |
| Kimi K3 (Moonshot) | 42 | 36 (P3 = 5, P6 = 3) | 17.4 h | ~$31.40 |
| GPT-5.6 Sol Pro (xhigh) | 37 | single pass (P3 = 2) | 2.1 h | ~$42.32 |
| Meta Muse Spark 1.1 | 26 | single pass | 2.3 h | ~$4.45 |
| DeepSeek V4 Pro (max) | 19 | single pass | 8.9 h | ~$6.05 |
| xAI Grok 4.5 | 13 | single pass | 3.2 h | ~$14.60 |

Repair rounds for Sol and K3 used only the reviewer's defect findings. P3 and P6 are where every weaker
run lost points (same pattern as Nemotron's official 1/7 on P3 and P6).

**(c) Formal (Lean 4, machine-checked) 6/6 results -- all self-reported, none IMO-graded**

| System | Statements | Total time | Lines | Cost | Sources |
|---|---|---|---|---|---|
| Axiom Math AxiomProver | own, autonomously generated (the de-facto standard set, see 1.3) | 1,496 min (24 h 56 m): Q1 24, Q2 360, Q3 869, Q4 39, Q5 65, Q6 139 | 7,722: 521/1224/4229/520/457/771 | not stated | https://github.com/AxiomMath/IMO2026 |
| Boundless Intuition Dirac | Axiom's | 7 h 18 m: Q1 29 m, Q2 1 h 20, Q3 2 h 10, Q4 16 m, Q5 18 m, Q6 2 h 44 | 6,198 | $176.58 (Q2 $55.79, Q6 $51.06) | https://github.com/Boundless-Intuition/IMO2026 |
| Pramaana Labs Hardy (+ Panini autoformaliser) | own (Panini, human-checked) in main track; Axiom's in appendix | own: 6 h 59 m, $148.64 (Q3 3 h 32 m, $76.23, 3,032 lines); on Axiom's: 8 h 57 m | 338/765/3032/311/236/515 | $148.64 | https://github.com/pramaana-labs/imo2026-lean |
| MechMath / EonMath agent team | own; NL proof first, then Lean | 1,178 min total (NL 775 + formal 403); Q3 306 min, Q6 352 min (327 NL) | 6,116 (Q3 2,983) | not stated | blog 2026-07-18 https://mechmath.github.io/blogs/imo-2026-progress/ ; https://github.com/MechMath/IMO2026 |
| Humanfia (Humanize harness; GPT-5.6 Sol worker + reviewer; Kimi-K3 worker + Codex gpt-5.5 reviewer) | Axiom's | GPT-5.6: 497.7 min API time (Q3 187); Kimi-K3: 1,034.9 min | not stated | GPT-5.6 $127.41; Kimi-K3 $57.70 | https://github.com/humanfia/imo2026 (moved to humanfia/hoa-qed) |
| Meta FAIR h1 (minimal harness, GPT-5.6 Sol) | not stated | not stated | not stated | ~$8.07 per problem | arXiv 2610.35962 https://arxiv.org/abs/2610.35962 |
| junaid-hasan/2026_problems (GPT-5.6 Sol) | Axiom's | n/a | n/a | n/a | https://github.com/junaid-hasan/2026_problems (unverified) |
| math-ai-org/IMO2026 (community) | own, Lean 4.30.0-rc2 | n/a | n/a | n/a | https://github.com/math-ai-org/IMO2026 -- all six "Proved", contributors not named |

Observations across the formal runs: Q3 (combinatorial game on interval subdivisions) is the hardest formal
problem by every metric (Axiom 14.5 h and 4,229 lines; Pramaana $76; MechMath 2,983 lines); Q2 (geometry)
is the second most expensive for provers without a geometry engine (Axiom 6 h; Dirac $56); Q4/Q5 take
15-65 minutes for everyone. The spread between Dirac (7 h) and Axiom (25 h) on identical statements, and
between humanfia's two backends (498 vs 1,035 min), shows wall time is dominated by harness/model
choice, not by the problems.

### 1.3 The AxiomMath/IMO2026 repository

https://github.com/AxiomMath/IMO2026 -- MIT, 1 commit, ~104 stars. Layout `IMO2026/Q<n>/problem.lean`
(statement, proof bodies `sorry`) and `solution.lean` (proof). README: "both autonomously generated by
AxiomProver", "autonomous multi-agent ensemble theorem prover for Lean 4", built against Mathlib
v4.31.0. Verification: `verify.py` calls Axiom's own AXLE `verify_proof` (axle.axiommath.ai; results
cached) and the README says results were "also validated locally using Comparator"
(https://github.com/leanprover/comparator). No compute, hardware, or grading-process statements; no
human role described beyond "autonomously generated"; no independent check that the formalisations
match the official wording (Pramaana and this project both note Q2's "inside the angle" weakening).
These statements are what Dirac, Pramaana (appendix), humanfia and junaid-hasan all score against, which
is why this project's Isabelle translations track them.

### 1.4 Systems with no IMO 2026 result found

- **Gemini Deep Think**: no DeepMind IMO 2026 post found; the 2026-02-11 Deep Think post mentions only the 2025 gold and IMO-ProofBench (up to 90% on Advanced; Aletheia above 90%) https://deepmind.google/blog/accelerating-mathematical-and-scientific-discovery-with-gemini-deep-think/ . Secondary sources call dots-note-3.0 "the second AI after Gemini Deep Think" to be officially graded, implying DeepMind did not enter 2026. Unverified.
- **OpenAI**: no official entry found; GPT-5.6 Sol appears only in third-party harnesses. Noam Brown (post dated ~Sep 2026): "for the 2026 IMO, anyone with a $20/month ChatGPT subscription could do it" -- a claim, not a run. https://x.com/polynoamial/status/2097375837670785447
- **Seed-Prover 1.5 / "Seed-Prover 2"**: no IMO 2026 result and no "Seed-Prover 2" publication found (searches hit only Seed 2.0/2.1 chat models).
- **Harmonic Aristotle**: no IMO 2026 result found; 2026 news is Erdős #728 (arXiv 2601.07421, with GPT-5.2 Pro), Erdős #124 variant, and a Lean FRO donation.
- **Math Inc Gauss**: autoformalisation only (strong PNT 2025; sphere packing in 8 and 24 dimensions, ~500K -> ~200K lines, 2026; Erdős #1196). No competition work.
- **Claude Opus 5 "42/42 on IMO 2026"** appears only on benchlm.ai; unverified.

---

## 2. Formal benchmarks as of late 2026

### 2.1 PutnamBench, Lean track (672 problems; 346 carry an answer placeholder)

Official leaderboard https://trishullab.github.io/PutnamBench/leaderboard.html (data file
`results.json`, fetched 2026-11-10; the HTML renders client-side). Condensed chronology of the Lean
"with-solution" track:

| Added | System | Solved | Budget / notes |
|---|---|---|---|
| 2025-06-03 | DeepSeek-Prover-V2 (671B) | 47 | pass@1024 |
| 2025-07-22 | Goedel-Prover-V2 (32B) | 86 | pass@184 |
| 2025-10-06 | Hilbert (Apple/UCSD) | 462 | avg pass@1840 LLM calls (med 620, max 60,893) |
| 2025-11-20 | GPT-5 (ReAct, 10 turns) | 28 | pass@1 |
| 2025-12-23 | Seed-Prover 1.0 (ByteDance) | 329 | "medium" setting (18 H20-days/problem per the 1.5 paper) |
| 2025-12-23 | Aleph Prover (Logical Intelligence) | 500 | pass@1, avg $23, cap $100, avg 1,834 tool calls; 2 h 48 m avg, 12 h 50 m max; 7,497 lemmas |
| 2025-12-23 | Ax-Prover (Axiomatic AI) | 91 | pass@1, 100 tool calls, $4,000 total |
| 2025-12-26 | Aleph | 637 | pass@2, avg $54, cap $400 |
| 2025-12-27 | Seed-Prover 1.5 | 581 | 10 H20-days per problem |
| 2026-01-11 | Aleph | 668 | pass@3, avg $68, cap $1,400, max $1,012, avg 6,569 tool calls |
| 2026-04-14 | AxProverBase (Axiomatic AI) | 365 | Claude Opus 4.5, 50 tool calls, 32k ctx, avg $12.60 |
| 2026-06-06 | Goedel-Architect (Princeton) | 597 | pass@4 with NL guidance, avg $1.47 |
| 2026-07-02 | Goedel-Architect | 642 | Gemini 3.1 Pro + DeepSeek V4 Pro, avg $5.80 |
| 2026-07-19 | Leanstral 1.5 (Mistral, 119B/6B active) | 588 | 4M tokens per problem |
| 2026-08-26 | Aleph | **672** | avg $74, max $1,468 |
| 2026-08-27 | Humanfia (GPT-5.6 Sol xhigh, worker/reviewer) | **672** | avg $44.50 |
| 2026-09-04 | Mistral Prover (DeepSeek V4 Pro + Leanstral) | 658 | 5.38M tokens/solved; ground-truth informal proofs supplied |
| 2026-09-04 | **NEAR AI (DeepSeek V4 Flash 653 + V4 Pro 19)** | **672** | mean $0.17, median $0.04, max $11.18 per problem; open agent code (this project's upstream, https://github.com/nearai/putnambench-deepseek) |
| 2026-09-12 | Midas Prover | 672 (no-answer mode) | avg $6.17 and 31 min/problem, $4,144 total |
| 2026-09-24 | Forall (Astrio, Claude Opus 5 xhigh) | 672 | actor-side mean $3.52 (662 in round 1, 10 in round 2) |
| (paper, 2026-10-25) | Meta FAIR h1 (GPT-5.5) | 670 single run; 672 with retries | est. $17.86/problem incl. failures; DeepSeek V4 Flash 598 at $1.08; Gemini 3.1 Pro 642 at $6.32 |

No-answer ("Hard Mode") track: TIR Conjecturor 15 (pass@4), Enumerate-Conjecture-Prove 17 (pass@32),
Discover-and-Prove 36 (arXiv 2604.15839), Midas 672. The benchmark is saturated in with-answer mode;
the maintainers ask that proofs not be published. The leaderboard notes several entries used corrected
formalisations for defective statements (NEAR AI: 2; Aleph found counterexamples to 15 statements,
https://logicalintelligence.com/blog/aleph-solves-putnambench).

### 2.2 PutnamBench, Isabelle (640) and Rocq (412) tracks

Isabelle rows in `results.json`: Sledgehammer 3 (pass@1, 120 s: 1971 B1, 2001 A1, 2012 A2), GPT-4o 1,
DSP (GPT-4o) 4 (pass@10), and **Varto 640/640 (added 2026-08-01, GPT-5.5, avg $8/problem, note "130
requires formalization fixes")**. Varto's post (2026-07-23, https://varto.com/news/putnambench/) gives
median $6 / max $67 and 16 min average (median 14, max 121) over a 100-target sample, says the
auto-formalised fixes are "under review by the benchmark maintainers", attributes the result to
"self-learning skills, Isabelle's built-in proof tactics and the AFP", does not mention Sledgehammer, and
claims ~8x cheaper / 23x faster than the top Lean entry of 20 July 2026. Self-reported; the leaderboard
entry is the only external confirmation and it carries the 130-fix caveat. Rocq: Fable 5.1 Max 8
(2026-10-05, $45/task, three corrected statements); otherwise CoqHammer/Tactician 0.

### 2.3 miniF2F saturation

Seed-Prover 1.0: 99.6% on miniF2F-test (243/244) and 100% on valid under the medium setting; the heavy
setting proved IMO 1990 P3 and failed IMOSL 2007 A6 (arXiv 2507.23726 Table 3). Goedel-Architect: 242/244
pass@1 without NL guidance, 244/244 with (arXiv 2606.06468). MechMath-Hard 242/244 with 512 LLM calls
vs ~11.3K for Hilbert (arXiv 2603.24465). The remaining action is on correctness: miniF2F-v2 corrected
>300 Lean statements and 16 unprovable ones (arXiv 2511.03108); "Faults in Our Formal Benchmarking"
(ICML 2026, arXiv 2606.29493) audits miniF2F, ProofNet, FormalMATH, CombiBench, ProverBench: 4,833
findings, 398 mechanically certified (counterexamples, vacuous theorems, unsound axioms).

### 2.4 Other hard formal benchmarks

- **ProofNet**: no 2026 SOTA found; last figures ~30% (2024-25). ProofNet-Verified (NeurIPS 2026) is an audited Lean 4 version (367 statements). https://github.com/marcusm117/ProofNet-Verified
- **FormalMATH** (5,560 Lean statements; Findings of EMNLP 2026). https://aclanthology.org/2026.findings-emnlp.579/ No 2026 top score found.
- **CombiBench** (100): Seed-Prover 1.0 30%, Seed-Prover 1.5 48% (arXiv 2512.17260 Table 2); Discover-and-Prove 10 solved in Hard Mode vs 7 prior (arXiv 2604.15839). Leaderboard https://moonshotai.github.io/CombiBench/leaderboard not fetched.
- **FATE-H / FATE-X** (graduate / PhD algebra, 100 each): Seed-Prover 1.5 80% / 33%; h1 with GPT-5.6 Sol 90/100 on FATE-X at $38/problem (arXiv 2610.35962).
- **FormalProofBench** (private, graduate-level, Lean 4; ICLR 2026 VerifAI-2): best model 33.5% with an agentic harness; leaderboard at vals.ai. https://arxiv.org/abs/2603.26996
- **Formal Conjectures** (Google DeepMind; arXiv 2605.13171, 2026-05-13): 2,615 Lean statements (1,029 open, 836 solved, 750 other); 3,604 by 2026-10-02 with 511 misformalisation fixes merged. Frozen sets: FC100SolvedSet1 -- AlphaProof 45% (1k sims) / 50% (16k), DeepMind prover agent 66%, h1 GPT-5.6 Sol 78; FC100OpenSet1 -- 0% for all. h1 settled 8 open items (Erdős 138 and 337 variants, three OEIS conjectures, one quantum problem, two "Written on the Wall II").
- **FrontierMath Erdős** (Epoch AI, Sep 2026): 68 Erdős conjectures open as of Aug 2026, Lean 4 + Mathlib proof or disproof required, Comparator-checked, one attempt, $300 and 72 h caps, offline container with 476K arXiv papers to 2022. Scores: GPT-6.1 Sol 3/68, GPT-6 Astra 2/68, Claude Opus 5.5 and Sonnet 5.5 2/68 each. https://epoch.ai/benchmarks/frontiermath-erdos
- **Lean-Eval** (Lean FRO, Comparator-based, first submissions 2026-08-29): Humanfia claims #1 with 166-172 problems. https://github.com/leanprover/lean-eval-leaderboard
- **AlphaProof Nexus** (DeepMind, arXiv 2605.22763, 2026-05-21): 9/353 open Erdős problems and 44/492 OEIS conjectures, "a few hundred dollars" per problem.
- **RealMath** (NeurIPS 2025) is a natural-language research-level benchmark, explicitly not formal. **IMO-ProofBench** (DeepMind) is also natural-language.
- **FrontierMath** proper has no formal track; the Erdős set above is Epoch's formal component.

---

## 3. What made the difference on the hardest solved problems (authors' own accounts)

**Seed-Prover 1.0 (IMO 2025 P3, P4; past IMO 78.1%)** -- arXiv 2507.23726. Three inference settings:
*light* = whole proof + up to m rounds of Lean-feedback refinement, "equivalent to Pass@64-256", 1-2 h,
proves IMO 2022 P2 where unrefined sampling needs pass@8192; *medium* = outer refinement of the main
proof plus inner light-setting refinement of the lemmas the outer loop fails on (IMO 2003 P6, 2020 P5,
2025 P5); *heavy* = a proposer seeds a conjecture pool (default 5,000), every conjecture is attempted in
the light setting, proved ones move to a lemma pool, "after days of thinking the lemma pool accumulates
several thousand nontrivial math facts", lemmas are scored by proof rate (low proof rate = valuable),
LLM-judged relevance and length, and hundreds of top lemmas are handed to a medium run; the model was
RL-trained to use supplied lemmas. Seed-Geometry (its own DD/AR engine) solved P2 in 2 s. Lean v4.14.

**Seed-Prover 1.5 (Putnam 2025 11/12 in 9 h; PutnamBench 580/660)** -- arXiv 2512.17260 (2025-12-19).
Agentic RL (reward +1/-1 on Lean verification; VAPO + ReTool-style tool calls to Lean, Mathlib search,
Python); over ~1,200 RL steps function calls fell from ~15 to ~10 and sequence length from ~28K to ~17K
tokens. Test-time workflow: NL prover (from Doubao-Seed-1.6) writes a lemma-style informal proof ->
sketch model emits a Lean skeleton with lemmas as `sorry` -> agentic prover attempts each lemma (pass@3x3,
64K context, 28 tool calls per attempt) -> unproved lemmas are recursively re-decomposed (depth 4, then 8
by restarting with proved lemmas); disproved lemmas trigger sketch repair. Budgets: 10 H20-days/problem
on PutnamBench (log-linear solve-rate vs compute, long tail to hour 53), 40 H20-days max on Putnam 2025,
~20 H20-days on IMO 2025 (P1 16.5 h, P4 8 h, P3 5 h, P5 1 h). The paper quotes AlphaProof at ~500
TPU-days per problem.

**Aristotle (IMO 2025 5/6)** -- arXiv 2510.01346. (i) Lean proof search: highly parallel Monte Carlo
*Graph* Search with a learned value function, generative policy with progressive widening, a single
model producing hidden chain-of-thought, informal comments and Lean code; (ii) lemma pipeline: informal
proof -> restructure as a lemma sequence -> autoformalise each lemma statement -> error-correct -> search
proves lemmas -> failed attempts feed a revised lemma list (proved ones kept); (iii) Yuclid, a C++ DD/AR
geometry engine (open source) solving 17/30 of AG-30 in minutes. Scaling for the IMO: >200B-parameter
model, "many parallel instances" of the lemma pipeline, repeated feedback iterations, and test-time
training (retrain on own search traces when the problem is still unsolved; "allowed Aristotle to solve
difficult problems unsolved by our base model at the same search budget"). The only human step was
formalising the six statements. The authors' own diagnosis of convergence with Seed-Prover: "natural
language reasoning to decompose problems into simpler subproblems, combined with RL based on formal
feedback from a Lean compiler".

**Gemini Deep Think / OpenAI (IMO 2025, NL)** -- parallel thinking over several candidate solutions
plus RL on multi-step reasoning data (DeepMind); general RL + test-time compute scaling, scaffold only
selected which samples to submit (OpenAI). No compute figures beyond Brown's "millions of dollars".

**NVIDIA Nemotron recipe (IMO 2026 30/42 official, NL)** -- arXiv 2609.10712. Three checkpoints (GA, SFT,
RL specialists) run an iterative generate -> verify -> refine search capped at 8 rounds: round 1 = 384
attempts (3 ckpts x 8 prompts x 16 samples), later rounds up to 192; a proof is accepted only if all 16
judge samples (8 RL + 8 SFT) score it 1; finalists re-scored 48 times. Proofs found after ~707M tokens
and 1,464 GB200 GPU-hours; the full run ~2.31B tokens and ~4,785 GPU-hours. SFT: 414,890 examples, 512
GB200s; RL: 9,597 problems, 128 trainer + 128 inference + 16 judge nodes. Ensemble 188/210 on their dev
set vs 162-180 for single checkpoints.

**dots-note-3.0 (IMO 2026 42/42 official, NL)** -- agent with NL reasoning + Python execution, self-critique
of weak steps before answering; the P3 solution used a direct induction rather than the graph
reformulation most students used (China Daily). No technical report yet.

**Hilbert (PutnamBench 462)** -- arXiv 2509.22819 / ICLR 2026: informal reasoner + specialised Lean prover +
verifier + semantic retriever; on failure, recursive decomposition into subgoals. ~$163-170K Gemini spend
per Goedel-Architect's estimate.

**Aleph Prover (first 672/672)** -- planning (subproblems) / proving (Lean-kernel-checked) / refining the plan
from which subproblems succeed, "highly parallel Lean verification calls" (avg 1,841 Lean checks per
problem at the 500 level, max 37,061; 730 lines of Lean per proof on average; ~15 lemmas per proof, max 62).
https://logicalintelligence.com/aleph-prover.html

**Goedel-Architect (642 at $5.80)** -- arXiv 2606.06468 (2026-06-04). One *blueprint* per problem: a Lean
file of definitions and lemmas with declared dependencies and `sorry` bodies (retry up to 8 times to
compile); every open lemma goes in parallel to a tool-using Lean prover that sees only the lemma and its
parents; failed lemmas are diagnosed as "false statement" or "too hard" and the refinement model fixes
statements or adds helpers, keeping solved nodes (up to 16 iterations on PutnamBench). DeepSeek-V4-Flash
backbone; Gemini 3.1 Pro writes NL proofs for hard problems. Direct inference 6.5%, tool-integrated
single prover 54.5%, blueprint 75.6%, +NL guidance pass@4 88.8%. Negated sub-lemmas (counterexamples)
appeared on 292/672 problems and drive revision. "On nine hard problems the pipeline closed none without
natural-language guidance across 4-12 runs each."

**MechMath (Putnam 2025 11/12; IMO 2025 4/4 attempted)** -- arXiv 2603.24465, COLM 2026. The *Sorrifier*
compiles a failing proof, finds the innermost enclosing block of the primary error, replaces that block's
body (or truncates the line) with `sorry`, repeats until the file compiles, then extracts each `sorry` as a
self-contained subproblem. Ablation on Putnam 2025 A1-A4 at 128 LLM calls: discard-and-retry 0/4,
iterative whole-proof repair 3/4 (A4: 126 calls, 518 min, $55.70), Sorrifier 4/4 (A4: 88 calls, 114 min,
$19.90). Gemini 3.1 Pro as reasoner/verifier/prover; Kimina Lean server; budgets $100 Putnam / $200 IMO.
Informal proof first mattered: without it A2 was not solved. IMO 2025 P1 cost $141 and 363 min.

**h1 "A Taste of the Bitter Lesson" (Meta FAIR, arXiv 2610.35962, 2026-10-25)** -- a minimal harness
with no imposed decomposition or search: persistent working file with targeted edits, compiler feedback
after every edit, Lean REPL, language server for goals, LeanExplore/Loogle/grep, all of Mathlib imported,
retries and file restoration after Lean timeouts. Removing REPL/LSP/search drops Putnam100 from 69 to 49.
Matches or beats Goedel-Architect, Numina, AlphaProof Nexus and Humanfia at matched models and lower
cost; the authors conclude "an efficient Lean interface largely determines cost and solve rate". Note
that a frontier model doing its own planning inside a long agent loop is still decomposition, just not
a harness-enforced one.

**Numina-Lean-Agent (Putnam 2025 12/12 with Claude Opus 4.5)** -- arXiv 2601.14027: Claude Code + an MCP
server with Lean interaction, retrieval, informal proving; swapping the base model improves it without
training. In h1's matched comparison Numina without its informal prover drops to 4/12.

**AxiomProver** -- no technical report ("to follow", Axiom blog 2026-01-08
https://axiommath.ai/research/from-seeing-why-to-checking-everything/ ). Described only as an
"autonomous multi-agent ensemble theorem prover" over AXLE (Axiom's Lean cloud, 14 tools, >500M requests,
arXiv 2606.26442). Putnam 2025 12/12 with 8 in the exam window (A5: 2,054 lines, 518 min; A6 ~5 h);
Fel's conjecture (arXiv 2602.03716); 6/10 partition-polynomial conjectures.

**AlphaProof (Nature, 2025-11-12)** -- Lean environment, ~80M autoformalised statements, RL, and for the
hardest IMO 2024 problems test-time RL on millions of problem variants; 2-3 days of compute per problem in
2024 (DeepMind blog), quoted as ~500 TPU-days/problem by ByteDance. https://www.nature.com/articles/s41586-025-09833-y

**Human-in-the-loop** -- all formal IMO 2025 entries had humans formalise the statements; by 2026 Axiom,
Pramaana and MechMath autoformalised them (Pramaana human-checked). Research-level work (Erdős #728, Fel's
conjecture) is run by a human operator choosing the target. "Just Type It in Isabelle" (arXiv 2604.15713)
and "Sorries Are Not the Hard Part" (arXiv 2606.13925) both find that closing sorries is the easy part
and that human review is still needed for statement faithfulness, definitions and API design.

**Common threads, stated by the authors themselves:** (1) natural-language proof first, then a formal
skeleton whose lemmas are `sorry` placeholders, then per-lemma proving with verifier feedback (Seed-Prover
1.5, Goedel-Architect, MechMath, Aleph, Hilbert, Aristotle's lemma pipeline); (2) disproof/counterexample
as a first-class signal that a lemma statement is wrong (Seed-Prover 1.5, Goedel-Architect 292/672, Aleph
15 statements, Sorrifier); (3) long-horizon test-time compute with log-linear returns (Seed-Prover 1.5,
Goedel-Architect, Deep Think) and massive parallel verification; (4) geometry engines for geometry (Seed-
Geometry 2 s, Yuclid; Goedel-Architect calls IMO 2025 P2 "out of reach for a general-purpose Lean prover");
(5) ensembles/judges in NL (Nemotron's 16-of-16 unanimity); (6) repair with placeholders beats
regenerate-from-scratch (MechMath 4/4 vs 0/4 at equal budget); (7) the 2026 counter-trend (h1, NEAR AI,
Forall, Deedy's NL harness): with GPT-5.5/5.6-class models the harness can be minimal if the verifier
interface is tight -- cost drops to $0.17-$18/problem on PutnamBench.

---

## 4. Cost and scalability

**What a hard problem costs (published figures)**

| Setting | Figure | Source |
|---|---|---|
| AlphaProof, hardest IMO 2024 problems | 2-3 days; ~500 TPU-days/problem | DeepMind blog 2024; arXiv 2512.17260 |
| Seed-Prover 1.0 | medium = 18 H20-days/problem; heavy = "days" with 5,000-conjecture pools | arXiv 2507.23726 / 2512.17260 |
| Seed-Prover 1.5 | 10 H20-days/problem (PutnamBench), 40 max (Putnam 2025), ~20 (IMO 2025, P1 16.5 h) | arXiv 2512.17260 |
| OpenAI IMO 2025 | "millions of dollars" | Brown |
| Nemotron IMO 2026 | 4,785 GB200 GPU-hours total; 1,464 to the proofs actually found | arXiv 2609.10712 |
| Aleph PutnamBench | $23 -> $54 -> $68 -> $74 average as the budget cap rose $100 -> $1,468; single problems up to $1,468 | leaderboard JSON |
| Hilbert PutnamBench | ~$163K total (third-party estimate) | arXiv 2606.06468 |
| Goedel-Architect | $0.44/problem (one blueprint), $5.80 at 642 | arXiv 2606.06468 |
| h1 | $17.86 (GPT-5.5, 672), $81.52 on Putnam 2025 A5 alone, $8.07/problem IMO 2026 | arXiv 2610.35962 |
| Humanfia | $44.50/problem PutnamBench; $127 (GPT-5.6) / $58 (Kimi-K3) for IMO 2026 | leaderboard; humanfia repo |
| NEAR AI | mean $0.17, max $11.18 (DeepSeek V4) | leaderboard |
| Dirac / Pramaana IMO 2026 | $176.58 / $148.64 for all six | repos |
| Deedy NL IMO 2026 | $20-51 per full 42/42 run | repo |
| MechMath | $82 avg per IMO 2025 problem; Sorrifier vs repair $19.90 vs $55.70 on A4 | arXiv 2603.24465 |
| AlphaProof Nexus open Erdős problems | "a few hundred dollars" each | arXiv 2605.22763 |
| "Just Type It in Isabelle" | ~$140 per ~2,000-line Isabelle development | arXiv 2604.15713 |

Cost per competition problem fell roughly three orders of magnitude between IMO 2024 (TPU-days) and
IMO 2026 ($8-30/problem formal, $3-9/problem NL), mostly through better base models.

**How pipelines parallelise verification**
- Kimina Lean Server: one persistent REPL per core, idle-REPL routing; ~2.1 req/s at concurrency 8 on 8 vCPU, median 0.75 s, p90 6.4 s (measured in the AXLE paper, arXiv 2606.26442; original arXiv 2504.21230).
- AXLE (Axiom): multi-tenant cloud with per-request isolation, sub-second median `verify_proof`, >500M requests, MCP/HTTP/SDK (arXiv 2606.26442).
- Proof-state snapshotting (arXiv 2605.25556): import load ~60 s and theorem-body elaboration 18-735 s are >99% of per-branch wall time in portfolio tactic search; snapshotting gives 5.6-50x (median 9.7x) on miniF2F-v2 branches; a 2,800-branch job from ~29 h to ~3.5 h.
- Learned verifiers (arXiv 2610.21881): a GPU evaluator predicting Lean verdicts at 87.8% accuracy, 3.5 candidates/s per H100 = 4.2x a 64-worker Lean farm, used as a hybrid RL reward (31% shorter steps).
- Aleph: avg 1,841 (max 37,061) Lean checks per problem; Goedel-Architect: one prover per open lemma in parallel; Aristotle: "highly parallel" MCGS over a distributed GPU setup; Seed-Prover 1.0: distributed GPU processes with a CPU thread pool each for Lean.

**What fails at scale (reported)**
- *Verifier throughput and timeouts*: "AI now writes Lean proofs faster than Lean can check them" (eunomia.dev 2026-11-06): on OpenAI's AI-generated Lean library (163,096 files), Lean checks the median file at ~400 tokens/s per core, a 450-line file takes 2.6 h on one core, 1% of files take 25% of CPU time, `decide +kernel` appears 1,354,379 times (Mathlib: 7) and 3.6% of files take 18% of time; full first check 31.5 h on a 24-core desktop. h1: Erdős 125 timed out in all 16 attempts. This project's own `IB_LOAD_TIMEOUT` handling is the same failure class.
- *Context growth*: h1 -- 200 turns per iteration drops Putnam100 from 69 to 60 and FATE-X from 63 to 52 ("context rot"); MechMath's stated motivation for extracting sorries into fresh contexts; Seed-Prover 1.5 RL shortened trajectories 28K -> 17K tokens.
- *Statement defects*: Aleph counterexamples to 15 PutnamBench statements; Goedel-Architect negated sub-lemmas on 292/672; "Faults in Our Formal Benchmarking" 398 certified defects; Formal Conjectures 511 fix PRs; Varto "130 require formalization fixes" on the Isabelle set; Poincaré-conjecture statement missing a hypothesis (h1). Scores both inflate and deflate.
- *Infrastructure*: AxProverBase lost 42.2% of compile failures to invalid imports (h1 imports all of Mathlib); Claude Code runs died on repeated API errors/timeouts (h1); Deedy's runs lost time to orchestrator errors and models claiming to write files without calling the tool; humanfia reports a 2.5 h run with 0.7 h of infra retries.
- *Soundness*: "Summer of Soundness Bugs" 2026 -- several Lean kernel bugs (one admitting a disproof of Collatz) found by AI-assisted security researchers, all fixed, Mathlib re-verified (Hales on Tao's blog, 2026-10-09, https://terrytao.wordpress.com/2026/10/09/what-mathematicians-should-know-about-the-lean-theorem-proverquestions-of-reliability-and-ai/ ). Comparator/SafeVerify-style independent checking is now standard for leaderboards.
- *Geometry*: general Lean provers without a DD/AR engine spend hours on geometry (Axiom Q2 6 h; Goedel-Architect calls IMO 2025 P2 out of reach), while Seed-Geometry/Yuclid take seconds.

---

## 5. Isabelle/HOL for competition problems, 2025-2026

**Benchmarks and results**
- PutnamBench Isabelle (640): historically Sledgehammer 3, DSP(GPT-4o) 4; Varto 640/640 in Aug 2026 with GPT-5.5, ~$8 and ~16 min per problem, 130 statements needing fixes, self-reported and "under review" (section 2.2). This is the only Isabelle leaderboard entry since 2024 and the only large Isabelle result found.
- miniF2F Isabelle: HybridProver (arXiv 2505.15740, EMNLP Findings 2026) 73.8% in v2 (59.4% in v1; prior SOTA 56.4-61.9%) with two 7B models, proof sketches with `sorry` placeholders refined and closed by Sledgehammer with heuristics.
- PISA: Isabelle/Minilang (arXiv 2507.18885, OOPSLA 2026) -- a 10-operation proof language (HAVE, CONSIDER, RULE, CHOOSE, SIMPLIFY, CASE_SPLIT, INDUCT, END, NEXT, INTRO) whose END/NEXT steps discharge obligations via `auto` then an improved "Sledgehammer*" with `fastforce` in parallel; ~85% of 340K AFP/HOL Isar proofs auto-translated; pass@1 69.1% (vs Baldur pass@64 65.7%), pass@8 79.2% (vs Magnushammer 71.0%); Sledgehammer* is +6 points over stock Sledgehammer. Argues Lean/Isar expert tactics add learning burden.
- No Isabelle entry for IMO 2025/2026, Putnam 2025, FATE, or Formal Conjectures was found. The CLAUDE.md note that a DeepSeek run discharged all five IMO 2026 P1 theorems in `~/GitHub/isabelle-humanize` appears to be the only Isabelle IMO 2026 result in existence; it is unpublished.

**Sledgehammer-based pipelines and agent harnesses**
- Isabellm / "Vibe Coding an LLM-powered Theorem Prover" (Zhe Hou, arXiv 2601.04653, 2026-01-08; https://github.com/zhehou/llm-isabelle ): beam-search stepwise prover over `apply`/finisher commands with rerankers, premise selection, Quickcheck/Nitpick pruning, plus an Isar planner that emits outlines with gaps and a CEGIS-style repair loop; runs on an M1 MacBook with local models; **no quantitative evaluation**; the author reports that repair stages "rarely succeed beyond trivial cases" and most successes come from the initial outline or the stepwise prover. Its README mentions a PutnamBench-Isabelle benchmark command (Isabelle2025).
- IsabeLLM (arXiv 2606.18098, 2026-06-16): RAG + error tracing + counterexamples, latest Sledgehammer; target is Bitcoin PoW verification, no numbers on the abstract page.
- LLMemma (ResearchGate, 2026-06-12, D. Busing): Isar skeleton fallback with each hole closed by Sledgehammer / fixed tactics / fact-closer / LLM decomposition; unverified, no arXiv version found.
- Apply2Isar (arXiv 2603.07771): apply-style -> structured Isar conversion.
- "Just Type It in Isabelle!" (Kappelmann, Schäffeler, Stevens, Abdulaziz, Popescu, Traytel; arXiv 2604.15713, Apr-Jun 2026): Claude Opus 4.6 in OpenCode driving **Isabelle/Q**, an Isabelle/jEdit MCP server exposing theory editing, fact search, Sledgehammer and proof states. Two ~2,000-line sorry-free developments at ~$140 each after human review rounds; failure modes: skipping the incremental workflow and writing big Isar blocks then fixing errors, misreading a non-terminating method, verbose object-level quantification, copying rather than importing, mis-scoped locale assumptions that a human caught. Hypothesis (not measured) that human hints make LLM proving cheaper.
- MCP servers: xqyww123/Isabelle-MCP (stdio, one session per agent, `isabelle_launch/evaluate_to/goal/hover/find_theorems/command_output`, ML debugger; Claude Code and Codex; Isabelle2026; **no Sledgehammer tool**), ZhichengHui / FullBackward / Deep-LCF Isabelle-Pool-Server (warm session pool behind REST with two MCP servers -- this project's server), ppetr/llm-math-prover (kernel-checked `isabelle_check_theory` tool), jcschuster/AtpMcp (`prove_isabelle`). Isabelle2026 was released October 2026.

**Lean vs Isabelle for LLM provers**
- No 2026 head-to-head study exists. The 2024 PutnamBench paper found Sledgehammer the strongest single baseline across all three languages (5 of the 6 problems solved in any language); by 2026 Lean has 10+ systems at 597-672/672 while Isabelle has one self-reported 640/640 with 130 fixes.
- Stated reasons for Lean's lead (HybridProver, Discover-and-Prove, "From Solvers to Research" arXiv 2607.07779): Mathlib is the largest *mathematics* library and every open prover model (DeepSeek-Prover, Goedel, Kimina, Leanstral) and every leaderboard targets Lean; Isabelle's AFP is larger in lines (5M+ vs 1.9M+) and theorems (~200K vs ~140K) but skewed to systems verification. Isabelle's advantage is Sledgehammer, which Lean lacks (Lean-SMT, aesop, `grind`, LeanHammer are partial replacements); Isabelle work therefore keeps the "sketch + hammer" shape (DSP, HybridProver, Minilang, LLMemma), which is exactly this project's skeleton arm.
- Verification-side: Isabelle's PIDE keeps sessions warm but a session is single-threaded mutable state (Isabelle-MCP README), so parallelism means session pools (IPS) -- the same import-load problem that Lean solved with REPL pools and snapshotting (60 s import per branch in Lean).

**Implications for this experiment**
1. The field's best formal results all use the shape this project's *skeleton* arm enforces (NL plan -> `sorry` skeleton -> per-lemma fill with verifier feedback -> repair of false lemmas), and the strongest ablation evidence is MechMath's 4/4 vs 3/4 vs 0/4 and Goedel-Architect's 6.5% -> 54.5% -> 75.6% -> 88.8%. But h1 shows a frontier model with a tight verifier interface can match or beat enforced decomposition; with DeepSeek-class models the open question is whether the model is strong enough to self-decompose.
2. Per-goal Sledgehammer has no published 2025-26 competition result better than PutnamBench's 3/640; every Isabelle gain since has come from LLM sketches with hammers closing leaves. The experiment's *per-goal-sledgehammer* arm is therefore testing the 2022 DSP shape against the 2025-26 skeleton shape.
3. Nobody has published an Isabelle result on IMO 2025/2026; this harness would be the first. Expect Q3 to dominate budget (14.5 h / 4,229 lines for Axiom in Lean) and Q2 to be hard without a geometry engine.
4. Budget comparables: $8-$30 per formal IMO 2026 problem for GPT-5.6-class systems; NEAR AI's $0.17 mean on PutnamBench with DeepSeek V4.

---

## 6. Unverified or conflicting items

- Whether the IMO itself graded any AI entries in 2026 (only company statements via AFP/China Daily; one blog says the IMO does not recognise AI participants).
- Any IMO 2026 result for Gemini Deep Think, OpenAI (official), Seed-Prover, Aristotle; "Seed-Prover 2" existence; Claude Opus 5 42/42 (benchlm.ai only).
- Varto's 640/640 Isabelle (self-reported; 130 fixes; maintainers "reviewing").
- AxiomProver's internals (no technical report); whether its IMO 2026 run had any human involvement.
- Hilbert's ~$163K cost (Goedel-Architect estimate, "likely an underestimate").
- The eunomia.dev checking-cost numbers (single blog, one machine).
- tech-insider.org articles are internally inconsistent (dates, counts) and were used only as pointers.
