"""First-round figures for results/combined_draft.md. The main tables use the second
round (round2.py); the first round stays in the cost of
safeguards (Tables D17a and D17b: Pi Zero stack protector and linking; ESP32 compiler stack
protector), the Jade firmware calibration (Table D18), and the reproducibility comparison
(round2.py reads the first-round files itself). Run from the repository root (fill.py
loads it from there). Writes out/tables2.md under this script's directory; round2.py reads
cols, sd, swn140, value(), pubrows, and pubcell() from this module."""
import collections
import csv
import importlib.util
import math
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


summ = _load("summ", "scripts/summarize.py")
NF = _load("numfmt", os.path.join(HERE, "numfmt.py"))
Q = 1e-4  # print resolution of the first round's files (seconds)


def variant(path, row):
    if path.endswith(".csv"):
        return "l" if "shrincs-l" in row["build"].lower() else "b"
    return "l" if "-L-" in os.path.basename(path) else "b"


def load(paths, keep=lambda r: True):
    """(op, swn) -> (mean, n, sd) over the rows of the given files."""
    g = collections.defaultdict(list)
    for p in paths:
        for r in summ.read_rows(p):
            if not keep(r) or r["op"].endswith("selftest"):
                continue
            op = r["op"]
            if op.startswith("shrincs"):
                op = op.replace("shrincs", "shrincs_" + variant(p, r))
            g[(op, r["swn"] if op == "shrincs_l_sign" else "")].append(r["wall_s"])
    return dict((k, (statistics.mean(v), len(v), statistics.stdev(v) if len(v) > 1 else 0.0))
                for k, v in g.items())


def fit(path):
    script = "scripts/grind_fit_csv.py" if path.endswith(".csv") else "scripts/grind_fit_logs.py"
    out = subprocess.run([sys.executable, "-I", script, ".", path], capture_output=True,
                         text=True).stdout
    return float(re.findall(r"swn140=([0-9.]+)", out)[-1])


cols, swn140, paths_of, rows_of = {}, {}, {}, {}


def load_rows(paths, keep=lambda r: True):
    """(op, variant, swn) -> the rows behind load()'s figures, with each row's file, for
    results/summary.csv."""
    g = collections.defaultdict(list)
    for p in paths:
        for r in summ.read_rows(p):
            if not keep(r) or r["op"].endswith("selftest"):
                continue
            g[(r["op"], variant(p, r).upper(), r["swn"])].append(dict(r, path=p))
    return dict(g)


def add(name, paths, lpath, keep=lambda r: True):
    cols[name] = load(paths, keep)
    paths_of[name] = list(paths)
    rows_of[name] = load_rows(paths, keep)
    if lpath:
        swn140[name] = fit(lpath)


PI, PIO = "results/raw/pi0w/r1/", "results/raw/pi0w/r1/raw-opt/"
add("pi_L1", [PI + "results_plainc_20261119_134109.csv"],
    PI + "results_plainc_20261119_134109.csv")
add("pi_L2", [PI + "results_20261119_010831.csv"], PI + "results_20261119_010831.csv",
    lambda r: "plain-c" not in r["build"])
add("pi_L3", [PI + "results_l3pie_20261119_172249.csv"], PI + "results_l3pie_20261119_172249.csv")
add("pi_L3_ssp_static", [PI + "results_l3ssp_20261119_152137.csv"],
    PI + "results_l3ssp_20261119_152137.csv")
add("pi_L3_nossp_static", [PIO + "results_confirm_20261119_061006.csv"],
    PIO + "results_confirm_20261119_061006.csv")

for b, d in (("s3", "esp32s3"), ("p4", "esp32p4")):
    R, O = f"results/raw/{d}/r1/{b}", f"results/raw/{d}/r1/raw-opt/{b}"
    pairs = {
        "L1c1": (f"{R}-{{}}-soft-dc0-direct-r10.log"),
        "L1c2": (f"{O}-{{}}-soft-dc1-direct-r10.log"),
        "L2c1": (f"{R}-{{}}-hw-dc0-direct-r10.log"),
        "L2c2": (f"{R}-{{}}-hw-dc1-direct-r10.log"),
        "L3c1": (f"{O}-opt-{{}}-hwshadow-dc0-r10.log"),
        "L3c2": (f"{O}-opt-{{}}-hwshadow-dc1-r10.log"),
        "ssp_L3c1": (f"{O}-optssp-{{}}-hwshadow-dc0-r10.log"),
        "ssp_L3c2": (f"{O}-optssp-{{}}-hwshadow-dc1-r10.log"),
    }
    for k, pat in pairs.items():
        add(f"{b}_{k}", [pat.format("B"), pat.format("L")], pat.format("L"))

jade = collections.defaultdict(list)
for r in csv.DictReader(open("results/jade_runs.csv")):
    if r["seconds"]:
        jade[(r["op"].replace("shrincs", "shrincs_b"), "")].append(float(r["seconds"]))
cols["s3_jade"] = dict((k, (statistics.mean(v), len(v), statistics.stdev(v)))
                       for k, v in jade.items())
paths_of["s3_jade"] = ["results/jade_runs.csv"]

pubrows = {}
for line in open("results/published/blockstream_2026-08-19.csv"):
    if line.startswith("#") or line.startswith("op,"):
        continue
    f = line.strip().split(",")
    pubrows[(f[0], f[1])] = f[3:7]
# Blockstream labels its Trezor signing column "Trezor Safe 3/5/7" and its key generation
# column "Trezor Safe 3"; one column here holds both, footnoted.
PUB_COLS = ["Jade Plus", "Trezor Safe 3/5/7{{fn:trezor-label}}", "Ledger Nano gen5/S+",
            "BitBox02 Nova"]

ROWS = [
    ("SLH-DSA-SHA2-128s sign", ("slh_dsa_sign", "")),
    ("SPHINCS+ 2^40 sign", ("sphincs40_sign", "")),
    ("SHRINCS-B sign", ("shrincs_b_sign", "")),
    ("SHRINCS-L sign, swn=96", ("shrincs_l_sign", "96")),
    ("SHRINCS-L sign, swn=140 (expected)", "swn140"),
    ("XMSS 2^10 sign", ("xmss_sign", "")),
    ("SLH-DSA-SHA2-128s keygen", ("slh_dsa_keygen", "")),
    ("SPHINCS+ 2^40 keygen", ("sphincs40_keygen", "")),
    ("SHRINCS-L keygen", ("shrincs_l_keygen", "")),
    ("SHRINCS-B keygen", ("shrincs_b_keygen", "")),
    ("XMSS 2^10 keygen", ("xmss_keygen", "")),
]
# swn=96 is not the scheme's specified target sum; it appears only in the comparison with
# Blockstream's table (Table H4), so the first-round tables leave it out.
MAIN_ROWS = [r for r in ROWS if r[1] != ("shrincs_l_sign", "96")]
SIGN_ROWS = [r for r in MAIN_ROWS if r[0].endswith(("sign", "(expected)"))]
PUBKEY = {"slh_dsa_sign": ("slh_dsa_sign", ""), "sphincs40_sign": ("sphincs40_sign", ""),
          "shrincs_b_sign": ("shrincs_b_sign", "2040"), "xmss_sign": ("xmss_sign", ""),
          "slh_dsa_keygen": ("slh_dsa_keygen", ""),
          "sphincs40_keygen": ("sphincs40_keygen", ""),
          "shrincs_l_keygen": ("shrincs_l_keygen", ""),
          "shrincs_b_keygen": ("shrincs_b_keygen", ""), "xmss_keygen": ("xmss_keygen", "")}


def value(col, key):
    if key == "swn140":
        return swn140.get(col)
    v = cols[col].get(key)
    return v[0] if v else None


def sd(col, key):
    """Standard error of the mean (seconds); None for fits and missing cells."""
    if key == "swn140":
        return None
    v = cols[col].get(key)
    return v[2] / math.sqrt(v[1]) if v and v[1] > 1 else None


def fmt(col, key):
    x = value(col, key)
    if x is None:
        return "not run"
    return NF.num(x, sd(col, key), Q)


def cal_value(op):
    """Table D18's figure for Jade's firmware on our ESP32-S3 board, as displayed."""
    return fmt("s3_jade", (op, ""))


def pubcell(key):
    if key == "swn140":
        return pubrows[("shrincs_l_sign", "140")]
    op, swn = key
    if op == "shrincs_l_sign":
        return pubrows[("shrincs_l_sign", swn)]
    pk = PUBKEY.get(op)
    return pubrows.get(pk) if pk else None


def pct(a, t, nd=1):
    return "not run" if a is None or t is None else f"{100 * (t / a - 1):+.{nd}f}%"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def cost_pi():
    """Table D17a: the Pi Zero level-3 builds, times and percent changes."""
    a, b, c = "pi_L3_nossp_static", "pi_L3_ssp_static", "pi_L3"
    rows = []
    for label, key in MAIN_ROWS:
        rows.append([label, fmt(a, key), fmt(b, key), fmt(c, key),
                     pct(value(a, key), value(b, key)), pct(value(b, key), value(c, key))])
    return table(["Operation", "Static, no stack protector (s)", "Static, stack protector (s)",
                  "PIE, stack protector, SDK defaults (s)",
                  "Stack protector, static builds", "PIE and dynamic linking"], rows)


def cost_ssp():
    """Table D17b: ESP32 compiler stack protector at level 3, percent change."""
    head = ["Operation", "ESP32-P4, one core", "ESP32-P4, two cores",
            "ESP32-S3, one core",
            "ESP32-S3, two cores"]
    pairs = [(f"{b}_L3c{c}", f"{b}_ssp_L3c{c}") for b in ("p4", "s3") for c in (1, 2)]
    rows = []
    worst = None
    for label, key in SIGN_ROWS:
        cells = []
        for (base, test), h in zip(pairs, head[1:]):
            x, t = value(base, key), value(test, key)
            cells.append(pct(x, t))
            if x is not None and t is not None and (worst is None or t / x < worst[0]):
                worst = (t / x, label, key, base, test, h)
        rows.append([label] + cells)
    return table(head, rows), worst


def per_run_change(base, test, key):
    """Per-run percent change of test against base for one (op, swn) key, matched by run
    (first-round ESP32 logs; the same messages in both)."""
    op, swn = ("shrincs_l_sign", "140") if key == "swn140" else key

    def runs(col):
        out = {}
        for p in paths_of[col]:
            for r in summ.read_rows(p):
                o = r["op"]
                if o.startswith("shrincs"):
                    o = o.replace("shrincs", "shrincs_" + variant(p, r))
                if o == op and (op != "shrincs_l_sign" or r["swn"] == swn):
                    out[r["run"]] = r["wall_s"]
        return out

    a, t = runs(base), runs(test)
    ch = [100 * (t[k] / a[k] - 1) for k in sorted(set(a) & set(t))]
    return min(ch), max(ch), len(ch)


def cost_ssp_note(worst):
    if worst is None or worst[0] >= 1:
        return ""
    lo, hi, n = per_run_change(worst[3], worst[4], worst[2])
    label = worst[1].replace(" (expected)", "")
    head = f"The most negative value in Table D17b, {pct(1, worst[0])} ({label}, {worst[5]})"
    if hi < 0:
        return (f"{head}, holds run by run: on each of the {n} messages the stack-protected "
                f"build took {abs(hi):.1f} to {abs(lo):.1f}% less time. The cause was not "
                f"investigated.")
    return (f"{head}: per message, the stack-protected build's time changed by {lo:+.1f} to "
            f"{hi:+.1f}% over {n} messages. The cause was not investigated.")


def calibration():
    """Table D18: Blockstream's Jade firmware on the Waveshare ESP32-S3 Touch LCD 2,
    timed on the host as Blockstream timed it, against Blockstream's published Jade Plus
    figures."""
    rows = []
    for label, key in MAIN_ROWS:
        if key == "swn140" or value("s3_jade", key) is None:
            continue
        pub = pubcell(key)
        x = value("s3_jade", key)
        rows.append([label, fmt("s3_jade", key), str(cols["s3_jade"][key][1]), pub[0],
                     NF.ratio(x / float(pub[0]))])
    return table(["Operation", "Jade firmware, our ESP32-S3 board (s)", "n",
                  "Jade Plus, Blockstream's published figure (s)",
                  "Ours divided by published"], rows)


T = collections.OrderedDict()
T["COST_PI"] = cost_pi()
T["COST_SSP"], _worst = cost_ssp()
T["COST_SSP_NOTE"] = cost_ssp_note(_worst)
T["CAL_JADE"] = calibration()

os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
with open(os.path.join(HERE, "out", "tables2.md"), "w") as f:
    for k, v in T.items():
        f.write(f"## {k}\n\n{v}\n\n")
for k in sorted(swn140):
    print(f"{k:22s} swn140={swn140[k]:.2f}")
