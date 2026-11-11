"""Replay every leaf-rule rejection with the filler keys the harness had, with and without Isabelle-symbol normalisation (needs an Isabelle etc/symbols file as the second argument).

Usage: .venv/bin/python scripts/analysis/rep1_leaf_replay.py <runs dir, e.g. runs-server/rep1> [problem ...]
Written for the rep-1 forced pass (2026-11-11); see docs/rep1-analysis-2026-11-11.md."""
import sys
RUNS = sys.argv[1]
ARGS = sys.argv[2:]
import json, re, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from harness import leaves
tab = {}
for m in re.finditer(r"^(\\<[^>]+>)\s+code:\s+(0x[0-9a-fA-F]+)", open(ARGS[0]).read(), re.M):
    tab[chr(int(m.group(2), 16))] = m.group(1)
rx = re.compile("|".join(re.escape(c) for c in sorted(tab, key=len, reverse=True)))
def ascii(s): return rx.sub(lambda m: tab[m.group(0)], s)
orig_norm = leaves._norm
def J(s):
    try: return json.loads(s)
    except Exception: return None
root = pathlib.Path(RUNS)/"skeleton_forced"
tot = {"rejections": 0, "lines": 0, "lines_fixed_by_symbols": 0, "rejections_fully_fixed": 0}
for p in ["imo_2026_p1","imo_2026_p2","imo_2026_p3","imo_2026_p4","imo_2026_p5","imo_2026_p6"]:
    recs = [json.loads(l) for l in open(root/p/"rep1"/"transcript.jsonl")]
    staged = None
    # the staged file = the first read_file result? use the first write's previous content: take first read_file tool result lines (strip "   N| ")
    allowed_raw, allowed_sym = set(), set()
    def add(text):
        leaves._norm = orig_norm; allowed_raw.update(leaves.leaf_keys(text))
        leaves._norm = lambda s: orig_norm(ascii(s)); allowed_sym.update(leaves.leaf_keys(text))
        leaves._norm = orig_norm
    for r in recs:
        if r["kind"] == "tool" and r["name"] == "read_file" and staged is None:
            staged = "\n".join(re.sub(r"^\s*\d+\| ?", "", l) for l in (r["result"] or "").splitlines())
            add(staged)
        if r["kind"] == "mcp" and r["name"] in ("isabelle_fill_sorries", "isabelle_fill_status"):
            d = J(r["result"])
            if isinstance(d, dict) and isinstance(d.get("patched_text"), str) and d.get("filled"):
                add(d["patched_text"])
        if r["kind"] == "tool" and r["name"] == "write_file" and (r["result"] or "").startswith("REJECTED (file unchanged): the LEAF RULE"):
            content = J(r["arguments"])["content"]
            leaves._norm = orig_norm; bad_raw = leaves.check(content, allowed_raw)
            leaves._norm = lambda s: orig_norm(ascii(s)); bad_sym = leaves.check(content, allowed_sym)
            leaves._norm = orig_norm
            tot["rejections"] += 1; tot["lines"] += len(bad_raw); tot["lines_fixed_by_symbols"] += len(bad_raw) - len(bad_sym)
            if bad_raw and not bad_sym: tot["rejections_fully_fixed"] += 1
            fixed = [v.text[:70] for v in bad_raw if v.line not in {w.line for w in bad_sym}]
            print(f"{p} n{r['n']}: {len(bad_raw)} bad line(s) as run, {len(bad_sym)} with symbol normalisation" + (f"  fixed: {fixed}" if fixed else ""))
print(tot)
