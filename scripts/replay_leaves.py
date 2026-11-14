#!/usr/bin/env python3
"""Replay the open leaves of finished attempts through the server -- no model calls.

Putnam pass finding (docs/putnam-pass-analysis-2026-11-14.md §3): most leaves the filler
left open in the forced arm need the file's own definitions unfolded or a heuristic method
with facts, and the filler's cheap stage runs `try0` with no facts at all. This script tests
that claim for free on each failed attempt's final `.thy` (the file the model left behind,
`sorry`s and all). Three measurements per file:

  control     the file sent to `fill_sorries` as-is: what the filler closes on a quiet server
  facts       every leaf rewritten to `unfolding <f_def ...> using <g.simps ...> sorry`, then
              the same fill: the filler with the file's definitions in view
  heuristics  every leaf rewritten to `by <method>` for each method of HEURISTICS (DSP's
              list with the file's definitions and the intro families real-analysis leaves
              need), the document loaded once per method, a leaf counted closed when its
              line carries no error. This is the Section 7 item-1 probe, measured directly.

Every rewrite stays on the leaf's own line, so result rows line up across variants.
Facts are the names Isabelle generates: `f_def` for `definition f`, `f.simps` for
`fun`/`primrec`/`function f`; `abbreviation`s need nothing.

    .venv/bin/python scripts/replay_leaves.py --results runs            # the forced failures
    .venv/bin/python scripts/replay_leaves.py --results runs --problems putnam_1963_a6
    .venv/bin/python scripts/replay_leaves.py --results runs --skip-done # continue a run
    .venv/bin/python scripts/replay_leaves.py --selftest                # the rewrites, no server

Cost: server CPU only. A fill variant is about --timeout seconds per leaf worst case; a
heuristic pass is one document load per method (bounded by --load-timeout). Files with more
than --max-sorries leaves are skipped (the putnam_1970_a3 skeleton has 267). Output: a line
per file and `<results>/../replay_leaves.json`. A file whose session fails is recorded with
its error and the run goes on.
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

# ---- the rewrites ----

# A definition command at the start of a line gives one Isabelle-generated fact name.
_DEF_RE = re.compile(r'^(definition|fun|primrec|function)\s+(?:\(.*?\)\s*)?("?)([A-Za-z_][A-Za-z0-9_\']*)\2', re.M)
_SORRY_RE = re.compile(r'(?<![\w\'])sorry(?![\w\'])')
_HIDDEN_RE = re.compile(r'\(\*.*?\*\)|"[^"]*"')   # single-line comments and strings

# The heuristic methods, DSP (Jiang et al. 2023, §4.2) plus the intro families of §3 kind 2.
# Each builder takes the file's `*_def` names and `*.simps` names and returns a method text.
def _with(facts: list[str], head: str, tail: str = "") -> str:
    mod = "add:" if head == "simp" else "simp add:"     # `simp add: ...` but `auto simp add: ...`
    return f"({head} {mod} {' '.join(facts)}{tail})" if facts else (f"({head}{tail})" if tail else head)


HEURISTICS = {
    "simp+algebra_simps": lambda d, s: _with(d + s + ["algebra_simps"], "simp"),
    "auto+field_simps": lambda d, s: _with(d + s + ["field_simps"], "auto"),
    "fastforce": lambda d, s: _with(d + s, "fastforce"),
    "auto+intros": lambda d, s: _with(d + s, "auto", " intro!: continuous_intros tendsto_eq_intros derivative_eq_intros"),
    "unfold+algebra": lambda d, s: f"(unfold {' '.join(d)}, algebra)" if d else "algebra",
    "linarith": lambda d, s: "linarith",
}


def definition_facts(text: str) -> tuple[list[str], list[str]]:
    """(`*_def` names, `*.simps` names) the file's own definitions generate, in order, deduplicated."""
    defs: list[str] = []
    simps: list[str] = []
    for m in _DEF_RE.finditer(text):
        kind, name = m[1], m[3]
        tgt, fact = (defs, f"{name}_def") if kind == "definition" else (simps, f"{name}.simps")
        if fact not in tgt:
            tgt.append(fact)
    return defs, simps


def _sorry_spans(line: str) -> list[tuple[int, int]]:
    """Positions of the proof-ending `sorry` tokens of a line (outside comments and strings)."""
    hidden = [(m.start(), m.end()) for m in _HIDDEN_RE.finditer(line)]
    return [(m.start(), m.end()) for m in _SORRY_RE.finditer(line)
            if not any(a <= m.start() < b for a, b in hidden)]


def rewrite_sorries(text: str, replacement: str) -> tuple[str, list[int]]:
    """Every proof-ending `sorry` becomes `replacement`, on its own line; returns (text, 1-based lines)."""
    lines_hit: list[int] = []
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        pieces, pos = [], 0
        for a, b in _sorry_spans(line):
            pieces.append(line[pos:a] + replacement); pos = b; lines_hit.append(i)
        out.append("".join(pieces) + line[pos:])
    return "\n".join(out), lines_hit


def facts_prefix(defs: list[str], simps: list[str]) -> str:
    parts = []
    if defs:
        parts.append("unfolding " + " ".join(defs))
    if simps:
        parts.append("using " + " ".join(simps))
    return " ".join(parts)


def with_facts(text: str, defs: list[str], simps: list[str]) -> tuple[str, int]:
    prefix = facts_prefix(defs, simps)
    if not prefix:
        return text, 0
    t, hit = rewrite_sorries(text, prefix + " sorry")
    return t, len(hit)


def with_method(text: str, name: str, defs: list[str], simps: list[str]) -> tuple[str, list[int]]:
    return rewrite_sorries(text, "by " + HEURISTICS[name](defs, simps))


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
    defs, simps = definition_facts(t)
    assert (defs, simps) == (["f_def"], ["g.simps"]), (defs, simps)
    assert count_sorries(t) == 4, count_sorries(t)
    u, n = with_facts(t, defs, simps)
    assert n == 4 and u.count("unfolding f_def using g.simps sorry") == 4, u
    assert "(* sorry in a comment *)" in u and '"sorry_free x = x" unfolding f_def' in u
    assert len(u.split("\n")) == len(t.split("\n"))
    v, lines = with_method(t, "simp+algebra_simps", defs, simps)
    assert lines == [5, 8, 10, 12] and v.count("by (simp add: f_def g.simps algebra_simps)") == 4, v
    r = {k: b(defs, simps) for k, b in HEURISTICS.items()}
    assert r["unfold+algebra"] == "(unfold f_def, algebra)" and r["fastforce"] == "(fastforce simp add: f_def g.simps)", r
    assert r["auto+intros"] == "(auto simp add: f_def g.simps intro!: continuous_intros tendsto_eq_intros derivative_eq_intros)", r
    r0 = {k: b([], []) for k, b in HEURISTICS.items()}
    assert r0["unfold+algebra"] == "algebra" and r0["fastforce"] == "fastforce" and r0["linarith"] == "linarith", r0
    assert r0["simp+algebra_simps"] == "(simp add: algebra_simps)", r0
    assert r["auto+field_simps"] == "(auto simp add: f_def g.simps field_simps)", r
    assert r0["auto+intros"] == "(auto intro!: continuous_intros tendsto_eq_intros derivative_eq_intros)", r0
    rep = {"timed_out": True, "commands": [
        {"line": 5, "status": "ok", "messages": []}, {"line": 5, "status": "ok", "messages": []},
        {"line": 8, "status": "ok", "messages": []}, {"line": 8, "status": "failed", "messages": [{"sev": "error", "text": "Failed"}]},
        {"line": 10, "status": "running", "messages": []},
    ]}
    assert leaf_verdicts(rep, [5, 8, 10, 12]) == {5: "closed", 8: "failed", 10: "unknown", 12: "unknown"}, leaf_verdicts(rep, [5, 8, 10, 12])
    assert _errors(rep) == {8: "Failed"}
    print("replay_leaves selftest ok")
    return 0


# ---- the replay ----

class _Session:
    """acquire / load / release with one retry when the session is gone (404 between calls)."""

    def __init__(self, gym, entry: dict, args):
        self.gym, self.entry, self.args = gym, entry, args
        self.sid = self.lease = None

    async def __aenter__(self):
        s = await self.gym.acquire_session(theories=self.entry["imports"], field=self.entry["field"])
        self.sid, self.lease = s["session_id"], s["lease_id"]
        return self

    async def __aexit__(self, *exc):
        try:
            await self.gym.release_session(self.sid, lease_id=self.lease)
        except Exception:  # noqa: BLE001
            pass

    async def load(self, text: str, timeout: float | None = None) -> dict:
        """Load the document; returns the server's per-command *report* (`{timed_out, commands,
        success, error}`, nested under `report` in the client's response). A 404 (session gone)
        gets one fresh session."""
        for attempt in (1, 2):
            try:
                resp = await self.gym.load_document(self.sid, text, report=True,
                                                    timeout=timeout or self.args.load_timeout, lease_id=self.lease)
                return resp.get("report") or {}
            except Exception as e:  # noqa: BLE001
                if attempt == 2 or "404" not in str(e):
                    raise
                s = await self.gym.acquire_session(theories=self.entry["imports"], field=self.entry["field"])
                self.sid, self.lease = s["session_id"], s["lease_id"]
        return {}


def _errors(report: dict) -> dict[int, str]:
    out: dict[int, str] = {}
    for c in (report.get("commands") or []):
        for m in (c.get("messages") or []):
            if m.get("sev") == "error":
                out.setdefault(int(c.get("line") or 0), str(m.get("text", ""))[:160])
    return out


def leaf_verdicts(report: dict, lines: list[int]) -> dict[int, str]:
    """closed / failed / unknown per leaf line. A line may start several commands (`have ... by ...`
    on one line is two); the leaf is closed only if every command starting on that line has
    status `ok` and no error message; `failed` on any is failed; a command still `running` or
    `unprocessed` (the load timed out before reaching it) is unknown; a line the report never
    mentions is unknown too."""
    per_line: dict[int, list[dict]] = {}
    for c in (report.get("commands") or []):
        per_line.setdefault(int(c.get("line") or 0), []).append(c)
    out = {}
    for ln in lines:
        cmds = per_line.get(ln)
        if not cmds:
            out[ln] = "unknown"; continue
        statuses = {c.get("status") for c in cmds}
        has_err = any(m.get("sev") == "error" for c in cmds for m in (c.get("messages") or []))
        if has_err or "failed" in statuses:
            out[ln] = "failed"
        elif statuses <= {"ok"}:
            out[ln] = "closed"
        else:
            out[ln] = "unknown"
    return out


async def fill_variant(s: _Session, text: str, label: str, args) -> dict:
    out: dict = {"label": label, "sorries": count_sorries(text)}
    t0 = time.time()
    report = await s.load(text)
    errs = _errors(report)
    if errs:   # a rewrite the context rejects (a fact name out of scope) is an error at that line
        out.update(parses=False, errors=[f"line {k}: {v}" for k, v in sorted(errs.items())[:5]],
                   elapsed_s=round(time.time() - t0, 1))
        return out
    out["parses"] = True
    if report.get("timed_out"):
        out["load_timed_out"] = True   # the fill then runs on a document still being checked
    total = min(args.max_total, out["sorries"] * args.timeout + 120)
    job = await s.gym.fill_sorries(s.sid, text, mode="document", timeout_s=args.timeout, max_total_s=total,
                                   load_timeout=args.load_timeout, lease_id=s.lease, try0_s=args.try0,
                                   nitpick_s=0, isar=True, split=False, parallel=args.parallel)
    while job.get("status") not in ("done", "cancelled", "error"):
        await asyncio.sleep(5)
        job = await s.gym.fill_status(s.sid, lease_id=s.lease)
    rows = job.get("results") or []
    out["rows"] = [{k: r.get(k) for k in ("line", "outcome", "stage", "method", "goal")} for r in rows]
    out["proved"] = sum(1 for r in rows if r.get("outcome") == "proved" and r.get("method"))
    out["stages"] = job.get("stages") or {}
    if job.get("error"):
        out["error"] = str(job["error"])[:300]
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


async def heuristic_variant(s: _Session, text: str, defs: list[str], simps: list[str], args) -> dict:
    """For each method: load the document with every leaf closed by it; a leaf is closed when
    its line has no error. Returns per-method closed lines and the union."""
    out: dict = {"methods": {}, "closed_any": []}
    closed_any: set[int] = set()
    for h in HEURISTICS:
        t0 = time.time()
        doc, lines = with_method(text, h, defs, simps)
        try:
            report = await s.load(doc, timeout=args.heur_timeout)
        except Exception as e:  # noqa: BLE001
            out["methods"][h] = {"error": f"{type(e).__name__}: {e}"[:200], "elapsed_s": round(time.time() - t0, 1)}
            continue
        verdicts = leaf_verdicts(report, lines)
        closed = [ln for ln, v in verdicts.items() if v == "closed"]
        unknown = [ln for ln, v in verdicts.items() if v == "unknown"]
        # an error elsewhere than a leaf line means the document itself broke (should not happen:
        # the control variant loaded clean); record it so the count is not trusted blindly
        foreign = {k: v for k, v in _errors(report).items() if k not in lines}
        out["methods"][h] = {"closed": closed, "n": len(closed), "unknown": len(unknown),
                             "timed_out": bool(report.get("timed_out")), "elapsed_s": round(time.time() - t0, 1),
                             **({"foreign_errors": list(foreign.items())[:3]} if foreign else {})}
        closed_any |= set(closed)
    out["closed_any"] = sorted(closed_any)
    return out


async def replay_one(gym, entry: dict, text: str, args) -> dict:
    defs, simps = definition_facts(text)
    rec: dict = {"sorries": count_sorries(text), "defs": defs, "simps": simps}
    async with _Session(gym, entry, args) as s:
        rec["control"] = await fill_variant(s, text, "control", args)
        if defs or simps:
            alt, _ = with_facts(text, defs, simps)
            rec["facts"] = await fill_variant(s, alt, "facts", args)
        else:
            rec["facts"] = {"label": "facts", "skipped": "no definitions in file"}
        if not args.no_heuristics:
            rec["heuristics"] = await heuristic_variant(s, text, defs, simps, args)
    ctl_closed = {r["line"] for r in rec["control"].get("rows", []) if r["outcome"] == "proved"}
    fx_closed = {r["line"] for r in rec["facts"].get("rows", []) if r["outcome"] == "proved"}
    h_closed = set(rec.get("heuristics", {}).get("closed_any", []))
    rec["only_facts"] = sorted(fx_closed - ctl_closed)
    rec["only_heuristics"] = sorted(h_closed - ctl_closed - fx_closed)
    rec["closed_by_any"] = sorted(ctl_closed | fx_closed | h_closed)
    return rec


def _fmt(v: dict) -> str:
    if "skipped" in v:
        return "  -  "
    if v.get("parses") is False:
        return " err "
    return f"{v.get('proved', '-')!s:>3} ({v.get('elapsed_s', '-')}s)"


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
    lock = asyncio.Lock()
    async with PoolAsyncClient(args.gym_url, timeout=args.load_timeout + 120) as gym:
        sem = asyncio.Semaphore(args.sessions)

        async def one(r):
            p = r["problem"]
            if args.skip_done and p in report and "error" not in report[p]:
                return
            f = results / args.arm / p / f"rep{args.rep}" / f"{p}.thy"
            if not f.exists() or p not in man:
                print(f"{p}: no final file or not in manifest, skipped", flush=True); return
            text = f.read_text()
            n = count_sorries(text)
            if n == 0 or n > args.max_sorries:
                print(f"{p}: {n} sorries, skipped (0 or > --max-sorries {args.max_sorries})", flush=True); return
            async with sem:
                try:
                    rec = await replay_one(gym, man[p], text, args)
                except Exception as e:  # noqa: BLE001
                    rec = {"sorries": n, "error": f"{type(e).__name__}: {e}"[:300]}
            rec["status"] = r["status"]
            async with lock:
                report[p] = rec
                out_path.write_text(json.dumps(report, indent=1))
            if "error" in rec:
                print(f"{p:16} sorries {n:3}  ERROR {rec['error']}", flush=True); return
            hs = rec.get("heuristics", {}).get("methods", {})
            hline = " ".join(f"h{i}={v.get('n', 'err')}" + (f"?{v['unknown']}" if v.get("unknown") else "")
                             for i, v in enumerate(hs.values(), 1)) if hs else "heuristics off"
            print(f"{p:16} sorries {n:3}  control {_fmt(rec['control'])}  facts {_fmt(rec['facts'])}  "
                  f"{hline}  closed by any: {len(rec['closed_by_any'])}"
                  + (f"  [{rec['control'].get('errors') or rec['facts'].get('errors')}]"
                     if rec['control'].get('parses') is False or rec['facts'].get('parses') is False else ""),
                  flush=True)

        await asyncio.gather(*(one(r) for r in rows))
    done = {p: v for p, v in report.items() if "error" not in v}
    tot = sum(v["sorries"] for v in done.values())
    c = sum(v["control"].get("proved", 0) for v in done.values())
    f = sum(v["facts"].get("proved", 0) for v in done.values())
    h = sum(len(v.get("heuristics", {}).get("closed_any", [])) for v in done.values())
    a = sum(len(v["closed_by_any"]) for v in done.values())
    print(f"\n{len(done)} files, {tot} open leaves: control {c}, facts {f}, heuristics {h}, "
          f"any {a} (+{sum(len(v['only_facts']) for v in done.values())} only facts, "
          f"+{sum(len(v['only_heuristics']) for v in done.values())} only heuristics) -> {out_path}")
    for i, hname in enumerate(HEURISTICS, 1):
        print(f"  h{i} = {hname}: {HEURISTICS[hname](['f_def'], [])}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--results", default="runs-server/putnam", help="pass directory holding results.jsonl and <arm>/<problem>/repN/")
    p.add_argument("--source", default="putnambench", help="results.jsonl holds every source's rows")
    p.add_argument("--arm", default="skeleton_forced")
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--problems", nargs="*", help="default: every timeout/failed/gave_up row of the arm")
    p.add_argument("--skip-done", action="store_true", help="leave files already in replay_leaves.json alone")
    p.add_argument("--no-heuristics", action="store_true")
    p.add_argument("--timeout", type=int, default=30, help="per-sorry sledgehammer budget (the pass used 30)")
    p.add_argument("--try0", type=int, default=5)
    p.add_argument("--parallel", type=int, default=2, help="fill workers inside one session")
    p.add_argument("--sessions", type=int, default=2, help="concurrent sessions (1.5-4 GB each)")
    p.add_argument("--max-total", type=float, default=3600.0)
    p.add_argument("--max-sorries", type=int, default=60)
    p.add_argument("--load-timeout", type=float, default=300.0)
    p.add_argument("--heur-timeout", type=float, default=180.0,
                   help="document load budget per heuristic method; leaves not reached count as unknown (h=n?k)")
    p.add_argument("--gym-url", default=ib.GYM_URL)
    args = p.parse_args()
    if args.selftest:
        return selftest()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
