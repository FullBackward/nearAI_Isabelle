"""arms.py - the experimental conditions.

Every arm drives the SAME Isabelle Pool Server LSP MCP, the same model, the
same harness loop, the same verifier and the same rules; an arm only decides
(1) which MCP tools the agent sees, (2) whether `write_file` runs the
server-side `fill_sorries` automatically on a sorry-skeleton, and (3) the
strategy section of the system prompt.

    plain          sledgehammer one goal at a time (isabelle_sledgehammer),
                   no fill tools. The "normal MCP" baseline.
    skeleton       the agent is made to work skeleton-first: no per-goal
                   sledgehammer; every write_file whose text parses and still
                   has `sorry`s is automatically sent to isabelle_fill_sorries
                   (sledgehammer on every sorry at once, server-side), the
                   patched text is written back, and the agent continues from
                   what remains. The explicit fill tools stay available for a
                   re-run with other budgets.
    fill_optional  both tool sets, nothing automatic, neutral prompt --
                   measures whether the agent reaches for fill_sorries on its
                   own. (Optional third arm.)

In every arm the SOLVER RULE is enforced by the harness, not just worded:
proof text invoking an ATP-reconstruction method (metis / smt / meson / moura)
is accepted by write_file only when that exact method call came out of a
sledgehammer / fill_sorries result during the attempt. So the two main arms
differ in exactly one thing: how sledgehammer is reached.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# File-scoped read-only tools every arm gets (file_path is injected by the
# harness; the agent never passes paths). Lifecycle, checkpoint, heap and
# memory tools are harness business and stay hidden.
COMMON_TOOLS = [
    "isabelle_diagnostic_messages",
    "isabelle_goal",
    "isabelle_proof_state",
    "isabelle_command_at_line",
    "isabelle_query",
    "isabelle_local_facts",
    "isabelle_global_facts",
    "isabelle_hover_info",
    "isabelle_definition",
    "isabelle_multi_attempt",
    "isabelle_run_code",
]
SLEDGEHAMMER_TOOLS = ["isabelle_sledgehammer"]
FILL_TOOLS = ["isabelle_fill_sorries", "isabelle_fill_status", "isabelle_fill_cancel"]
# Outputs of these tools are the only source of sanctioned solver calls.
SOLVER_SOURCE_TOOLS = set(SLEDGEHAMMER_TOOLS + FILL_TOOLS)


@dataclass(frozen=True)
class Arm:
    name: str
    description: str
    mcp_tools: list[str]
    auto_fill: bool
    strategy: str
    tool_notes: str = ""


_COMMON_STRATEGY = """\
1. Read the file. Restate the goal to yourself in ordinary mathematics.
2. Get the mathematical idea straight before writing Isar -- these are
   competition problems: formalizing is routine once the argument is right and
   hopeless when it is not. A sketch you could say aloud in a minute, then test
   its first step against Isabelle.
3. Write STRUCTURED Isar (`proof -` ... `have ... by ...` ... `show ?thesis` ...
   `qed`), one small, checkable step per `have`. Flat `apply` scripts and
   one-line `by auto` attempts on the whole goal rarely work on these problems.
4. General-purpose closers worth trying first on a step: `simp`,
   `simp add: algebra_simps field_simps`, `auto`, `force`, `fastforce`, `blast`,
   `linarith`, `arith`, `algebra`, `presburger`, `argo`, `(rule ...)`,
   `(induct n)`, `(cases ...)`, `eval`/`norm_num`-style `by simp`/`by eval`
   for ground arithmetic, `unfolding ..._def`.
5. Find lemmas with isabelle_query("find_theorems ...") and
   isabelle_query("thm name"); inspect a goal state with isabelle_goal(line).
   isabelle_multi_attempt(line, candidates) tries several candidate steps in
   isolation without touching the file.
6. After EVERY write_file read the diagnostics it returns and fix every error
   it reports (line, kind, message). Keep writes small and frequent.
7. When the diagnostics are clean and no `sorry` remains, call completed().
"""

_PLAIN_STRATEGY = _COMMON_STRATEGY + """\
8. When a subgoal defeats the closers above, call
   isabelle_sledgehammer(line=<the line of the `have`/`show` whose goal is
   open>, subgoal=1, timeout_s=30..120). Paste its suggested method VERBATIM.
   If it finds nothing, split the goal into smaller `have` steps and
   sledgehammer those, or give it more facts via `using`.
"""

_SKELETON_STRATEGY = _COMMON_STRATEGY + """\
8. SKELETON FIRST. Write the whole proof as an Isar skeleton in which EVERY
   step you cannot close with the simple closers above ends in `sorry` --
   including `show ?thesis ... sorry` and the leaves of case splits and
   inductions. Each write_file whose text parses with no errors and still
   contains `sorry` is AUTOMATICALLY handed to the server, which runs
   sledgehammer on every `sorry` at once and writes the proved ones back into
   your file (you get the new file text, the per-sorry outcomes and the lines
   still `sorry`).
9. Then iterate on what remains: for each surviving `sorry`, refine the
   skeleton -- split the step into smaller `have`s, add the facts it needs
   with `using`, state the intermediate equalities explicitly -- and write the
   file again. Do not try to hand-prove a hard leaf before the filler has had
   a go at a well-stated version of it. isabelle_fill_sorries(timeout_s=...)
   re-runs the filler with a bigger per-sorry budget when a leaf looks
   plausible but timed out.
"""

_OPTIONAL_STRATEGY = _COMMON_STRATEGY + """\
8. Two ways to reach sledgehammer: isabelle_sledgehammer(line, subgoal) on one
   open goal, or isabelle_fill_sorries() which runs sledgehammer on every
   `sorry` in the file at once and returns the patched text (write it back
   with write_file). Use whichever fits.
"""

ARMS: dict[str, Arm] = {
    "plain": Arm(
        name="plain",
        description="LSP MCP with per-goal sledgehammer; no fill_sorries",
        mcp_tools=COMMON_TOOLS + SLEDGEHAMMER_TOOLS,
        auto_fill=False,
        strategy=_PLAIN_STRATEGY,
    ),
    "skeleton": Arm(
        name="skeleton",
        description="LSP MCP, skeleton-first: write_file auto-runs fill_sorries; no per-goal sledgehammer",
        mcp_tools=COMMON_TOOLS + FILL_TOOLS,
        auto_fill=True,
        strategy=_SKELETON_STRATEGY,
    ),
    "fill_optional": Arm(
        name="fill_optional",
        description="LSP MCP with both sledgehammer and fill_sorries; nothing automatic",
        mcp_tools=COMMON_TOOLS + SLEDGEHAMMER_TOOLS + FILL_TOOLS,
        auto_fill=False,
        strategy=_OPTIONAL_STRATEGY,
    ),
}
