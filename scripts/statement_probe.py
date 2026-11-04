#!/usr/bin/env python3
"""statement_probe.py - LLM-free pass over the manifest, straight against the
Pool Server HTTP API (no MCP, no model):

  parses      does the staged statement (with its `sorry`) load under the
              server's Isabelle (2026)? miniF2F/PutnamBench were written for
              older releases; a statement that fails to parse is excluded
              from the experiment rather than counted as a loss.
  sh_proved   does plain sledgehammer close the WHOLE theorem from the bare
              statement in `--sh-timeout` seconds (the server's fill_sorries
              on the single sorry)? These are the "sledgehammer-trivial"
              problems: both arms get them for free, so they dilute the
              comparison and `ib.py select --exclude-sh-trivial` drops them.

Writes/updates probe.json (resumable: problems already present are skipped
unless --redo). Problems are grouped by import set so warm sessions are
reused; --parallel bounds concurrent sessions (each is 1.5-4 GB on the server).

    python3 scripts/statement_probe.py --source minif2f --split test
    python3 scripts/statement_probe.py --subset subsets/pilot.txt --sh-timeout 60
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("ib", ROOT / "harness" / "ib.py")
ib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ib)

from client import PoolAsyncClient  # noqa: E402  (pip install -e Isabelle-Pool-Server/client)


async def probe_one(gym: PoolAsyncClient, entry: dict, variant: str, sh_timeout: int,
                    load_timeout: float, retries: int = 3) -> dict:
    """`_probe_once` with retries on the two transient server answers: 404 on
    the session (acquired warm, evicted before use) and 503 memory_pressure."""
    for attempt in range(retries):
        out = await _probe_once(gym, entry, variant, sh_timeout, load_timeout)
        err = str(out.get("error") or out.get("parse_error") or "")
        if "404" in err or "503" in err or "memory_pressure" in err:
            await asyncio.sleep(30 * (attempt + 1))
            continue
        return out
    return out


async def _probe_once(gym: PoolAsyncClient, entry: dict, variant: str, sh_timeout: int,
                      load_timeout: float) -> dict:
    out: dict = {"name": entry["name"], "field": entry["field"], "sessions": entry["sessions"]}
    text = ib.staged_text(entry, variant)
    t0 = time.time()
    try:
        s = await gym.acquire_session(theories=entry["imports"], field=entry["field"])
    except Exception as e:                               # noqa: BLE001
        out.update(parses=False, parse_error=f"acquire: {type(e).__name__}: {e}"[:400], sh_proved=False)
        return out
    sid, lease = s["session_id"], s["lease_id"]
    out["acquire_s"] = round(time.time() - t0, 1)
    try:
        # 1. parse: load the whole staged document
        rep = await gym.load_document(sid, text, report=True, timeout=load_timeout, lease_id=lease)
        cmds = rep.get("commands") or []
        errs = [f"line {c.get('line')} [{c.get('kind')}]: {m.get('text','')[:200]}"
                for c in cmds for m in (c.get("messages") or []) if m.get("sev") == "error"]
        out["parses"] = bool(rep.get("success")) and not errs
        if errs:
            out["parse_error"] = errs[:3]
        if not out["parses"]:
            out["sh_proved"] = False
            return out
        # 2. sledgehammer the single sorry
        t1 = time.time()
        job = await gym.fill_sorries(sid, text, mode="document", timeout_s=sh_timeout,
                                     max_total_s=sh_timeout + 60, load_timeout=load_timeout, lease_id=lease)
        while job.get("status") not in ("done", "cancelled", "error"):
            await asyncio.sleep(3)
            job = await gym.fill_status(sid, lease_id=lease)
        res = job.get("results") or []
        r0 = res[0] if res else {}
        out["sh_proved"] = r0.get("outcome") == "proved" and bool(r0.get("method"))
        out["sh_outcome"] = r0.get("outcome")
        out["sh_method"] = r0.get("method")
        out["sh_s"] = round(time.time() - t1, 1)
        if job.get("error"):
            out["sh_error"] = str(job["error"])[:300]
    except Exception as e:                               # noqa: BLE001
        out.setdefault("parses", False)
        out["sh_proved"] = False
        out["error"] = f"{type(e).__name__}: {e}"[:400]
    finally:
        try:
            await gym.release_session(sid, lease_id=lease)
        except Exception:                                # noqa: BLE001
            pass
    return out


async def main_async(args) -> int:
    man = ib.load_manifest()
    names = ib._filter(man, args)
    if args.subset:
        wanted = [ln.strip() for ln in Path(args.subset).read_text().splitlines() if ln.strip()]
        names = [n for n in wanted if n in man]
    if args.limit:
        names = names[: args.limit]
    out_path = Path(args.out)
    probe = json.loads(out_path.read_text()) if out_path.exists() else {}
    todo = [n for n in names if args.redo or n not in probe]
    print(f"{len(todo)} to probe ({len(names) - len(todo)} already done) -> {out_path}", flush=True)
    # group by import set so a worker's warm session is reused
    todo.sort(key=lambda n: (man[n]["field"], ",".join(man[n]["imports"]), n))
    sem = asyncio.Semaphore(args.parallel)
    lock = asyncio.Lock()
    done = 0

    async with PoolAsyncClient(args.gym_url, timeout=args.load_timeout + 120) as gym:
        async def work(n: str):
            nonlocal done
            async with sem:
                r = await probe_one(gym, man[n], args.variant, args.sh_timeout, args.load_timeout)
            async with lock:
                probe[n] = r
                done += 1
                out_path.write_text(json.dumps(probe, indent=1, ensure_ascii=False))
                print(f"[{done}/{len(todo)}] {n}: parses={r.get('parses')} sh={r.get('sh_proved')} "
                      f"{r.get('sh_outcome') or r.get('parse_error') or r.get('error') or ''}"[:160], flush=True)

        await asyncio.gather(*(work(n) for n in todo))
    n_p = sum(1 for n in names if probe.get(n, {}).get("parses"))
    n_s = sum(1 for n in names if probe.get(n, {}).get("sh_proved"))
    print(f"summary over {len(names)}: parses={n_p} sledgehammer-trivial={n_s}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["minif2f", "putnambench", "imo2026"])
    p.add_argument("--split", choices=["test", "valid"], help="minif2f split (manifest field)")
    p.add_argument("--category"); p.add_argument("--with-answer", action="store_true"); p.add_argument("--no-answer", action="store_true")
    p.add_argument("--subset"); p.add_argument("--limit", type=int, default=0)
    p.add_argument("--variant", choices=["wsolution", "full"], default="wsolution")
    p.add_argument("--sh-timeout", type=int, default=60)
    p.add_argument("--load-timeout", type=float, default=180.0)
    p.add_argument("--parallel", type=int, default=2)
    p.add_argument("--gym-url", default=ib.GYM_URL)
    p.add_argument("--out", default=str(ROOT / "probe.json"))
    p.add_argument("--redo", action="store_true")
    args = p.parse_args()
    if args.split:
        # ib._filter does not know `split`; narrow afterwards
        man = ib.load_manifest()
        keep = {n for n, e in man.items() if e.get("split") == args.split}
        orig = ib._filter
        ib._filter = lambda m, a: [n for n in orig(m, a) if n in keep]
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
