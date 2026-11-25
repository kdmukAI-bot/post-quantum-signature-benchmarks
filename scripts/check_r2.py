#!/usr/bin/env python3
"""
Round-2 correctness gate: every row of every result file must match the host reference
output for the same (SHRINCS variant, op, swn, run) and must not report verified=0.

Usage: check_r2.py --ref REFERENCE_CSV [--ref ...] RESULT...
  REFERENCE_CSV  host reference files (scripts/r2_host_reference.sh: reference-B.csv and
                 reference-L.csv)
  RESULT         round-2 pq_bench CSVs (Pi Zero W) and harness/esp-idf logs, in any mix

Rules:
  - verified must not be 0.
  - Rows that must verify (verified=1): every *_verify and *_selftest op, SLH-DSA, SPHINCS+,
    ML-DSA, and FN-DSA signing, SHRINCS stateless signing at swn = SWN (2040 for SHRINCS-B,
    140 for SHRINCS-L), and SHRINCS-L stateful signing at swn = 140 (Blockstream's fixed
    SHRINCS-L key is consistent; its SHRINCS-B key is not).
  - out_sha256 must equal the reference, except on dual-core ESP32 builds for the SHRINCS
    signing ops (shrincs_sign, shrincs_selftest, shrincs_sign_stateless), where
    Blockstream's dual-core grinding can return a different valid counter; such rows are
    reported as "differs (dual-core)" and must still verify where the rule above applies.
SHRINCS rows are matched by variant through the build column ("shrincs-b"/"shrincs-l").
Exit status 0 only if every row passes.
"""
import argparse
import collections
import sys

R2_COLS = ["board", "build", "op", "swn", "run", "wall_s", "cpu_s", "out_bytes", "out_sha256",
           "verified", "stack_peak_bytes", "heap_peak_bytes", "heap_min_free_bytes", "grind"]
SWN = dict((("B", "2040"), ("L", "140")))
DUAL_DIFF_OK = set(("shrincs_sign", "shrincs_selftest", "shrincs_sign_stateless"))


def rows(path):
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    for ln in text.split("\n"):
        ln = ln.strip("\r")
        if not ln or ln.startswith("#") or ln.startswith("board,"):
            continue
        parts = ln.split(",")
        if len(parts) != len(R2_COLS):
            continue
        r = dict(zip(R2_COLS, parts))
        try:
            r["run"] = int(r["run"])
            float(r["wall_s"])
        except ValueError:
            continue
        yield r


def variant(build):
    b = build.lower()
    if "shrincs-l" in b:
        return "L"
    if "shrincs-b" in b:
        return "B"
    return ""


def key(r):
    op = r["op"]
    v = variant(r["build"]) if op.startswith("shrincs") else ""
    return (op, v, r["swn"], r["run"])


def must_verify(r):
    op = r["op"]
    v = variant(r["build"])
    if op.endswith("_verify") or op.endswith("_selftest"):
        return True
    if op in ("slh_dsa_sign", "sphincs40_sign") or op.startswith(("mldsa", "fndsa")):
        return op.endswith("_sign")
    if op == "shrincs_sign_stateless":
        return r["swn"] == SWN.get(v)
    if op == "shrincs_sign":
        return v == "L" and r["swn"] == "140"
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", action="append", required=True)
    ap.add_argument("results", nargs="+")
    args = ap.parse_args()

    ref = {}
    for p in args.ref:
        for r in rows(p):
            ref.setdefault(key(r), r["out_sha256"])
    bad = 0
    total = 0
    for path in args.results:
        groups = collections.OrderedDict()
        for r in rows(path):
            total += 1
            k = key(r)
            g = groups.setdefault((r["build"], k[0], k[1], k[2]), collections.Counter())
            dual = "dual-core" in r["build"]
            problem = None
            note = None
            if r["verified"] == "0":
                problem = "verification failed"
            elif must_verify(r) and r["verified"] != "1":
                problem = f"verified={r['verified']}, expected 1"
            elif k not in ref:
                problem = "no reference row"
            elif ref[k] != r["out_sha256"]:
                if dual and r["op"] in DUAL_DIFF_OK:
                    note = "differs (dual-core)"
                else:
                    problem = "output differs"
            if problem:
                bad += 1
                g["fail"] += 1
                print(f"FAIL {path}: {r['op']} {k[1]} swn={r['swn']} run={r['run']}: {problem}")
            elif note:
                g["note"] += 1
            else:
                g["ok"] += 1
        for (build, op, v, swn), c in groups.items():
            n = sum(c.values())
            label = f"{op}{('-' + v) if v else ''}{(' swn=' + swn) if swn else ''}"
            extra = f", {c['note']} differ (dual-core, allowed)" if c["note"] else ""
            print(f"{'FAIL' if c['fail'] else 'ok  '} {path.split('/')[-1]}: {label}: "
                  f"{c['ok'] + c['note']}/{n} pass{extra}")
    print(f"{'PASS' if not bad and total else 'FAIL'}: {total - bad}/{total} rows pass")
    return 0 if not bad and total else 1


if __name__ == "__main__":
    sys.exit(main())
