# IMO 2026 in Isabelle/HOL

The six problems of the 67th IMO (Shanghai, 15–16 July 2026), as Isabelle/HOL
statement files. The formal statements follow, definition for definition and
hypothesis for hypothesis, the Lean 4 statements published by
[AxiomMath/IMO2026](https://github.com/AxiomMath/IMO2026) (`IMO2026/Q*/problem.lean`),
which every published IMO 2026 proving harness (AxiomProver, MechMath,
humanfia, …) is scored on; the Lean originals are kept in `../lean/`. For a
strict comparison the files contain exactly what the Lean files contain: the
formal statement and the per-definition docstrings (as `text` blocks), and no
informal problem text. The official wording is in the
[problems PDF](https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf).

Like the Lean harnesses' `verify.py`, a problem counts as solved only when
**every** `sorry` in its file is gone and the whole file builds, with all
definitions and all theorem statements unchanged (`harness/ib.py` enforces this
textually; the bigstep build does the rest). A file may state several
theorems: P1 has five, P3 six; all of them are the problem.

| file | heap needed | theorems | Lean file |
|---|---|---|---|
| `imo_2026_p1.thy` | HOL-Computational_Algebra | 5 | Q1 |
| `imo_2026_p2.thy` | HOL-Analysis | 1 | Q2 |
| `imo_2026_p3.thy` | HOL (Complex_Main) | 6 | Q3 |
| `imo_2026_p4.thy` | HOL (Complex_Main + HOL-Library.Multiset) | 1 | Q4 |
| `imo_2026_p5.thy` | HOL (Complex_Main) | 1 | Q5 |
| `imo_2026_p6.thy` | HOL (Main) | 1 | Q6 |

Check that the statements build (no model involved):

    python3 scripts/bigstep_check.py problems/imo2026/isabelle/*.thy

## Lean → Isabelle correspondence and deviations

Common: `ℕ`/`ℝ` → `nat`/`real`; `Finset`/`Multiset` → `set` with `finite` /
`multiset`; `Relation.ReflTransGen` → `rtranclp`; Lean's
`set_option backward.isDefEq.respectTransparency false` has no analogue and
is dropped. Statements that in Lean quantify over a subtype (`{x : ℝ // 0 < x}`)
quantify over the base type with the positivity hypothesis made explicit.

**P1** (`imo_2026_p1.thy`, taken verbatim from `~/GitHub/isabelle-humanize`,
where a DeepSeek run already discharged all five theorems):
`Multiset ℕ` ~ `nat multiset`; `m ::ₘ s` ~ `add_mset m s`; `Multiset.card` ~
`size`; `B.filter P` ~ `filter_mset P B`; `padicValNat p a` ~
`multiplicity p a` (agree for prime `p`, which is the only use);
`(B.map (padicValNat p)).gcd` ~ `Gcd (set_mset (image_mset (multiplicity p) B))`
(gcd is idempotent and `gcd a 0 = a`, so duplicates and zeros do not matter,
`Gcd {} = 0` matches `Multiset.gcd ∅ = 0`); `B.prod.primeFactors` ~
`prime_factors (prod_mset B)`.

**P2**: `EuclideanSpace ℝ (Fin 2)` ~ `real^2`; `midpoint ℝ A B` ~
`midpoint A B`; `Collinear ℝ {A,B,C}` ~ `collinear {A, B, C}`; `α • X` ~
`α *⇩R X`; `EuclideanGeometry.angle P Q R` has no distribution counterpart and is
defined in the file as `angle P Q R = arccos (((P-Q) ∙ (R-Q)) / (norm (P-Q) * norm (R-Q)))`,
which is Mathlib's definition unfolded (both systems give `pi/2` for a zero
vector, since `x / 0 = 0`). `InsideTriangle`, `InsideAngle` and
`IsCircumcentre` are transcribed literally. Note that the Lean file (and so this
file) only asks that `K` lie inside the *angle* `LBA` and `L` inside the *angle*
`ACK`, where the official wording puts `K` strictly inside triangle `ABL` and `L`
inside triangle `AKC`. A triangle interior lies inside the angle cone, so the Lean
hypotheses are weaker and the Lean theorem is the stronger one; do not "fix" this
towards the official wording, the comparison is against the Lean statement.
Docstrings must not use checked antiquotations (`\<^const>`, `\<^term>`) for names
defined later in the file; P1 uses the unchecked `\<const>` symbol on purpose.
The circumcentre is named `Oc`, not
`O`: in HOL `O` is the infix for relation composition (`r O s`) and cannot be
a variable.

**P3**: `Finset ℝ` ~ `real set` plus `finite`, so `AdmissibleMark` gains
`finite X` and the two sanity theorems gain `finite` hypotheses;
`pieceLengths` uses `sorted_list_of_set` for `Finset.sort`;
`firstPlayerShare`'s "even positions of the list sorted non-increasingly" is
`rev (sort L)` indexed by `filter even [0..<length s]`; `L A B` is named
`liu_share` (`L` would clash with the bound variable of the same name);
`⨆ A : {A // …}, ⨅ B : {B // …}, …` ~ `Sup ((λA. Inf (… ` {B. …})) ` {A. …})`
(same values: both are the conditionally complete `Sup`/`Inf` of the real
line over non-empty bounded sets). The unused Lean `answer` definition is
not reproduced; the theorems use the literal `2^n / (2^(n+1) - 1)` as in Lean.

**P4**: `Multiset ℝ` ~ `real multiset`, `{α, β, γ}` ~ `{#α, β, γ#}`,
`s.sum` ~ `sum_mset s`; the `inductive MulanWins` becomes an Isabelle
`inductive` with the same two rules `win` and `move`; `180 / n` with `n : ℕ`
cast ~ `180 / real n`.

**P5**: `f : PositiveReal → PositiveReal` ~ `f :: real ⇒ real` with the
hypothesis `∀x>0. 0 < f x`; the inequality is required for all positive `x, y`;
`Real.sqrt` ~ `sqrt`.

**P6**: `IsValidSeq` transcribed literally (0-indexed, `Nat.gcd` ~ `gcd`).
