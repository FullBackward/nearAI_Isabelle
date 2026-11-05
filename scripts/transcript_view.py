#!/usr/bin/env python3
"""Readable view of an attempt's transcript.jsonl, while it is still being written.

    python3 scripts/transcript_view.py runs/plain/imo_2026_p1/rep0/transcript.jsonl            # all so far
    python3 scripts/transcript_view.py runs/plain/imo_2026_p1/rep0/transcript.jsonl --last 5   # last 5 records
    python3 scripts/transcript_view.py runs/plain/imo_2026_p1/rep0/transcript.jsonl --follow   # like tail -f
    python3 scripts/transcript_view.py ... --full      # no truncation of reasoning / tool results
    python3 scripts/transcript_view.py ... --summary   # one line per record (what happened, in order)

Each record is one model call (`chat`: finish reason, tokens, seconds, the
reply's reasoning, content and tool calls), one tool execution (`tool`: name,
arguments, result) or one call the harness itself made to the prover inside a
tool (`mcp`: the sync report after a write, the diagnostics, a fill job). Reasoning and tool results are cut at --width characters
unless --full is given; the jsonl itself is never truncated (see transcript.md
for the whole thing once the attempt is over).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _cut(s: object, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = s.replace("\r", "")
    return s if n <= 0 or len(s) <= n else s[:n] + f" ... [{len(s) - n} more chars]"


def _args(fn_args: str, n: int) -> str:
    try:
        d = json.loads(fn_args)
    except (TypeError, ValueError):
        return _cut(fn_args, n)
    if isinstance(d, dict) and "content" in d and isinstance(d["content"], str):
        c = d["content"]
        return f"content=<{len(c)} chars, {c.count(chr(10)) + 1} lines, {c.count('sorry')} sorry>"
    return _cut(json.dumps(d, ensure_ascii=False), n)


def render(rec: dict, width: int, summary: bool) -> str:
    n = rec.get("n")
    if rec.get("kind") == "chat":
        r = rec.get("response") or {}
        u = rec.get("usage") or {}
        tcs = r.get("tool_calls") or []
        head = (f"#{n} MODEL  finish={rec.get('finish_reason')}  "
                f"tokens prompt={u.get('prompt_tokens')} cached={u.get('cached_tokens')} "
                f"completion={u.get('completion_tokens')}  {rec.get('elapsed_s')}s  "
                f"calls: {', '.join((t.get('function') or {}).get('name', '?') for t in tcs) or '-'}")
        if summary:
            return head
        out = [head]
        if r.get("error"):
            out.append("  ERROR: " + _cut(r["error"], width))
        if r.get("reasoning_content"):
            out.append("  reasoning: " + _cut(r["reasoning_content"], width).replace("\n", "\n    "))
        if r.get("content"):
            out.append("  content: " + _cut(r["content"], width).replace("\n", "\n    "))
        for t in tcs:
            fn = t.get("function") or {}
            out.append(f"  -> {fn.get('name')}({_args(fn.get('arguments', ''), width)})")
        return "\n".join(out)
    if rec.get("kind") in ("tool", "mcp"):
        # `tool`: a call the model made; `mcp`: a call the harness made to the
        # prover on its behalf (sync reports, diagnostics, fill jobs).
        label = "TOOL  " if rec.get("kind") == "tool" else "MCP   "
        head = (f"#{n} {label} {rec.get('name')}  {rec.get('elapsed_s')}s"
                + (f"  error={rec.get('error')}" if rec.get("error") else "")
                + (f"  retries={rec.get('retries')}" if rec.get("retries") else ""))
        if summary:
            res = rec.get("result") or ""
            return head + "  -> " + _cut(res.splitlines()[0] if res else "", 100)
        return head + "\n  " + _cut(rec.get("result") or "", width).replace("\n", "\n  ")
    return f"#{n} {rec.get('kind')}: {_cut(rec, width)}"


def _read(path: Path, offset: int) -> tuple[list[dict], int]:
    recs: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            if not line.endswith("\n"):          # partial last line: wait for the rest
                return recs, f.tell() - len(line.encode("utf-8"))
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
        return recs, f.tell()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("jsonl", type=Path)
    p.add_argument("--last", type=int, default=0, help="show only the last N records")
    p.add_argument("--follow", action="store_true", help="keep printing new records as they arrive")
    p.add_argument("--full", action="store_true", help="never truncate")
    p.add_argument("--summary", action="store_true", help="one line per record")
    p.add_argument("--width", type=int, default=600, help="truncate long fields at this many chars")
    a = p.parse_args()
    width = 0 if a.full else a.width
    if not a.jsonl.exists():
        print(f"not there yet: {a.jsonl}", file=sys.stderr)
        return 1
    recs, off = _read(a.jsonl, 0)
    if a.last:
        recs = recs[-a.last:]
    for r in recs:
        print(render(r, width, a.summary), flush=True)
    if not a.follow:
        chats = sum(1 for r in recs if r.get("kind") == "chat")
        print(f"-- {len(recs)} records shown ({chats} model calls)", file=sys.stderr)
        return 0
    try:
        while True:
            time.sleep(2)
            new, off = _read(a.jsonl, off)
            for r in new:
                print(render(r, width, a.summary), flush=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
