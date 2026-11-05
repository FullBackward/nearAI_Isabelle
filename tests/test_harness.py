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
        self.fill = {"filled": 0, "n": 0, "continuing": False, "results": [], "patched_text": None}
        self.sh = {"found": True, "results": [{"method": "by (metis add.commute)"}]}

    def call(self, name, args, timeout=0):
        self.calls.append((name, args))
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
    assert names == ["isabelle_diagnostic_messages", "isabelle_fill_sorries", "isabelle_diagnostic_messages"]


def test_skeleton_no_auto_fill_on_errors(tmp_path):
    at, b, reg = make(tmp_path, arm="skeleton")
    b.diag = {"messages": [{"line": 4, "col": 1, "kind": "theorem", "text": "Bad"}], "success": False}
    out = reg.invoke("write_file", json.dumps({"content": THY}))
    assert "1 error(s)" in out
    assert [c[0] for c in b.calls] == ["isabelle_diagnostic_messages"]


def test_plain_arm_never_auto_fills(tmp_path):
    at, b, reg = make(tmp_path, arm="plain")
    reg.invoke("write_file", json.dumps({"content": THY}))
    assert [c[0] for c in b.calls] == ["isabelle_diagnostic_messages"]


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
