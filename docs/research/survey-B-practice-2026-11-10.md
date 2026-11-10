# B. Practice survey: how people and agents actually work with Isabelle/HOL and Lean 4

Prepared 2026-11-10 for the nearAI_Isabelle experiment (LLM agent + Isabelle Pool Server MCP;
per-goal sledgehammer vs. sorry-skeleton + server-side `fill_sorries`; IMO 2026-level targets).

Method: web search (standard + extended) and direct reads of primary sources (manuals, arXiv
HTML/abstracts, GitHub READMEs, blog posts). Every claim is tagged:

- **[P]** read in the primary source during this survey;
- **[S]** secondary source only (aggregator, HN/Zulip commenter, press) -- treat as provisional;
- **[U]** unverified: could not open the source, or the number is recalled rather than read.

Where a PDF could not be parsed (TUM hosts refused connections on 2026-11-10; several arXiv PDFs
came back as binary) I say so rather than guess.

---

## A. Isabelle automation practice

### A1. Sledgehammer: what the manual actually says (Isabelle2025, read via the GitHub mirror of `src/Doc/Sledgehammer/document/root.tex`) [P]

Defaults that matter for an agent pipeline:

| option | default | note |
|---|---|---|
| `provers` | "a subset of CVC4, E, SPASS, Vampire, veriT, Z3, Zipperposition, and proof methods", chosen by cores/installed provers | run in parallel |
| `timeout` | 30 s, *soft*, excludes problem preparation | manual's own example uses `timeout = 120` |
| `preplay_timeout` | 1 s | 0 disables preplay |
| `minimize` | true | minimisation "reduces the number of facts and helps reconstruction" |
| `isar_proofs` | smart | Isar proof generated only when no working one-liner is found |
| `compress` | smart (10 if `isar_proofs` forced, else infinity) | |
| `try0` | true | preplays with the `try0` method set too |
| `max_facts` | smart (prover-dependent, "typical values between 0 and 1000") | manual: restrict to 25-50 for long proofs |
| `slices` | 24 x cores | slicing is the unit of prover invocation |
| `max_proofs` | 4 (soft) | |
| `smt_proofs` | true | `smt` one-liners allowed |

History of the 30 s default [P, Isabelle hg changesets]: default went 60 s -> 30 s in 2010; the
commit message cites Böhme & Nipkow 2010 ("Judgement Day") as evidence that "very few proofs are
lost", partly because provers run in parallel. 2011: a soft 30 s / hard 60 s split so minimisation
can finish. Sources:
https://isabelle.in.tum.de/repos/isabelle/rev/87a9ff4d5817 ,
https://isabelle.in.tum.de/repos/isabelle/rev/07ebc2398731 .
The Judgement Day paper itself (IJCAR 2010, LNCS 6173 pp.107-121;
https://www21.in.tum.de/~boehmes/judgement.html) could not be fetched (host refused); its exact
success-vs-time curve is **[U]**.

Why a found proof fails to replay (manual FAQ "Why does Metis fail to reconstruct the proof?") [P]:
1. Metis is complete for first-order logic with equality, but E, Vampire, Zipperposition are
   higher-order provers, so Metis may be unable to re-find their proofs.
2. If Metis runs "seemingly forever", the proof is probably just too hard for it (it is a
   much weaker prover than the ATP that found the proof).
3. Rare fast failure "One-line proof reconstruction failed": goal provable but beyond Metis for
   technical reasons; remedy: retry with `strict`.
4. Type encodings: `full_types`/`mono_tags` variants are slower but more complete and are used
   as fallback; `no_types` is faster but "often fails"; some encodings "can give rise to spurious
   proofs (unreconstructible using metis)". A "Falling back on" warning means you should write
   `metis (full_types)` directly.
5. Remedies the manual lists: fewer facts (minimise; `max_facts` 25-50), simplify the goal first,
   Isar proofs ("can be faster and sometimes more intelligible").

Practical implication for the harness: the 1 s preplay means a suggested one-liner has already
been checked once *in the interactive context*; failures appear later mainly when (a) the
one-liner is transplanted to a different goal (your "metis transplant" finding), (b) `smt`
replay differs across solver versions, or (c) the build runs the proof under a different timeout
regime. The manual does not recommend a per-goal budget; the 30 s default is a UI-latency
choice justified by the 2010 study, not by hard-problem data.

Independent evidence on how Sledgehammer's success scales with compute:
- Magnushammer (ICLR 2024, arXiv 2303.04488) [P abstract, S for details]: Sledgehammer 38.3% on
  PISA vs. Magnushammer 59.5%; authors state that "increasing computational power for Sledgehammer
  brings diminishing returns quickly" (their Fig. 1). The Lean Zulip notes the comparison is
  "messy" (GPU vs. CPU budgets). https://arxiv.org/abs/2303.04488
- miniF2F-Isabelle baselines (DSP, ICLR 2023) [P]: Sledgehammer alone 9.9%/10.4%
  (valid/test); Sledgehammer + 11 heuristic tactics 18.0%/20.9%. The heuristics are run at 10 s
  each *before* a 120 s Sledgehammer call. https://arxiv.org/abs/2210.12283
- Hammering towards QED (JFR 2016, Blanchette/Kaliszyk/Paulson/Urban): PDF fetched but
  unparsable **[U]**; the DFG "Hardening the Hammer" project page reports a representative-benchmark
  success rate rising 64% -> 77% from ML fact selection, lightweight encodings and prover
  improvements [P, https://gepris.dfg.de/gepris/projekt/226154341/ergebnisse ].

### A2. `try0`, `try`, `solve_direct` (Isar reference, HOL-specific chapter, mirror) [P]
- `try0`: "attempts to prove a subgoal using a combination of standard proof methods" (`auto`,
  `simp`, `blast`, ... ); accepts `simp:`/`intro:`/`elim:`/`dest:` facts. No time limit documented
  in the manual text I read; the Sledgehammer `try0` *option* preplays suggestions with roughly
  the same method set.
- `try`: runs `solve_direct`, `quickcheck`, `try0`, `sledgehammer`, `nitpick` -- the manual lists
  them in that order but does not state scheduling or limits.
- `solve_direct`: checks whether an existing theorem closes the goal directly (also detects
  duplicate lemmas). Cheap; a natural first step before any hammer.
  https://raw.githubusercontent.com/isabelle-prover/mirror-isabelle/master/src/Doc/Isar_Ref/HOL_Specific.thy

### A3. Disproof: Nitpick and Quickcheck [P for Nitpick manual; U for current default timeout]
- Nitpick (`src/Doc/Nitpick/document/root.tex`): default `card` 1-10 per type, enumerated under
  scope monotonicity; with four type variables "no fewer than 10,000 scopes". Outcomes are
  **genuine**, **quasi genuine** (unsound option used), or **potentially spurious** (infinite
  types / outside the supported fragment: `nat`, `int` are approximated by finite subsets, giving a
  three-valued logic). "Nitpick found no counterexample" is explicitly *not* a proof. Reals and
  rationals: "rudimentary" support. Default `timeout`: 30 s in older manual revisions [S]; the
  current manual text I read gives no default in prose [U -- check `nitpick_params` output].
- Quickcheck: exhaustive by default; `random`/`narrowing` testers; `quickcheck_timeout` 30 s in the
  ML source [S, source grep]; inductive predicates can make it "loop forever" (Nitpick manual).
- Evidence of use in LLM loops: IsabeLLM (2026) reports that Nitpick counterexamples plus an error
  trace "reduced repeated failed proof loops" [P, https://arxiv.org/html/2606.18098v1 ].
- AFP policy: counterexample tools must carry `expect =` so a build is not silently green [P,
  https://www.isa-afp.org/submission/ ].

### A4. Isar structuring advice (Prog_Prove ch. 4 = Concrete Semantics part I; Isar reference) [P]
- Patterns (Sec. 4.2): case analysis via `cases`; equivalence by two `show`s; contradiction with
  `rule ccontr`; `fix` for universals, `obtain x where ... by blast` to use an existential; set
  equality by two inclusions. Link facts with `this`/`then`/`hence`/`with`; name facts only when
  reused ("labels interrupt the reader's flow"). Calculational `also`/`finally` support `=`, `<=`,
  `<` (not `>=`, `>`); the `finally` relation must be the most precise one that holds.
  `moreover`/`ultimately` collect facts without names. `(is "?L <-> ?R")`, `?thesis`, `let ?t`,
  `assms(n)` reduce repetition.
- Warnings the chapter gives: `proof` with no method applies a default intro rule -- give one
  explicitly; `auto`/`simp` "can silently rewrite assumptions and goals" -- check intermediate
  statements; `case` assumptions after `induction ... arbitrary:` may not look like what you
  wrote.
  https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/library/Doc/Prog_Prove/Isar.html
- AFP style [P]: structured Isar preferred over `apply`; do not rely on generated names (`xa`);
  attributes only on named lemmas; steps slower than ~1 minute need a comment; every session has a
  `timeout`, a multiple of 300 s; `sorry`, `sledgehammer`, `smt_oracle` banned in submissions.
  https://www.isa-afp.org/submission/
- Apply2Isar (arXiv 2603.07771, 2026) [S]: structured Isar "arguably more robust than tactic
  scripts", but proof behaviour still changes when simp rules are added/removed.
- Blanchette et al., "Semi-intelligible Isar proofs from machine-generated proofs" (JAR 2016):
  the motivation for `isar_proofs` -- one-liners were "unpalatable", and "metis ... can fail to
  re-find a proof produced by a superposition prover"; Isar output is iteratively preplayed and
  compressed. Success numbers not read [U]. https://wwwbroy.in.tum.de/~blanchet/isar2.pdf

### A5. Known pitfalls (community) [P unless marked]
- Simplifier loops: usually user-added `[simp]` rules combining with the default simpset into a
  rewrite cycle (Isabelle Zulip, Beginner Questions); `simp (no_asm)` ignores assumptions that
  cause non-termination (UNSW course notes) [S].
- `auto` leaving goals: no canonical thread found; Prog_Prove's warning above is the closest
  documented statement. Lean-side analogue (Trail of Bits skill): "never use non-terminal
  unsqueezed simp".
- Build timeouts: `timeout_scale` multiplies the session timeout (2015 NEWS; since 2021 also
  scales Isabelle/ML timeouts and Sledgehammer learning timeouts)
  https://mailman46.in.tum.de/pipermail/isabelle-dev/2015-November/006406.html . Hanging
  `metis`/`blast` are a recognised failure mode: IsabeLLM specifically re-checks "hanging tactics
  such as metis and blast that cause timeouts" with Sledgehammer [P].
- `smt` replay: AFP does not ban `smt` (only `smt_oracle`), but the Z3 version pin means replay
  can break across releases [U -- inference from AFP rules, not a cited incident].

### A6. Isabelle environments and LLM systems (for comparison with the Pool Server)
- Headless PIDE / `isabelle server` (JSON over TCP) since Isabelle2019 [S, Wenzel UITP 2018].
- PISA (Jiang et al. 2021) is the Scala interaction layer used by Thor (57.0% PISA), Baldur
  (65.7% with Thor; whole-proof + repair model reading Isabelle errors), Magnushammer+Thor (71%),
  MiniLang (69.1% pass@1, 79.2% pass@8; a 10-operation proof language that removes tactics and
  leaves gaps to Sledgehammer) [P abstracts].
  https://arxiv.org/abs/2303.04910 , https://arxiv.org/abs/2205.10893 , https://arxiv.org/abs/2507.18885
- ProofAug (2025, Isabelle 2022 via PISA, 12 instances in parallel) [P]: `<ATP>` = ~10 methods at
  10 s each + Sledgehammer at 120 s; failing steps are replaced by `sorry` (FindMCSP), automation
  tried at each `sorry`, and if that fails the enclosing `proof..qed` block is dropped and the
  coarser goal retried. https://arxiv.org/html/2501.18310
- HybridProver (2025) [P]: n=128 whole proofs; if none pass, *every tactic in each syntactically
  valid proof is replaced by `sorry`* and the sketches are checked; Sledgehammer 30 s with E,
  SPASS, Vampire, Z3, CVC4 + 11 heuristics fills; 59.4% miniF2F-Isabelle. Sketch refinement moved
  tactic-only 34.8% -> 56.1%. https://arxiv.org/html/2505.15740v1
- Lyra (2023) [S]: "Tool Correction" replaces hallucinated tactics with Sledgehammer; "Conjecture
  Correction" feeds errors back; miniF2F 45.5 -> 51.2 test. https://arxiv.org/abs/2309.15806
- IsabeLLM (2026, Scala-Isabelle) [P]: build -> extract unproven lemmas -> LLM -> rebuild ->
  Sledgehammer (60 s) on failing lines -> LLM again; max 3 iterations x 10 attempts; small eval
  (16 lemmas) 76.3% -> 94.4% with 3 retrieved similar proofs in the prompt.
- MCP servers for Isabelle: `kappelmann/isabelle-pide-ai` (Sheffield; PIDE MCP preprint on
  Zenodo, Sept 2026; headless PIDE sessions shared by several agents, file watcher, tool-call
  progress/cancellation, proof states only if the base session was built with `-o show_states`
  which "takes significantly longer"; ships `isabelle`, `isabelle-ml`, `pide-ai` agent skills) [P
  README]; `danmatichuk/isabelle-pide-mcp` [S]. https://github.com/kappelmann/isabelle-pide-ai ,
  https://zenodo.org/records/22726567
- "IsabelleGym": no such system found [searched]. PutnamBench-Isabelle: Sledgehammer alone solved
  3/640 in the original paper [S]; no Isabelle MCP agent results on PutnamBench found other than
  this repo.

---

## B. Lean 4 automation and agent tooling

### B1. Tactics and hammers
- Search/finishing tactics (core since Lean 4.7): `exact?` (single lemma closing the goal),
  `apply?` (candidate list), `simp?`/`aesop?` (print the lemmas used), `aesop`, `omega` (linear
  N/Z), `linarith`/`nlinarith`, `polyrith` (needs network; doc not re-read [U]) [P, Mathlib manual
  and v4.7.0 release notes]. https://leanprover-community.github.io/mathlib-manual/html-multi/Tactics/Automation
- LeanHammer (CMU, arXiv 2506.07477, ICLR 2026) [P HTML]: pipeline Aesop -> premise application
  (LeanPremise, priority 20%) -> Lean-auto (10%) -> Zipperposition (10 s per call) -> Duper
  reconstruction; 300 s wall-clock and default 200k heartbeats per theorem. Mathlib-test 30.1%
  (33.3% cumulative; 16.9% with no premises; 43.0% with ground-truth premises); miniCTX-v2 20.7%.
  Aesop-with-premises alone 24.1%, i.e. ATP+Duper adds ~6 points. Reconstruction failures
  (Zipperposition proves, Duper cannot rebuild) ~1.2-1.6%, "rare". No time-limit ablation.
  https://arxiv.org/html/2506.07477v2 , https://github.com/JOSHCLUNE/LeanHammer
- Canonical (Norman & Avigad, ITP 2025) [P abstract]: type-inhabitation solver, iterative-deepening
  refinement; 84% of Natural Number Game in 51 s total. https://arxiv.org/abs/2504.06239
- Lean Copilot (PMLR 2025) [S]: 2.08 manual steps vs. 3.86 with aesop when assisting humans.
  LeanDojo/ReProver (NeurIPS 2023): retrieval-augmented tactic prover; still the default Copilot
  model. https://arxiv.org/abs/2404.12534
- Mathlib `hint` (tries a bundle of finishing tactics) is what APOLLO's AutoSolver calls first [P].

### B2. Verification servers
- Kimina Lean Server (arXiv 2504.21230, NeurIPS MATH-AI 2025) [P HTML]: one persistent REPL per
  core; LRU cache keyed on the import header so only bodies re-verify (0.099 s -> 0.051 s per
  proof, 1.94x); 9,419 proofs at 64 cores in 7:56 vs LeanInteract 12:56 vs leanclient 18:01;
  near-linear 8->32 cores (3.7x). Config: `LEAN_SERVER_MAX_REPLS`, `_MAX_WAIT`, `_MAX_REPL_MEM`;
  client example `timeout=120`. Lessons stated: workers = physical cores; reuse imports; batch
  submissions. https://arxiv.org/abs/2504.21230
- Aristotle (Harmonic) [P HTML]: Lean REPL as *stateless* CPU-only GKE workers; every request
  carries the full state so any worker can apply a tactic; finished proofs re-rendered as
  self-contained files and checked for kernel errors, axioms, and used lemmas; extra well-typedness
  checks on tactic-produced terms. https://arxiv.org/html/2510.01346v1
- Gauss (Math Inc) [P page]: "thousands of concurrent agents", each with its own Lean runtime, on
  Morph Cloud "Infinibranch" snapshots; multiple TB of RAM. https://www.math.inc/gauss
- Others named by Kimina as baselines: Lean REPL, Pantograph (single-threaded), LeanDojo /
  ProofWala (gym-like, not throughput-oriented), LeanInteract, leanclient.

### B3. MCP servers and agent skills
- `lean-lsp-mcp` (Dressler; PyPI 0.30.x by 2026) [P README]: tools `lean_goal`,
  `lean_diagnostic_messages`, `lean_file_outline`, `lean_run_code` (REPL-backed), `lean_multi_attempt`
  (parallel tactic tries), `lean_local_search` (ripgrep), `lean_verify`, `lean_build`, remote
  LeanSearch/Loogle/Lean Finder/`hammer_premise`. Diagnostics/goal fields are **truncated to 6000
  chars from the middle** so local context and target both survive (`LEAN_MCP_MAX_OUTPUT_CHARS`).
  Advice: `lake build` before starting; prefer local search before remote (Loogle 3 req/30 s);
  disable risky tools via `LEAN_MCP_DISABLED_TOOLS`. Users: Ax-Prover, Numina-Lean-Agent, MerLean,
  M2F. https://github.com/oOo0oOo/lean-lsp-mcp
- `cameronfreer/lean4-skills` (Claude Code / Codex plugin) [P README]: `draft`/`formalize`,
  `prove`/`autoprove` (explicit stop budgets), `disprove`, `review`, `refactor`, `golf`,
  `checkpoint`; per-sorry loop = Mathlib search -> tactic attempts -> validate; "Blocked-Goal
  Triage" when stuck; declaration headers frozen in prove mode. No effectiveness data.
  https://github.com/cameronfreer/lean4-skills
- Trail of Bits "Writing Lean proofs" skill [P]: "design top-down, prove bottom-up"; skeleton
  with `:= sorry` that compiles, each sorry an independent unit; inside a proof lay out
  `have`/`suffices`/`calc` with sorry justifications first; one focused goal at a time with `·`
  and `show`; `trace_state`/`done` probes; terminal simp unsqueezed, non-terminal `simp only`;
  re-derive `simp only` lists with `simp?` at their own site; treat any `maxHeartbeats` raise as an
  unproven claim (`#count_heartbeats`, bisect); verify with `#print axioms`/`Lean.collectAxioms`,
  not grep for sorry; `native_decide` is a trust decision. https://trailofbits.com/skills/writing-lean-proofs/
- `scottnarmstrong/LeanAutoformalizationSkills` (Codex + Claude Code, Mathlib discovery, audits) [S].
- Rocq-MCP Putnam 2025 (Baudart et al., arXiv 2603.20405) [P abstract]: Opus 4.6 offline, MCP tools
  designed by analysing logs of a prior miniF2F-Rocq run, "compile-first, interactive-fallback";
  141 subagents; 10/12; 17.7 h active compute (51.6 h wall), ~1.9B tokens.
- Practitioner reports [S]: Thomas Kahle (2026) -- an LSP server gives Claude "a direct feedback
  loop" and is faster than CLI compile-and-read; without it the model is slower and "relies more on
  trial and error"; he moved from broad goals to a second LLM writing detailed guides.
  https://thomas-kahle.de/blog/2026/auto-formalization-1-keep-trying/ . John D. Cook (June 2026):
  first attempts fail mostly on Mathlib renames and occasional hallucinated lemmas.
- Terence Tao, "Formalizing a proof in Lean using Claude Code" (video, March 2026; HN thread) [S --
  commenter account, Tao's own words only where quoted]: whole-proof attempt ran ~45 min and
  produced nothing; decomposed into steps, done in ~25 min; third take: Tao wrote "a step-by-step
  recipe" first and fixed one step by hand while Claude skeletonised the next lemma; Tao: "it
  actually struggles a lot with the lowest level steps of the proof" and "you do need to keep
  [checking]". https://news.ycombinator.com/item?id=47306852

### B4. LLM-written Lean at scale and what the experts say
- Math Inc Gauss, strong PNT (Sept 2025) [P]: ~25k lines, >1,000 theorems/defs, ~3 weeks; humans
  supplied natural-language scaffolding and expert guidance; Gauss also formalised missing
  complex-analysis results. Tao (Oct 2026) calls it "quasi-autoformalization" with humans stepping
  in when the AI got stuck. Sphere packing in 24 dimensions (March 2026): ~500k lines golfed to
  ~200k [P, Tao post]. https://www.math.inc/gauss , https://github.com/math-inc/strongpnt
- Anthropic FLT (Sept 4 2026) [P, Buzzard]: 13.4M lines, 11 days, compiles in ~20x mathlib's time
  on 96 cores; follows Darmon-Diamond-Taylor 1995; Buzzard compiled it, ran `comparator`, audited
  the non-mathematical code with an agent's help; verdict: "adds essentially nothing
  mathematically" (he was 99.9% sure already) but matters for what it shows about
  autoformalization; proof "far from optimal" in length.
  https://xenaproject.wordpress.com/2026/09/04/flt-anthropic-has-beaten-me-to-it/
- Tao, "What mathematicians should know about Lean: reliability and AI" (Oct 9 2026) [P]: don't
  believe a proof until the kernel checks it; auditing *statement fidelity* is "massively easier"
  than auditing the proof and is where humans should spend effort; use `comparator`, scan for
  axioms, cross-check with independent kernels; the 2026 "Summer of Soundness Bugs" (a false
  Collatz disproof got through a kernel bug). https://terrytao.wordpress.com/2026/10/09/...
- Mathlib contribution policy (mid-2026) [P]: AI use must be disclosed with tools and how used;
  `LLM-generated` label; "code written by an AI without the supervision of a Lean subject expert
  fails to meet that bar by a large margin"; author must understand and defend every line; no LLM
  text in GitHub/Zulip comments. https://leanprover-community.github.io/contribute/index.html
- Formal Conjectures (DeepMind) [S]: most recent submissions use AI tooling; repo added
  AGENTS.md; DeepMind's prover ran all 353 Erdős statements (Feb 2026) with results in
  `alphaproof-nexus-results`. https://arxiv.org/html/2605.13171v1
- Buzzard elsewhere [S]: an LLM's informal proof that was auto-formalised "does not formalise the
  original proof" (Nebius interview, Apr 2026) -- statement/proof drift is the recurring expert
  worry.

---

## C. Agent-loop design lessons

### C1. Verifier-in-the-loop and repair
- Goedel-Prover-V2 (ICLR 2026) [P HTML]: one 30k-token attempt + up to 2 self-correction rounds
  (40k total) with the Lean error messages and previous CoT in the prompt. 32B: miniF2F pass@32
  88.1 -> 90.4; PutnamBench pass@32 43 -> 57 problems (86 at pass@184). Ablation: *removing the
  compiler error messages "significantly lowers performance"*; removing prior CoT hurts only
  slightly. With 128k context and 5 rounds, pass@32 92.7% beats no-correction pass@8192 92.2%.
  https://arxiv.org/html/2508.03613
- Kimina-Prover 72B (HF blog, July 2025) [S]: miniF2F pass@32 84.0 -> 86.4 with one error-fix
  round; a Zulip user notes feedback in fix mode is "very sparse and very delayed".
- APOLLO (NeurIPS 2025) [P HTML]: Syntax Refiner (regex) -> Sorrifier (compile; per failing block
  remove line / remove block / insert `sorry`) -> AutoSolver (`hint`, then `nlinarith`, `norm_num`,
  `norm_cast`, `ring_nf`, `simp`, `simp_all`) -> recursive LLM repair on remaining sorries to depth
  r -> assembler checks no sorry/admit. o4-mini 7.0% -> 46.7% at 15 samples; Kimina-7B 63.1 ->
  75.0 at ~307 samples; o3-mini: plain REPL-feedback repair 25.4% at 10 samples vs APOLLO 40.2% at
  8. 5-minute compile timeout "rarely reached". Ablation: each component alone adds <= 1-6 pts;
  the combination adds ~40. https://arxiv.org/html/2505.05758
- Delta-Prover (ByteDance, 2025; Gemini 2.5 Pro, no fine-tuning) [P HTML]: repair prompt includes
  failed proof, kernel error + tactic state, and Mathlib retrieval when the error names an unknown
  identifier. Repair-only beats Best-of-N at every budget and the gap widens; at a fixed 1024
  budget more repairs-per-round beats more rounds. miniF2F-test 95.9% vs 49.1% BoN at the same
  16,384-call budget. IMO 2019 P1: pure repair failed after 1,024 calls; decomposition into 83
  subproblems averaged ~4 calls each (~332 total). https://arxiv.org/html/2507.15225
- Minimal agent / AxProverBase (ICML 2026) [P HTML]: ReAct proposer + LeanSearch + compile +
  reviewer LLM (statement preserved, no cheating). Opus 4.5, 32k thinking, 50 iterations:
  PutnamBench 54.7% pass@1 (Hilbert 55.9%) at $12.6/problem average incl. failures, ~4.2M
  tokens/problem vs ~1,880M for Hilbert; >70% of tokens are input. Ablations: iterative refinement
  is the largest gain and single-shot sampling adds little; self-managed "lab notebook" memory
  +~7% theorems at ~20% lower cost with half the run-to-run variance; search tools cut name errors
  53% and syntax errors 26% but matter less than feedback/memory; raising thinking 10k -> 32k
  matched doubling iterations at lower cost; Gemini models had 33-56% of errors from bad imports
  vs <1.1% for Claude. https://arxiv.org/html/2602.24273v3
- Baldur (2023) [S]: repair model conditioned on Isabelle error messages lifts Thor 57.0 -> 65.7
  PISA. https://arxiv.org/abs/2303.04910

### C2. Sorry-skeleton-then-fill and lemma-style decomposition
- Draft-Sketch-Prove (ICLR 2023) [P via ar5iv]: sketch = declarative Isar with gaps `<...>`
  (not `sorry`) and inline comments copying the informal proof; gaps filled by 11 heuristics at
  10 s each, then Sledgehammer 120 s. 100 attempts/problem. Human-draft ablation (valid/test):
  full 42.6/39.3; no inline comments 37.7/36.5; no informal proof 38.9/34.0; *no automation*
  (model writes full proofs) 32.8/30.3; without sketching 154 problems vs 181 with. Saturates at
  ~70 attempts. https://ar5iv.labs.arxiv.org/html/2210.12283
- ProofAug [P]: zero-shot DSP-style sketching + ERP (re-query with proof state and verified
  partial proof on an ATP failure) reaches 56.1% miniF2F-Isabelle at <= 500 queries, matching
  SubgoalXL which used 16,384; RMaxTS gained <0.2% over naive retry at 3,200. Key design: fail
  fine, retry coarse (drop the `proof..qed` block and let automation take the whole subgoal).
- HybridProver [P]: sorry-ifying every tactic of a syntactically valid proof and refilling moved
  34.8% -> 56.1%; full system 59.4%.
- Seed-Prover 1.0 (ByteDance, July 2025) [P abstract; S details]: "lemma-style whole-proof
  reasoning model"; iteratively refines on Lean feedback, proved lemmas and self-summarization;
  three test-time settings (light/medium/heavy); 78.1% past IMO, >50% PutnamBench, 5/6 IMO 2025
  (P3 and P4 each took ~3 days, 2,000- and 4,000-line proofs; P5 1 day) [P, GitHub README].
  https://arxiv.org/abs/2507.23726 , https://github.com/ByteDance-Seed/Seed-Prover
- Seed-Prover 1.5 (Dec 2025) [P HTML]: NL prover -> sketch model emits a Lean sketch with lemmas
  admitted by `sorry` -> agentic prover attacks each lemma at pass@3x3 with tools (LooKeng REPL
  verifying one lemma at a time, verified lemmas cached in context; embedding Mathlib search;
  Python) under 64k tokens and 28 tool calls per attempt -> unsolved lemmas decomposed
  recursively to depth 4, then restart with proven lemmas kept and depth 8; a *disproved* lemma
  sends the sketch back for revision. 10 H20-days/problem vs 18 for 1.0-medium; PutnamBench
  87.9%; IMO 2025 P1 16.5 h, P3 5 h, P4 8 h, P5 1 h, P6 unsolved; Putnam 2025 11/12 within 9 h.
  RL reduced average tool calls 15 -> 10 and sequence length 28k -> 17k ("less trial and
  error"); 32-64k-token trajectories stayed net-negative. https://arxiv.org/html/2512.17260
- Aristotle (Harmonic, IMO 2025 gold-equivalent 5/6) [P HTML]: informal proof -> rewrite as a
  sequence of lemmas "each meant to have a very short proof" -> formalise statements (REPL errors
  fed back) -> MCGS tactic search per lemma; after a failure the lemma list is annotated
  proved/unproved and revised, and failures are attributed to "an unworkable strategy" or to
  "lemmas too coarse for search". Natural-language drafts contained subtle quantifier errors
  (strictly vs eventually decreasing) that formalisation caught. Statements hand-translated by
  humans. https://arxiv.org/html/2510.01346v1
- Hilbert (Apple, ICLR 2026) [S]: recursive subgoal splitting with prover + reasoner + retriever;
  PutnamBench 70.0% (462/660); average proof 1,454 lines, longest >15,000; pass@1840 average per
  Seed 1.5's accounting. https://arxiv.org/abs/2509.22819
- Numina-Lean-Agent (Claude Code + Numina-Lean-MCP; ICML 2026) [P HTML]: "blueprint" = DAG of
  definitions/lemmas/theorem with `\uses{}` edges, revised recursively on Lean feedback; Gemini
  informal prover (generator/verifier loop, accept only after 3 independent approvals, <=20
  iterations); `discuss_partner` to consult other LLMs; subagent isolates a stuck lemma (Putnam A5
  needed a GPT-5.2 hint). 12/12 Putnam 2025 with Opus 4.5; $50 default budget, ~$1,000 for A5,
  ~$300 for B6; minutes: A1 97, A2 30, A5 2040, B6 797. Observed "very long contexts degrade
  instruction-following" -> subagents. B4: iterative refinement solved in 5 rounds where
  independent sampling failed in 10. Table 2 (extraction uncertain): ~4 problems without informal
  prover, 11 with, 12 with subagent. https://arxiv.org/html/2601.14027v1
- Gödel's Poetry, Prover Agent (small-model lemma generation, 88.1% miniF2F) [S].

### C3. How diagnostics are presented to the model
- Include the *compiler message plus the goal/tactic state at the failure*, not pass/fail: this is
  the component whose removal hurts most (Goedel-V2 [P]); APOLLO queries "exact goal statements"
  for each sorry [P]; Delta-Prover adds retrieval only when the error is an unknown identifier [P].
- Replace placeholders with nothing so the checker reports the *unsolved goals* at those sites
  (Minimal agent) [P]; `lean-lsp-mcp` truncates goal/diagnostic fields to 6000 chars *from the
  middle* [P]; IsabeLLM feeds "current proof state, the failing line and error, and an error trace
  of automated fixes" [P].
- Fix-mode caveat: a model reading sparse, delayed error output does worse than one with an
  interactive goal view (Kimina Zulip [S]; Kahle [S]).
- Reviewer / cheat-screen as a separate LLM pass (Minimal agent) and axiom/`sorry` checks in the
  verifier, never by grep (Trail of Bits; Numina's standard-axiom check) [P].

### C4. Context bloat and compaction
- Evidence of harm: Numina (instruction-following degrades) [P]; Seed-Prover 1.5 (32-64k
  trajectories net-negative; RL itself shortened trajectories) [P].
- Mitigations with measured effect: self-managed short notes (+7% / -20% cost, Minimal agent)
  [P]; cache *verified* lemmas and re-inject them on restart instead of transcripts (Seed 1.5)
  [P]; isolate stuck lemmas in subagents with fresh context (Numina) [P]; whiteboard that only
  stores Lean-verified items (OpenProver, arXiv 2607.09217) [S]; ProofAug dropped 3-shot for
  1-shot because 4,096-token prompts truncated proofs [P].

### C5. Budget schedules and reported costs
- Fixed vs adaptive LLM-attempt budgets: "Optimizing the Cost-Quality Tradeoff of Agentic
  Theorem Provers in Lean" (MathArena, 2026) [P]: a control plane deciding continue-vs-restart
  from trajectory features cut cost 28.9% at equal accuracy (+7.9% accuracy at equal cost) over
  fixed attempts-per-target; *error diversity* across failed attempts was the most predictive
  feature, attempt count alone only 13.1%; oracle routing would save 62-67%. 85-problem
  PutnamBench subset, 1,600-2,000 GH200 hours. https://arxiv.org/html/2606.04883 ,
  https://matharena.ai/optimizing_agents/
- Reported costs (not comparable; collect for calibration) [P unless marked]: Minimal agent
  $12.6/problem avg; Numina $50 default / $1,000 max; Aleph Prover ~$74 avg, max $1,468.74 incl.
  failures [S]; MerLean ~$118 per solved Putnam 2025 problem [S]; NEAR AI DeepSeek-V4 agent ~$112
  total for 724 attempts on 672 PutnamBench problems (~$0.17 each; flash solved 653, pro 19; two
  problems are corrected variants) [S, repo README via search]; Seed-Prover 1.5 10 H20-days per
  problem (~$168 at Apr 2026 cloud prices, third-party estimate) [S]; Rocq-MCP ~1.9B tokens for
  12 problems [P]; AlphaProof ~500 TPU-days/problem (as cited by Seed 1.5) [S].
- Hammer-side budgets actually used by sketch-fill systems: 10 s per heuristic + 120 s
  Sledgehammer (DSP, ProofAug); 30 s (HybridProver); 60 s (IsabeLLM); LeanHammer 10 s per ATP
  call, 300 s per theorem; APOLLO 5 min compile, rarely hit. No paper varies the hammer timeout
  as an experimental factor -- see D2.

### C6. Parallel verification and caching
- Kimina: header-keyed REPL warm cache is the single biggest win (1.94x); one REPL per physical
  core; batch at the client [P]. Aristotle: stateless workers, full state per request [P].
  Gauss: a Lean runtime per agent, thousands concurrent [P]. ProofAug: 12 PISA instances [P].
- Isabelle-specific: proof states for pre-built sessions require `-o show_states` at build time
  (slow) -- kappelmann README [P]; Pool-Server-style scratch sessions are the Isabelle analogue of
  Kimina's warm REPLs (your own system; no external evaluation found).

### C7. Lemma reuse across problems
- LEGO-Prover (ICLR 2024) claimed a growing library of 20k+ skills raised miniF2F-Isabelle to
  57.0/50.0 [S]. "LLM Library Learning Fails: A LEGO-Prover Case Study" (Berlot-Attwell, Rudzicz,
  Si, 2025) [P abstract]: "no evidence of the direct reuse of learned lemmas", evidence *against*
  soft reuse, and the accuracy gains "vanish once computational cost is accounted for"; the
  companion paper attributes gains to self-correction and self-consistency.
  https://arxiv.org/abs/2504.03048
- *Within-problem* lemma caching does pay (Seed 1.5, Numina blueprint, Aristotle's proved-lemma
  annotations) [P]. Cross-problem libraries: unproven for competition math.

---

## D. Prompting evidence

### D1. Do worked examples / few-shot exemplars help strong LLMs prove?
- DSP [P]: 3 of 20 hand-written sketch examples per prompt (type-matched when known). The
  ablations show inline informal comments (+3-5 pts) and the informal proof (+4-5) matter, and
  gap-filling automation matters most (+9-10); there is **no zero-shot vs few-shot ablation**.
- COPRA (COLM 2024) [P abstract]: "few-shot prompting of GPT-4 is not effective at proof
  generation"; a stateful agent with execution feedback and retrieved lemmas beats it.
  https://arxiv.org/abs/2310.04353
- HybridProver (Isabelle, fine-tuned Qwen-Coder-7B) [P]: no improvement from few-shot examples;
  "the model has already learned the Isabelle syntax ... the few-shot prompting provides no extra
  hints to prove the theorem."
- ProofAug (Isabelle, deepseek-math-7b-base) [P]: without ProofAug, both few-shot and zero-shot
  are well below DSP-style prompting; with ProofAug's structural repair they catch up; they
  reduced to 1-shot because of context length.
- ProofBridge (Lean, 2025) [S]: *random* in-context examples raised syntactic correctness
  (TC 93.85%) but lowered semantic correctness (SC 31.56%) -- models imitate shape and hallucinate
  content; retrieval-matched examples behaved differently.
- IsabeLLM (2026, n=16 lemmas) [P]: 3 *retrieved similar proofs* in the prompt lifted 76.3% ->
  94.4% (Chimera) and fixed a 0% lemma to 90%; helps "proofs that mirror existing ones", less for
  novel ones.
- Minimal agent / Numina / Delta-Prover (frontier models) [P]: none use few-shot proof exemplars;
  they rely on instructions, feedback and retrieval. Trail of Bits / lean4-skills encode *rules*,
  not exemplars.
- Net reading: for strong, Isabelle-literate models, exemplars buy syntax/style conformance, not
  proving power; retrieval-matched exemplars (similar lemma in the same development) are the
  variant with measured benefit; random exemplars can hurt semantics; no controlled 2025-26
  ablation on frontier models in Isabelle exists -- **a gap this project could fill cheaply**.

### D2. Fixed vs adaptive hammer timeouts
- Isabelle's 30 s default rests on the 2010 Böhme-Nipkow study (few proofs lost going 60 -> 30 s
  with parallel provers) [P commit message; paper numbers U]. Magnushammer's Fig. 1 shows
  Sledgehammer saturating quickly with compute [P statement, S figure].
- Every LLM-Isabelle system fixes the budget (10 s heuristics / 120 s hammer is the de facto
  DSP-lineage standard; 30 s and 60 s also used) and none reports a timeout ablation [P].
- LeanHammer: 10 s ATP calls inside a 300 s theorem budget, no time ablation [P].
- The only adaptive-budget evidence is for *LLM attempts*, not hammer time: dynamic
  continue/restart saved ~29% cost (MathArena) [P]; Delta-Prover's "more repairs per round"
  finding [P].
- Conclusion: there is no published evidence that adaptive hammer timeouts beat a fixed short
  budget for hard problems; the published practice is short-first (try0/heuristics at 5-10 s),
  one longer Sledgehammer (30-120 s), then *change the goal* (decompose) rather than wait longer.
  Marking "adaptive hammer timeout helps" as **unverified**.

---

## E. Synthesis: evidence-backed design rules for an agentic Isabelle pipeline on hard problems

Decomposition
1. **Skeleton first, prove bottom-up.** Make a `sorry`-skeleton that *checks* before any proof
   work; each `sorry` is an independent unit. (Trail of Bits skill [P]; DSP sketch ablation +9-10
   pts from automation on sketch gaps [P]; HybridProver 34.8 -> 56.1 [P]; Tao's whole-proof attempt
   failing vs step-wise succeeding [S].)
2. **Lemmas should have very short proofs.** Aristotle restructures the informal proof into
   lemmas "each meant to have a very short proof" and attributes failure to lemmas "too coarse for
   search" [P]; Delta-Prover solved IMO 2019 P1 as 83 subproblems at ~4 calls each after 1,024
   monolithic calls failed [P]. Operationally: if a Sledgehammer fill fails twice, split the goal
   rather than raise the timeout.
3. **Fail fine, retry coarse, then re-sketch.** ProofAug drops the enclosing `proof..qed` block
   and lets automation try the coarser goal; Seed 1.5 and Aristotle send a *disproved* or
   repeatedly failing lemma back to sketch revision [P]. Build this escalation ladder explicitly.
4. **Disprove early.** Run `nitpick`/`quickcheck` on every new `have`/lemma statement before
   proving it; a genuine counterexample means the sketch is wrong, not the proof. (IsabeLLM: fewer
   repeated failure loops [P]; Seed 1.5 routes disproved lemmas to sketch repair [P]; Aristotle
   caught quantifier errors only at formalisation [P].) Treat "potentially spurious" as a hint only
   (Nitpick manual [P]).

Automation budgets
5. **Cheap-to-expensive ladder per goal**: `solve_direct`/`try0` (seconds) -> heuristics
   (`auto`, `simp`, `blast`, `fastforce`, `linarith`, `presburger`, `arith`, `auto simp:
   field_simps`) at ~10 s -> Sledgehammer 30-120 s, once. (DSP/ProofAug 10 s + 120 s [P];
   HybridProver 30 s [P]; Isabelle default 30 s soft [P].) Don't spend hammer time twice on the same
   goal; spend it on a reshaped goal.
6. **Trust the preplayed one-liner only in its own context.** Sledgehammer preplays for 1 s with
   `try0`-set fallbacks; transplanting a `metis` call to another goal has no such guarantee
   (manual [P]; your transplant finding). Bind fills to goals *in the verifier's bookkeeping* even
   if the solver rule does not.
7. **Prefer `isar_proofs` / `smt` fallbacks when `metis` times out**, and limit facts. The manual's
   remedies are: fewer facts (25-50), simplify the goal, `metis (full_types)`, Isar proof; "runs
   seemingly forever" means too hard for Metis, not "needs more time" [P].
8. **Budget by LLM attempts adaptively, not by hammer seconds.** The one measured adaptive policy
   (continue vs. restart from failed-trajectory *error diversity*) saved 28.9% cost at equal
   accuracy [P]; repair beats best-of-N at every budget and more repairs-per-round beats more
   rounds [P]. Stop a target when consecutive failures repeat the same error.

Feedback format
9. **Always return error + goal state at the failure site**, with `sorry`s reported as unsolved
   goals; truncate from the middle, keep context and target (Goedel-V2 ablation [P]; Minimal agent
   [P]; lean-lsp-mcp 6000-char rule [P]).
10. **Make feedback interactive and fast**; an LSP-style goal view beats compile-and-read logs
    (Kahle [S]; Kimina fix-mode complaint [S]; Isabelle PIDE MCP states need `show_states` builds
    [P]). Report Sledgehammer *results per goal with the fact list*, so the model can minimise.
11. **Keep a verified-lemma cache and a short self-managed notebook instead of the raw
    transcript**; restart with the cache when context passes ~30k tokens (Seed 1.5 negative
    32-64k [P]; Minimal agent +7%/-20% [P]; Numina subagents [P]).

Repair
12. **Iterate, don't resample.** Iterative refinement is the dominant lever (Minimal agent [P];
    Goedel-V2 +14 PutnamBench problems at pass@32 [P]; APOLLO 7 -> 46.7% [P]; Numina B4 5 rounds vs
    10 failed samples [P]). Two to five rounds capture most of the gain.
13. **Sorrify before re-prompting.** Convert a failing proof into the maximal compiling
    semi-proof (remove line / remove block / insert sorry), run automation on the holes, and send
    only the surviving holes back (APOLLO [P], ProofAug FindMCSP [P], HybridProver [P]).
14. **Retrieve on name errors only.** Unknown-identifier errors trigger library retrieval
    (Delta-Prover [P]); search tools cut name errors ~53% but matter less than feedback (Minimal
    agent [P]). For Isabelle: `find_theorems`/`solve_direct` on demand, not every turn.

Parallelism and infrastructure
15. **Warm sessions keyed by imports; one worker per core; batch checks.** Kimina's 1.94x from
    import-cache reuse and near-linear scaling to 32 cores [P]; Aristotle's stateless workers
    [P]. Your scratch-session pool is the Isabelle analogue; measure its hit rate.
16. **Verify a frozen artifact, not the live session.** Re-render the final theory and build it
    cold; check for `sorry`/oracles/`smt_oracle` and that statements are unchanged (Aristotle,
    Minimal agent's reviewer, Trail of Bits `collectAxioms`, Tao's statement-fidelity advice [P]).
    (Your `verified.thy` + `_final_verify` already follows this.)

Cost control
17. **Set a per-problem dollar/time cap with a documented escalation tier** ($50 default with
    rare $300-1,000 escalations is the Numina pattern; $12.6 average for a minimal agent; hours
    not days for IMO-level with Seed 1.5's workflow [P]). Log tokens per solved problem so the
    experiment can report cost-per-solve, not just solve rate (Berlot-Attwell's equal-compute
    critique [P]).
18. **Don't build a cross-problem lemma library expecting reuse**; within-problem caching pays,
    cross-problem reuse has no evidence (LEGO-Prover critique [P]).
19. **Spend prompt budget on instructions and retrieved near-identical proofs, not random
    exemplars** (HybridProver, COPRA, ProofBridge, IsabeLLM [P/S]); run your own
    zero-shot-vs-3-shot ablation since none exists for frontier models in Isabelle.

---

## F. Gaps and unverified items (for the owner)
- Judgement Day (2010) success-vs-timeout curve; "Hammering towards QED" numbers; Blanchette's
  Isar-proof reconstruction success rates -- all [U], TUM hosts refused on 2026-11-10.
- Current default Nitpick/Quickcheck timeout (30 s in older manuals) -- confirm with
  `nitpick_params`/`quickcheck_params` in Isabelle2025.
- Seed-Prover 1.0 light/medium/heavy specifics -- abstract and README only.
- Tao's Claude Code video content is from an HN commenter; Tao's direct quotes are limited to the
  ones listed.
- NEAR AI $112 / 672 PutnamBench run: repo README seen via search snippets only.
- No published ablation on fixed vs adaptive hammer timeouts; no Isabelle MCP agent evaluated on
  PutnamBench or IMO other than this repository.

## Source index (primary URLs used)
- Sledgehammer manual (mirror): https://raw.githubusercontent.com/isabelle-prover/mirror-isabelle/master/src/Doc/Sledgehammer/document/root.tex
- Nitpick manual (mirror): https://raw.githubusercontent.com/isabelle-prover/mirror-isabelle/master/src/Doc/Nitpick/document/root.tex
- Isar-ref HOL chapter (mirror): https://raw.githubusercontent.com/isabelle-prover/mirror-isabelle/master/src/Doc/Isar_Ref/HOL_Specific.thy
- Prog_Prove Isar chapter: https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/library/Doc/Prog_Prove/Isar.html
- AFP submission rules: https://www.isa-afp.org/submission/
- Sledgehammer timeout commits: https://isabelle.in.tum.de/repos/isabelle/rev/87a9ff4d5817 , https://isabelle.in.tum.de/repos/isabelle/rev/07ebc2398731
- timeout_scale NEWS: https://mailman46.in.tum.de/pipermail/isabelle-dev/2015-November/006406.html
- Judgement Day (unfetched): https://www21.in.tum.de/~boehmes/judgement.html
- Hammering towards QED: https://jfr.unibo.it/article/view/4593 ; Hardening the Hammer: https://gepris.dfg.de/gepris/projekt/226154341/ergebnisse
- Magnushammer: https://arxiv.org/abs/2303.04488 ; Thor: https://arxiv.org/abs/2205.10893 ; Baldur: https://arxiv.org/abs/2303.04910 ; MiniLang: https://arxiv.org/abs/2507.18885
- DSP: https://ar5iv.labs.arxiv.org/html/2210.12283 ; Lyra: https://arxiv.org/abs/2309.15806 ; LEGO-Prover: https://arxiv.org/abs/2310.00656 ; critique: https://arxiv.org/abs/2504.03048
- ProofAug: https://arxiv.org/html/2501.18310 ; HybridProver: https://arxiv.org/html/2505.15740v1 ; IsabeLLM: https://arxiv.org/html/2606.18098v1
- Isabelle PIDE MCP: https://github.com/kappelmann/isabelle-pide-ai , https://zenodo.org/records/22726567 ; https://github.com/danmatichuk/isabelle-pide-mcp
- LeanHammer: https://arxiv.org/html/2506.07477v2 , https://github.com/JOSHCLUNE/LeanHammer ; Canonical: https://arxiv.org/abs/2504.06239 ; Lean Copilot: https://arxiv.org/abs/2404.12534
- Kimina Lean Server: https://arxiv.org/abs/2504.21230 ; Kimina-Prover 72B: https://huggingface.co/blog/AI-MO/kimina-prover
- lean-lsp-mcp: https://github.com/oOo0oOo/lean-lsp-mcp ; lean4-skills: https://github.com/cameronfreer/lean4-skills ; Trail of Bits: https://trailofbits.com/skills/writing-lean-proofs/
- Numina-Lean-Agent: https://arxiv.org/html/2601.14027v1 , https://github.com/project-numina/Numina-Putnam2025
- Seed-Prover: https://arxiv.org/abs/2507.23726 , https://arxiv.org/html/2512.17260 , https://github.com/ByteDance-Seed/Seed-Prover
- Delta-Prover: https://arxiv.org/html/2507.15225 ; Goedel-Prover-V2: https://arxiv.org/html/2508.03613 ; APOLLO: https://arxiv.org/html/2505.05758
- Aristotle: https://arxiv.org/html/2510.01346v1 ; Hilbert: https://arxiv.org/abs/2509.22819 ; Minimal agent: https://arxiv.org/html/2602.24273v3
- Cost-quality routing: https://arxiv.org/html/2606.04883 , https://matharena.ai/optimizing_agents/ ; Rocq-MCP Putnam: https://arxiv.org/abs/2603.20405
- Gauss: https://www.math.inc/gauss , https://github.com/math-inc/strongpnt ; Buzzard on FLT: https://xenaproject.wordpress.com/2026/09/04/flt-anthropic-has-beaten-me-to-it/
- Tao, Oct 2026: https://terrytao.wordpress.com/2026/10/09/what-mathematicians-should-know-about-the-lean-theorem-proverquestions-of-reliability-and-ai/ ; Tao video thread: https://news.ycombinator.com/item?id=47306852
- Mathlib AI policy: https://leanprover-community.github.io/contribute/index.html ; Formal Conjectures: https://arxiv.org/html/2605.13171v1
- COPRA: https://arxiv.org/abs/2310.04353 ; ProofBridge: https://arxiv.org/pdf/2510.15681 ; Kahle blog: https://thomas-kahle.de/blog/2026/auto-formalization-1-keep-trying/
- NEAR AI PutnamBench agent: https://github.com/nearai/putnambench-deepseek ; Aleph: https://logicalintelligence.com/aleph-prover-final.html
