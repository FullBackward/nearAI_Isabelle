"""Follow every fill job to its final state, sum scratch calls with a long timeout, pair dead-session errors with the preceding call.

Usage: .venv/bin/python scripts/analysis/rep1_fills.py <runs dir, e.g. runs-server/rep1> [problem ...]
Written for the rep-1 forced pass (2026-11-11); see docs/rep1-analysis-2026-11-11.md."""
import sys
RUNS = sys.argv[1]
ARGS = sys.argv[2:]
import json, re, collections, pathlib
root = pathlib.Path(RUNS)/"skeleton_forced"
def J(s):
    try: return json.loads(s)
    except Exception: return None
for p in ["imo_2026_p1","imo_2026_p2","imo_2026_p3","imo_2026_p4","imo_2026_p5","imo_2026_p6"]:
    recs=[json.loads(l) for l in open(root/p/"rep1"/"transcript.jsonl")]
    mcp=[r for r in recs if r["kind"]=="mcp"]
    print("="*90); print(p)
    # fills with their polling tail
    i=0; abandoned=0; skipped_final=0; already=0; fills=0
    while i < len(mcp):
        r=mcp[i]
        if r["name"]=="isabelle_fill_sorries":
            fills+=1
            d=J(r["result"]) or {}
            a=J(r["arguments"]) or {}
            polls=0; wall=r["elapsed_s"]; j=i+1; last=d
            while j < len(mcp) and mcp[j]["name"]=="isabelle_fill_status":
                polls+=1; wall+=mcp[j]["elapsed_s"]+5; last=J(mcp[j]["result"]) or last; j+=1
            st=last.get("status"); cont=last.get("continuing")
            outs=collections.Counter(t.get("outcome") for t in last.get("results") or [])
            if cont: abandoned+=1
            if outs.get("skipped") and not cont: skipped_final+=1
            if "already running" in r["result"]: already+=1
            flag = " <-- LEFT RUNNING" if cont else (" <-- skipped in final" if outs.get("skipped") else "")
            if cont or outs.get("skipped") or d.get("error"):
                print(f"  fill n{r['n']} timeout_s={a.get('timeout_s')} max_total={a.get('max_total_s')} patience={a.get('patience_s')} polls={polls} wall~{wall:.0f}s final status={st} continuing={cont} outcomes={dict(outs)} err={d.get('error')}{flag}")
            i=j
        else: i+=1
    print(f"  fills={fills} left_running={abandoned} skipped_in_final={skipped_final} already_running={already}")
    # scratch time with timeout>180 and session_gone pairing
    long_t=0; n_long=0; pairs=[]
    prev=None
    for r in mcp:
        if r["name"] in ("isabelle_run_code","isabelle_multi_attempt"):
            a=J(r["arguments"]) or {}; d=J(r["result"]); d=d if isinstance(d,dict) else {}
            t=a.get("timeout") or a.get("timeout_s")
            if t and float(t)>180: long_t+=r["elapsed_s"]; n_long+=1
            err=str(d.get("error") or "")
            if "session_gone" in err or "died" in err:
                pd=(J(prev["result"]) if prev else None); pe = str(pd.get("error") or "")[:50] if isinstance(pd,dict) else None
                pairs.append((r["n"], r["name"], err[:30], prev["n"] if prev else None, prev["name"] if prev else None, pe))
            prev=r
    print(f"  scratch calls with timeout>180: {n_long}, {long_t/60:.0f} min")
    for x in pairs: print("  gone:", x)
    errs=collections.Counter()
    for r in mcp:
        d=J(r["result"]); d=d if isinstance(d,dict) else {}
        e=str(d.get("error") or "")
        if re.search(r"http_|already running|busy|exhausted|memory", e): errs[(r["name"], e[:40])]+=1
    print("  http/busy errors:", dict(errs))
