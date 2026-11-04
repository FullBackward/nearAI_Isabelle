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
