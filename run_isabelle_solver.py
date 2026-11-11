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
  * no step budget, as upstream (the harness owns the stopping rule); a wall-clock
    cap only: --timeout 14400 s (4 h). --max-steps N caps turns if you want it.

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
import hashlib
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

import httpx

import agentlib
from harness import leaves
from harness.arms import ARMS, FILL_TOOLS, SOLVER_SOURCE_TOOLS, Arm
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

FILL_TIMEOUT_S = 30           # sledgehammer budget per `sorry`
FILL_MAX_TOTAL_S = 600        # per fill job (floor; the automatic round scales with the sorry count)
FILL_MAX_TOTAL_CEIL_S = 1800  # ceiling of the scaled automatic round
FILL_S_PER_SORRY = 10         # Q1 forced run 2026-11-05: 223 sorries in 600 s left 94 untouched


def auto_fill_budget(n_sorries: int) -> int:
    """Job cap of the automatic fill round: 10 s per sorry, between the
    600 s floor and the 1800 s ceiling. The first forced Q1 round proved 127
    of 223 sorries and hit the 600 s cap with 94 skipped; the model then had
    to notice and re-run the explicit tool with a bigger budget by itself."""
    return max(FILL_MAX_TOTAL_S, min(FILL_MAX_TOTAL_CEIL_S, FILL_S_PER_SORRY * n_sorries))
FILL_PATIENCE_S = 240         # the MCP returns `continuing` after this
FILL_MIN_REMAINING_S = 180    # no fill round starts with less than this left on the wall clock
# The staged filler (IPS 2026-11-10): cheap closers before the hammer, a nitpick
# verdict on what try0 cannot close, a structured retry, intro-splitting with a
# second pass, and sibling sessions. Env-tunable so a pass can switch stages off.
FILL_TRY0_S = int(os.environ.get("IB_FILL_TRY0_S", "5"))
FILL_NITPICK_S = int(os.environ.get("IB_FILL_NITPICK_S", "10"))
FILL_ISAR = os.environ.get("IB_FILL_ISAR", "1") == "1"
FILL_SPLIT = os.environ.get("IB_FILL_SPLIT", "1") == "1"
FILL_PARALLEL = int(os.environ.get("IB_FILL_PARALLEL", "2"))


def fill_stage_options() -> dict:
    return {"try0_s": FILL_TRY0_S, "nitpick_s": FILL_NITPICK_S, "isar": FILL_ISAR,
            "split": FILL_SPLIT, "parallel": FILL_PARALLEL}
GIVE_UP_STOPS = 3             # consecutive turns without a tool call that end the attempt
SLEDGEHAMMER_MAX_S = 90       # cap on the model's per-goal sledgehammer timeout_s
ATTEMPT_TIMEOUT_S = 180       # multi_attempt / run_code per candidate; also the cap on the model's own `timeout`
# The server's fill_sorries schema (fill_models.py) rejects values outside
# these ranges with a 422 the model cannot act on (rep 1: eight such calls,
# try0_s 90..120 and timeout_s 600); the wrapper clamps and says so instead.
FILL_CAPS = {"timeout_s": (1, 300), "try0_s": (0, 60), "nitpick_s": (0, 120),
             "max_total_s": (60, 3600), "parallel": (1, FILL_PARALLEL)}
# Wall budget for the session's check of the whole file after a write. The
# MCP default (120 s) was too short for an 850-line file; isabelle-humanize
# needed 600 s for the IMO P1 theory class. A check that expires is reported
# as such, naming the running line (see _Attempt.diagnostics).
LOAD_TIMEOUT_S = int(os.environ.get("IB_LOAD_TIMEOUT", "600"))
# One MCP call through the bridge. Must exceed the fill patience and the load
# budget plus a diagnostics call, otherwise the bridge cuts the call before the
# server's partial report arrives and the model sees a generic timeout instead
# of the line that is stuck.
TOOL_TIMEOUT_S = max(330, LOAD_TIMEOUT_S + 120)
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
        # skeleton_forced (leaf rule): the leaves the filler wrote, keyed by
        # statement and enclosing goals (harness/leaves.py), seeded with the
        # staged file's own proofs; write_file accepts no other method text.
        self.filler_keys: set[leaves.Key] = (
            leaves.leaf_keys(self.thy.read_text(encoding="utf-8"))
            if arm.filler_only and self.thy.exists() else set())
        self.leaf_rejections = 0
        self.frozen_rejections = 0   # writes refused for touching the frozen header/statements
        # give-up detection (pass 1, 2026-11-08/09: plain P3 and P6 stopped trying and
        # were nudged 489 and 425 times until the wall; see docs/pass1-analysis-2026-11-10.md)
        self.consecutive_stops = 0
        self.gave_up = False
        self.deadline: float | None = None   # wall-clock end of the attempt, when a timeout is set
        # outcome (set only by the finishing tools)
        self.kind: str | None = None          # None | completed | disproved
        self.disproof_file = ""
        self.explanation = ""
        self.nudges = 0
        self.failed_completions = 0
        self.verifier_unavailable = 0
        self.last_verify = ""
        self.disproof_build_ok: bool | None = None   # last write_disproof build (F7)
        # effort counters
        self.tool_calls: dict[str, int] = {}
        self.writes = 0
        self.rejected_writes = 0
        self.fills = 0
        self.fill_sorries_total = 0
        self.fill_sorries_proved = 0
        self.fill_stages: dict[str, int] = {}     # how the filler settled sorries: try0 / sledgehammer / isar / split / nitpick(false)
        self.fill_false = 0                       # statements nitpick found false
        self.auto_fills = 0
        self.sledgehammer_calls = 0
        self.sledgehammer_found = 0
        self.tool_time_s = 0.0
        self.busy_retries = 0       # server refusals (pool full / memory) retried by the harness
        self.releases = 0           # isabelle_release_idle calls the harness made for the model

    def count(self, name: str) -> None:
        self.tool_calls[name] = self.tool_calls.get(name, 0) + 1
        self.consecutive_stops = 0            # a tool call is work; the give-up counter restarts

    def remaining_s(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.time()

    def note_filler_text(self, raw: str) -> None:
        """Leaf rule: every leaf in a text the filler returned is allowed from
        now on (under its statement and enclosing goals)."""
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return
        pt = d.get("patched_text") if isinstance(d, dict) else None
        if isinstance(pt, str) and pt.strip():
            self.filler_keys |= leaves.leaf_keys(pt)

    def mcp(self, name: str, args: dict, timeout: float = TOOL_TIMEOUT_S) -> str:
        """One MCP call with the session housekeeping the model cannot do.
        The MCP's memory/lifecycle tools (isabelle_release_idle, close, list,
        memory_status) are hidden from the model on purpose, but the server's
        refusals name them in their advice -- and a model that cannot call
        them wastes turns reasoning about it (seen on the first P1 run). So a
        capacity refusal (pool_full, memory_pressure, scratch exhausted, ...)
        is handled here: free the idle scratch sessions this MCP holds, wait
        the server's retry_after, call again, up to _BUSY_MAX_TRIES; and
        whatever comes back has the hidden tool names replaced by what the
        model should actually do (retry)."""
        t0 = time.time()
        full_args = {"file_path": str(self.thy), **args} if _takes_file_path(name) else args
        for attempt in range(_BUSY_MAX_TRIES):
            out = self.bridge.call(name, full_args, timeout=timeout)
            kind, retry = _busy_error(out)
            if kind is None or name == "isabelle_release_idle" or attempt == _BUSY_MAX_TRIES - 1:
                break
            self.busy_retries += 1
            try:
                rel = self.bridge.call("isabelle_release_idle", {"max_idle_s": 0}, timeout=60)
                self.releases += 1
                print(f"[harness] {name}: {kind}; released idle sessions ({rel[:100]}); retry in {retry:.0f}s",
                      flush=True)
            except Exception as e:                       # noqa: BLE001
                print(f"[harness] {name}: {kind}; release_idle failed: {e}; retry in {retry:.0f}s", flush=True)
            time.sleep(min(max(retry, 2.0), 30.0))
        out = _strip_hidden_advice(out)
        self.tool_time_s += time.time() - t0
        # The prover side of the conversation: every MCP call, including the
        # ones the harness makes inside write_file/completed (sync reports,
        # diagnostics, fill jobs), goes into the attempt's transcript too.
        agentlib._emit(agentlib.TOOL_SINK, {
            "kind": "mcp", "name": name, "arguments": json.dumps(args, ensure_ascii=False),
            "result": out, "elapsed_s": round(time.time() - t0, 3), "retries": attempt})
        if name in SOLVER_SOURCE_TOOLS:
            self.sanctioned |= sanctioned_from_output(out)
        if name in FILL_TOOLS and self.arm.filler_only:
            self.note_filler_text(out)
        if name == "isabelle_sledgehammer":
            self.sledgehammer_calls += 1
            if '"found": true' in out or '"success": true' in out:
                self.sledgehammer_found += 1
        return out

    # -- diagnostics summary used after every write ------------------------ #
    def stuck_line(self) -> int | None:
        """The line the prover was still running when the last full-file check
        hit its wall budget (LOAD_TIMEOUT_S), or None if the check finished.
        The session checks the file under a budget and hands back a PARTIAL
        report when it expires; a step still running at that point has no
        message, so the error list alone looks clean. Q1 rerun, 2026-11-05: a
        divergent metis made every check expire, the harness said "no errors",
        the model called completed() and the build hung on the same step."""
        raw = self.mcp("isabelle_sync", {})
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if d.get("success"):
            return None
        # The MCP computes the field as `timed_out and commands and next(...)`,
        # so a check that merely FAILED (no timeout) hands back False, and
        # bool is an int in Python: the Q1 plain run (2026-11-05) told the
        # model "still running line False" after a 5 s check with 22 errors.
        # Only a positive integer names a running line.
        sl = d.get("stuck_line")
        if isinstance(sl, int) and not isinstance(sl, bool) and sl > 0:
            return sl
        m = re.search(r"still running at line (\d+)", str(d.get("error") or ""))
        return int(m.group(1)) if m else None

    def line_text(self, n: int) -> str:
        try:
            return self.thy.read_text(encoding="utf-8").splitlines()[n - 1].strip()[:200]
        except (IndexError, OSError):
            return ""

    def diagnostics(self) -> tuple[str, bool, bool]:
        """(text for the agent, has_errors, has_sorry)"""
        stuck = self.stuck_line()
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
        if stuck is not None:
            text = (f"CHECK TIMED OUT: the prover could not finish checking the file within "
                    f"{LOAD_TIMEOUT_S}s -- it was still running line {stuck}: `{self.line_text(stuck)}`. "
                    "A step that runs this long will not build either: treat it as FAILED and "
                    "replace it (a method sledgehammer found for one goal need not terminate on "
                    "another). Commands after it were not checked.")
            if msgs:
                text += f"\nAlso {len(msgs)} error(s) in what was checked:\n" + "\n".join(lines)
        elif msgs:
            text = f"{len(msgs)} error(s):\n" + "\n".join(lines)
        else:
            text = "no errors"
            if d.get("proof_open"):
                text += "; a proof is still OPEN (unfinished)"
        text += f"; sorry present: {has_sorry}"
        return text, bool(msgs) or stuck is not None, has_sorry


# Server-capacity refusals the harness absorbs (see _Attempt.mcp). The error
# names are the MCP's (mcp_servers/common/memory_advice.translate_http_error);
# "scratch pool exhausted" is the MCP's own RuntimeError text.
_BUSY_ERRORS = ("pool_full", "memory_pressure", "server_recovering", "busy")
_BUSY_MAX_TRIES = 3


def _busy_error(out: str) -> tuple[str | None, float]:
    """(error kind, retry_after_s) when an MCP result is a capacity refusal,
    else (None, 0). Also catches multi_attempt answers whose every candidate
    was refused."""
    if not isinstance(out, str):
        return None, 0.0
    if "scratch pool exhausted" in out:
        return "scratch_exhausted", 10.0
    try:
        d = json.loads(out)
    except (TypeError, ValueError):
        return None, 0.0
    if not isinstance(d, dict):
        return None, 0.0
    err = d.get("error")
    if isinstance(err, str) and err in _BUSY_ERRORS:
        return err, float(d.get("retry_after_s") or 5)
    res = d.get("results")
    if isinstance(res, list) and res and all(isinstance(r, dict) and r.get("error") in _BUSY_ERRORS for r in res):
        return str(res[0].get("error")), float(res[0].get("retry_after_s") or 5)
    return None, 0.0


# The MCP words its advice with its own tool names; these four are hidden from
# the model (harness business), so the text is rewritten to the action the
# model can take. Applied to every MCP result (MEMORY REMINDERs ride on
# ordinary results too).
_HIDDEN_ADVICE = [
    (re.compile(r"call isabelle_release_idle\(\)"), "wait (the harness has already freed the idle sessions)"),
    (re.compile(r"isabelle_release_idle\(\)"), "the harness (it frees idle sessions for you automatically)"),
    (re.compile(r"isabelle_release_idle"), "the harness's automatic session release"),
    (re.compile(r"isabelle_close\(file_path, destroy=true\)"), "do nothing (the harness manages the file session)"),
    (re.compile(r"\(isabelle_memory_status\(\) shows the numbers\)"), "(the harness logs the numbers)"),
    (re.compile(r"isabelle_memory_status\(\)|isabelle_list_sessions\(\)"), "the harness log"),
]


def _strip_hidden_advice(out: str) -> str:
    if not isinstance(out, str) or "isabelle_" not in out:
        return out
    for pat, repl in _HIDDEN_ADVICE:
        out = pat.sub(repl, out)
    return out


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
    def read_file(**kwargs) -> str:
        # Seen on the first P1 run: the model called read_file with a `content`
        # argument, twice -- a 9k-token file each time, meant for write_file.
        # The TypeError that came back threw both writes away. Route it.
        if isinstance(kwargs.get("content"), str):
            return ("(note: read_file takes no arguments; your `content` was treated as "
                    "write_file(content))\n" + write_file(kwargs["content"]))
        if kwargs:
            return f"ERROR: read_file takes no arguments (got {sorted(kwargs)}); use write_file(content) to write."
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
        if at.kind is not None:
            # DeepSeek batches tool calls; a write in the same turn as a
            # passing completed() would change the file after its verdict.
            return f"The run is over ({at.kind}): the file is frozen and this write was NOT applied."
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
        if at.arm.filler_only:
            # The leaf rule (harness/leaves.py): the model never closes a step
            # itself. Checked before the file changes, like the solver rule.
            bad = leaves.check(content, at.filler_keys)
            if bad:
                at.rejected_writes += 1
                at.leaf_rejections += 1
                return ("REJECTED (file unchanged): the LEAF RULE of this arm -- you never write a "
                        "closing proof method yourself; every leaf is `sorry` until the filler proves "
                        "it, and filler-proved lines are kept verbatim under the same statement. "
                        f"{len(bad)} offending line(s):\n" + leaves.summarize(bad) +
                        "\nPut `sorry` back on those steps and write again. If the filler already failed on a "
                        "step, writing the closer yourself is not the move: RESTATE the step so the filler "
                        "can -- split it into two or three smaller `have`s, give it the facts it needs with "
                        "`using`, or prove a helper lemma above the theorem and use it. Test a candidate "
                        "decomposition in scratch (isabelle_run_code / isabelle_multi_attempt) if unsure.")
        # The frozen parts (header, definition blocks, theorem statements) are
        # the verifier's rule; checking them only at completed() let the forced
        # P2 run (2026-11-09) spend its last two hours on a 15-line scratch file
        # with no theorem in it. Everything but the sorry check applies here.
        try:
            frozen = [f for f in ib.textual_checks(content, at.entry, at.variant)
                      if not f.startswith("file still contains sorry")]
        except Exception as e:                           # noqa: BLE001
            frozen = [f"cannot check the file: {type(e).__name__}: {e}"]
        if frozen:
            at.rejected_writes += 1
            at.frozen_rejections += 1
            return ("REJECTED (file unchanged): the frozen parts of the file are missing or changed -- "
                    + "; ".join(frozen[:6]) +
                    ". Keep the theory header, every definition block and every theorem statement "
                    "exactly as staged; add helper lemmas above the theorems and replace only the "
                    "proofs. Test scratch lemmas with isabelle_run_code, not in this file.")
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
                    if at.arm.auto_fill else ".")
        + (" LEAF RULE: a write carrying any closing method the filler did not produce for that "
           "statement (`by ...`, `.`, `..`, `apply`, `qed <method>`, `proof (auto)`) is REJECTED "
           "and the file stays unchanged; every leaf is `sorry` or a filler-written line kept verbatim."
           if at.arm.filler_only else ""),
        {"type": "object",
         "properties": {"content": {"type": "string", "description": "the complete new file content"}},
         "required": ["content"]},
        write_file)


def _collect_fill(at: _Attempt, first: str, max_total_s: int = FILL_MAX_TOTAL_S) -> dict:
    """Wait for a fill job that returned `continuing: true`: for the job's own
    budget (plus the server's grace), never past the attempt's wall. Rep 1
    (P3): a job asked for with max_total_s=3600 was waited for 720 s, then
    its snapshot was summarised as a verdict with the untried main statements
    `skipped`, while the job ran on. A job still running when the wait ends
    is cancelled (it would hold prover slots and collide with the next
    write's fill) and the summary says what was never tried."""
    try:
        d = json.loads(first)
    except (TypeError, ValueError):
        return {"raw": first}
    t0 = time.time()
    deadline = t0 + max_total_s + 120
    remaining = at.remaining_s()
    if remaining is not None:
        deadline = min(deadline, t0 + max(0.0, remaining - 60))
    while isinstance(d, dict) and d.get("continuing") and time.time() < deadline:
        time.sleep(5)
        raw = at.mcp("isabelle_fill_status", {})
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return {"raw": raw}
    if isinstance(d, dict) and d.get("continuing"):
        at.mcp("isabelle_fill_cancel", {})
        d["cut_after_s"] = round(time.time() - t0)
    return d


def _fill_summary(at: _Attempt, d: dict) -> str:
    if "raw" in d:
        return f"fill_sorries returned: {d['raw'][:1500]}"
    res = d.get("results") or []
    at.fill_sorries_total += len(res)
    proved = [r for r in res if r.get("outcome") == "proved" and r.get("method")]
    at.fill_sorries_proved += len(proved)
    for k, v in (d.get("stages") or {}).items():
        if k != "open":
            at.fill_stages[k] = at.fill_stages.get(k, 0) + int(v)
    false_rows = [r for r in res if r.get("outcome") == "false"]
    at.fill_false += len(false_rows)
    stages = d.get("stages") or {}
    pending = [r for r in res if r.get("outcome") == "pending"]
    lines = [f"fill_sorries: {len(proved)}/{len(res)} sorry(s) proved"
             + (f" [{', '.join(f'{k} {v}' for k, v in stages.items())}]" if stages else "")
             + (f" (job error: {d.get('error')})" if d.get("error") else "")]
    if d.get("cut_after_s") is not None:
        lines[0] += (f" -- the job was still running after {d['cut_after_s']}s and was CANCELLED; "
                     f"the {len(pending)} line(s) marked pending were never tried: split them into smaller "
                     "steps and write again")
    elif d.get("continuing"):
        lines[0] += (f" -- STILL RUNNING server-side: {len(pending)} line(s) not tried yet (pending); "
                     "call isabelle_fill_status() to collect the rest")
    if d.get("clamped"):
        lines[0] += f" (clamped to the server's ranges: {d['clamped']})"
    for r in res:
        method = r.get("method")
        head = f"  line {r.get('line')}: {r.get('outcome')}"
        if r.get("stage") and r.get("outcome") in ("proved", "split", "false"):
            head += f" [{r['stage']}]"
        if method:
            one = " ".join(str(method).split())
            head += f" -> {one if len(one) <= 160 else one[:157] + '...'}"
        if r.get("split"):
            head += f" (split into {r['split'].get('k')} leaves, {r['split'].get('proved')} proved)"
        elif r.get("reason"):
            head += f" ({r.get('reason')})"
        lines.append(head)
        if r.get("outcome") not in ("proved",) and r.get("goal"):
            lines.append(f"      goal: {str(r['goal'])[:200]}")
    open_rows = [r for r in res if r.get("outcome") not in ("proved", "false", "pending")]
    if open_rows and at.arm.filler_only:
        lines.append("  NEXT: the filler could not close the step(s) above AS STATED, and you may not write "
                     "their closers yourself. Restate them: split each into smaller `have`s (one fact per "
                     "step), add the facts they need with `using`/`unfolding`, state the intermediate "
                     "equality or bound explicitly, or prove a helper lemma above and use it. A split row "
                     "shows which leaves survived; refine those. Then write the file again.")
    if false_rows:
        lines.append("  WARNING: nitpick found a counterexample to the statement(s) at line(s) "
                     f"{[r.get('line') for r in false_rows]}: they are FALSE as written. Fix the statement "
                     "(a missing hypothesis, a wrong bound or quantifier); do not try to prove it. While a "
                     "false `sorry` stays in the file, other proofs may silently rest on it.")
    return "\n".join(lines)


def _auto_fill(at: _Attempt) -> str:
    """The skeleton arm's automatic step: fill every sorry, write the patched
    text back, re-diagnose."""
    at.auto_fills += 1
    at.fills += 1
    at.count("auto:isabelle_fill_sorries")
    n_sorries = len(re.findall(r"\bsorry\b", ib.strip_comments(at.thy.read_text(encoding="utf-8"))))
    budget = auto_fill_budget(n_sorries)
    remaining = at.remaining_s()
    if remaining is not None:
        # A fill job that outlives the attempt is wasted (forced P6, pass 1,
        # ended inside one); shrink it to what is left, or skip it.
        if remaining < FILL_MIN_REMAINING_S:
            return (f"fill_sorries skipped: only {remaining:.0f}s remain in this attempt, "
                    "not enough for a sledgehammer round.")
        budget = max(60, min(budget, int(remaining - 120)))
    raw = at.mcp("isabelle_fill_sorries", {"timeout_s": FILL_TIMEOUT_S, "max_total_s": budget,
                                          "patience_s": FILL_PATIENCE_S, **fill_stage_options()})
    d = _collect_fill(at, raw, budget)
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
        # The MCP's descriptions talk to an agent that has its memory and heap
        # tools; ours does not (the harness does that work), so drop the MEMORY
        # paragraph and rewrite any hidden tool name the way results are.
        desc = re.sub(r"\s*MEMORY:.*$", "", desc)
        desc = _strip_hidden_advice(desc)
        if name == "isabelle_run_code":
            # task_group / heap_session name heaps the model cannot see or
            # build; the imports decide the image (FIELD_FROM_IMPORTS).
            for k in ("task_group", "heap_session"):
                props.pop(k, None)
            schema["required"] = [r for r in schema["required"] if r not in ("task_group", "heap_session")]
            desc = re.sub(r"\s*heap_session runs it in that heap's import context\.", "", desc)
        if name == "isabelle_fill_sorries" and at.arm.auto_fill:
            desc = ("Re-run the server-side sledgehammer on every `sorry` of the file "
                    "(write_file already does this automatically with "
                    f"timeout_s={FILL_TIMEOUT_S} per sorry and a job cap of {FILL_S_PER_SORRY} s "
                    f"per sorry between {FILL_MAX_TOTAL_S} and {FILL_MAX_TOTAL_CEIL_S} s; call this to retry "
                    "the survivors with a larger timeout_s / max_total_s). Ranges, clamped silently: "
                    + ", ".join(f"{k} {lo}..{hi}" for k, (lo, hi) in FILL_CAPS.items()) + ". " + desc)
        if name in ("isabelle_run_code", "isabelle_multi_attempt"):
            desc += (f" `timeout` is capped at {ATTEMPT_TIMEOUT_S} s: a step that needs longer will not "
                     "build either; split it or give it the facts it needs.")

        def make(n: str):
            def fn(**kwargs):
                at.count(n)
                if n == "isabelle_fill_sorries":
                    at.fills += 1
                    kwargs.setdefault("timeout_s", FILL_TIMEOUT_S)
                    kwargs.setdefault("max_total_s", FILL_MAX_TOTAL_S)
                    kwargs.setdefault("patience_s", FILL_PATIENCE_S)
                    for k, v in fill_stage_options().items():
                        kwargs.setdefault(k, v)
                    clamped = []
                    for k, (lo, hi) in FILL_CAPS.items():
                        try:
                            v = int(float(kwargs.get(k, lo)))
                        except (TypeError, ValueError):
                            v = lo
                        if v != max(lo, min(hi, v)):
                            clamped.append(f"{k} {v}->{max(lo, min(hi, v))}")
                        kwargs[k] = max(lo, min(hi, v))
                    remaining = at.remaining_s()
                    if remaining is not None:
                        if remaining < FILL_MIN_REMAINING_S:
                            return (f"fill_sorries refused: only {remaining:.0f}s remain in this attempt, "
                                    "not enough for a sledgehammer round.")
                        kwargs["max_total_s"] = max(60, min(int(kwargs["max_total_s"]), int(remaining - 120)))
                    raw = at.mcp(n, kwargs)
                    d = _collect_fill(at, raw, int(kwargs["max_total_s"]))
                    if "raw" in d:
                        return d["raw"]
                    if clamped:
                        d["clamped"] = ", ".join(clamped)
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
                if n in ("isabelle_run_code", "isabelle_multi_attempt"):
                    # Rep 1: P2 spent 74 min in twelve scratch runs of 300..600 s,
                    # P6 16 min in one multi_attempt of four `smt` candidates at
                    # 300 s. The MCP default (ATTEMPT_TIMEOUT_S) is the cap too.
                    try:
                        kwargs["timeout"] = min(float(kwargs.get("timeout") or ATTEMPT_TIMEOUT_S), ATTEMPT_TIMEOUT_S)
                    except (TypeError, ValueError):
                        kwargs["timeout"] = ATTEMPT_TIMEOUT_S
                    raw = at.mcp(n, kwargs)
                    if re.search(r'timed out \(still running|"timed_out": true', raw):
                        raw += (f"\n\nNOTE: that ran for the cap of {ATTEMPT_TIMEOUT_S}s and did not finish. "
                                "A longer timeout is not available and would not help: a step this slow "
                                "will not build either. Treat it as too hard as stated -- split it into "
                                "smaller steps or give it the facts it needs with `using`.")
                    return raw
                if n == "isabelle_sledgehammer":
                    # Pass 1: the model escalated timeout_s to 120..300 after
                    # failures (plain P6: 42 calls, 114 min, 2 found); the server
                    # overran its budget past 120 s and answered 500. More seconds
                    # buy nothing (docs/research-pipeline-2026-11-10.md, 2a).
                    kwargs.setdefault("timeout_s", 60)
                    kwargs["timeout_s"] = min(int(kwargs["timeout_s"]), SLEDGEHAMMER_MAX_S)
                    raw = at.mcp(n, kwargs)
                    if re.search(r'"error": "http_5\d\d"|Backend call timed out|did not finish within|timed out \(budget', raw):
                        return json.dumps({
                            "found": False,
                            "error": f"the server could not finish sledgehammer within its budget "
                                     f"(timeout_s={kwargs['timeout_s']}). Do not retry with a longer "
                                     "timeout: this goal is too hard for the provers as stated. Split "
                                     "the step into smaller `have`s, add the facts it needs with `using`, "
                                     "or try simple closers (simp, auto, blast, linarith) instead.",
                            "server_said": raw[:300]})
                    return raw
                return at.mcp(n, kwargs)
            return fn

        reg.register(name, desc, schema, make(name))


def _register_finishing_tools(reg: agentlib.ToolRegistry, at: _Attempt) -> None:
    def completed() -> str:
        at.count("completed")
        text = at.thy.read_text(encoding="utf-8")
        # A file whose session check never finished is not sent to the build:
        # the build would sit on the same step until its own limit (16 min
        # lost per call on the Q1 rerun) and come back with no usable reason.
        stuck = at.stuck_line()
        if stuck is not None:
            at.failed_completions += 1
            report = (f"FAIL [{at.entry['name']}] the prover never finished checking the file: "
                      f"still running line {stuck}: `{at.line_text(stuck)}` after {LOAD_TIMEOUT_S}s. "
                      "Not built.")
            at.last_verify = report
            return (report + "\n\nVERIFY FAILED. You are NOT done. That step does not terminate "
                    "(or is far too slow): replace it with a different proof and call completed() again.")
        ok, report = _safe_verify(text, at.entry, at.variant, gym_url=GYM_URL)
        at.last_verify = report
        if ok:
            at.kind = "completed"
            # The bytes that passed, kept beside the working file: the final
            # verdict is taken on these, whatever happens to the file later.
            (at.bench_dir / "verified.thy").write_text(text, encoding="utf-8")
            return (report + "\n\nVERIFY PASSED. The problem is SOLVED and you are DONE.\n"
                    "Write your final report as your next message -- the mathematical idea, "
                    "what you tried, what worked -- and then stop. Do not call any more tools.")
        if "verifier unavailable" in report:
            # Infrastructure, not the proof: the build service did not answer.
            # Not counted as a failed completion and not blamed on the model.
            at.verifier_unavailable += 1
            return (report + "\n\nVERIFIER UNAVAILABLE. Your file was NOT judged: the build service "
                    "did not answer, which is a fault on our side, not in your proof. Do not change "
                    "the file because of this. Call completed() again; if it happens repeatedly, "
                    "keep re-checking the file in the session in the meantime.")
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
        if not at.disproof_build_ok:
            return (f"{name} has not passed a build (last write_disproof build: "
                    + ("FAILED" if at.disproof_build_ok is False else "never run") +
                    "). The claim was NOT recorded and you are NOT done. Fix the disproof until "
                    "write_disproof reports `Build: OK`, then call disproved() again.")
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
        if at.kind is not None:
            return f"The run is over ({at.kind}): nothing more is written."
        (at.bench_dir / "DISPROOF.thy").write_text(content, encoding="utf-8")
        ok, log = ib.build_check(content, {"name": ib.parse_header(content)[0] if content.strip().startswith(("theory", "(*")) else "DISPROOF",
                                           "field": at.entry["field"], "sessions": at.entry["sessions"]},
                                 gym_url=GYM_URL)
        at.disproof_build_ok = ok
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

def _make_should_continue(at: _Attempt):
    """agentlib asks this after every turn that ended without a tool call:
    a string continues the run with that message, None ends it. A stop after
    the run is over is the final report. Otherwise the model is nudged -- but
    only GIVE_UP_STOPS times in a row: pass 1 (2026-11-08/09) nudged a model
    that had written "I was unable to complete the proof" 489 times on P3 and
    425 on P6, three hours each, at 600 k tokens a call. Any tool call resets
    the counter (`_Attempt.count`), so a model that is working is never cut."""
    def should_continue(assistant_msg, step_idx):
        if at.kind is not None:
            return None
        at.consecutive_stops += 1
        if at.consecutive_stops >= GIVE_UP_STOPS:
            at.gave_up = True
            print(f"[harness] GAVE UP: {GIVE_UP_STOPS} consecutive turns without a tool call; ending the attempt",
                  flush=True)
            return None
        return _nudge(at)
    return should_continue


def _nudge(at: _Attempt) -> str:
    """What we say when the agent stops without having finished. The no-limits
    sentences are upstream's (nearai/putnambench-deepseek): pass 1 had dropped
    them from the prompt and the nudge, and plain P3 then gave up "in the
    available time" -- a limit nothing had mentioned. Restored 2026-11-10,
    worded for a run that does have a wall clock the harness, not the model,
    owns. The give-up cap in `_make_should_continue` stays: a model that
    ignores this three turns running is not going to be argued out of it."""
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
        "You have NO turn limit and NO time limit to manage. There is no budget you are "
        "spending, nothing is running out, and no one is waiting on you. Taking another hundred "
        "turns costs nothing and is completely fine.\n\n"
        "You are doing well -- the work you have already done is still in front of you and none "
        "of it is wasted. Pick up where you left off: try another angle on the mathematics, look "
        "for different lemmas (find_theorems), break the goal into smaller `have` steps and prove "
        "them one at a time, or test a small case to sharpen your intuition. If you have started "
        "to suspect the goal is actually false, chase that: build the counterexample and derive "
        "False from the hypotheses in Isabelle." + extra + "\n\nContinue now, with a tool call."
    )


def fetch_symbols(gym_url: str, timeout: float = 10.0) -> dict | None:
    """The Pool Server's symbol table (`GET /api/v1/symbols`: `{"\\<le>": "≤",
    ...}`), or None when the server does not answer or has no table."""
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{gym_url.rstrip('/')}/api/v1/symbols")
            r.raise_for_status()
            d = r.json()
    except Exception as e:  # noqa: BLE001 - never fatal; the keys fall back to literal
        print(f"[harness] symbols: fetch failed ({type(e).__name__}: {e})", flush=True)
        return None
    table = d.get("symbols") if isinstance(d, dict) else None
    return table if isinstance(table, dict) and table else None


def prompt_sha(at: _Attempt | None) -> str | None:
    """Fingerprint of the system prompt text the model saw, kept in the results
    row so passes run under different prompt wordings stay distinguishable (the
    no-limits section was added 2026-11-10, between pass 1 and rep 1)."""
    if at is None:
        return None
    return hashlib.sha256(_system_prompt(at).encode()).hexdigest()[:12]


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
    if at.arm.filler_only:
        rule_block = """# LEAF RULE (enforced; it subsumes the solver rule)

You never write a closing proof method yourself. write_file REJECTS a file in
which any `by ...`, `.`, `..`, `apply`, `qed <method>` or goal-closing
`proof <method>` was not produced by the filler for that very statement under
the same enclosing goals. Yours: the structure (`proof -`, `proof (rule ...)`,
`(intro ...)`, `(cases ...)`, `(induction ...)`, `fix`/`assume`/`obtain`/
`have`/`show`/`qed`), the intermediate facts, `using`/`unfolding` facts, and
`sorry` on every leaf. The filler's lines come back through write_file; keep
them exactly as read_file shows them.
"""
    else:
        rule_block = """# SOLVER RULE (enforced)

Never write `metis`, `smt`, `meson` or `moura` calls yourself. write_file
REJECTS a file containing such a call unless that exact call came out of a
sledgehammer / fill result in this run -- paste those verbatim. Everything
else (simp, auto, force, blast, linarith, arith, algebra, presburger, argo,
induction, cases, unfolding, rule applications, structured Isar) is yours.
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

{rule_block}
# HOW THIS RUN ENDS

There are exactly TWO ways to finish, and you must reach one of them:

  (a) completed() returns PASS -- you proved the theorem; or
  (b) you prove in Isabelle that the goal is false and call disproved().

Nothing else ends the run. If you stop for any other reason -- out of ideas,
feeling stuck, "this seems infeasible", believing you have done enough -- you
will simply be told to continue, and you will have lost nothing but the turn.
Stopping three turns in a row, with no tool call in between, ends the run
unsolved: it is the one way to lose everything.

# You have NO limits

This is the single most important thing to understand about this run:

- There is NO turn limit. Not a large one -- none. Take ten turns or ten
  thousand.
- There is NO time limit for you to manage. The harness owns the wall clock;
  you cannot see it, speed it or save it, and nothing you do makes it run out
  sooner. Treat it as if it did not exist.
- There is NO token budget you are spending down, and no cost you should be
  economizing on.
- Nobody is waiting on you. There is no deadline, no queue behind you, and no
  penalty whatsoever for taking longer.

So never ration your effort, never rush a proof because it is "taking too
long", never give up "in the available time", and never wrap up early with a
summary of what you would have tried. If an approach needs fifty writes of
lemma-by-lemma grinding, spend them. If you need to test a small case, or
restate the problem from scratch, or throw away an hour of work and start
over, do it -- that is a normal and good use of this run, not a waste.

The ONLY thing that ends this run is (a) or (b) above.

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
  angle, not a stopping condition. "I was unable to complete the proof" is
  never a final answer here; it is a prompt to continue.
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
        "ISABELLE_MCP_LSP_LOAD_TIMEOUT": str(LOAD_TIMEOUT_S),
        "ISABELLE_MCP_LSP_CLOSE_DESTROYS": "true",
        # warm scratch sessions (run_code / multi_attempt) per agent: 2 keeps a
        # worker at 3 server sessions (file + 2 scratch); size ISABELLE_POOL_SIZE
        # on the server at >= 3 x workers
        "ISABELLE_MCP_LSP_SCRATCH_POOL_SIZE": "2",
        # start the file session on the heap its imports name (IPS patch; the
        # server must have that heap built) instead of loading from source
        "ISABELLE_MCP_LSP_FIELD_FROM_IMPORTS": "true",
        "PYTHONUTF8": "1",
    }
    return [MCP_PYTHON, "-m", "mcp_servers.lsp.app"], env


OPEN_RETRIES = 8
OPEN_RETRY_S = 60.0


def _safe_verify(text: str, entry: dict, variant: str, **kw) -> tuple[bool, str]:
    """verify_text that cannot take the worker down. The checks are written
    to report, not raise, but a verdict site is the wrong place to find the
    exception that proves otherwise (P2 plain, 2026-11-08: the worker died
    after the agent loop on a file with no closing `end`, no results row)."""
    try:
        return ib.verify_text(text, entry, variant, **kw)
    except Exception as e:                               # noqa: BLE001
        return False, f"FAIL [{entry['name']}] verifier error: {type(e).__name__}: {e}"


def _final_verify(at: _Attempt, entry: dict, variant: str) -> tuple[bool, str]:
    """The harness's own verdict on an attempt, taken while its session is
    still up. Judged on the bytes completed() verified (verified.thy) when
    there are any; otherwise on the working file, and then only built when
    the session finished checking it -- a file the prover is still running
    would cost the whole build limit and leave an orphaned build on the
    server (Q1 rerun, 2026-11-05)."""
    snap = at.bench_dir / "verified.thy"
    if snap.exists():
        text = snap.read_text(encoding="utf-8")
    elif at.thy.exists():
        text = at.thy.read_text(encoding="utf-8")
    else:
        text = ""
    if not text.strip():
        return False, "no file"
    ok, report = _safe_verify(text, entry, variant, build=False, gym_url=GYM_URL)
    if not ok:
        return ok, report
    if not snap.exists():
        try:
            stuck = at.stuck_line()
        except Exception:                                # noqa: BLE001
            stuck = None
        if stuck is not None:
            return False, (f"FAIL [{entry['name']}] the prover never finished checking the file: "
                           f"still running line {stuck}: `{at.line_text(stuck)}`. Not built.")
    return _safe_verify(text, entry, variant, gym_url=GYM_URL)


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
    transcript: _Transcript | None = None
    result = None
    timed_out = False
    setup_error: str | None = None
    at: _Attempt | None = None
    final: tuple[bool, str] | None = None
    elapsed_agent: float | None = None
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
                f"{at.thy.name} with a complete Isar proof, then call completed(). You have no "
                f"turn limit and no time limit to manage. The run ends only when completed() "
                f"reports PASS, or -- in the rare case where the formalized goal is false -- when "
                f"you have proven that and called disproved()."
            )

            should_continue = _make_should_continue(at)

            def _alarm(signum, frame):
                raise _Timeout()

            if args.timeout:
                signal.signal(signal.SIGALRM, _alarm)
                signal.alarm(args.timeout)
                at.deadline = time.time() + args.timeout
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
            elapsed_agent = time.time() - t0
            # The definitive check is OURS, not the agent's claim -- taken
            # while the session is still up (see _final_verify).
            final = _final_verify(at, entry, variant)
            try:
                bridge.call("isabelle_close", {"file_path": str(at.thy), "destroy": True}, timeout=60)
            except Exception:                            # noqa: BLE001
                pass
    except Exception as e:                               # noqa: BLE001
        setup_error = f"{type(e).__name__}: {e}"
        compactions = 0
        print(f"[harness] ERROR: {setup_error}", flush=True)
    elapsed = elapsed_agent if elapsed_agent is not None else time.time() - t0

    if final is None:   # the session never came up: judge the file blind
        text = (bench_dir / f"{problem}.thy").read_text(encoding="utf-8") if (bench_dir / f"{problem}.thy").exists() else ""
        final = (_safe_verify(text, entry, variant, gym_url=GYM_URL) if text else (False, "no file"))
    passed, report = final
    reason = next((l.strip() for l in reversed(report.splitlines()) if l.strip().startswith("FAIL [")), "")
    if not reason and not passed:
        reason = (setup_error or report.strip().splitlines()[-1] if report.strip() else "")

    usage_rows = agentlib.USAGE_LOG[usage_mark:]
    length_turns = sum(1 for c in (transcript.calls if transcript is not None else []) if c.get("finish") == "length")
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
        print(f"writes         : {at.writes} (rejected {at.rejected_writes}: leaf rule {at.leaf_rejections}, frozen {at.frozen_rejections})  fills: {at.fills} "
              f"({at.fill_sorries_proved}/{at.fill_sorries_total} sorries)  sledgehammer: "
              f"{at.sledgehammer_found}/{at.sledgehammer_calls}  busy retries: {at.busy_retries} "
              f"(releases {at.releases})")
    print(f"tokens         : {tokens}")
    if not passed:
        print(f"verify said    : {reason or '(no output)'}")
    print("=" * 70, flush=True)

    status = ("solved" if passed else
              "disproved" if (at is not None and at.kind == "disproved" and not timed_out) else
              "timeout" if timed_out else
              "gave_up" if (at is not None and at.gave_up) else "failed")
    row = {
        "problem": problem, "source": entry["source"], "category": entry.get("category"),
        "arm": arm_name, "variant": variant, "rep": rep, "model": cfg.model,
        "solved": passed, "status": status,
        "finish_reason": getattr(result, "finish_reason", None), "timed_out": timed_out,
        "timeout_s": args.timeout, "max_steps": args.max_steps,   # the budget the attempt ran under
        "prompt_sha": prompt_sha(at),                              # which system prompt text the model saw
        "symbols": leaves.symbols_in_use(),                        # server symbol table behind the leaf rule (0 = literal keys)
        "length_turns": length_turns,                              # model turns cut at the provider's output ceiling
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
            "verifier_unavailable": at.verifier_unavailable,
            "tool_calls": at.tool_calls, "writes": at.writes, "rejected_writes": at.rejected_writes,
            "leaf_rejections": at.leaf_rejections, "frozen_rejections": at.frozen_rejections,
            "gave_up": at.gave_up,
            "fills": at.fills, "auto_fills": at.auto_fills,
            "fill_sorries_total": at.fill_sorries_total, "fill_sorries_proved": at.fill_sorries_proved,
            "fill_stages": at.fill_stages, "fill_false": at.fill_false, "fill_options": fill_stage_options(),
            "sledgehammer_calls": at.sledgehammer_calls, "sledgehammer_found": at.sledgehammer_found,
            "tool_time_s": round(at.tool_time_s, 1),
            "busy_retries": at.busy_retries, "releases": at.releases,
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
    p.add_argument("--max-steps", type=int, default=0, help="turn cap; 0 = unlimited (default, as upstream)")
    p.add_argument("--timeout", type=int, default=14400, help="wall-clock seconds per attempt (default 4 h; 0 = none)")
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

    # The leaf rule compares text the way Isabelle reads it: the server's own
    # symbol table (its etc/symbols), fetched once per worker; without it the
    # keys are literal and the log says so (docs/rep1-analysis-2026-11-11.md H4).
    n_sym = leaves.set_symbols(fetch_symbols(GYM_URL))
    print(f"[harness] symbols: {n_sym} from {GYM_URL}" if n_sym else
          f"[harness] symbols: none from {GYM_URL} (leaf keys compare literally)", flush=True)

    if args.problem:
        arm = (args.arm or ["plain"])[0]
        if arm not in ARMS:
            print(f"[harness] ERROR: unknown arm {arm}; choose from {list(ARMS)}")
            return 2
        status = _solve_one(args.problem, arm, args.variant or "wsolution", args.rep, args)
        return 0 if status == "solved" else 1

    n_done = ok = 0
    stop_file = Path(args.runs_dir) / "STOP"
    while args.loop == 0 or n_done < args.loop:
        if stop_file.exists():
            # `scripts/imo2026_pass.py stop` drops this file: finish the current
            # row, claim no more (a server restart can then happen between rows).
            print(f"[harness] {stop_file} present; not claiming another row", flush=True)
            break
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
            # One row's harness error must not end the pass: mark the row,
            # keep the traceback in the log, go on to the next row. (The
            # P2 plain crash of 2026-11-08 stopped a ten-attempt pass at its
            # first row.) A persistent error fails rows in seconds, which the
            # queue notes show.
            import traceback
            traceback.print_exc()
            print(f"[harness] ERROR on {problem}/{arm}/rep{rep}: {type(e).__name__}: {e}; continuing", flush=True)
            ib.cmd_release(SimpleNamespace(problem=problem, arm=arm, rep=rep, variant=variant,
                                           status="failed", steps=None, note=f"harness error: {e}"[:120]))
            n_done += 1
            continue
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
