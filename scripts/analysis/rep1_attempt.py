"""Per-attempt timeline of a skeleton_forced run: time split, slowest calls, every fill call, errors, write_file results, turns without a tool call, remaining sorries.

Usage: .venv/bin/python scripts/analysis/rep1_attempt.py <runs dir, e.g. runs-server/rep1> [problem ...]
Written for the rep-1 forced pass (2026-11-11); see docs/rep1-analysis-2026-11-11.md."""
import sys
RUNS = sys.argv[1]
ARGS = sys.argv[2:]
import json, sys, re, collections, pathlib
root = pathlib.Path(RUNS)/"skeleton_forced"
probs = ARGS or ["imo_2026_p1","imo_2026_p2","imo_2026_p3","imo_2026_p4","imo_2026_p5","imo_2026_p6"]
def J(s):
    try: return json.loads(s)
    except Exception: return None
for p in probs:
    d = root/p/"rep1"
    recs = [json.loads(l) for l in open(d/"transcript.jsonl")]
    chat = [r for r in recs if r["kind"]=="chat"]; tools=[r for r in recs if r["kind"]=="tool"]; mcp=[r for r in recs if r["kind"]=="mcp"]
    print("="*100); print(p, "records", len(recs), "chat", len(chat), "tool", len(tools), "mcp", len(mcp))
    t_model = sum(r["elapsed_s"] for r in chat); t_tool = sum(r.get("elapsed_s") or 0 for r in tools)
    by = collections.defaultdict(float); cnt=collections.Counter()
    for r in tools: by[r["name"]] += r.get("elapsed_s") or 0; cnt[r["name"]]+=1
    print(f"time: model {t_model/60:.0f} min, tools {t_tool/60:.0f} min; per tool (min/count):", {k:(round(v/60,1),cnt[k]) for k,v in sorted(by.items(), key=lambda kv:-kv[1])})
    slow = sorted(chat, key=lambda r:-r["elapsed_s"])[:3]
    print("slowest model calls (s):", [(r["n"], round(r["elapsed_s"]), (r.get("usage") or {}).get("prompt_tokens")) for r in slow])
    slowt = sorted(tools, key=lambda r:-(r.get("elapsed_s") or 0))[:5]
    print("slowest tool calls (s):", [(r["n"], r["name"], round(r.get("elapsed_s") or 0)) for r in slowt])
    # fills
    print("-- fill calls (mcp isabelle_fill_sorries):")
    for r in mcp:
        if r["name"]!="isabelle_fill_sorries": continue
        res = J(r["result"]) if isinstance(r["result"], str) else r["result"]
        a = J(r["arguments"]) or {}
        if isinstance(res, dict):
            out = collections.Counter((t.get("outcome"), t.get("stage")) for t in res.get("targets") or res.get("results") or [])
            keys = {k: res[k] for k in ("status","proved","total","elapsed_s","error","stages","parallel","timed_out","job_id") if k in res}
            print(f"   n{r['n']} {r['elapsed_s']:.0f}s args={ {k:v for k,v in a.items() if k!='file_path'} } {keys} outcomes={dict(out)}")
        else:
            print(f"   n{r['n']} {r['elapsed_s']:.0f}s raw={str(r['result'])[:200]}")
    # errors in mcp results
    errs = collections.Counter()
    for r in mcp:
        res = J(r["result"]) if isinstance(r["result"], str) else r["result"]
        if isinstance(res, dict) and res.get("error"): errs[(r["name"], str(res["error"])[:80])]+=1
        elif isinstance(r["result"], str) and re.search(r"http_5|Internal server|Traceback|timed out|scratch_exhausted|memory_pressure", r["result"]): errs[(r["name"], re.search(r"http_5|Internal server|Traceback|timed out|scratch_exhausted|memory_pressure", r["result"]).group(0))]+=1
    print("-- mcp errors:", dict(errs))
    # rejections and fill summaries from write_file results
    print("-- write_file results:")
    for r in tools:
        if r["name"]!="write_file": continue
        res = r["result"] or ""
        head = res.splitlines()[0][:160] if res else ""
        m = re.search(r"(\d+)/(\d+) sorr", res)
        print(f"   n{r['n']} step{r['step']} {round(r.get('elapsed_s') or 0)}s :: {head}" + (f"  [fill {m.group(0)}]" if m else ""))
    # stops
    print("-- turns without a tool call:")
    for r in chat:
        resp = r.get("response") or {}
        if not resp.get("tool_calls"):
            print(f"   n{r['n']} fin={r.get('finish_reason')} content={ (resp.get('content') or '')[:220]!r}")
    # final theory
    thy = (d/f"{p}.thy").read_text()
    lines = thy.splitlines()
    sor = [i for i,l in enumerate(lines) if re.search(r"\bsorry\b", l)]
    print(f"-- final theory: {len(lines)} lines, {len(sor)} sorry lines, verified.thy exists: {(d/'verified.thy').exists()}")
    for i in sor[:12]:
        ctx = " ".join(lines[max(0,i-1):i+1]).strip()
        print("   ", i+1, ctx[:160])
