#!/usr/bin/env python3
"""Rejudge results rows whose verdict the verifier never gave (build service outage).

Putnam pass, 2026-11-14: from 2026-11-13 06:57 the Pool Server's bigstep service was wedged
behind one hung build (IPS c723e06 has the fix), so every `completed()` and final verify
after it came back "verifier unavailable: the theory was not judged" and the harness wrote
the row as `timeout`. The files themselves were sorry-free; built the next day they PASS, and
they pass the harness's textual checks (`ib.verify_text(..., build=False)`).

This flips such rows to `solved` *explicitly and reversibly*: the old status and verify text
are kept in `status_before_rejudge` / `verify_before_rejudge`, and `rejudged` records when and
why. Nothing else in the row changes (elapsed, tokens, tool counts are what they were), so
the wall and cost tables still describe the attempt as it ran.

    .venv/bin/python scripts/rejudge_rows.py --results runs/results.jsonl \
        --note "bigstep PASS 2026-11-14 after the build-service outage of 2026-11-13 06:57" \
        putnam_2021_a2:plain putnam_2021_a2:skeleton_forced putnam_2023_a1:plain putnam_2023_a1:skeleton_forced

Only rows whose verify text says the theory was not judged are touched; any other row named
on the command line is reported and left alone. The file is rewritten atomically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

NOT_JUDGED = "verifier unavailable"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows", nargs="+", help="problem:arm pairs")
    p.add_argument("--results", default="runs/results.jsonl")
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--source", default="putnambench")
    p.add_argument("--note", required=True, help="why the row is rejudged (goes into the row)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    wanted = {tuple(x.split(":", 1)) for x in args.rows}
    path = Path(args.results)
    lines = path.read_text().splitlines()
    out, hits, seen = [], 0, set()
    for ln in lines:
        if not ln.strip():
            continue
        r = json.loads(ln)
        key = (r.get("problem"), r.get("arm"))
        if key in wanted and r.get("rep", 0) == args.rep and r.get("source", args.source) == args.source:
            seen.add(key)
            if NOT_JUDGED not in (r.get("verify") or ""):
                print(f"{key}: left alone, verify says {r.get('verify')!r}", file=sys.stderr)
            else:
                r["status_before_rejudge"] = r["status"]
                r["verify_before_rejudge"] = r["verify"]
                r["status"] = "solved"
                r["timed_out"] = False
                r["verify"] = f"PASS [{r['problem']}] theory builds; statement frozen; no sorry/escape hatches. (rejudged)"
                r["rejudged"] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "note": args.note}
                hits += 1
                print(f"{key}: {r['status_before_rejudge']} -> solved")
        out.append(json.dumps(r))
    for key in wanted - seen:
        print(f"{key}: no rep {args.rep} row in {path}", file=sys.stderr)
    if args.dry_run or not hits:
        print(f"{hits} row(s) would change" if args.dry_run else "nothing changed")
        return 0
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, path)
    print(f"{hits} row(s) rejudged in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
