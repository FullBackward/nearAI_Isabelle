"""leaves.py - the leaf rule of the `skeleton_forced` arm.

In that arm the model never writes a closing proof method itself: every
terminal step of a proof is `sorry` until the server-side filler (sledgehammer
on every `sorry`, run by write_file) proves it, and the only method text the
file may carry is what the filler wrote back -- kept verbatim, under the same
statement, inside the same enclosing goal. The model keeps the parts of the
job sledgehammer cannot do: the structure of the argument, the intermediate
facts, the granularity of the steps, the `using` facts a leaf needs.

Why a textual rule and not a prover-side one: the owner's constraint (the
experiment can only block textually; a mechanical block inside Isabelle or
the Pool Server is not realistic), and the same reason the solver rule is
textual -- the file is the only thing the model changes, so the file is where
the rule is checked.

Why the key binds a leaf to its statement AND the enclosing goal: a leaf line
is usually just `by simp` on its own; once the filler has produced that once,
a line-only rule would let the model paste it under every statement. The
statement text alone is not enough either, `show ?thesis` repeats in every
block -- so the chain of goals that opened the enclosing `proof`s (outermost
to innermost) is part of the key. A proved block moved into another lemma
goes back to `sorry` and through the filler again: strict, and predictable.
This is the mechanical goal binding the owner wanted measured (audit F8,
2026-11-05), on the skeleton side.

What counts as a leaf (checked on a copy with comments, string literals and
cartouches blanked, so `by` inside a `text` block or a term never matters):

  * a line containing the method keyword `by`;
  * a line ending in the immediate-proof `.` or `..`;
  * `qed <method>` (a terminal method on the enclosing goal);
  * `proof <method>` whose initial method is not goal-shaping (anything but
    `-`, rule, intro, elim, induct, induction, cases, standard, insert,
    unfold, subst, goal_cases) -- `proof (auto)` closes goals as surely as
    `by auto`;
  * `apply` / `done` scripts, never accepted (the filler never writes them).

`sorry` is always accepted (the verifier refuses it at completed()). Two
definition idioms the filler cannot produce are whitelisted: the
`function` package's `by pat_completeness auto` and
`termination by lexicographic_order` / `size_change`.

Public API:
    leaf_keys(text)            -> set of (enclosing_goal, block) keys for every
                                  method leaf of `text` (what the filler wrote)
    check(text, allowed_keys)  -> list of Violation for every leaf the model
                                  wrote itself
    selftest()                 -> raises AssertionError on regression
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- masking ------------------------------------------------------------- #

def mask(text: str, *, literals: bool = True) -> str:
    """Blank the inside of (* *) comments (nesting) and -- with `literals` --
    "..." strings and \\<open>...\\<close> / ‹...› cartouches (nesting),
    keeping every newline and every position so line numbers survive.
    Leaf DETECTION runs on the fully masked text (a `by` inside a term or a
    text block is not a method); leaf KEYS are built from the comment-only
    masked text, so the statement's actual content is part of the key."""
    out = []
    i, n = 0, len(text)
    cdepth = 0      # comment depth
    qdepth = 0      # cartouche depth
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  " if text[i + 1] != "\n" else " \n")
                i += 2
                continue
            if ch == '"':
                in_str = False
                out.append('"')
            else:
                out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if cdepth:
            if text.startswith("(*", i):
                cdepth += 1; out.append("  "); i += 2; continue
            if text.startswith("*)", i):
                cdepth -= 1; out.append("  "); i += 2; continue
            out.append("\n" if ch == "\n" else " "); i += 1; continue
        if qdepth:
            if text.startswith("\\<open>", i):
                qdepth += 1; out.append(" " * 7); i += 7; continue
            if ch == "‹":
                qdepth += 1; out.append(" "); i += 1; continue
            if text.startswith("\\<close>", i):
                qdepth -= 1; out.append(" " * 8); i += 8; continue
            if ch == "›":
                qdepth -= 1; out.append(" "); i += 1; continue
            out.append("\n" if ch == "\n" else " "); i += 1; continue
        # outside everything
        if text.startswith("(*", i):
            cdepth = 1; out.append("  "); i += 2; continue
        if not literals:
            out.append(ch); i += 1; continue
        if text.startswith("\\<open>", i):
            qdepth = 1; out.append(" " * 7); i += 7; continue
        if ch == "‹":
            qdepth = 1; out.append(" "); i += 1; continue
        if ch == '"':
            in_str = True; out.append('"'); i += 1; continue
        out.append(ch); i += 1
    return "".join(out)


# ---- scanning ------------------------------------------------------------ #

# A line that starts a new command which may own a proof leaf (or that ends
# the previous one). `using`, `unfolding`, `by`, `apply`, `.`, `supply`,
# `including` CONTINUE the current command and are deliberately absent.
_START_RE = re.compile(
    r"^\s*(have|show|obtain|hence|thus|then|also|finally|moreover|ultimately|from|with|"
    r"lemma|theorem|corollary|proposition|schematic_goal|interpret|interpretation|instance|"
    r"termination|function|fun|definition|abbreviation|primrec|inductive|inductive_set|"
    r"coinductive|datatype|codatatype|record|type_synonym|typedef|locale|context|sublocale|"
    r"case|next|fix|assume|presume|let|define|note|text|txt|section|subsection|subsubsection|"
    r"paragraph|declare|lemmas|named_theorems|theory|begin|end|notepad|consider|guess|write|"
    r"print_\w+|find_\w+|thm|term|value|typ|prop|declaration|setup|ML|ML_val|attribute_setup|"
    r"method_setup|syntax|translations|no_notation|notation|axiomatization|nominal_datatype|"
    r"lift_definition|setup_lifting|quotient_type|specification|overloading|bundle|unbundle|"
    r"experiment|class|instantiation|subclass|rep_datatype|free_constructors|partial_function|"
    r"code_datatype|export_code|global_interpretation|proof|qed|oops|sorry)\b")
_BY_RE = re.compile(r"\bby\b")
_IMMEDIATE_RE = re.compile(r"(^|\s)\.\.?\s*$")
_APPLY_RE = re.compile(r"^\s*(apply|apply_end|done|defer|prefer|back)\b")
_QED_RE = re.compile(r"^\s*qed\b\s*(.*?)\s*$")
_PROOF_RE = re.compile(r"^\s*proof\b\s*(.*?)\s*$")
_PROOF_MARK_RE = re.compile(r"\bproof\b")
_STRUCTURAL_INITIAL = {"-", "rule", "intro", "elim", "induct", "induction", "cases", "standard",
                       "insert", "unfold", "subst", "goal_cases"}
_WHITELIST_RE = re.compile(
    r"^\s*(termination\b[^\n]*?)?\bby\s+(pat_completeness\s+auto|lexicographic_order|size_change)\s*$")

Key = tuple[str, str]


@dataclass(frozen=True)
class Violation:
    line: int           # 1-based
    text: str           # the offending line, stripped
    reason: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _initial_method_ok(rest: str) -> bool:
    """`proof` followed by `rest`: goal-shaping methods only."""
    rest = rest.strip()
    if not rest or rest == "-":
        return True
    m = re.match(r"\(?\s*([A-Za-z_][A-Za-z0-9_']*)", rest)
    return bool(m) and m.group(1) in _STRUCTURAL_INITIAL


def _scan(text: str):
    """Yield (line_no, kind, key, line_text) for every leaf of `text`.
    kind: 'method' (by/./../qed m), 'initial' (proof m, not goal-shaping),
    'apply' (apply-script), 'sorry'."""
    masked = mask(text).split("\n")                     # for detection
    plain = mask(text, literals=False).split("\n")      # for keys (comments blanked only)
    raw = text.split("\n")
    stack: list[str] = []            # statement that opened each open `proof`
    cur_start = 0
    block_of_proof: dict[int, str] = {}   # depth -> statement block (for qed keys)
    for i, ml in enumerate(masked):
        if not ml.strip():
            continue
        if _START_RE.match(ml) and not _PROOF_RE.match(ml) and not _QED_RE.match(ml) \
                and not re.match(r"^\s*(sorry|oops)\b", ml):
            cur_start = i
        statement = _norm(" ".join(plain[cur_start:i + 1]))
        enclosing = " > ".join(stack)
        pm = _PROOF_RE.match(ml)
        if pm:
            # the statement this proof is for: everything from cur_start up to
            # the `proof` keyword
            head = _norm(" ".join(plain[cur_start:i])) + " " + _norm(plain[i][:pm.start(1)].replace("proof", ""))
            head = _norm(head)
            stack.append(head)
            block_of_proof[len(stack)] = head
            if not _initial_method_ok(pm.group(1)):
                yield i + 1, "initial", (enclosing, head + " proof " + _norm(pm.group(1))), raw[i].strip()
            continue
        qm = _QED_RE.match(ml)
        if qm:
            head = stack.pop() if stack else ""
            enclosing = " > ".join(stack)
            if qm.group(1):
                yield i + 1, "method", (enclosing, head + " qed " + _norm(qm.group(1))), raw[i].strip()
            cur_start = i + 1
            continue
        if re.match(r"^\s*(sorry|oops)\b", ml):
            yield i + 1, "sorry", (enclosing, statement), raw[i].strip()
            continue
        if _APPLY_RE.match(ml):
            yield i + 1, "apply", (enclosing, statement), raw[i].strip()
            continue
        if _BY_RE.search(ml) or _IMMEDIATE_RE.search(ml):
            # `have "x" by simp` may also carry a trailing `sorry`-free leaf;
            # an inline `proof` on the same line is handled above.
            yield i + 1, "method", (enclosing, statement), raw[i].strip()
            continue


def leaf_keys(text: str) -> set[Key]:
    """Keys of every method leaf of `text` -- call on text the filler wrote
    (and on the staged statement file, whose own proofs are given)."""
    return {key for _ln, kind, key, _t in _scan(text) if kind == "method"}


def check(text: str, allowed: set[Key]) -> list[Violation]:
    """Every leaf of `text` that is not `sorry`, not whitelisted and not a
    filler-written leaf under the same statement and enclosing goal."""
    out: list[Violation] = []
    for ln, kind, key, t in _scan(text):
        if kind == "sorry":
            continue
        if kind == "apply":
            out.append(Violation(ln, t, "apply-script step; only `sorry` or a filler-written `by`"))
        elif kind == "initial":
            out.append(Violation(ln, t, "initial method that can close goals; use `proof -`, "
                                        "`proof (rule ...)`, `(cases ...)`, `(induction ...)`"))
        elif key in allowed or _WHITELIST_RE.match(mask(t)):
            continue
        else:
            out.append(Violation(ln, t, "method the filler did not produce for this statement "
                                        "(under this goal); put `sorry` here"))
    return out


def summarize(bad: list[Violation], limit: int | None = None) -> str:
    """Every offending line (the Q1 forced run's one rejection had 33; a cut
    list costs the model a round trip per 8 lines)."""
    shown = bad if limit is None else bad[:limit]
    lines = [f"  line {v.line}: `{v.text[:110]}` -- {v.reason}" for v in shown]
    if len(bad) > len(shown):
        lines.append(f"  ... and {len(bad) - len(shown)} more")
    return "\n".join(lines)


# ---- selftest ------------------------------------------------------------ #

def selftest() -> None:
    T = '''theory t imports Main
begin
text \\<open>proved by hand, by the way\\<close>
(* by simp *)
lemma a: "x = (x::nat)"
  by simp
lemma b: "P \\<longrightarrow> P"
proof -
  have h: "True" by auto
  show ?thesis
    using h by blast
qed
lemma c: "Q \\<longrightarrow> Q"
proof -
  show ?thesis by blast
qed
end
'''
    keys = leaf_keys(T)
    assert len(keys) == 4, keys
    assert ("", 'lemma a: "x = (x::nat)" by simp') in keys, keys
    # the same leaf text under a different enclosing goal is a different key
    b_show = [k for k in keys if k[1].startswith("show ?thesis using h")]
    c_show = [k for k in keys if k[1] == "show ?thesis by blast"]
    assert len(b_show) == 1 and b_show[0][0].startswith("lemma b"), keys
    assert len(c_show) == 1 and c_show[0][0].startswith("lemma c"), keys
    # a file whose leaves all come from `keys` passes; a hand-written one does not
    assert check(T, keys) == []
    hand = T.replace("show ?thesis by blast", "show ?thesis by simp")
    bad = check(hand, keys)
    assert len(bad) == 1 and bad[0].line == 15 and "filler" in bad[0].reason, bad
    # the comment / text block never counts as a leaf
    assert all(v.line not in (3, 4) for v in check(T, set()))
    # sorry is always fine; apply / proof (auto) / qed auto never are
    S = 'lemma d: "x = (x::nat)"\n  sorry\nlemma e: "x = (x::nat)"\n  apply simp\n  done\n' \
        'lemma f: "True"\nproof (auto)\nqed\nlemma g: "True"\nproof -\n  show ?thesis sorry\nqed simp\n'
    v = check(S, set())
    assert [x.line for x in v] == [4, 5, 7, 12], v
    assert "apply" in v[0].reason and "initial" in v[2].reason and "filler" in v[3].reason, v
    # goal-shaping initial methods are fine; the definition idioms are whitelisted
    OK = 'lemma h: "P"\nproof (rule ccontr)\n  assume "\\<not> P"\n  show False sorry\nqed\n' \
         'lemma i: "P"\nproof (induction n)\n  case 0 show ?case sorry\nqed\n' \
         'function f :: "nat \\<Rightarrow> nat" where "f n = n"\n  by pat_completeness auto\ntermination by lexicographic_order\n'
    assert check(OK, set()) == [], check(OK, set())
    # `by` inside a string or cartouche is masked
    assert check('lemma "by_x = by_x"\n  sorry\n', set()) == []
    # nested proofs: the inner leaf is keyed by the inner goal, and leaves
    # written after the inner qed are keyed by the outer goal again
    N = 'lemma j: "A"\nproof -\n  have k: "B"\n  proof -\n    show ?thesis by simp\n  qed\n  show ?thesis using k by blast\nqed\n'
    nk = leaf_keys(N)
    inner = [k for k in nk if k[1] == "show ?thesis by simp"]
    outer = [k for k in nk if k[1].startswith("show ?thesis using k")]
    assert inner and inner[0][0] == 'lemma j: "A" > have k: "B"', nk
    assert outer and outer[0][0].startswith("lemma j"), nk
    print("leaves selftest: PASSED")


if __name__ == "__main__":
    selftest()
