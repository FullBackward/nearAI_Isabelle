# subsets/

Committed problem draws for the pass driver (`scripts/imo2026_pass.py --subset <file>`).
One problem name per line, nothing else (the queue reads the file verbatim).

## putnam36.txt (2026-11-11)

36 PutnamBench problems, three per slot A1-A6 and B1-B6, seeded, no probe or
property exclusion (owner's choice: switch the problem set, do not select for
a property). To reproduce from a manifest built by
`ib.py prepare --source putnambench --root benchmarks/putnambench/isabelle`:

```bash
.venv/bin/python harness/ib.py select --source putnambench --stratify category --n 36 --seed 1 --out /tmp/redraw.txt
diff subsets/putnam36.txt /tmp/redraw.txt      # identical on 2026-11-11 (manifest of 638 Isabelle statements)
```

The server runs the committed file, not a redraw, so the pass is the same 36
problems on every machine even if PutnamBench upstream changes.

`*_repeat.txt` and `*_unsolved.txt` are written by the driver's `report` and
`repeat --unsolved` and are ignored by git.
