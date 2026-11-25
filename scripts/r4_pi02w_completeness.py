#!/usr/bin/env python3
"""
Round 4, Pi Zero 2 W: checks a fetched run against its plan. For every job line of the plan
(scripts/r4_pi02w_queue.sh format), the raw directory must hold result files named as the
queue names them; the newest one must have exactly n data rows, runs 0 to n-1. Also lists
files of the round that no plan line explains, and .failed, .aborted, and .throttled files.

Usage: r4_pi02w_completeness.py PLAN [RAW_DIR]     (default results/raw/pi02w/r4)
Exit status 0 only if every line is complete and no failed, aborted, or throttled file
exists.
"""
import collections
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    plan = sys.argv[1]
    raw = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "results", "raw", "pi02w", "r4")
    jobs = []
    for ln in open(plan):
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("#"):
            continue
        f = ln.split("|")
        b, label, op, n = f[:4]
        swn = f[4] if len(f) > 4 else ""
        prefix = (f"pi02w-{label.split(' ')[0]}-{b[len('r4-pi02w-'):]}-{op}"
                  + (f"-swn{swn}" if swn else "") + f"-n{n}-")
        jobs.append((ln, prefix, int(n)))
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(raw, "pi02w-*")))
    used = set()
    bad = 0
    per_section = collections.Counter()
    for ln, prefix, n in jobs:
        text_op = ln.split("|")[2] in ("cbench", "cbench-armcap0", "probe")
        ext = "txt" if text_op else "csv"
        cands = [f for f in files if f.startswith(prefix)
                 and re.fullmatch(r"\d{8}_\d{6}\." + ext, f[len(prefix):])]
        used.update(cands)
        if not cands:
            print(f"MISSING {ln}")
            bad += 1
            continue
        f = cands[-1]
        if text_op:
            continue
        runs = []
        for row in open(os.path.join(raw, f)):
            parts = row.rstrip("\n").split(",")
            if len(parts) == 14 and parts[0] != "board":
                runs.append(int(parts[4]))
        if runs != list(range(n)):
            print(f"INCOMPLETE {f}: {len(runs)} rows, expected runs 0 to {n - 1}")
            bad += 1
        if len(cands) > 1:
            print(f"note: {len(cands)} files for {ln}; newest used, older: {', '.join(cands[:-1])}")
    for f in files:
        if f.endswith((".failed", ".aborted", ".throttled")):
            print(f"PROBLEM FILE {f}")
            bad += 1
        elif f.endswith(".csv") and f not in used and f.startswith("pi02w-r4-L"):
            print(f"note: no plan line for {f}")
    print(f"{'COMPLETE' if not bad else 'NOT COMPLETE'}: {len(jobs)} plan lines, {bad} problems")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
