#!/usr/bin/env python3
"""ib.py - the benchmark side of the Isabelle harness (the `pb.py` of
nearai/putnambench-deepseek, rewritten for Isabelle/HOL and for two sources).

The agent never runs this. It is what the harness uses to turn a benchmark
checkout into a manifest, to stage one problem into its own bench directory,
to VERIFY a bench directory (the only judge of "solved"), and to run the
flock-protected work queue that lets any number of workers run in parallel.

Sources
    minif2f       facebookresearch/miniF2F, isabelle/{test,valid}. About 70 of
                  the 244 test files ship WITH a proof; prepare strips every
                  proof back to `sorry`, so the agent starts from the bare
                  statement in all cases.
    putnambench   trishullab/PutnamBench, isabelle/ (640 files). 325 carry a
                  factored answer: `definition <name>_solution ... undefined`
                  with the reference answer in the comment below it. As
                  upstream, the `wsolution` variant inlines the answer into the
                  statement (the leaderboard setting) and `full` leaves the
                  `undefined` for the agent to replace.

Commands
    prepare --source S --root DIR [--split test|valid] [--informal JSON]
                                  add the source to manifest.json
    list [filters]                problem names
    show <problem>                manifest entry
    stage <problem> --dest DIR [--variant V]
                                  write the bench directory (one .thy)
    verify --bench DIR            PASS/FAIL one bench directory (textual rules
                                  + an `isabelle build` through the Pool Server)
    select ...                    write a subset file (see `select --help`)
    selftest                      exercise the textual checks on synthetic input

Work queue (used by run_isabelle_solver.py)
    queue-init [--subset FILE] [--arm A ...] [--variant V] [--repeats N]
    claim --owner NAME [--pid P] [--arm A]
    release <problem> --arm A --rep R --status S [--note ..]
    reap / requeue / queue-status [-v]

What `verify` checks (the Isabelle counterpart of upstream's verify.sh)
    1. no `sorry` / `oops` outside comments;
    2. no escape hatch: `axiomatization`, `ML*`, `setup`, `oracle`, `consts`,
       `overloading`, `hide_*`, `notation`/`syntax`/`translations`,
       `declare [[...]]` (quick_and_dirty & co.), `nitpick_params`, ...;
    3. the theory header (name + imports) is the frozen one;
    4. the theorem statement -- from `theorem <name>` to the first proof
       command -- is the frozen one, comments stripped and whitespace
       normalized; the theorem keeps its name;
    5. no helper definition shadows a name the statement uses (Isabelle lets a
       new `definition prime` silently win over the imported `prime`);
    6. the theory builds (`isabelle build`, via the Pool Server bigstep endpoint)
       -- the whole file, so helper lemmas are checked too.
    `full` variant: the `<name>_solution` definition must remain, with its
    type unchanged and `undefined` replaced.

Environment: IB_MANIFEST, IB_QUEUE, IB_GYM_URL (default http://localhost:8000),
IB_BUILD_TIMEOUT (seconds, default 900).
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                         # the repository
MANIFEST = HERE / "manifest.json"
QUEUE = HERE / "problems.tsv"

GYM_URL = os.environ.get("IB_GYM_URL", "http://localhost:8000")
BUILD_TIMEOUT = float(os.environ.get("IB_BUILD_TIMEOUT", "900"))
BUILD_WAIT_S = float(os.environ.get("IB_BUILD_WAIT_S", "900"))        # waiting out a 503 memory gate
BUILD_WAIT_POLL_S = float(os.environ.get("IB_BUILD_WAIT_POLL_S", "30"))

# --------------------------------------------------------------------------- #
# text utilities
# --------------------------------------------------------------------------- #

def strip_comments(text: str) -> str:
    """Remove (nesting-aware) (* ... *) comments. Everything the checks
    compare starts at a keyword, so nothing of interest is lost."""
    out, i, n, depth = [], 0, len(text), 0
    while i < n:
        if text.startswith("(*", i):
            depth += 1
            i += 2
        elif text.startswith("*)", i) and depth:
            depth -= 1
            i += 2
        elif depth:
            i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def normalize(text: str) -> str:
    """Comment-free, whitespace-collapsed, quote-style-agnostic form used for
    frozen-signature matching."""
    t = strip_comments(text)
    t = t.replace("\\<open>", "\u2039").replace("\\<close>", "\u203a")
    return re.sub(r"\s+", " ", t).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The commands that START a proof (or close a statement without one). The
# statement is everything from the theorem keyword up to the first of these
# found OUTSIDE strings, cartouches and comments.
PROOF_START = ("sorry", "oops", "proof", "by", "using", "apply", "unfolding",
               "supply", "including", "apply_end", "done", "..", ".")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_']*|\.\.|\.")


def find_proof_start(text: str, start: int = 0) -> int | None:
    """Index of the first proof-start token at or after `start`, scanning
    outside "strings", ‹cartouches›, \\<open>..\\<close> and (* comments *).
    None when there is none (a bare statement with nothing after it)."""
    i, n = start, len(text)
    depth = 0
    cart = 0
    while i < n:
        ch = text[i]
        if depth:
            if text.startswith("(*", i):
                depth += 1
                i += 2
            elif text.startswith("*)", i):
                depth -= 1
                i += 2
            else:
                i += 1
            continue
        if text.startswith("(*", i):
            depth += 1
            i += 2
            continue
        if cart:
            if ch == "\u2039" or text.startswith("\\<open>", i):
                cart += 1
                i += 7 if text.startswith("\\<open>", i) else 1
            elif ch == "\u203a" or text.startswith("\\<close>", i):
                cart -= 1
                i += 8 if text.startswith("\\<close>", i) else 1
            else:
                i += 1
            continue
        if ch == "\u2039" or text.startswith("\\<open>", i):
            cart = 1
            i += 7 if text.startswith("\\<open>", i) else 1
            continue
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        m = _WORD.match(text, i)
        if m:
            w = m.group(0)
            if w in PROOF_START and (i == 0 or not (text[i-1].isalnum() or text[i-1] in "_'")):
                # `.`/`..` only count as a proof when they stand alone on a line
                if w in (".", "..") and not re.match(r"\s*\.\.?\s*$", text[text.rfind("\n", 0, i)+1:text.find("\n", i) if text.find("\n", i) >= 0 else n]):
                    i = m.end()
                    continue
                return i
            i = m.end()
            continue
        i += 1
    return None


_HEADER_RE = re.compile(r"^\s*(?:\(\*.*?\*\)\s*)*theory\s+(\S+)\s+imports\s+(.+?)\s+begin\b",
                        re.DOTALL)
_STMT_RE = re.compile(r"^[ \t]*(theorem|lemma|corollary|proposition)\s+([A-Za-z0-9_']+)\s*(?:\[[^\]]*\])?\s*:",
                      re.MULTILINE)


def parse_header(text: str) -> tuple[str, list[str], int]:
    """(theory_name, imports, index just after `begin`)."""
    m = _HEADER_RE.match(text)
    if not m:
        raise ValueError("cannot parse theory header")
    imports = [t.strip('"') for t in re.findall(r'"[^"]+"|\S+', m.group(2))]
    return m.group(1), imports, m.end()


def frozen_header(text: str) -> str:
    name, imports, _ = parse_header(text)
    return name + " imports " + " ".join(sorted(imports))


def locate_statement(text: str, name: str | None = None) -> tuple[str, int, int, int]:
    """(theorem_name, stmt_start, proof_start, end_of_proof) for the target
    theorem. With `name` None, the FIRST theorem-like statement is the target.
    `end_of_proof` is the index of the final `end` of the theory."""
    clean_for_search = text
    for m in _STMT_RE.finditer(clean_for_search):
        # skip matches inside comments: cheap test via comment-stripped prefix
        if strip_comments(text[:m.start()]).count("(*") != 0:
            continue
        if name is None or m.group(2) == name:
            stmt_start = m.start()
            break
    else:
        raise ValueError(f"target theorem {name or '(first)'} not found")
    tname = m.group(2)
    ps = find_proof_start(text, m.end())
    end = _theory_end(text)
    if ps is None or ps > end:
        ps = end
    return tname, stmt_start, ps, end


def _theory_end(text: str) -> int:
    """Index of the theory's closing `end` (the last `end` on its own line)."""
    stripped = strip_comments(text)
    # positions are preserved only if comments are replaced by spaces, so do
    # that instead of removing them
    padded = _pad_comments(text)
    ms = list(re.finditer(r"^[ \t]*end[ \t]*$", padded, re.MULTILINE))
    if not ms:
        raise ValueError("theory has no closing `end`")
    _ = stripped
    return ms[-1].start()


def _pad_comments(text: str) -> str:
    out, i, n, depth = [], 0, len(text), 0
    while i < n:
        if text.startswith("(*", i):
            depth += 1
            out.append("  "); i += 2
        elif text.startswith("*)", i) and depth:
            depth -= 1
            out.append("  "); i += 2
        elif depth:
            out.append("\n" if text[i] == "\n" else " "); i += 1
        else:
            out.append(text[i]); i += 1
    return "".join(out)


def statement_text(text: str, name: str | None = None) -> str:
    tname, a, b, _ = locate_statement(text, name)
    return text[a:b]


def sorryfy(text: str, name: str | None = None) -> str:
    """The same theory with the target theorem's proof replaced by `sorry`
    and everything between the proof and the final `end` dropped."""
    _, a, b, end = locate_statement(text, name)
    stmt = text[a:b].rstrip()
    return text[:a] + stmt + "\n  sorry\n\n" + text[end:]


# --------------------------------------------------------------------------- #
# escape hatches and shadowing
# --------------------------------------------------------------------------- #

FORBIDDEN = [
    (r"^\s*axiomatization\b", "axiomatization"),
    (r"^\s*(ML|ML_val|ML_prf|ML_command|ML_file|ML_file_debug|ML_file_no_debug|SML_file|SML_import|SML_export)\b", "ML"),
    (r"^\s*(setup|local_setup|attribute_setup|method_setup|simproc_setup|declaration|syntax_declaration|oracle)\b", "setup/oracle"),
    (r"^\s*(parse_translation|print_translation|typed_print_translation|parse_ast_translation|print_ast_translation)\b", "translation"),
    (r"^\s*(consts|defs|overloading|typedecl|code_printing|code_reserved|code_datatype|code_abort)\b", "unchecked declaration"),
    (r"^\s*(hide_const|hide_fact|hide_type|hide_class)\b", "hide_*"),
    (r"^\s*(notation|no_notation|syntax|no_syntax|translations|no_translations|type_notation|no_type_notation|abbreviation\s*\(input\))\b", "notation/syntax"),
    (r"^\s*declare\s*\[\[", "declare [[...]] (config options)"),
    (r"\[\[\s*(quick_and_dirty|skip_proofs)\b", "quick_and_dirty/skip_proofs"),
    (r"^\s*(nitpick_params|sledgehammer_params)\b", "params"),
    (r"^\s*(instance|instantiation|interpretation|global_interpretation|sublocale)\b.*\bsorry\b", "sorry in instance"),
    (r"^\s*(theory|end)\b.*\n.*^\s*theory\b", "second theory header"),
]

DEFINES_RE = re.compile(
    r"^\s*(?:private\s+|qualified\s+)?"
    r"(definition|abbreviation|fun|function|primrec|primcorec|inductive|inductive_set|coinductive|"
    r"datatype|codatatype|record|type_synonym|typedef|lift_definition|locale|class|"
    r"lemma|theorem|corollary|proposition|lemmas|named_theorems|nominal_datatype|"
    r"specification|partial_function|quotient_type|quotient_definition)\s+"
    r"(?:\([^)]*\)\s*)?"
    r"([A-Za-z_][A-Za-z0-9_']*)", re.MULTILINE)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")


def defined_names(text: str) -> set[str]:
    """Names introduced by definition-like commands (comment-stripped text)."""
    names: set[str] = set()
    for m in DEFINES_RE.finditer(text):
        kw, nm = m.group(1), m.group(2)
        # `fun f and g where` / `datatype 'a t = ...` -- the first name is the
        # one that matters for shadowing; `where`/`is` are not names
        if nm not in ("where", "is", "and", "fixes", "assumes", "shows"):
            names.add(nm)
    return names


def shadowed(defined: set[str], statement: str, keep: set[str] = frozenset()) -> set[str]:
    """Defined names that also occur in the frozen statement (minus `keep`)."""
    idents = set(IDENT_RE.findall(strip_comments(statement)))
    return (defined & idents) - keep


# --------------------------------------------------------------------------- #
# session derivation
# --------------------------------------------------------------------------- #

# The Pool Server builds a theory as a child session of ONE parent heap; pick
# the parent that already contains every other session the file imports.
# Order = "contains the ones after it" (HOL-Analysis includes
# HOL-Computational_Algebra, HOL-Library, HOL-Combinatorics; HOL-Number_Theory
# includes HOL-Computational_Algebra, ...). Files that mix two incomparable
# sessions (HOL-Algebra + HOL-Analysis) are flagged by the statement probe.
SESSION_ORDER = ["HOL-Probability", "HOL-Analysis", "HOL-Number_Theory",
                 "HOL-Algebra", "HOL-Computational_Algebra", "HOL-Combinatorics",
                 "HOL-Library", "HOL"]


def derive_field(imports: list[str]) -> str:
    sessions = {i.split(".")[0] for i in imports if "." in i}
    for s in SESSION_ORDER:
        if s in sessions:
            return s
    return "HOL"


def session_set(imports: list[str]) -> list[str]:
    return sorted({i.split(".")[0] for i in imports if "." in i})


# --------------------------------------------------------------------------- #
# prepare
# --------------------------------------------------------------------------- #

MINIF2F_CATEGORY = re.compile(r"^(mathd_algebra|mathd_numbertheory|amc12[ab]?|aime|imo|algebra|numbertheory|induction)")


def inline_solution(text: str, base: str) -> tuple[str, str | None, str | None]:
    """PutnamBench `wsolution`: drop `definition <base>_solution ... undefined`
    + its answer comment and substitute `(answer)` for the name in the rest
    of the file. Returns (new_text, answer, solution_type). Mirrors
    isabelle/scripts/rewrite_solutions.py upstream."""
    dm = re.search(rf"^[ \t]*definition\s+{re.escape(base)}_solution\b", text, re.MULTILINE)
    if not dm:
        return text, None, None
    defn = dm.start()
    # type: between `::` and `where`
    tm = re.search(r"::\s*(\"[^\"]*\"|\S+)\s+where", text[defn:], re.DOTALL)
    sol_type = tm.group(1).strip('"') if tm else None
    cs = text.find("(*", defn)
    ce = text.find("*)", cs)
    if cs < 0 or ce < 0:
        return text, None, sol_type
    answer = text[cs+2:ce].strip()
    rest = text[ce+2:]
    rest = rest.replace(f"{base}_solution", "(" + answer + ")")
    return text[:defn] + rest.lstrip("\n"), answer, sol_type


def _entry_from_file(path: Path, source: str, split: str | None,
                     informal: dict | None) -> dict:
    text = path.read_text(encoding="utf-8")
    name, imports, _ = parse_header(text)
    base = path.stem
    if name != base:
        raise ValueError(f"{path.name}: theory name {name!r} != file stem")
    pristine = sorryfy(text, None)          # proofs stripped, one `sorry`
    tname, a, b, _ = locate_statement(pristine, None)
    entry = {
        "name": base,
        "source": source,
        "split": split,
        "theorem_name": tname,
        "imports": imports,
        "sessions": session_set(imports),
        "field": derive_field(imports),
        "header": frozen_header(pristine),
        "sig": normalize(pristine[a:b]),
        "has_solution": False,
        "solution_name": None,
        "solution_type": None,
        "reference_answer": None,
        "sig_wsolution": None,
        "pristine_sha256": sha256(path),
        "pristine_path": str(path),
        "src_had_proof": bool(re.search(r"\bsorry\b", strip_comments(text[a:]))) is False,
    }
    if source == "minif2f":
        m = MINIF2F_CATEGORY.match(base)
        entry["category"] = m.group(1) if m else "other"
        entry["tags"] = [entry["category"]]
    elif source == "putnambench":
        m = re.match(r"putnam_(\d{4})_([ab])(\d)", base)
        entry["year"] = int(m.group(1)) if m else None
        entry["category"] = f"{m.group(2)}{m.group(3)}" if m else "other"
        inf = (informal or {}).get(base) or {}
        entry["tags"] = inf.get("tags") or []
        entry["informal_statement"] = inf.get("informal_statement")
        entry["informal_solution"] = inf.get("informal_solution")
        if f"definition {base}_solution" in pristine:
            w, answer, sol_type = inline_solution(pristine, base)
            entry["has_solution"] = True
            entry["solution_name"] = f"{base}_solution"
            entry["solution_type"] = sol_type
            entry["reference_answer"] = answer
            _, wa, wb, _ = locate_statement(w, tname)
            entry["sig_wsolution"] = normalize(w[wa:wb])
    return entry


def load_manifest() -> dict:
    p = manifest_path()
    if not p.exists():
        sys.exit(f"no {p} - run `ib.py prepare` first")
    return json.loads(p.read_text(encoding="utf-8"))


def manifest_path() -> Path:
    return Path(os.environ.get("IB_MANIFEST", MANIFEST))


def cmd_prepare(args) -> int:
    root = Path(args.root).resolve()
    if args.source == "minif2f":
        split = args.split or "test"
        files = sorted((root / split).glob("*.thy"))
        informal = None
    else:
        split = None
        files = sorted(root.glob("*.thy"))
        informal = None
        inf_path = Path(args.informal) if args.informal else root.parent / "informal" / "putnam.json"
        if inf_path.exists():
            informal = {e["problem_name"]: e for e in json.loads(inf_path.read_text(encoding="utf-8"))}
    if not files:
        sys.exit(f"no .thy files under {root}")
    man = json.loads(manifest_path().read_text(encoding="utf-8")) if manifest_path().exists() else {}
    added, skipped = 0, []
    for f in files:
        try:
            e = _entry_from_file(f, args.source, split, informal)
        except Exception as ex:                     # noqa: BLE001
            skipped.append(f"{f.name}: {type(ex).__name__}: {ex}")
            continue
        man[e["name"]] = e
        added += 1
    manifest_path().write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    n_sol = sum(1 for e in man.values() if e["has_solution"])
    print(f"manifest: +{added} from {args.source} -> {len(man)} problems "
          f"({n_sol} with a factored answer) in {manifest_path()}")
    if skipped:
        print(f"skipped {len(skipped)}:", file=sys.stderr)
        for s in skipped[:30]:
            print("  " + s, file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# list / show / select
# --------------------------------------------------------------------------- #

def _filter(man: dict, args) -> list[str]:
    names = []
    for name, e in sorted(man.items()):
        if getattr(args, "source", None) and e["source"] != args.source:
            continue
        if getattr(args, "category", None) and e.get("category") != args.category:
            continue
        if getattr(args, "with_answer", False) and not e["has_solution"]:
            continue
        if getattr(args, "no_answer", False) and e["has_solution"]:
            continue
        names.append(name)
    return names


def cmd_list(args) -> int:
    man = load_manifest()
    for name in _filter(man, args):
        e = man[name]
        if args.verbose:
            print(f"{name:40s} {e['source']:12s} {'ANS' if e['has_solution'] else '   '} "
                  f"{e.get('category','')} {e['field']}")
        else:
            print(name)
    return 0


def cmd_show(args) -> int:
    man = load_manifest()
    if args.problem not in man:
        sys.exit(f"unknown problem: {args.problem}")
    print(json.dumps(man[args.problem], indent=2, ensure_ascii=False))
    return 0


def cmd_select(args) -> int:
    """A stratified, seeded subset. `--probe probe.json` (from
    scripts/statement_probe.py) lets you drop problems that do not parse under
    the server's Isabelle and -- the point of this experiment -- problems that
    plain sledgehammer already closes from the bare statement."""
    man = load_manifest()
    names = _filter(man, args)
    probe = json.loads(Path(args.probe).read_text(encoding="utf-8")) if args.probe else {}
    dropped = {"unparsed": 0, "sh_trivial": 0, "unprobed": 0}
    keep = []
    for n in names:
        p = probe.get(n)
        if args.probe:
            if p is None:
                dropped["unprobed"] += 1
                if args.require_probe:
                    continue
            else:
                if args.exclude_unparsed and not p.get("parses", True):
                    dropped["unparsed"] += 1
                    continue
                if args.exclude_sh_trivial and p.get("sh_proved"):
                    dropped["sh_trivial"] += 1
                    continue
        keep.append(n)
    rng = random.Random(args.seed)
    if args.n and args.n < len(keep):
        key = args.stratify
        if key:
            groups: dict[str, list[str]] = {}
            for n in keep:
                groups.setdefault(str(man[n].get(key)), []).append(n)
            # proportional allocation, largest remainders
            quota = {g: args.n * len(v) / len(keep) for g, v in groups.items()}
            take = {g: int(q) for g, q in quota.items()}
            for g in sorted(quota, key=lambda g: quota[g] - take[g], reverse=True)[: args.n - sum(take.values())]:
                take[g] += 1
            keep = sorted(x for g, v in groups.items() for x in rng.sample(v, min(take[g], len(v))))
        else:
            keep = sorted(rng.sample(keep, args.n))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(keep) + "\n", encoding="utf-8")
    print(f"{len(keep)} problems -> {out}  (dropped {dropped})")
    return 0


# --------------------------------------------------------------------------- #
# stage
# --------------------------------------------------------------------------- #

def staged_text(entry: dict, variant: str) -> str:
    """The .thy the agent starts from."""
    text = Path(entry["pristine_path"]).read_text(encoding="utf-8")
    text = sorryfy(text, None)
    base = entry["name"]
    if entry["has_solution"]:
        if variant == "wsolution":
            text, _, _ = inline_solution(text, base)
        else:
            # `full`: keep the definition, drop the answer comment
            cs = text.find("(*", text.find(f"definition {base}_solution"))
            ce = text.find("*)", cs)
            if cs >= 0 and ce >= 0:
                text = text[:cs] + text[ce+2:]
    return text


def cmd_stage(args) -> int:
    man = load_manifest()
    e = man.get(args.problem) or sys.exit(f"unknown problem: {args.problem}")
    dest = Path(args.dest).resolve()
    if dest.exists() and not args.force:
        sys.exit(f"{dest} exists (use --force)")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{e['name']}.thy").write_text(staged_text(e, args.variant), encoding="utf-8")
    (dest / ".ib.json").write_text(json.dumps({"problem": e["name"], "variant": args.variant}),
                                   encoding="utf-8")
    print(f"staged {e['name']} ({args.variant}) -> {dest}")
    return 0


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #

def textual_checks(text: str, entry: dict, variant: str) -> list[str]:
    """Every reason the file fails the rules, without touching Isabelle."""
    name = entry["name"]
    fails: list[str] = []
    clean = strip_comments(text)

    if re.search(r"\b(sorry|oops)\b", clean):
        fails.append("file still contains sorry/oops")
    for pat, label in FORBIDDEN:
        if re.search(pat, clean, re.MULTILINE):
            fails.append(f"forbidden command: {label}")
    try:
        if frozen_header(text) != entry["header"]:
            fails.append("theory header (name/imports) differs from the frozen one")
    except ValueError as ex:
        fails.append(f"cannot parse theory header: {ex}")
        return fails
    try:
        tname, a, b, _ = locate_statement(text, entry["theorem_name"])
    except ValueError as ex:
        fails.append(str(ex))
        return fails
    want = entry["sig_wsolution"] if (variant == "wsolution" and entry["has_solution"]) else entry["sig"]
    got = normalize(text[a:b])
    if got != want:
        fails.append("theorem statement differs from the frozen one")
    # the target theorem must be stated exactly once
    if len([m for m in _STMT_RE.finditer(clean) if m.group(2) == tname]) != 1:
        fails.append(f"theorem {tname} must be stated exactly once")
    defs = defined_names(clean) - {tname}
    keep = set()
    if entry["has_solution"] and variant == "full":
        keep.add(entry["solution_name"])
        dm = re.search(rf"^[ \t]*definition\s+{re.escape(entry['solution_name'])}\b.*?::\s*(\"[^\"]*\"|\S+)\s+where\s*(\"[^\"]*\")",
                       clean, re.MULTILINE | re.DOTALL)
        if not dm:
            fails.append(f"{entry['solution_name']} definition missing or malformed")
        else:
            if dm.group(1).strip('"').split() != (entry["solution_type"] or "").split():
                fails.append(f"{entry['solution_name']} type changed")
            if re.search(r"\bundefined\b", dm.group(2)):
                fails.append(f"{entry['solution_name']} still undefined")
    elif entry["has_solution"] and f"{entry['solution_name']}" in clean:
        fails.append(f"{entry['solution_name']} must not be reintroduced (answer is inlined)")
    sh = shadowed(defs, text[a:b], keep)
    if sh:
        fails.append(f"helper definitions shadow names used in the statement: {sorted(sh)}")
    return fails


def build_check(text: str, entry: dict, timeout: float = BUILD_TIMEOUT, gym_url: str = GYM_URL) -> tuple[bool, str]:
    """`isabelle build` the whole theory through the Pool Server. (True, log)
    when the theory is verified; (False, reason) otherwise."""
    import httpx  # local import: the textual checks must work without it

    # `field` is the parent session of the generated ROOT; the server derives
    # the dependency key from the theory's own imports (its `dependencies`
    # parameter takes theory names, not sessions, so it is not used here).
    payload = {"theory_name": entry["name"], "field": entry["field"],
               "theory": text, "timeout": timeout}
    # The server refuses a build (503) while its memory tier is high -- a
    # sledgehammer job of another worker, a session being torn down, the
    # page cache after a heap build. That is the harness's problem, not the
    # agent's: wait it out here (the agent is blocked inside completed())
    # rather than hand back "try later" and have the model spend steps
    # polling. Budget: BUILD_WAIT_S total, polling every BUILD_WAIT_POLL_S.
    last = ""
    deadline = time.time() + BUILD_WAIT_S
    attempt = 0
    while True:
        attempt += 1
        try:
            with httpx.Client(timeout=timeout + 60) as c:
                r = c.post(f"{gym_url}/api/v1/sessions/bigstep", json=payload)
            if r.status_code == 503:
                last = f"server 503: {r.text[:200]}"
                if time.time() < deadline:
                    time.sleep(BUILD_WAIT_POLL_S)
                    continue
                break
            r.raise_for_status()
            d = r.json()
            if d.get("theory_verified"):
                return True, str(d.get("output") or "")[:2000]
            return False, (d.get("error") or d.get("output") or "bigstep verification failed")[:4000]
        except Exception as ex:                      # noqa: BLE001
            last = f"{type(ex).__name__}: {ex}"
            if attempt < 4 and time.time() < deadline:
                time.sleep(10)
                continue
            break
    return False, f"build service unavailable: {last}"


def verify_text(text: str, entry: dict, variant: str, *, build: bool = True,
                timeout: float = BUILD_TIMEOUT, gym_url: str = GYM_URL) -> tuple[bool, str]:
    """PASS/FAIL report in upstream's format."""
    name = entry["name"]
    fails = textual_checks(text, entry, variant)
    if fails:
        return False, "\n".join(f"FAIL [{name}] {f}" for f in fails)
    if not build:
        return True, f"PASS [{name}] (textual checks only; no build)"
    ok, log = build_check(text, entry, timeout=timeout, gym_url=gym_url)
    if ok:
        return True, f"PASS [{name}] theory builds; statement frozen; no sorry/escape hatches."
    return False, f"isabelle build output:\n{log}\n\nFAIL [{name}] the theory does not build"


def verify_bench(bench_dir: Path, *, build: bool = True) -> tuple[bool, str]:
    meta = json.loads((bench_dir / ".ib.json").read_text(encoding="utf-8"))
    man = load_manifest()
    e = man[meta["problem"]]
    thy = bench_dir / f"{e['name']}.thy"
    if not thy.exists():
        return False, f"FAIL [{e['name']}] {thy.name} missing"
    return verify_text(thy.read_text(encoding="utf-8"), e, meta["variant"], build=build)


def cmd_verify(args) -> int:
    ok, report = verify_bench(Path(args.bench).resolve(), build=not args.no_build)
    print(report)
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# work queue (flock-protected TSV, as upstream)
# --------------------------------------------------------------------------- #

QCOLS = ["problem", "arm", "variant", "rep", "status", "owner", "pid",
         "claimed_at", "steps", "note"]
STALE_SECONDS = 48 * 3600


def queue_path() -> Path:
    return Path(os.environ.get("IB_QUEUE", QUEUE))


class _Lock:
    def __init__(self, shared: bool = False):
        self.shared = shared
        self.fh = None

    def __enter__(self):
        lp = queue_path().with_suffix(".lock")
        self.fh = open(lp, "a+")
        fcntl.flock(self.fh, fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _read_rows() -> list[dict]:
    p = queue_path()
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines()[1:]:
        if ln.strip():
            rows.append(dict(zip(QCOLS, ln.split("\t"))))
    return rows


def _write_rows(rows: list[dict]) -> None:
    p = queue_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\t".join(QCOLS) + "\n" +
                   "".join("\t".join(str(r.get(c, "") or "") for c in QCOLS) + "\n" for r in rows),
                   encoding="utf-8")
    os.replace(tmp, p)


def _pid_alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def cmd_queue_init(args) -> int:
    man = load_manifest()
    names = _filter(man, args)
    if args.subset:
        wanted = [ln.strip() for ln in Path(args.subset).read_text(encoding="utf-8").splitlines() if ln.strip()]
        missing = [w for w in wanted if w not in man]
        if missing:
            sys.exit(f"subset names not in manifest: {missing[:5]}")
        names = [n for n in wanted if n in set(names)]
    with _Lock():
        rows = _read_rows()
        have = {(r["problem"], r["arm"], r["variant"], r["rep"]) for r in rows}
        n = 0
        for rep in range(args.repeats):
            for arm in args.arm:
                for name in names:
                    key = (name, arm, args.variant, str(rep))
                    if key in have:
                        continue
                    rows.append({"problem": name, "arm": arm, "variant": args.variant,
                                 "rep": str(rep), "status": "todo"})
                    n += 1
        # interleave arms per problem so partial runs stay paired
        rows.sort(key=lambda r: (int(r["rep"]), r["problem"], r["arm"]))
        _write_rows(rows)
    print(f"queue: +{n} rows -> {queue_path()} ({len(rows)} total)")
    return 0


def cmd_claim(args) -> int:
    with _Lock():
        rows = _read_rows()
        now = time.time()
        for r in rows:  # reap dead claims
            if r["status"] == "running":
                dead = not _pid_alive(r["pid"]) if r["pid"] else True
                stale = now - float(r["claimed_at"] or 0) > STALE_SECONDS
                if dead or stale:
                    r.update(status="todo", owner="", pid="", claimed_at="",
                             note=f"reaped ({'dead' if dead else 'stale'})")
        for r in rows:
            if r["status"] != "todo":
                continue
            if args.arm and r["arm"] not in args.arm:
                continue
            if args.problem and r["problem"] != args.problem:
                continue
            r.update(status="running", owner=args.owner, pid=str(args.pid or os.getpid()),
                     claimed_at=f"{now:.0f}", note="")
            _write_rows(rows)
            print(f"{r['problem']}\t{r['arm']}\t{r['variant']}\t{r['rep']}")
            return 0
    return 1


def cmd_release(args) -> int:
    with _Lock():
        rows = _read_rows()
        for r in rows:
            if (r["problem"], r["arm"], str(r["rep"])) == (args.problem, args.arm, str(args.rep)) \
                    and (not args.variant or r["variant"] == args.variant):
                r.update(status=args.status, note=(args.note or "")[:160].replace("\t", " ").replace("\n", " "),
                         steps=str(args.steps or ""))
                if args.status == "todo":
                    r.update(owner="", pid="", claimed_at="")
                _write_rows(rows)
                return 0
    print("row not found", file=sys.stderr)
    return 1


def cmd_requeue(args) -> int:
    with _Lock():
        rows = _read_rows()
        n = 0
        for r in rows:
            if r["status"] in set(args.statuses):
                r.update(status="todo", owner="", pid="", claimed_at="")
                n += 1
        _write_rows(rows)
    print(f"requeued {n}")
    return 0


def cmd_queue_status(args) -> int:
    with _Lock(shared=True):
        rows = _read_rows()
    from collections import Counter
    c = Counter((r["arm"], r["status"]) for r in rows)
    arms = sorted({r["arm"] for r in rows})
    for arm in arms:
        parts = ", ".join(f"{s}={c[(arm, s)]}" for s in ("todo", "running", "solved", "failed", "timeout", "disproved") if c[(arm, s)])
        print(f"{arm:14s} {parts}")
    if args.verbose:
        for r in rows:
            print("\t".join(str(r.get(k, "")) for k in QCOLS))
    return 0


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

SYNTH = '''(* Authors: test *)
theory synth_1 imports Complex_Main "HOL-Number_Theory.Number_Theory"
begin

definition synth_1_solution :: "nat" where "synth_1_solution \\<equiv> undefined"
(* 5 *)
theorem synth_1:
  fixes n :: nat
  assumes "n = 2 + 3" (* a comment with the word by *)
  shows "n = synth_1_solution"
  sorry

end
'''


def cmd_selftest(args) -> int:
    import tempfile
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + msg)
        ok = ok and cond

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "synth_1.thy"
        p.write_text(SYNTH, encoding="utf-8")
        e = _entry_from_file(p, "putnambench", None, {})
        check(e["theorem_name"] == "synth_1", "theorem name")
        check(e["field"] == "HOL-Number_Theory", f"field {e['field']}")
        check(e["has_solution"] and e["reference_answer"] == "5", "factored answer parsed")
        check("(5)" in e["sig_wsolution"], "wsolution inlines the answer")
        w = staged_text(e, "wsolution")
        check("synth_1_solution" not in w and "sorry" in w, "staged wsolution text")
        f = staged_text(e, "full")
        check("undefined" in f and "(* 5 *)" not in f, "staged full text keeps undefined, drops answer")
        # proofs are stripped
        proved = SYNTH.replace("  sorry\n", "  using assms by simp\n")
        check(sorryfy(proved).count("sorry") == 1 and "by simp" not in sorryfy(proved), "sorryfy strips a proof")
        # verify: textual
        good = w.replace("  sorry\n", "  using assms by simp\n")
        check(textual_checks(good, e, "wsolution") == [], "clean proof passes textual checks")
        bad = good.replace("by simp", "sorry")
        check(any("sorry" in x for x in textual_checks(bad, e, "wsolution")), "sorry is caught")
        bad = good.replace("theorem synth_1:\n  fixes n :: nat\n  assumes \"n = 2 + 3\"",
                           "theorem synth_1:\n  fixes n :: nat\n  assumes \"n = 5\"")
        check(any("statement differs" in x for x in textual_checks(bad, e, "wsolution")), "statement change is caught")
        bad = good.replace("theorem synth_1:", "declare [[quick_and_dirty]]\ntheorem synth_1:")
        check(any("forbidden" in x for x in textual_checks(bad, e, "wsolution")), "quick_and_dirty is caught")
        bad = good.replace("theorem synth_1:", 'definition n :: nat where "n = 0"\ntheorem synth_1:')
        check(any("shadow" in x for x in textual_checks(bad, e, "wsolution")), "shadowing is caught")
        bad = good.replace('"HOL-Number_Theory.Number_Theory"', '"HOL-Analysis.Analysis"')
        check(any("header" in x for x in textual_checks(bad, e, "wsolution")), "import change is caught")
        bad = good.replace("by simp", "by (metis add_2_eq_Suc) (* sorry *)")
        check(textual_checks(bad, e, "wsolution") == [], "sorry inside a comment is fine")
        # full variant
        fg = f.replace("undefined", "5").replace("  sorry\n", "  using assms unfolding synth_1_solution_def by simp\n")
        check(textual_checks(fg, e, "full") == [], "full variant with answer passes")
        fb = f.replace("  sorry\n", "  using assms by simp\n")
        check(any("undefined" in x for x in textual_checks(fb, e, "full")), "full variant still undefined is caught")
        # the proof-start scanner respects strings
        s = 'theorem t:\n  shows "P by Q"\n  by simp\nend\n'
        check(statement_text(s).strip().endswith('"P by Q"'), "proof start ignores `by` inside a string")
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("prepare"); s.add_argument("--source", choices=["minif2f", "putnambench"], required=True)
    s.add_argument("--root", required=True); s.add_argument("--split", choices=["test", "valid"])
    s.add_argument("--informal"); s.set_defaults(fn=cmd_prepare)

    def filters(sp):
        sp.add_argument("--source", choices=["minif2f", "putnambench"])
        sp.add_argument("--category"); sp.add_argument("--with-answer", action="store_true")
        sp.add_argument("--no-answer", action="store_true")

    s = sub.add_parser("list"); filters(s); s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("show"); s.add_argument("problem"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("select"); filters(s)
    s.add_argument("--n", type=int, default=0); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--stratify", help="manifest key to stratify by (category, source, year)")
    s.add_argument("--probe", help="probe.json from scripts/statement_probe.py")
    s.add_argument("--exclude-unparsed", action="store_true"); s.add_argument("--exclude-sh-trivial", action="store_true")
    s.add_argument("--require-probe", action="store_true", help="drop problems the probe has not seen")
    s.add_argument("--out", required=True); s.set_defaults(fn=cmd_select)
    s = sub.add_parser("stage"); s.add_argument("problem"); s.add_argument("--dest", required=True)
    s.add_argument("--variant", choices=["wsolution", "full"], default="wsolution")
    s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_stage)
    s = sub.add_parser("verify"); s.add_argument("--bench", required=True)
    s.add_argument("--no-build", action="store_true"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("selftest"); s.set_defaults(fn=cmd_selftest)

    s = sub.add_parser("queue-init"); filters(s); s.add_argument("--subset")
    s.add_argument("--arm", nargs="+", default=["plain", "skeleton"])
    s.add_argument("--variant", choices=["wsolution", "full"], default="wsolution")
    s.add_argument("--repeats", type=int, default=1); s.set_defaults(fn=cmd_queue_init)
    s = sub.add_parser("claim"); s.add_argument("--owner", required=True); s.add_argument("--pid", type=int)
    s.add_argument("--arm", nargs="*"); s.add_argument("--problem"); s.set_defaults(fn=cmd_claim)
    s = sub.add_parser("release"); s.add_argument("problem"); s.add_argument("--arm", required=True)
    s.add_argument("--rep", required=True); s.add_argument("--variant"); s.add_argument("--status", required=True)
    s.add_argument("--steps"); s.add_argument("--note"); s.set_defaults(fn=cmd_release)
    s = sub.add_parser("requeue"); s.add_argument("statuses", nargs="*", default=["failed", "timeout"]); s.set_defaults(fn=cmd_requeue)
    s = sub.add_parser("queue-status"); s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(fn=cmd_queue_status)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
