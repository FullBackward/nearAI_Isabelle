#!/usr/bin/env python3
"""watch.py - follow the running attempts, one line per model turn and per tool call.

The worker logs (runs/<owner>.log) carry the MCP's HTTP chatter interleaved
across workers; the per-turn record of an attempt is its transcript.jsonl.
This script finds the attempts the queue marks `running`, tails each one's
transcript and prints, with a short tag per attempt:

    12:01:33 p1962_b3/forced  #255 CHAT  tool_calls  10.2s  cmpl 612
    12:01:40 p1962_b3/forced  #257 TOOL  isabelle_run_code  6.7s -> {"success": true, ...
    12:01:44 p1962_b3/plain   #140 CHAT  stop        8.0s  "I have not completed the proof..."

When a worker finishes a row and claims the next, the new transcript is
picked up on the next scan. Nothing here touches the queue or the attempts.

    .venv/bin/python scripts/watch.py              # follow every running attempt
    .venv/bin/python scripts/watch.py --once       # the last 15 records of each, then exit
    .venv/bin/python scripts/watch.py --last 40    # start with more history
    .venv/bin/python scripts/watch.py runs/plain/putnam_1962_b3/rep0/transcript.jsonl   # a given file
    .venv/bin/python scripts/watch.py --reasoning             # plus the model's reasoning, 800 chars a turn
    .venv/bin/python scripts/watch.py --reasoning 0 --args 0  # everything: full reasoning, full tool arguments
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import ib  # noqa: E402

RUNS = ROOT / "runs"
ARM_SHORT = {"plain": "plain", "skeleton": "skel", "skeleton_forced": "forced", "fill_optional": "fillopt"}


def running_transcripts() -> dict[str, Path]:
    """tag -> transcript path for every queue row marked running by a live pid."""
    with ib._Lock(shared=True):
        rows = ib._read_rows()
    out = {}
    for r in rows:
        if r["status"] != "running" or not (r["pid"] and ib._pid_alive(r["pid"])):
            continue
        p = RUNS / r["arm"] / r["problem"] / f"rep{r['rep']}" / "transcript.jsonl"
        tag = f"{r['problem'].replace('putnam_', 'p').replace('imo_2026_', 'imo')}/{ARM_SHORT.get(r['arm'], r['arm'])}"
        out[tag] = p
    return out


REASON: int | None = None   # chars of the model's reasoning to print per turn (None = off, 0 = all)
TOOLARGS: int | None = None  # chars of a tool call's arguments to print (None = off, 0 = all)


def block(label: str, text: str, limit: int | None) -> str:
    """An indented block under a line: the model's reasoning, its text, or a tool's arguments."""
    text = (text or "").strip()
    if not text:
        return ""
    if limit:
        text = text[:limit] + (" [...]" if len(text) > limit else "")
    body = "\n".join("    | " + ln for ln in text.splitlines())
    return f"\n    {label}:\n{body}"


def fmt(tag: str, rec: dict) -> str | None:
    kind = rec.get("kind")
    t = (rec.get("started") or "")[11:19]
    n = rec.get("n", "?")
    if kind == "chat":
        resp = rec.get("response") or {}
        usage = rec.get("usage") or {}
        fin = rec.get("finish_reason") or "?"
        content = (resp.get("content") or "").strip()
        head = ""
        if not resp.get("tool_calls") and REASON is None:
            head = "  " + json.dumps(content[:90])
        line = (f"{t} {tag:18s} #{n:>4} CHAT  {fin:10s} {float(rec.get('elapsed_s') or 0):6.1f}s"
                f"  cmpl {usage.get('completion_tokens', '?')}{head}")
        if REASON is not None:
            line += block("reasoning", resp.get("reasoning_content") or "", REASON)
            line += block("text", content, REASON)
        return line
    if kind == "tool":
        res = (rec.get("result") or "").replace("\n", " ")
        err = rec.get("error")
        tail = f" !! {err}" if err and err != "None" else ""
        line = (f"{'':8s} {tag:18s} #{n:>4} TOOL  {rec.get('name', '?'):24s} {float(rec.get('elapsed_s') or 0):6.1f}s"
                f" -> {res[:110]}{tail}")
        if TOOLARGS is not None:
            line += block("args", rec.get("arguments") or "", TOOLARGS)
        return line
    return None   # mcp records are the harness's own calls; the tool line already covers them


def tail_lines(path: Path, n: int) -> tuple[list[str], int]:
    """last n lines and the byte offset at end of file."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return [], 0
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[-n:], len(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="transcript.jsonl files to follow (default: every running attempt)")
    ap.add_argument("--last", type=int, default=15, help="history lines per attempt at start (default 15)")
    ap.add_argument("--once", action="store_true", help="print the history and exit")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between scans")
    ap.add_argument("--reasoning", type=int, nargs="?", const=800, default=None, metavar="CHARS",
                    help="also print the model's reasoning and text per turn (CHARS each, default 800; 0 = all)")
    ap.add_argument("--args", dest="toolargs", type=int, nargs="?", const=300, default=None, metavar="CHARS",
                    help="also print each tool call's arguments (CHARS, default 300; 0 = all)")
    args = ap.parse_args()
    global REASON, TOOLARGS
    REASON, TOOLARGS = args.reasoning, args.toolargs

    offsets: dict[Path, int] = {}
    tags: dict[Path, str] = {}

    def discover() -> None:
        if args.files:
            found = {f"{Path(f).parent.parent.name.replace('putnam_', 'p').replace('imo_2026_', 'imo')}/"
                     f"{ARM_SHORT.get(Path(f).parent.parent.parent.name, Path(f).parent.parent.parent.name)}": Path(f)
                     for f in args.files}
        else:
            found = running_transcripts()
        for tag, p in found.items():
            if p not in offsets:
                lines, off = tail_lines(p, args.last)
                tags[p] = tag
                print(f"--- following {tag}: {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}", flush=True)
                for ln in lines:
                    try:
                        s = fmt(tag, json.loads(ln))
                    except json.JSONDecodeError:
                        continue
                    if s:
                        print(s, flush=True)
                offsets[p] = off

    discover()
    if not offsets:
        print("no running attempt (queue has no live `running` row); pass a transcript path to follow one")
        return 1
    if args.once:
        return 0
    scan = 0
    while True:
        time.sleep(args.interval)
        for p, off in list(offsets.items()):
            try:
                with open(p, "rb") as f:
                    f.seek(off)
                    chunk = f.read()
            except FileNotFoundError:
                continue
            if not chunk:
                continue
            offsets[p] = off + len(chunk)
            for ln in chunk.decode("utf-8", "replace").splitlines():
                try:
                    s = fmt(tags[p], json.loads(ln))
                except json.JSONDecodeError:
                    continue   # a partial last line is re-read on the next scan only if complete; rare
                if s:
                    print(s, flush=True)
        scan += 1
        if scan % 5 == 0 and not args.files:
            discover()   # a worker may have moved to its next row


if __name__ == "__main__":
    sys.exit(main())
