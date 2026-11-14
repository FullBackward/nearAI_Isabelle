#!/usr/bin/env python3
"""Replay the open leaves of finished attempts through the server's filler -- no model calls.

Putnam pass finding (docs/putnam-pass-analysis-2026-11-14.md §3): most leaves the filler
left open in the forced arm need the file's own definitions unfolded, and the cheap stage
(`try0`) runs with no facts at all, so a goal like `det2 u u = 0` with `det2` a `definition`
never gets the one rewrite it needs. This script tests that claim for free: it takes the
final `.thy` of each attempt (the file the model left behind, `sorry`s and all), sends it to
`fill_sorries` as-is (`control`) and once more with every leaf written as
`using <the file's definition facts> sorry` (`facts`), and counts what closes.

The rewrite is textual and stays on the same line, so result rows line up across variants.
Facts are the names Isabelle itself generates: `f_def` for `definition f`, `f.simps` for
`fun`/`primrec`/`function f`. `abbreviation`s need nothing (they are folded by the parser).

    .venv/bin/python scripts/replay_leaves.py --results runs-server/putnam        # the forced timeouts
    .venv/bin/python scripts/replay_leaves.py --results runs-server/putnam --problems putnam_1963_a6 putnam_2015_a3
    .venv/bin/python scripts/replay_leaves.py --selftest                           # the rewrite alone, no server

Cost: server CPU only -- about `--timeout` seconds per open leaf per variant (worst case),
nothing on the model key. Files with more than --max-sorries leaves are skipped (the
putnam_1970_a3 skeleton has 267). Output: a table per file and `<results>/../replay_leaves.json`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import ib  # noqa: E402

# ---- the rewrite ----

# A definition command at the start of a line gives one Isabelle-generated fact name.
# `definition f :: ... where` -> f_def; `fun f ... where` / `primrec` / `function` -> f.simps.
_DEF_RE = re.compile(r'^(definition|fun|primrec|function)\s+(?:\(.*?\)\s*)?("?)([A-Za-z_][A-Za-z0-9_\']*)\2', re.M)
# A `sorry` token that ends a proof (not inside a comment or a string); same-line rewrite.
_SORRY_RE = re.compile(r'(?<![\w\'])sorry(?![\w\'])')


def definition_facts(text: str) -> list[str]:
    """The fact names the file's own definitions generate, in order of appearance, deduplicated."""
    out: list[str] = []
    for m in _DEF_RE.finditer(text):
        kind, name = m[1], m[3]
        fact = f"{name}_def" if kind == "definition" else f"{name}.simps"
        if fact not in out:
            out.append(fact)
    return out


_HIDDEN_RE = re.compile(r'\(\*.*?\*\)|"[^"]*"')   # single-line comments and strings


def _sorry_spans(line: str) -> list[tuple[int, int]]:
    """Positions of the proof-ending `sorry` tokens of a line: those outside (* *) comments and
    strings. Single-line only; a `sorry` inside a multi-line comment is rare enough to accept."""
    hidden = [(m.start(), m.end()) for m in _HIDDEN_RE.finditer(line)]
    return [(m.start(), m.end()) for m in _SORRY_RE.finditer(line)
            if not any(a <= m.start() < b for a, b in hidden)]


def with_facts(text: str, facts: list[str]) -> tuple[str, int]:
    """Every proof-ending `sorry` becomes `using <facts> sorry`, on its own line; returns (text, n)."""
    if not facts:
        return text, 0
    using = "using " + " ".join(facts) + " sorry"
    n = 0
    out = []
    for line in text.split("\n"):
        pieces, pos = [], 0
        for a, b in _sorry_spans(line):
            pieces.append(line[pos:a] + using); pos = b; n += 1
        out.append("".join(pieces) + line[pos:])
    return "\n".join(out), n


def count_sorries(text: str) -> int:
    return sum(len(_sorry_spans(l)) for l in text.split("\n"))


def selftest() -> int:
    t = ('theory T imports Main begin\n'
         'definition f :: "nat \\<Rightarrow> nat" where "f n = n + 1"\n'
         'fun g :: "nat \\<Rightarrow> nat" where "g 0 = 0" | "g (Suc n) = g n"\n'
         'abbreviation h where "h \\<equiv> f"\n'
         'lemma a: "f 1 = 2" sorry\n'
         'lemma b: "g n = 0" (* sorry in a comment *)\n'
         '  proof (induct n)\n    case 0 then show ?case sorry\n  next\n    case (Suc n) then show ?case sorry\n  qed\n'
         'lemma c: "sorry_free x = x" sorry\n'
         'end\n')
    assert definition_facts(t) == ["f_def", "g.simps"], definition_facts(t)
    assert count_sorries(t) == 4, count_sorries(t)
    u, n = with_facts(t, definition_facts(t))
    assert n == 4, n
    assert u.count("using f_def g.simps sorry") == 4, u
    assert "(* sorry in a comment *)" in u
    assert '"sorry_free x = x" using f_def g.simps sorry' in u
    assert len(u.split("\n")) == len(t.split("\n"))       # line numbers preserved
    print("replay_leaves selftest ok")
    return 0


# ---- the replay ----

async def replay_file(gym, entry: dict, text: str, label: str, args) -> dict:
    out: dict = {"label": label, "sorries": count_sorries(text)}
    t0 = time.time()
    s = await gym.acquire_session(theories=entry["imports"], field=entry["field"])
    sid, lease = s["session_id"], s["lease_id"]
    try:
        rep = await gym.load_document(sid, text, report=True, timeout=args.load_timeout, lease_id=lease)
        errs = [f"line {c.get('line')}: {m.get('text','')[:160]}"
                for c in (rep.get("commands") or []) for m in (c.get("messages") or []) if m.get("sev") == "error"]
        if errs:
            # a `using` that names a fact the context cannot see is an error at that line; report, do not fill
            out.update(parses=False, errors=errs[:5]); return out
        out["parses"] = True
        total = min(args.max_total, out["sorries"] * args.timeout + 120)
        job = await gym.fill_sorries(sid, text, mode="document", timeout_s=args.timeout, max_total_s=total,
                                     load_timeout=args.load_timeout, lease_id=lease, try0_s=args.try0,
                                     nitpick_s=0, isar=True, split=False, parallel=args.parallel)
        while job.get("status") not in ("done", "cancelled", "error"):
            await asyncio.sleep(5)
            job = await gym.fill_status(sid, lease_id=lease)
        rows = job.get("results") or []
        out["rows"] = [{k: r.get(k) for k in ("line", "outcome", "stage", "method", "goal")} for r in rows]
        out["proved"] = sum(1 for r in rows if r.get("outcome") == "proved" and r.get("method"))
        out["stages"] = job.get("stages") or {}
        if job.get("error"):
            out["error"] = str(job["error"])[:300]
    finally:
        out["elapsed_s"] = round(time.time() - t0, 1)
        try:
            await gym.release_session(sid, lease_id=lease)
        except Exception:  # noqa: BLE001
            pass
    return out


async def main_async(args) -> int:
    from client import PoolAsyncClient  # noqa: E402  (pip install -e Isabelle-Pool-Server/client)
    man = ib.load_manifest()
    results = Path(args.results)
    rows = [json.loads(l) for l in (results / "results.jsonl").open() if l.strip()]
    rows = [r for r in rows if r["arm"] == args.arm and r.get("rep", 0) == args.rep
            and r.get("source", args.source) == args.source]
    if args.problems:
        rows = [r for r in rows if r["problem"] in set(args.problems)]
    else:
        rows = [r for r in rows if r["status"] in ("timeout", "failed", "gave_up")]
    out_path = results.parent / "replay_leaves.json"
    report = json.loads(out_path.read_text()) if out_path.exists() else {}
    async with PoolAsyncClient(args.gym_url, timeout=args.load_timeout + 120) as gym:
        sem = asyncio.Semaphore(args.sessions)

        async def one(r):
            p = r["problem"]
            f = results / args.arm / p / f"rep{args.rep}" / f"{p}.thy"
            if not f.exists() or p not in man:
                print(f"{p}: no final file or not in manifest, skipped", flush=True); return
            text = f.read_text()
            n = count_sorries(text)
            if n == 0 or n > args.max_sorries:
                print(f"{p}: {n} sorries, skipped (0 or > --max-sorries {args.max_sorries})", flush=True); return
            facts = definition_facts(text)
            alt, _ = with_facts(text, facts)
            async with sem:
                ctl = await replay_file(gym, man[p], text, "control", args)
                fx = await replay_file(gym, man[p], alt, "facts", args) if facts else {"label": "facts", "skipped": "no definitions in file"}
            only_facts = []
            if fx.get("rows") and ctl.get("rows"):
                closed_ctl = {r["line"] for r in ctl["rows"] if r["outcome"] == "proved"}
                only_facts = [r for r in fx["rows"] if r["outcome"] == "proved" and r["line"] not in closed_ctl]
            report[p] = dict(status=r["status"], sorries=n, facts=facts, control=ctl, facts_variant=fx,
                             only_with_facts=only_facts)
            out_path.write_text(json.dumps(report, indent=1))
            print(f"{p:16} sorries {n:3}  control {ctl.get('proved','-')!s:>3} ({ctl.get('elapsed_s','-')}s)"
                  f"  facts {fx.get('proved','-')!s:>3} ({fx.get('elapsed_s','-')}s)  closed only with facts: {len(only_facts)}"
                  + (f"  [{ctl.get('errors') or fx.get('errors') or fx.get('skipped') or ''}]" if not (ctl.get('parses') and fx.get('parses')) else ""),
                  flush=True)

        await asyncio.gather(*(one(r) for r in rows))
    tot = sum(v["sorries"] for v in report.values())
    c = sum(v["control"].get("proved", 0) for v in report.values())
    f = sum(v["facts_variant"].get("proved", 0) for v in report.values())
    print(f"\n{len(report)} files, {tot} open leaves: control closed {c}, with definition facts {f} "
          f"(+{sum(len(v['only_with_facts']) for v in report.values())} only with facts) -> {out_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--results", default="runs-server/putnam", help="pass directory holding results.jsonl and <arm>/<problem>/repN/")
    p.add_argument("--source", default="putnambench", help="results.jsonl holds every source's rows")
    p.add_argument("--arm", default="skeleton_forced")
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--problems", nargs="*", help="default: every timeout/failed/gave_up row of the arm")
    p.add_argument("--timeout", type=int, default=30, help="per-sorry sledgehammer budget (the pass used 30)")
    p.add_argument("--try0", type=int, default=5)
    p.add_argument("--parallel", type=int, default=2, help="fill workers inside one session")
    p.add_argument("--sessions", type=int, default=2, help="concurrent sessions (1.5-4 GB each)")
    p.add_argument("--max-total", type=float, default=3600.0)
    p.add_argument("--max-sorries", type=int, default=60)
    p.add_argument("--load-timeout", type=float, default=300.0)
    p.add_argument("--gym-url", default=ib.GYM_URL)
    args = p.parse_args()
    if args.selftest:
        return selftest()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
