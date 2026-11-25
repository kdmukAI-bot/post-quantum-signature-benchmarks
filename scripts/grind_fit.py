"""Grinding analysis for SHRINCS-L signing: counters, exact expected attempts, and per-attempt
time fits for each platform's measured runs.

Usage: grind_fit.py <pq-sig-bench root>
Inputs: results/raw/host/r1/host-sigs-L/ and results/raw/host/r1/host-L-swn{96,140}.csv
from the host build:
  harness/linux/build/host-shrincsL-openssl/pq_bench --board host --build L \
      --op shrincs_sign --swn 140 -n 100 --save results/raw/host/r1/host-sigs-L \
      --save-all --header > results/raw/host/r1/host-L-swn140.csv
  (and the same with --swn 96), plus results/raw/ for the device runs.
Method: docs/knowledge/shrincs-l-grinding-time-method.md
"""
import csv
import glob
import os
import sys
from fractions import Fraction

ROOT = sys.argv[1]
W, L = 4, 64


def ways(target):
    # Number of L-digit base-W strings whose digits sum to target
    dp = [1]
    for _ in range(L):
        nxt = [0] * (len(dp) + W - 1)
        for s, c in enumerate(dp):
            for d in range(W):
                nxt[s + d] += c
        dp = nxt
    return dp[target] if target < len(dp) else 0


def counters(swn):
    out = {}
    for x in range(100):
        p = os.path.join(ROOT, "results/raw/host/r1/host-sigs-L", f"shrincs_sign_swn{swn}_run{x}.bin")
        b = open(p, "rb").read()
        out[x] = int.from_bytes(b[48:52], "big")
    return out


def host_hashes(swn):
    rows = list(csv.DictReader(open(os.path.join(ROOT, f"results/raw/host/r1/host-L-swn{swn}.csv"))))
    return dict((int(r["run"]), r["out_sha256"]) for r in rows)


def esp_rows(path):
    rows = []
    for line in open(path, errors="replace"):
        f = line.strip().split(",")
        if len(f) >= 12 and f[2] == "shrincs_sign":
            rows.append((int(f[3]), int(f[4]), float(f[5]), f[8]))
    return rows


def pi_rows(path):
    rows = []
    for r in csv.DictReader(open(path)):
        if r["op"] == "shrincs_sign" and r["swn"] in ("96", "140") and "shrincs-l" in r["build"]:
            rows.append((int(r["swn"]), int(r["run"]), float(r["wall_s"]), r["out_sha256"]))
    return rows


def fit(points):
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    b = sxy / sxx
    a = my - b * mx
    resid = max(abs(p[1] - (a + b * p[0])) for p in points)
    return a, b, resid


ctr = dict((swn, counters(swn)) for swn in (96, 140))
hh = dict((swn, host_hashes(swn)) for swn in (96, 140))
total = 4 ** L
exp_att = dict((swn, Fraction(total, ways(swn))) for swn in (96, 140))
for swn in (96, 140):
    att = [ctr[swn][x] + 1 for x in range(100)]
    print(f"swn={swn}: exact expected attempts {float(exp_att[swn]):.1f}; "
          f"100-message sample mean {sum(att)/100:.1f}; messages 0-9 mean {sum(att[:10])/10:.1f}")
print("counters swn140 msgs 0-9:", [ctr[140][x] for x in range(10)])

sources = [("pi0w openssl", "pi", glob.glob(os.path.join(ROOT, "results/raw/pi0w/r1/*.csv"))[0])]
for chip, d in (("esp32p4", "p4"), ("esp32s3", "s3")):
    for v in ("soft-dc0", "hw-dc0", "hw-dc1"):
        sources.append((f"{chip} {v}", "esp",
                        os.path.join(ROOT, f"results/raw/{chip}/r1/{d}-L-{v}-direct-r10.log")))

for name, kind, path in sources:
    rows = pi_rows(path) if kind == "pi" else esp_rows(path)
    mism = sum(1 for swn, x, t, h in rows if hh[swn].get(x) != h)
    pts = [(ctr[swn][x] + 1, t) for swn, x, t, h in rows]
    if "dc1" in name:
        print(f"{name:22s} rows={len(rows):3d} hash mismatches vs host={mism}")
        continue
    a, b, resid = fit(pts)
    e140 = a + b * float(exp_att[140])
    e96 = a + b * float(exp_att[96])
    print(f"{name:22s} rows={len(rows):3d} hash mismatches vs host={mism}  "
          f"fixed={a:.4f}s per-attempt={b*1e6:.2f}us maxresid={resid:.3f}s  "
          f"expected swn96={e96:.3f}s swn140={e140:.2f}s")

print()
# Dual-core: core 0 (SHA engine) takes even counters, core 1 (plain C) takes odd ones.
# When the output matches the host (lowest valid counter c found), time = fixed + attempts
# on the winning core: c/2+1 on core 0 (even c) or (c+1)/2 on core 1 (odd c).
for chip, d in (("esp32p4", "p4"), ("esp32s3", "s3")):
    rows = esp_rows(os.path.join(ROOT, f"results/raw/{chip}/r1/{d}-L-hw-dc1-direct-r10.log"))
    mism = [(swn, x, t) for swn, x, t, h in rows if hh[swn].get(x) != h]
    print(f"{chip} dual-core rows differing from host (swn, msg, s): {mism}")
    fixed = sum(t for swn, x, t, h in rows if swn == 96) / sum(1 for r in rows if r[0] == 96)
    ev, od = [], []
    for swn, x, t, h in rows:
        if swn != 140 or hh[swn].get(x) != h:
            continue
        c = ctr[140][x]
        if c % 2 == 0:
            ev.append((t - fixed) / (c // 2 + 1))
        else:
            od.append((t - fixed) / ((c + 1) // 2))
    t0 = sum(ev) / len(ev)
    t1 = sum(od) / len(od)
    e = float(exp_att[140])
    exp_dual = fixed + e / (1 / t0 + 1 / t1)
    print(f"  core0 per-attempt {t0*1e6:.2f}us (n={len(ev)}, range "
          f"{min(ev)*1e6:.2f}-{max(ev)*1e6:.2f}), core1 {t1*1e6:.2f}us (n={len(od)}, range "
          f"{min(od)*1e6:.2f}-{max(od)*1e6:.2f}); expected swn140 {exp_dual:.2f}s")
