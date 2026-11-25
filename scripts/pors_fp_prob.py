#!/usr/bin/env python3
"""
Exact probability that one PORS+FP grinding attempt in Jade's SHRINCS code succeeds, and the
expected number of attempts per stateless signature.

pors_grind() (third_party/jade-hbs/main/shrincs/pors_fp.c) repeats until pors_octopus() accepts: the K
leaf indices drawn from the attempt's digest must have an Octopus authentication set of at
most M_MAX nodes. pors_msg_to_indices() draws 24-bit candidates and rejects values >= T and
repeats, so the K indices are a uniformly random K-subset of [0, T).

The tree (pors_octopus(), pors_treehash()): a binary tree of height B whose 2^(B-1) level-1
nodes are either internal with two leaf children (the first s = T - 2^(B-1) of them, holding
leaves 0 .. 2s-1) or leaves themselves (the rest, holding leaves 2s .. T-1). The
authentication set holds every sibling of a node on a path from a chosen leaf to the root
that is not itself on such a path.

Dynamic programming over the tree: for a subtree, f[j][a] counts the ways to choose j leaves
in it with a authentication nodes inside it. At a node with children L and R:
  j_L > 0, j_R > 0: a = a_L + a_R;  only one side chosen: a = a_side + 1;  none: a = 0.
Subtrees are complete over two-leaf level-1 nodes ("full"), complete over leaf level-1 nodes
("half"), or the one per level that straddles index s ("mixed").

Usage: pors_fp_prob.py [--k K] [--m-max M] [--t T] [--b B]  (defaults: Jade's SHRINCS-B and
SHRINCS-L constants, which share these values)
"""
import argparse
import sys
from fractions import Fraction
from math import comb


def combine(fl, fr, kmax, amax):
    out = [[0] * (amax + 1) for _ in range(kmax + 1)]
    for jl in range(kmax + 1):
        for al, cl in enumerate(fl[jl]):
            if not cl:
                continue
            for jr in range(kmax + 1 - jl):
                for ar, cr in enumerate(fr[jr]):
                    if not cr:
                        continue
                    if jl and jr:
                        a = al + ar
                    elif jl:
                        a = al + 1
                    elif jr:
                        a = ar + 1
                    else:
                        a = 0
                    if a <= amax:
                        out[jl + jr][a] += cl * cr
    return out


def distributions(k=6, m_max=91, t=9245141, b=24):
    """Returns (s, C(T,K), full-path size counts, Jade-code size counts)."""
    s = t - (1 << (b - 1))
    assert 0 < s < (1 << (b - 1))
    amax = k * b  # no authentication set is larger

    leaf = [[0] * (amax + 1) for _ in range(k + 1)]
    leaf[0][0] = 1
    leaf[1][0] = 1
    # full[h]: subtree whose root is at level h, all of whose level-1 nodes are internal
    # half[h]: subtree whose root is at level h, all of whose level-1 nodes are leaves
    full = {0: leaf}
    half = {1: leaf}
    for h in range(1, b + 1):
        full[h] = combine(full[h - 1], full[h - 1], k, amax)
        if h >= 2:
            half[h] = combine(half[h - 1], half[h - 1], k, amax)

    # Mixed subtrees along the path to level-1 node s. At level h the subtree containing
    # level-1 node s covers level-1 nodes [idx * 2^(h-1), (idx + 1) * 2^(h-1)).
    def subtree(h, idx):
        lo = idx << (h - 1)
        hi = (idx + 1) << (h - 1)
        if hi <= s:
            return full[h]
        if lo >= s:
            return half[h]
        return combine(subtree(h - 1, 2 * idx), subtree(h - 1, 2 * idx + 1), k, amax)

    # With the early stop: a selection stops at the lowest level h at which every chosen
    # leaf is under node (h, 0). Selections inside the leftmost level-h subtree whose left
    # child is empty, or whose two children are both non-empty, stop exactly at h (one
    # whose right child is empty stopped lower and is counted there). The authentication
    # set is then the nodes inside that subtree.
    def stop_counts(fl, fr):
        out = [0] * (amax + 1)
        for jl in range(k + 1):
            jr = k - jl
            if jr == 0:
                continue  # all in the left child: stopped at a lower level
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

    stops = [0] * (amax + 1)
    if k <= 2:
        # every chosen leaf under level-1 node 0 (leaves 0 and 1; s > 0 so it has two)
        stops[0 if k == 2 else 1] += 1 if k == 2 else 2
    for h in range(2, b + 1):
        sc = stop_counts(subtree(h - 1, 0), subtree(h - 1, 1))
        for a, c in enumerate(sc):
            stops[a] += c

    root = subtree(b, 0)
    total = sum(root[k])
    assert total == comb(t, k), (total, comb(t, k))
    assert sum(stops) == total, (sum(stops), total)
    return s, total, root[k], stops


def expected_attempts(k=6, m_max=91, t=9245141, b=24):
    """Expected PORS+FP grinding attempts per signature for Jade's code (exact)."""
    _, total, _, stops = distributions(k, m_max, t, b)
    return float(Fraction(total, sum(stops[: m_max + 1])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--m-max", type=int, default=91)
    ap.add_argument("--t", type=int, default=9245141)
    ap.add_argument("--b", type=int, default=24)
    args = ap.parse_args()
    k, m_max, t, b = args.k, args.m_max, args.t, args.b
    s, total, full_paths, stops = distributions(k, m_max, t, b)
    print(f"T={t} B={b} K={k} M_MAX={m_max} s={s}")
    for label, dist in (("full paths to the root", full_paths), ("as Jade's code counts", stops)):
        ok = sum(dist[: m_max + 1])
        p = Fraction(ok, total)
        mean_a = Fraction(sum(a * c for a, c in enumerate(dist)), total)
        print(f"{label}: mean set size {float(mean_a):.4f} nodes, "
              f"P(accept) = {float(p):.6e}, expected attempts = {float(1 / p):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
