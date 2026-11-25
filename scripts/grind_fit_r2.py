#!/usr/bin/env python3
"""
Round-2 per-message expected-value fits for operations whose time depends on a
message-dependent amount of work. Reads round-2 rows from pq_bench CSVs (Pi Zero W) and
harness/esp-idf logs (ESP32 boards) alike; the grind column carries each signature's
counters, read on the device. Methods: docs/knowledge/shrincs-l-grinding-time-method.md,
docs/knowledge/shrincs-stateless-signing-in-jade.md, and
docs/knowledge/ml-dsa-signing-attempts.md.

Usage: grind_fit_r2.py [--attempts CSV] [--pors-work V=CSV ...] RESULT...
  --attempts   ML-DSA signing attempts per message (default:
               results/raw/host/r2/mldsa-attempts.csv, from scripts/r2_host_reference.sh)
  --pors-work  per-message PORS+FP tree work for SHRINCS variant V (default:
               results/raw/host/r2/pors-work-B.csv and pors-work-L.csv, from
               scripts/pors_work.c)

Fits, by least squares over all rows of one (file, build, op[, swn]) group:
  shrincs_sign, SHRINCS-L (swn 96 and 140 pooled when one file holds both), counter c
  from "wots=c":
      one core:  t = fixed + per_attempt * (c + 1)
      two cores: t = fixed + t0 * n0 + t1 * n1, where the counter's parity says which core
                 found it: even c gives n0 = c/2 + 1 attempts on core 0, odd c gives
                 n1 = (c + 1)/2 on core 1 (Blockstream's even/odd split)
      expected(swn) = fixed + per_attempt * E(swn), or fixed + E(swn) * h with
                 h = 1 / (1/t0 + 1/t1)
  shrincs_sign_stateless, "pors=p;wots0=a;wots1=b", plus th, the message's PORS+FP tree
  hash calls (pors_auth_path() rebuilds every authentication node's subtree, and
  pors_octopus() stops early when all K leaves lie under the leftmost node of a lower
  level, so th ranges from about 0.06 to 1.0 of a whole-tree rebuild between messages):
      one core:  t = fixed + k_pors * (p + 1) + k_wots * (a + b + 2) + k_tree * th
      two cores: t = fixed + k_pors * (p + 1) + k_tree * th + t0 * n0 + t1 * n1 (WOTS+C
                 attempts of both layers split by parity; the PORS+FP grinding and tree
                 hashing have no dual-core path)
      expected = fixed + k_pors * E_pors + 2 * E_wots(SWN) * k_wots + k_tree * E_tree
                 (two cores: fixed + k_pors * E_pors + k_tree * E_tree + 2 * E_wots * h)
  mldsa<set>[_lowram]_sign, attempts per message from --attempts (the host counting build;
  outputs are deterministic, so the counts hold on every board):
      t = fixed + per_attempt * attempts; expected = fixed + per_attempt * E, with E the
      key-averaged mean that mldsa-native's test suite gives (4.361, 5.138, 3.906, which
      it says match the FIPS 204 errata) and, for comparison, the host mean over 20,000
      messages for the benchmark's own key.

Constants, exact for Jade's code: E(swn) for WOTS+C is W^L / #(L-digit base-W strings with
digit sum swn); E_pors = 1,659,626.0 attempts (scripts/pors_fp_prob.py); E_tree =
18,235,751.1 hash calls (scripts/pors_stop_levels.py).

Every fit also gives the standard error of its expected value (least squares covariance,
sigma^2 from the residuals; delta method for the two-core harmonic term). It covers the
fit only, not the spread of the per-message work around its expectation.

The stateless model includes the tree term; without it, residuals reach 38 s on Pi Zero
runs of 59 to 300 s. The functions below are importable; scripts/report/round2.py uses
them.
"""
import argparse
import collections
import csv
import importlib.util
import math
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOST_DIR = os.path.join(ROOT, "results", "raw", "host", "r2")
R2_COLS = ["board", "build", "op", "swn", "run", "wall_s", "cpu_s", "out_bytes", "out_sha256",
           "verified", "stack_peak_bytes", "heap_peak_bytes", "heap_min_free_bytes", "grind"]
WL = dict((("B", (256, 16)), ("L", (4, 64))))
SWN = dict((("B", 2040), ("L", 140)))
MLDSA_E_LIB = dict((("44", 4.361), ("65", 5.138), ("87", 3.906)))
_CONST = dict()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ways(w, l, target):
    dp = [1]
    for _ in range(l):
        nxt = [0] * (len(dp) + w - 1)
        for s, c in enumerate(dp):
            if c:
                for d in range(w):
                    nxt[s + d] += c
        dp = nxt
    return dp[target] if target < len(dp) else 0


def e_wots(v, swn):
    w, l = WL[v]
    return float(Fraction(w ** l, ways(w, l, swn)))


def e_pors():
    if "pors" not in _CONST:
        mod = load("pors_fp_prob", os.path.join(HERE, "pors_fp_prob.py"))
        _CONST["pors"] = mod.expected_attempts()
    return _CONST["pors"]


def e_tree():
    if "tree" not in _CONST:
        mod = load("pors_stop_levels", os.path.join(HERE, "pors_stop_levels.py"))
        _CONST["tree"] = mod.expected_tree_hashes()
    return _CONST["tree"]


def solve(a, b):
    """Solves a x = b (Gaussian elimination with partial pivoting); a is k x k."""
    k = len(a)
    a = [row[:] for row in a]
    b = b[:]
    for c in range(k):
        p = max(range(c, k), key=lambda i: abs(a[i][c]))
        if abs(a[p][c]) < 1e-300:
            raise ValueError("singular fit (a regressor does not vary)")
        a[c], a[p] = a[p], a[c]
        b[c], b[p] = b[p], b[c]
        for i in range(c + 1, k):
            f = a[i][c] / a[c][c]
            for j in range(c, k):
                a[i][j] -= f * a[c][j]
            b[i] -= f * b[c]
    x = [0.0] * k
    for i in range(k - 1, -1, -1):
        x[i] = (b[i] - sum(a[i][j] * x[j] for j in range(i + 1, k))) / a[i][i]
    return x


def lstsq(xs, ys):
    """Least squares with an intercept; xs is a list of regressor tuples. Returns
    (coefficients with the intercept first, max |residual|, covariance matrix or None)."""
    rows = [(1.0,) + tuple(float(v) for v in x) for x in xs]
    k = len(rows[0])
    # scale columns for conditioning
    sc = [max(abs(r[j]) for r in rows) or 1.0 for j in range(k)]
    rs = [[r[j] / sc[j] for j in range(k)] for r in rows]
    a = [[sum(r[i] * r[j] for r in rs) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * y for r, y in zip(rs, ys)) for i in range(k)]
    cs = solve(a, b)
    coef = [c / s for c, s in zip(cs, sc)]
    res = [y - sum(c * v for c, v in zip(coef, r)) for r, y in zip(rows, ys)]
    cov = None
    if len(rows) > k:
        s2 = sum(e * e for e in res) / (len(rows) - k)
        inv = [solve(a, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
        cov = [[s2 * inv[j][i] / (sc[i] * sc[j]) for j in range(k)] for i in range(k)]
    return coef, max(abs(e) for e in res), cov


def se_linear(cov, c):
    if cov is None:
        return float("nan")
    return math.sqrt(max(0.0, sum(c[i] * cov[i][j] * c[j] for i in range(len(c))
                                  for j in range(len(c)))))


def rows(path):
    """Round-2 rows of one result file (pq_bench CSV or harness/esp-idf log); other lines are
    skipped."""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    for ln in text.split("\n"):
        parts = ln.strip("\r").split(",")
        if len(parts) != len(R2_COLS) or parts[0] == "board":
            continue
        r = dict(zip(R2_COLS, parts))
        try:
            r["run"] = int(r["run"])
            r["wall_s"] = float(r["wall_s"])
        except ValueError:
            continue
        yield r


def grind(r):
    return dict((kv.split("=")[0], int(kv.split("=")[1])) for kv in r["grind"].split(";") if kv)


def variant(build):
    b = build.lower()
    return "L" if "shrincs-l" in b else "B"


def is_dual(build):
    return "dual-core" in build


def parity_split(counters):
    n0 = sum(c // 2 + 1 for c in counters if c % 2 == 0)
    n1 = sum((c + 1) // 2 for c in counters if c % 2 == 1)
    return n0, n1


def load_attempts(path):
    """ML-DSA attempts per (parameter set, message), and the mean per parameter set."""
    attempts = dict()
    per = collections.defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            ps = r["op"][5:7]
            a = int(r["grind"].split("=")[1])
            attempts[(ps, int(r["run"]))] = a
            per[ps].append(a)
    return attempts, dict((ps, sum(v) / len(v)) for ps, v in per.items())


def load_tree_work(paths=None):
    """Per-message PORS+FP tree hash calls: dict variant -> dict message -> count."""
    if paths is None:
        paths = dict((v, os.path.join(HOST_DIR, f"pors-work-{v}.csv")) for v in ("B", "L"))
    work = dict()
    for v, p in paths.items():
        if os.path.exists(p):
            with open(p) as f:
                work[v] = dict((int(r["x"]), int(r["tree_hashes"])) for r in csv.DictReader(f))
    return work


def fit_mldsa(rs, ps, attempts, host_mean=None):
    """ML-DSA signing: dict with expected (s) at E_lib, se, resid, fixed, per_attempt,
    expected_host (at the benchmark key's host mean), and the mean attempts of these
    messages."""
    ys = [r["wall_s"] for r in rs]
    xs = [(attempts[(ps, r["run"])],) for r in rs]
    (fx, k), res, cov = lstsq(xs, ys)
    e_lib = MLDSA_E_LIB[ps]
    e_host = (host_mean or dict()).get(ps)
    return dict((
        ("expected", fx + k * e_lib), ("se", se_linear(cov, (1.0, e_lib))), ("resid", res),
        ("fixed", fx), ("per_attempt", k), ("e", e_lib),
        ("expected_host", fx + k * e_host if e_host is not None else None),
        ("e_host", e_host), ("mean_attempts", sum(x[0] for x in xs) / len(xs)),
    ))


def fit_shrincs_l(rs, dual):
    """SHRINCS-L stateful signing (rows of every swn in one file, pooled): dict with
    expected per swn (96 and 140), se per swn, resid, and the coefficients."""
    ys = [r["wall_s"] for r in rs]
    cs = [grind(r)["wots"] for r in rs]
    exp = dict()
    se = dict()
    if dual:
        xs = [parity_split([c]) for c in cs]
        (fx, t0, t1), res, cov = lstsq(xs, ys)
        hm = 1 / (1 / t0 + 1 / t1)
        for s in (96, 140):
            ew = e_wots("L", s)
            exp[s] = fx + ew * hm
            se[s] = se_linear(cov, (1.0, ew * hm * hm / (t0 * t0), ew * hm * hm / (t1 * t1)))
        coef = dict((("fixed", fx), ("core0", t0), ("core1", t1)))
    else:
        (fx, k), res, cov = lstsq([(c + 1,) for c in cs], ys)
        for s in (96, 140):
            ew = e_wots("L", s)
            exp[s] = fx + k * ew
            se[s] = se_linear(cov, (1.0, ew))
        coef = dict((("fixed", fx), ("per_attempt", k)))
    out = dict((("expected", exp), ("se", se), ("resid", res), ("n", len(rs))))
    out.update(coef)
    return out


def fit_stateless(rs, v, swn, dual, work):
    """SHRINCS stateless signing with the tree-work term: dict with expected (s), se,
    resid, and the coefficients. work: load_tree_work() output."""
    ys = [r["wall_s"] for r in rs]
    g = [grind(r) for r in rs]
    th = [work[v][r["run"]] for r in rs]
    ep = e_pors()
    et = e_tree()
    ew = e_wots(v, int(swn))
    if dual:
        xs = [(x["pors"] + 1, t) + parity_split([x["wots0"], x["wots1"]])
              for x, t in zip(g, th)]
        (fx, kp, kt, t0, t1), res, cov = lstsq(xs, ys)
        hm = 1 / (1 / t0 + 1 / t1)
        exp = fx + kp * ep + kt * et + 2 * ew * hm
        grad = (1.0, ep, et, 2 * ew * hm * hm / (t0 * t0), 2 * ew * hm * hm / (t1 * t1))
        coef = dict((("core0", t0), ("core1", t1)))
    else:
        xs = [(x["pors"] + 1, x["wots0"] + x["wots1"] + 2, t) for x, t in zip(g, th)]
        (fx, kp, kw, kt), res, cov = lstsq(xs, ys)
        exp = fx + kp * ep + 2 * ew * kw + kt * et
        grad = (1.0, ep, 2 * ew, et)
        coef = dict((("k_wots", kw),))
    out = dict((
        ("expected", exp), ("se", se_linear(cov, grad)), ("resid", res), ("fixed", fx),
        ("k_pors", kp), ("k_tree", kt), ("e_pors", ep), ("e_tree", et), ("e_wots", ew),
        ("n", len(rs)), ("sample_mean", sum(ys) / len(ys)),
    ))
    out.update(coef)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", default=os.path.join(HOST_DIR, "mldsa-attempts.csv"),
                    help="ML-DSA attempts CSV from scripts/r2_host_reference.sh")
    ap.add_argument("--pors-work", action="append", default=[],
                    help="V=CSV: scripts/pors_work.c output for SHRINCS variant V")
    ap.add_argument("results", nargs="+")
    args = ap.parse_args()

    attempts, host_mean = dict(), dict()
    if os.path.exists(args.attempts):
        attempts, host_mean = load_attempts(args.attempts)
    work_paths = dict((v, os.path.join(HOST_DIR, f"pors-work-{v}.csv")) for v in ("B", "L"))
    for spec in args.pors_work:
        v, p = spec.split("=", 1)
        work_paths[v] = p
    work = load_tree_work(work_paths)

    for path in args.results:
        groups = collections.OrderedDict()
        for r in rows(path):
            op = r["op"]
            if op == "shrincs_sign" and variant(r["build"]) == "L":
                gk = (r["build"], op, "")
            elif op == "shrincs_sign_stateless" or (op.startswith("mldsa") and op.endswith("_sign")):
                gk = (r["build"], op, r["swn"])
            else:
                continue
            groups.setdefault(gk, []).append(r)
        name = os.path.basename(path)
        for (build, op, swn), rs in groups.items():
            dual = is_dual(build)
            v = variant(build)
            mean = sum(r["wall_s"] for r in rs) / len(rs)
            head = (f"{name}: {op}{(' swn=' + swn) if swn else ''}"
                    f"{' (two cores)' if dual else ''} n={len(rs)}")
            try:
                if op == "shrincs_sign":
                    f = fit_shrincs_l(rs, dual)
                    if dual:
                        tail = (f"core0={f['core0'] * 1e6:.3f} us core1={f['core1'] * 1e6:.3f} us")
                    else:
                        tail = f"per_attempt={f['per_attempt'] * 1e6:.4f} us"
                    print(f"{head}: fixed={f['fixed']:.4f} s {tail} maxresid={f['resid']:.3f} s "
                          f"expected swn96={f['expected'][96]:.3f} s "
                          f"swn140={f['expected'][140]:.2f} s (se {f['se'][140]:.3f} s)")
                elif op == "shrincs_sign_stateless":
                    if v not in work:
                        print(f"{head}: no fit (no pors-work file for SHRINCS-{v})")
                        continue
                    f = fit_stateless(rs, v, swn, dual, work)
                    if dual:
                        tail = f"core0={f['core0'] * 1e6:.3f} us core1={f['core1'] * 1e6:.3f} us"
                    else:
                        tail = f"per_wots_attempt={f['k_wots'] * 1e6:.4f} us"
                    print(f"{head}: fixed={f['fixed']:.3f} s per_pors_attempt="
                          f"{f['k_pors'] * 1e6:.4f} us {tail} per_tree_hash="
                          f"{f['k_tree'] * 1e6:.5f} us maxresid={f['resid']:.3f} s "
                          f"sample_mean={mean:.2f} s expected={f['expected']:.2f} s "
                          f"(se {f['se']:.2f} s; E_pors={f['e_pors']:.0f}, "
                          f"E_wots={f['e_wots']:.1f}, E_tree_hashes={f['e_tree']:.0f})")
                else:
                    ps = op[5:7]
                    if not attempts:
                        print(f"{head}: needs --attempts")
                        continue
                    f = fit_mldsa(rs, ps, attempts, host_mean)
                    eh = f["expected_host"]
                    print(f"{head}: fixed={f['fixed'] * 1e3:.3f} ms per_attempt="
                          f"{f['per_attempt'] * 1e3:.3f} ms maxresid={f['resid'] * 1e3:.3f} ms "
                          f"sample_mean={mean * 1e3:.2f} ms expected={f['expected'] * 1e3:.2f} ms "
                          f"(se {f['se'] * 1e3:.2f} ms; E={f['e']}; with the host mean "
                          f"{f['e_host']:.3f}: {eh * 1e3:.2f} ms)")
            except (ValueError, KeyError, ZeroDivisionError) as ex:
                print(f"{head}: no fit ({ex})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
