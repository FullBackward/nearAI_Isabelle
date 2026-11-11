#!/usr/bin/env python3
"""imo2026_pass.py - drive the IMO 2026 comparison in passes.

The experiment runs in two stages: every problem once on each arm (rep 0),
then a decision -- from that pass's table -- on which problems are worth
repeating N times. This script is the server-side driver for both stages;
it only wraps the existing queue (harness/ib.py) and worker
(run_isabelle_solver.py), so nothing about an attempt changes.

    # stage 1: one rep of every problem on both arms
    .venv/bin/python scripts/imo2026_pass.py init                 # queue rep 0, skip attempts already in results.jsonl
    .venv/bin/python scripts/imo2026_pass.py launch               # one worker, detached (spends money: your call)
    .venv/bin/python scripts/imo2026_pass.py status               # queue + results so far
    .venv/bin/python scripts/imo2026_pass.py report               # per-problem table, discordant pairs, repeat advice

    # stage 2: repeats where the report says they are worth it
    .venv/bin/python scripts/imo2026_pass.py repeat 3             # reps 1..2 of the problems in subsets/imo2026_repeat.txt
    .venv/bin/python scripts/imo2026_pass.py repeat 3 --all       # ... or of every problem
    .venv/bin/python scripts/imo2026_pass.py repeat --unsolved --rep 2   # one new rep (rep 2), both arms, only the
                                                                  # problems no arm has solved; then launch --timeout 28800
    .venv/bin/python scripts/imo2026_pass.py launch

Why a queue and one worker: the Pool Server builds one theory at a time and a
200-sorry fill job already saturates its sledgehammer slots, so a second
worker would mostly wait. The queue interleaves arms per problem, so a pass
interrupted half-way is still paired. `init` marks queue rows that already
have a results row (the hand-launched P1 runs) with that status, so they are
not run again; `repeat` adds rows for reps 1..N-1 only.

Why the report recommends rather than decides: with one rep per cell the
only information is agreement or disagreement per problem. A problem both
arms solve at rep 0 needs repeats only to estimate variance; a discordant
problem or one both arms miss is where repeats can change the conclusion.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import ib  # noqa: E402

ARMS_DEFAULT = ["plain", "skeleton_forced"]
SOURCE = "imo2026"
VARIANT = "wsolution"
RESULTS = ROOT / "runs" / "results.jsonl"
SUBSET = ROOT / "subsets" / "imo2026_repeat.txt"
IPS_URL = os.environ.get("IPS_URL", "http://localhost:8000")


# ---- helpers ------------------------------------------------------------- #

def results_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("source") == SOURCE and r.get("variant", VARIANT) == VARIANT:
                out.append(r)
    return out


def problems() -> list[str]:
    man = ib.load_manifest()
    return sorted(n for n, e in man.items() if e["source"] == SOURCE)


def ips_health() -> str:
    try:
        import requests  # noqa: WPS433 (venv dependency of the harness)
        r = requests.get(f"{IPS_URL}/healthz", timeout=5)
        return f"{r.status_code} {r.text.strip()[:80]}"
    except Exception as e:  # noqa: BLE001
        return f"DOWN ({type(e).__name__}: {e})"


def sync_queue_from_results(path: Path) -> int:
    """Queue rows that already have a results row get that row's status, so
    an attempt made by hand (P1 on both arms, 2026-11-05) is not repeated by
    the worker. Latest results row per (problem, arm, rep) wins."""
    latest: dict[tuple, dict] = {}
    for r in results_rows(path):
        latest[(r["problem"], r["arm"], str(r["rep"]))] = r
    n = 0
    with ib._Lock():
        rows = ib._read_rows()
        for q in rows:
            key = (q["problem"], q["arm"], str(q["rep"]))
            if q["status"] == "todo" and key in latest:
                r = latest[key]
                q.update(status=r["status"], owner="results.jsonl", pid="",
                         steps=str(r.get("steps") or ""),
                         note=f"from results.jsonl ({r.get('elapsed_s', 0):.0f}s)")
                n += 1
        ib._write_rows(rows)
    return n


def queue_init(arms: list[str], repeats: int, subset: Path | None, reps: list[int] | None = None) -> None:
    ib.cmd_queue_init(SimpleNamespace(source=SOURCE, category=None, with_answer=False, no_answer=False,
                                      subset=str(subset) if subset else None, arm=arms,
                                      variant=VARIANT, repeats=repeats, reps=reps))


def unsolved_problems(results: Path) -> list[str]:
    """The problems no arm has solved in any results row: the ones worth a
    rerun when nothing in the mechanism changed (owner, 2026-11-11)."""
    solved = {r["problem"] for r in results_rows(results) if r.get("solved")}
    return [p for p in problems() if p not in solved]


def queue_status() -> None:
    ib.cmd_queue_status(SimpleNamespace(verbose=False))


def worker_alive() -> list[str]:
    with ib._Lock(shared=True):
        rows = ib._read_rows()
    return [f"{r['problem']}/{r['arm']}/rep{r['rep']} pid {r['pid']}"
            for r in rows if r["status"] == "running" and r["pid"] and ib._pid_alive(r["pid"])]


# ---- commands ------------------------------------------------------------ #

def cmd_init(args) -> int:
    print(f"IPS {IPS_URL}/healthz: {ips_health()}")
    print(f"problems ({SOURCE}): {', '.join(problems())}")
    queue_init(args.arms, 1, None)
    n = sync_queue_from_results(Path(args.results))
    print(f"queue rows settled from results.jsonl: {n}")
    queue_status()
    return 0


def cmd_repeat(args) -> int:
    if args.unsolved:
        names = unsolved_problems(Path(args.results))
        if not names:
            sys.exit("every problem has been solved by some arm; nothing to repeat")
        subset = ROOT / "subsets" / "imo2026_unsolved.txt"
        subset.parent.mkdir(parents=True, exist_ok=True)
        subset.write_text("\n".join(names) + "\n", encoding="utf-8")
    else:
        subset = None if args.all else Path(args.subset)
        if subset and not subset.exists():
            sys.exit(f"{subset} not found: run `report` first, or pass --all / --unsolved")
    if args.rep is not None:
        # exactly one new rep, every arm: the 8 h pass (rep 2) on the unsolved
        # problems only, both arms, so the budget is the one thing that changes
        print(f"queueing rep {args.rep} of: {', '.join(names) if args.unsolved else (subset or 'every problem')}")
        queue_init(args.arms, 0, subset, reps=[args.rep])
    else:
        if args.n is None:
            sys.exit("repeat needs N (reps 1..N-1) or --rep R")
        if subset:
            names = [ln.strip() for ln in subset.read_text(encoding="utf-8").splitlines() if ln.strip()]
            print(f"repeating {args.n}x: {', '.join(names)}")
        queue_init(args.arms, args.n, subset)
    n = sync_queue_from_results(Path(args.results))
    print(f"queue rows settled from results.jsonl: {n}")
    queue_status()
    return 0


def model_config_ok() -> str:
    """Load config/model.json the way the worker does (agentlib.load_config
    reads `apikey_file`), so a missing or empty key file fails here, before a
    queue row is claimed -- and without ever printing the key."""
    import agentlib  # noqa: WPS433
    cfg_path = ROOT / "config" / "model.json"
    if not cfg_path.exists():
        return f"MISSING {cfg_path} (copy config/model.example.json)"
    try:
        cfg = agentlib.load_config(cfg_path)
    except Exception as e:  # noqa: BLE001
        return f"BAD ({type(e).__name__}: {e})"
    return f"ok: {cfg.model} @ {cfg.host} (key read from file, {len(cfg.apikey)} chars)"


def cmd_launch(args) -> int:
    alive = worker_alive()
    if alive and not args.force:
        print("a worker is already running on: " + "; ".join(alive) + "  (use --force to start another)")
        return 1
    health = ips_health()
    print(f"IPS {IPS_URL}/healthz: {health}")
    model = model_config_ok()
    print(f"model config: {model}")
    if not health.startswith("200") or not model.startswith("ok"):
        print("refusing to launch: fix the above first")
        return 1
    if args.dry_run:
        print("dry run: checks passed, no worker started")
        return 0
    logs = ROOT / "runs"
    logs.mkdir(parents=True, exist_ok=True)
    stop = logs / "STOP"
    if stop.exists():
        stop.unlink()
        print("removed a leftover STOP file")
    log = logs / f"{args.owner}.log"
    cmd = [sys.executable, str(ROOT / "run_isabelle_solver.py"), "--loop", "0",
           "--timeout", str(args.timeout), "--owner", args.owner, "--results", args.results]
    if args.arms_only:
        cmd += ["--arm", *args.arms_only]
    env = dict(os.environ)
    env.setdefault("ISABELLE_POOL_SERVER", str(Path.home() / "Isabelle-Pool-Server"))
    with open(log, "ab") as lf:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=lf, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    print(f"worker pid {proc.pid}; log {log}")
    print("watch:  .venv/bin/python scripts/imo2026_pass.py status")
    print("        tail -f " + str(log))
    return 0


def _cell(r: dict | None) -> str:
    if r is None:
        return "-"
    s = {"solved": "SOLVED", "failed": "failed", "timeout": "timeout", "gave_up": "gave up", "disproved": "disproved"}.get(r["status"], r["status"])
    budget = f"/{int(r['timeout_s']) // 3600}h" if r.get("timeout_s") else ""
    return f"{s} {r.get('elapsed_s', 0) / 60:.0f}m{budget}"


def cmd_stop(args) -> int:
    """Ask the worker to finish its current attempt and claim no more rows.
    `launch` removes the file again."""
    stop = ROOT / "runs" / "STOP"
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text(time.strftime("%Y-%m-%d %H:%M:%S\n"), encoding="utf-8")
    alive = worker_alive()
    print(f"STOP file written: {stop}. " + ("The worker finishes: " + "; ".join(alive) if alive else "No worker is running."))
    return 0


def cmd_status(args) -> int:
    print(f"IPS: {ips_health()}")
    print(f"model config: {model_config_ok()}")
    alive = worker_alive()
    print("worker: " + ("; ".join(alive) if alive else "none running"))
    queue_status()
    rows = results_rows(Path(args.results))
    if rows:
        print(f"\nresults.jsonl: {len(rows)} {SOURCE} rows; latest: "
              f"{rows[-1]['problem']} {rows[-1]['arm']} rep{rows[-1]['rep']} -> {rows[-1]['status']}")
    return 0


def cmd_report(args) -> int:
    rows = results_rows(Path(args.results))
    arms = args.arms
    probs = problems()
    # latest attempt per cell for the rep requested; every attempt for pass@any
    cell: dict[tuple, dict] = {}
    attempts: dict[tuple, list] = defaultdict(list)
    for r in rows:
        attempts[(r["problem"], r["arm"])].append(r)
        if str(r["rep"]) == str(args.rep):
            cell[(r["problem"], r["arm"])] = r
    w = max(len(p) for p in probs) + 2
    print(f"rep {args.rep}: status and wall clock per cell; "
          f"[steps / writes / leaf-rule rejections / sledgehammer calls / fills proved-of-tried / completion tokens]")
    print(f"{'problem':{w}s}" + "".join(f"{a:>44s}" for a in arms))
    disc, both_miss, both_solve, incomplete = [], [], [], []
    for p in probs:
        line = f"{p:{w}s}"
        got = []
        for a in arms:
            r = cell.get((p, a))
            got.append(r)
            if r is None:
                line += f"{'-':>44s}"
                continue
            detail = (f"[{r.get('steps')}/{r.get('writes')}/{r.get('leaf_rejections', 0)}/"
                      f"{r.get('sledgehammer_calls')}/{r.get('fill_sorries_proved')}-{r.get('fill_sorries_total')}/"
                      f"{(r.get('tokens') or {}).get('completion', 0) // 1000}k]")
            line += f"{_cell(r) + ' ' + detail:>44s}"
        print(line)
        if any(r is None for r in got):
            incomplete.append(p)
        elif len({r["solved"] for r in got}) > 1:
            disc.append(p)
        elif all(r["solved"] for r in got):
            both_solve.append(p)
        else:
            both_miss.append(p)
    print()
    for a in arms:
        rs = [cell[(p, a)] for p in probs if (p, a) in cell]
        solved = sum(1 for r in rs if r["solved"])
        print(f"{a:16s} rep {args.rep}: {solved}/{len(rs)} solved; "
              f"mean wall {sum(r['elapsed_s'] for r in rs) / 60 / max(1, len(rs)):.0f} min; "
              f"pass@any over all reps: {sum(1 for p in probs if any(x['solved'] for x in attempts[(p, a)]))}/{len(probs)}")
    print(f"\ndiscordant (one arm solved, the other not): {disc or 'none'}")
    print(f"both solved: {both_solve or 'none'}")
    print(f"both missed: {both_miss or 'none'}")
    if incomplete:
        print(f"not yet run on every arm: {incomplete}")
    # ---- recommendation --------------------------------------------------- #
    repeat = disc + both_miss
    print("\nrecommendation:")
    if incomplete:
        print("  finish the pass first (cells missing above).")
    if not repeat and not incomplete:
        print("  every problem agrees across arms at rep 0. Repeats can only estimate variance here;")
        print("  with the budget to spare, repeat the whole set (`repeat N --all`), otherwise stop.")
    elif repeat:
        print(f"  repeat {', '.join(repeat)}: " +
              ("a discordant cell is one run away from flipping, " if disc else "") +
              ("a miss on both arms may be variance (the first P1 plain run failed, the second solved). " if both_miss else ""))
        print(f"  {len(repeat)} problem(s) x {len(arms)} arms x (N-1) reps; at ~1.5 h per run, N=3 is ~{len(repeat) * len(arms) * 2 * 1.5:.0f} h.")
        SUBSET.parent.mkdir(parents=True, exist_ok=True)
        SUBSET.write_text("\n".join(repeat) + "\n", encoding="utf-8")
        print(f"  subset written: {SUBSET.relative_to(ROOT)}  ->  scripts/imo2026_pass.py repeat 3 && scripts/imo2026_pass.py launch")
    return 0


# ---- main ---------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default=str(RESULTS))
    p.add_argument("--arms", default=",".join(ARMS_DEFAULT), type=lambda v: [a for a in v.replace(" ", ",").split(",") if a],
                   help="comma-separated arms (default: %(default)s); a list would swallow the subcommand")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="queue rep 0 of every problem on each arm; settle rows already in results.jsonl")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("repeat", help="queue reps 1..N-1 of the repeat subset (or --all); or --rep R for exactly one rep")
    s.add_argument("n", type=int, nargs="?", default=None)
    s.add_argument("--all", action="store_true"); s.add_argument("--subset", default=str(SUBSET))
    s.add_argument("--unsolved", action="store_true", help="only the problems no arm has solved (from results.jsonl)")
    s.add_argument("--rep", type=int, default=None, help="queue exactly this rep index for every arm")
    s.set_defaults(fn=cmd_repeat)
    s = sub.add_parser("launch", help="start one detached worker that drains the queue (spends money)")
    s.add_argument("--owner", default=f"imo-{time.strftime('%m%d-%H%M')}")
    s.add_argument("--timeout", type=int, default=14400)
    s.add_argument("--arms-only", nargs="*", default=None, help="claim only these arms")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true", help="run the checks, start nothing")
    s.set_defaults(fn=cmd_launch)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("stop", help="let the worker finish its current attempt, then stop (writes runs/STOP)")
    s.set_defaults(fn=cmd_stop)
    s = sub.add_parser("report", help="per-problem table and the repeat recommendation")
    s.add_argument("--rep", type=int, default=0); s.set_defaults(fn=cmd_report)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
