"""Unit tests for the harness tools, with a fake MCP bridge (no server, no model).

    .venv/bin/python -m pytest tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agentlib  # noqa: E402
import run_isabelle_solver as rs  # noqa: E402
from harness.arms import ARMS  # noqa: E402


class FakeBridge:
    """Scripted MCP: `diag` is the next diagnostics payload, `fill` the next
    fill_sorries payload; every call is recorded."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.diag = {"messages": [], "success": True, "proof_open": False, "used_sorry": True}
        self.sync = {"synced": True, "success": True, "proof_open": False, "error": None, "stuck_line": None}
        self.fill = {"filled": 0, "n": 0, "continuing": False, "results": [], "patched_text": None}
        self.sh = {"found": True, "results": [{"method": "by (metis add.commute)"}]}

    def call(self, name, args, timeout=0):
        self.calls.append((name, args))
        if name == "isabelle_sync":
            return json.dumps(self.sync)
        if name == "isabelle_diagnostic_messages":
            return json.dumps(self.diag)
        if name == "isabelle_fill_sorries":
            return json.dumps(self.fill)
        if name == "isabelle_sledgehammer":
            return json.dumps(self.sh)
        return "{}"


ENTRY = {"name": "t1", "source": "minif2f", "theorem_name": "t1", "imports": ["Main"],
         "sessions": [], "field": "HOL", "header": "t1 imports Main",
         "sig": 'theorem t1: shows "True"', "has_solution": False, "solution_name": None,
         "solution_type": None, "reference_answer": None, "sig_wsolution": None, "tags": []}
THY = 'theory t1 imports Main\nbegin\n\ntheorem t1: shows "True"\n  sorry\n\nend\n'


def make(tmp_path, arm="plain", enforce=True):
    thy = tmp_path / "t1.thy"
    thy.write_text(THY)
    b = FakeBridge()
    at = rs._Attempt(ENTRY, "wsolution", ARMS[arm], tmp_path, b, enforce)
    reg = agentlib.ToolRegistry()
    rs._register_file_tools(reg, at)
    return at, b, reg


def test_extract_solver_calls():
    got = rs.extract_solver_calls('by (metis foo\n  bar) qed\nby smt\n  by (simp add: x) (meson a)')
    assert got == {"metis foo bar", "smt", "meson a"}


def test_write_file_rejects_unsanctioned_metis(tmp_path):
    at, b, reg = make(tmp_path)
    out = reg.invoke("write_file", json.dumps({"content": THY.replace("sorry", "by (metis TrueI)")}))
    assert out.startswith("REJECTED")
    assert at.rejected_writes == 1 and at.writes == 0
    assert "sorry" in (tmp_path / "t1.thy").read_text()


def test_sledgehammer_output_sanctions_its_method(tmp_path):
    at, b, reg = make(tmp_path)
    at.mcp("isabelle_sledgehammer", {"line": 4})
    assert "metis add.commute" in at.sanctioned
    out = reg.invoke("write_file", json.dumps({"content": THY.replace("sorry", "by (metis add.commute)")}))
    assert out.startswith("wrote") and at.writes == 1


def test_file_path_is_injected(tmp_path):
    at, b, reg = make(tmp_path)
    at.mcp("isabelle_goal", {"line": 3})
    assert b.calls[-1] == ("isabelle_goal", {"file_path": str(at.thy), "line": 3})


def test_skeleton_auto_fill_writes_patch_back(tmp_path):
    at, b, reg = make(tmp_path, arm="skeleton")
    patched = THY.replace("sorry", "by (smt (verit) TrueI)")
    b.fill = {"filled": 1, "n": 1, "continuing": False, "patched_text": patched,
              "results": [{"line": 5, "outcome": "proved", "method": "by (smt (verit) TrueI)"}]}
    b.diag = {"messages": [], "success": True, "proof_open": False, "used_sorry": True}
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "fill_sorries: 1/1" in out
    assert (tmp_path / "t1.thy").read_text() == patched
    assert at.auto_fills == 1 and at.fill_sorries_proved == 1
    assert "smt (verit) TrueI" in at.sanctioned
    names = [c[0] for c in b.calls]
    assert names == ["isabelle_sync", "isabelle_diagnostic_messages", "isabelle_fill_sorries",
                     "isabelle_sync", "isabelle_diagnostic_messages"]


def test_skeleton_no_auto_fill_on_errors(tmp_path):
    at, b, reg = make(tmp_path, arm="skeleton")
    b.diag = {"messages": [{"line": 4, "col": 1, "kind": "theorem", "text": "Bad"}], "success": False}
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "1 error(s)" in out
    assert [c[0] for c in b.calls] == ["isabelle_sync", "isabelle_diagnostic_messages"]


def test_plain_arm_never_auto_fills(tmp_path):
    at, b, reg = make(tmp_path, arm="plain")
    reg.invoke("write_file", json.dumps({"content": THY}))
    assert [c[0] for c in b.calls] == ["isabelle_sync", "isabelle_diagnostic_messages"]


def test_completed_runs_textual_verifier(tmp_path, monkeypatch):
    at, b, reg = make(tmp_path)
    rs._register_finishing_tools(reg, at)
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: (True, "ok"))
    out = reg.invoke("completed", "{}")
    assert "VERIFY FAILED" in out and "sorry" in out and at.kind is None
    at.thy.write_text(THY.replace("sorry", "by simp"))
    out = reg.invoke("completed", "{}")
    assert "VERIFY PASSED" in out and at.kind == "completed"


def test_arm_tool_sets_are_disjoint_on_the_treatment():
    assert "isabelle_sledgehammer" in ARMS["plain"].mcp_tools
    assert "isabelle_fill_sorries" not in ARMS["plain"].mcp_tools
    assert "isabelle_sledgehammer" not in ARMS["skeleton"].mcp_tools
    assert "isabelle_fill_sorries" in ARMS["skeleton"].mcp_tools
    assert ARMS["skeleton"].auto_fill and not ARMS["plain"].auto_fill


def test_system_prompt_for_multi_target_entry(tmp_path):
    """IMO 2026 files state several theorems: the prompt must say all of them
    are the problem and name them; single-target entries keep the old text."""
    at, b, reg = make(tmp_path)
    assert "single theorem" in rs._system_prompt(at)
    entry = dict(ENTRY, source="imo2026", targets=["t1", "t_two", "t_three"],
                 sigs={}, frozen_blocks=[], pristine_defs=[], tags=["imo2026"])
    at2 = rs._Attempt(entry, "wsolution", ARMS["skeleton"], tmp_path, b, True)
    txt = rs._system_prompt(at2)
    assert "3 theorems" in txt and "t_three" in txt and "EVERY `sorry`" in txt
    assert "IMO 2026" in txt


def test_transcript_records_everything(tmp_path, monkeypatch):
    """Fake model: one turn calls a tool, the next stops. The jsonl must carry
    the exact request (system prompt, tool schemas, every message) and reply
    (reasoning, tool call) per call, plus the tool execution; the markdown must
    show all of it, untruncated."""
    replies = [
        ({"role": "assistant", "content": "", "reasoning_content": "let me add",
          "tool_calls": [{"id": "c1", "type": "function",
                          "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'}}]}, "tool_calls"),
        ({"role": "assistant", "content": "five, done"}, "stop"),
    ]
    monkeypatch.setattr(agentlib, "_stream_chat_inner", lambda *a, **k: replies.pop(0))
    reg = agentlib.ToolRegistry()
    reg.register("add", "adds", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
                 lambda a, b: a + b)
    cfg = agentlib.AgentConfig(host="http://x/chat", model="fake", apikey="k")
    agent = agentlib.Agent(cfg, reg, db_path=str(tmp_path / "db.sql"), agent_name="isa-test")
    tr = rs._Transcript(tmp_path / "transcript.jsonl")
    monkeypatch.setattr(agentlib, "CHAT_SINK", tr)
    monkeypatch.setattr(agentlib, "TOOL_SINK", tr)
    res = agent.run("add two and three", system_prompt="SYSTEM PROMPT TEXT", max_steps=5)
    assert res.finish_reason == "stop"

    recs = [json.loads(l) for l in (tmp_path / "transcript.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in recs] == ["chat", "tool", "chat"]
    first = recs[0]["request"]
    assert first["messages"][0] == {"role": "system", "content": "SYSTEM PROMPT TEXT"}
    assert first["messages"][1]["content"] == "add two and three"
    assert first["tools"][0]["function"]["name"] == "add"
    assert recs[0]["response"]["reasoning_content"] == "let me add"
    assert recs[0]["response"]["tool_calls"][0]["function"]["name"] == "add"
    assert recs[1]["name"] == "add" and recs[1]["result"] == "5" and recs[1]["error"] is None
    # the second request carries the tool result back to the model
    roles = [m["role"] for m in recs[2]["request"]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert recs[2]["request"]["messages"][3]["content"] == "5"

    rows = rs._trajectory_rows(agent, "isa-test")
    md = rs._render_transcript_md(rows, tr.calls, {"problem": "p", "arm": "plain", "rep": 0})
    for needle in ("SYSTEM PROMPT TEXT", "add two and three", "let me add", "tool call `add`",
                   "tool result `add`", "five, done", "## Model calls"):
        assert needle in md, needle
    agent.close()


def test_capacity_refusal_is_released_and_retried(tmp_path, monkeypatch):
    """pool_full once -> the harness calls isabelle_release_idle itself, waits,
    retries, and the model sees the successful answer; a refusal that persists
    comes back with the hidden tool names rewritten into 'retry' advice."""
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    at, b, reg = make(tmp_path)
    answers = [json.dumps({"error": "pool_full", "retry_after_s": 3,
                           "advice": ["release what you no longer need (isabelle_release_idle()) and retry in 3 s."]}),
               json.dumps({"success": True, "output": "found 1 theorem(s)"})]
    orig = b.call

    def call(name, args, timeout=0):
        if name == "isabelle_query":
            b.calls.append((name, args))
            return answers.pop(0)
        return orig(name, args, timeout)        # FakeBridge.call records the others
    b.call = call
    out = at.mcp("isabelle_query", {"command": "find_theorems foo"})
    assert "found 1 theorem" in out
    assert [n for n, _ in b.calls] == ["isabelle_query", "isabelle_release_idle", "isabelle_query"]
    assert at.busy_retries == 1 and at.releases == 1

    answers[:] = [json.dumps({"error": "memory_pressure", "retry_after_s": 5,
                              "advice": ["Release the 2 session(s) ...: call isabelle_release_idle(), then retry in 5 s.",
                                         "Retry in 5 s; if it keeps failing, tell the user (isabelle_memory_status() shows the numbers)."]})] * 3
    out = at.mcp("isabelle_query", {"command": "find_theorems bar"})
    assert "isabelle_release_idle" not in out and "isabelle_memory_status" not in out
    assert "memory_pressure" in out and "harness" in out
    assert at.busy_retries == 3 and at.releases == 3


def test_exposed_tools_do_not_reference_hidden_ones(tmp_path):
    """The MCP's own descriptions address an agent that has the memory/heap
    tools; ours must not see those names or the heap-naming parameters."""
    at, b, reg = make(tmp_path)
    available = [
        {"name": "isabelle_multi_attempt", "description":
            "Try several candidates ... MEMORY: a candidate result with error memory_pressure "
            "means ... call isabelle_release_idle(), then retry; if the advice says the memory is "
            "held by others, stop and tell the user.",
         "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "line": {"type": "integer"},
                        "candidates": {"type": "array"}}, "required": ["file_path", "line", "candidates"]}},
        {"name": "isabelle_run_code", "description":
            "Run an independent Isar snippet on a warm scratch session. heap_session runs it in that "
            "heap's import context. Returns {success, output}.",
         "parameters": {"type": "object", "properties": {"chunk": {"type": "string"}, "imports": {"type": "array"},
                        "task_group": {"type": "string"}, "heap_session": {"type": "string"},
                        "timeout": {"type": "number"}}, "required": ["chunk"]}},
    ]
    at.arm = type(at.arm)(**{**at.arm.__dict__, "mcp_tools": ["isabelle_multi_attempt", "isabelle_run_code"]})
    rs._register_mcp_tools(reg, at, available)
    tools = {t["function"]["name"]: t["function"] for t in reg.to_openai()}
    ma = tools["isabelle_multi_attempt"]
    assert "isabelle_release_idle" not in ma["description"] and "MEMORY:" not in ma["description"]
    assert "file_path" not in ma["parameters"]["properties"]
    rc = tools["isabelle_run_code"]
    assert set(rc["parameters"]["properties"]) == {"chunk", "imports", "timeout"}
    assert "heap_session" not in rc["description"]


def test_read_file_with_content_is_routed_to_write_file(tmp_path):
    at, b, reg = make(tmp_path)
    new = THY.replace("sorry", "by simp")
    out = reg.invoke("read_file", json.dumps({"content": new}))
    assert "treated as write_file" in out and at.writes == 1
    assert (tmp_path / "t1.thy").read_text() == new
    assert reg.invoke("read_file", json.dumps({"foo": 1})).startswith("ERROR: read_file takes no arguments")


def test_timed_out_check_is_an_error_and_blocks_the_build(tmp_path, monkeypatch):
    """Q1 rerun 2026-11-05: a divergent metis made the session's full-file
    check expire; the error list was empty, the harness said "no errors", and
    completed() sent the file to a build that hung on the same step."""
    at, b, reg = make(tmp_path, arm="skeleton")
    rs._register_finishing_tools(reg, at)
    b.sync = {"synced": True, "success": False, "error": "timed out (still running at line 5)",
              "stuck_line": 5}
    b.diag = {"messages": [], "success": False, "proof_open": False, "used_sorry": False}
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "CHECK TIMED OUT" in out and "line 5" in out and "sorry" in out
    assert "fill_sorries" not in out                        # a stuck check is an error: no auto-fill
    built = []
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: built.append(1) or (True, "ok"))
    at.thy.write_text(THY.replace("sorry", "by simp"))
    out = reg.invoke("completed", "{}")
    assert "VERIFY FAILED" in out and "still running line 5" in out and not built
    assert at.failed_completions == 1 and at.kind is None


def test_failed_check_with_false_stuck_line_is_not_a_timeout(tmp_path, monkeypatch):
    """Q1 plain run 2026-11-05: the LSP MCP computes stuck_line as
    `timed_out and commands and next(...)`, so a check that failed on plain
    errors reports stuck_line=False -- and bool is an int. The harness told
    the model "CHECK TIMED OUT ... line False" after a 5 s check. A failed
    check lists its errors and nothing else; completed() still builds."""
    at, b, reg = make(tmp_path)
    rs._register_finishing_tools(reg, at)
    b.sync = {"synced": True, "success": False, "error": None, "stuck_line": False}
    b.diag = {"messages": [{"line": 3, "kind": "by", "severity": "error", "text": "Failed to finish proof"}],
              "success": False, "proof_open": False, "used_sorry": False}
    out = reg.invoke("write_file", json.dumps({"content": THY.replace("sorry", "by simp")}))
    assert "CHECK TIMED OUT" not in out and "line False" not in out and "Failed to finish proof" in out
    assert at.stuck_line() is None
    built = []
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: built.append(1) or (False, "FAIL: build"))
    out = reg.invoke("completed", "{}")
    assert built and "still running" not in out


def test_verifier_outage_is_not_a_failed_completion(tmp_path, monkeypatch):
    at, b, reg = make(tmp_path)
    rs._register_finishing_tools(reg, at)
    at.thy.write_text(THY.replace("sorry", "by simp"))
    monkeypatch.setattr(rs.ib, "build_check",
                        lambda text, entry, **kw: (False, "build service unavailable: ReadTimeout: timed out"))
    out = reg.invoke("completed", "{}")
    assert "VERIFIER UNAVAILABLE" in out and "verifier unavailable" in out
    assert "VERIFY FAILED" not in out and "Fix what it reported" not in out
    assert at.failed_completions == 0 and at.verifier_unavailable == 1 and at.kind is None


def test_write_after_pass_is_refused_and_verified_bytes_kept(tmp_path, monkeypatch):
    """Audit F1: DeepSeek batches tool calls, so a write_file can follow a
    passing completed() in the same turn. The file is frozen from the PASS on
    and the bytes that passed are kept as verified.thy."""
    at, b, reg = make(tmp_path)
    rs._register_finishing_tools(reg, at)
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: (True, "ok"))
    proved = THY.replace("sorry", "by simp")
    at.thy.write_text(proved)
    assert "VERIFY PASSED" in reg.invoke("completed", "{}")
    assert (tmp_path / "verified.thy").read_text() == proved
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "frozen" in out and "NOT applied" in out
    assert at.thy.read_text() == proved and at.writes == 0
    assert "run is over" in reg.invoke("write_disproof", json.dumps({"content": "theory X imports Main begin end"}))


def test_disproved_requires_a_built_disproof(tmp_path, monkeypatch):
    """Audit F7: a disproof that did not build (or was never built through
    write_disproof) cannot end the run."""
    at, b, reg = make(tmp_path)
    rs._register_finishing_tools(reg, at)
    (tmp_path / "DISPROOF.thy").write_text("theory DISPROOF imports Main begin lemma False sorry end")
    out = reg.invoke("disproved", json.dumps({"explanation": "x"}))
    assert "never run" in out and at.kind is None
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: (False, "boom"))
    assert "FAILED" in reg.invoke("write_disproof", json.dumps({"content": "theory DISPROOF imports Main begin end"}))
    out = reg.invoke("disproved", json.dumps({"explanation": "x"}))
    assert "FAILED" in out and at.kind is None
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: (True, "ok"))
    assert "Build: OK" in reg.invoke("write_disproof", json.dumps({"content": "theory DISPROOF imports Main begin end"}))
    monkeypatch.setattr(rs, "DEFECTS_DIR", tmp_path / "defects")
    out = reg.invoke("disproved", json.dumps({"explanation": "x"}))
    assert "recorded" in out and at.kind == "disproved"


def test_final_verify_skips_the_build_on_a_stuck_file(tmp_path, monkeypatch):
    """Audit F3: after a timeout the harness's own verdict must not build a
    file the session never finished checking; and once completed() passed,
    the verdict is taken on verified.thy."""
    at, b, reg = make(tmp_path)
    built = []
    monkeypatch.setattr(rs.ib, "build_check", lambda text, entry, **kw: built.append(text) or (True, "ok"))
    at.thy.write_text(THY.replace("sorry", "by simp"))
    b.sync = {"synced": True, "success": False, "error": "timed out (still running at line 5)", "stuck_line": 5}
    ok, report = rs._final_verify(at, ENTRY, "wsolution")
    assert not ok and "still running line 5" in report and not built
    b.sync = {"synced": True, "success": True, "error": None, "stuck_line": None}
    ok, report = rs._final_verify(at, ENTRY, "wsolution")
    assert ok and len(built) == 1
    # a sorry-laden file fails on the textual checks before any session call
    at.thy.write_text(THY)
    calls_before = len(b.calls)
    ok, report = rs._final_verify(at, ENTRY, "wsolution")
    assert not ok and "sorry" in report and len(b.calls) == calls_before
    # verified bytes win over whatever is on disk afterwards
    (tmp_path / "verified.thy").write_text(THY.replace("sorry", "by simp"))
    ok, report = rs._final_verify(at, ENTRY, "wsolution")
    assert ok and built[-1] == THY.replace("sorry", "by simp")


def test_harness_mcp_calls_are_in_the_transcript(tmp_path):
    """Audit F6: the prover side of the conversation (sync report,
    diagnostics) is recorded as `mcp` records in the same transcript."""
    at, b, reg = make(tmp_path)
    recs = []
    agentlib.TOOL_SINK = recs.append
    try:
        reg.invoke("write_file", json.dumps({"content": THY}))
    finally:
        agentlib.TOOL_SINK = None
    kinds = [(r["kind"], r["name"]) for r in recs]
    assert ("mcp", "isabelle_sync") in kinds and ("mcp", "isabelle_diagnostic_messages") in kinds
    rec = next(r for r in recs if r["name"] == "isabelle_diagnostic_messages")
    assert json.loads(rec["arguments"]) == {"severity": "error"} and "messages" in rec["result"]


# ---- skeleton_forced: the leaf rule ------------------------------------- #

PROVED = THY.replace("sorry", "by simp")


def test_leaf_rule_rejects_hand_written_closers(tmp_path):
    """skeleton_forced: the model never closes a step itself. A write with a
    hand-written `by` is refused before the file changes; a sorry skeleton is
    accepted and goes to the filler."""
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    out = reg.invoke("write_file", json.dumps({"content": PROVED}))
    assert out.startswith("REJECTED") and "LEAF RULE" in out and "line 5" in out and "by simp" in out
    assert at.thy.read_text() == THY and at.leaf_rejections == 1 and at.rejected_writes == 1
    assert not any(c[0] == "isabelle_sync" for c in b.calls)          # refused before any session call
    # apply scripts and goal-closing initial methods are refused too
    for bad in ('theorem t1: shows "True"\n  apply simp\n  done\n',
                'theorem t1: shows "True"\nproof (auto)\nqed\n',
                'theorem t1: shows "True"\nproof -\n  show ?thesis sorry\nqed simp\n'):
        text = THY.replace('theorem t1: shows "True"\n  sorry\n', bad)
        assert reg.invoke("write_file", json.dumps({"content": text})).startswith("REJECTED"), bad
    # a skeleton is fine and triggers the auto-fill
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert out.startswith("wrote") and "fill_sorries" in out
    assert [c[0] for c in b.calls][-3:] == ["isabelle_sync", "isabelle_diagnostic_messages", "isabelle_fill_sorries"]


def test_leaf_rule_accepts_filler_lines_verbatim_and_bound_to_their_statement(tmp_path):
    """What the filler wrote back may be kept, verbatim, under the same
    statement; the same method under another statement is a new leaf."""
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    b.fill = {"filled": 1, "n": 1, "continuing": False,
              "results": [{"line": 5, "outcome": "proved", "method": "by simp"}],
              "patched_text": PROVED}
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "1/1 sorry(s) proved" in out and at.thy.read_text() == PROVED
    # the model writes the filler's text back unchanged (plus a new sorry lemma): accepted
    more = PROVED.replace("\nend", '\nlemma t2: shows "True \\<and> True"\n  sorry\n\nend')
    assert reg.invoke("write_file", json.dumps({"content": more})).startswith("wrote")
    # the same `by simp` pasted under the new statement is NOT the filler's leaf
    pasted = more.replace('shows "True \\<and> True"\n  sorry', 'shows "True \\<and> True"\n  by simp')
    out = reg.invoke("write_file", json.dumps({"content": pasted}))
    assert out.startswith("REJECTED") and "line 8" in out
    # a reworded statement over a filler leaf is a new leaf as well
    reworded = more.replace('theorem t1: shows "True"\n  by simp', 'theorem t1: shows "True \\<or> False"\n  by simp')
    assert reg.invoke("write_file", json.dumps({"content": reworded})).startswith("REJECTED")
    # whitespace changes do not matter
    spaced = more.replace('theorem t1: shows "True"\n  by simp', 'theorem t1:   shows "True"\n      by   simp')
    assert reg.invoke("write_file", json.dumps({"content": spaced})).startswith("wrote")


def test_leaf_rule_seeds_from_the_staged_file_and_explicit_fill_results(tmp_path):
    """Proofs already in the statement file are allowed as they are, and a
    patched text from an explicit isabelle_fill_sorries call counts too."""
    given = THY.replace('theorem t1: shows "True"\n  sorry', 'lemma pre: "1 = (1::nat)"\n  by simp\n\ntheorem t1: shows "True"\n  sorry')
    (tmp_path / "t1.thy").write_text(given)
    b = FakeBridge()
    at = rs._Attempt(ENTRY, "wsolution", ARMS["skeleton_forced"], tmp_path, b, True)
    reg = agentlib.ToolRegistry()
    rs._register_file_tools(reg, at)
    assert reg.invoke("write_file", json.dumps({"content": given})).startswith("wrote")
    # an explicit fill result registers its leaves even though the model, not
    # the harness, writes the patched text back
    at.note_filler_text(json.dumps({"patched_text": given.replace("  sorry", "  by blast")}))
    assert reg.invoke("write_file", json.dumps({"content": given.replace("  sorry", "  by blast")})).startswith("wrote")
    assert at.leaf_rejections == 0


def test_leaf_rule_is_off_in_the_other_arms(tmp_path):
    for arm in ("plain", "skeleton", "fill_optional"):
        at, b, reg = make(tmp_path, arm=arm)
        assert reg.invoke("write_file", json.dumps({"content": PROVED})).startswith("wrote"), arm
        assert at.leaf_rejections == 0


def test_leaves_selftest():
    from harness import leaves
    leaves.selftest()


def test_auto_fill_budget_scales_with_the_sorry_count(tmp_path):
    """Q1 forced run 2026-11-05: 223 sorries hit the 600 s job cap with 94
    untouched. The automatic round now gets 10 s per sorry, 600..1800 s."""
    assert rs.auto_fill_budget(5) == 600 and rs.auto_fill_budget(100) == 1000 and rs.auto_fill_budget(500) == 1800
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    many = THY.replace('theorem t1: shows "True"\n  sorry',
                       "".join(f'lemma l{i}: "True"\n  sorry\n' for i in range(70)) + 'theorem t1: shows "True"\n  sorry')
    reg.invoke("write_file", json.dumps({"content": many}))
    fill_args = [a for n, a in b.calls if n == "isabelle_fill_sorries"]
    assert fill_args and fill_args[-1]["max_total_s"] == 710 and fill_args[-1]["timeout_s"] == rs.FILL_TIMEOUT_S


def test_leaf_rejection_lists_every_line(tmp_path):
    from harness import leaves
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    text = THY.replace('theorem t1: shows "True"\n  sorry',
                       "".join(f'lemma l{i}: "True"\n  by simp\n' for i in range(40)) + 'theorem t1: shows "True"\n  sorry')
    out = reg.invoke("write_file", json.dumps({"content": text}))
    assert out.startswith("REJECTED") and "40 offending" in out and "more" not in out
    assert len(leaves.check(text, set())) == 40 and out.count("-- method") == 40


def test_textual_checks_report_a_missing_end_instead_of_raising():
    """P2 plain 2026-11-08: the worker died in _final_verify on a multi-target
    file with no closing `end`. A broken file is a FAIL, not an exception."""
    entry = dict(ENTRY, source="imo2026", targets=["t1"], header="t1 imports Main")
    broken = 'theory t1 imports Main\nbegin\n\ntheorem t1: shows "True"\n  by simp\n'
    fails = rs.ib.textual_checks(broken, entry, "wsolution")
    assert fails and any("closing `end`" in f for f in fails)
    ok, report = rs._safe_verify(broken, entry, "wsolution", build=False)
    assert not ok and report.startswith("FAIL [t1]")


def test_final_verify_never_raises(tmp_path, monkeypatch):
    at, b, reg = make(tmp_path)
    monkeypatch.setattr(rs.ib, "verify_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    at.thy.write_text(THY.replace("sorry", "by simp"))
    ok, report = rs._final_verify(at, ENTRY, "wsolution")
    assert not ok and "verifier error: RuntimeError: boom" in report


def _all_tools(arm):
    """The MCP tool list the arm expects, as the registry check wants it."""
    return [{"name": n, "description": n, "parameters": {"type": "object", "properties": {"file_path": {}, "timeout_s": {}, "max_total_s": {}}, "required": ["file_path"]}}
            for n in ARMS[arm].mcp_tools]


# ---- pass-1 fixes (2026-11-10) --------------------------------------------- #

def test_three_consecutive_stops_end_the_attempt_and_a_tool_call_resets():
    """Pass 1: plain P3/P6 were nudged 489/425 times after the model had given
    up. Two stops are nudged, the third ends the run; any tool call resets."""
    at, b, reg = make(__import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    sc = rs._make_should_continue(at)
    assert sc(None, 1) and sc(None, 2) and at.nudges == 2 and not at.gave_up
    reg.invoke("read_file", "{}")                      # work: counter restarts
    assert at.consecutive_stops == 0
    assert sc(None, 3) and sc(None, 4) and sc(None, 5) is None and at.gave_up
    # after a PASS the stop is the final report, never a nudge
    at2, b2, reg2 = make(__import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    at2.kind = "completed"
    assert rs._make_should_continue(at2)(None, 1) is None and not at2.gave_up


def test_write_that_drops_or_changes_the_frozen_statement_is_refused(tmp_path):
    """Forced P2, pass 1: the model used write_file as a scratchpad and ended
    with a 15-line file holding no theorem. The frozen parts are checked at
    write time now; sorry is still allowed (that is completed()'s business)."""
    at, b, reg = make(tmp_path)
    scratch = 'theory t1 imports Main\nbegin\n\nlemma test_x: "1 = (1::nat)"\n  by simp\n\nend\n'
    out = reg.invoke("write_file", json.dumps({"content": scratch}))
    assert out.startswith("REJECTED") and "frozen" in out and at.frozen_rejections == 1
    assert at.thy.read_text() == THY
    changed = THY.replace('shows "True"', 'shows "True \\<or> False"')
    assert reg.invoke("write_file", json.dumps({"content": changed})).startswith("REJECTED")
    assert reg.invoke("write_file", json.dumps({"content": THY.replace("imports Main", "imports Complex_Main")})).startswith("REJECTED")
    # the same statement with helper lemmas above and sorry inside is fine
    ok = THY.replace("theorem t1", 'lemma helper: "2 = (2::nat)"\n  by simp\n\ntheorem t1')
    assert reg.invoke("write_file", json.dumps({"content": ok})).startswith("wrote")


def test_sledgehammer_timeout_is_clamped_and_a_server_timeout_is_worded(tmp_path):
    at, b, reg = make(tmp_path)
    rs._register_mcp_tools(reg, at, _all_tools("plain"))
    reg.invoke("isabelle_sledgehammer", json.dumps({"timeout_s": 300}))
    assert b.calls[-1][1]["timeout_s"] == rs.SLEDGEHAMMER_MAX_S
    b.sh = {"error": "http_504", "detail": "Backend call timed out after 150.0s"}
    out = json.loads(reg.invoke("isabelle_sledgehammer", json.dumps({"timeout_s": 60})))
    assert out["found"] is False and "Do not retry with a longer timeout" in out["error"] and "150.0s" in out["server_said"]
    b.sh = {"found": True, "results": ["by simp"]}
    assert '"found": true' in reg.invoke("isabelle_sledgehammer", "{}")


def test_fill_rounds_respect_the_wall_clock(tmp_path):
    """Forced P6, pass 1, ended inside a fill job. With little time left the
    automatic round is skipped and the explicit tool refuses; otherwise the
    job cap shrinks to what remains."""
    import time as _t
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    at.deadline = _t.time() + 100
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "fill_sorries skipped" in out and not any(c[0] == "isabelle_fill_sorries" for c in b.calls)
    at.deadline = _t.time() + 400
    reg.invoke("write_file", json.dumps({"content": THY}))
    fill_args = [a for n, a in b.calls if n == "isabelle_fill_sorries"]
    assert fill_args and 270 <= fill_args[-1]["max_total_s"] <= 280
    rs._register_mcp_tools(reg, at, _all_tools("skeleton_forced"))
    at.deadline = _t.time() + 50
    assert reg.invoke("isabelle_fill_sorries", "{}").startswith("fill_sorries refused")


# ---- staged filler (IPS 2026-11-10) ---------------------------------------- #

def test_fill_summary_reports_stages_goals_and_false_statements(tmp_path):
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    d = {"filled": 2, "n": 4, "continuing": False, "stages": {"try0": 1, "split": 1, "nitpick": 1, "open": 1},
         "results": [
             {"line": 3, "outcome": "proved", "stage": "try0", "method": "by simp", "goal": "1 + 1 = 2"},
             {"line": 5, "outcome": "false", "stage": "nitpick", "method": None, "nitpick": "genuine",
              "reason": "nitpick: genuine counterexample -- n = 5", "goal": "∀n. n < 5"},
             {"line": 7, "outcome": "split", "stage": "split", "method": "apply (intro conjI impI allI ballI iffI)\nsubgoal by simp\nsubgoal sorry\ndone",
              "split": {"k": 2, "proved": 1}, "goal": "A ∧ B"},
             {"line": 9, "outcome": "none", "stage": "sledgehammer", "method": None, "goal": "hard"}]}
    out = rs._fill_summary(at, d)
    assert "1/4 sorry(s) proved [try0 1, split 1, nitpick 1, open 1]" in out
    assert "line 3: proved [try0] -> by simp" in out
    assert "line 5: false [nitpick]" in out and "WARNING: nitpick found a counterexample" in out and "[5]" in out
    assert "split into 2 leaves, 1 proved" in out and "goal: A ∧ B" in out and "goal: hard" in out
    assert at.fill_stages == {"try0": 1, "split": 1, "nitpick": 1} and at.fill_false == 1


def test_fill_calls_carry_the_stage_options(tmp_path):
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    reg.invoke("write_file", json.dumps({"content": THY}))
    args = [a for n, a in b.calls if n == "isabelle_fill_sorries"][-1]
    assert args["try0_s"] == rs.FILL_TRY0_S and args["nitpick_s"] == rs.FILL_NITPICK_S
    assert args["split"] is rs.FILL_SPLIT and args["isar"] is rs.FILL_ISAR and args["parallel"] == rs.FILL_PARALLEL
    rs._register_mcp_tools(reg, at, _all_tools("skeleton_forced"))
    reg.invoke("isabelle_fill_sorries", json.dumps({"timeout_s": 60}))
    args = [a for n, a in b.calls if n == "isabelle_fill_sorries"][-1]
    assert args["timeout_s"] == 60 and args["try0_s"] == rs.FILL_TRY0_S


def test_leaf_rule_keeps_a_filler_written_split_skeleton_and_refuses_a_hand_written_one(tmp_path):
    from harness import leaves
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    skeleton = ('theory t1 imports Main\nbegin\n\ntheorem t1: shows "True"\n'
                '  apply (intro conjI impI allI ballI iffI)\n  subgoal by simp\n  subgoal sorry\n  done\n\nend\n')
    # hand-written: refused (apply script)
    out = reg.invoke("write_file", json.dumps({"content": skeleton}))
    assert out.startswith("REJECTED") and "apply-script" in out
    # the same text as a filler result: accepted, including the `done`
    b.fill = {"filled": 1, "n": 1, "continuing": False,
              "results": [{"line": 5, "outcome": "split", "stage": "split", "method": "apply (intro conjI impI allI ballI iffI)\nsubgoal by simp\nsubgoal sorry\ndone", "split": {"k": 2, "proved": 1}}],
              "patched_text": skeleton}
    reg.invoke("write_file", json.dumps({"content": THY}))
    assert at.thy.read_text() == skeleton
    assert reg.invoke("write_file", json.dumps({"content": skeleton})).startswith("wrote")
    # keys exist for the apply lines, and a reworded leaf is still a new leaf
    assert any(k[1].endswith("done") for k in leaves.leaf_keys(skeleton))
    assert reg.invoke("write_file", json.dumps({"content": skeleton.replace("subgoal by simp", "subgoal by auto")})).startswith("REJECTED")


def test_leaf_rejection_and_open_fill_rows_tell_the_model_to_restate(tmp_path):
    """Rep-1 observation (2026-11-10): many leaf-rule rejections after a fill
    failed -- the model wrote the closer itself. Both messages the model reads
    at that moment now say: restate the step, do not write the closer."""
    at, b, reg = make(tmp_path, arm="skeleton_forced")
    out = reg.invoke("write_file", json.dumps({"content": THY.replace("sorry", "by simp")}))
    assert out.startswith("REJECTED") and "RESTATE the step" in out and "helper lemma" in out
    d = {"filled": 0, "n": 1, "stages": {"open": 1},
         "results": [{"line": 5, "outcome": "none", "stage": "sledgehammer", "method": None, "goal": "hard"}]}
    s = rs._fill_summary(at, d)
    assert "NEXT: the filler could not close" in s and "split each into smaller `have`s" in s
    # a plain-arm summary (no leaf rule) carries no such instruction
    at2, b2, reg2 = make(tmp_path, arm="plain")
    assert "NEXT:" not in rs._fill_summary(at2, d)
