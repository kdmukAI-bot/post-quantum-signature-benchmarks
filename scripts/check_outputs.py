#!/usr/bin/env python3
"""
Correctness gate for pq_bench result CSVs: every row's out_sha256 must equal the reference
CSV's out_sha256 for the same (op, swn, run), and no row may report verified=0.

Self-test ops (shrincs_selftest, xmss_selftest) are checked against the reference as well,
and must report verified=1. SHRINCS rows are matched by variant through the build column
("shrincs-b" or "shrincs-l"), since the two variants share op names.

Usage: check_outputs.py REFERENCE_CSV RESULT_CSV...
Exit status 0 only if every row of every result file has a reference row and matches it.
"""
import csv
import sys


def variant(build):
    b = build.lower()
    if "shrincs-l" in b:
        return "L"
    if "shrincs-b" in b:
        return "B"
    return ""


def key(row):
    op = row["op"]
    v = variant(row["build"]) if op.startswith("shrincs") else ""
    return (op, v, row["swn"], int(row["run"]))


def load(path):
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("op")]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ref = {}
    for r in load(sys.argv[1]):
        ref.setdefault(key(r), r["out_sha256"])
    bad = 0
    total = 0
    for path in sys.argv[2:]:
        groups = {}
        for r in load(path):
            total += 1
            k = key(r)
            g = groups.setdefault(k[:3], [0, 0, 0])
            g[0] += 1
            problem = None
            if k not in ref:
                problem = "no reference row"
            elif ref[k] != r["out_sha256"]:
                problem = "output differs"
            elif r["verified"] == "0":
                problem = "verification failed"
            elif r["op"].endswith("_selftest") and r["verified"] != "1":
                problem = "self-test not verified"
            if problem:
                bad += 1
                g[1] += 1
                print(f"FAIL {path}: {r['op']} {k[1]} swn={r['swn']} run={r['run']}: {problem}")
            else:
                g[2] += 1
        for (op, v, swn), (n, nbad, nok) in sorted(groups.items()):
            label = f"{op}{('-' + v) if v else ''}{(' swn=' + swn) if swn else ''}"
            print(f"{'ok  ' if not nbad else 'FAIL'} {label}: {nok}/{n} rows match")
    print(f"{'PASS' if not bad else 'FAIL'}: {total - bad}/{total} rows match the reference")
    return 0 if not bad and total else 1


if __name__ == "__main__":
    sys.exit(main())
