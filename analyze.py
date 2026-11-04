#!/usr/bin/env python3
"""analyze.py - summarize runs/results.jsonl per arm, per category, and as a
paired per-problem comparison between two arms.

    python3 analyze.py                       # all arms, all rows
    python3 analyze.py --pair plain skeleton # + paired table and McNemar counts
    python3 analyze.py --results other.jsonl --source minif2f

A problem attempted several times in one arm (repeats, re-runs) counts as
solved for pass@k purposes if ANY attempt solved it; the per-attempt means
use every attempt. Rows with a setup_error (MCP or server failure before the
agent ran) are listed separately and excluded from the rates.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def load(path: Path, source: str | None, arms: list[str] | None) -> list[dict]:
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        if source and r.get("source") != source:
            continue
        if arms and r.get("arm") not in arms:
            continue
        rows.append(r)
    return rows


def mean(xs):
    xs = [x for x in xs if x is not None]
    return f"{st.mean(xs):.1f}" if xs else "-"


def per_arm(rows: list[dict]) -> None:
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    print(f"{'arm':14s} {'attempts':>8s} {'setup-err':>9s} {'solved':>7s} {'rate':>6s} {'problems':>8s} {'pass@any':>8s} "
          f"{'steps':>6s} {'wall_s':>7s} {'writes':>6s} {'rej':>4s} {'fills':>5s} {'sh':>4s} {'out_tok':>8s} {'nudges':>6s}")
    for arm, rs in sorted(by_arm.items()):
        ok = [r for r in rs if not r.get("setup_error")]
        bad = len(rs) - len(ok)
        solved = sum(1 for r in ok if r["solved"])
        probs = {r["problem"] for r in ok}
        solved_any = {r["problem"] for r in ok if r["solved"]}
        print(f"{arm:14s} {len(rs):8d} {bad:9d} {solved:7d} {solved/len(ok)*100 if ok else 0:5.1f}% "
              f"{len(probs):8d} {len(solved_any)/len(probs)*100 if probs else 0:7.1f}% "
              f"{mean([r.get('steps') for r in ok]):>6s} {mean([r.get('elapsed_s') for r in ok]):>7s} "
              f"{mean([r.get('writes') for r in ok]):>6s} {mean([r.get('rejected_writes') for r in ok]):>4s} "
              f"{mean([r.get('fills') for r in ok]):>5s} {mean([r.get('sledgehammer_calls') for r in ok]):>4s} "
              f"{mean([(r.get('tokens') or {}).get('completion') for r in ok]):>8s} {mean([r.get('nudges') for r in ok]):>6s}")


def per_category(rows: list[dict]) -> None:
    cats = sorted({r.get("category") or "?" for r in rows})
    arms = sorted({r["arm"] for r in rows})
    print(f"\n{'category':22s}" + "".join(f"{a:>16s}" for a in arms))
    for c in cats:
        line = f"{c:22s}"
        for a in arms:
            rs = [r for r in rows if (r.get("category") or "?") == c and r["arm"] == a and not r.get("setup_error")]
            n = len({r["problem"] for r in rs})
            s = len({r["problem"] for r in rs if r["solved"]})
            line += f"{(f'{s}/{n}' if n else '-'):>16s}"
        print(line)


def paired(rows: list[dict], a: str, b: str) -> None:
    def best(arm):
        d = defaultdict(lambda: {"solved": False, "steps": [], "wall": []})
        for r in rows:
            if r["arm"] != arm or r.get("setup_error"):
                continue
            e = d[r["problem"]]
            e["solved"] = e["solved"] or r["solved"]
            e["steps"].append(r.get("steps") or 0)
            e["wall"].append(r.get("elapsed_s") or 0)
        return d
    da, db = best(a), best(b)
    common = sorted(set(da) & set(db))
    both = sum(1 for p in common if da[p]["solved"] and db[p]["solved"])
    only_a = sum(1 for p in common if da[p]["solved"] and not db[p]["solved"])
    only_b = sum(1 for p in common if db[p]["solved"] and not da[p]["solved"])
    neither = len(common) - both - only_a - only_b
    print(f"\npaired on {len(common)} problems attempted in both {a} and {b}:")
    print(f"  both solved {both}, only {a} {only_a}, only {b} {only_b}, neither {neither}")
    if only_a + only_b:
        # exact McNemar (binomial) two-sided p-value on the discordant pairs
        from math import comb
        n, k = only_a + only_b, min(only_a, only_b)
        p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
        print(f"  McNemar exact p = {p:.3f} (discordant n={n})")
    solved_both = [p for p in common if da[p]["solved"] and db[p]["solved"]]
    if solved_both:
        print(f"  on the {len(solved_both)} problems both solved: mean steps {a}={st.mean(min(da[p]['steps']) for p in solved_both):.1f} "
              f"{b}={st.mean(min(db[p]['steps']) for p in solved_both):.1f}; mean wall_s {a}={st.mean(min(da[p]['wall']) for p in solved_both):.0f} "
              f"{b}={st.mean(min(db[p]['wall']) for p in solved_both):.0f}")
    print(f"\n{'problem':40s} {a:>10s} {b:>10s}")
    for p in common:
        print(f"{p:40s} {'solved' if da[p]['solved'] else '-':>10s} {'solved' if db[p]['solved'] else '-':>10s}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=str(Path(__file__).resolve().parent / "runs" / "results.jsonl"))
    ap.add_argument("--source", choices=["minif2f", "putnambench"])
    ap.add_argument("--arms", nargs="*")
    ap.add_argument("--pair", nargs=2, metavar=("ARM_A", "ARM_B"))
    ap.add_argument("--errors", action="store_true", help="list attempts with a setup error")
    args = ap.parse_args()
    path = Path(args.results)
    if not path.exists():
        print(f"no results at {path}")
        return 1
    rows = load(path, args.source, args.arms)
    if not rows:
        print("no rows")
        return 1
    per_arm(rows)
    per_category(rows)
    if args.pair:
        paired(rows, *args.pair)
    if args.errors:
        print("\nsetup errors:")
        for r in rows:
            if r.get("setup_error"):
                print(f"  {r['arm']:12s} {r['problem']:40s} {r['setup_error'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
