# The prompts, side by side

Rendered on 2026-11-10 for `imo_2026_p1`; regenerate with the snippet at the
end after any change to `_system_prompt` or `harness/arms.py`.

| File | What |
|---|---|
| `system_prompt_upstream_nearai_lean.md` | nearai/putnambench-deepseek's Lean prompt, user message and nudge |
| `system_prompt_plain.md` | our plain arm (per-goal sledgehammer) |
| `system_prompt_skeleton_forced.md` | our forced arm (skeleton + filler, leaf rule) |
| `plain_vs_skeleton_forced.diff` | the only lines that differ between our two arms |

## Upstream vs our plain arm

Same skeleton: the opening sentence, a Problem block, the tools, "HOW THIS RUN
ENDS" with the same two exits, "If the goal is false", Rules, the nudge. The
user message is the same sentence with Lean swapped for Isabelle.

| Section | upstream (Lean) | ours (plain) | why |
|---|---|---|---|
| Tools | one `bash` tool (read/rewrite the file, run `lake env lean`, scratch files) + `completed`, `disproved` | `read_file`/`write_file` returning diagnostics, 11 structured Isabelle queries, `isabelle_sledgehammer`, `completed`, `disproved`, `write_disproof` | no shell; the MCP is the interface under test |
| How to build | explains `lake env lean`, the 30-60 s cold start | none; every write returns diagnostics | the server replaces the compiler loop |
| Solver rule | none (verify.sh bans soundness escapes only) | SOLVER RULE: no hand-written metis/smt/meson/moura, enforced | the experiment's variable |
| "You have NO limits" | a whole section, repeated in the user message and the nudge | pass 1: one sentence ("do not ration effort ..."); from rep 1 (2026-11-10): the same section, user-message sentence and nudge, worded for a run whose wall clock the harness owns ("you cannot see it, speed it or save it") | the model is never the one managing the 4 h / 8 h wall |
| If the goal is false | three steps + reviewer warning | one paragraph, Isabelle-flavoured causes | condensed |
| Rules | do not modify the Mathlib project | do not change the header; no axiomatization/ML/setup/declare/notation/hide_* | Isabelle's escape hatches |
| Anti-cheat | a CRITICAL section (no other dirs, no find/grep, no web) | one line | no shell |
| Strategy | none beyond "think harder, try a different tactic, intermediate lemmas" | 8 steps: structured Isar, closers, find_theorems, multi_attempt, diagnostics, completed, sledgehammer | Isabelle needs method guidance |
| Problem block | informal statement | "(none)"; the five frozen theorems named | IMO files carry statements only |
| Nudge | + "NO turn limit and NO time limit", "you are doing well", "chase a suspected false goal" | pass 1: those sentences removed; from rep 1: restored; third consecutive stop ends the attempt either way | give-up cap added 2026-11-10 (489 nudges on P3 in pass 1) |

Two of these may have moved the pass-1 numbers: the missing no-limits language
(plain P3 gave up "in the available time", which nothing in our prompt mentioned
and upstream denies three times), and the Strategy section (ours is more guided
than upstream's). The no-limits language is back from rep 1 on; the prompt also
tells the model that three consecutive stops end the run unsolved, which is
true of our harness and not of upstream's. Every results row carries
`prompt_sha`, the first 12 hex digits of the SHA-256 of the system prompt the
model saw, so rows under the two wordings are separable (pass-1 rows have no
such field). The arm comparison is unaffected: the two arms differ only inside
the Strategy section and the rule block (see the diff).

## Regenerate

```python
import sys, tempfile, pathlib; sys.path.insert(0, "tests")
import run_isabelle_solver as rs; from harness import ib; from harness.arms import ARMS
from test_harness import FakeBridge
entry = ib.load_manifest()["imo_2026_p1"]
for arm in ("plain", "skeleton_forced"):
    d = pathlib.Path(tempfile.mkdtemp())
    ib.cmd_stage(type("A", (), {"problem": "imo_2026_p1", "dest": str(d), "variant": "wsolution", "force": True})())
    at = rs._Attempt(entry, "wsolution", ARMS[arm], d, FakeBridge(), True)
    pathlib.Path(f"docs/prompts/system_prompt_{arm}.md").write_text(rs._system_prompt(at))
```
