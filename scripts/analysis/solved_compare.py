"""The solved attempts side by side: wall, model/tool time, tokens, writes, and the shape of the
verified proof (lines, leaves, closing methods, ATP calls, helper lemmas).

Usage: .venv/bin/python scripts/analysis/solved_compare.py <results.jsonl> <runs dir for rep0> <runs dir for rep1> ...
   e.g. scripts/analysis/solved_compare.py runs-server/rep2/results.jsonl runs-server/pass1 runs-server/rep1
Written for the solved-set comparison after rep 2 (2026-11-11)."""
import collections, json, pathlib, re, sys

RESULTS = sys.argv[1]
RUNS = {i: pathlib.Path(p) for i, p in enumerate(sys.argv[2:])}   # rep index -> runs dir

ATP = ("metis", "smt", "meson", "moura")
# a leaf: `by ...` (one or two methods), `.` / `..` alone, `qed <method>`, `apply ...`
LEAF_RE = re.compile(r"^\s*(?:(?:then|also|finally|ultimately|thus|hence)\s+)?(?:show|have|from|using|with|note|unfolding|interpret|obtain)?[^\n]*?\bby[ \t]+(\(?[A-Za-z_]+)|^\s*\.\.?\s*$|^\s*qed[ \t]+(\(?[A-Za-z_]+)|^\s*apply[ \t]+(\(?[A-Za-z_]+)", re.M)


def proof_shape(text):
    lines = text.splitlines()
    nonblank = [l for l in lines if l.strip()]
    methods = collections.Counter()
    for m in LEAF_RE.finditer(text):
        name = (m.group(1) or m.group(2) or m.group(3) or ".").lstrip("(")
        methods[name] += 1
    leaves = sum(methods.values())
    atp = sum(v for k, v in methods.items() if k in ATP)
    # every `by` token, including second methods after a comma-free `by simp, auto`? keep to leaves above
    lemmas = len(re.findall(r"^\s*(?:lemma|theorem|corollary|proposition)\b", text, re.M))
    defs = len(re.findall(r"^\s*(?:definition|fun|function|primrec|abbreviation|inductive)\b", text, re.M))
    isar = len(re.findall(r"^\s*proof\b", text, re.M))
    haves = len(re.findall(r"^\s*(?:have|show|obtain|hence|thus|then show|then have|moreover have|ultimately have|finally have)\b", text, re.M))
    return dict(lines=len(lines), nonblank=len(nonblank), leaves=leaves, atp=atp, lemmas=lemmas, defs=defs,
                proof_blocks=isar, steps=haves, methods=methods)


rows = [json.loads(l) for l in open(RESULTS)]
solved = [r for r in rows if r["solved"] and r["rep"] in RUNS]
solved.sort(key=lambda r: (r["problem"], r["arm"], r["rep"]))
print(f"{'attempt':26s} {'wall':>6s} {'model':>6s} {'tools':>6s} {'turns':>5s} {'cmpl k':>7s} {'uncach k':>8s} {'prompt M':>8s} "
      f"{'writes':>6s} {'fills':>11s} {'lines':>5s} {'leaves':>6s} {'atp':>4s} {'lemmas':>6s} {'steps':>5s}  methods")
for r in solved:
    rep = r["rep"]
    d = RUNS[rep] / r["arm"] / r["problem"] / f"rep{rep}"
    thy = (d / "verified.thy").read_text() if (d / "verified.thy").exists() else (d / f"{r['problem']}.thy").read_text()
    shape = proof_shape(thy)
    recs = [json.loads(l) for l in open(d / "transcript.jsonl")]
    model_s = sum(float(x["elapsed_s"]) for x in recs if x["kind"] == "chat")
    tool_s = sum(float(x.get("elapsed_s") or 0) for x in recs if x["kind"] == "tool")
    t = r["tokens"]
    fills = f"{r.get('fill_sorries_proved', 0)}/{r.get('fill_sorries_total', 0)} in {r.get('fills', 0)}" if r.get("fills") else "-"
    name = f"{r['problem'][-2:]} {r['arm'][:6]} r{rep}"
    top = ", ".join(f"{k} {v}" for k, v in shape["methods"].most_common(6))
    print(f"{name:26s} {r['elapsed_s']/60:6.0f} {model_s/60:6.0f} {tool_s/60:6.0f} {r['steps']:5d} {t['completion']/1e3:7.0f} "
          f"{(t['prompt']-t['cached'])/1e3:8.0f} {t['prompt']/1e6:8.1f} {r.get('writes',0):6d} {fills:>11s} "
          f"{shape['lines']:5d} {shape['leaves']:6d} {shape['atp']:4d} {shape['lemmas']:6d} {shape['steps']:5d}  {top}")
print("\nwall/model/tools in minutes; cmpl = completion tokens (reasoning + text); uncach = prompt tokens not served from cache;"
      "\nleaves = closing methods in the verified theory (by/./../qed m/apply); atp = metis/smt/meson/moura among them;"
      "\nsteps = have/show/obtain lines; fills = sorries proved/tried over fill calls.")
