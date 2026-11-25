#!/usr/bin/env python3
"""
SHRINCS-L grinding fit for any pq_bench CSV, with the same method as scripts/grind_fit.py
(which reads the baseline Pi CSV only): least-squares fit of wall time against the number
of grinding attempts over the swn=96 and swn=140 rows, then the expected signing time at
the exact expected attempt count for each swn. Method:
docs/knowledge/shrincs-l-grinding-time-method.md.

Usage: grind_fit_csv.py <pq-sig-bench root> CSV...
Needs results/raw/host/r1/host-sigs-L/ and results/raw/host/r1/host-L-swn{96,140}.csv from
the host build (see grind_fit.py) for the counters and the reference output hashes.
"""
import csv
import os
import sys
from fractions import Fraction

W, L = 4, 64


def ways(target):
    dp = [1]
    for _ in range(L):
        nxt = [0] * (len(dp) + W - 1)
        for s, c in enumerate(dp):
            for d in range(W):
                nxt[s + d] += c
        dp = nxt
    return dp[target] if target < len(dp) else 0


def main():
    root = sys.argv[1]
    ctr, hh = {}, {}
    for swn in (96, 140):
        ctr[swn] = {}
        for x in range(100):
            p = os.path.join(root, "results/raw/host/r1/host-sigs-L", f"shrincs_sign_swn{swn}_run{x}.bin")
            ctr[swn][x] = int.from_bytes(open(p, "rb").read()[48:52], "big")
        rows = csv.DictReader(open(os.path.join(root, f"results/raw/host/r1/host-L-swn{swn}.csv")))
        hh[swn] = dict((int(r["run"]), r["out_sha256"]) for r in rows)
    exp_att = dict((swn, float(Fraction(4 ** L, ways(swn)))) for swn in (96, 140))

    for path in sys.argv[2:]:
        pts, mism = [], 0
        for r in csv.DictReader(open(path)):
            if r["op"] != "shrincs_sign" or r["swn"] not in ("96", "140"):
                continue
            if "shrincs-l" not in r["build"]:
                continue
            swn, x = int(r["swn"]), int(r["run"])
            mism += hh[swn].get(x) != r["out_sha256"]
            pts.append((ctr[swn][x] + 1, float(r["wall_s"])))
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sum((p[0] - mx) ** 2 for p in pts)
        a = my - b * mx
        resid = max(abs(p[1] - (a + b * p[0])) for p in pts)
        print(f"{os.path.basename(path)}: rows={n} hash mismatches vs host={mism} "
              f"fixed={a:.4f}s per-attempt={b * 1e6:.2f}us maxresid={resid:.3f}s "
              f"expected swn96={a + b * exp_att[96]:.3f}s swn140={a + b * exp_att[140]:.2f}s")


if __name__ == "__main__":
    main()
