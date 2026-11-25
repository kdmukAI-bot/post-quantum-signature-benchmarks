#!/usr/bin/env python3
"""
Checks the benchmark's saved SHRINCS stateful signatures with
BlockstreamResearch/shrincs-cpp (a separate C++ implementation by the group that wrote the
scheme; see scripts/shrincs_cpp_verify.cpp for what each mode checks), then ties the
checked files to the result rows through their SHA-256.

  - shrincs_selftest_run0.bin (consistent key from seed[i] = i + 0): full verification.
  - shrincs_sign_swn2040_run*.bin (SHRINCS-B) and shrincs_sign_swn140_run*.bin
    (SHRINCS-L), signed with Blockstream's fixed test key: which stored key parts match
    the key's seeds, plus every signature check short of the final root comparison, and
    full verification with the stored key (which only a consistent key can pass).
  - shrincs_sign_swn96_run*.bin are skipped: both implementations verify against the fixed
    target sum SWN = 140 for SHRINCS-L, so a signature ground to sum 96 cannot pass.

Row linkage: a result row (op, variant, swn, run) is "covered" when its out_sha256 equals
the SHA-256 of a checked file for the same key. Two-core ESP32 rows of SHRINCS may differ
in bytes (the first valid grinding counter found wins), so they are counted separately.

Usage: shrincs_cpp_verify.py --cpp-repo DIR [--results DIR] [--saved DIR ...]
The shrincs-cpp checkout is compiled (unmodified) into build/independent-verification.
"""
import argparse
import glob
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BUILD = os.path.join(ROOT, "build", "independent-verification")
DRIVER = os.path.join(ROOT, "scripts", "shrincs_cpp_verify.cpp")
# Blockstream's fixed SHRINCS test key (third_party/jade-hbs/main/process/sign_shrincs.c
# line 114; the same constant is SK_HEX in harness/common/op_shrincs.c): seed, prf, sf,
# sl, pk.seed, pk.root.
SK_HEX = ("0517400a7d4f5a532d4f34b077182caf1a79e406404e29a7feed94aa546330ac"
          "00ae2c282f33b319d83b705b4b5487c618311f77a5283cf39aabaf35dc3dfd79"
          "918fd17d889f34eb76a99a0c93a2015eda5a08dc47d1e05d0d4d816f72e78e27")
SIZE_VARIANT = {324: "B", 1092: "L"}


def build(cpp_repo):
    os.makedirs(BUILD, exist_ok=True)
    srcs = sorted(glob.glob(os.path.join(cpp_repo, "src", "*.cpp")))
    out = dict()
    for v in ("B", "L"):
        exe = os.path.join(BUILD, "shrincs_cpp_verify_" + v)
        subprocess.run(["g++", "-O2", "-std=c++17", "-Wno-deprecated-declarations",
                        "-DSHRINCS_" + v, "-I", os.path.join(cpp_repo, "include")] + srcs
                       + [DRIVER, "-lcrypto", "-pthread", "-o", exe], check=True)
        out[v] = exe
    return out


def git_rev(repo):
    p = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%H %ad",
                        "--date=short"], capture_output=True, text=True)
    return p.stdout.strip()


def parse(line):
    return dict(kv.split("=", 1) for kv in line.split())


def variant_of(build_label):
    b = build_label.lower()
    if "shrincs-l" in b or "shrincsl" in b:
        return "L"
    if "shrincs-b" in b or "shrincsb" in b:
        return "B"
    return None


def result_rows(results_dir):
    for dirpath, dirnames, filenames in os.walk(results_dir):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith((".csv", ".log")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", errors="replace")
            cols = None
            for ln in text.split("\n"):
                ln = ln.strip("\r")
                if ln.startswith("board,"):
                    cols = ln.split(",")
                    continue
                if not cols or "out_sha256" not in cols:
                    continue
                parts = ln.split(",")
                if len(parts) != len(cols):
                    continue
                r = dict(zip(cols, parts))
                if r.get("op") not in ("shrincs_sign", "shrincs_selftest"):
                    continue
                try:
                    r["run"] = int(r["run"])
                except ValueError:
                    continue
                yield path, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpp-repo", required=True)
    ap.add_argument("--results", default=os.path.join(ROOT, "results"))
    ap.add_argument("--saved", nargs="*",
                    default=[os.path.join(ROOT, "results", "raw", "host", "r1", d)
                             for d in ("host-sigs", "host-sigs-L")])
    a = ap.parse_args()

    print("shrincs-cpp:", git_rev(a.cpp_repo))
    exe = build(a.cpp_repo)
    failures = 0
    checked = dict()  # (op, variant, swn, run) -> set of sha256 of files that passed
    tally = dict()
    key_report = dict()

    files = []
    for d in a.saved:
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames.sort()
            for name in sorted(filenames):
                files.append(os.path.join(dirpath, name))

    for path in files:
        name = os.path.basename(path)
        m_self = re.fullmatch(r"shrincs_selftest_run(\d+)\.bin", name)
        m_sign = re.fullmatch(r"shrincs_sign_swn(\d+)_run(\d+)\.bin", name)
        if not (m_self or m_sign):
            continue
        size = os.path.getsize(path)
        v = SIZE_VARIANT.get(size)
        if v is None:
            print("skip %s: unexpected size %d" % (os.path.relpath(path, ROOT), size))
            continue
        if m_self:
            x = int(m_self.group(1))
            cmd = [exe[v], "selftest", path, str(x)]
            key = ("shrincs_selftest", v, "", x)
            label = "selftest-" + v
        else:
            swn, x = m_sign.group(1), int(m_sign.group(2))
            if v == "L" and swn != "140":
                tally.setdefault("sign-L swn=%s (skipped)" % swn, [0, 0])[0] += 1
                continue
            cmd = [exe[v], "fixedkey", SK_HEX, path, str(x)]
            key = ("shrincs_sign", v, swn, x)
            label = "fixedkey-%s swn=%s" % (v, swn)
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = parse(p.stdout.strip()) if p.stdout.strip() else dict()
        ok = p.returncode == 0 and out.get("result") == "PASS"
        t = tally.setdefault(label, [0, 0])
        t[0] += 1
        if not ok:
            t[1] += 1
            failures += 1
            print("FAIL %s: %s %s" % (os.path.relpath(path, ROOT), p.stdout.strip(),
                                       p.stderr.strip()))
            continue
        if m_sign:
            rep = key_report.setdefault(v, dict(full_verify_passed=0, files=0))
            rep.update((k, out[k]) for k in out if k.startswith("key_"))
            rep["files"] += 1
            rep["full_verify_passed"] += out["full_verify_stored_key"] == "1"
        with open(path, "rb") as f:
            checked.setdefault(key, set()).add(hashlib.sha256(f.read()).hexdigest())

    print("\nshrincs-cpp checks of saved files (files, failures):")
    for label, (n, bad) in sorted(tally.items()):
        print("%s %-24s files=%4d failures=%d"
              % ("ok  " if not bad else "FAIL", label, n, bad))
    for k, s in sorted(checked.items()):
        if len(s) != 1:
            print("note: %s has %d distinct checked files" % (str(k), len(s)))
    for v, rep in sorted(key_report.items()):
        print("fixed key under SHRINCS-%s: %s" % (v, " ".join(
            "%s=%s" % (k, rep[k]) for k in sorted(rep))))

    # Tie the checked files to the result rows.
    cov = dict()
    for path, r in result_rows(a.results):
        v = variant_of(r["build"])
        swn = r["swn"] if r["op"] == "shrincs_sign" else ""
        k = (r["op"], v, swn, r["run"])
        if k not in checked:
            continue
        two_core = "dual" in r["build"].lower()
        g = cov.setdefault((r["op"], v, swn, "two cores" if two_core else "one core"),
                           [0, 0, set()])
        if r["out_sha256"] in checked[k]:
            g[0] += 1
        else:
            g[1] += 1
            if not two_core:
                failures += 1
                print("FAIL one-core row differs from the checked file: %s run %d"
                      % (os.path.relpath(path, ROOT), r["run"]))
        g[2].add(r["run"])
    print("\nResult rows whose (op, variant, swn, run) has a checked file:")
    for (op, v, swn, cores), (same, diff, runs) in sorted(cov.items()):
        print("  %-16s %s swn=%-4s %-9s rows identical=%4d differing=%3d runs=%d"
              % (op, v, swn or "-", cores, same, diff, len(runs)))

    print("\n%s: %d failure(s)" % ("PASS" if not failures else "FAIL", failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
