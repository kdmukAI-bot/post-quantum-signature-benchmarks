#!/usr/bin/env python3
"""
Stop-level distribution of accepted PORS+FP selections in Jade's SHRINCS code, and the
expected authentication-path work per stateless signature (extends
scripts/pors_fp_prob.py, whose combine() it imports; the dynamic program is the same).

pors_octopus() stops at the lowest level h whose leftmost node holds every chosen leaf,
and pors_auth_path() then rebuilds, with pors_treehash(), every authentication node's
subtree. Those subtrees cover every leaf under the stop node except the K chosen ones, so
the work of one signature is
    tree_hashes = 3 * (leaves(h) - K) - |A|
(two hashes per leaf, the secret value and the leaf; one per internal node; a subtree with
n leaves has n - 1 internal nodes), where leaves(h) is the number of leaves under node
(h, 0) and |A| the size of the authentication set. Grinding repeats until |A| <= M_MAX, so
the expected work per signature is the mean over accepted selections. For Jade's constants
it is 18,235,751.1 hash calls (0.6575 of a whole-tree rebuild); scripts/grind_fit_r2.py
uses it as E_tree. Per-message work: scripts/pors_work.c.

Usage: pors_stop_levels.py [--k K] [--m-max M] [--t T] [--b B] [--check CSV ...]
  --check: pors_work.c output files; compares their stop levels with the distribution.
"""
import argparse
import collections
import csv
import importlib.util
import os
import sys
from fractions import Fraction
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pors_fp_prob",
                                               os.path.join(HERE, "pors_fp_prob.py"))
_pfp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pfp)
combine = _pfp.combine


def leaves_under_left(h, s):
    """Leaves under node (h, 0): level-1 nodes 0 .. 2^(h-1) - 1, two leaves each below
    s."""
    if h == 0:
        return 1
    n1 = 1 << (h - 1)
    return n1 + min(n1, s)


def by_stop_level(k=6, m_max=91, t=9245141, b=24):
    """Returns (s, C(T,K), dict h -> (accepted count, sum of |A| over accepted))."""
    s = t - (1 << (b - 1))
    amax = k * b
    leaf = [[0] * (amax + 1) for _ in range(k + 1)]
    leaf[0][0] = 1
    leaf[1][0] = 1
    full = dict(((0, leaf),))
    half = dict(((1, leaf),))
    for h in range(1, b + 1):
        full[h] = combine(full[h - 1], full[h - 1], k, amax)
        if h >= 2:
            half[h] = combine(half[h - 1], half[h - 1], k, amax)

    def subtree(h, idx):
        lo = idx << (h - 1)
        hi = (idx + 1) << (h - 1)
        if hi <= s:
            return full[h]
        if lo >= s:
            return half[h]
        return combine(subtree(h - 1, 2 * idx), subtree(h - 1, 2 * idx + 1), k, amax)

    def stop_counts(fl, fr):
        out = [0] * (amax + 1)
        for jl in range(k + 1):
            jr = k - jl
            if jr == 0:
                continue
            for al, cl in enumerate(fl[jl]):
                if not cl:
                    continue
                for ar, cr in enumerate(fr[jr]):
                    if not cr:
                        continue
                    a = al + ar if jl else ar + 1
                    if a <= amax:
                        out[a] += cl * cr
        return out

    if k <= 2:
        raise ValueError("k <= 2 not handled here")
    per = dict()
    total_stops = 0
    for h in range(2, b + 1):
        sc = stop_counts(subtree(h - 1, 0), subtree(h - 1, 1))
        total_stops += sum(sc)
        acc = sum(sc[: m_max + 1])
        asum = sum(a * c for a, c in enumerate(sc[: m_max + 1]))
        per[h] = (acc, asum)
    total = comb(t, k)
    assert total_stops == total, (total_stops, total)
    return s, total, per


def expected_tree_hashes(k=6, m_max=91, t=9245141, b=24):
    """E[tree_hashes] over accepted selections, as a float (exact rational underneath)."""
    s, _, per = by_stop_level(k, m_max, t, b)
    acc = sum(v[0] for v in per.values())
    e_leaves = Fraction(sum(c * leaves_under_left(h, s) for h, (c, _) in per.items()), acc)
    e_a = Fraction(sum(a for _, a in per.values()), acc)
    return float(3 * (e_leaves - k) - e_a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--m-max", type=int, default=91)
    ap.add_argument("--t", type=int, default=9245141)
    ap.add_argument("--b", type=int, default=24)
    ap.add_argument("--check", nargs="*", default=[])
    args = ap.parse_args()
    k, m_max, t, b = args.k, args.m_max, args.t, args.b
    s, total, per = by_stop_level(k, m_max, t, b)
    acc = sum(v[0] for v in per.values())
    p = Fraction(acc, total)
    print(f"T={t} B={b} K={k} M_MAX={m_max} s={s}: P(accept) = {float(p):.6e}, "
          f"expected attempts = {float(1 / p):.1f}")
    e_leaves = Fraction(sum(c * leaves_under_left(h, s) for h, (c, _) in per.items()), acc)
    e_a = Fraction(sum(a for _, a in per.values()), acc)
    e_th = 3 * (e_leaves - k) - e_a
    full_th = 3 * (t - k) - e_a
    print(f"accepted selections: E[leaves under stop node] = {float(e_leaves):,.1f} "
          f"(whole tree {t:,}), E[|A|] = {float(e_a):.3f}, "
          f"E[tree_hashes] = {float(e_th):,.1f} ({float(e_th / full_th):.4f} of a whole-tree "
          f"rebuild)")
    obs = collections.Counter()
    nobs = 0
    for path in args.check:
        for r in csv.DictReader(open(path)):
            obs[int(r["stop_level"])] += 1
            nobs += 1
    print("\n| Stop level | Leaves under stop node | P(stop level, accepted) | Cumulative |"
          + (f" Observed ({nobs} messages) |" if nobs else ""))
    print("|---|---|---|---|" + ("---|" if nobs else ""))
    cum = Fraction(0)
    for h in sorted(per):
        c, _ = per[h]
        if not c:
            continue
        q = Fraction(c, acc)
        cum += q
        extra = f" {obs.get(h, 0)} |" if nobs else ""
        print(f"| {h} | {leaves_under_left(h, s):,} | {float(q):.4f} | {float(cum):.4f} |{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
