# LLM theorem-proving systems and pipelines, 2022–2026: a survey for the nearAI_Isabelle experiment

Compiled 2026-11-10. Sources are primary where possible (arXiv abstracts/full texts, GitHub READMEs, the PutnamBench `docs/results.json`, Nature supplementary PDF, vendor blogs). Every number is given with the pass budget its authors report. Items marked **[unverified]** come from secondary sources or could not be checked against a primary text; **[self-reported]** marks vendor claims with no independent grading.

The experiment this survey serves compares, in Isabelle/HOL with DeepSeek driving an MCP tool server, (A) a plain agent that calls sledgehammer per goal against (B) an agent forced to write a `sorry` skeleton that the server then fills (`fill_sorries`). The literature has a direct lineage for arm (B): DSP (2022) -> POETRY (2024) -> DeepSeek-Prover-V2 cold start, Hilbert, Seed-Prover 1.5 sketch model, Aristotle (2025) -> MechMath, Goedel-Architect, the Munkres Isabelle project (2026). Arm (A) descends from Thor (2022) and Lyra (2023).

---

## 0. Quick reference table

| System | Year | Prover | Granularity | Training | Headline result (budget) |
|---|---|---|---|---|---|
| Thor | 2022 | Isabelle | step + hammer token | fine-tuned 700M | miniF2F-test 29.9% (300 LM queries, 500 s); PISA 39.0->57.0% |
| DSP | 2022 | Isabelle | sketch + sledgehammer fill | prompted (Codex/Minerva) | miniF2F-test 39.3% human drafts, 38.9% Minerva-540B (100 attempts) |
| Magnushammer | 2023 | Isabelle | premise selection | contrastive transformer | miniF2F 34.0% vs Sledgehammer 20.9%; PISA 59.5% vs 38.3% |
| Baldur | 2023 | Isabelle | whole proof + repair | fine-tuned Minerva 8B/62B | PISA 47.9% (64 samples); 65.7% union with Thor |
| Lyra | 2023 | Isabelle | sketch + tool/conjecture correction | prompted GPT-4 | miniF2F-test 51.2% |
| LEGO-Prover | 2023 | Isabelle | sketch + growing lemma library | prompted GPT-3.5/4 | miniF2F-test 47.1%, valid 57.0% |
| POETRY | 2024 | Isabelle | recursive `sorry` sketches | fine-tuned 1.3B | miniF2F 42.2%/42.2% (pass@1, 600 s) |
| SubgoalXL | 2024 | Isabelle | subgoal proofs, expert learning | fine-tuned | miniF2F-test 56.1% (16,384 queries) |
| Lean-STaR | 2024 | Lean 4 | step + thoughts | fine-tuned 7B | miniF2F-test 46.3% (pass@64) |
| DeepSeek-Prover-V1.5 | 2024 | Lean 4 | whole proof + RMaxTS | RL (RLPAF) 7B | miniF2F-test 63.5% (32x6400); ProofNet 25.3% |
| InternLM2.5-StepProver | 2024 | Lean 4 | step, BFS + critic | expert iteration, 20k CPU-days | miniF2F-test 65.9% (256x32x600); PutnamBench 6 |
| HunyuanProver | 2024 | Lean 4 | step, BFS + distance critic | fine-tuned 7B | miniF2F-test 68.4% (600x8x400) |
| AlphaProof | 2024/Nature 2025 | Lean 4 | step, MCTS, test-time RL | RL, ~80k TPU-days | IMO 2024 28/42 (with AG2), 2–3 days TTRL per problem |
| BFS-Prover | 2025 | Lean 4 | step, plain BFS | expert iteration + DPO 7B | miniF2F-test 70.83% (2048x2x600); 72.95% accumulative |
| ProofAug | 2025 | Isabelle (+Lean) | proof-structure-aware automation | prompted 7B base | miniF2F-test 66.0% curated / 61.9% (2,100 queries) |
| Goedel-Prover V1 | 2025 | Lean 4 | whole proof | SFT + expert iteration | miniF2F 57.6% (pass@32); PutnamBench 7 (pass@512) |
| Leanabell-Prover | 2025 | Lean 4 | whole proof | continued training + RL | miniF2F-test 59.8% (pass@32) |
| Kimina-Prover | 2025 | Lean 4 | whole proof, long CoT, TTRL search | RL from Qwen2.5-72B | miniF2F-test 80.7% (pass@8192) Preview; 72B: 84.0% pass@32, 92.2% TTRL search |
| DeepSeek-Prover-V2 | 2025 | Lean 4 | subgoal decomposition -> whole proof | RL 671B (and 7B) | miniF2F-test 88.9% (pass@8192); PutnamBench 47/658 (pass@1024) |
| APOLLO | 2025 | Lean 4 | repair pipeline | prompted/plug-in | Goedel-SFT 65.6% miniF2F at a few hundred samples |
| Delta-Prover | 2025 | Lean 4 | reflective decomposition + repair | prompted Gemini 2.5 Pro | miniF2F-test 95.9% (budget 16,384 API calls) |
| Prover Agent | 2025 | Lean 4 | informal + lemmas + prover | small models | miniF2F 88.1%; PutnamBench 25 |
| Goedel-Prover V2 | 2025 | Lean 4 | whole proof + self-correction | SFT/RL 8B, 32B, model averaging | miniF2F 90.4% (pass@32, self-corr); PutnamBench 86 (pass@184) |
| Seed-Prover 1.0 | 2025 | Lean 4 | lemma-style whole proof, 3 inference tiers | RL | IMO 2025 5/6 (4 in contest); PutnamBench 331/657 (medium) |
| Hilbert | 2025 | Lean 4 | recursive `have ... sorry` decomposition | prompted reasoner + open prover | miniF2F 99.2%; PutnamBench 462/660 (avg 1,840 LLM calls) |
| Aristotle | 2025 | Lean 4 | MCGS over sketches + lemma pipeline | RL, >200B model, test-time training | IMO 2025 5/6 (gold-equivalent) |
| Gauss | 2025 | Lean 4 | autoformalization agent | proprietary | strong PNT, ~25k lines in ~3 weeks |
| Seed-Prover 1.5 | 2025 | Lean 4 | agentic lemma-at-a-time + sketch model | agentic RL | PutnamBench 580/660 (10 H20-days/problem); Putnam 2025 11/12 in 9 h |
| Numina-Lean-Agent | 2026 | Lean 4 | general coding agent + MCP | prompted Claude Opus 4.5 | Putnam 2025 12/12 |
| MechMath | 2026 | Lean 4 | sorrifier decomposition of failed proofs | agentic | efficiency claims (no table in abstract) |
| Goedel-Architect | 2026 | Lean 4 | blueprint DAG, parallel lemma proving | prompted DeepSeek-V4-Flash | miniF2F 99.2% pass@1; PutnamBench 597/672 ($1.47/problem) -> 642 ($5.8) |
| OProver | 2026 | Lean 4 | agentic repair in training | 32B | miniF2F 93.3% (pass@32); PutnamBench 11.3% |
| Leanstral 1.5 | 2026 | Lean 4 | multiturn + code agent | RL (CISPO), 119B/6B active | PutnamBench 587/672 (pass@8, 4M tokens); miniF2F 100% |
| Aleph | 2025–26 | Lean 4 | plan/prove/refine orchestration | prompted GPT-5.2 | PutnamBench 668/672 (Jan 2026, avg $68) -> 672 (Aug 2026, avg $74) |
| AxiomProver | 2026 | Lean 4 | multi-agent ensemble | proprietary | IMO 2026 42/42 **[self-reported]**, ~25 h total |
| Humanfia/Humanize | 2026 | Lean 4 | builder/reviewer agent loops | prompted GPT-5.6 | PutnamBench 672/672 (avg $44.5); IMO 2026 6/6 Lean **[self-reported]** |
| Magenta | 2026 | Lean 4 | NL answer -> Lean statement -> proof | training-free | IMO 2026 6/6 with K2-Horizon-7B **[unverified]** |
| NEAR AI putnambench-deepseek | 2026 | Lean 4 | single bash tool, nudge loop | prompted DeepSeek V4 | PutnamBench 672/672, mean $0.17, max 78 h |
| Varto | 2026 | Isabelle | undisclosed agent | prompted GPT-5.5 | PutnamBench-Isabelle 640/640, avg $8, avg 16 min |

---

## 1. Isabelle-based systems

### 1.1 Thor (Jiang et al., 2022)
- **Year / prover:** May 2022; Isabelle (PISA environment, Isabelle2021).
- **Granularity:** step-level tactic prediction; the LM may emit a special `<hammer>` token instead of a tactic, at which point Sledgehammer is invoked on the current goal.
- **Search / compute:** best-first search ordered by cumulative log-likelihood; queue max length 32; per-step timeout 10 s; stop after 300 LM queries or 500 s wall-clock; sampling T=1.2; about 60 TPU-hours per 1,000 problems.
- **Automation:** Sledgehammer with the default 30 s timeout and five on-machine ATPs (E, SPASS, Vampire, Z3, CVC4). Design principle: "hammers for premise selection, language models for everything else".
- **Self-correction:** none beyond search.
- **Training:** fine-tuned 700M-parameter decoder on PISA; `metis`/`meson`/`smt` steps in the corpus are rewritten as `<hammer>` so the model learns *when* to call the hammer, not which premises to pass.
- **Results:** PISA 39.0% (LM) -> 57.0% (Thor); Sledgehammer alone 25.7%; LM-union-Sledgehammer 48.8%, so 8.2% of problems need the interleaving. miniF2F valid/test: Sledgehammer 9.9/10.4; LM 25.0/24.2; LM-union-SH 27.1/27.5; Thor 28.3/29.9 (prior SOTA 29.6% with far more compute).
- **Lesson:** premise selection over a large library is the LM bottleneck; delegating it to a hammer gives large gains at small compute. A loose union of LM and hammer is much weaker than tight interleaving.
- **URL:** https://arxiv.org/abs/2205.10893

### 1.2 Draft, Sketch, and Prove (DSP; Jiang et al., 2022 / ICLR 2023)
- **Year / prover:** Oct 2022; Isabelle2021.
- **Granularity:** sketch + fill. An informal draft (human or LM) is mapped to a declarative Isar *formal sketch* whose intermediate conjectures are left open (a special token marks each open gap); an automated prover then closes every gap.
- **Search / compute:** 100 autoformalization attempts per problem (figure 3 plateaus at ~70); human drafts reach the plateau in ~7 attempts. 200 of 488 miniF2F problems proved overall.
- **Automation:** Sledgehammer, default Isabelle2021 configuration, **120 s timeout**, five ATPs; plus 11 heuristic tactics (`auto`, `simp`, `blast`, `fastforce`, `force`, `eval`, `presburger`, `sos`, `arith`, `linarith`, `auto simp: field_simps`) each tried with a 10 s timeout before falling back to Sledgehammer.
- **Self-correction:** none; diversity comes from resampling drafts/sketches.
- **Training:** none (Codex, Minerva 8B/62B/540B, few-shot).
- **Results (miniF2F valid/test):** Sledgehammer 9.9/10.4; Sledgehammer+heuristics 18.0/20.9; Thor 28.3/29.9; Thor+expert iteration 37.3/35.2; DSP human drafts 42.6/39.3; Codex drafts 40.6/35.3; Minerva-8B 40.6/35.3; Minerva-62B 43.9/37.7; Minerva-540B 42.6/38.9. **Ablation without open conjectures** (LM must write complete proofs): -9.8 valid / -9.0 test points, "the essential role of automated provers". PutnamBench (2024) later measured DSP with GPT-4o at 4/640 Isabelle problems (pass@10) against 3/640 for bare Sledgehammer at 120 s.
- **Failure analysis worth remembering:** of 50 Minerva drafts whose sketches *did* close, only 29 informal proofs were entirely correct, 16 had an identifiable wrong step and 5 were nonsense; the automation closed gaps regardless. Human drafts sometimes "leave gaps between conjectures that are too difficult for automated provers", and LM drafts solved one IMO problem (1959 P1) that the human draft did not.
- **Lesson:** the sketch's job is to cut the problem into gaps a hammer can close; the informal draft need not be right for this to work; sledgehammer timeouts dominate wall-clock.
- **URL:** https://arxiv.org/abs/2210.12283

### 1.3 Magnushammer (Mikula et al., 2023 / ICLR 2024)
- Isabelle; learned premise selection (contrastive transformer) replacing Sledgehammer's relevance filter + ATP round-trip. PISA 59.5% vs Sledgehammer 38.3%; miniF2F 34.0% vs 20.9%. Combined with Thor's LM: PISA 57.0% -> 71.0% with 4x fewer parameters. Released an Isabelle (proof state, premise) dataset. **Lesson:** the premise-selection component, not the ATP, is where the hammer's recall is lost; a learned selector plus Isabelle's own methods can beat the full ATP pipeline.
- **URL:** https://arxiv.org/abs/2303.04488

### 1.4 Baldur (First et al., 2023)
- Isabelle/HOL, PISA (6,336 test theorems); whole-proof generation with fine-tuned Minerva 8B/62B; a separate *repair model* takes (statement, failed proof, error message).
- **Results:** 8B generate 34.8% (16 samples) / 40.7% (64); 8B generate+repair 36.3% at matched budget (half the samples, one repair each); 8B with file context 40.9/47.5; 62B with context 42.2/47.9; union with Thor 65.7% (Thor alone 57.0%; Sledgehammer 25.6%).
- **Lesson:** error-message repair helps but at matched sample budget the gain is modest (+1.5 points); preceding theory-file context helped more. Whole-proof generation matches search-based methods without search.
- **URL:** https://arxiv.org/abs/2303.04910

### 1.5 Lyra (Zheng et al., 2023 / TMLR 2024)
- Isabelle, GPT-4, DSP-style sketches plus two corrections: **Tool Correction** (post-process hallucinated or failing tool calls by substituting predefined Isabelle automation such as the sledgehammer heuristics) and **Conjecture Correction** (feed prover error messages back to revise the sketch's conjectures). miniF2F valid 48.0->55.3%, test 45.5->51.2%; 3 IMO problems. **Lesson:** replacing bad tool calls mechanically "significantly contributes to mitigating hallucinations"; error feedback improves sketches without collecting paired repair data.
- **URL:** https://arxiv.org/abs/2309.15806

### 1.6 LEGO-Prover (Wang et al., 2023 / ICLR 2024)
- Isabelle, GPT-3.5/GPT-4; modular proofs built from a *growing skill library* of verified lemmas (retrieve, create, evolve). miniF2F valid 48.0->57.0%, test 45.5->47.1%; >20,000 lemmas generated; ablation attributes 47.1->50.4 to the library. **Lesson:** a fixed library caps LLM provers; verified reusable lemmas are a transferable asset (the same idea reappears in Seed-Prover's lemma pool and ProofEvolve's schema library).
- **URL:** https://arxiv.org/abs/2310.00656

### 1.7 POETRY: Proving Theorems Recursively (Wang et al., 2024 / NeurIPS 2024)
- Isabelle; **recursive, level-by-level sketches in which deeper conjectures are replaced by `sorry`**, e.g. `have "..." sorry`, chosen jointly with the step by the model. Best-first search finds a sketch at the current level, pauses, recurses into each `sorry`; a failed sub-search propagates FAILED upward and the paused search looks for a new sketch (node states OPEN/FAILED/PROVED/HALF-PROVED). Budget: 600 s global, 10 s per step, 120 s per deeper level, 32 samples per expansion, 128 expansions, max depth 10; 1.3B model.
- **Results (pass@1):** miniF2F valid/test 42.2/42.2 vs step-wise GPT-f baseline 39.3/37.3 and Thor+Magnushammer 36.9/37.3; PISA 49.6 (multi-level subset 13.6 vs 11.1). Max proof length found grew 10 -> 26 on PISA; per-sketch length 3.3 steps vs 12.7 for flat proofs.
- **Lesson:** recursion shrinks the search per level; the model may propose *false* conjectures, handled by letting the sub-search fail and resketching; gains are orthogonal to Sledgehammer/retrieval/expert iteration (left for future work).
- **URL:** https://arxiv.org/abs/2405.14414

### 1.8 SubgoalXL (Zhao et al., 2024)
- Isabelle; subgoal-based proofs plus expert learning that iteratively refines formal-statement, proof and subgoal generators. miniF2F 56.1% (ProofAug reports this used 16,384 queries per problem); 41 AMC12, 9 AIME, 3 IMO. **Lesson:** subgoal-level supervision extracts more from scarce human proofs.
- **URL:** https://arxiv.org/abs/2408.11172

### 1.9 ProofAug (Liu, Sun, Li, Yao; ICML 2025)
- Isabelle (plus a Lean 4 port); analyses the structure of an LLM proof proposal and applies automation at several granularities (whole block, sub-blocks, single steps), plugging into any tree search as a recursive proving module. With deepseek-math-7b-base: miniF2F-test 66.0% on the curated set / 61.9% original with 2,100 queries, versus SubgoalXL 56.1% at 16,384; 52.5% with <=100 queries. In Lean 4 it lifts Kimina-Distill-1.5B pass@1 44.3->50.4%. **Lesson:** salvaging the correct skeleton of a failed proof and re-automating the broken pieces is far cheaper than resampling.
- **URL:** https://arxiv.org/abs/2501.18310

### 1.10 HybridProver (Hu, Zhang, Zhao, Ringer; 2025, EMNLP Findings 2026)
- Isabelle; whole-proof synthesis + tactic-based refinement with *proof sketches as the intermediate representation* so partially correct structure is reused; two post-trained 7B models. v2 reports miniF2F 73.8% vs prior 61.9%; v1 reported 59.4% and noted one run cost 300 CPU-hours for 244 theorems at 32 samples. Sledgehammer is the hammer **[per search snippet; not confirmed in the abstract]**.
- **URL:** https://arxiv.org/abs/2505.15740

### 1.11 Munkres' General Topology autoformalized in Isabelle/HOL (Bryant, Huerta y Munive, Kaliszyk, Urban; Apr 2026)
- The closest published analogue to arm (B). Claude Opus runs in tmux under a CLAUDE.md with rules "sorry-first, prefer small lemmas, try sledgehammer before manual tactics". Workflow: the agent writes a skeleton where every major step ends in `sorry`; **each `sorry` is replaced by a sledgehammer call with a ~10 s timeout and the build runs all of them in parallel**; successes (blast/auto/metis) are substituted in; failures are split by the LLM into smaller `sorry` sub-steps; slow proofs profiled.
- **Results:** 806 results, zero `sorry`, 85,472 lines, 199 definitions, ~3.1 helper lemmas per textbook result; 24 active days; about $160 of Opus subscription; Tietze in 324 lines vs 10,369 in Megalodon.
- **Failure modes:** weak definitions (e.g. topology predicate not requiring T a subset of P(X)); missed hypotheses from prose; verbose proofs; "tactic explosion" (repeating failed tactics) and "cherry-picking" (solving easy lemmas, avoiding hard ones), fixed by CLAUDE.md edits or chat nudges. One-shot full proofs "led to hallucinations or logical dead ends", motivating sorry-first.
- **URL:** https://arxiv.org/abs/2604.07455

### 1.12 Other 2026 Isabelle work
- **Neuro-symbolic proof generation for systems verification (OSDI'26; arXiv 2603.19715):** new Isabelle REPL exposing proof states; best-first search over states with a fine-tuned LLM proposing steps; symbolic tools repair rejected steps, filter/rank states and discharge subgoals when search stalls; up to 77.6% of seL4 (FVEL) theorems, beating standalone Sledgehammer. https://arxiv.org/abs/2603.19715
- **Isabellm (Hou, Jan 2026; arXiv 2601.04653):** LLM-written Isabelle prover with a stepwise prover and an Isar-outline planner that fills and repairs gaps; qualitative claim that it proves some lemmas Sledgehammer cannot; the author reports frontier models "struggled to reliably implement the intended fill-and-repair mechanisms". https://arxiv.org/abs/2601.04653
- **IsabeLLM (Jones & Knottenbelt, 2026; arXiv 2606.18098):** Isabelle + LLM with RAG, error tracing, counterexample generation, Sledgehammer-based repair, applied to Bitcoin PoW consensus; no benchmark table. https://arxiv.org/abs/2606.18098
- **Varto (blog 2026-07-23):** PutnamBench Isabelle 640/640 with GPT-5.5 at medium/high reasoning; average ~$8 per problem (median $6, range <$1–$67); average ~16 min (median 14, range <2–121 min); credits "self-learning skills, Isabelle's built-in proof tactics, and the Archive of Formal Proofs"; claims 8x cheaper and 23x faster than the top Lean entry of 2026-07-20. The leaderboard note adds "130 requires formalization fixes" and the blog charts show 100 targets, so treat as **[self-reported; architecture undisclosed]**. https://varto.com/blog/putnambench
- **Baseline anchor:** PutnamBench (2024) Isabelle track: Sledgehammer 3/640 (pass@1, 120 s), DSP(GPT-4o) 4/640 (pass@10).

---

## 2. Lean step-level / search provers

### 2.1 Lean-STaR (Lin, Sun, Welleck, Yang; 2024)
- Lean 4; emits an informal "thought" before each tactic; synthetic thoughts from retrospective ground-truth tactics; expert iteration (STaR). miniF2F-test pass@64 43.4 -> 46.3% (search 64x1x50). **Lesson:** informal rationale absent from formal corpora helps even at step level.
- https://arxiv.org/abs/2407.10040

### 2.2 InternLM2.5-StepProver (Wu et al., 2024)
- Lean 4; 7B prover + 1.8B critic trained on path/sibling preference pairs (454K); best-first search, 32 tactics per state, 600 expansions, T=0.7. miniF2F-test 59.4% (BF) / 65.6% (critic) / 65.9% (both) at 256x32x600; ProofNet 27.0% at 256x32x600; Lean-Workbook-Plus 17.0% solved (13.1% proved, 3.9% disproved); PutnamBench 6 (pass@2x32x600). Expert iteration cost ~21,364 CPU-days. **Lessons:** plain best-first "degrades into brute force" beyond ~10,000 s per problem; the critic finds deeper proofs (4.44 vs 1.66 tactics on average); 1.5% of CPU time produced all the solved problems, the rest went to never-solved ones.
- https://arxiv.org/abs/2410.15700

### 2.3 HunyuanProver (Li et al., Dec 2024)
- Lean 4, Hunyuan 7B; iterative data synthesis (~20M autoformalized statements, >20M tactic examples) and BFS with a *distance critic*. miniF2F-test 68.4% at 600x8x400; distance critic beats policy-confidence by ~3.7 points (68.44 vs 64.75). **Lesson:** trained critics and harder-data curation matter more than search algorithm choice.
- https://arxiv.org/abs/2412.20735

### 2.4 BFS-Prover (ByteDance Seed; Feb 2025)
- Lean 4, Qwen2.5-Math-7B; plain best-first search, 10 expert-iteration rounds filtering out beam-solvable problems, DPO on (on-path tactic, Lean-error tactic) pairs, length normalisation alpha=0.5. miniF2F-test 70.83 +/- 0.89% at 2048x2x600; 72.95% accumulated over alpha in {0, 0.5, 1}. **Lesson:** simple BFS scales to match critic/MCTS systems, but pass@k grows logarithmically with "diminishing returns", which the authors see as a limit of search-only scaling.
- https://arxiv.org/abs/2502.03438

### 2.5 AlphaProof (Google DeepMind; IMO July 2024; Nature 12 Nov 2025, doi 10.1038/s41586-025-09833-y)
- Lean 4; 3B encoder-decoder with policy and value heads; AlphaZero/Sampled-MuZero-style MCTS over tactics with an AND-OR tree (value = min over subgoals, rewarding balanced splits; each tactic costs -1).
- **Training pipeline:** ~300B tokens pretraining; SFT on ~300K Mathlib state-tactic pairs (~10 TPU-days); Gemini-based autoformalization of ~1M informal problems into ~80M Lean statements (~100,000 TPU-days); main RL ~80,000 TPU-days with a matchmaker prioritising informative problems.
- **Test-time RL (TTRL):** for an unsolved target, generate a curriculum of hundreds of thousands of Lean-validated variants (simplifications, generalisations, decompositions, up to 15 evolutionary iterations) and run RL on them.
- **Results:** IMO 2024: P1, P2, P6 proved (each after 2–3 days of TTRL), P4 by AlphaGeometry 2, P3/P5 (combinatorics) unsolved; 28/42, one point below gold. Supplementary Table 1 solve rates (formal-imo algebra/combinatorics/number theory; putnam-test algebra/analysis/geometry/linear algebra/number theory): 2 TPU-min 44.8/11.2/38.6; 26.9/40.1/4.3/16.5/27.2. 12 TPU-h 53.1/13.5/61.3; 41.2/43.0/39.5/16.7/39.5. TTRL 50 TPU-days 67.9/17.6/70.3; 48.7/51.8/30.0/27.8/57.6. TTRL 500 TPU-days 72.6/20.3/75.7; 61.5/64.3/35.0/38.9/66.7. miniF2F-valid reaches 100% with TTRL. Seed-Prover 1.5 cites AlphaProof at 56.1% PutnamBench and ~500 TPU-days per problem.
- **Lessons stated:** search scaling 2 TPU-min -> 12 TPU-h adds >10 points; TTRL adds ~15 more; combinatorics stays weak (20.3%); the compute is "far beyond" contest limits; research mathematics needs theory building, an open challenge.
- URLs: https://www.nature.com/articles/s41586-025-09833-y ; supplementary https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41586-025-09833-y/MediaObjects/41586_2025_9833_MOESM1_ESM.pdf ; https://deepmind.google/blog/ai-solves-imo-problems-at-silver-medal-level/

---

## 3. Lean whole-proof RL provers

### 3.1 DeepSeek-Prover-V1.5 (Aug 2024)
- Lean 4, 7B; SFT on V1 data, then RL from proof-assistant feedback (RLPAF, GRPO); RMaxTS, an MCTS variant with intrinsic (novelty) reward; truncate-and-resume lets the whole-proof model act as a tree-search policy. miniF2F-test 63.5% (RL+RMaxTS; BFS-Prover decomposes this budget as 32x6400); ProofNet 25.3%.
- https://arxiv.org/abs/2408.08152

### 3.2 Goedel-Prover V1 (Princeton; Feb 2025)
- Lean 4; autoformalised 1.64M statements (Goedel-Pset-v1), expert iteration producing >800K proofs; SFT of DeepSeek-Prover-V1.5-Base. miniF2F 57.6% pass@32 (SFT), >60% after RL/DPO; PutnamBench 7 (pass@512); 29.7K Lean Workbook proofs released. **Lesson:** data scarcity is the bottleneck; statement autoformalisation plus iterative proving fixes it.
- https://arxiv.org/abs/2502.07640

### 3.3 Leanabell-Prover (Apr 2025)
- Lean 4; continued training on statement-proof pairs plus "cognitive behaviour" data, then RL with Lean outcome rewards, applied to DeepSeek-Prover-V1.5 and Goedel-Prover; miniF2F-test 59.8% pass@32 (vs 50.0 / 57.6 for the bases).
- https://arxiv.org/abs/2504.06122

### 3.4 Kimina-Prover (Numina + Moonshot; Apr/Jul 2025)
- Lean 4; Qwen2.5-72B trained with the Kimi k1.5 RL pipeline to produce a "formal reasoning pattern" (long CoT interleaving informal reasoning and Lean snippets). Preview: miniF2F-test 80.7% pass@8192; pass@1 ~52.9% **[secondary]**; distilled 1.5B/7B released; first clear gain with model size for a formal prover.
- **Kimina-Prover-72B (blog 2025-07-10):** pass@1 63.9%, pass@32 84.0%, pass@1024 87.7%; one error-correction round lifts pass@32 to 86.4%; the full **test-time RL search** framework reaches 92.2% at an estimated upper bound of ~42,000 samples. Components: RL training with lemma-augmented prompts; **sublemma generation** triggered after N=128 failed attempts (a general LLM proposes lemmas in natural language, Kimina-Autoformalizer-7B formalises them; recursive); **negation filtering** (try to prove the negation; discard inconsistent lemmas); a per-scope lemma pool with utilisation scores (pruned below 0.10 after 50 insertions). On a 59-problem hard subset, 16+16 attempt-and-fix scored 35.6% vs 28.8% for 32x1 brute force; 32+32 reached 44.1%. Authors note "a large portion of the current sampling is spent on proving unhelpful or redundant lemmas".
- **Kimina Lean Server (arXiv 2504.21230):** REPL pooling, LRU import cache, batched parallel verification; 1.5–2x faster than previous tools; used by Hilbert as the verifier.
- URLs: https://arxiv.org/abs/2504.11354 ; https://huggingface.co/blog/AI-MO/kimina-prover ; https://arxiv.org/abs/2504.21230

### 3.5 DeepSeek-Prover-V2 (Apr 2025, v2 Jul 2025)
- Lean 4; 7B and 671B (on DeepSeek-V3-Base).
- **Subgoal decomposition cold start:** DeepSeek-V3 writes an informal sketch and a Lean statement made of `have` steps each ending in `sorry`; a 7B prover recursively fills each subgoal; composed proofs appended to V3's CoT form the cold-start data (hundreds of examples).
- **RL:** GRPO, binary reward, 256 problems x 32 candidates per step, 32,768-token limit; early on a *consistency reward* penalises proofs that omit the decomposed `have` lemmas.
- **Results (miniF2F-test, pass@32 / pass@8192):** 7B non-CoT 68.0/75.0; 7B CoT 75.6/82.0; 671B non-CoT 73.8/78.3; 671B CoT 82.4/88.9. PutnamBench 47/658 at pass@1024 (initially 49; two misformalised statements excluded); 7B CoT 11; ProverBench 59.1% at pass@512; AIME 24-25 subset 6/15 (DeepSeek-V3 informal majority vote 8/15). The 7B's 13 "extra" Putnam solves were a Lean 4.9.0 `apply?` bug the model learned to exploit and were retracted.
- **Lessons:** CoT beats non-CoT at every budget ("inference-time scaling works"); automation tactics can be gamed by RL; informal-formal gap "substantially narrowing".
- https://arxiv.org/abs/2504.21801 ; https://github.com/deepseek-ai/DeepSeek-Prover-V2

### 3.6 Goedel-Prover V2 (Aug 2025)
- Lean 4; 8B and 32B. **Scaffolded data synthesis:** `extract_goal` captures unsolved subgoals (and their negations) from failed attempts; Qwen3-32B generates easier/harder informal variants. **Verifier-guided self-correction:** first attempt 30K tokens, then 2 compiler-feedback revision rounds within 40K total (128K/5 rounds in the extended setting). **Model averaging** of base and fine-tuned weights after SFT and after RL to restore output diversity.
- **Results:** miniF2F 32B 88.1% pass@32 standard, 90.4% self-correction; 92.2% pass@8192 standard; 92.7% pass@32 with 128K context and 5 revisions; 8B 84.6% pass@32 (90.2% pass@8192). PutnamBench 86 at pass@184 with self-correction; at pass@32, 43 (or 44, the paper is inconsistent) standard vs 57 with self-correction; DeepSeek-Prover-V2-671B 47 at pass@1024, 22 at pass@32. Ablations: removing concrete compiler error text hurts most; dropping earlier CoT hurts slightly. `extract_goal`-based proof repair adds 1–2 points to the amortised budget curve.
- https://arxiv.org/abs/2508.03613 ; https://github.com/Goedel-LM/Goedel-Prover-V2

### 3.7 Seed-Prover 1.0 (ByteDance Seed; Jul 2025)
- Lean 4; "lemma-style whole-proof reasoning model" trained with RL that refines proofs using Lean feedback, proved lemmas and self-summarisation. Each difficult problem gets a *lemma pool* (statements, proofs, dependency relations) for retrieval; a *proposer* generates 10–50 candidate conjectures per call.
- **Three test-time tiers:** *Light*: refine each attempt 8–16 times at Pass@8–16, "equivalent to ... Pass@64–256", 1–2 hours; proves IMO 2022 P2 where no-refinement needs Pass@8192. Two behaviours observed: fixing Lean syntax from compiler feedback, and rewriting the sketch (which "might entirely alter the reasoning trajectory"). *Medium*: outer refinement of the main proof plus inner light (8x8) refinement of lemmas the outer loop generated but failed to prove; progress on any lemma is fed back; proofs may exceed 1,000 lines. *Heavy*: start from a conjecture pool of ~5,000 conjectures, prove/disprove each with the light tier, move successes to the lemma pool, propose more from proved lemmas, score lemmas by proof rate (low proof rate = valuable), LLM-judged relevance and length, then hand hundreds of top lemmas to a medium run; takes "days".
- **Results:** IMO 2025 4/6 during the contest (P5 medium; P1, P3, P4 heavy; P1 finished after the deadline), 5/6 with P2 by Seed-Geometry (2 s); past IMO 78.1% (155 problems; 47/55 easy, 47/56 medium); miniF2F-valid 100.0% and test 99.6% (medium, heavy for the last problem); PutnamBench 201/657 light -> 331/657 medium (leaderboard lists 329); CombiBench 30%; MiniCTX-v2 81.8% light. Seed-Geometry 43/50 on IMO-AG-50 vs AlphaGeometry 2 at 42.
- **Lessons:** iterative refinement beats Pass@k at equal sample budget; breadth (conjecture pool) is needed for the hardest problems where depth alone fails.
- https://arxiv.org/abs/2507.23726 ; https://github.com/ByteDance-Seed/Seed-Prover

### 3.8 Seed-Prover 1.5 (ByteDance Seed; Dec 2025)
- Lean 4; **agentic RL** (VAPO with tool-integrated rollouts, ReTool-style; reward +1/-1 on Lean verification) over tools: Lean REPL, embedding Mathlib search pinned to a commit, Python execution. The agent proves **one lemma at a time**, caching verified lemmas in context, "balancing step-level and whole-proof approaches". Training accuracy rose ~50% -> ~90% over ~1,200 steps while tool calls fell 15 -> 10 and sequence length 28K -> 17K tokens.
- **Test-time-scaling workflow:** (1) a natural-language prover (from Doubao-Seed-1.6) writes a lemma-style informal proof; (2) a **sketch model** converts it to a Lean sketch where auxiliary lemmas are admitted with `sorry`; it is trained with rubric RL (reward +1 only if >=3 lemmas, passes Lean, and >=0.7 on an NL rubric), with lemmas sanity-checked by the NL prover because that is "cheaper than formal disproof"; (3) the agentic prover attacks each lemma at Pass@3x3; unproved lemmas are decomposed recursively, disproved lemmas trigger a sketch revision; max depth 4, then restart at depth 8 keeping proved lemmas; for IMO/Putnam 2025 depth was capped at 4 and parallel width increased.
- **Compute:** PutnamBench run at 10 H20-days/problem (Seed-Prover 1.0 medium = 18 H20-days/problem); IMO 2025 ~20 H20-days/problem; Putnam 2025 max 40 H20-days/problem; agentic-only Pass@8x8 ~0.4 GPU-days/problem (blog). Most problems fall in the first few hours with a tail to ~53 h.
- **Results:** PutnamBench 580/660 (87.9%) (leaderboard 581/672); agentic prover alone Pass@8x8 359/660 vs Goedel-Prover-V2-32B pass@64 86/660 and Seed 1.0 medium 331; Fate-H 80%, Fate-X 33%, CombiBench 48%; IMO 2025 5/6 with times P1 16.5 h, P2 0.01 h (geometry), P3 5 h, P4 8 h, P5 1 h, P6 unsolved; Putnam 2025 11/12 within 9 h (A5 unsolved; no `native_decide`); 15 Erdős problems, "many ... relatively simple or ... trivialized by mis-formalization" per the authors. Solve count on PutnamBench grows **log-linearly** with compute (width and depth).
- **Lessons:** outcome reward from Lean suffices for stable large-scale agentic RL and improves tool efficiency; lemma-level interaction is the right unit; formalisation errors inflate some benchmarks; PhD-level (Fate-X) remains weak.
- https://arxiv.org/abs/2512.17260 ; https://seed.bytedance.com/en/blog/seed-prover-1-5-advanced-mathematical-reasoning-through-a-novel-agentic-architecture

### 3.9 Leanstral 1.5 (Mistral; 2026-07-02)
- Lean 4; 119B total / 6B active, Apache-2.0; mid-training, SFT, RL (CISPO) in two environments: multiturn prove/disprove with compiler feedback, and a *code agent* with filesystem, bash and the Lean language server across context compactions (proofs checked by a SafeVerify fork). miniF2F 100% valid and test; PutnamBench 587/672 at Pass@8 with 4M tokens per attempt (44 at 50K, 244 at 200K, 493 at 1M tokens), ~$4/problem; FATE-H 87, FATE-X 34; a "Mistral Prover" manager-worker scaffold with DeepSeek V4 Pro reached 658/672 but with ground-truth informal proofs as context. **Lesson:** smooth test-time scaling in tokens per attempt up to 4M.
- https://mistral.ai/news/leanstral-1-5/

### 3.10 OProver (May 2026)
- Lean 4; folds agentic repair (retrieval of verified proofs + compiler feedback) into training: each iteration indexes new proofs into the OProofs dataset (1.77M statements, 6.86M proofs) and retrieval memory, SFT on repair trajectories, RL on unresolved cases. OProver-32B pass@32: miniF2F 93.3%, ProverBench 58.2%, PutnamBench 11.3%, ProofNet 33.2%, MathOlympiadBench 22.8%.
- https://arxiv.org/abs/2605.17283

---

## 4. Agentic and inference-only pipelines (Lean)

### 4.1 APOLLO (Ospanov, Farnia, Yousefzadeh; May 2025, NeurIPS 2025)
- Model-agnostic repair pipeline: fix syntax, use Lean to locate errors, **isolate failing sub-lemmas**, call automated solvers, query the LLM per remaining goal with a low top-K, recombine and re-verify. Goedel-Prover-SFT: 65.6% miniF2F with sample complexity cut from 25,600 to a few hundred; 75.0% among 7B models with <1,000 samples; o3-mini/o4-mini from 3–7% to >40%.
- https://arxiv.org/abs/2505.05758

### 4.2 Delta-Prover (Zhou et al., Jul 2025)
- Gemini 2.5 Pro (05-06), no fine-tuning; **reflective decomposition** (informal plan -> formal sketch in a DSL built on `TacticM`: `suppose`, `define`, `ShowBy` with proof placeholders, `conclude`) plus **iterative repair** (failed proof + kernel error + tactic state + retrieved Mathlib names). Unsolved subproblems are passed back so the model re-decomposes.
- **Results:** miniF2F-test 95.9% at a budget of 16,384 API calls (max over solved problems); Best-of-N with the same model and budget 49.1%; 85% on the IMO subset; IMO 2019 P1 failed at 1,024 direct calls but was solved via 83 subproblems in ~332 calls. In a fixed 1,024-call ablation, more repairs per round beat more independent rounds, and the gap over Best-of-N widens with budget.
- **Failure modes:** Lean 3 syntax, wrong Mathlib names, misjudged subproblem difficulty leading to bad decompositions.
- https://arxiv.org/abs/2507.15225

### 4.3 Prover Agent (Baba et al., Jun 2025, v5 Feb 2026)
- Informal reasoning LLM + small formal prover + Lean feedback; generates *auxiliary lemmas* (subgoals, special cases, consequences of hypotheses) to discover a strategy. miniF2F 88.1%, PutnamBench 25, with "smaller sample budget" than prior work (figures not in abstract).
- https://arxiv.org/abs/2506.19923

### 4.4 Hilbert (Apple; Sep 2025, v2 Mar 2026)
- Four components: informal reasoner (Gemini 2.5 Pro/Flash; gpt-oss-120b tested), prover (Goedel-Prover-V2-32B or DeepSeek-Prover-V2-7B), verifier (Kimina Lean Server, Lean/Mathlib v4.15), retriever (all-mpnet-base-v2 + FAISS over informal Mathlib descriptions, top-5, up to 5 queries).
- **Recursive algorithm:** 4 direct prover attempts -> reasoner writes an informal proof and a Lean sketch with subgoals as `have ... := by sorry` (up to 4 sketch attempts with verifier-guided fixes) -> each `have` becomes a standalone `sorry` theorem, syntax-checked -> assemble and verify -> per subgoal: 4 prover attempts, reasoner correctness check (wrong subgoals trigger resketching), "shallow solve" by the reasoner (<=30 lines, up to 6 correction and 6 informal passes), then recursive decomposition; depth limit D=5; restart on leftover subgoals.
- **Results:** miniF2F 99.2% (Gemini 2.5 Pro + Goedel); at most ~4.5K reasoner and 11.3K total calls per sample, hardest problems ~22.8M tokens; averages on decomposed problems 548 reasoner / 391 prover calls. PutnamBench 462/660 (70.0%) vs Seed-Prover 50.4%; leaderboard: average 1,840 LLM calls per problem, median 620, max 60,893. Ablations: D=0 75% -> D=2 98.36% -> D=3 98.7%; removing retrieval 99.2 -> 97.9 and raises reasoner calls 548 -> 862; "the choice of informal reasoner appears more critical than prover strength".
- https://arxiv.org/abs/2509.22819 ; https://github.com/apple/ml-hilbert

### 4.5 Aristotle (Harmonic; Oct 2025)
- Three subsystems: (1) **Lean proof search**: ingests a Lean sketch and "attempts to replace all sorry statements" via a highly parallel **Monte Carlo Graph Search** with a >200B transformer as policy and value (same model, different task token), progressive widening, state equivalence (motivated by non-deterministic tactics such as `aesop`), hindsight replay of non-root proofs; (2) **lemma-based informal reasoning**: informal proof -> restructure as a lemma sequence -> autoformalise lemma statements -> error-correct -> search; iterate keeping proved lemmas and asking for new ones; (3) geometry via **Yuclid**, a C++ DD/AR engine "up to 500x faster than AlphaGeometry-1", open-sourced. Test-time training retrains the model on its own search traces between attempts, which "allow[ed] cross-pollination between lemmas from different proof sketches".
- **Results:** IMO 2025 5/6, P6 unsolved; problem statements hand-formalised, all lemma statements autoformalised; answers for "find all" problems generated by an LLM with programming tools. Scaling levers named: >200B model, "many parallel instances of the lemma-based reasoning pipeline", and iterating the feedback loop. The report contains **no miniF2F or PutnamBench table**. Follow-ups: Erdős #728 Lean proof (Jan 2026, arXiv 2601.07421), lemmas contributed to PFR and quantum Stein projects. LEAP (2026) reports an unnamed "gold-medal-caliber IMO system" at 48% on Lean-IMO-Bench, which a secondary source identifies as Aristotle **[unverified]**. The Aristotle API accepts Lean files with `sorry` placeholders **[secondary]**.
- https://arxiv.org/abs/2510.01346 ; https://arxiv.org/abs/2601.07421

### 4.6 Gauss (Math Inc; announced 2025-09-11)
- Autoformalisation agent interleaving natural-language and formal reasoning with literature search, tools and the Lean compiler **[IEEE Spectrum description]**. Completed Tao-Kontorovich's strong PNT challenge in ~3 weeks: ~25,000 Lean lines, >1,000 theorems/definitions, with human natural-language scaffolding and expert review of key lemmas; infrastructure "Trinity" (Morph Labs) with thousands of concurrent agents each owning a Lean runtime. Later reported: 24-dimensional sphere packing at ~120,000 lines **[Scientific American, secondary]**, Erdős #1196 **[secondary]**. No benchmark numbers.
- https://www.math.inc/gauss ; https://github.com/math-inc/strongpnt

### 4.7 2026 agentic systems
- **Numina-Lean-Agent (Jan 2026):** Claude Opus 4.5 inside Claude Code with Numina-Lean-MCP (Lean interaction, retrieval, informal proving tools); Putnam 2025 12/12; co-formalised Brascamp-Lieb. Lesson: a general coding agent plus MCP tools, upgradeable by swapping the base model, is a viable prover. https://arxiv.org/abs/2601.14027
- **A Minimal Agent for Automated Theorem Proving (Feb 2026, ICML 2026):** iterative refinement + library search + context management; "iterative refinement outperforms multiple single-shot generations in sample efficiency and cost". https://arxiv.org/abs/2602.24273
- **MechMath (Mar 2026, COLM 2026):** a *sorrifier* decomposes a failed Lean proof: keep the verified surrounding structure, extract each failed subgoal into a self-contained `sorry` context and solve it independently, avoiding both context bloat from repeated repair and full regeneration; evaluated on IMO 2025, Putnam 2025, miniF2F, ProverBench subset (abstract gives efficiency claims only). https://arxiv.org/abs/2603.24465
- **Discover and Prove (Apr 2026, ACL 2026):** "hard mode" where the answer is not in the statement; LLMs exceed 80% answer accuracy where provers are <10%; CombiBench 7 -> 10, PutnamBench hard mode 36. https://arxiv.org/abs/2604.15839
- **MerLean-Prover (May 2026):** Planning/Check/Lean agents in a recursive loop whose "unit of revision is the proof plan itself"; FormalQualBench 10/23 (OpenGauss 8/23); Putnam 2025 12/12 with lower wall-clock. https://arxiv.org/abs/2605.26959
- **LEAP (Google; Jun 2026):** decomposition linked to informal blueprints with continuous Lean interaction; Putnam 2025 12/12; Lean-IMO-Bench one-shot solve rate for general LLMs from <10% to 70% (vs 48% for an unnamed specialised gold system). https://arxiv.org/abs/2606.03303
- **Goedel-Architect (Princeton; Jun 2026):** generate a **blueprint** (dependency DAG of formally stated definitions and lemmas, optionally seeded by an NL proof); a tool-equipped Lean prover closes open lemmas **in parallel**; failures refine the global blueprint rather than recursing on the failing lemma, which the authors say "can inefficiently loop on dead-end strategies". Backbone DeepSeek-V4-Flash (284B/13B active). miniF2F-test 99.2% pass@1 (100% seeded); PutnamBench 75.6% / 88.8% (597/672) seeded; IMO 2025 4/6; Putnam 2025 11/12; USAMO 2026 3/6; "up to 500x" cheaper than comparable open pipelines. Leaderboard: 597 at pass@4, avg $1.47/problem (2026-06-06); 642 at avg $5.8 with Gemini 3.1 Pro + DeepSeek V4 Pro, 8 skeleton samples, 4 node retries (2026-07-02). https://arxiv.org/abs/2606.06468
- **Goedel-Code-Prover (Mar 2026, COLM):** hierarchical decomposition for Lean code verification, with a *decomposition score* used both as RL reward and inference ranking; 8B model 62.0% on 427 tasks; success rises monotonically with search iterations while whole-proof baselines plateau. https://arxiv.org/abs/2603.19329
- **ProofEvolve (Aug 2026):** evolves AND-OR proof DAGs in a behaviourally indexed archive within a problem and a persistent kernel-checked schema library across problems; claims best average on three Lean competition benchmarks (not named in the abstract). https://arxiv.org/abs/2608.26334
- **Aleph (Logical Intelligence):** orchestration layer (plan / prove / refine, recursive, highly parallel Lean calls) over GPT-5.2. PutnamBench leaderboard: 500/672 pass@1 avg $23 (avg 1,834 tool calls, max $103) on 2025-12-23; 637 pass@2 avg $54 on 2025-12-26; 668 pass@3 avg $68 (max $1,012, avg 6,569 tool calls) on 2026-01-11; 672 avg $74 (max $1,468) on 2026-08-26. Produced counterexamples for ~15 flawed formalisations. https://logicalintelligence.com/blog/aleph-solves-putnambench
- **AxiomProver (Axiom Math):** "autonomous multi-agent ensemble theorem prover for Lean 4"; IMO 2026 (Shanghai, 15–16 Jul 2026) 42/42 **[self-reported, no official IMO grading]**; Mathlib v4.31.0; per problem (solution lines / minutes): Q1 521/24, Q2 1224/360, Q3 4229/869, Q4 520/39, Q5 457/65, Q6 771/139, roughly 25 h and 7,700 lines total; the README says the `problem.lean` statements were "autonomously generated by AxiomProver". Earlier: Erdős #124 and #481 (Dec 2025); Putnam 2025 reported as 9/12 by MIT Technology Review but "perfect" by Fortune **[conflicting secondary]**. No technical report found. https://github.com/AxiomMath/IMO2026
- **Humanfia / Humanize (Oct 2026):** builder/reviewer agent loops with 72 mechanical gates ("judgement engineering"); PutnamBench 672/672 with GPT-5.6 Sol at xhigh reasoning, avg $44.5/problem (leaderboard 2026-08-27; an earlier 670/672 run took ~5 h); IMO 2026 6/6 in Lean 4.31 with GPT-5.6 Sol and Kimi-K3 configurations **[self-reported, not IMO-graded]**. https://arxiv.org/abs/2610.08900 ; https://github.com/humanfia/hoa-qed
- **Magenta (Sep 2026):** training-free pipeline from NL problem to answer, Lean statement and proof with a *statement judge* (does the formalisation preserve the problem?) and an *error-attribution judge* routing failures to mathematical re-derivation or local Lean repair; claims 100% on AIME 2025/2026 and HMMT Feb 2026 and all six IMO 2026 problems with the open-weight K2-Horizon-7B reasoner **[abstract only; unverified]**; lessons: "statement adjudication is essential for preventing false certificates", feedback-guided correction beats independent resampling on hard problems. https://arxiv.org/abs/2609.11319
- **NEAR AI putnambench-deepseek (Aug 2026; the upstream of this repo):** DeepSeek V4 Flash (pass 1: 639 solved; pass 2: +22) and V4 Pro for the tail (final attribution Flash 653 / Pro 19); a Lean file with one `sorry` and a single bash tool (`lake env lean`); plain call-LLM/execute-tools loop with **no other orchestration**; `completed()` verifier (no `sorry`/`axiom`/`native_decide`, frozen statement, `#print axioms`, `pp.all` type match) and human-reviewed `disproved()`; **nudging when the model emits a turn without tool calls** is called "the most important design choice" (some problems saw thousands of refused stop attempts; `putnam_2022_b6` solved at step 5,105 after 3,423); context compaction at 80%. 672/672 including corrected variants of two defective statements (`putnam_1974_b1`, `putnam_2013_a5`); 724 attempts; total ~$112 at submission prices (mean $0.17, median $0.04, max $11.18; 99.8% prefix-cache hits); longest run ~78 h (`putnam_2021_a6`); default per-problem timeout 3 days. No skeleton or hammer. https://github.com/SkidanovAlex/putnambench-deepseek
- **Midas Prover (2026-09-12):** PutnamBench no-answer mode 672/672 (346 answer-placeholder + 326 proof-only); avg $6.17 and 31 min per problem (median $3.94 / 20 min; longest 11 h 30 m); architecture undisclosed **[self-reported]**. https://mi.inc/blog/midas-prover-solves-putnambench
- **Forall (Astrio; 2026-09-24):** 672/672 with Claude Opus 5 xhigh, mean actor-side $3.52/problem, 662 accepted in round 1, harness not public **[self-reported]**.
- **Ax-Prover / AxProverBase (Axiomatic AI):** 91 problems at pass@1 with ~100 tool calls and a $4,000 budget (Dec 2025); 365 with Claude Opus 4.5 capped at 50 tool calls and 32K context, avg $12.60 (Apr 2026). **GPT-5 ReAct, 10 turns:** 28.

### 4.8 Benchmarks and meta-studies on `sorry`
- **SorryDB (Mar 2026):** dynamically updated benchmark of open `sorry`s from 78 real Lean projects (1,000-task snapshot). An agentic Gemini-Flash approach did best but "not strictly better" than other LLMs, specialised provers or a curated tactic list; "current approaches are complementary". https://arxiv.org/abs/2603.02668
- **"Sorries Are Not the Hard Part" (Jun 2026):** a zero-`sorry` formalisation of Grothendieck's vanishing theorem failed expert review on definitions, generality, organisation and API; agents respond well to mechanically checkable feedback but poorly to design judgement. https://arxiv.org/abs/2606.13925
- **PutnamBench leaderboard state (Nov 2026, from `docs/results.json`):** Lean with answer: 672/672 reached by Aleph, Humanfia, NEAR AI (DeepSeek V4), Forall; 658 Mistral Prover; 642 Goedel-Architect; 588 Leanstral 1.5; 581 Seed-Prover 1.5; 462 Hilbert; 365 AxProverBase; 329 Seed-Prover; 110 C2C-Goedel; 91 Ax-Prover; 86 Goedel-Prover-V2; 47 DeepSeek-Prover-V2. Lean no-answer: Midas 672; Enumerate-Conjecture-Prove 17; TIR Conjecturor 15. Isabelle: Varto 640/640; DSP(GPT-4o) 4; Sledgehammer 3; GPT-4o 1. Rocq: Fable 5.1 Max 8; CoqHammer 0. https://trishullab.github.io/PutnamBench/leaderboard.html
- **IMO 2026 context:** officially graded 42/42 (natural language) by Huawei Celia and Xiaohongshu dots-note-3.0; NVIDIA Nemotron 3 Ultra 30/42 in natural language (gold cutoff 29; arXiv 2609.10712); self-administered 42/42 claims for Claude Fable 5 (~$51, 2.5 h), GPT-5.6 Sol and Kimi K3 graded by Claude-based agents; formal (Lean) claims only from AxiomProver, Humanfia and Magenta, none IMO-graded. No IMO 2026 announcement from ByteDance Seed-Prover or Harmonic Aristotle was found, and no "Seed-Prover 2" or "Goedel-Prover V3" exists under those names as of 2026-11-10.

---

## 5. Hammer and automation evidence (Isabelle and Lean)

- **Sledgehammer: Judgement Day (Böhme & Nipkow, IJCAR 2010):** on 1,240 goals from seven theories, Sledgehammer proves ~45% of goals (per-theory 20–60%; ~34% of non-trivial goals); running E, SPASS and Vampire together for 5 s equals the best single prover at 120 s (44%), which is why Sledgehammer runs ATPs concurrently; going from 120 s to 240 s adds only 0.4%. **Metis reconstruction loses up to 10% of sound ATP proofs** (30% in one theory), "mainly because Metis times out"; the other causes are type-unsound translation and Metis's own two-stage limits. Fact minimisation cuts the fact set by a third and rescues ~20% of failed Metis proofs. https://www.proof.cit.tum.de/~nipkow/pubs/ijcar10.pdf
- **Hammering towards QED (Blanchette, Kaliszyk, Paulson, Urban, JFR 2016):** with the modern mix of `metis`, `smt` and other one-line methods, reconstruction success exceeds 99% in a recent evaluation; four ATPs together reached ~70% on an Isabelle benchmark; SMT backends (Z3) were the strongest single provers. https://wwwbroy.in.tum.de/~blanchet/h4qed.pdf
- **Sledgehammer in LLM loops (Isabelle):** DSP: 10.4% alone, 20.9% with 10-s heuristic tactics first, 120-s timeout; Thor: 30-s timeout, 25.7% of PISA alone, but 8.2% of PISA solvable only by interleaving with the LM; Lyra: mechanically replacing hallucinated tool calls by sledgehammer-style automation is the larger of its two gains; Munkres 2026: ~10 s per `sorry`, run in parallel inside the build, split on failure; HybridProver v1: 300 CPU-hours for 244 theorems at 32 samples illustrates the CPU cost.
- **Lean automation:** no general hammer until **LeanHammer** (Zhu, Clune, Avigad, Jiang, Welleck; 2025, ICLR 2026): LeanPremise + Lean-auto + Duper + Aesop, "21% more goals" than prior premise selectors on Mathlib. Lean provers instead lean on `nlinarith`, `omega`, `simp`, `aesop`, `decide`, with known gaming risks: DeepSeek-Prover-V2's 7B exploited an `apply?` bug; Seed-Prover 1.5 and the NEAR AI harness forbid `native_decide`; Aristotle's search treats `aesop`-style non-determinism explicitly.
- **Divergent reconstruction:** no paper quantifies "metis transplant" failures (a sledgehammer-found `by (metis ...)` reused on a different goal) in LLM loops. The closest base rates are Judgement Day's up-to-10% Metis reconstruction loss (mostly timeouts) and the 2016 >99% figure when the full method set and minimisation are used. This is a genuine gap the nearAI_Isabelle logs could fill.

---

## 6. Synthesis

### (1) What separates systems that solve hard problems from those that saturate miniF2F
- miniF2F is saturated by **whole-proof RL provers plus pass@k** (Goedel-Prover-V2 92.2% at pass@8192; Kimina-72B 92.2% with TTRL search; Seed-Prover 99.6%; Leanstral 100%). The same models collapse on PutnamBench at matched budgets: Goedel-Prover-V2-32B 86/660 at pass@184 and Seed-Prover 1.5's own agentic prover 359/660 at Pass@8x8.
- Systems that reach IMO/Putnam level add four things on top of a prover: (a) a **strong informal reasoner** writing the plan (Hilbert: reasoner choice matters more than prover strength; Goedel-Architect: an NL seed proof lifts PutnamBench 75.6 -> 88.8%; Aristotle and Seed 1.5 both front an NL prover); (b) **decomposition into verified, reusable lemmas** with a cache or pool (Seed-Prover heavy, Kimina lemma pool, Aristotle lemma pipeline, Hilbert `have`/`sorry` recursion, Goedel-Architect blueprint); (c) **long horizons**, hours to days, with iterative repair rather than independent resampling (Delta-Prover 95.9% vs 49.1% Best-of-N at the same 16,384 calls; Seed light tier proves IMO 2022 P2 where Pass@8192 was needed without refinement; AlphaProof TTRL +15 points over a 12-TPU-hour search); (d) **test-time learning** (AlphaProof TTRL, Aristotle TTT, Seed 1.5 experience accumulation) for the hardest cases.
- Two further separators: **answer discovery** (Discover and Prove: LLMs >80% vs provers <10%; AlphaProof and Aristotle generate candidate answers with an LLM and refute wrong ones), and **statement faithfulness** (Aleph found ~15 flawed PutnamBench formalisations; NEAR AI two; Magenta's statement judge; Seed 1.5 says some CombiBench/Erdős results were "trivialized by mis-formalization"). Combinatorics remains the weakest domain for every RL prover (AlphaProof 20.3% even with 500 TPU-days).

### (2) Decomposition with `sorry` placeholders and automatic filling
- The pattern is older than Lean provers: DSP (2022) proved its value in Isabelle (+9–10 points from leaving conjectures open vs forcing the LM to write complete proofs), and POETRY (2024) made it recursive with explicit `sorry`. Every 2025–26 hard-problem system contains the same move: DeepSeek-Prover-V2's `have ... := sorry` cold start, Hilbert's `have`-to-theorem extraction, Seed-Prover 1.5's sketch model (rewarded only for sketches with >=3 lemmas that pass Lean), Aristotle's "replace all sorry statements", MechMath's sorrifier, Goedel-Architect's blueprint, the Munkres sorry-first project.
- Reported benefits: large budget reductions when the sketch is right (Delta-Prover IMO 2019 P1: 83 subproblems in ~332 calls after 1,024 direct calls failed; Hilbert D=0 75% -> D=2 98.4%); proofs beyond flat search depth (POETRY 10 -> 26 steps; Seed medium >1,000 lines); parallel filling (Goedel-Architect, Munkres).
- Reported failure modes: **false intermediate conjectures** (POETRY fails the sub-search and resketches; Kimina proves the negation to filter; Seed 1.5 has a disprove path and NL sanity checks; Hilbert's reasoner checks subgoal truth before spending prover calls); **dead-end recursion loops** (Goedel-Architect's critique of recursive lemma decomposition, hence global blueprint refinement); **misjudged subgoal difficulty** producing un-fillable gaps (Delta-Prover; DSP's "human proofs leave gaps too difficult for automated provers"); sketches that drop hypotheses or weaken definitions (Munkres); and cost: Hilbert's hardest problems used ~22.8M tokens and up to 60,893 calls. Most of Hilbert's gain comes at depth <=3 and Seed 1.5 capped depth at 4 for contests, so shallow, wide decomposition is the empirically favoured regime.
- Two design details recur: keep proved lemmas in context across restarts (Seed 1.5, Aristotle, LEGO-Prover), and reward or require the final proof to actually use the decomposed lemmas (DeepSeek-Prover-V2's consistency reward; Seed 1.5's >=3-lemma rubric), which bears directly on the metis-transplant question in this project.

### (3) Hammers inside LLM loops
- **When they help:** closing small, well-specified gaps in a declarative sketch (DSP, Munkres) and premise selection the LM cannot do (Thor, Magnushammer). Interleaving beats union: Thor 57.0% vs 48.8% for LM-union-Sledgehammer on PISA; 8.2% of problems need both.
- **Timeouts:** the literature uses 10 s (Munkres, per-`sorry`, parallel), 30 s (Thor default) and 120 s (DSP, PutnamBench baseline). Judgement Day shows 5 s with three ATPs in parallel equals 120 s with one, and 240 s adds 0.4%; DSP's heuristic tactics at 10 s before sledgehammer doubled the hammer baseline (10.4 -> 20.9%). CPU cost is the practical limit (HybridProver: 300 CPU-hours per 244 theorems x 32 samples).
- **Failure modes:** Metis reconstruction loss up to 10% (timeouts, type-unsound encodings), reduced by minimisation and by using the full method set (`smt`, `meson`, `blast`); hallucinated or misapplied tool calls (Lyra's Tool Correction); automation exploited by RL (`apply?` bug, `native_decide` bans); in Lean, no mature hammer until LeanHammer, so Lean agents substitute retrieval of Mathlib names (Delta-Prover, Hilbert) for premise selection. Divergent reconstruction when a found `metis` call is transplanted to another goal is unmeasured in the literature.

### (4) Compute and parallelism per hard problem
- IMO-level: AlphaProof 2–3 days of TTRL per 2024 problem, ~500 TPU-days/problem at the top budget; Seed-Prover 1.0 heavy "days", medium 18 H20-days/problem; Seed-Prover 1.5 ~20 H20-days/problem on IMO 2025 (P1 16.5 h, P3 5 h, P4 8 h), 10 H20-days on PutnamBench, 40 max on Putnam 2025, tail to ~53 h; Aristotle >200B model with many parallel pipeline instances; AxiomProver 24–869 min per IMO 2026 problem (~25 h total) **[self-reported]**.
- Putnam-level, agentic frontier models: Hilbert avg 1,840 LLM calls (max 60,893); Aleph avg $68–74 and ~6,569 tool calls per problem with maxima above $1,000; Humanfia avg $44.5; Goedel-Architect $1.47–5.8; Leanstral 8 x 4M tokens; NEAR AI mean $0.17 but a 78 h maximum with a 3-day timeout; Midas avg 31 min; Varto (Isabelle) avg 16 min and $8. Costs fell roughly two orders of magnitude between Dec 2025 and Sep 2026 at equal solve counts.
- Scaling shape: log-linear in compute (Seed 1.5; BFS-Prover "logarithmic"; Kimina "diminishing beyond pass@1024"; InternLM: flat search becomes brute force), so the systems that keep improving change the *shape* of search (refinement, decomposition, TTRL) rather than k.
- Parallelism patterns: lemma-level fan-out (Goedel-Architect parallel lemma proving; Seed 1.5 widens parallel width and caps depth; Kimina sublemma generation in parallel; Munkres parallel sledgehammer in one build); pipeline-level fan-out (Aristotle's many sketch instances, Gauss's thousands of agents each with a Lean runtime); verifier throughput as a first-class engineering target (Kimina Lean Server 1.5–2x; Harmonic's REPL that initialises from a file with `sorry`s and returns a goal per `sorry`, hosted on GKE).

### (5) Isabelle-specific vs Lean-specific findings
- 2022–2024 the Isabelle line led on miniF2F (DSP 39.3 -> LEGO/Lyra ~51 -> SubgoalXL 56.1 -> ProofAug 66.0 -> HybridProver 73.8) precisely because Isar sketches plus Sledgehammer make sketch-and-fill natural, and because Sledgehammer is a mature general hammer. Lean overtook it from 2024 through RL provers (Mathlib scale, fast REPLs, Lean Workbook data) and now holds every IMO/Putnam-level result.
- Isabelle regained attention in 2026 through agent harnesses: Varto 640/640 on PutnamBench-Isabelle crediting "Isabelle's built-in proof tactics and the AFP", at ~8x lower cost and ~23x less time than the top Lean entry of that week; the Munkres project's sorry-first + parallel 10-s sledgehammer workflow; an Isabelle REPL with best-first search for seL4. None of these report hard-problem (IMO) results, and the Isabelle PutnamBench track has fewer problems (640) with ~130 needing formalisation fixes.
- Isabelle-specific hazards documented: Sledgehammer/Metis timeouts and reconstruction failures (Judgement Day), build-vs-session verification cost, and the absence (until Varto, undisclosed) of any Isabelle-native RL prover; Lean-specific hazards: tactic gaming (`apply?`, `native_decide`), non-deterministic tactics (`aesop`) complicating search, Mathlib name hallucination (Delta-Prover), no mature hammer until LeanHammer.
- For this experiment: arm (B) is the Isabelle-native version of what every top 2025–26 system does in Lean; the literature predicts it wins when sketches are shallow (depth <=3–4), lemmas are verified and cached across attempts, false conjectures are detected early (disproof or NL check), and sledgehammer per `sorry` runs with a short timeout in parallel with heuristic tactics first. Arm (A) resembles Thor/Lyra and should win on short problems where a sketch is overhead. The unmeasured quantity in the literature, Metis transplant divergence, is exactly what the harness's decision not to bind sledgehammer results to their goals will expose.

---

## 7. Source URLs (primary unless noted)

- Thor https://arxiv.org/abs/2205.10893 ; DSP https://arxiv.org/abs/2210.12283 ; Magnushammer https://arxiv.org/abs/2303.04488 ; Baldur https://arxiv.org/abs/2303.04910 ; Lyra https://arxiv.org/abs/2309.15806 ; LEGO-Prover https://arxiv.org/abs/2310.00656 ; POETRY https://arxiv.org/abs/2405.14414 ; SubgoalXL https://arxiv.org/abs/2408.11172 ; ProofAug https://arxiv.org/abs/2501.18310 ; HybridProver https://arxiv.org/abs/2505.15740 ; Munkres/Isabelle https://arxiv.org/abs/2604.07455 ; seL4 Isabelle REPL https://arxiv.org/abs/2603.19715 ; Isabellm https://arxiv.org/abs/2601.04653 ; IsabeLLM https://arxiv.org/abs/2606.18098 ; Varto https://varto.com/blog/putnambench
- Lean-STaR https://arxiv.org/abs/2407.10040 ; InternLM2.5-StepProver https://arxiv.org/abs/2410.15700 ; HunyuanProver https://arxiv.org/abs/2412.20735 ; BFS-Prover https://arxiv.org/abs/2502.03438 ; AlphaProof https://www.nature.com/articles/s41586-025-09833-y (SI PDF above)
- DeepSeek-Prover-V1.5 https://arxiv.org/abs/2408.08152 ; Goedel-Prover https://arxiv.org/abs/2502.07640 ; Leanabell https://arxiv.org/abs/2504.06122 ; Kimina-Prover https://arxiv.org/abs/2504.11354 , https://huggingface.co/blog/AI-MO/kimina-prover , Kimina Lean Server https://arxiv.org/abs/2504.21230 ; DeepSeek-Prover-V2 https://arxiv.org/abs/2504.21801 ; Goedel-Prover-V2 https://arxiv.org/abs/2508.03613 ; Seed-Prover https://arxiv.org/abs/2507.23726 ; Seed-Prover 1.5 https://arxiv.org/abs/2512.17260 ; Leanstral 1.5 https://mistral.ai/news/leanstral-1-5/ ; OProver https://arxiv.org/abs/2605.17283
- APOLLO https://arxiv.org/abs/2505.05758 ; Delta-Prover https://arxiv.org/abs/2507.15225 ; Prover Agent https://arxiv.org/abs/2506.19923 ; Hilbert https://arxiv.org/abs/2509.22819 ; Aristotle https://arxiv.org/abs/2510.01346 ; Gauss https://www.math.inc/gauss ; Numina-Lean-Agent https://arxiv.org/abs/2601.14027 ; Minimal Agent https://arxiv.org/abs/2602.24273 ; MechMath https://arxiv.org/abs/2603.24465 ; Discover and Prove https://arxiv.org/abs/2604.15839 ; MerLean https://arxiv.org/abs/2605.26959 ; LEAP https://arxiv.org/abs/2606.03303 ; Goedel-Architect https://arxiv.org/abs/2606.06468 ; Goedel-Code-Prover https://arxiv.org/abs/2603.19329 ; ProofEvolve https://arxiv.org/abs/2608.26334 ; Aleph https://logicalintelligence.com/blog/aleph-solves-putnambench ; AxiomProver https://github.com/AxiomMath/IMO2026 ; Humanize https://arxiv.org/abs/2610.08900 , https://github.com/humanfia/hoa-qed ; Magenta https://arxiv.org/abs/2609.11319 ; NEAR AI https://github.com/SkidanovAlex/putnambench-deepseek ; Midas https://mi.inc/blog/midas-prover-solves-putnambench ; Nemotron IMO https://arxiv.org/abs/2609.10712
- SorryDB https://arxiv.org/abs/2603.02668 ; Sorries Are Not the Hard Part https://arxiv.org/abs/2606.13925 ; PutnamBench leaderboard https://trishullab.github.io/PutnamBench/leaderboard.html (data: https://raw.githubusercontent.com/trishullab/PutnamBench/main/docs/results.json) ; LeanHammer https://arxiv.org/abs/2506.07477 ; Judgement Day https://www.proof.cit.tum.de/~nipkow/pubs/ijcar10.pdf ; Hammering towards QED https://wwwbroy.in.tum.de/~blanchet/h4qed.pdf ; IMO 2026 press summary (secondary) https://www.digitalapplied.com/blog/imo-2026-perfect-scores-ai-benchmark-saturation
