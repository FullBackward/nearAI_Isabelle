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
| "You have NO limits" | a whole section, repeated in the user message and the nudge | one sentence ("do not ration effort ...") | we run a 4 h wall clock, upstream 3 days |
| If the goal is false | three steps + reviewer warning | one paragraph, Isabelle-flavoured causes | condensed |
| Rules | do not modify the Mathlib project | do not change the header; no axiomatization/ML/setup/declare/notation/hide_* | Isabelle's escape hatches |
| Anti-cheat | a CRITICAL section (no other dirs, no find/grep, no web) | one line | no shell |
| Strategy | none beyond "think harder, try a different tactic, intermediate lemmas" | 8 steps: structured Isar, closers, find_theorems, multi_attempt, diagnostics, completed, sledgehammer | Isabelle needs method guidance |
| Problem block | informal statement | "(none)"; the five frozen theorems named | IMO files carry statements only |
| Nudge | + "NO turn limit and NO time limit", "you are doing well", "chase a suspected false goal" | those sentences removed; third consecutive stop ends the attempt | shortened; give-up cap added 2026-11-10 |

Two of these may have moved the numbers: the missing no-limits language (plain
P3 gave up "in the available time", which nothing in our prompt mentions and
upstream denies three times), and the Strategy section (ours is more guided than
upstream's). The arm comparison is unaffected: the two arms differ only inside
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
