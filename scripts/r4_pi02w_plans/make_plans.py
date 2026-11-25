#!/usr/bin/env python3
"""
Round 4: writes the Pi Zero 2 W run plans for scripts/r4_pi02w_queue.sh and estimates
their device time.

  make_plans.py [--l3 BUILD] [--dual thread|pool] [--l2 shared|static] [--speed L1,L2,L3]
                [--dual-speedup X]

Writes, in this directory:
  screen.plan   the level-3 screen (run at 600 MHz; screen1g.plan is the same with the
                label r4-screen1g, run at 1 GHz): OpenSSL's run-time SHA-256 path (armcap probe),
                compress_bench of the candidates, and short signing and key-generation
                runs of each candidate build, plus a two-core sanity check
  pi02w.plan    the measurement plan, in the brief's priority order:
                (a) level 3, one core: signing, key generation, and verification for every
                    hash-based scheme, the lattice operations, and the self-tests
                (b) levels 1 and 2, one core: the same (lattice operations at level 1 only,
                    as on the Pi Zero W)
                (c) two cores (DUAL_CORE=1 builds) at levels 3, 1, and 2: the operations
                    with a two-core code path in Jade (SLH-DSA and SPHINCS+ signing and key
                    generation, SHRINCS signing, key generation, and self-tests)
                (d) peak memory (MEM=1 builds), levels 3, 1, and 2, with the run counts of
                    the Pi Zero W's memory pass
                (e) SHRINCS stateless signing, n=10: level 3 one core, level 3 two cores,
                    then levels 2 and 1 on one core, then on two cores
Run counts and operations mirror scripts/r2_plans/pi0w.plan (round 2, Pi Zero W).

--l3 names the level-3 build kind (default asmrevbe-apinative-opto3-lto). The estimate
scales each line's measured job duration on the Pi Zero W (round 2 queue log, start to
done, so untimed work is included) by the Pi Zero 2 W's time ratio per level (--speed,
Pi Zero 2 W time divided by Pi Zero W time; defaults are guesses until the screen
measures them) and, for two-core lines, divides by --dual-speedup.
"""
import argparse
import collections
import datetime
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

LEVELS = dict((
    ("1", ("soft-apidirect", "plain-c direct; gcc13.3 -O2")),
    ("2", ("openssl", "openssl3.4.1; gcc13.3 -O2")),
))
L3_LABEL = dict((
    ("asmrevbe-apinative-opto3-lto", "asmrevbe native; gcc13.3 -O3 -flto PIE"),
    ("asmneonbe-apinative-opto3-lto", "asmneonbe native; gcc13.3 -O3 -flto PIE"),
    ("asmneon-apinative-opto3-lto", "asmneon native; gcc13.3 -O3 -flto PIE"),
))
SWN = dict((("B", "2040"), ("L", "140")))
VERIFY = dict((("B", ["slh_dsa_verify", "sphincs40_verify", "xmss_verify", "shrincs_verify",
                      "shrincs_verify_stateless"]),
               ("L", ["shrincs_verify", "shrincs_verify_stateless"])))
LATTICE = []
for ps in ("44", "65", "87"):
    for var in ("", "_lowram"):
        for k in ("keygen", "sign", "verify"):
            LATTICE.append(f"mldsa{ps}{var}_{k}")
for nn in ("512", "1024"):
    for k in ("keygen", "sign", "verify"):
        LATTICE.append(f"fndsa{nn}_{k}")
# Round-1 operations, as in scripts/r2_plans/make_plans.py, signing first
SIGN = dict((
    ("B", [("slh_dsa_sign", 100, ""), ("sphincs40_sign", 100, ""),
           ("shrincs_sign", 100, "2040"), ("xmss_sign", 100, "")]),
    ("L", [("shrincs_sign", 100, "140"), ("shrincs_sign", 100, "96")]),
))
KEYGEN = dict((
    ("B", [("slh_dsa_keygen", 100, ""), ("sphincs40_keygen", 100, ""),
           ("shrincs_keygen", 100, ""), ("xmss_keygen", 100, "")]),
    ("L", [("shrincs_keygen", 100, "")]),
))
SELFTEST = dict((
    ("B", [("shrincs_selftest", 3, "2040"), ("xmss_selftest", 3, "")]),
    ("L", [("shrincs_selftest", 3, "140")]),
))
# Operations with a two-core code path in Jade (slh_dsa.c, shrincs/wots_c.c)
DUAL_OPS = set(("slh_dsa_sign", "sphincs40_sign", "slh_dsa_keygen", "sphincs40_keygen",
                "shrincs_sign", "shrincs_keygen", "shrincs_selftest",
                "shrincs_sign_stateless"))
SWN_OPS = set(("shrincs_verify", "shrincs_verify_stateless", "shrincs_sign",
               "shrincs_sign_stateless", "shrincs_selftest"))


DUAL = dict((("thread", ("-dc1", " dual-core")), ("pool", ("-dc1pool", " dual-core pool"))))
DUAL_FORM = ["thread"]
L2_FORMS = dict((
    ("shared", ("openssl", "openssl3.4.1; gcc13.3 -O2")),
    ("static", ("openssl-optstatic", "openssl3.4.1 static; gcc13.3 -O2")),
))


def build(lvl, v, l3, dual=False, mem=False):
    kind, lab = (l3, L3_LABEL[l3]) if lvl == "3" else LEVELS[lvl]
    dsuf, dlab = DUAL[DUAL_FORM[0]] if dual else ("", "")
    suffix = dsuf + ("-mem" if mem else "")
    word = f"r4-L{lvl}{'-mem' if mem else ''}"
    label = f"{word} shrincs-{v} {lab}{dlab}"
    return f"r4-pi02w-shrincs{v}-{kind}{suffix}", label


def line(lvl, v, op, n, swn, l3, dual=False, mem=False):
    b, lab = build(lvl, v, l3, dual, mem)
    if not swn and op in SWN_OPS:
        swn = SWN[v]
    return f"{b}|{lab}|{op}|{n}" + (f"|{swn}" if swn else "")


def one_core_set(lvl, l3, lattice):
    out = []
    for v in ("B", "L"):
        for op, n, swn in SIGN[v]:
            out.append(line(lvl, v, op, n, swn, l3))
    for v in ("B", "L"):
        for op, n, swn in KEYGEN[v]:
            out.append(line(lvl, v, op, n, swn, l3))
    for v in ("B", "L"):
        for op in VERIFY[v]:
            out.append(line(lvl, v, op, 100, "", l3))
    if lattice:
        for op in LATTICE:
            out.append(line(lvl, "B", op, 100, "", l3))
    for v in ("B", "L"):
        for op, n, swn in SELFTEST[v]:
            out.append(line(lvl, v, op, n, swn, l3))
    return out


def main_plan(l3):
    out = ["# Round-4 run plan, Pi Zero 2 W (scripts/r4_pi02w_queue.sh). Generated by",
           f"# scripts/r4_pi02w_plans/make_plans.py --l3 {l3}; see its docstring for the "
           "priorities.", "#",
           "# (a) level 3, one core: signing, key generation, verification, lattice, "
           "self-tests"]
    out += one_core_set("3", l3, True)
    out.append("# (b) levels 1 and 2, one core (lattice operations at level 1 only)")
    out += one_core_set("1", l3, True)
    out += one_core_set("2", l3, False)
    out.append("# (c) two cores (DUAL_CORE=1), levels 3, 1, 2: operations with a two-core "
               "path in Jade")
    for lvl in ("3", "1", "2"):
        for group in (SIGN, KEYGEN, SELFTEST):
            for v in ("B", "L"):
                for op, n, swn in group[v]:
                    if op in DUAL_OPS:
                        out.append(line(lvl, v, op, n, swn, l3, dual=True))
    out.append("# (d) peak memory (MEM=1 builds, not for timing), levels 3, 1, 2")
    for lvl in ("3", "1", "2"):
        for v in ("B", "L"):
            for op in VERIFY[v]:
                out.append(line(lvl, v, op, 10, "", l3, mem=True))
            for group in (SELFTEST, SIGN, KEYGEN):
                for op, n, swn in group[v]:
                    nn = 1 if (op.endswith("selftest") or swn == "140") else 3
                    out.append(line(lvl, v, op, nn, swn, l3, mem=True))
            out.append(line(lvl, v, "shrincs_sign_stateless", 1, "", l3, mem=True))
        if lvl != "2":
            for op in LATTICE:
                out.append(line(lvl, "B", op, 10, "", l3, mem=True))
    out.append("# (e) SHRINCS stateless signing, n=10: level 3 one core, level 3 two cores, "
               "levels 2 and 1 one core, levels 2 and 1 two cores")
    for lvl, dual in (("3", False), ("3", True), ("2", False), ("1", False), ("2", True),
                      ("1", True)):
        for v in ("B", "L"):
            out.append(line(lvl, v, "shrincs_sign_stateless", 10, "", l3, dual=dual))
    return out


def screen_plan():
    out = ["# Round-4 level-3 screen, Pi Zero 2 W (scripts/r4_pi02w_queue.sh). Generated by",
           "# scripts/r4_pi02w_plans/make_plans.py. Candidates: integer code (asmrevbe),",
           "# NEON code with a big-endian copy for SLH-DSA (asmneonbe), NEON code with the C",
           "# wrapper for SLH-DSA (asmneon); -O3 with LTO, and -O2 / -O3 without LTO.",
           "r4-pi02w-armcap-probe|r4-screen armcap|probe|1"]
    cands = ["asmrevbe-apinative-opto3-lto", "asmneonbe-apinative-opto3-lto",
             "asmneon-apinative-opto3-lto", "asmrevbe-apinative", "asmneonbe-apinative",
             "asmrevbe-apinative-opto3"]
    for c in cands:
        out.append(f"r4-pi02w-shrincsB-{c}|r4-screen shrincs-B {c}|cbench|200000")
    out.append("r4-pi02w-shrincsB-asmrevbe-apinative-opto3-lto|r4-screen shrincs-B "
               "asmrevbe-apinative-opto3-lto|cbench-armcap0|200000")
    out.append("r4-pi02w-shrincsB-soft-apidirect|r4-screen shrincs-B soft-apidirect|cbench|200000")
    out.append("r4-pi02w-shrincsB-openssl|r4-screen shrincs-B openssl|cbench|200000")
    out.append("r4-pi02w-shrincsB-openssl-optstatic|r4-screen shrincs-B openssl-optstatic|"
               "cbench|200000")
    ops = [("slh_dsa_sign", 3, ""), ("sphincs40_sign", 3, ""), ("xmss_sign", 3, ""),
           ("shrincs_sign", 10, "2040"), ("slh_dsa_verify", 100, ""),
           ("shrincs_verify", 100, "2040")]
    for c in cands:
        for op, n, swn in ops:
            out.append(f"r4-pi02w-shrincsB-{c}|r4-screen shrincs-B {c}|{op}|{n}"
                       + (f"|{swn}" if swn else ""))
        if c in ("asmrevbe-apinative-opto3-lto", "asmneonbe-apinative-opto3-lto"):
            out.append(f"r4-pi02w-shrincsL-{c}|r4-screen shrincs-L {c}|shrincs_keygen|10")
    for lvl, kind in (("1", "soft-apidirect"), ("2", "openssl"), ("2", "openssl-optstatic")):
        for op, n, swn in ops:
            out.append(f"r4-pi02w-shrincsB-{kind}|r4-screen shrincs-B {kind}|{op}|{n}"
                       + (f"|{swn}" if swn else ""))
    out.append("# two cores (level-3 integer candidate): one thread per Jade task, and one")
    out.append("# persistent worker thread")
    for suf, lab in (("-dc1", " dual-core"), ("-dc1pool", " dual-core pool")):
        for op, n, swn in (("slh_dsa_sign", 3, ""), ("slh_dsa_keygen", 10, ""),
                           ("shrincs_sign", 10, "2040"), ("shrincs_keygen", 10, "")):
            out.append(f"r4-pi02w-shrincsB-asmrevbe-apinative-opto3-lto{suf}|r4-screen shrincs-B "
                       f"asmrevbe-apinative-opto3-lto{lab}|{op}|{n}" + (f"|{swn}" if swn else ""))
    return out


def r2_durations():
    """Measured Pi Zero W job durations (s) from the round-2 queue log, keyed by
    (level, variant, op, n, swn, mem)."""
    durs = dict()
    pat = re.compile(r"^(\S+ \S+) (start|done) (r2-armv6-shrincs(\w)-\S+?)\|r2-L(\d)(-mem)?"
                     r" [^|]*\|(\w+)\|(\d+)(?:\|(\d+))?")
    for path in sorted(glob.glob(os.path.join(ROOT, "results/raw/pi0w/r2/queue-*.log"))):
        start = dict()
        for ln in open(path):
            m = pat.match(ln)
            if not m:
                continue
            t = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            k = (m.group(5), m.group(4), m.group(7), int(m.group(8)), m.group(9) or "",
                 bool(m.group(6)))
            if m.group(2) == "start":
                start[k] = t
            elif k in start:
                durs[k] = (t - start.pop(k)).total_seconds()
    return durs


def estimate(plan, speed, dual_speedup):
    durs = r2_durations()
    per_prio = collections.OrderedDict()
    prio = "?"
    missing = []
    pat = re.compile(r"^r4-pi02w-shrincs(\w)-\S+?\|r4-L(\d)(-mem)? [^|]*\|(\w+)\|(\d+)(?:\|(\d+))?")
    for ln in plan:
        if ln.startswith("# ("):
            prio = ln[2:5]
            per_prio.setdefault(prio, 0.0)
            continue
        m = pat.match(ln)
        if not m:
            continue
        v, lvl, mem, op, n, swn = m.groups()
        k = (lvl, v, op, int(n), swn or "", bool(mem))
        dual = "dual-core" in ln
        if k not in durs:
            # same op at another n: scale by n
            alt = [kk for kk in durs if kk[:3] == k[:3] and kk[4:] == k[4:]]
            if not alt:
                missing.append(ln)
                continue
            d = durs[alt[0]] * int(n) / alt[0][3]
        else:
            d = durs[k]
        d = max(d, 1.0) * speed[lvl]
        if dual:
            d /= dual_speedup
        per_prio[prio] += d
    return per_prio, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--l3", default="asmrevbe-apinative-opto3-lto", choices=sorted(L3_LABEL))
    ap.add_argument("--speed", default="0.7,0.7,0.7",
                    help="Pi Zero 2 W / Pi Zero W time ratio at levels 1, 2, 3")
    ap.add_argument("--dual-speedup", type=float, default=1.3)
    ap.add_argument("--dual", default="thread", choices=sorted(DUAL),
                    help="two-core form: thread (DUAL_CORE=1) or pool (DUAL_CORE=pool)")
    ap.add_argument("--l2", default="shared", choices=sorted(L2_FORMS),
                    help="level-2 libcrypto: shared (the board's libcrypto.so.3) or static "
                         "(the SDK's libcrypto.a, for a board whose library differs)")
    args = ap.parse_args()
    DUAL_FORM[0] = args.dual
    LEVELS["2"] = L2_FORMS[args.l2]
    s1, s2, s3 = (float(x) for x in args.speed.split(","))
    speed = dict((("1", s1), ("2", s2), ("3", s3)))
    plan = main_plan(args.l3)
    open(os.path.join(HERE, "pi02w.plan"), "w").write("\n".join(plan) + "\n")
    open(os.path.join(HERE, "screen.plan"), "w").write("\n".join(screen_plan()) + "\n")
    # the same screen with its own label and done-list, for the run at 1 GHz (force_turbo=1)
    s1g = [ln.replace("|r4-screen ", "|r4-screen1g ") for ln in screen_plan()]
    s1g[0] = s1g[0].replace("Round-4 level-3 screen,", "Round-4 level-3 screen at 1 GHz,")
    open(os.path.join(HERE, "screen1g.plan"), "w").write("\n".join(s1g) + "\n")
    per_prio, missing = estimate(plan, speed, args.dual_speedup)
    jobs = sum(1 for ln in plan if ln and not ln.startswith("#"))
    print(f"pi02w.plan: {jobs} jobs; estimate with time ratio {args.speed} (L1,L2,L3) and "
          f"two-core speedup {args.dual_speedup}:")
    for p, d in per_prio.items():
        print(f"  {p}: {d / 3600:.2f} h")
    print(f"  total: {sum(per_prio.values()) / 3600:.2f} h")
    for ln in missing:
        print("  no Pi Zero W duration for:", ln)


if __name__ == "__main__":
    main()
