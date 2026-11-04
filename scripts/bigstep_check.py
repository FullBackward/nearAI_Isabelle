#!/usr/bin/env python3
"""bigstep_check.py - does a statement file build on the Pool Server?

A lease-free check of hand-written or imported statement files (`problems/`)
through the server's bigstep endpoint (`isabelle build` of the whole theory,
the same path the verifier's `build_check` uses). No session, no LSP, no
model. Because a plain build rejects `sorry` ("Cheating requires
quick_and_dirty mode"), the copy sent to the server gets
`declare [[quick_and_dirty]]` injected right after `begin`; nothing else is
changed and the file on disk is never touched. A PASS therefore means: the
header resolves on an existing heap, every definition type-checks and every
statement parses. It says nothing about provability.

    python3 scripts/bigstep_check.py problems/imo2026/isabelle/*.thy
    python3 scripts/bigstep_check.py --timeout 900 problems/imo2026/isabelle/imo_2026_p2.thy

Exit status is the number of failing files (capped at 125).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import ib  # noqa: E402

_BEGIN_RE = re.compile(r"\bbegin\b")


def with_quick_and_dirty(text: str) -> str:
    _, _, after_begin = ib.parse_header(text)
    return text[:after_begin] + "\n\ndeclare [[quick_and_dirty]]\n" + text[after_begin:]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--timeout", type=float, default=ib.BUILD_TIMEOUT, help="per-file build timeout (s)")
    p.add_argument("--gym-url", default=ib.GYM_URL)
    p.add_argument("--no-quick-and-dirty", action="store_true",
                   help="send the file as is (a file with sorry then FAILS, by design)")
    args = p.parse_args(argv)

    failures = 0
    for f in args.files:
        path = Path(f)
        text = path.read_text(encoding="utf-8")
        try:
            name, imports, _ = ib.parse_header(text)
        except ValueError as ex:
            print(f"FAIL {path.name}: {ex}")
            failures += 1
            continue
        if name != path.stem:
            print(f"FAIL {path.name}: theory name {name!r} != file stem")
            failures += 1
            continue
        entry = {"name": name, "field": ib.derive_field(imports)}
        sent = text if args.no_quick_and_dirty else with_quick_and_dirty(text)
        t0 = time.time()
        ok, out = ib.build_check(sent, entry, timeout=args.timeout, gym_url=args.gym_url)
        dt = time.time() - t0
        n_sorry = len(re.findall(r"\bsorry\b", ib.strip_comments(text)))
        if ok:
            print(f"PASS {path.name}  field={entry['field']}  sorries={n_sorry}  {dt:.0f}s")
        else:
            failures += 1
            print(f"FAIL {path.name}  field={entry['field']}  {dt:.0f}s")
            for line in out.strip().splitlines()[-25:]:
                print("    " + line)
        sys.stdout.flush()
    return min(failures, 125)


if __name__ == "__main__":
    sys.exit(main())
