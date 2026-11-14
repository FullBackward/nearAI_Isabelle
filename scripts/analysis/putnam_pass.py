"""The Putnam pass (rep 0, 2026-11-12/13) read from the retrieved attempts: per-attempt time by tool,
fill rounds (automatic and explicit), timed-out scratch runs, open goals of the forced timeouts.

Usage: .venv/bin/python scripts/analysis/putnam_pass.py stats|fills|timeouts
Writes runs-server/putnam_stats.json and runs-server/putnam_fills.json (gitignored with runs-server/).
Written for docs/putnam-pass-analysis-2026-11-14.md; each pass streams the transcripts
(5.7 GB for 72 attempts), so it takes a few minutes."""
import sys


def _stats():
    import json, re, sys, collections, pathlib
    ROOT = pathlib.Path("/Users/winstonren/GitHub/nearAI_Isabelle/runs-server/putnam")
    rows = [json.loads(l) for l in open(ROOT / "results.jsonl") if l.strip()]
    rows = [r for r in rows if r.get("source") == "putnambench"]
    FILL_RE = re.compile(r"fill_sorries: (\d+)/(\d+) sorry\(s\) proved")
    OPEN_RE = re.compile(r"\[open (\d+)\]")
    STAGE_RE = re.compile(r"^\s+line \d+: (\w[\w-]*)", re.M)
    COMPUTE = ("value ", "nitpick", "quickcheck", "eval ", "ML ", "ML_val", "normalization", "code_simp")
    out = []
    for r in rows:
        d = ROOT / r["arm"] / r["problem"] / f"rep{r['rep']}"
        tp = d / "transcript.jsonl"
        st = dict(problem=r["problem"], arm=r["arm"], status=r["status"], wall=r["elapsed_s"], cat=r.get("category"),
                  cmpl=r["tokens"]["completion"], uncached=r["tokens"]["prompt"] - r["tokens"]["cached"], calls=r["tokens"]["calls"],
                  writes=r.get("writes", 0), rej=r.get("rejected_writes", 0), leaf_rej=r.get("leaf_rejections", 0),
                  fills=r.get("fills", 0), auto_fills=r.get("auto_fills", 0), fs_total=r.get("fill_sorries_total", 0),
                  fs_proved=r.get("fill_sorries_proved", 0), stages=r.get("fill_stages") or {}, sh_calls=r.get("sledgehammer_calls", 0),
                  sh_found=r.get("sledgehammer_found", 0), tool_time=r.get("tool_time_s", 0), nudges=r.get("nudges", 0),
                  length_turns=r.get("length_turns", 0), verify=(r.get("verify") or "")[:120])
        model_s = 0.0; tool_s = collections.Counter(); tool_n = collections.Counter()
        fill_calls = []; compute_n = collections.Counter(); run_code_n = 0; rejections = []; stops = []
        last_chat = ""; nturns = 0; reasoning_chars = 0; sorry_traj = []
        fill_open_last = None; fill_goals_last = []
        if tp.exists():
            with open(tp) as f:
                for ln in f:
                    try: rec = json.loads(ln)
                    except json.JSONDecodeError: continue
                    k = rec.get("kind")
                    if k == "chat":
                        nturns += 1
                        model_s += float(rec.get("elapsed_s") or 0)
                        resp = rec.get("response") or {}
                        reasoning_chars += len(resp.get("reasoning_content") or "")
                        if not resp.get("tool_calls"):
                            c = (resp.get("content") or "").strip()
                            if c: stops.append(c[:300]); last_chat = c[:600]
                    elif k == "tool":
                        name = rec.get("name", "?"); el = float(rec.get("elapsed_s") or 0)
                        tool_s[name] += el; tool_n[name] += 1
                        res = rec.get("result") or ""; args = rec.get("arguments") or ""
                        if name == "isabelle_run_code":
                            run_code_n += 1
                            for kw in COMPUTE:
                                if kw in args: compute_n[kw.strip()] += 1
                        if name == "isabelle_fill_sorries" or name.endswith("fill_sorries"):
                            m = FILL_RE.search(res)
                            if m:
                                o = OPEN_RE.search(res)
                                stages = collections.Counter(STAGE_RE.findall(res))
                                fill_calls.append(dict(proved=int(m[1]), total=int(m[2]), open=int(o[1]) if o else None,
                                                       elapsed=el, args=args[:80], stages=dict(stages)))
                                fill_open_last = int(o[1]) if o else None
                                fill_goals_last = re.findall(r"goal: (.{0,140})", res)[:6]
                            elif "refused" in res:
                                fill_calls.append(dict(refused=res[:100], elapsed=el))
                        if name == "write_file":
                            if "REJECTED" in res or "rejected" in res[:200]:
                                rejections.append(res[:200])
                            m2 = re.search(r"(\d+) sorr", res)
                            if m2: sorry_traj.append(int(m2[1]))
        st.update(model_s=model_s, tool_s=dict(tool_s), tool_n=dict(tool_n), nturns=nturns, reasoning_chars=reasoning_chars,
                  fill_calls=fill_calls, compute=dict(compute_n), run_code=run_code_n, rejections=rejections,
                  stops=stops[-3:], n_stops=len(stops), last_chat=last_chat, sorry_traj=sorry_traj[-12:],
                  fill_open_last=fill_open_last, fill_goals_last=fill_goals_last)
        out.append(st)
        print(r["arm"], r["problem"], r["status"], f"turns {nturns} model {model_s/60:.0f}m tool {sum(tool_s.values())/60:.0f}m", file=sys.stderr, flush=True)
    json.dump(out, open(ROOT.parent.parent / "runs-server" / "putnam_stats.json", "w"), indent=1)
    print("written", len(out))


def _fills():
    import json, re, collections, pathlib
    ROOT = pathlib.Path("/Users/winstonren/GitHub/nearAI_Isabelle/runs-server/putnam")
    rows = [json.loads(l) for l in open(ROOT / "results.jsonl") if l.strip()]
    rows = [r for r in rows if r.get("source") == "putnambench" and r["arm"] == "skeleton_forced"]
    FILL_RE = re.compile(r"fill_sorries: (\d+)/(\d+) sorry\(s\) proved(?: \[([^\]]*)\])?")
    ROW_RE = re.compile(r"^\s+line (\d+): (\S+)(.*)$", re.M)
    out = {}
    for r in rows:
        d = ROOT / r["arm"] / r["problem"] / f"rep{r['rep']}"
        rounds = []; stops = []; last_open_goals = []; cum_open = collections.Counter()
        with open(d / "transcript.jsonl") as f:
            for ln in f:
                try: rec = json.loads(ln)
                except json.JSONDecodeError: continue
                if rec.get("kind") == "chat":
                    resp = rec.get("response") or {}
                    if not resp.get("tool_calls"):
                        c = (resp.get("content") or "").strip()
                        if c: stops.append(c[:500])
                if rec.get("kind") != "tool": continue
                name = rec.get("name", ""); res = rec.get("result") or ""
                if name not in ("write_file", "isabelle_fill_sorries"): continue
                m = FILL_RE.search(res)
                if not m: continue
                stage = collections.Counter(); open_goals = []
                for lm in ROW_RE.finditer(res):
                    stage[lm[2]] += 1
                for g in re.findall(r"goal: (.{0,160})", res):
                    open_goals.append(g)
                rounds.append(dict(kind="auto" if name == "write_file" else "explicit", proved=int(m[1]), total=int(m[2]),
                                   note=m[3] or "", elapsed=float(rec.get("elapsed_s") or 0), stages=dict(stage), open_goals=open_goals[:8]))
                if open_goals: last_open_goals = open_goals[:8]
        out[r["problem"]] = dict(status=r["status"], wall=r["elapsed_s"], rounds=rounds, stops=stops[-3:], n_stops=len(stops),
                                 last_open_goals=last_open_goals, final_sorries=len(re.findall(r"\bsorry\b", (d / f"{r['problem']}.thy").read_text())))
        print(r["problem"], r["status"], "rounds", len(rounds), "sent", sum(x["total"] for x in rounds), "proved", sum(x["proved"] for x in rounds), flush=True)
    json.dump(out, open(ROOT.parent / "putnam_fills.json", "w"), indent=1)


def _timeouts():
    import json,re,collections,pathlib,statistics as st
    ROOT=pathlib.Path("/Users/winstonren/GitHub/nearAI_Isabelle/runs-server/putnam")
    rows=[json.loads(l) for l in open(ROOT/"results.jsonl") if l.strip()]
    cls=collections.defaultdict(collections.Counter); tcls=collections.defaultdict(collections.Counter); el=collections.defaultdict(list)
    def kind(a):
        if re.search(r'\b(value|eval|normalization|quickcheck|nitpick)\b',a): return "compute"
        if re.search(r'\bsledgehammer\b|\btry\b|\btry0\b',a): return "hammer/try"
        if re.search(r'\b(fun|function|definition|primrec)\b',a): return "defs+proof"
        if re.search(r'\b(lemma|theorem|have|show)\b',a): return "proof"
        return "other"
    for r in rows:
        if r.get("source")!="putnambench": continue
        d=ROOT/r["arm"]/r["problem"]/"rep0"
        try: f=open(d/"transcript.jsonl")
        except FileNotFoundError: continue
        for l in f:
            try: rec=json.loads(l)
            except json.JSONDecodeError: continue
            if rec.get("kind")!="tool" or rec.get("name")!="isabelle_run_code": continue
            a=rec.get("arguments") or ""; res=rec.get("result") or ""; e=float(rec.get("elapsed_s") or 0)
            k=kind(a); el[r["arm"]].append(e)
            if "timed out" in res: tcls[r["arm"]][k]+=1; cls[r["arm"]][(k,"t")]+=e
    for arm in ("plain","skeleton_forced"):
        print(arm, "run_code elapsed median", st.median(el[arm]), "p90", st.quantiles(el[arm],n=10)[8])
        print("   timed-out calls by kind:", dict(tcls[arm]), "| hours:", {k[0]:round(v/3600,1) for k,v in cls[arm].items()})


if __name__ == "__main__":
    {"stats": _stats, "fills": _fills, "timeouts": _timeouts}[sys.argv[1]]()
