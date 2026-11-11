"""How an attempt stopped: every model turn without a tool call, the nudge that followed, and what
the model did between stops (tool calls, writes, sorries left, fills proved).

Usage: .venv/bin/python scripts/analysis/giveup.py <runs dir> <rep> [arm/problem ...]
   e.g. scripts/analysis/giveup.py runs-server/rep2 rep2
        scripts/analysis/giveup.py runs-server/pass1 rep0 plain/imo_2026_p3
Written for the give-up question after rep 2 (2026-11-11)."""
import collections, json, pathlib, re, sys

RUNS, REP = pathlib.Path(sys.argv[1]), sys.argv[2]
SEL = sys.argv[3:]


def J(s):
    try:
        return json.loads(s)
    except Exception:
        return None


def attempts():
    for arm in ("plain", "skeleton_forced"):
        for p in sorted((RUNS / arm).glob("imo_2026_p*")):
            d = p / REP
            if (d / "transcript.jsonl").exists() and (not SEL or f"{arm}/{p.name}" in SEL):
                yield arm, p.name, d


def sorries_in(text):
    return len(re.findall(r"\bsorry\b", text or ""))


for arm, prob, d in attempts():
    recs = [json.loads(l) for l in open(d / "transcript.jsonl")]
    chat = [r for r in recs if r["kind"] == "chat"]
    tools = [r for r in recs if r["kind"] == "tool"]
    t0 = chat[0]["started"] if chat else None
    print("=" * 110)
    print(f"{arm}/{prob}/{REP}: {len(chat)} model turns, {len(tools)} tool calls")
    # ---- walk the turns: a stop is a turn with no tool call ----
    segs = []          # activity segments between stop runs
    stops = []         # (turn index, consecutive count, content, reasoning head)
    cur = collections.Counter()
    cur_writes = []    # (sorries after write, accepted?)
    consec = 0
    last_fill = None
    by_step = collections.defaultdict(list)
    for r in tools:
        by_step[int(r["step"])].append(r)
    for i, r in enumerate(chat):
        resp = r.get("response") or {}
        if isinstance(resp, str):
            resp = J(resp.replace("'", '"')) or {}
        tcs = resp.get("tool_calls") or []
        if not tcs:
            consec += 1
            if cur or cur_writes:
                segs.append((cur, cur_writes))
                cur, cur_writes = collections.Counter(), []
            content = (resp.get("content") or "").strip()
            reasoning = (resp.get("reasoning_content") or "").strip()
            stops.append((i + 1, consec, r.get("finish_reason"), content, reasoning, r.get("started")))
            continue
        consec = 0
        for tc in tcs:
            name = tc.get("function", {}).get("name") or tc.get("name")
            cur[name] += 1
        for tr in by_step.get(i + 1, []):
            if tr["name"] == "write_file":
                res = tr.get("result") or ""
                ok = not res.startswith("REJECTED")
                m = re.search(r"(\d+) sorr", res)
                fill = re.search(r"(\d+)/(\d+) sorr", res)
                cur_writes.append((ok, m.group(1) if m else "?", fill.group(0) if fill else ""))
    if cur or cur_writes:
        segs.append((cur, cur_writes))
    print(f"stops: {len(stops)} turns without a tool call; longest run {max((s[1] for s in stops), default=0)}")
    # ---- interleave: segment k, then the stop run that ended it ----
    si = 0
    for k, (cnt, writes) in enumerate(segs):
        accepted = [w for w in writes if w[0]]
        print(f"  seg {k}: {sum(cnt.values())} tool calls {dict(cnt.most_common(5))}; writes {len(writes)} ({len(accepted)} accepted)"
              + (f"; sorries after last accepted write: {accepted[-1][1]} {accepted[-1][2]}" if accepted else ""))
        # print the stop run after this segment
        run = []
        while si < len(stops) and (not run or stops[si][1] > 1):
            run.append(stops[si]); si += 1
        for (n, c, fin, content, reasoning, started) in run:
            head = (content or reasoning or "")[:300].replace("\n", " ")
            print(f"    STOP turn {n} (#{c} in a row, finish={fin}): {head!r}")
    while si < len(stops):
        (n, c, fin, content, reasoning, started) = stops[si]; si += 1
        head = (content or reasoning or "")[:300].replace("\n", " ")
        print(f"    STOP turn {n} (#{c} in a row, finish={fin}): {head!r}")
    # ---- what the file looked like at the end ----
    thy = (d / f"{prob}.thy").read_text()
    lines = thy.splitlines()
    sor = [i for i, l in enumerate(lines) if re.search(r"\bsorry\b", l)]
    print(f"final theory: {len(lines)} lines, {len(sor)} sorry lines")
    for i in sor[:10]:
        print("   ", i + 1, lines[i].strip()[:140])
