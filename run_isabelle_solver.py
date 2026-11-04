#!/usr/bin/env python3
"""run_isabelle_solver.py - agent harness for Isabelle/HOL benchmarks.

The Isabelle counterpart of nearai/putnambench-deepseek's run_putnam_solver.py,
built on the same agentlib (trajectory capture, compaction, the loop that
refuses to let the model stop). What changed:

  * no bash. The agent's world is ONE .thy file plus the Isabelle Pool Server
    LSP MCP (mcp_servers.lsp in Isabelle-Pool-Server): `read_file` /
    `write_file` from the harness, the MCP's read-only query tools, and --
    depending on the ARM (harness/arms.py) -- per-goal sledgehammer and/or the
    server-side `fill_sorries`.
  * the finishing tools are the same two: `completed()` runs the verifier
    (harness/ib.py: textual rules + `isabelle build` through the Pool Server)
    and only a PASS ends the run; `disproved()` files a human-reviewed claim
    that the formalized statement is false.
  * the SOLVER RULE is enforced: write_file rejects proof text with a
    metis/smt/meson/moura call that did not come out of a sledgehammer or
    fill_sorries result in this attempt.
  * budgets are finite by default (this is a comparison, not a leaderboard
    push): --max-steps 150, --timeout 3600 s. Raise them as you like.

Usage:
    python3 run_isabelle_solver.py --problem mathd_algebra_276 --arm skeleton
    python3 run_isabelle_solver.py --loop 0            # drain the queue
    python3 run_isabelle_solver.py --loop 0 --arm plain

Every attempt appends one row to runs/results.jsonl (the analysis input) and
leaves the final .thy in runs/<arm>/<problem>/rep<k>/.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import io
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import agentlib
from harness.arms import ARMS, SOLVER_SOURCE_TOOLS, Arm
from harness.mcp_bridge import MCPBridge

HERE = Path(__file__).resolve().parent
DB_PATH = os.path.expanduser(os.environ.get("TRAJ_DB", str(HERE / "db.sql")))
RUNS_DIR = HERE / "runs"
DEFECTS_DIR = RUNS_DIR / "defects"
RESULTS = RUNS_DIR / "results.jsonl"
MODEL_CFG = HERE / "config" / "model.json"

# The Isabelle Pool Server checkout: its mcp_servers package and client are
# imported by the MCP subprocess (PYTHONPATH), its HTTP API is the backend.
IPS_ROOT = Path(os.environ.get("ISABELLE_POOL_SERVER", "~/GitHub/Isabelle-Pool-Server")).expanduser()
GYM_URL = os.environ.get("IB_GYM_URL", "http://localhost:8000")
MCP_PYTHON = os.environ.get("IPS_MCP_PYTHON", sys.executable)

TOOL_TIMEOUT_S = 330          # one MCP call; must exceed the fill patience
FILL_TIMEOUT_S = 30           # sledgehammer budget per `sorry`
FILL_MAX_TOTAL_S = 600        # per fill job
FILL_PATIENCE_S = 240         # the MCP returns `continuing` after this
ATTEMPT_TIMEOUT_S = 180       # multi_attempt / run_code per candidate
UNLIMITED_STEPS = 10_000_000


def _load_ib():
    spec = importlib.util.spec_from_file_location("ib", HERE / "harness" / "ib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ib = _load_ib()

# --------------------------------------------------------------------------- #
# Solver rule
# --------------------------------------------------------------------------- #

SOLVER_KW = re.compile(r"\b(metis|smt|meson|moura)\b")


def extract_solver_calls(text: str) -> set[str]:
    """Every metis/smt/meson/moura method call in `text`, whitespace-normalized:
    `by (metis foo bar)` -> 'metis foo bar'; a bare `by metis` -> 'metis'."""
    calls: set[str] = set()
    for m in SOLVER_KW.finditer(text):
        i = m.start()
        j = i - 1
        while j >= 0 and text[j] in " \t":
            j -= 1
        if j >= 0 and text[j] == "(":
            depth, k = 0, j
            while k < len(text):
                if text[k] == "(":
                    depth += 1
                elif text[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            frag = text[j + 1:k]
        else:
            nl = text.find("\n", i)
            frag = text[i:nl if nl >= 0 else len(text)]
            # a bare method may be followed by another command on the line
            frag = re.split(r"\s+(?:qed|next|then|from|using|have|show|thus|hence|also|finally|moreover|ultimately)\b", frag)[0]
        calls.add(re.sub(r"\s+", " ", frag).strip())
    return calls


def _strings_in(obj: Any) -> list[str]:
    """Every string inside a decoded JSON value (tool outputs are JSON; the
    Isabelle escapes inside them must be compared UNescaped)."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings_in(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings_in(v)]
    return []


def sanctioned_from_output(output: str) -> set[str]:
    try:
        decoded = json.loads(output)
    except (TypeError, ValueError):
        return extract_solver_calls(output)
    out: set[str] = set()
    for s in _strings_in(decoded):
        out |= extract_solver_calls(s)
    return out


# --------------------------------------------------------------------------- #
# Attempt state
# --------------------------------------------------------------------------- #

class _Attempt:
    """Everything one attempt's tools share."""

    def __init__(self, entry: dict, variant: str, arm: Arm, bench_dir: Path,
                 bridge: MCPBridge, enforce_solver_rule: bool):
        self.entry = entry
        self.variant = variant
        self.arm = arm
        self.bench_dir = bench_dir
        self.thy = bench_dir / f"{entry['name']}.thy"
        self.bridge = bridge
        self.enforce = enforce_solver_rule
        self.sanctioned: set[str] = set()
        # outcome (set only by the finishing tools)
        self.kind: str | None = None          # None | completed | disproved
        self.disproof_file = ""
        self.explanation = ""
        self.nudges = 0
        self.failed_completions = 0
        self.last_verify = ""
        # effort counters
        self.tool_calls: dict[str, int] = {}
        self.writes = 0
        self.rejected_writes = 0
        self.fills = 0
        self.fill_sorries_total = 0
        self.fill_sorries_proved = 0
        self.auto_fills = 0
        self.sledgehammer_calls = 0
        self.sledgehammer_found = 0
        self.tool_time_s = 0.0

    def count(self, name: str) -> None:
        self.tool_calls[name] = self.tool_calls.get(name, 0) + 1

    def mcp(self, name: str, args: dict, timeout: float = TOOL_TIMEOUT_S) -> str:
        t0 = time.time()
        out = self.bridge.call(name, {"file_path": str(self.thy), **args} if _takes_file_path(name) else args,
                               timeout=timeout)
        self.tool_time_s += time.time() - t0
        if name in SOLVER_SOURCE_TOOLS:
            self.sanctioned |= sanctioned_from_output(out)
        if name == "isabelle_sledgehammer":
            self.sledgehammer_calls += 1
            if '"found": true' in out or '"success": true' in out:
                self.sledgehammer_found += 1
        return out

    # -- diagnostics summary used after every write ------------------------ #
    def diagnostics(self) -> tuple[str, bool, bool]:
        """(text for the agent, has_errors, has_sorry)"""
        raw = self.mcp("isabelle_diagnostic_messages", {"severity": "error"})
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return raw, True, True
        msgs = d.get("messages") or []
        lines = []
        for m in msgs[:25]:
            lines.append(f"  line {m.get('line')}:{m.get('col')} [{m.get('kind')}] {str(m.get('text') or '').strip()[:600]}")
        has_sorry = bool(d.get("used_sorry")) or bool(re.search(r"\b(sorry|oops)\b", ib.strip_comments(self.thy.read_text(encoding='utf-8'))))
        if msgs:
            text = f"{len(msgs)} error(s):\n" + "\n".join(lines)
        else:
            text = "no errors"
            if d.get("proof_open"):
                text += "; a proof is still OPEN (unfinished)"
        text += f"; sorry present: {has_sorry}"
        return text, bool(msgs), has_sorry


_FILE_SCOPED = {"isabelle_diagnostic_messages", "isabelle_goal", "isabelle_proof_state",
                "isabelle_command_at_line", "isabelle_query", "isabelle_local_facts",
                "isabelle_global_facts", "isabelle_hover_info", "isabelle_definition",
                "isabelle_multi_attempt", "isabelle_sledgehammer", "isabelle_fill_sorries",
                "isabelle_fill_status", "isabelle_fill_cancel", "isabelle_source",
                "isabelle_open", "isabelle_close", "isabelle_sync"}


def _takes_file_path(name: str) -> bool:
    return name in _FILE_SCOPED


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

def _register_file_tools(reg: agentlib.ToolRegistry, at: _Attempt) -> None:
    def read_file() -> str:
        at.count("read_file")
        text = at.thy.read_text(encoding="utf-8")
        return "\n".join(f"{i+1:4d}| {ln}" for i, ln in enumerate(text.splitlines()))

    reg.register(
        "read_file",
        f"The current content of {at.thy.name}, with 1-based line numbers "
        "(the numbers are display only -- never include them in write_file).",
        {"type": "object", "properties": {}}, read_file)

    def write_file(content: str) -> str:
        at.count("write_file")
        content = re.sub(r"[\uD800-\uDFFF]", "", content)  # lone surrogates kill the prover
        if not content.strip():
            return "ERROR: write_file needs the COMPLETE new file content."
        if re.match(r"\s*\d+\|", content):
            return "ERROR: the content starts with line-number prefixes from read_file; send the bare file text."
        if at.enforce:
            bad = extract_solver_calls(ib.strip_comments(content)) - at.sanctioned
            if bad:
                at.rejected_writes += 1
                return ("REJECTED (file unchanged): the SOLVER RULE forbids writing metis/smt/"
                        "meson/moura calls yourself. Not sanctioned: "
                        + "; ".join(sorted(bad)[:5]) +
                        ". Only method calls returned by the sledgehammer/fill tools in this "
                        "run may be pasted (verbatim). Replace them with simple closers, "
                        "`sorry` (then let the filler try), or a sledgehammer result.")
        at.thy.write_text(content, encoding="utf-8")
        at.writes += 1
        diag, errors, has_sorry = at.diagnostics()
        out = f"wrote {len(content)} chars to {at.thy.name}.\nDiagnostics: {diag}"
        if at.arm.auto_fill and not errors and has_sorry:
            out += "\n\n" + _auto_fill(at)
        return out

    reg.register(
        "write_file",
        f"Replace the ENTIRE content of {at.thy.name} (always the complete file). "
        "The Isabelle session re-syncs and the error diagnostics come back with the "
        "result" + (", and -- when the file parses cleanly but still contains `sorry` -- the "
                    "server runs sledgehammer on every `sorry` and the proved ones are written "
                    "back into the file automatically (the result tells you what remains)."
                    if at.arm.auto_fill else "."),
        {"type": "object",
         "properties": {"content": {"type": "string", "description": "the complete new file content"}},
         "required": ["content"]},
        write_file)


def _collect_fill(at: _Attempt, first: str) -> dict:
    """Wait for a fill job that returned `continuing: true`."""
    try:
        d = json.loads(first)
    except (TypeError, ValueError):
        return {"raw": first}
    deadline = time.time() + FILL_MAX_TOTAL_S + 120
    while isinstance(d, dict) and d.get("continuing") and time.time() < deadline:
        time.sleep(5)
        raw = at.mcp("isabelle_fill_status", {})
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return {"raw": raw}
    return d


def _fill_summary(at: _Attempt, d: dict) -> str:
    if "raw" in d:
        return f"fill_sorries returned: {d['raw'][:1500]}"
    res = d.get("results") or []
    at.fill_sorries_total += len(res)
    proved = [r for r in res if r.get("outcome") == "proved" and r.get("method")]
    at.fill_sorries_proved += len(proved)
    lines = [f"fill_sorries: {len(proved)}/{len(res)} sorry(s) proved"
             + (f" (job error: {d.get('error')})" if d.get("error") else "")]
    for r in res:
        lines.append(f"  line {r.get('line')}: {r.get('outcome')}"
                     + (f" -> {r.get('method')}" if r.get("method") else "")
                     + (f" ({r.get('reason')})" if r.get("reason") else ""))
    return "\n".join(lines)


def _auto_fill(at: _Attempt) -> str:
    """The skeleton arm's automatic step: fill every sorry, write the patched
    text back, re-diagnose."""
    at.auto_fills += 1
    at.fills += 1
    at.count("auto:isabelle_fill_sorries")
    raw = at.mcp("isabelle_fill_sorries", {"timeout_s": FILL_TIMEOUT_S, "max_total_s": FILL_MAX_TOTAL_S,
                                          "patience_s": FILL_PATIENCE_S})
    d = _collect_fill(at, raw)
    summary = _fill_summary(at, d)
    patched = d.get("patched_text") if isinstance(d, dict) else None
    if isinstance(patched, str) and patched.strip() and d.get("filled"):
        at.sanctioned |= extract_solver_calls(patched)
        at.thy.write_text(patched, encoding="utf-8")
        at.writes += 1
        diag, _errors, has_sorry = at.diagnostics()
        summary += ("\n\nThe proved sorries were written back into the file "
                    f"(read_file to see it). Diagnostics now: {diag}")
        if not has_sorry:
            summary += "\nNo `sorry` remains -- check the diagnostics and call completed()."
    else:
        summary += "\nNothing was filled; the file is unchanged. Refine the skeleton (smaller steps, more `using` facts) and write again."
    return summary


def _register_mcp_tools(reg: agentlib.ToolRegistry, at: _Attempt, available: list[dict]) -> None:
    """Expose the arm's MCP tools, with file_path injected and dropped from
    the schema the model sees."""
    by_name = {t["name"]: t for t in available}
    missing = [n for n in at.arm.mcp_tools if n not in by_name]
    if missing:
        raise RuntimeError(f"the MCP server does not offer: {missing}")
    for name in at.arm.mcp_tools:
        t = by_name[name]
        schema = json.loads(json.dumps(t["parameters"]))
        props = schema.get("properties") or {}
        props.pop("file_path", None)
        schema["properties"] = props
        schema["required"] = [r for r in schema.get("required") or [] if r != "file_path"]
        desc = re.sub(r"\s+", " ", t["description"]).strip()
        desc = desc.replace("(file_path)", "()").replace("file_path, ", "").replace("file_path", "the problem file")
        if name == "isabelle_fill_sorries" and at.arm.auto_fill:
            desc = ("Re-run the server-side sledgehammer on every `sorry` of the file "
                    "(write_file already does this automatically; call this to retry with a "
                    f"larger timeout_s than the default {FILL_TIMEOUT_S}). " + desc)

        def make(n: str):
            def fn(**kwargs):
                at.count(n)
                if n == "isabelle_fill_sorries":
                    at.fills += 1
                    kwargs.setdefault("timeout_s", FILL_TIMEOUT_S)
                    kwargs.setdefault("max_total_s", FILL_MAX_TOTAL_S)
                    kwargs.setdefault("patience_s", FILL_PATIENCE_S)
                    raw = at.mcp(n, kwargs)
                    d = _collect_fill(at, raw)
                    if "raw" in d:
                        return d["raw"]
                    summary = _fill_summary(at, d)
                    patched = d.get("patched_text")
                    if isinstance(patched, str) and d.get("filled"):
                        at.sanctioned |= extract_solver_calls(patched)
                        return summary + "\n\npatched_text (write it to the file with write_file):\n" + patched
                    return summary
                if n == "isabelle_fill_status":
                    raw = at.mcp(n, kwargs)
                    d = _collect_fill(at, raw)
                    if "raw" in d:
                        return d["raw"]
                    patched = d.get("patched_text")
                    if isinstance(patched, str) and d.get("filled"):
                        at.sanctioned |= extract_solver_calls(patched)
                    return _fill_summary(at, d) + ("\n\npatched_text:\n" + patched if patched and d.get("filled") else "")
                if n == "isabelle_sledgehammer":
                    kwargs.setdefault("timeout_s", 60)
                    kwargs["timeout_s"] = min(int(kwargs["timeout_s"]), TOOL_TIMEOUT_S - 30)
                return at.mcp(n, kwargs)
            return fn

        reg.register(name, desc, schema, make(name))


def _register_finishing_tools(reg: agentlib.ToolRegistry, at: _Attempt) -> None:
    def completed() -> str:
        at.count("completed")
        text = at.thy.read_text(encoding="utf-8")
        ok, report = ib.verify_text(text, at.entry, at.variant, gym_url=GYM_URL)
        at.last_verify = report
        if ok:
            at.kind = "completed"
            return (report + "\n\nVERIFY PASSED. The problem is SOLVED and you are DONE.\n"
                    "Write your final report as your next message -- the mathematical idea, "
                    "what you tried, what worked -- and then stop. Do not call any more tools.")
        at.failed_completions += 1
        return (report + "\n\nVERIFY FAILED. You are NOT done. The exact verifier output is "
                "above -- it names the precise reason. Fix what it reported and call "
                "completed() again. If instead you come to believe the goal is FALSE, prove "
                "that in Isabelle and call disproved().")

    reg.register(
        "completed",
        "Declare the proof finished. Runs the DEFINITIVE check: no sorry/oops, no "
        "escape hatch (axiomatization, ML, setup, declare [[...]], notation, ...), "
        "theory header and theorem statement byte-identical to the frozen ones "
        "(comments/whitespace aside), no helper definition shadowing a name of the "
        "statement, and the whole theory builds with `isabelle build`. If it passes you "
        "are done. If it fails you get the exact reason and must keep working -- a "
        "failed check is not an ending. Call it as often as you like.",
        {"type": "object", "properties": {}}, completed)

    def disproved(explanation: str, file: str = "DISPROOF.thy") -> str:
        at.count("disproved")
        name = os.path.basename(file or "DISPROOF.thy")
        path = at.bench_dir / name
        if not path.exists() or not path.read_text(encoding="utf-8", errors="replace").strip():
            return (f"No such (non-empty) file: {name}. The claim was NOT recorded and you are NOT "
                    "done. Use write_disproof(content) to write an Isabelle theory that derives "
                    "False from the theorem's hypotheses (or proves the negation of its "
                    "conclusion) with no sorry, then call disproved() again.")
        DEFECTS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, DEFECTS_DIR / f"{at.entry['name']}.DISPROOF.thy")
        (DEFECTS_DIR / f"{at.entry['name']}.claim.md").write_text(
            f"# Claimed disproof: {at.entry['name']}\n\nFiled by the solver ({at.arm.name}); NOT "
            f"machine-checked. Review by hand against the frozen statement.\n\n## Explanation\n\n"
            f"{explanation}\n", encoding="utf-8")
        at.kind = "disproved"
        at.disproof_file = str(path)
        at.explanation = explanation
        return ("Disproof claim recorded. It will be checked by a human, not by this harness. "
                "You are DONE. Write your final report -- the counterexample and where the "
                "formalization diverges from the informal problem -- and then stop.")

    reg.register(
        "disproved",
        "Declare that the goal as formalized is FALSE and that you have PROVEN so in "
        "Isabelle: a separate theory (default DISPROOF.thy, written with write_disproof) "
        "that derives False from the hypotheses, or proves the negation of the conclusion, "
        "with no sorry. NOT machine-checked -- reviewed by a human later -- so never reach "
        "for it to escape a hard proof.",
        {"type": "object",
         "properties": {"explanation": {"type": "string", "description": "the counterexample or contradiction, in ordinary mathematics, for a human reviewer"},
                        "file": {"type": "string", "description": "disproof file name (default DISPROOF.thy)"}},
         "required": ["explanation"]},
        disproved)

    def write_disproof(content: str) -> str:
        at.count("write_disproof")
        (at.bench_dir / "DISPROOF.thy").write_text(content, encoding="utf-8")
        ok, log = ib.build_check(content, {"name": ib.parse_header(content)[0] if content.strip().startswith(("theory", "(*")) else "DISPROOF",
                                           "field": at.entry["field"], "sessions": at.entry["sessions"]},
                                 gym_url=GYM_URL)
        return ("DISPROOF.thy written. Build: " + ("OK" if ok else "FAILED\n" + log[:3000]))

    reg.register(
        "write_disproof",
        "Write DISPROOF.thy (a complete theory: header, imports, a lemma deriving False "
        "from the frozen statement's hypotheses or proving the negation of its conclusion) "
        "and build it. Only for the rare defective formalization; see disproved().",
        {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
        write_disproof)


# --------------------------------------------------------------------------- #
# Prompt and nudge
# --------------------------------------------------------------------------- #

def _nudge(at: _Attempt) -> str:
    at.nudges += 1
    extra = ""
    if at.failed_completions:
        extra = (f"\n\nYou have called completed() and had it come back FAILED {at.failed_completions} "
                 "time(s). That is normal -- it is a checkpoint, not a verdict on you. Read the last "
                 "verifier output again and fix precisely what it named.")
    return (
        "You are not finished, so do not stop.\n\n"
        "A run ends in exactly one of two ways, and neither has happened yet:\n"
        "  (a) you call completed() and the verifier PASSES, or\n"
        "  (b) you prove in Isabelle that the goal is false and call disproved().\n\n"
        "Taking more turns is fine. Pick up where you left off: try another angle on the "
        "mathematics, look for different lemmas (find_theorems), break the goal into smaller "
        "`have` steps and prove them one at a time, or test a small case to sharpen your "
        "intuition." + extra + "\n\nContinue now, with a tool call."
    )


def _system_prompt(at: _Attempt) -> str:
    e = at.entry
    answer_block = ""
    if at.variant == "full" and e.get("has_solution"):
        answer_block = f"""
# This problem also asks for the ANSWER

`{e['solution_name']}` is defined as `undefined` at the top of the file. The
theorem is stated in terms of it, so you must supply the correct closed-form
answer there AND prove the theorem with it. Its TYPE is frozen -- change the
value, never the type. A wrong answer makes the theorem false and unprovable,
so work the mathematics out before you start proving.
"""
    informal = e.get("informal_statement") or "(none -- the formal statement is the problem)"
    source = {"minif2f": "miniF2F (competition problems: AMC, AIME, IMO, MATH)",
              "putnambench": "PutnamBench (William Lowell Putnam competition)",
              "imo2026": "IMO 2026 (the six problems, formal statements after AxiomMath/IMO2026)"}[e["source"]]
    targets = e.get("targets") or [e["theorem_name"]]
    if len(targets) > 1:
        task_block = f"""The file defines the objects of the problem and states {len(targets)} theorems
({', '.join(targets)}), each with proof `sorry`. ALL of them are the problem:
replace EVERY `sorry` with a real, complete Isar proof. The definitions and the
theorem statements are frozen -- do not edit, rename, move or restate them.
Helper lemmas anywhere between the frozen blocks are welcome (same rules: no
sorry, nothing that shadows a name used in the frozen text). Prove the
theorems in whichever order helps; an earlier target may be used in a later
proof once it is proved."""
    else:
        task_block = """The file contains a single theorem whose proof is `sorry`. Replace the `sorry`
with a real, complete Isar proof. Helper lemmas ABOVE the theorem are welcome
(same rules: no sorry, nothing that shadows a name used in the statement)."""
    fill_note = ""
    if at.arm.auto_fill:
        fill_note = """
# How sledgehammer reaches you in this run

There is no per-goal sledgehammer tool. Instead, every write_file whose text
has NO errors but still contains `sorry` is sent to the server, which runs
sledgehammer on EVERY `sorry` at once and writes the proved ones back into the
file; the write_file result tells you what it proved and which lines are still
`sorry`. So: state your proof as a skeleton of small, true `have` steps ending
in `sorry`, write it, and iterate on the survivors.
"""
    return f"""\
You are an autonomous Isabelle/HOL proof engineer working on {source}.

# Problem

Name: {e['name']}
File: {at.thy.name}   (the ONLY file you may edit, via write_file)
Imports: {', '.join(e['imports'])}
Tags: {', '.join(e.get('tags') or []) or '(untagged)'}

Informal statement:

{informal}

{task_block}
{answer_block}
# Your tools

- read_file() / write_file(content): the file. write_file takes the COMPLETE
  file and returns the prover's error diagnostics for it.
- Isabelle queries on the file (the prover re-syncs it from disk first):
  isabelle_diagnostic_messages, isabelle_goal(line), isabelle_proof_state,
  isabelle_query(command) for `thm`, `find_theorems`, `term`, `print_*` ...,
  isabelle_local_facts / isabelle_global_facts, isabelle_hover_info(line,
  column), isabelle_definition(line, column), isabelle_multi_attempt(line,
  candidates) to test alternative steps without touching the file,
  isabelle_run_code(chunk) for an independent snippet.
{at.arm.tool_notes}{fill_note}
- completed(): the DEFINITIVE check (details in its description). PASS = done.
- disproved() / write_disproof(): only for a formalization that is actually
  false -- see below. Rare.

# SOLVER RULE (enforced)

Never write `metis`, `smt`, `meson` or `moura` calls yourself. write_file
REJECTS a file containing such a call unless that exact call came out of a
sledgehammer / fill result in this run -- paste those verbatim. Everything
else (simp, auto, force, blast, linarith, arith, algebra, presburger, argo,
induction, cases, unfolding, rule applications, structured Isar) is yours.

# HOW THIS RUN ENDS

There are exactly TWO ways to finish, and you must reach one of them:

  (a) completed() returns PASS -- you proved the theorem; or
  (b) you prove in Isabelle that the goal is false and call disproved().

Nothing else ends the run. If you stop for any other reason -- out of ideas,
feeling stuck, believing you have done enough -- you will simply be told to
continue. Do not ration effort and do not wrap up early with a summary of
what you would have tried.

# If the goal is false

Rarely the formalization is defective and the goal as stated is FALSE: a
hypothesis dropped, a quantifier misplaced, integer division or `nat`
subtraction where the informal problem meant reals, an edge case the informal
problem excluded. A false goal is unprovable, so if the mathematics keeps
refusing to work out, settle the question instead of guessing: find the
counterexample, write DISPROOF.thy with write_disproof (it must build with no
sorry) and call disproved(explanation=...). That claim is reviewed by a human;
a disproof filed to escape a hard proof is worse than useless.

# Rules

- Edit ONLY {at.thy.name}, only through write_file.
- Do NOT change the theory header or the theorem statement -- not a binder,
  not an assumption, not the conclusion, not the theorem's name. completed()
  compares against a frozen copy.
- No sorry/oops, no axiomatization, no ML, no setup, no `declare [[...]]`,
  no notation/syntax/translations, no hide_*. Helper lemmas and definitions
  are fine if their names do not occur in the statement.
- Do not try to find the reference answer or solution on disk; there is no
  disk. Think about the mathematics.

# Strategy

{at.arm.strategy}
# Operating rules

- Work autonomously. Do not stop until completed() passes or you have filed a
  proven disproved(). Running out of ideas is a signal to try a different
  angle, not a stopping condition.
- Your trajectory is saved automatically. Write a final report only once a
  finishing tool has told you that you are done.
"""


# --------------------------------------------------------------------------- #
# Full transcript of an attempt
# --------------------------------------------------------------------------- #
# Two files per attempt in its bench dir. `transcript.jsonl` is the raw record:
# one line per model call (the exact request body -- system prompt, every
# message, the tool schemas -- and the assembled reply with reasoning_content,
# tool_calls, finish_reason, usage, timing) and one line per tool execution
# (arguments, result, timing), in the order they happened, written as they
# happen so a timeout or crash loses nothing. `transcript.md` is the same
# conversation rendered for reading, from the SQLite trajectory (every message
# once, in order, compactions marked) plus a per-call table from the jsonl.

class _Transcript:
    """The sink both agentlib hooks write to; appends and flushes per record."""

    def __init__(self, path: Path):
        self.path = path
        self.n = 0
        self.calls: list[dict] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def __call__(self, rec: dict) -> None:
        self.n += 1
        rec = {"n": self.n, **rec}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        if rec["kind"] == "chat":
            u = rec.get("usage") or {}
            self.calls.append({"n": self.n, "finish": rec.get("finish_reason"),
                               "prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens"),
                               "cached": u.get("cached_tokens"), "elapsed_s": rec.get("elapsed_s"),
                               "error": (rec.get("response") or {}).get("error")})


_FENCE = "~~~~"


def _fenced(s: object) -> str:
    text = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False, indent=1, default=str)
    return f"{_FENCE}\n{text}\n{_FENCE}\n"


def _render_transcript_md(rows: list[dict], calls: list[dict], header: dict) -> str:
    """Markdown of a whole attempt: header, per-call table, then every
    trajectory message in order. Nothing is truncated -- the point of the
    file is that everything the model saw and said is in it."""
    out = [f"# Transcript: {header.get('problem')} / {header.get('arm')} / rep{header.get('rep')}\n",
           "| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in header.items()), ""]
    if calls:
        out.append("## Model calls\n\n| call | finish | prompt | completion | cached | s | error |\n|---|---|---|---|---|---|---|")
        for c in calls:
            out.append(f"| {c['n']} | {c['finish']} | {c['prompt']} | {c['completion']} | {c['cached']} | "
                       f"{c['elapsed_s']} | {(c['error'] or '')[:80]} |")
        out.append("")
    step = 0
    for i, m in enumerate(rows):
        role = m.get("role")
        if role == "system":
            out.append(f"## [{i}] system prompt\n" + _fenced(m.get("content")))
        elif role == "user":
            out.append(f"## [{i}] user\n" + _fenced(m.get("content")))
        elif role == "assistant":
            step += 1
            out.append(f"## [{i}] assistant (turn {step})")
            if m.get("error"):
                out.append("**error:** " + _fenced(m["error"]))
            if m.get("reasoning_content"):
                out.append("### reasoning\n" + _fenced(m["reasoning_content"]))
            if m.get("content"):
                out.append("### content\n" + _fenced(m["content"]))
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args = fn.get("arguments", "")
                try:
                    args = json.dumps(json.loads(args), ensure_ascii=False, indent=1)
                except Exception:  # noqa: BLE001
                    pass
                out.append(f"### tool call `{fn.get('name')}` ({tc.get('id')})\n" + _fenced(args))
        elif role == "tool":
            out.append(f"## [{i}] tool result `{m.get('name')}` ({m.get('tool_call_id')})\n" + _fenced(m.get("content")))
        elif role == "compaction":
            out.append(f"## [{i}] compaction (what the model sees from here on)\n" + _fenced(m.get("stats")))
        else:
            out.append(f"## [{i}] {role}\n" + _fenced(m))
    return "\n".join(out) + "\n"


def _trajectory_rows(agent: "agentlib.Agent", agent_name: str) -> list[dict]:
    """All messages of this attempt's trajectory, found by its unique agent
    name (the result object is missing after a timeout)."""
    cur = agent.store._conn.execute(
        "SELECT payload FROM messages WHERE trajectory_id = "
        "(SELECT id FROM trajectories WHERE agent_name=? ORDER BY created_at DESC LIMIT 1) ORDER BY seq ASC",
        (agent_name,))
    return [json.loads(r[0]) for r in cur.fetchall()]


# --------------------------------------------------------------------------- #
# One attempt
# --------------------------------------------------------------------------- #

class _Timeout(BaseException):
    """BaseException on purpose: agentlib wraps every tool call in
    `except Exception` and would otherwise swallow an alarm that fires while a
    tool (a long fill job, a build) is running, turning the wall-clock cap
    into a tool error string and letting the run continue."""


def _mcp_command() -> tuple[list[str], dict[str, str]]:
    env = {
        "PYTHONPATH": str(IPS_ROOT),
        "ISABELLE_MCP_LSP_GYM_URL": GYM_URL,
        "ISABELLE_MCP_LSP_TRANSPORT": "stdio",
        "ISABELLE_MCP_LSP_FILL_TIMEOUT_S": str(FILL_TIMEOUT_S),
        "ISABELLE_MCP_LSP_FILL_MAX_TOTAL_S": str(FILL_MAX_TOTAL_S),
        "ISABELLE_MCP_LSP_FILL_PATIENCE_S": str(FILL_PATIENCE_S),
        "ISABELLE_MCP_LSP_ATTEMPT_TIMEOUT": str(ATTEMPT_TIMEOUT_S),
        "ISABELLE_MCP_LSP_CLOSE_DESTROYS": "true",
        # start the file session on the heap its imports name (IPS patch; the
        # server must have that heap built) instead of loading from source
        "ISABELLE_MCP_LSP_FIELD_FROM_IMPORTS": "true",
        "PYTHONUTF8": "1",
    }
    return [MCP_PYTHON, "-m", "mcp_servers.lsp.app"], env


OPEN_RETRIES = 8
OPEN_RETRY_S = 60.0


def _open_with_retries(bridge: MCPBridge, thy: Path) -> str:
    """isabelle_open, waiting out the server's memory gate. The gate answers a
    JSON {"error": "memory_pressure", ..., "retry_after_s": N} (not an MCP
    error), which the first smoke run took for success -- the agent then ran
    25 steps against a file that was never bound. Setup, not agent time."""
    last = ""
    for attempt in range(OPEN_RETRIES):
        out = bridge.call("isabelle_open", {"file_path": str(thy)}, timeout=900)
        if out.startswith("MCP tool error"):
            raise RuntimeError(f"isabelle_open failed: {out[:400]}")
        try:
            d = json.loads(out)
        except (TypeError, ValueError):
            d = {}
        err = d.get("error") if isinstance(d, dict) else None
        if not err:
            return out
        last = out
        if err in ("memory_pressure", "pool_full", "gateway_unavailable"):
            wait = float(d.get("retry_after_s") or OPEN_RETRY_S)
            print(f"[harness] isabelle_open refused ({err}); retry {attempt+1}/{OPEN_RETRIES} in {wait:.0f}s", flush=True)
            time.sleep(min(wait, 300))
            continue
        raise RuntimeError(f"isabelle_open failed: {out[:400]}")
    raise RuntimeError(f"isabelle_open refused {OPEN_RETRIES} times: {last[:300]}")


def _solve_one(problem: str, arm_name: str, variant: str, rep: int, args) -> str:
    man = ib.load_manifest()
    if problem not in man:
        print(f"[harness] ERROR: unknown problem {problem}")
        return "failed"
    entry = man[problem]
    arm = ARMS[arm_name]

    bench_dir = Path(args.runs_dir) / arm_name / (problem + ("-full" if variant == "full" else "")) / f"rep{rep}"
    if bench_dir.exists():
        shutil.rmtree(bench_dir)
    ib.cmd_stage(SimpleNamespace(problem=problem, dest=str(bench_dir), variant=variant, force=True))

    print(f"[harness] bench_dir={bench_dir}")
    print(f"[harness] problem={problem} arm={arm_name} variant={variant} rep={rep}")
    print(f"[harness] max_steps={args.max_steps} timeout={args.timeout}s db={args.db}", flush=True)

    cfg = agentlib.load_config(args.model_cfg)
    print(f"[harness] model: {cfg.model} @ {cfg.host}", flush=True)

    cmd, env = _mcp_command()
    started = _dt.datetime.now(_dt.timezone.utc)
    t0 = time.time()
    usage_mark = len(agentlib.USAGE_LOG)
    result = None
    timed_out = False
    setup_error: str | None = None
    at: _Attempt | None = None
    try:
        with MCPBridge(cmd, env, cwd=str(IPS_ROOT), startup_timeout=120) as bridge:
            at = _Attempt(entry, variant, arm, bench_dir, bridge, not args.no_enforce_solver_rule)
            # open + warm the file session (the first acquire for an import set
            # may build a heap -- that is setup, not agent time)
            opened = _open_with_retries(bridge, at.thy)
            print(f"[harness] opened: {opened[:200]}", flush=True)
            available = bridge.list_tools()

            reg = agentlib.ToolRegistry()
            _register_file_tools(reg, at)
            _register_mcp_tools(reg, at, available)
            _register_finishing_tools(reg, at)
            agent_name = f"isa-{arm_name}-{problem}-rep{rep}"
            agent = agentlib.Agent(cfg, reg, db_path=args.db, agent_name=agent_name)
            transcript = _Transcript(bench_dir / "transcript.jsonl")
            agentlib.CHAT_SINK = transcript
            agentlib.TOOL_SINK = transcript

            user_input = (
                f"Solve the problem '{problem}' ({entry['source']}): replace every `sorry` in "
                f"{at.thy.name} with a complete Isar proof, then call completed(). The run "
                f"ends only when completed() reports PASS, or -- in the rare case where the "
                f"formalized goal is false -- when you have proven that and called disproved()."
            )

            def should_continue(assistant_msg, step_idx):
                if at.kind is not None:
                    return None
                return _nudge(at)

            def _alarm(signum, frame):
                raise _Timeout()

            if args.timeout:
                signal.signal(signal.SIGALRM, _alarm)
                signal.alarm(args.timeout)
            max_steps = args.max_steps if args.max_steps > 0 else UNLIMITED_STEPS
            t0 = time.time()
            try:
                result = agent.run(user_input, system_prompt=_system_prompt(at), max_steps=max_steps,
                                   connect_timeout=10.0, read_timeout=600.0, llm_retries=3,
                                   should_continue=should_continue)
            except _Timeout:  # noqa: B030 - deliberate BaseException
                timed_out = True
                print(f"[harness] TIMEOUT after {args.timeout}s", flush=True)
            finally:
                if args.timeout:
                    signal.alarm(0)
                agentlib.CHAT_SINK = None
                agentlib.TOOL_SINK = None
            try:
                md = _render_transcript_md(
                    _trajectory_rows(agent, agent_name), transcript.calls,
                    {"problem": problem, "arm": arm_name, "rep": rep, "variant": variant, "model": cfg.model,
                     "started": started.isoformat(), "finish_reason": getattr(result, "finish_reason", "timeout"),
                     "steps": getattr(result, "num_steps", None)})
                (bench_dir / "transcript.md").write_text(md, encoding="utf-8")
            except Exception as e:                       # noqa: BLE001
                print(f"[harness] transcript.md not written: {type(e).__name__}: {e}", flush=True)
            compactions = agent.store._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE trajectory_id=? AND role='compaction'",
                (result.trajectory_id if result else "",)).fetchone()[0]
            agent.close()
            try:
                bridge.call("isabelle_close", {"file_path": str(at.thy), "destroy": True}, timeout=60)
            except Exception:                            # noqa: BLE001
                pass
    except Exception as e:                               # noqa: BLE001
        setup_error = f"{type(e).__name__}: {e}"
        compactions = 0
        print(f"[harness] ERROR: {setup_error}", flush=True)
    elapsed = time.time() - t0

    # The definitive check is OURS, re-run here, not the agent's claim.
    text = (bench_dir / f"{problem}.thy").read_text(encoding="utf-8") if (bench_dir / f"{problem}.thy").exists() else ""
    passed, report = (ib.verify_text(text, entry, variant, gym_url=GYM_URL) if text else (False, "no file"))
    reason = next((l.strip() for l in reversed(report.splitlines()) if l.strip().startswith("FAIL [")), "")
    if not reason and not passed:
        reason = (setup_error or report.strip().splitlines()[-1] if report.strip() else "")

    usage_rows = agentlib.USAGE_LOG[usage_mark:]
    tokens = {
        "prompt": sum(u["prompt_tokens"] for u in usage_rows),
        "completion": sum(u["completion_tokens"] for u in usage_rows),
        "cached": sum(u["cached_tokens"] for u in usage_rows),
        "calls": len(usage_rows),
    }

    print("=" * 70)
    print(f"problem        : {problem} ({variant}) arm={arm_name} rep={rep}")
    if result is not None:
        print(f"finish_reason  : {result.finish_reason}")
        print(f"num_steps      : {result.num_steps}")
        print(f"trajectory_id  : {result.trajectory_id}")
    print(f"elapsed        : {elapsed:.0f}s")
    print(f"passed         : {passed}")
    if at is not None:
        print(f"finishing tool : {at.kind or '(none called)'}")
        print(f"nudges         : {at.nudges}   failed completions: {at.failed_completions}")
        print(f"writes         : {at.writes} (rejected {at.rejected_writes})  fills: {at.fills} "
              f"({at.fill_sorries_proved}/{at.fill_sorries_total} sorries)  sledgehammer: "
              f"{at.sledgehammer_found}/{at.sledgehammer_calls}")
    print(f"tokens         : {tokens}")
    if not passed:
        print(f"verify said    : {reason or '(no output)'}")
    print("=" * 70, flush=True)

    status = ("solved" if passed else
              "disproved" if (at is not None and at.kind == "disproved" and not timed_out) else
              "timeout" if timed_out else "failed")
    row = {
        "problem": problem, "source": entry["source"], "category": entry.get("category"),
        "arm": arm_name, "variant": variant, "rep": rep, "model": cfg.model,
        "solved": passed, "status": status,
        "finish_reason": getattr(result, "finish_reason", None), "timed_out": timed_out,
        "steps": getattr(result, "num_steps", None), "trajectory_id": getattr(result, "trajectory_id", None),
        "elapsed_s": round(elapsed, 1), "started": started.isoformat(), "ended": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "verify": reason if not passed else "PASS",
        "setup_error": setup_error, "compactions": compactions,
        "tokens": tokens,
        "bench_dir": str(bench_dir),
        "transcript": str(bench_dir / "transcript.jsonl") if (bench_dir / "transcript.jsonl").exists() else None,
    }
    if at is not None:
        row.update({
            "finishing_tool": at.kind, "nudges": at.nudges, "failed_completions": at.failed_completions,
            "tool_calls": at.tool_calls, "writes": at.writes, "rejected_writes": at.rejected_writes,
            "fills": at.fills, "auto_fills": at.auto_fills,
            "fill_sorries_total": at.fill_sorries_total, "fill_sorries_proved": at.fill_sorries_proved,
            "sledgehammer_calls": at.sledgehammer_calls, "sledgehammer_found": at.sledgehammer_found,
            "tool_time_s": round(at.tool_time_s, 1),
        })
    results_path = Path(args.results)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _solve_one.last_steps = getattr(result, "num_steps", None)
    _solve_one.last_note = f"{elapsed:.0f}s | {getattr(result, 'finish_reason', '') or ''} | {reason[:70]}"
    return status


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--problem", help="solve this problem (skip the queue)")
    p.add_argument("--arm", nargs="*", default=None,
                   help=f"arm(s): {', '.join(ARMS)}. With --problem: one arm (default plain); "
                        "with the queue: only claim rows of these arms")
    p.add_argument("--variant", choices=["wsolution", "full"], default=None)
    p.add_argument("--rep", type=int, default=0, help="repeat index for --problem")
    p.add_argument("--loop", type=int, default=1, help="queue rows to take (0 = until it drains)")
    p.add_argument("--owner", default=None)
    p.add_argument("--runs-dir", default=str(RUNS_DIR))
    p.add_argument("--results", default=str(RESULTS))
    p.add_argument("--max-steps", type=int, default=150, help="0 = unlimited")
    p.add_argument("--timeout", type=int, default=3600, help="wall-clock seconds per attempt (0 = none)")
    p.add_argument("--queue", default=None)
    p.add_argument("--model-cfg", default=str(MODEL_CFG))
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--no-enforce-solver-rule", action="store_true")
    args = p.parse_args()

    if args.queue:
        os.environ["IB_QUEUE"] = os.path.abspath(args.queue)
    if not IPS_ROOT.exists():
        print(f"[harness] ERROR: Isabelle-Pool-Server checkout not found at {IPS_ROOT} (set ISABELLE_POOL_SERVER)")
        return 2
    if not Path(args.model_cfg).exists():
        print(f"[harness] ERROR: model config {args.model_cfg} not found (copy config/model.example.json)")
        return 2

    owner = args.owner or f"{socket.gethostname()}-{os.getpid()}"

    if args.problem:
        arm = (args.arm or ["plain"])[0]
        if arm not in ARMS:
            print(f"[harness] ERROR: unknown arm {arm}; choose from {list(ARMS)}")
            return 2
        status = _solve_one(args.problem, arm, args.variant or "wsolution", args.rep, args)
        return 0 if status == "solved" else 1

    n_done = ok = 0
    while args.loop == 0 or n_done < args.loop:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ib.cmd_claim(SimpleNamespace(owner=owner, pid=os.getpid(), arm=args.arm, problem=None))
        if rc != 0:
            print("[harness] queue drained; nothing left to claim")
            break
        problem, arm, variant, rep = buf.getvalue().strip().split("\t")
        rep = int(rep)
        try:
            status = _solve_one(problem, arm, variant, rep, args)
        except KeyboardInterrupt:
            ib.cmd_release(SimpleNamespace(problem=problem, arm=arm, rep=rep, variant=variant,
                                           status="todo", steps=None, note="interrupted"))
            raise
        except Exception as e:                           # noqa: BLE001
            ib.cmd_release(SimpleNamespace(problem=problem, arm=arm, rep=rep, variant=variant,
                                           status="failed", steps=None, note=f"harness error: {e}"[:120]))
            raise
        ib.cmd_release(SimpleNamespace(problem=problem, arm=arm, rep=rep, variant=variant, status=status,
                                       steps=getattr(_solve_one, "last_steps", None),
                                       note=getattr(_solve_one, "last_note", "")))
        n_done += 1
        ok += (status == "solved")
    if n_done:
        print(f"[harness] {ok}/{n_done} solved this worker")
    return 0 if (n_done and ok == n_done) else 1


if __name__ == "__main__":
    sys.exit(main())
