#!/usr/bin/env python3
"""
SHRINCS-L swn=140 expected signing time for any harness/esp-idf L logs, by the method of
docs/knowledge/shrincs-l-grinding-time-method.md (the same arithmetic as grind_fit.py,
which reads only the original results/raw/ logs).

Usage: grind_fit_logs.py <pq-sig-bench root> LOG...
Needs the host counters in results/raw/host/r1/host-sigs-L/ and
results/raw/host/r1/host-L-swn{96,140}.csv.

Single-core log: least-squares fit time = fixed + attempts x per-attempt over all swn=96
and swn=140 rows, attempts = counter + 1; expected = fixed + per-attempt x E.
Dual-core log: fixed = mean swn=96 time; per-attempt time of core 0 (even counters) and
core 1 (odd counters) from the swn=140 rows whose output matches the host; expected =
fixed + E / (1/t0 + 1/t1).
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
    e140 = float(Fraction(4 ** L, ways(140)))

    for path in sys.argv[2:]:
        rows = []
        dual = False
        for line in open(path, errors="replace"):
            f = line.strip().split(",")
            if len(f) == 12 and f[2] == "shrincs_sign":
                rows.append((int(f[3]), int(f[4]), float(f[5]), f[8]))
                dual = dual or "dual-core" in f[1]
        mism = [(s, x) for s, x, t, h in rows if hh[s].get(x) != h]
        name = os.path.basename(path)
        if not dual:
            pts = [(ctr[s][x] + 1, t) for s, x, t, h in rows]
            n = len(pts)
            mx = sum(p[0] for p in pts) / n
            my = sum(p[1] for p in pts) / n
            sxx = sum((p[0] - mx) ** 2 for p in pts)
            b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
            a = my - b * mx
            resid = max(abs(p[1] - (a + b * p[0])) for p in pts)
            print(f"{name}: rows={n} mismatches vs host={len(mism)} fixed={a:.4f} s "
                  f"per-attempt={b * 1e6:.2f} us maxresid={resid:.3f} s "
                  f"expected swn140={a + b * e140:.2f} s")
            continue
        r96 = [t for s, x, t, h in rows if s == 96]
        fixed = sum(r96) / len(r96)
        ev, od = [], []
        for s, x, t, h in rows:
            if s != 140 or hh[s].get(x) != h:
                continue
            c = ctr[140][x]
            if c % 2 == 0:
                ev.append((t - fixed) / (c // 2 + 1))
            else:
                od.append((t - fixed) / ((c + 1) // 2))
        t0 = sum(ev) / len(ev)
        t1 = sum(od) / len(od)
        print(f"{name}: rows={len(rows)} differing from host={mism} fixed={fixed:.4f} s "
              f"core0 {t0 * 1e6:.2f} us (n={len(ev)}) "
              f"core1 {t1 * 1e6:.2f} us (n={len(od)}) "
              f"expected swn140={fixed + e140 / (1 / t0 + 1 / t1):.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
