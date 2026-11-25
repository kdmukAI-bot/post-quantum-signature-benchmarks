"""Tables and generated text for results/combined_draft.md, in the report's layers
(broad findings, detailed results, footnotes), built from the raw result files only, under results/raw/<device>/<round>/: rounds 2 and 3 on the Pi Zero (device
pi0w) and the ESP32 boards, round 4 on the Pi Zero 2 W and the RP2350, and the first
round's files (r1/ and r1/raw-opt/) for the reproducibility comparison. fill.py calls
build() with the levels2 module (first-round figures and Blockstream's published figures).

Rules this file implements (the draft's captions and footnotes give the reasons):
- Hash-based key generation and signing come from the second round, as does SHRINCS
  stateless signing.
- Verification and lattice figures come from round 3 when a complete round-3 file exists
  for the key; otherwise from round 2 with the cell marked R2_MARK, or "pending" when
  round 2 has no file for the key either. PEND counts them. Round
  3 runs one-core builds only, so ESP32 two-core figures stay with round 2, unmarked.
- Pi Zero: per (round, level, memory build, SHRINCS variant, op, swn) the newest file
  wins, so the repeat of priority (a) replaces its first pass; a round-3 file counts only
  when it holds at least the n rows its name gives.
- ESP32 boards: per (round, board, level, variant, cores, job set, n) the newest log that
  contains '#done' wins; a log still being written counts as missing.
- Pi Zero 2 W: one round (round 4, 1 GHz) for every operation, one file per (level,
  memory build, SHRINCS variant, cores, op, swn), newest wins, counted only when it holds
  the n rows its name gives. Level-2 memory comes from the shared-libcrypto rerun
  (scripts/r4_pi02w_plans/pi02w-l2mem.plan); the aborted static builds left .failed files,
  which the *.csv glob skips. A cell its run plans cover but no file fills is recorded in
  MISSING_R4, and fill.py stops on it. No round-3 mark applies to the board.
- RP2350: one round (round 4) in the ESP32 log format, per (level, variant, cores, job
  set) the newest log that contains '#done'; a job set its run plans list but no complete
  log fills is recorded in MISSING_RP, and fill.py stops on it. The level-3 lattice
  variation with c-fn-dsa's Cortex-M4 assembly (build r4-L3cm4) stays out of the tables;
  only its footnote reads it. No round-3 mark applies to the board.
- Lattice figures are over inputs 0 to 99: round 3 on every board; until then the Pi
  Zero W runs (n=100), the ESP32 level-3 n=100 runs, and at ESP32 level 1 the n=10 runs
  (inputs 0 to 9), except FN-DSA key generation, which reads "pending" there.
- Peak stack and heap come from the second round's runs: round 3 changes only how times
  are printed.
- Expected values come from scripts/grind_fit_r2.py: SHRINCS-L stateful signing at
  swn=140 (Pi Zero and Pi Zero 2 W: the swn=140 job; ESP32: swn 96 and 140 pooled per
  log, as in the round-2 summaries), ML-DSA signing, and SHRINCS stateless signing.
- Number format: numfmt.py. Each cell is kept in CELLS; K1 and the findings quote cells
  by key and record each quote in REFS, which fill.py checks against the final text.
- Every file read is recorded per table and listed under "Data and reproduction".
- Signature sizes come from the out_bytes column of the rows used, cross-checked against
  the scheme code's constants where they are plain macros (SHRINCS, ML-DSA, FN-DSA).
"""
import collections
import csv
import glob
import importlib.util
import math
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.join(ROOT, "results")
# Per-device environment descriptions (published; the run logs under results/raw/ are
# local only).
ENV_DIR = os.path.join(ROOT, "docs", "environments")
PENDING = "pending"
NA = "n/a"
R2_MARK = "†"
RES_Q = dict(((1, 1e-4), (2, 1e-4), (3, 1e-6), (4, 1e-6)))  # print resolution (seconds)
RAW = os.path.join(RES, "raw")


def raw_dir(device, rnd):
    """results/raw/<device>/<round>/."""
    return os.path.join(RAW, device, rnd)


HOST = raw_dir("host", "r2")
R4_DIR = raw_dir("pi02w", "r4")
R4_PLANS = [os.path.join(ROOT, "scripts", "r4_pi02w_plans", p)
            for p in ("pi02w.plan", "pi02w-l2mem.plan")]
RP_DIR = raw_dir("rp2350", "r4")
RP_PLANS = [os.path.join(ROOT, "scripts", "r4_plans", p)
            for p in ("rp2350.plan", "rp2350-stateless.plan")]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIT = load("grind_fit_r2", os.path.join(ROOT, "scripts", "grind_fit_r2.py"))
SUMM = load("summarize", os.path.join(ROOT, "scripts", "summarize.py"))
NF = load("numfmt", os.path.join(HERE, "numfmt.py"))

# The one setting for board order: fastest first (K1 holds this order on every row).
# Every table column, row group, per-board table (D1 to D5), and generated list follows
# it. The RP2350's hash-based operations take 1.10 to 1.49 times the
# ESP32-S3's time, so it is last.
BOARDS = ("pi2", "pi", "p4", "s3", "rp")
PI_BOARDS = tuple(b for b in BOARDS if b in ("pi", "pi2"))
ESP_BOARDS = tuple(b for b in BOARDS if b in ("p4", "s3"))
MCU_BOARDS = tuple(b for b in BOARDS if b in ("p4", "s3", "rp"))  # the microcontrollers
DUAL_BOARDS = tuple(b for b in BOARDS if b != "pi")  # boards with two-core builds
# The RP2350's round 4 is in (2026-11-24). With the switch off, its cells read "pending"
# (fill.py counts them), as while its run was in progress.
RP2350_DATA = True
NUM_WORD = dict(((2, "two"), (3, "three"), (4, "four"), (5, "five")))
# Boards are named by chip or product line ("Pi Zero" for the Pi Zero W measured, the
# ESP32 boards and the RP2350 by their chips); one footnote at the boards table ("boards"
# in the template) names the physical board behind each name. File names and identifiers
# keep pi0w.
BOARD_NAME = dict((("pi", "Pi Zero"), ("pi2", "Pi Zero 2 W"), ("p4", "ESP32-P4"),
                   ("s3", "ESP32-S3"), ("rp", "RP2350")))


def split_tab(a, b):
    """A table split by platform: the Pi boards in table a, the microcontrollers in b."""
    return dict((x, a if x in PI_BOARDS else b) for x in BOARDS)


# Tables split by platform to stay near ten columns with five boards.
VERIFY_TAB = split_tab("D8a", "D8b")
LAT_TAB = split_tab("D9a", "D9b")
RR_TAB = split_tab("D11a", "D11b")
MEM_TAB = split_tab("D13a", "D13b")
MAXMEM_TAB = split_tab("D14a", "D14b")
TWO_TAB = dict((b, "D15a" if b in PI_BOARDS else "D15b") for b in DUAL_BOARDS)


CORES = dict(((0, "one core"), (1, "two cores")))
SWN = dict((("B", "2040"), ("L", "140")))
LEVELS = (1, 2, 3)

HASH_SIGN = [
    ("slh_dsa_sign", "B", "", "SLH-DSA-SHA2-128s"),
    ("sphincs40_sign", "B", "", "SPHINCS+ 2^40"),
    ("shrincs_sign", "B", "2040", "SHRINCS-B, stateful"),
    ("shrincs_sign", "L", "140", "SHRINCS-L, stateful, swn=140 (expected)"),
    ("xmss_sign", "B", "", "XMSS 2^10"),
]
HASH_KEYGEN = [
    ("slh_dsa_keygen", "B", "", "SLH-DSA-SHA2-128s"),
    ("sphincs40_keygen", "B", "", "SPHINCS+ 2^40"),
    ("shrincs_keygen", "B", "", "SHRINCS-B"),
    ("shrincs_keygen", "L", "", "SHRINCS-L"),
    ("xmss_keygen", "B", "", "XMSS 2^10"),
]
HASH_GROUPS = (("Signing", HASH_SIGN), ("Key generation", HASH_KEYGEN))
VERIFY_OPS = [
    ("slh_dsa_verify", "B", "", "SLH-DSA-SHA2-128s"),
    ("sphincs40_verify", "B", "", "SPHINCS+ 2^40"),
    ("xmss_verify", "B", "", "XMSS 2^10"),
    ("shrincs_verify", "B", "2040", "SHRINCS-B, stateful"),
    ("shrincs_verify_stateless", "B", "2040", "SHRINCS-B, stateless"),
    ("shrincs_verify", "L", "140", "SHRINCS-L, stateful"),
    ("shrincs_verify_stateless", "L", "140", "SHRINCS-L, stateless"),
]
R1_OPS = [
    ("slh_dsa_sign", "B", "", "SLH-DSA-SHA2-128s sign"),
    ("sphincs40_sign", "B", "", "SPHINCS+ 2^40 sign"),
    ("shrincs_sign", "B", "2040", "SHRINCS-B sign"),
    ("shrincs_sign", "L", "96", "SHRINCS-L sign, swn=96"),
    ("shrincs_sign", "L", "140", "SHRINCS-L sign, swn=140"),
    ("xmss_sign", "B", "", "XMSS 2^10 sign"),
    ("slh_dsa_keygen", "B", "", "SLH-DSA-SHA2-128s keygen"),
    ("sphincs40_keygen", "B", "", "SPHINCS+ 2^40 keygen"),
    ("shrincs_keygen", "L", "", "SHRINCS-L keygen"),
    ("shrincs_keygen", "B", "", "SHRINCS-B keygen"),
    ("xmss_keygen", "B", "", "XMSS 2^10 keygen"),
    ("shrincs_selftest", "B", "", "SHRINCS-B self-test"),
    ("shrincs_selftest", "L", "", "SHRINCS-L self-test"),
    ("xmss_selftest", "B", "", "XMSS 2^10 self-test"),
]
LATTICE_SETS = [("mldsa44", "ML-DSA-44"), ("mldsa65", "ML-DSA-65"), ("mldsa87", "ML-DSA-87"),
                ("mldsa44_lowram", "ML-DSA-44, reduced RAM"),
                ("mldsa65_lowram", "ML-DSA-65, reduced RAM"),
                ("mldsa87_lowram", "ML-DSA-87, reduced RAM"),
                ("fndsa512", "FN-DSA-512"), ("fndsa1024", "FN-DSA-1024")]
# Key results order: each ML-DSA set followed by its reduced-RAM configuration.
K1_LATTICE = ["mldsa44", "mldsa44_lowram", "mldsa65", "mldsa65_lowram", "mldsa87",
              "mldsa87_lowram", "fndsa512", "fndsa1024"]
LAT_LABEL = dict(LATTICE_SETS)

SRC = collections.OrderedDict()  # table id -> set of paths
CELLS = dict()  # (table id, row key, column label) -> cell
PEND = collections.OrderedDict()  # canonical key -> (table id, row key, column, flag)
REFS = []  # (where, quoted number with flag, table id, row key, column label)
SIZES = collections.defaultdict(set)  # (op, variant) -> out_bytes of the rows used
CSV_ROWS = collections.defaultdict(list)  # csv name -> rows (dicts)
_CUR = [None]
LAST = [""]  # the result file the last pi_get(), pi2_get(), or esp_rows() read
S = dict()  # init(): directories, file indices, run plans
MISSING_R4 = set()  # Pi Zero 2 W keys a run plan covers but no complete file fills
MISSING_RP = set()  # RP2350 job sets a run plan lists but no complete log fills


def use(path):
    SRC.setdefault(_CUR[0], set()).add(path)


# Every measurement a table reads, for results/summary.csv (summary.py): (kind, board,
# level, op, variant, swn, cores index, round, path, rows, fit or None). kind is "time",
# "fit" (an expected value), or "mem" (peak memory).
SUMMARY_LOG = []


def note_summary(kind, board, level, op, v, swn, dc, rnd, path, rs, fit=None):
    SUMMARY_LOG.append((kind, board, level, op, v, swn or "", dc, rnd, path, rs, fit))


# ---------------------------------------------------------------- loading

PI_RE = re.compile(r"^pi0w-r([23])-L([123])(-mem)?-shrincs([BL])-(.*?)(?:-n(\d+))?"
                   r"-(\d{8}_\d{6})\.csv$")
ESP_RE = re.compile(r"^(s3|p4)-r([23])-L([123])-([BL])-dc([01])-(\w+?)-n(\w+)"
                    r"-(\d{8}_\d{6})\.log$")
_ROWS = dict()


def file_rows(path):
    """Result rows of one file. FIT.rows() (scripts/grind_fit_r2.py) parses wall_s with
    float(), so the six decimals of round 3 read as well as the four of round 2."""
    if path not in _ROWS:
        _ROWS[path] = list(FIT.rows(path))
    return _ROWS[path]


def index_pi(rnd, top):
    """top: the Pi Zero's directory for the round (results/raw/pi0w/r<rnd>)."""
    idx = dict()
    for path in glob.glob(os.path.join(top, f"pi0w-r{rnd}-*.csv")):
        m = PI_RE.match(os.path.basename(path))
        if not m or int(m.group(1)) != rnd:
            continue
        rs = file_rows(path)
        if not rs:
            continue
        if rnd == 3 and m.group(6) and len(rs) < int(m.group(6)):
            continue  # still being written or cut short
        op, swn = rs[0]["op"], rs[0]["swn"]
        key = (rnd, int(m.group(2)), bool(m.group(3)), m.group(4), op,
               swn if op == "shrincs_sign" else "")
        if key not in idx or m.group(7) > idx[key][0]:
            idx[key] = (m.group(7), path)
    return dict((k, v[1]) for k, v in idx.items())


def index_esp(rnd, tops):
    """tops: the ESP32 boards' directories for the round."""
    idx = dict()
    running = []
    for path in [p for top in tops for p in glob.glob(os.path.join(top, f"*-r{rnd}-*.log"))]:
        m = ESP_RE.match(os.path.basename(path))
        if not m or int(m.group(2)) != rnd:
            continue
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        if not any(ln.strip("\r").startswith("#done") for ln in text.split("\n")):
            running.append(path)
            continue
        b, _, lvl, v, dc, s, n, stamp = m.groups()
        key = (rnd, b, int(lvl), v, int(dc), s, int(n) if n.isdigit() else n)
        if key not in idx or stamp > idx[key][0]:
            idx[key] = (stamp, path)
    return idx, running


def load_plan(board):
    """Planned round-2 ESP32 job sets, in run order: list of (board, level, variant,
    cores, set, n, priority)."""
    out = []
    prio = ""
    path = os.path.join(ROOT, "scripts", "r2_plans", f"esp32{board}-full.plan")
    for ln in open(path):
        ln = ln.strip()
        m = re.match(r"#\s*\((\w)\)", ln)
        if m:
            prio = m.group(1)
        elif ln.startswith("# optional"):
            prio = "n=100"
        if not ln or ln.startswith("#"):
            continue
        build, s, n = ln.split("|")
        m = re.match(r"build-(s3|p4)-r2-L([123])-([BL])-dc([01])$", build)
        out.append((m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), s, int(n), prio))
    return out


PI2_RE = re.compile(r"^pi02w-r4-L([123])(-mem)?-shrincs([BL])-.*?-n(\d+)-(\d{8}_\d{6})\.csv$")


def pi2_key(level, mem, v, dc, op, swn=""):
    """Index key of a Pi Zero 2 W job: swn counts only for stateful SHRINCS signing, as on
    the Pi Zero."""
    return (level, bool(mem), v, int(dc), op, swn if op == "shrincs_sign" else "")


def index_pi2(top):
    """Round-4 Pi Zero 2 W files in top (not its screen subdirectories): key -> path. The
    file names carry the board's date (it has no real-time clock), which orders the files
    of one run correctly."""
    idx = dict()
    for path in glob.glob(os.path.join(top, "pi02w-r4-*.csv")):
        m = PI2_RE.match(os.path.basename(path))
        if not m:
            continue
        rs = file_rows(path)
        if not rs or len(rs) < int(m.group(4)):
            continue  # cut short
        op, swn = rs[0]["op"], rs[0]["swn"]
        dc = 1 if FIT.is_dual(rs[0]["build"]) else 0
        key = pi2_key(int(m.group(1)), m.group(2), m.group(3), dc, op, swn)
        if key not in idx or m.group(5) > idx[key][0]:
            idx[key] = (m.group(5), path)
    return dict((k, v[1]) for k, v in idx.items())


def load_pi2_plans():
    """Keys of every job the round-4 plans list (the level-2 memory rerun plan replaces
    the main plan's static-libcrypto memory jobs; both give the same keys)."""
    keys = set()
    for path in R4_PLANS:
        for ln in open(path):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            f = ln.split("|")
            build, label, op = f[0], f[1], f[2]
            swn = f[4] if len(f) > 4 else ""
            m = re.match(r"r4-L([123])(-mem)?\b", label)
            v = re.match(r"r4-pi02w-shrincs([BL])-", build).group(1)
            dc = 1 if re.search(r"-dc1(pool)?$", build) else 0
            keys.add(pi2_key(int(m.group(1)), m.group(2), v, dc, op, swn))
    return keys


RP_RE = re.compile(r"^rp2350-r4-L([123])(cm4)?-([BL])-dc([01])-(\w+?)-n(\d+)"
                   r"-(\d{8}_\d{6})\.log$")


def index_rp(top):
    """Round-4 RP2350 logs in top: (level, variant, cores, job set) -> path of the newest
    log that contains '#done' (the level-3 lattice variation under "cm4"); also the logs
    still being written."""
    idx = dict()
    running = []
    for path in glob.glob(os.path.join(top, "rp2350-r4-*.log")):
        m = RP_RE.match(os.path.basename(path))
        if not m:
            continue
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        if not any(ln.strip("\r").startswith("#done") for ln in text.split("\n")):
            running.append(path)
            continue
        lvl, cm4, v, dc, s, n, stamp = m.groups()
        key = ("cm4" if cm4 else int(lvl), v, int(dc), s)
        if key not in idx or stamp > idx[key][0]:
            idx[key] = (stamp, path)
    return dict((k, x[1]) for k, x in idx.items()), running


def load_rp_plans():
    """(level, variant, cores, job set) of every line of the RP2350's round-4 plans, the
    level-3 lattice variation under "cm4"."""
    keys = set()
    for path in RP_PLANS:
        for ln in open(path):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            build, s, _ = ln.split("|")
            m = re.match(r"build-r4-L([123])(cm4)?-([BL])-dc([01])$", build)
            keys.add(("cm4" if m.group(2) else int(m.group(1)), m.group(3), int(m.group(4)), s))
    return keys


def rp_rows(level, v, dc, s, op, swn=None):
    """Rows of one op in the RP2350's job set, or None; a planned job set with no
    complete log goes to MISSING_RP."""
    key = (level, v, dc, s)
    path = S["rp"].get(key)
    if not path:
        if key in S["rp_planned"]:
            MISSING_RP.add(key)
        return None
    rs = [r for r in file_rows(path) if r["op"] == op and (swn is None or r["swn"] == swn)]
    if not rs:
        return None
    use(path)
    LAST[0] = path
    return rs


def rp_missing(level, v, dc, s):
    """Cell text for an RP2350 job set with no rows: pending if a plan lists it (fill.py
    then stops), n/a if none does (no level-2 lattice set, no two-core lattice set)."""
    return PENDING if (level, v, dc, s) in S["rp_planned"] else NA


ESP_DEVICES = ("esp32p4", "esp32s3")
DEVICE = dict((("pi2", "pi02w"), ("pi", "pi0w"), ("p4", "esp32p4"), ("s3", "esp32s3"),
               ("rp", "rp2350")))


def init(csv_dir=None):
    S["csv_dir"] = csv_dir or os.path.join(RES, "derived")
    S["pi"] = index_pi(2, raw_dir("pi0w", "r2"))
    S["pi"].update(index_pi(3, raw_dir("pi0w", "r3")))
    S["pi2"] = index_pi2(R4_DIR)
    S["pi2_planned"] = load_pi2_plans()
    S["rp"], S["rp_running"] = index_rp(RP_DIR)
    S["rp_planned"] = load_rp_plans()
    e2, run2 = index_esp(2, [raw_dir(d, "r2") for d in ESP_DEVICES])
    e3, run3 = index_esp(3, [raw_dir(d, "r3") for d in ESP_DEVICES])
    S["esp"] = dict(e2)
    S["esp"].update(e3)
    S["esp_running"] = run2 + run3
    S["plan"] = dict((b, load_plan(b)) for b in ("p4", "s3"))
    S["planned"] = set(k[:6] for b in S["plan"] for k in S["plan"][b])
    S["att"] = None
    S["work"] = FIT.load_tree_work()


def pi_get(rnd, level, op, v, swn="", mem=False):
    path = S["pi"].get((rnd, level, mem, v, op, swn if op == "shrincs_sign" else ""))
    if not path:
        return None
    use(path)
    LAST[0] = path
    return file_rows(path)


def pi2_get(level, op, v, swn="", mem=False, dc=0):
    """Rows of one Pi Zero 2 W job, or None; a planned job with no file goes to
    MISSING_R4."""
    key = pi2_key(level, mem, v, dc, op, swn)
    path = S["pi2"].get(key)
    if not path:
        if key in S["pi2_planned"]:
            MISSING_R4.add(key)
        return None
    use(path)
    LAST[0] = path
    return file_rows(path)


def pi2_missing(level, op, v, swn="", mem=False, dc=0):
    """Cell text for a Pi Zero 2 W job with no file: pending if a plan covers it (fill.py
    then stops), n/a if no plan does (no two-core path, no level-2 lattice build)."""
    return PENDING if pi2_key(level, mem, v, dc, op, swn) in S["pi2_planned"] else NA


def esp_path(rnd, board, level, v, dc, s, n=None, nmin=1):
    """Newest complete log of a job set; n None takes any run count of at least nmin (a
    log name with no number counts as the build's default of 10)."""
    best = None
    for k, (stamp, path) in S["esp"].items():
        if k[:6] != (rnd, board, level, v, dc, s):
            continue
        kn = k[6] if isinstance(k[6], int) else 10
        if (n is not None and kn != n) or kn < nmin:
            continue
        if best is None or stamp > best[0]:
            best = (stamp, path)
    return best[1] if best else None


def esp_rows(rnd, board, level, v, dc, s, op, swn=None, n=None, nmin=1):
    """Rows of one op in one complete ESP32 job set; None if there are none."""
    path = esp_path(rnd, board, level, v, dc, s, n, nmin)
    if not path:
        return None
    rs = [r for r in file_rows(path) if r["op"] == op and (swn is None or r["swn"] == swn)]
    if not rs:
        return None
    use(path)
    LAST[0] = path
    return rs


def is_lattice(op):
    return op.startswith(("mldsa", "fndsa"))


def is_verify(op):
    return "_verify" in op


def esp_set_for(op):
    if is_lattice(op):
        return "lattice"
    if is_verify(op):
        return "verify"
    if op == "shrincs_sign_stateless":
        return "stateless"
    return "r1"


def r3_eligible(board, level, op, dc):
    """Whether round 3 reruns this cell: verification and lattice ops on one core, lattice
    at levels 1 and 3 only. The Pi Zero 2 W and the RP2350 have round 4 only."""
    if dc or board in ("pi2", "rp"):
        return False
    if is_lattice(op):
        return level in (1, 3)
    return is_verify(op)


def timing_rows(board, level, op, v="B", swn=None, dc=0, need100=False):
    """(rows, round, path) for one op, round 3 first where r3_eligible(); (None, None,
    None) when no complete file has the rows. need100: 100 inputs required."""
    lat = is_lattice(op)
    if board == "pi2":
        rs = pi2_get(level, op, v, swn or "", False, dc)
        if rs and need100 and len(rs) < 100:
            rs = None
        return (rs, 4, LAST[0]) if rs else (None, None, None)
    if board == "rp":
        rs = None
        for vv in ((v, "L" if v == "B" else "B") if lat else (v,)):
            rs = rp_rows(level, vv, dc, esp_set_for(op), op, swn)
            if rs:
                break
        if rs and need100 and len(rs) < 100:
            rs = None
        return (rs, 4, LAST[0]) if rs else (None, None, None)
    if r3_eligible(board, level, op, dc):
        if board == "pi":
            rs = pi_get(3, level, op, v, swn or "")
        else:
            rs = None
            for vv in ((v, "L" if v == "B" else "B") if lat else (v,)):
                rs = esp_rows(3, board, level, vv, dc, esp_set_for(op), op, swn,
                              nmin=100 if lat else 1)
                if rs:
                    break
        if rs and (not lat or len(rs) >= 100):
            return rs, 3, LAST[0]
    if board == "pi":
        rs = pi_get(2, level, op, v, swn or "")
        if rs and need100 and len(rs) < 100:
            rs = None
        return (rs, 2, LAST[0]) if rs else (None, None, None)
    for n in ((100, 10) if lat else (10,)):
        if need100 and n < 100:
            continue
        rs = esp_rows(2, board, level, v, dc, esp_set_for(op), op, swn, n=n)
        if rs:
            return rs, 2, LAST[0]
    return None, None, None


def missing_text(board, level, op, v, dc, swn=""):
    if board == "pi2":
        return pi2_missing(level, op, v, swn or "", False, dc)
    if board == "rp":
        return rp_missing(level, v, dc, esp_set_for(op))
    if r3_eligible(board, level, op, dc):
        return PENDING
    if board != "pi" and (board, level, v, dc, esp_set_for(op), 10) in S["planned"]:
        return PENDING
    return NA


def attempts():
    if S["att"] is None:
        S["att"] = FIT.load_attempts(os.path.join(HOST, "mldsa-attempts.csv"))
    use(os.path.join(HOST, "mldsa-attempts.csv"))
    return S["att"]


# ---------------------------------------------------------------- cells and formatting

def sc(x, unit):
    return x * 1e3 if unit == "ms" else x


def put(tab, row, col, value=None, num=None, text=None, flag="", pkey=None, unit="", **kw):
    c = dict(value=value, num=num if num is not None else text,
             text=text if text is not None else num, flag=flag, unit=unit)
    c.update(kw)
    CELLS[(tab, row, col)] = c
    if pkey is not None and flag in (R2_MARK, PENDING):
        PEND.setdefault(pkey, (tab, row, col, flag))
    return c


def show(c):
    if c["value"] is None:
        return c["text"]
    return c["text"] + (R2_MARK if c["flag"] == R2_MARK else "")


def cell(tab, row, col):
    return CELLS[(tab, row, col)]


def derived(tab, row, col, a, b, unit=""):
    """Cell a / b from two cells (ratios); marked when either input is."""
    if a["value"] is None or b["value"] is None:
        t = PENDING if PENDING in (a["text"], b["text"]) else NA
        return put(tab, row, col, text=t, unit=unit)
    flag = R2_MARK if R2_MARK in (a["flag"], b["flag"]) else ""
    r = a["value"] / b["value"]
    return put(tab, row, col, value=r, num=NF.ratio(r), flag=flag, unit=unit)


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def group_row(name, ncols):
    return [f"**{name}**"] + [""] * ncols


def rkey(group, label):
    return f"{group}/{label}" if group else label


# ---------------------------------------------------------------- timing cells

def time_cell(tab, row, col, board, level, op, v="B", swn=None, dc=0, unit="ms",
              stat="mean"):
    """One timing cell. stat: mean, median, min, max (of wall time), expected_mldsa,
    per_attempt (ML-DSA), expected_l140 (SHRINCS-L stateful signing at swn=140)."""
    if not RP2350_DATA and board == "rp":
        return put(tab, row, col, text=PENDING, unit=unit)
    need100 = op.startswith("fndsa") and op.endswith("_keygen")
    rs, rnd, path = timing_rows(board, level, op, v, swn, dc, need100)
    elig = r3_eligible(board, level, op, dc)
    pkey = (board, level, op, v, dc, stat) if elig else None
    if not rs:
        t = missing_text(board, level, op, v, dc, swn)
        return put(tab, row, col, text=t, flag=PENDING if t == PENDING else "", pkey=pkey,
                   unit=unit)
    flag = R2_MARK if (elig and rnd == 2) else ""
    q = sc(RES_Q[rnd], unit)
    if op.endswith(("_sign", "_sign_stateless")):
        SIZES[(op, v)].update(int(r["out_bytes"]) for r in rs if r["out_bytes"])
    w = [r["wall_s"] for r in rs]
    extra = dict(rnd=rnd, src=path, n=len(rs))
    note_summary("time", board, level, op, v, swn, dc, rnd, path, rs)
    if stat == "mean":
        m = statistics.mean(w)
        u = statistics.stdev(w) / math.sqrt(len(w)) if len(w) > 1 else None
        num = NF.num(sc(m, unit), sc(u, unit) if u else None, q)
        return put(tab, row, col, value=m, num=num, flag=flag, pkey=pkey, unit=unit,
                   se=u, **extra)
    if stat in ("median", "min", "max"):
        x = dict((("median", statistics.median), ("min", min), ("max", max)))[stat](w)
        return put(tab, row, col, value=x, num=NF.num(sc(x, unit), None, q), flag=flag,
                   pkey=pkey, unit=unit, **extra)
    if stat in ("expected_mldsa", "per_attempt"):
        att, hm = attempts()
        ps = op[5:7]
        f = FIT.fit_mldsa(rs, ps, att, hm)
        xs = [(att[(ps, r["run"])],) for r in rs]
        coef, res, cov = FIT.lstsq(xs, w)
        se_k = math.sqrt(cov[1][1]) if cov else float("nan")
        record_mldsa(board, level, op, rs, rnd, path, f, se_k)
        note_summary("fit", board, level, op, v, swn, dc, rnd, path, rs,
                     dict(model="ml-dsa: time = fixed + k x attempts", expected=f["expected"],
                          se=f["se"], e=f["e"], resid=f["resid"]))
        if stat == "expected_mldsa":
            x, u = f["expected"], f["se"]
        else:
            x, u = coef[1], se_k
        num, text = NF.pm(sc(x, unit), sc(u, unit), q)
        return put(tab, row, col, value=x, num=num, text=text, flag=flag, pkey=pkey,
                   unit=unit, se=u, **extra)
    if stat == "expected_l140":
        f = FIT.fit_shrincs_l(rs, dc == 1)
        x, u = f["expected"][140], f["se"][140]
        w140 = [r["wall_s"] for r in rs if r["swn"] == "140"]
        S.setdefault("l140_span", dict())[(board, level, dc)] = (min(w140), max(w140))
        note_summary("fit", board, level, op, v, swn, dc, rnd, path, rs,
                     dict(model="shrincs-l stateful: time = fixed + k x wots attempts",
                          expected=x, se=u, e="swn=140", resid=f["resid"]))
        num, text = NF.pm(sc(x, unit), sc(u, unit), q)
        return put(tab, row, col, value=x, num=num, text=text, flag=flag, pkey=pkey,
                   unit=unit, se=u, **extra)
    raise ValueError(stat)


_MLDSA_SEEN = set()


def record_mldsa(board, level, op, rs, rnd, path, f, se_k):
    key = (board, level, op, path)
    if key in _MLDSA_SEEN:
        return
    _MLDSA_SEEN.add(key)
    CSV_ROWS["mldsa_fit"].append(collections.OrderedDict((
        ("board", BOARD_NAME[board]), ("level", level), ("operation", op), ("round", rnd),
        ("n", len(rs)), ("expected_ms", f"{f['expected'] * 1e3:.4f}"),
        ("expected_se_ms", f"{f['se'] * 1e3:.4f}"),
        ("per_attempt_ms", f"{f['per_attempt'] * 1e3:.4f}"),
        ("per_attempt_se_ms", f"{se_k * 1e3:.4f}"), ("fixed_ms", f"{f['fixed'] * 1e3:.4f}"),
        ("max_residual_ms", f"{f['resid'] * 1e3:.4f}"), ("e_attempts", f["e"]),
        ("mean_attempts_these_inputs", f"{f['mean_attempts']:.3f}"),
        ("mean_ms", f"{statistics.mean(r['wall_s'] for r in rs) * 1e3:.4f}"),
        ("expected_at_host_mean_ms", f"{f['expected_host'] * 1e3:.4f}"))))


def hash_cell(tab, row, col, board, level, op, v, swn, dc):
    """Hash-based key generation and signing, second round: means, and SHRINCS-L stateful
    signing at swn=140 as an expected value."""
    if op == "shrincs_sign" and v == "L":
        return time_cell(tab, row, col, board, level, op, v,
                         "140" if board in PI_BOARDS else None,
                         dc, "s", "expected_l140")
    return time_cell(tab, row, col, board, level, op, v, swn or None, dc, "s", "mean")


# ---------------------------------------------------------------- 4.1 hash-based

def hash_cols(board):
    if board == "pi":
        return [(lvl, 0, f"Level {lvl}") for lvl in LEVELS]
    return [(lvl, dc, f"Level {lvl}, {CORES[dc]}") for lvl in LEVELS for dc in (0, 1)]


def t_hash_board(tab, board):
    _CUR[0] = tab
    cols = hash_cols(board)
    rows = []
    for group, ops in HASH_GROUPS:
        rows.append(group_row(group + ("{{fn:sha512}}" if board in PI_BOARDS and
                                       group == "Key generation" else ""), len(cols)))
        for op, v, swn, lab in ops:
            cells = [show(hash_cell(tab, rkey(group, lab), cl, board, lvl, op, v, swn, dc))
                     for lvl, dc, cl in cols]
            rows.append([lab] + cells)
    return table(["Operation"] + [c[2] for c in cols], rows)


# Method text of the per-board hash-based tables; hash_tables() numbers and orders them by
# BOARDS and puts a title line (board, chip, clock, what, unit, configuration) above each.
# {ref:b} is replaced by board b's table label.
HASH_CAPTION = dict((
    ("pi", "Means of n=100 runs over inputs 0 to 99{{fn:grinding}}{{fn:layout}}. {span}"),
    ("pi2", "Means of n=100 runs over inputs 0 to 99{{fn:grinding}}. {span} XMSS 2^10 has no "
            "two-core path and was run in the one-core build only, so its two-core cells "
            "read n/a."),
    ("p4", "Means of n=10 runs over inputs 0 to 9. {span} XMSS 2^10 has no two-core path: "
           "its two-core cells time it on one core of the two-core build."),
    ("s3", "As Table {ref:p4}. {span}"),
    ("rp", "Means of n=10 runs over inputs 0 to 9{{fn:rp-replay}}{{fn:rp-l2-dc}}. {span} "
           "XMSS 2^10 has no two-core path: its two-core cells time it on one core of the "
           "two-core build."),
))


def l140_span(b):
    """Caption sentence: the SHRINCS-L stateful figure's ± covers the fit only; how long
    single messages took at swn=140 on this board (level 3, one core)."""
    lo, hi = S["l140_span"][(b, 3, 0)]
    return (f"The SHRINCS-L expected value's ± is the fit's standard error, not the spread "
            f"between messages: at level 3 on one core, single messages at swn=140 took "
            f"{NF.rsig(lo, 2, cap=False)} to {NF.rsig(hi, 2, cap=False)} s.")


def hash_tables(T):
    """Section 3.1's per-board tables in BOARDS order: method text, title line, table."""
    out = []
    for b in BOARDS:
        tab = HASH_TAB[b]
        cap = re.sub(r"\{ref:(\w+)\}", lambda m: HASH_TAB[m.group(1)], HASH_CAPTION[b])
        cap = cap.replace("{span}", l140_span(b))
        cfg = "by level, one core" if b == "pi" else "by level and cores"
        out.append(f"{cap}\n\n"
                   f"**Table {tab}. {S['boards'][b]['title']}: hash-based signing and key "
                   f"generation, mean seconds, {cfg}**\n\n{T[tab]}")
    return "\n\n".join(out)


def table_list(labels):
    """'D1, D3, D4, and D7' (or 'D1 and D7')."""
    labels = list(labels)
    if len(labels) < 3:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def hash_col_label(board, level, dc=0):
    return f"Level {level}" if board == "pi" else f"Level {level}, {CORES[dc]}"


# Per-board hash-based tables D1 to D4, numbered in board order.
HASH_TAB = dict((b, f"D{i}") for i, b in enumerate(BOARDS, 1))


def t_level_ratio_hash():
    """Table D6: level-1 time divided by level-3 time, one core, from D1 to D4."""
    tab = "D6"
    rows = []
    for group, ops in HASH_GROUPS:
        rows.append(group_row(group, len(BOARDS)))
        for op, v, swn, lab in ops:
            cells = []
            for b in BOARDS:
                t = HASH_TAB[b]
                a = cell(t, rkey(group, lab), hash_col_label(b, 1))
                c = cell(t, rkey(group, lab), hash_col_label(b, 3))
                cells.append(show(derived(tab, rkey(group, lab), BOARD_NAME[b], a, c)))
            rows.append([lab] + cells)
    return table(["Operation"] + [BOARD_NAME[b] for b in BOARDS], rows)


def stateless_fit(board, level, v, dc):
    swn = SWN[v]
    if board == "rp":
        if not RP2350_DATA:
            return PENDING
        rs = rp_rows(level, v, dc, "stateless", "shrincs_sign_stateless", swn)
        if not rs:
            return rp_missing(level, v, dc, "stateless")
        if len(rs) < (6 if dc else 5):
            return NA  # too few runs for the fit's terms (footnote stateless-n)
    elif board == "pi":
        if dc:
            return NA
        rs = pi_get(2, level, "shrincs_sign_stateless", v)
        if not rs:
            return PENDING
    elif board == "pi2":
        rs = pi2_get(level, "shrincs_sign_stateless", v, "", False, dc)
        if not rs:
            return pi2_missing(level, "shrincs_sign_stateless", v, "", False, dc)
    else:
        rs = esp_rows(2, board, level, v, dc, "stateless", "shrincs_sign_stateless", swn, n=10)
        if not rs:
            return missing_text(board, level, "shrincs_sign_stateless", v, dc)
    path = LAST[0]
    use(os.path.join(HOST, f"pors-work-{v}.csv"))
    SIZES[("shrincs_sign_stateless", v)].update(int(r["out_bytes"]) for r in rs)
    f = FIT.fit_stateless(rs, v, swn, dc == 1, S["work"])
    f["path"] = path
    f["rows"] = rs
    note_summary("fit", board, level, "shrincs_sign_stateless", v, swn, dc,
                 4 if board in ("pi2", "rp") else 2, path, rs,
                 dict(model="shrincs stateless: time = fixed + pors, wots, and tree-work terms",
                      expected=f["expected"], se=f["se"], e="pors-fp probability "
                      "(scripts/pors_fp_prob.py) and tree work (scripts/pors_work.c)",
                      resid=f["resid"]))
    return f


def wide_note(wide):
    """Caption text for the stateless fits whose standard error is far above the rest:
    two-core SHRINCS-B fits, named by board and level."""
    if not wide:
        return ""
    assert all(dc == 1 and v == "B" for _, dc, v, _, _, _ in wide), wide
    by_board = collections.OrderedDict()
    for b, _, _, lvl, _, _ in wide:
        by_board.setdefault(b, []).append(str(lvl))
    where = table_list(f"the {BOARD_NAME[b]} at level{'s' if len(l) > 1 else ''} "
                       f"{table_list(l)}" for b, l in by_board.items())
    return (f" The larger standard errors of two-core SHRINCS-B ({where}) come from the fit: "
            f"the few WOTS+C attempts at swn=2040 are split between the cores by counter "
            f"parity, and over these messages the two per-core counts vary too little to fix "
            f"their terms.")


def three_term_resid(rs, v):
    """Largest residual of the fit without the tree-work term (one core)."""
    g = [FIT.grind(r) for r in rs]
    xs = [(x["pors"] + 1, x["wots0"] + x["wots1"] + 2) for x in g]
    _, res, _ = FIT.lstsq(xs, [r["wall_s"] for r in rs])
    return res


def t_stateless():
    """Table D7: SHRINCS stateless signing, expected value per message, seconds.
    The fit coefficients go to results/derived/stateless_fit.csv."""
    tab = "D7"
    _CUR[0] = tab
    cols = [(v, lvl) for v in ("B", "L") for lvl in LEVELS]
    rows = []
    r3, r4 = [], []
    spread, rp_runs, wide = [], [], []
    for b, dc in [(b, dc) for b in BOARDS for dc in ((0,) if b == "pi" else (0, 1))]:
        lab = f"{BOARD_NAME[b]}, {CORES[dc]}"
        cells = []
        for v, lvl in cols:
            cl = f"SHRINCS-{v}, level {lvl}"
            f = stateless_fit(b, lvl, v, dc)
            if isinstance(f, str):
                cells.append(show(put(tab, lab, cl, text=f, unit="s")))
                continue
            num, text = NF.pm(f["expected"], f["se"], RES_Q[4 if b in ("pi2", "rp") else 2])
            cells.append(show(put(tab, lab, cl, value=f["expected"], num=num, text=text,
                                  unit="s", se=f["se"], n=f["n"], src=f["path"])))
            r4.append(f["resid"])
            if not dc:
                r3.append(three_term_resid(f["rows"], v))
            w = [r["wall_s"] for r in f["rows"]]
            spread.append((min(w) / f["expected"], max(w) / f["expected"]))
            if b == "rp":
                rp_runs.extend(w)
            if f["se"] > 0.5:
                wide.append((b, dc, v, lvl, f["se"], f["n"]))
            row = collections.OrderedDict((
                ("board", BOARD_NAME[b]), ("cores", dc + 1),
                ("scheme", f"SHRINCS-{v}"), ("level", lvl), ("n", f["n"]),
                ("sample_mean_s", f"{f['sample_mean']:.4f}"),
                ("expected_s", f"{f['expected']:.4f}"), ("expected_se_s", f"{f['se']:.5f}"),
                ("max_residual_s", f"{f['resid']:.4f}"), ("fixed_s", f"{f['fixed']:.4f}"),
                ("per_pors_attempt_us", f"{f['k_pors'] * 1e6:.4f}"),
                ("per_wots_attempt_us", f"{f['k_wots'] * 1e6:.4f}" if "k_wots" in f else ""),
                ("per_wots_attempt_core0_us", f"{f['core0'] * 1e6:.4f}" if "core0" in f else ""),
                ("per_wots_attempt_core1_us", f"{f['core1'] * 1e6:.4f}" if "core1" in f else ""),
                ("per_tree_hash_us", f"{f['k_tree'] * 1e6:.5f}"),
                ("e_pors", f"{f['e_pors']:.1f}"), ("e_wots", f"{f['e_wots']:.1f}"),
                ("e_tree", f"{f['e_tree']:.1f}")))
            CSV_ROWS["stateless_fit"].append(row)
        rows.append([lab] + cells)
    note = dict((("e_pors", f"{FIT.e_pors():,.0f}"), ("e_tree", f"{FIT.e_tree():,.0f}"),
                 ("e_wots_b", f"{FIT.e_wots('B', 2040):,.1f}"),
                 ("e_wots_l", f"{FIT.e_wots('L', 140):,.0f}"),
                 ("r3", f"{max(r3):.1f}" if r3 else "n/a"),
                 ("r4", f"{max(r4):.2f}" if r4 else "n/a"),
                 ("spread_lo", NF.rsig(min(a for a, _ in spread), 2, cap=False)),
                 ("spread_hi", NF.rsig(max(b for _, b in spread), 2, cap=False)),
                 ("rp_min", f"{min(rp_runs) / 60:.0f}"), ("rp_max", f"{max(rp_runs) / 60:.0f}"),
                 ("wide", wide_note(wide))))
    return table(["Board, cores"] + [f"SHRINCS-{v}, level {lvl}" for v, lvl in cols], rows), note


def t_blockstream(L2):
    """Table H4: level 3 against Blockstream's published figures, one core on every board
    (Jade's release signs on one core); swn=96 appears among the signing results only here
    and in the round comparisons."""
    tab = "H4"
    _CUR[0] = tab
    cols = [(b, 0) for b in BOARDS]
    head = ["Operation"] + [BOARD_NAME[b] for b, dc in cols] + L2.PUB_COLS
    ours = dict((
        (("slh_dsa_sign", ""), ("Signing", "SLH-DSA-SHA2-128s")),
        (("sphincs40_sign", ""), ("Signing", "SPHINCS+ 2^40")),
        (("shrincs_b_sign", ""), ("Signing", "SHRINCS-B, stateful")),
        ("swn140", ("Signing", "SHRINCS-L, stateful, swn=140 (expected)")),
        (("xmss_sign", ""), ("Signing", "XMSS 2^10")),
        (("slh_dsa_keygen", ""), ("Key generation", "SLH-DSA-SHA2-128s")),
        (("sphincs40_keygen", ""), ("Key generation", "SPHINCS+ 2^40")),
        (("shrincs_l_keygen", ""), ("Key generation", "SHRINCS-L")),
        (("shrincs_b_keygen", ""), ("Key generation", "SHRINCS-B")),
        (("xmss_keygen", ""), ("Key generation", "XMSS 2^10"))))
    rows = []
    for label, key in L2.ROWS:
        cells = []
        for b, dc in cols:
            cl = head[1 + len(cells)]
            if key == ("shrincs_l_sign", "96"):
                c = time_cell(tab, label, cl, b, 3, "shrincs_sign", "L", "96", dc, "s", "mean")
            else:
                g, lab = ours[key]
                src = cell(HASH_TAB[b], rkey(g, lab), hash_col_label(b, 3, dc))
                use(src["src"])
                c = put(tab, label, cl, **dict((k, v) for k, v in src.items()))
            cells.append(show(c))
        rows.append([label] + cells + L2.pubcell(key))
    return table(head, rows)


# ---------------------------------------------------------------- 4.2 verification

# Verification is split by platform (four boards at three levels would make 13 columns).


def verify_key(b, lab, lvl=3):
    return (VERIFY_TAB[b], lab, f"{BOARD_NAME[b]}, level {lvl}")


def t_verify(tab, boards):
    _CUR[0] = tab
    cols = [(b, lvl) for b in boards for lvl in LEVELS]
    rows = []
    for op, v, swn, lab in VERIFY_OPS:
        cells = [show(time_cell(tab, lab, f"{BOARD_NAME[b]}, level {lvl}", b, lvl, op, v,
                                swn or None, 0, "ms")) for b, lvl in cols]
        rows.append([lab] + cells)
    return table(["Operation"] + [f"{BOARD_NAME[b]}, level {lvl}" for b, lvl in cols], rows)


def verify_dc_note():
    """Largest difference between the one- and two-core ESP32 verification means of the
    second round, for operations of 3 ms or more."""
    _CUR[0] = "D8b"
    worst = None
    n = 0
    for b in ("p4", "s3"):
        for lvl in LEVELS:
            for op, v, swn, lab in VERIFY_OPS:
                a = esp_rows(2, b, lvl, v, 0, "verify", op, swn or None, n=10)
                c = esp_rows(2, b, lvl, v, 1, "verify", op, swn or None, n=10)
                if not a or not c:
                    continue
                ma = statistics.mean(r["wall_s"] for r in a)
                mc = statistics.mean(r["wall_s"] for r in c)
                if ma < 0.003:
                    continue
                n += 1
                d = abs(mc / ma - 1) * 100
                if worst is None or d > worst[0]:
                    worst = (d, b, lvl, lab)
    if not worst:
        return "The two-core ESP32 builds' verification runs are missing."
    return (f"The ESP32 two-core builds run the same verification code. In the second "
            f"round, over the {n} verification operations of 3 ms or more measured in both, "
            f"the two-core mean differs from the one-core mean by at most {worst[0]:.1f}% "
            f"({worst[3]}, {BOARD_NAME[worst[1]]}, level {worst[2]}). The third round "
            f"reran the one-core builds only, so Table D8b gives one core.")


# ---------------------------------------------------------------- 4.3 lattice

def lattice_rows_spec():
    """(op, row label, stat) per row of Table D9."""
    out = []
    for s, lab in LATTICE_SETS:
        out.append((f"{s}_keygen", f"{lab} keygen", "mean"))
        if s.startswith("mldsa"):
            out.append((f"{s}_sign", f"{lab} sign (expected)", "expected_mldsa"))
            out.append((f"{s}_sign", f"{lab} sign, per attempt", "per_attempt"))
        else:
            out.append((f"{s}_sign", f"{lab} sign", "mean"))
        out.append((f"{s}_verify", f"{lab} verify", "mean"))
    return out


def sign_row(s):
    return f"{LAT_LABEL[s]} sign" + (" (expected)" if s.startswith("mldsa") else "")


def t_lattice(tab, boards):
    _CUR[0] = tab
    cols = [(b, lvl) for b in boards for lvl in (1, 3)]
    rows = []
    for op, lab, stat in lattice_rows_spec():
        cells = [show(time_cell(tab, lab, f"{BOARD_NAME[b]}, level {lvl}", b, lvl, op, "B",
                                None, 0, "ms", stat)) for b, lvl in cols]
        rows.append([lab] + cells)
    return table(["Operation"] + [f"{BOARD_NAME[b]}, level {lvl}" for b, lvl in cols], rows)


def mldsa_note():
    """Footnote texts: ML-DSA attempt counts of the inputs against the expectations used,
    and the spread of FN-DSA signing over messages."""
    att, hm = attempts()
    e = FIT.MLDSA_E_LIB

    def three(xs, nd):
        return f"{xs[0]:.{nd}f}, {xs[1]:.{nd}f}, and {xs[2]:.{nd}f}"

    ps = ("44", "65", "87")
    m10 = three([statistics.mean(att[(p, x)] for x in range(10)) for p in ps], 2)
    m100 = three([statistics.mean(att[(p, x)] for x in range(100)) for p in ps], 2)
    ratios = []
    for r in CSV_ROWS["mldsa_fit"]:
        if r["level"] == 3 or r["level"] == 1:
            ratios.append(float(r["expected_at_host_mean_ms"]) / float(r["expected_ms"]) - 1)
    out = (f"Messages 0 to 99 need {m100} attempts on average "
           f"(ML-DSA-44, -65, and -87; messages 0 to 9: {m10}), against the expectations "
           f"used, {three([e[p] for p in ps], 3)}. With the benchmark key's own mean over "
           f"20,000 messages ({three([hm[p] for p in ps], 3)}) in place of those, every "
           f"expected value in Tables D9a and D9b would be ")
    if ratios:
        out += f"{-max(ratios) * 100:.1f} to {-min(ratios) * 100:.1f}% lower."
    else:
        out += "lower."
    out += (" Fit coefficients, standard errors, residuals, and plain means: "
            "[`results/derived/mldsa_fit.csv`](derived/mldsa_fit.csv).")
    cvs = []
    for s in ("fndsa512", "fndsa1024"):
        for b in BOARDS:
            for lvl in (1, 3):
                c = CELLS.get(lat_key(b, f"{LAT_LABEL[s]} sign", lvl))
                if c and c["value"] is not None:
                    w = [r["wall_s"] for r in file_rows(c["src"]) if r["op"] == f"{s}_sign"]
                    cvs.append(statistics.stdev(w) / statistics.mean(w))
    fn = ""
    if cvs:
        fn = (f"FN-DSA signing time has a coefficient of variation of at most "
              f"{max(cvs) * 100:.2f}% over the messages of each of the {len(cvs)} jobs "
              f"Tables D9a and D9b use, so its mean needs no model.")
    return out, fn


def t_fndsa_keygen():
    """Table D10: FN-DSA key generation over seeds 0 to 99."""
    tab = "D10"
    _CUR[0] = tab
    stats = (("mean", "mean"), ("median", "median"), ("min", "minimum"), ("max", "maximum"))
    head = ["Board, level"]
    for s in ("fndsa512", "fndsa1024"):
        head += [f"{LAT_LABEL[s]} {name}" for _, name in stats]
    rows = []
    for b in BOARDS:
        for lvl in (1, 3):
            lab = f"{BOARD_NAME[b]}, level {lvl}"
            cells = []
            for s in ("fndsa512", "fndsa1024"):
                for st, name in stats:
                    cells.append(show(time_cell(tab, lab, f"{LAT_LABEL[s]} {name}", b, lvl,
                                                f"{s}_keygen", "B", None, 0, "ms", st)))
            rows.append([lab] + cells)
    return table(head, rows)


def fndsa_seed_note():
    """How far seeds 0 to 9 sit from the 100-seed mean, from the files Table D10 uses at
    level 3."""
    out = []
    for b in BOARDS:
        for s in ("fndsa512", "fndsa1024"):
            c = CELLS.get(("D10", f"{BOARD_NAME[b]}, level 3", f"{LAT_LABEL[s]} mean"))
            if not c or c["value"] is None:
                continue
            rs = [r for r in file_rows(c["src"]) if r["op"] == f"{s}_keygen"]
            m10 = statistics.mean(r["wall_s"] for r in rs if r["run"] < 10)
            out.append((m10 / c["value"] - 1) * 100)
    if not out:
        return ""
    return (f"At level 3, the mean over seeds 0 to 9 alone is {abs(max(out)):.0f} to "
            f"{abs(min(out)):.0f}% below the 100-seed mean on every board measured, which is why "
            f"the tables use 100 seeds.")


def t_reduced_ram(tab, boards):
    """Tables D11a and D11b: ML-DSA reduced RAM against default, level 3, one core: peak
    stack and expected signing time, reduced over default."""
    rows = []
    head = ["Parameter set"]
    for b in boards:
        head += [f"{BOARD_NAME[b]}, peak stack", f"{BOARD_NAME[b]}, expected signing time"]
    for s in ("mldsa44", "mldsa65", "mldsa87"):
        lab = LAT_LABEL[s]
        cells = []
        for b in boards:
            st_d = cell(MEM_TAB[b], rkey("Lattice", f"{LAT_LABEL[s]} sign"),
                        f"{BOARD_NAME[b]} stack")
            st_r = cell(MEM_TAB[b], rkey("Lattice", f"{LAT_LABEL[s + '_lowram']} sign"),
                        f"{BOARD_NAME[b]} stack")
            t_d = cell(*lat_key(b, sign_row(s)))
            t_r = cell(*lat_key(b, sign_row(s + "_lowram")))
            cells.append(show(derived(tab, lab, f"{BOARD_NAME[b]}, peak stack", st_r, st_d)))
            cells.append(show(derived(tab, lab, f"{BOARD_NAME[b]}, expected signing time",
                                      t_r, t_d)))
        rows.append([lab] + cells)
    return table(head, rows)


def t_level_ratio_lattice():
    """Table D12: lattice level-1 time divided by level-3 time, from D9."""
    tab = "D12"
    rows = []
    for op, lab, stat in lattice_rows_spec():
        if stat == "per_attempt":
            continue
        cells = []
        for b in BOARDS:
            a = cell(*lat_key(b, lab, 1))
            c = cell(*lat_key(b, lab, 3))
            cells.append(show(derived(tab, lab, BOARD_NAME[b], a, c)))
        rows.append([lab] + cells)
    return table(["Operation"] + [BOARD_NAME[b] for b in BOARDS], rows)


def op_words(lab):
    """A row label of Table D9a or D9b as words: "ML-DSA-65 sign (expected)" becomes
    "ML-DSA-65 signing"."""
    lab = lab.replace(" (expected)", "")
    for a, b in ((" keygen", " key generation"), (" sign", " signing"),
                 (" verify", " verification")):
        if lab.endswith(a):
            return lab[:-len(a)] + b
    return lab


def s3_level1_note():
    """Footnote text: lattice ops that run faster at level 1 than at level 3 on the
    ESP32-S3 (Table D12)."""
    faster = []
    for op, lab, stat in lattice_rows_spec():
        c = CELLS.get(("D12", lab, BOARD_NAME["s3"]))
        if c and c["value"] is not None and c["value"] < 1:
            faster.append(f"{op_words(lab)} ({show(c)})")
    if not faster:
        return ("In Table D12 no lattice operation on the ESP32-S3 runs "
                "faster at level 1 than at level 3.")
    names = (", ".join(faster[:-1]) + (", and " if len(faster) > 2 else " and ") + faster[-1]
             if len(faster) > 1 else faster[0])
    return (f"On the ESP32-S3, {names} run faster at level 1 than at "
            f"level 3 (Table D12, level-1 over level-3 time). Level 3 keeps the lattice code "
            f"in flash, so the levels differ in -O3 and the cache sizes; the cause was not "
            f"investigated.")


# ---------------------------------------------------------------- 4.4 memory

def mem_rows_spec():
    """(group, row label, op, variant, swn, cores, merged) for Tables D13 and D14; merged
    marks a row whose two-core run Table D14 folds into the one-core row."""
    out = []
    H = "Hash-based"
    for op_k, op_s, op_v, lab in (("slh_dsa", "slh_dsa", "slh_dsa", "SLH-DSA-SHA2-128s"),
                                  ("sphincs40", "sphincs40", "sphincs40", "SPHINCS+ 2^40")):
        out += [(H, f"{lab} keygen", f"{op_k}_keygen", "B", "", 0, False),
                (H, f"{lab} sign", f"{op_s}_sign", "B", "", 0, False),
                (H, f"{lab} verify", f"{op_v}_verify", "B", "", 0, False)]
    for v in ("B", "L"):
        swn = SWN[v]
        sf = f", stateful, swn={swn}" if v == "L" else ", stateful"
        out += [(H, f"SHRINCS-{v} keygen", "shrincs_keygen", v, "", 0, False),
                (H, f"SHRINCS-{v} sign{sf}", "shrincs_sign", v, swn, 0, False),
                (H, f"SHRINCS-{v} verify, stateful", "shrincs_verify", v, swn, 0, False),
                (H, f"SHRINCS-{v} sign, stateless", "shrincs_sign_stateless", v, swn, 0,
                 True),
                (H, f"SHRINCS-{v} sign, stateless, two cores", "shrincs_sign_stateless", v,
                 swn, 1, True),
                (H, f"SHRINCS-{v} verify, stateless", "shrincs_verify_stateless", v, swn, 0,
                 False)]
    out += [(H, "XMSS 2^10 keygen", "xmss_keygen", "B", "", 0, False),
            (H, "XMSS 2^10 sign", "xmss_sign", "B", "", 0, False),
            (H, "XMSS 2^10 verify", "xmss_verify", "B", "", 0, False)]
    for s, lab in LATTICE_SETS:
        for o in ("keygen", "sign", "verify"):
            out.append(("Lattice", f"{lab} {o}", f"{s}_{o}", "B", "", 0, False))
    return out


def mem_of(rs):
    st = [int(r["stack_peak_bytes"]) for r in rs if r["stack_peak_bytes"]]
    hp = [int(r["heap_peak_bytes"]) for r in rs if r["heap_peak_bytes"]]
    return (max(st) if st else None, max(hp) if hp else None)


def mem_cell(board, level, op, v, swn, dc=0):
    st, hp = _mem_cell(board, level, op, v, swn, dc)
    if not isinstance(st, str) and LAST_MEM[0]:
        rnd, rs = LAST_MEM[0]
        note_summary("mem", board, level, op, v, swn, dc, rnd, LAST[0], rs)
    LAST_MEM[0] = None
    return st, hp


LAST_MEM = [None]


def _mem_cell(board, level, op, v, swn, dc=0):
    if board == "rp":
        if not RP2350_DATA:
            return (PENDING, PENDING)
        s = esp_set_for(op)
        rs = None
        for vv in ((v, "L" if v == "B" else "B") if is_lattice(op) else (v,)):
            rs = rp_rows(level, vv, dc, s, op, swn if swn else None)
            if rs:
                break
        if not rs:
            m = rp_missing(level, v, dc, s)
            return (m, m)
        LAST_MEM[0] = (4, rs)
        return mem_of(rs)
    if board == "pi":
        if dc:
            return (NA, NA)
        rs = pi_get(2, level, op, v, swn, mem=True)
        if not rs:
            return (PENDING, PENDING)
        LAST_MEM[0] = (2, rs)
        return mem_of(rs)
    if board == "pi2":
        # Memory builds are one-core only, as on the Pi Zero.
        if dc:
            return (NA, NA)
        rs = pi2_get(level, op, v, swn, mem=True)
        if not rs:
            m = pi2_missing(level, op, v, swn, True, 0)
            return (m, m)
        LAST_MEM[0] = (4, rs)
        return mem_of(rs)
    s = esp_set_for(op)
    rs = esp_rows(2, board, level, v, dc, s, op, swn if swn else None, n=10)
    if not rs:
        m = missing_text(board, level, op, v, dc)
        return (m, m)
    LAST_MEM[0] = (2, rs)
    return mem_of(rs)


def num_cell(tab, row, col, x):
    if isinstance(x, str) or x is None:
        return put(tab, row, col, text=x or NA, unit="bytes")
    return put(tab, row, col, value=x, num=f"{x:,}", unit="bytes")


def t_memory(tab, boards):
    _CUR[0] = tab
    rows = []
    group = None
    pi_only = all(b in PI_BOARDS for b in boards)
    for g, lab, op, v, swn, dc, merged in mem_rows_spec():
        if dc and pi_only:
            continue  # the Pi boards' memory builds ran on one core only
        if g != group:
            rows.append(group_row(g, 2 * len(boards)))
            group = g
        cells = []
        for b in boards:
            st, hp = mem_cell(b, 3, op, v, swn, dc)
            cells += [show(num_cell(tab, rkey(g, lab), f"{BOARD_NAME[b]} stack", st)),
                      show(num_cell(tab, rkey(g, lab), f"{BOARD_NAME[b]} heap", hp))]
        rows.append([lab] + cells)
    head = ["Operation"]
    for b in boards:
        head += [f"{BOARD_NAME[b]} stack", f"{BOARD_NAME[b]} heap"]
    return table(head, rows)


def t_memory_max(tab, boards):
    _CUR[0] = tab
    rows = []
    group = None
    for g, lab, op, v, swn, dc0, merged in mem_rows_spec():
        if dc0:
            continue  # the two-core runs are part of each operation's maximum
        if g != group:
            rows.append(group_row(g, 2 * len(boards)))
            group = g
        lab = lab + " (one and two cores)" if merged and not all(
            b in PI_BOARDS for b in boards) else lab
        cells = []
        for b in boards:
            best_s, best_h = None, None
            for lvl in LEVELS:
                for dc in ((0,) if b in PI_BOARDS else (0, 1)):
                    st, hp = mem_cell(b, lvl, op, v, swn, dc)
                    where = f"L{lvl}" + ("" if b in PI_BOARDS else f", {dc + 1}c")
                    if not isinstance(st, str) and st is not None and (
                            best_s is None or st > best_s[0]):
                        best_s = (st, where)
                    if not isinstance(hp, str) and hp is not None and (
                            best_h is None or hp > best_h[0]):
                        best_h = (hp, where)
            cells += [f"{best_s[0]:,} ({best_s[1]})" if best_s else PENDING,
                      f"{best_h[0]:,} ({best_h[1]})" if best_h else PENDING]
        rows.append([lab] + cells)
    head = ["Operation"]
    for b in boards:
        head += [f"{BOARD_NAME[b]} stack (where)", f"{BOARD_NAME[b]} heap (where)"]
    return table(head, rows)


# ---------------------------------------------------------------- 4.5 two cores

def t_two_cores(tab, boards):
    """Tables D15a and D15b: one-core time divided by two-core time on the boards with
    two-core builds."""
    cols = [(b, lvl) for b in boards for lvl in LEVELS]
    rows = []
    for group, ops in HASH_GROUPS:
        rows.append(group_row(group, len(cols)))
        for op, v, swn, lab in ops:
            cells = []
            for b, lvl in cols:
                t = HASH_TAB[b]
                a = cell(t, rkey(group, lab), hash_col_label(b, lvl, 0))
                c = cell(t, rkey(group, lab), hash_col_label(b, lvl, 1))
                cells.append(show(derived(tab, rkey(group, lab), f"{BOARD_NAME[b]}, level {lvl}",
                                          a, c)))
            rows.append([lab] + cells)
    g = "Signing, stateless"
    rows.append(group_row(g, len(cols)))
    for v in ("B", "L"):
        lab = f"SHRINCS-{v}, stateless (expected)"
        cells = []
        for b, lvl in cols:
            a = cell("D7", f"{BOARD_NAME[b]}, one core", f"SHRINCS-{v}, level {lvl}")
            c = cell("D7", f"{BOARD_NAME[b]}, two cores", f"SHRINCS-{v}, level {lvl}")
            cells.append(show(derived(tab, rkey(g, lab), f"{BOARD_NAME[b]}, level {lvl}", a, c)))
        rows.append([lab] + cells)
    return table(["Operation"] + [f"{BOARD_NAME[b]}, level {lvl}" for b, lvl in cols], rows)


# ---------------------------------------------------------------- 4.6 reproducibility

PI_R1 = dict(((1, "raw/pi0w/r1/results_plainc_20261119_134109.csv"),
              (2, "raw/pi0w/r1/results_20261119_010831.csv"),
              (3, "raw/pi0w/r1/results_l3pie_20261119_172249.csv")))


def esp_r1_path(b, lvl, v, dc):
    if lvl == 1:
        sub = "" if dc == 0 else "raw-opt/"
        return f"raw/esp32{b}/r1/{sub}{b}-{v}-soft-dc{dc}-direct-r10.log"
    if lvl == 2:
        return f"raw/esp32{b}/r1/{b}-{v}-hw-dc{dc}-direct-r10.log"
    return f"raw/esp32{b}/r1/raw-opt/{b}-opt-{v}-hwshadow-dc{dc}-r10.log"


_R1 = dict()


def r1_rows(path, op, v, swn):
    full = os.path.join(RES, path)
    if full not in _R1:
        _R1[full] = list(SUMM.read_rows(full))
    use(full)
    out = []
    for r in _R1[full]:
        if r["op"] != op or (op == "shrincs_sign" and r["swn"] != swn):
            continue
        b = r["build"].lower()
        if path == PI_R1[2] and "plain-c" in b:
            continue
        if op.startswith("shrincs") and path.endswith(".csv"):
            if ("shrincs-l" in b) != (v == "L"):
                continue
        out.append(r)
    return out


def repro_cell(board, lvl, op, v, swn, dc):
    if board == "pi":
        r1 = r1_rows(PI_R1[lvl], op, v, swn)
        r2 = pi_get(2, lvl, op, v, swn)
    else:
        r1 = r1_rows(esp_r1_path(board, lvl, v, dc), op, v, swn)
        r2 = esp_rows(2, board, lvl, v, dc, "r1", op, swn if op == "shrincs_sign" else None,
                      n=10)
        if r2 is None:
            return missing_text(board, lvl, op, v, dc), None
    if not r1 or not r2:
        return PENDING, None
    runs = set(r["run"] for r in r1) & set(r["run"] for r in r2)
    m1 = statistics.mean(r["wall_s"] for r in r1 if r["run"] in runs)
    m2 = statistics.mean(r["wall_s"] for r in r2 if r["run"] in runs)
    h1 = dict((r["run"], r["out_sha256"]) for r in r1)
    differ = sum(1 for r in r2 if r["run"] in runs and h1.get(r["run"]) != r["out_sha256"])
    return (m2 / m1 - 1) * 100, differ


def t_repro(board, tab):
    _CUR[0] = tab
    if board == "pi":
        cols = [(lvl, 0) for lvl in LEVELS]
    else:
        cols = [(lvl, dc) for lvl in LEVELS for dc in (0, 1)]
    labels = [f"Level {lvl}" + ("" if board == "pi" else f", {CORES[dc]}") for lvl, dc in cols]
    rows = []
    stats_by_col = collections.defaultdict(list)
    for op, v, swn, lab in R1_OPS:
        cells = []
        for (lvl, dc), cl in zip(cols, labels):
            ch, differ = repro_cell(board, lvl, op, v, swn, dc)
            if isinstance(ch, str):
                cells.append(ch)
                continue
            put(tab, lab, cl, value=ch, num=f"{ch:+.2f}", unit="%")
            stats_by_col[(lvl, dc)].append((abs(ch), lab, differ))
            cells.append(f"{ch:+.2f}%" + (" *" if differ else ""))
        rows.append([lab] + cells)
    summary = []
    for (lvl, dc), cl in zip(cols, labels):
        xs = stats_by_col.get((lvl, dc))
        if not xs:
            summary.append(f"{cl}: pending")
            continue
        w = max(xs)
        txt = f"{cl}: {w[0]:.2f}% ({w[1]})"
        if len(xs) < len(R1_OPS):
            txt += f" over the {len(xs)} of {len(R1_OPS)} operations measured so far"
        summary.append(txt)
    marked = sum(1 for col in stats_by_col.values() for x in col if x[2])
    tail = (f" Cells marked * ({marked}) hold at least one run whose output differs from "
            f"the first round's, so the work differed (two-core grinding)." if marked else
            " Every compared output equals the first round's." if stats_by_col else "")
    return (table(["Operation"] + labels, rows),
            "Largest absolute change per column:\n\n" + "\n".join(f"- {x}" for x in summary)
            + "\n\n" + tail.strip())


def p4_shift_note():
    """Footnote text: the ESP32-P4 two-core shift at levels 1 and 2 (Table D16b)."""
    ops = ["SHRINCS-B sign", "SHRINCS-B keygen", "SHRINCS-B self-test"]
    low = []
    l3 = []
    one = []
    for lab in ops:
        for lvl in LEVELS:
            for dc in (0, 1):
                c = CELLS.get(("D16b", lab, f"Level {lvl}, {CORES[dc]}"))
                if not c or c["value"] is None:
                    continue
                if dc and lvl < 3:
                    low.append(c["value"])
                elif dc:
                    l3.append(abs(c["value"]))
                else:
                    one.append(abs(c["value"]))
    if not low:
        return "Pending: Table D16b is incomplete."
    if min(low) > 0:
        change = f"take {min(low):.2f} to {max(low):.2f}% longer in the second round than in the first"
    else:
        change = f"change by {min(low):+.2f} to {max(low):+.2f}% from the first round to the second"
    return (f"On the ESP32-P4 with two cores, SHRINCS-B signing, key generation, and "
            f"self-test at levels 1 and 2 {change} (Table D16b), against at most "
            f"{max(l3):.2f}% at level 3 and {max(one):.2f}% on one core; the hot SHRINCS "
            f"functions sit at different flash "
            f"addresses in the two rounds' binaries, consistent with a flash-cache placement "
            f"effect that was not tested further. Either round's figure describes a valid "
            f"build.")


# ---------------------------------------------------------------- key results



def flag_of(*keys):
    return R2_MARK if any(cell(*k)["flag"] == R2_MARK for k in keys) else ""


def hash_sign_key(b, lab, dc=0):
    return (HASH_TAB[b], rkey("Signing", lab), hash_col_label(b, 3, dc))


def lat_key(b, row, lvl=3):
    return (LAT_TAB[b], row, f"{BOARD_NAME[b]}, level {lvl}")


def stateless_key(b, v):
    return ("D7", f"{BOARD_NAME[b]}, one core", f"SHRINCS-{v}, level 3")


# K1 groups: (key, heading as shown, rows); a row is (label, detail row label or None for
# SHRINCS stateless, variant, size key, expected, label footnotes). SHRINCS-B and
# SHRINCS-L (the earlier SHRINCS design) are left out: they appear in the detail tables
# only.
K1_STATELESS = "Stateless: nothing to keep between signatures"
K1_STATEFUL = "Stateful: the device must never lose or reuse its counter"
K1_LATTICE = "Lattice (stateless)"
K1_GROUPS = [
    (K1_STATELESS, K1_STATELESS, [
        ("SLH-DSA-SHA2-128s", "SLH-DSA-SHA2-128s", "B", ("slh_dsa_sign", "B"), False, ""),
        ("SPHINCS+ 2^40", "SPHINCS+ 2^40", "B", ("sphincs40_sign", "B"), False,
         "{{fn:shrincs-draft}}"),
    ]),
    (K1_STATEFUL, K1_STATEFUL, [
        ("XMSS 2^10", "XMSS 2^10", "B", ("xmss_sign", "B"), False, "{{fn:fixed-keys}}"),
    ]),
    (K1_LATTICE, K1_LATTICE + "{{fn:deterministic}}",
     [(LAT_LABEL[s], sign_row(s), "B", (f"{s}_sign", "B"), s.startswith("mldsa"),
       "{{fn:fndsa-standard}}" if s.startswith("fndsa") else "")
      for s in ("mldsa44", "mldsa65", "mldsa87", "fndsa512", "fndsa1024")]),
]


def size_text(key):
    sizes = SIZES.get(key)
    if not sizes:
        return PENDING
    assert len(sizes) == 1, (key, sizes)
    return f"{next(iter(sizes)):,} bytes"


def k1_sign_key(group, row, v, b):
    if group == K1_LATTICE:
        return lat_key(b, row)
    if row is None:
        return stateless_key(b, v)
    return hash_sign_key(b, row)


def k1():
    """Table K1: signing time at level 3 on one core, rounded to three significant
    figures from the detail tables; an asterisk marks expected values."""
    head = ["Scheme"] + [BOARD_NAME[b] for b in BOARDS]
    rows = []
    for gkey, gshow, specs in K1_GROUPS:
        rows.append(group_row(gshow, len(head) - 1))
        for label, row, v, size, expected, fn in specs:
            cells = []
            unit = "ms" if gkey == K1_LATTICE else "s"
            for b in BOARDS:
                key = k1_sign_key(gkey, row, v, b)
                c = cell(*key)
                if c["value"] is None:
                    cells.append(c["text"])
                    continue
                s = NF.rsig(c["num"], 3)
                REFS.append(dict(kind="cell", where=("K1", rkey(gkey, label), BOARD_NAME[b]),
                                 keys=[key], sig=3, mode="round", scale=1, factor=1,
                                 text=s + flag_of(key)))
                cells.append(f"{s} {unit}" + ("*" if expected else "") + flag_of(key))
            rows.append([label + fn] + cells)
    note = ("\\* Expected value per message: the signing time varies by message, and the "
            "figure comes from a fit over the measured messages (sections 3.1 and 3.3).")
    if PEND:
        note += (f" {R2_MARK} Second-round figure, to be replaced by round "
                 f"3{{{{fn:r3}}}}.")
    return table(head, rows), note


def pi2_clock():
    """The one footnote on the Pi Zero 2 W's clock, cited where the pages say it ran at
    1 GHz: SeedSigner OS currently runs it at 600 MHz."""
    return ("SeedSigner OS currently runs the Pi Zero 2 W at 600 MHz "
            "([SeedSigner/seedsigner-os#129]"
            "(https://github.com/SeedSigner/seedsigner-os/issues/129)).")


# ---------------------------------------------------------------- C1: rough comparison

PUB_DIR = os.path.join(RES, "published")
URL_BLOCKSTREAM = "https://blog.blockstream.com/hardware-wallets-post-quantum-signatures/"
URL_GIST = "https://gist.github.com/onvej-sl/3851bdae7ae5aa1f2624ca769737ea2e"
URL_DONJON = "https://www.ledger.com/blog-quantum-computing-threat-to-blockchain"
URL_PQM4 = "https://github.com/mupq/pqm4/tree/master/results/speed"
# Chips and clocks of Blockstream's wallets: vendor and certification documents
# (docs/other-devices-hash-hardware.md) and Jade's build configuration, footnoted
# once at each table's "Chip and clock" header.
CHIP_JADE = "ESP32-S3, 240 MHz"
CHIP_SAFE3 = "STM32F427, 180 MHz, or STM32U585, 160 MHz"
# Blockstream's signing column for Trezor reads "Trezor Safe 3/5/7": the Safe 3 (STM32F427
# or STM32U585), the Safe 5 (STM32U585), and the Safe 7 (STM32U5G9).
TREZOR_SIGN = "Trezor Safe 3/5/7"
CHIP_TREZOR = "STM32F427, 180 MHz, or STM32U585 or STM32U5G9, 160 MHz"
CHIP_LEDGER = "ST33K1M5 secure element, 70 or 75 MHz"
CHIP_BITBOX = "ATSAMD51J20A (Cortex-M4F), 120 MHz"
# Columns: (header, unit, our detail-table row for that scheme's signing).
C1_COLS = [("SLH-DSA-SHA2-128s", "s", "SLH-DSA-SHA2-128s"),
           ("SPHINCS+ 2^40", "s", "SPHINCS+ 2^40"),
           ("ML-DSA-44", "ms", "mldsa44"), ("FN-DSA-512", "ms", "fndsa512")]
# Other reports' devices: label, chip and clock (as the source states them), source cell,
# and per column a transcription lookup (file, match, column, factor to the column's unit,
# and, for cycle counts, the column holding the clock in MHz to divide by).
BS = "blockstream_2026-08-19.csv"
GIST = "onvej-sl-gist_2025-04.csv"
DONJON = "ledger-donjon_2026-02-26.csv"
PQM4 = "pqm4_2026-11-24.csv"
TZ_HW = "trezor-hw-sha_2025-12.csv"
URL_TZ_ISSUE = "https://github.com/trezor/trezor-firmware/issues/6835"
URL_TZ_NOTES = ("https://github.com/trezor/trezor-firmware/blob/cepetr/slh-dsa-hw-sha/"
                "branch-notes.md")
C1_OTHERS = [
    ("Jade Plus", "{CHIP_JADE}",
     f"[Blockstream, 2026-08-19]({URL_BLOCKSTREAM})",
     dict(((0, (BS, dict(op="slh_dsa_sign"), "jade_plus", "1", None)),
           (1, (BS, dict(op="sphincs40_sign"), "jade_plus", "1", None))))),
    (TREZOR_SIGN, "{CHIP_TREZOR}", f"[Blockstream, 2026-08-19]({URL_BLOCKSTREAM})",
     dict(((0, (BS, dict(op="slh_dsa_sign"), "trezor_safe_3", "1", None)),
           (1, (BS, dict(op="sphincs40_sign"), "trezor_safe_3", "1", None))))),
    ("Ledger Nano gen5/S+", "{CHIP_LEDGER}", f"[Blockstream, 2026-08-19]({URL_BLOCKSTREAM})",
     dict(((0, (BS, dict(op="slh_dsa_sign"), "ledger_nano_gen5_splus", "1", None)),
           (1, (BS, dict(op="sphincs40_sign"), "ledger_nano_gen5_splus", "1", None))))),
    ("BitBox02 Nova", "{CHIP_BITBOX}", f"[Blockstream, 2026-08-19]({URL_BLOCKSTREAM})",
     dict(((0, (BS, dict(op="slh_dsa_sign"), "bitbox02_nova", "1", None)),
           (1, (BS, dict(op="sphincs40_sign"), "bitbox02_nova", "1", None))))),
    ("Trezor Model T{{fn:comp-gist}}", "STM32F427 (Cortex-M4F), 180 MHz",
     f"[trezor-firmware PR #4901](https://github.com/trezor/trezor-firmware/pull/4901) and [gist]({URL_GIST}), 2025-04",
     dict(((0, (GIST, dict(op="sign", scheme="SLH-DSA-SHA2-128s"), "time_ms", "0.001", None)),
           (2, (GIST, dict(op="sign", scheme="ML-DSA-44"), "time_ms", "1", None)),
           (3, (GIST, dict(op="sign", scheme="FN-DSA-512"), "time_ms", "1", None))))),
    ("Not named in the post{{fn:comp-donjon}}", "not stated", f"[Ledger Donjon, 2026-02-26]({URL_DONJON})",
     dict(((2, (DONJON, dict(table="time", op="Signing", scheme="ML-DSA-44"), "value", "1",
                None)),
           (3, (DONJON, dict(table="time", op="Signing", scheme="Falcon-512"), "value", "1",
                None))))),
    ("Trezor Safe 7, developer experiment with the hash unit{{fn:tz-hw}}",
     "STM32U5G9 (Cortex-M33), 160 MHz",
     f"[trezor-firmware issue #6835]({URL_TZ_ISSUE}) and [branch notes]({URL_TZ_NOTES})",
     dict(((0, (TZ_HW, dict(device="Trezor Safe 7", scheme="SPHINCS+ SHA2-128s", op="sign"),
                "seconds", "1", None)),))),
    ("NUCLEO-L4R5ZI", "Cortex-M4, {clock:pqm4} MHz", f"[pqm4]({URL_PQM4}), derived{{{{fn:comp-pqm4}}}}",
     dict(((0, (PQM4, dict(scheme="slh-dsa-sha2-128s", implementation="ref", op="sign"),
                "avg_cycles", "1", "clock_mhz")),
           (2, (PQM4, dict(scheme="ml-dsa-44", implementation="clean", op="sign"),
                "avg_cycles", "1000", "clock_mhz"))))),
]


def pub_rows(name):
    use(os.path.join(PUB_DIR, name))
    with open(os.path.join(PUB_DIR, name)) as f:
        return list(csv.DictReader(ln for ln in f if not ln.startswith("#")))


def pub_lookup(name, match, column, factor, per):
    """A transcribed figure in the column's unit, as a Decimal: the matching row's column
    times factor, divided by its clock (MHz x 10^6) for cycle counts."""
    rs = [r for r in pub_rows(name) if all(r.get(k, "") == v for k, v in match.items())]
    assert len(rs) == 1, (name, match, len(rs))
    x = NF.dnum(rs[0][column]) * NF.dnum(factor)
    if per:
        x = x / (NF.dnum(rs[0][per]) * 1000000)
    return x, rs[0]


def t_compare():
    """Table H5: signing time per device for four schemes, ours at level 3 on one core (as
    K1) and other reports' as transcribed under results/published/, rounded to two
    significant figures; rows ordered by the geometric mean, over the columns a row has,
    of its time divided by the Pi Zero's. Every cell is recorded in REFS for fill.py."""
    tab = "H5"
    _CUR[0] = tab
    head = ["Device", "Chip and clock{{fn:chips}}"] + [c[0] for c in C1_COLS] + ["Source"]

    def our_key(b, i):
        row = C1_COLS[i][2]
        if row.startswith(("mldsa", "fndsa")):
            return lat_key(b, sign_row(row))
        return hash_sign_key(b, row)

    rows = []  # (sort value, label, chip, cells, source)
    ref = [cell(*our_key("pi", i))["value"] * (1000 if C1_COLS[i][1] == "ms" else 1)
           for i in range(len(C1_COLS))]
    for b in BOARDS:
        cells, logs = [], []
        if cell(*our_key(b, 0))["value"] is None:
            rows.append((float("inf"), BOARD_NAME[b], S["boards"][b]["chip_clock"],
                         [PENDING] * len(C1_COLS), "this report"))
            continue
        for i, (hd, unit, _) in enumerate(C1_COLS):
            key = our_key(b, i)
            c = cell(*key)
            s = NF.rsig(c["num"], 2)
            REFS.append(dict(kind="cell", where=(tab, BOARD_NAME[b], hd), keys=[key], sig=2,
                             mode="round", scale=1, factor=1, text=s + flag_of(key)))
            cells.append(f"{s} {unit}" + flag_of(key))
            v = c["value"] * (1000 if unit == "ms" else 1)
            logs.append(math.log(v / ref[i]))
        chip = S["boards"][b]["chip_clock"]
        rows.append((sum(logs) / len(logs), BOARD_NAME[b], chip, cells, "this report"))
    for label, chip, source, spec in C1_OTHERS:
        cells, logs = [], []
        for i, (hd, unit, _) in enumerate(C1_COLS):
            if i not in spec:
                cells.append("–")
                continue
            name, match, column, factor, per = spec[i]
            x, r = pub_lookup(name, match, column, factor, per)
            s = NF.rsig(x, 2, cap=False)
            REFS.append(dict(kind="pub", where=(tab, re.sub(r"\{\{fn:[\w-]+\}\}", "", label),
                                                hd),
                             file=name, match=match, column=column, factor=factor, per=per,
                             sig=2, text=s))
            cells.append(f"{s} {unit}")
            logs.append(math.log(float(x) / ref[i]))
            if per:
                chip = chip.replace("{clock:pqm4}", r[per])
        chip = chip.format(CHIP_JADE=CHIP_JADE, CHIP_TREZOR=CHIP_TREZOR,
                           CHIP_LEDGER=CHIP_LEDGER,
                           CHIP_BITBOX=CHIP_BITBOX) if "{CHIP_" in chip else chip
        rows.append((sum(logs) / len(logs), label, chip, cells, source))
    rows.sort(key=lambda x: x[0])
    return table(head, [[lab, chip] + cells + [src] for _, lab, chip, cells, src in rows])


# C1: a rough ranking by one factor: each device's signing time for SLH-DSA-SHA2-128s and
# for SPHINCS+ 2^40 (the parameters of the current SHRINCS draft's stateless path),
# divided by the fastest device's time for that scheme; the factor is the geometric mean
# of the two ratios. Both schemes are in Blockstream's table and neither depends on the
# earlier SHRINCS design. Devices: ours (level 3, one core, the detail cells as displayed)
# and Blockstream's four wallets. (label, detail row, published-figure match; Table D18
# labels its rows "<label> sign".)
C1_SCHEMES = [("SLH-DSA-SHA2-128s", "SLH-DSA-SHA2-128s", dict(op="slh_dsa_sign")),
              ("SPHINCS+ 2^40", "SPHINCS+ 2^40", dict(op="sphincs40_sign"))]
C1_WALLETS = [("Jade Plus", CHIP_JADE, "jade_plus"),
              (TREZOR_SIGN, CHIP_TREZOR, "trezor_safe_3"),
              ("Ledger Nano gen5/S+", CHIP_LEDGER, "ledger_nano_gen5_splus"),
              ("BitBox02 Nova", CHIP_BITBOX, "bitbox02_nova")]
C1_HEAD_PLAIN = "Relative to the Jade Plus"
C1_HEAD = C1_HEAD_PLAIN + "{{fn:c1-method}}"
C1_BASE = "Jade Plus"  # the baseline: Blockstream's published figure, 1.0x
MINUS = "\u2212"
C1_OURS = "Boards tested here"
# Single-scheme rows: a result with one scheme, compared with the
# baseline on that scheme only; (label as shown, footnote, scheme index, transcription
# spec).
C1_SINGLE = [("Trezor Safe 7 (test build)", "{{fn:tz-hw}}", 0,
              dict(kind="pub", file=TZ_HW, match=dict(device="Trezor Safe 7",
                                                       scheme="SPHINCS+ SHA2-128s", op="sign"),
                   column="seconds", factor="1", per=None))]
C1_THEIRS = "Hardware wallets, Blockstream, 2026-08-19"


def c1_value(spec):
    if spec["kind"] == "cell":
        return NF.dnum(cell(*spec["key"])["num"])
    return pub_lookup(spec["file"], spec["match"], spec["column"], spec["factor"],
                      spec["per"])[0]


def t_rank():
    """Table C1 (two columns, two row groups) and its method footnote: returns (table,
    footnote text). Every multiplier, and the footnote's order check and largest ratio
    spread, are recorded in REFS for fill.py."""
    tab = "C1"
    _CUR[0] = tab
    devs = []  # (group, label, input specs or None)
    for b in BOARDS:
        keys = [hash_sign_key(b, row) for _, row, _ in C1_SCHEMES]
        specs = None if any(cell(*k)["value"] is None for k in keys) else [
            dict(kind="cell", key=list(k)) for k in keys]
        devs.append((C1_OURS, BOARD_NAME[b], specs))
    for label, chip, col in C1_WALLETS:
        devs.append((C1_THEIRS, label, [dict(kind="pub", file=BS, match=m, column=col,
                                             factor="1", per=None) for _, _, m in C1_SCHEMES]))
    vals = dict((d[1], [c1_value(s) for s in d[2]]) for d in devs if d[2])
    best = [min(v[i] for v in vals.values()) for i in range(len(C1_SCHEMES))]
    ratios = dict((k, [v[i] / best[i] for i in range(len(best))]) for k, v in vals.items())
    factor = dict((k, (r[0] * r[1]).sqrt()) for k, r in ratios.items())
    S["c1"] = dict(vals=vals, factor=factor, devs=devs)
    head = ["Device", C1_HEAD]
    rows = []
    fb = factor[C1_BASE]

    def shown(label):
        """+N.N (N times as fast as the baseline), -N.N with U+2212 (N times as long), or
        1.0 for the baseline; two significant figures."""
        f = factor[label]
        if label == C1_BASE:
            return "1.0"
        if f < fb:
            return "+" + NF.rsig(fb / f, 2, cap=False)
        return MINUS + NF.rsig(f / fb, 2, cap=False)

    # Single-scheme rows: that scheme's time over the baseline's for the same scheme,
    # placed in the speed order by the equivalent factor (the baseline's factor divided by
    # the ratio); they stay out of the order check and the spread below.
    base_specs = dict((d[1], d[2]) for d in devs if d[2])[C1_BASE]
    single = dict()
    for label, fnm, i, spec in C1_SINGLE:
        rel = vals[C1_BASE][i] / c1_value(spec)
        single[label] = (rel, fnm, [spec, base_specs[i]])
        factor[label] = fb / rel
    # No group rows and no fastest or slowest tags: the green and red values and the
    # chart's bars carry the direction.
    measured = sorted([d for d in devs if d[2]] + [(None, k, None) for k in single],
                      key=lambda d: factor[d[1]])
    for _, label, specs in measured:
        lab = f"{label} (baseline)" if label == C1_BASE else label
        if label in single:
            rel, fnm, ins = single[label]
            s = ("+" + NF.rsig(rel, 2, cap=False) if rel > 1 else
                 MINUS + NF.rsig(1 / rel, 2, cap=False))
            REFS.append(dict(kind="factor1", where=(tab, lab, C1_HEAD_PLAIN), inputs=ins,
                             text=s))
            rows.append([lab + fnm, f"{s}x"])
            continue
        s = shown(label)
        REFS.append(dict(kind="factor", where=(tab, lab, C1_HEAD_PLAIN),
                         inputs=specs, text=s, baseline=label == C1_BASE))
        rows.append([lab, f"{s}x"])
    for label in single:  # keep the two-scheme checks below to two-scheme rows
        del factor[label]
    rows += [[d[1], PENDING] for d in devs if not d[2]]
    orders = [[k for k, _ in sorted(ratios.items(), key=lambda kv: kv[1][i])]
              for i in range(len(C1_SCHEMES))]
    spread = dict((k, max(r) / min(r)) for k, r in ratios.items())
    worst = max(spread, key=lambda k: spread[k])
    sp, r0, r1 = (NF.rsig(x, 2, cap=False)
                  for x in (spread[worst], ratios[worst][0], ratios[worst][1]))
    swaps = [(a, b) for i, a in enumerate(orders[0]) for b in orders[0][i + 1:]
             if orders[1].index(a) > orders[1].index(b)]
    REFS.append(dict(kind="c1-spread", where=("C1 footnote",), device=worst,
                     text=f"{sp}|{r0}|{r1}|{len(swaps)}"))
    same = ("Both schemes put the devices in the same order" if not swaps else
            "The schemes order the devices differently for " + table_list(
                [f"{a} and {b}" for a, b in swaps]))
    fn = (f"Relative to the {C1_BASE}: each device's factor is the geometric mean of its "
          f"two ratios, its {C1_SCHEMES[0][0]} and its {C1_SCHEMES[1][0]} signing "
          f"time, each divided by the fastest device's time for that scheme. The table "
          f"compares that factor with the {C1_BASE}'s, from Blockstream's published figures: "
          f"+Nx means the device signs N times as fast as the {C1_BASE} (the {C1_BASE}'s "
          f"factor divided by the device's), {MINUS}Nx that it takes N times as long (the "
          f"device's factor divided by the {C1_BASE}'s), to two significant figures. The "
          f"{table_list([re.sub(r' [(](.*)[)]$', lambda m: ' ' + m.group(1), k) for k, _, _, _ in C1_SINGLE])} "
          f"has one scheme: its row compares that scheme's time with the {C1_BASE}'s for the "
          f"same scheme and is left out of what follows. {same}, and a device's two ratios "
          f"differ by up to a factor of {sp} "
          f"(the {worst}: {r0} for {C1_SCHEMES[0][0]} against {r1} for {C1_SCHEMES[1][0]}). "
          f"Our boards: level 3, one core, the means of the per-board tables in section 3.1; "
          f"chips and clocks in section 2.1. Blockstream's wallets: its published averages of "
          f"100 executions, timed on the host over each wallet's USB interface, which "
          f"includes data transfer and any display work during the operation "
          f"(`results/published/blockstream_2026-08-19.csv`). Their chips and clocks come "
          f"from vendor and certification documents, not from the post: "
          + "; ".join(f"{lab}, {chip}" for lab, chip, _ in C1_WALLETS)
          + " (Jade Plus: Jade's build configuration; Blockstream's Trezor signing figures "
          "are labeled Trezor Safe 3/5/7, and it does not say which model or hardware "
          "revision it timed; `docs/other-devices-hash-hardware.md`).")
    return table(head, rows), fn


# Section 1's discussion: two short paragraphs whose figures come from displayed detail
# cells, Table D18, and the transcriptions; each figure is recorded in REFS (kind "quote")
# for fill.py, which recomputes it and finds it in section 1.
def quote(op, inputs, vals, sig, mode="round"):
    if op == "value":
        x = vals[0]
    elif op == "ratio":
        x = vals[0] / vals[1]
    elif op == "min":
        x = min(vals)
    elif op == "max":
        x = max(vals)
    elif op == "gm-ratio":
        x = (vals[0] * vals[1]).sqrt() / (vals[2] * vals[3]).sqrt()
    else:
        raise ValueError(op)
    s = NF.rsig(x, sig, mode, cap=False)
    REFS.append(dict(kind="quote", op=op, inputs=inputs, sig=sig, mode=mode, text=s))
    return s


def discussion(L2):
    """Returns (speed paragraph, wallets paragraph) for section 1."""
    def cval(key):
        return NF.dnum(cell(*key)["num"])

    def cs(k):
        return dict(kind="cell", key=list(k))

    def wal(op):
        return [dict(kind="pub", file=BS, match=dict(op=op), column=c, factor="1",
                     per=None) for _, _, c in C1_WALLETS]

    def wv(specs):
        return [c1_value(x) for x in specs]

    # Headline level only (a summary for casual readers): the figures a reader needs,
    # each checked; the breakdowns live in section 3 (K1, D18, H5).
    ours = [b for b in BOARDS if b != "rp" or RP2350_DATA]
    slh_row = C1_SCHEMES[0][1]
    mine = [hash_sign_key(b, slh_row) for b in ours]
    top = max(cval(k) for k in mine)
    limit = int(top) + 1
    REFS.append(dict(kind="bound", inputs=[cs(k) for k in mine], limit=str(limit),
                     text=f"under {limit} seconds"))
    w_slh, w_shr = (wal(m["op"]) for _, _, m in C1_SCHEMES)
    speed = (
        f"Signing with {C1_SCHEMES[0][0]}, the standardized hash-based scheme that needs "
        f"nothing saved between signatures:\n\n"
        f"- **SeedSigner ecosystem boards:** under {limit} seconds.\n"
        f"- **Hardware wallets in Blockstream's tests:** "
        f"{quote('min', w_slh, wv(w_slh), 2)} to {quote('max', w_slh, wv(w_slh), 2)} "
        f"seconds.")
    s3_slh, s3_shr = (hash_sign_key("s3", row) for _, row, _ in C1_SCHEMES)
    jade = [x for x in w_slh if x["column"] == "jade_plus"][0]
    jade_shr = [x for x in w_shr if x["column"] == "jade_plus"][0]
    safe3 = [x for x in w_slh if x["column"] == "trezor_safe_3"][0]
    jv, jsv, s3v = c1_value(jade), c1_value(jade_shr), c1_value(safe3)
    s7 = dict(kind="pub", file=TZ_HW, match=dict(device="Trezor Safe 7",
                                                  scheme="SPHINCS+ SHA2-128s", op="sign"),
              column="seconds", factor="1", per=None)
    s7v = c1_value(s7)
    # Low end: Jade's own firmware timed on our ESP32-S3 board (Table D18) against our
    # level-3 build; high end: Blockstream's published Jade Plus figures against it.
    cal = [dict(kind="cell",
                key=["D18", f"{lab} sign", "Jade firmware, our ESP32-S3 board (s)"])
           for lab, _, _ in C1_SCHEMES]
    calv = [NF.dnum(L2.cal_value(m["op"])) for _, _, m in C1_SCHEMES]
    lo = quote("gm-ratio", cal + [cs(s3_slh), cs(s3_shr)],
               calv + [cval(s3_slh), cval(s3_shr)], 1)
    hi = quote("gm-ratio", [jade, jade_shr, cs(s3_slh), cs(s3_shr)],
               [jv, jsv, cval(s3_slh), cval(s3_shr)], 1)
    same_chip = f"{lo} to {hi}" if lo != hi else lo
    faster = (
        f"- **Same chip, different result:** the Jade Plus uses the same chip as our "
        f"ESP32-S3 board, yet our build signs about {same_chip} times as fast, largely by "
        f"making better use of the chip's SHA-256 hardware.\n"
        f"- **Trezor too:** a Trezor developer's test firmware signed about "
        f"{quote('ratio', [safe3, s7], [s3v, s7v], 1)} times as fast as Blockstream's "
        f"Trezor figure, using a hash unit that production Trezor firmware does not let "
        f"applications use{{{{fn:tz-hw}}}}.\n"
        f"- **Open question:** how much faster the other wallets could sign.")
    return speed, faster


# ---------------------------------------------------------------- RP2350 footnotes

def rp_cm4_note():
    """Footnote text: c-fn-dsa's Cortex-M4 assembly on the RP2350 (the level-3 lattice
    variation, one core, n=100) against the integer emulation in Table D9b: per operation,
    the variation's mean time over the table's, for FN-DSA-512 and -1024."""
    _CUR[0] = "D9b"
    alt = S["rp"].get(("cm4", "B", 0, "lattice"))
    if not alt:
        return PENDING
    use(alt)
    out = dict()
    for o in ("keygen", "sign", "verify"):
        rs = []
        for st in ("fndsa512", "fndsa1024"):
            w = [r["wall_s"] for r in file_rows(alt) if r["op"] == f"{st}_{o}"]
            assert len(w) == 100, (st, o, len(w))
            rs.append(statistics.mean(w) / cell(*lat_key("rp", f"{LAT_LABEL[st]} {o}"))["value"])
        a, b = sorted(f"{x:.2f}" for x in rs)
        out[o] = a if a == b else f"{a} to {b}"
    return (f"On the RP2350, c-fn-dsa's Cortex-M4 assembly, which runs on the Cortex-M33 "
            f"through its DSP extension, signs with FN-DSA-512 and -1024 in {out['sign']} of "
            f"the integer emulation's time, verifies in {out['verify']}, and generates keys "
            f"in {out['keygen']} (level 3, one core, n=100), with outputs equal to the host "
            f"reference byte for byte. The tables keep the integer emulation, which every "
            f"board runs.")


def rp_l2_note():
    """Footnote text: the RP2350's level-2 two-core slowdown (Table D15b) and the check
    build with the hash-based and SHA-256 code in SRAM, compared over the same messages
    with the level-2 two-core log of Table D5."""
    _CUR[0] = HASH_TAB["rp"]
    slow = []
    for group, ops in HASH_GROUPS:
        for op, v, swn, lab in ops:
            if op.startswith(("slh_dsa", "sphincs40")) or (op.startswith("shrincs") and
                                                           v == "B"):
                a = cell(HASH_TAB["rp"], rkey(group, lab), hash_col_label("rp", 2, 0))
                c = cell(HASH_TAB["rp"], rkey(group, lab), hash_col_label("rp", 2, 1))
                slow.append(a["value"] / c["value"])
    assert max(slow) < 1, slow  # the text says two cores took longer
    hot = glob.glob(os.path.join(RP_DIR, "check", "rp2350-r4x-L2hot-B-dc1-r1-*.log"))
    assert len(hot) == 1, hot
    use(hot[0])
    h = [r for r in file_rows(hot[0]) if r["op"] == "slh_dsa_sign"]
    runs = set(r["run"] for r in h)
    assert runs == set((0, 1)), runs  # the text says "messages 0 and 1"
    main = [r for r in rp_rows(2, "B", 1, "r1", "slh_dsa_sign") if r["run"] in runs]
    assert len(main) == len(h) == len(runs), (len(main), len(h))
    mh = statistics.mean(r["wall_s"] for r in h)
    mm = statistics.mean(r["wall_s"] for r in main)
    return (f"On the RP2350 at level 2, two cores took longer than one for SLH-DSA-SHA2-128s, "
            f"SPHINCS+ 2^40, and SHRINCS-B signing and key generation (one-core time over "
            f"two-core time "
            f"{min(slow):.2f} to {max(slow):.2f}, Table D15b). A check build of the same "
            f"configuration with the hash-based and SHA-256 code in SRAM signed messages 0 "
            f"and 1 with SLH-DSA-SHA2-128s on two cores in a mean of {mh:.2f} s, against "
            f"{mm:.2f} s for the same messages in the level-2 build, whose code runs from flash "
            f"through a 16 KB cache both cores share. The tables report the level-2 build as "
            f"measured, with the SDK's default code placement.")


# ---------------------------------------------------------------- sizes and boards

def header_macros(path, block=None):
    """Integer #define values of a C header; block selects the #if, #elif, or #else
    branch whose condition (the rest of its line, stripped) equals it."""
    text = open(path).read()
    if block:
        parts = re.split(r"^#(?:if|elif|else|endif)\b(.*)$", text, flags=re.M)
        chosen = [parts[i + 1] for i in range(1, len(parts) - 1, 2)
                  if parts[i].strip() == block]
        assert len(chosen) == 1, (path, block)
        text = chosen[0]
    out = dict()
    for m in re.finditer(r"^#define\s+(\w+)\s+\(\(uint32_t\)(\d+)\)", text, flags=re.M):
        out[m.group(1)] = int(m.group(2))
    for m in re.finditer(r"^#define\s+(\w+)\s+(\d+)\s*$", text, flags=re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def fndsa_sig_size(logn):
    """FNDSA_SIGNATURE_SIZE(logn) evaluated from the macro in c-fn-dsa's fndsa.h."""
    text = open(os.path.join(ROOT, "third_party", "c-fn-dsa", "fndsa.h")).read()
    m = re.search(r"#define\s+FNDSA_SIGNATURE_SIZE\(logn\)\s*\\\n((?:.*\\\n)*.*)", text)
    expr = m.group(1).replace("\\\n", " ").replace("(logn)", str(logn))
    expr = re.sub(r"(\d+)u\b", r"\1", expr)
    assert re.fullmatch(r"[\d\s+\-*()<>]+", expr), expr
    return eval(expr)  # digits and arithmetic only, checked above


def check_sizes():
    """Signature sizes from the rows against the scheme code's constants; returns the
    SHRINCS stateful size rule for the footnote."""
    const = os.path.join(ROOT, "third_party", "jade-hbs", "main", "shrincs", "constants.h")
    common = header_macros(const)
    rule = dict()
    for v, blk in (("B", "defined(SHRINCS_B)"), ("L", "// SHRINCS_L")):
        mm = header_macros(const, blk)
        n, rlen = common["N"], common["R_LEN"]
        wots = rlen + 4 + mm["L"] * n
        base = n + wots
        rule[v] = dict(base=base, n=n, hsf=mm["HSF"], max=base + mm["HSF"] * n)
        sl = n + (rlen + (mm["K"] + mm["M_MAX"]) * n) + (wots + mm["HSL"] // mm["D"] * n) * mm["D"]
        for key, want in ((("shrincs_sign", v), base + n), (("shrincs_sign_stateless", v), sl)):
            got = SIZES.get(key)
            assert not got or got == set((want,)), (key, got, want)
    mh = open(os.path.join(ROOT, "third_party", "mldsa-native", "mldsa", "mldsa_native.h")).read()
    for ps in ("44", "65", "87"):
        want = int(re.search(rf"#define MLDSA{ps}_BYTES (\d+)", mh).group(1))
        for s in (f"mldsa{ps}_sign", f"mldsa{ps}_lowram_sign"):
            got = SIZES.get((s, "B"))
            assert not got or got == set((want,)), (s, got, want)
    for logn, s in ((9, "fndsa512_sign"), (10, "fndsa1024_sign")):
        got = SIZES.get((s, "B"))
        assert not got or got == set((fndsa_sig_size(logn),)), (s, got)
    return rule


def shrincs_q_note(rule):
    b, l = rule["B"], rule["L"]
    return (f"SHRINCS stateful signatures grow with the state counter: the q-th signature "
            f"from a key carries min(q, HSF) authentication nodes of {b['n']} bytes, so it "
            f"takes {b['base']:,} + {b['n']}q bytes under SHRINCS-B (HSF = {b['hsf']}, at "
            f"most {b['max']:,} bytes) and {l['base']:,} + {l['n']}q bytes under SHRINCS-L "
            f"(HSF = {l['hsf']}, at most {l['max']:,} bytes). Sources: "
            f"`third_party/jade-hbs/main/shrincs/constants.h` and `uxmss_auth_path()` in `uxmss.c`. The "
            f"benchmark signs with q = 1 (`harness/common/op_shrincs.c`), the size shown.")


def heap_text(env):
    """Free heap before a job set at levels 1 and 3, to the nearest thousand bytes (it
    varies by a few hundred bytes between job sets; docs/environments/ gives the
    ranges)."""
    k = dict((l, round(int(env[l]["heap_free_internal"]) / 1000)) for l in (1, 3))
    if k[1] == k[3]:
        return f"about {k[1]:,},000 bytes at levels 1 and 3"
    return f"about {k[1]:,},000 bytes at level 1 and {k[3]:,},000 at level 3"


def t_boards():
    """Boards: chip, cores, and clock from the ESP32 logs' #env lines and the Pi Zero's
    clock checks; RAM as the summaries record it. Also fills S["boards"] (processor and
    clock per board) for "What was tested". Rows follow BOARDS; the header carries the
    footnote that names the ESP32 development boards."""
    _CUR[0] = "Boards"
    rows = dict()
    S["boards"] = dict()
    words = dict((("1", "one"), ("2", "two")))
    env_pi = os.path.join(ENV_DIR, "pi0w.md")
    use(env_pi)
    use(os.path.join(raw_dir("pi0w", "r2"), "clock_checks.txt"))
    summ = open(env_pi).read()
    ram = re.search(r"([\d,]+) KiB of RAM visible to Linux", summ).group(1)
    cpu = re.search(r"(ARM1176JZF-S)", summ).group(1)
    mhz = []
    for ln in open(os.path.join(raw_dir("pi0w", "r2"), "clock_checks.txt")):
        mhz += [int(x) for x in re.findall(r"compress(?:_soft)?,\d+,\d+,[\d.]+,[\d.]+,\d+,(\d+)",
                                           ln)]
    S["boards"]["pi"] = dict(proc=f"BCM2835, one {cpu} core", clock="1 GHz",
                             chip_clock="ARM1176, 1 GHz", title="Pi Zero (ARM1176, 1 GHz)")
    rows["pi"] = ["Pi Zero", f"BCM2835, one {cpu} core", "1 GHz"
                  + (f" (cycle-counter checks: {min(mhz):,} to {max(mhz):,} MHz)" if mhz else "")
                  + ", set with `force_turbo=1`, as in SeedSigner OS's Pi Zero image",
                  f"{ram} KiB visible to Linux"]
    # Pi Zero 2 W: the 1 GHz environment record (cpuinfo, MemTotal) and the run's clock
    # checks; the chip name is the board's environment file's.
    env = sorted(glob.glob(os.path.join(R4_DIR, "environment-*-1ghz-before.txt")))[-1]
    summ4 = os.path.join(ENV_DIR, "pi02w.md")
    for p in (env, summ4, os.path.join(R4_DIR, "clock_checks.txt")):
        use(p)
    # the 600 MHz record and the record taken after the run, cited by the environment file
    use(os.path.join(R4_DIR, "environment-*.txt"))
    text = open(env).read()
    chip = re.search(r"\b(BCM2710A1)\b", open(summ4).read()).group(1)
    ncpu = len(re.findall(r"^processor\s*:", text, flags=re.M))
    feats = re.search(r"^Features\s*:(.*)$", text, flags=re.M).group(1).split()
    assert "neon" in feats and "sha2" not in feats, feats
    assert "v7l" in text, "expected the 32-bit (ARMv7 state) kernel"
    ram2 = int(re.search(r"^MemTotal:\s+(\d+) kB", text, flags=re.M).group(1))
    mhz = []
    for ln in open(os.path.join(R4_DIR, "clock_checks.txt")):
        mhz += [int(x) for x in re.findall(r"compress(?:_soft)?,\d+,\d+,[\d.]+,[\d.]+,\d+,(\d+)",
                                           ln)]
    proc = f"{chip}, {NUM_WORD[ncpu]} Cortex-A53 cores, run in 32-bit mode"
    S["boards"]["pi2"] = dict(proc=proc, clock="1 GHz", chip_clock="Cortex-A53, 1 GHz",
                              title="Pi Zero 2 W (Cortex-A53, 1 GHz)")
    span = (f"{min(mhz):,} MHz" if min(mhz) == max(mhz) else f"{min(mhz):,} to {max(mhz):,} MHz")
    rows["pi2"] = ["Pi Zero 2 W", proc + "; NEON, no SHA-256 instructions",
                   "1 GHz" + (f" (cycle-counter checks: {span})" if mhz else "")
                   + ", set with `force_turbo=1`{{fn:pi2-clock}}",
                   f"{ram2:,} KiB visible to Linux (512 MB on the board)"]
    for b in ESP_BOARDS:
        env = dict()
        for lvl in (1, 3):
            path = esp_path(2, b, lvl, "B", 0, "verify", n=10)
            use(path)
            for ln in open(path, errors="replace"):
                if ln.startswith("#env,"):
                    env[lvl] = dict(x.split("=", 1) for x in ln.strip().split(",")[1:]
                                    if "=" in x)
        e = env[3]
        heap = heap_text(env)
        brief = f"chip revision {e['chip_rev']}, {words.get(e['cores'], e['cores'])} cores"
        proc = f"{e['target'].upper().replace('ESP32', 'ESP32-')} ({brief.replace(', ', '), ', 1)}"
        S["boards"][b] = dict(proc=proc, brief=brief, clock=f"{e['cpu_mhz']} MHz",
                              chip_clock=f"{BOARD_NAME[b]}, {e['cpu_mhz']} MHz",
                              title=f"{BOARD_NAME[b]} ({e['cpu_mhz']} MHz)")
        rows[b] = [BOARD_NAME[b], proc, f"{e['cpu_mhz']} MHz",
                   f"internal heap free before a job set: {heap}"]
    # RP2350: package, chip revision, cores, clock, flash clock divider, and free heap
    # from its logs' #env lines (package QFN60 is the RP2350A); SRAM, flash size, and the
    # XIP cache as its environment file records them.
    use(os.path.join(ENV_DIR, "rp2350.md"))
    env = dict()
    for lvl in (1, 3):
        path = S["rp"][(lvl, "B", 0, "verify")]
        use(path)
        for ln in open(path, errors="replace"):
            if ln.startswith("#env,"):
                env[lvl] = dict(x.split("=", 1) for x in ln.strip().split(",")[1:]
                                if "=" in x)
                break
    e = env[3]
    assert e["target"] == "rp2350" and e["package"] == "QFN60", e
    mhz = e["cpu_mhz"]
    flash_mhz = int(mhz) / int(e["flash_clkdiv"])
    heap = heap_text(env)
    proc = (f"RP2350A (chip revision {e['chip_rev']}), {words.get(e['cores'], e['cores'])} "
            f"Arm Cortex-M33 cores used (its two Hazard3 RISC-V cores are not); one SHA-256 "
            f"accelerator, shared by both cores, that cannot resume from a saved state")
    S["boards"]["rp"] = dict(proc=proc, brief="two Arm Cortex-M33 cores", clock=f"{mhz} MHz",
                             chip_clock=f"Cortex-M33, {mhz} MHz",
                             title=f"RP2350 (Cortex-M33, {mhz} MHz)")
    rows["rp"] = ["RP2350", proc, f"{mhz} MHz (the SDK default)",
                  f"520 KB of SRAM, no PSRAM; FreeRTOS heap free before a job set: {heap}; "
                  f"16 MiB of QSPI flash at {flash_mhz:g} MHz behind a 16 KB XIP cache"]
    return table(["Board{{fn:boards}}", "Processor", "Clock", "RAM"],
                 [rows[b] for b in BOARDS])


def tested_schemes():
    """The scheme cells of "What was tested", each with its signature size (a property of
    the parameter set, from the rows' out_bytes, cross-checked by check_sizes()). Returns
    (hash-based cell, lattice cell)."""
    def n(op, v="B"):
        return size_text((op, v)).replace(" bytes", "")
    hb = "<br>".join((
        f"SLH-DSA-SHA2-128s: {n('slh_dsa_sign')}-byte signatures",
        f"SPHINCS+ 2^40: {n('sphincs40_sign')} bytes",
        f"SHRINCS-B and SHRINCS-L (an earlier SHRINCS design{{{{fn:shrincs-draft}}}}), "
        f"stateful: {n('shrincs_sign')} and "
        f"{n('shrincs_sign', 'L')} bytes{{{{fn:shrincs-q}}}}",
        f"SHRINCS-B and SHRINCS-L, stateless: {n('shrincs_sign_stateless')} and "
        f"{n('shrincs_sign_stateless', 'L')} bytes",
        f"XMSS 2^10: {n('xmss_sign')} bytes",
        "implementation: Blockstream's code in the Jade fork (jade-hbs @ f5c90a5e), with "
        "two build-time edits (methods page, Implementations and inputs)"))
    lat = "<br>".join((
        f"ML-DSA-44, -65, and -87: {n('mldsa44_sign')}, {n('mldsa65_sign')}, and "
        f"{n('mldsa87_sign')} bytes; mldsa-native v2.0.0, default and reduced-RAM "
        f"configurations",
        f"FN-DSA-512 and -1024: {n('fndsa512_sign')} and {n('fndsa1024_sign')} "
        f"bytes{{{{fn:fndsa-standard}}}}; c-fn-dsa @ 1b858880"))
    return hb, lat


def tested_boards():
    """The Boards cell of "What was tested": one line per board (the ESP32 boards' chip
    name is not repeated after the board name)."""
    return "<br>".join(f"{BOARD_NAME[b]}: {S['boards'][b].get('brief', S['boards'][b]['proc'])}, "
                       f"{S['boards'][b]['clock']}"
                       + (" (results pending)" if b == "rp" and not RP2350_DATA else "")
                       for b in BOARDS)


# ---------------------------------------------------------------- status, notes, sources

def r3_expected():
    """Round-3 jobs this generator looks for: (board, level, variant, set or op)."""
    out = []
    for lvl in LEVELS:
        for op, v, swn, lab in VERIFY_OPS:
            out.append(("pi", lvl, v, op))
    for lvl in (1, 3):
        for s, _ in LATTICE_SETS:
            for o in ("keygen", "sign", "verify"):
                out.append(("pi", lvl, "B", f"{s}_{o}"))
    for b in ("p4", "s3"):
        for lvl in LEVELS:
            for v in ("B", "L"):
                out.append((b, lvl, v, "verify"))
        for lvl in (1, 3):
            out.append((b, lvl, "B", "lattice"))
    return out


def pause_note():
    """Methods text: the vTaskDelay(1) pauses in Jade's WOTS+C grinding loops. On one core
    the loop pauses once at counter 0 and once per 100,000 counter values; each pause
    lasts until the next 10 ms tick (100 Hz), between 0 and 10 ms. An estimate from the
    expected attempt count, set against the microcontrollers' level-3 one-core figures."""
    e = FIT.e_wots("L", 140)
    calls = 1 + e / 100000
    shares = []
    for b in MCU_BOARDS:
        c = cell(*hash_sign_key(b, "SHRINCS-L, stateful, swn=140 (expected)"))
        if c["value"] is None:
            continue
        shares.append((b, c["value"]))
    fast = min(shares, key=lambda x: x[1])
    slow = max(shares, key=lambda x: x[1])
    lo_s, hi_s = calls * 0.005, calls * 0.010
    return (f"Jade's WOTS+C grinding loops call `vTaskDelay(1)`: on one core once at the "
            f"start and once every 100,000 counter values, and in the two-core code once every "
            f"100,000 counter values on the second core. On the ESP32 boards and the RP2350 "
            f"each call waits for the next FreeRTOS tick (100 Hz), between 0 and 10 ms, and "
            f"that wait is inside the timed call; on the Pi boards the call does nothing "
            f"(`harness/linux/shim/freertos/task.h`). An estimate, not a measurement: "
            f"SHRINCS-L stateful signing at swn=140 needs {e:,.0f} attempts on average, so "
            f"about {calls:.0f} pauses per message on one core, about "
            f"{lo_s:.1f} to {hi_s:.1f} s, which is {lo_s / slow[1] * 100:.1f} to "
            f"{hi_s / fast[1] * 100:.1f}% of the microcontrollers' level-3 one-core figures "
            f"({BOARD_NAME[fast[0]]} fastest, {BOARD_NAME[slow[0]]} slowest). Stateless signing "
            f"grinds WOTS+C at two layers, so it pauses about twice as often, a smaller share of "
            f"its much longer time; SHRINCS-B's grinding at swn=2040 needs too few attempts to "
            f"pause more than once.")


def correctness():
    """scripts/check_r2.py over every round-2 Pi Zero file, every complete round-2
    ESP32 log, every complete round-3 file, every Pi Zero 2 W file, and every complete
    RP2350 log this generator found (the lattice variation's included)."""
    files = sorted(p for k, p in S["pi"].items() if k[0] == 2)
    files += sorted(p for k, (s, p) in S["esp"].items() if k[0] == 2)
    r3 = sorted(p for k, p in S["pi"].items() if k[0] == 3)
    r3 += sorted(p for k, (s, p) in S["esp"].items() if k[0] == 3)
    r4 = sorted(S["pi2"].values())
    rp = sorted(S["rp"].values())
    for p in files + r3 + r4 + rp:
        use(p)
    ref = HOST
    out = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "check_r2.py"),
                          "--ref", os.path.join(ref, "reference-B.csv"),
                          "--ref", os.path.join(ref, "reference-L.csv")] + files + r3 + r4
                         + rp,
                         capture_output=True, text=True).stdout.split("\n")
    total = [ln for ln in out if ln.startswith(("PASS", "FAIL:"))]
    dual = [ln for ln in out if "dual-core, allowed" in ln]
    ndiff = sum(int(re.search(r"(\d+) differ", ln).group(1)) for ln in dual)
    npi = len([f for f in files if f.endswith(".csv")])
    # The differing two-core rows by their verified column: the gate requires
    # verification only where a consistent key and the specified target sum allow it
    # (self-tests, stateless signing, SHRINCS-L at swn=140).
    ref_out = dict()
    for p in ("reference-B.csv", "reference-L.csv"):
        for r in FIT.rows(os.path.join(ref, p)):
            v = FIT.variant(r["build"]) if r["op"].startswith("shrincs") else ""
            ref_out.setdefault((r["op"], v, r["swn"], r["run"]), r["out_sha256"])
    ver = collections.Counter()
    for p in files + r3 + r4 + rp:
        for r in file_rows(p):
            if not FIT.is_dual(r["build"]):
                continue
            v = FIT.variant(r["build"]) if r["op"].startswith("shrincs") else ""
            o = ref_out.get((r["op"], v, r["swn"], r["run"]))
            if o is not None and o != r["out_sha256"]:
                ok = r["verified"] == "1"
                ver[ok] += 1
                kind = (r["op"], v, r["swn"])
                assert (r["op"] in ("shrincs_selftest", "shrincs_sign_stateless") if ok else
                        kind in (("shrincs_sign", "B", "2040"), ("shrincs_sign", "L", "96"))), \
                    (kind, r["verified"])
    assert ver[True] + ver[False] == ndiff, (ver, ndiff)
    r3txt = (f", {len(r3)} third-round jobs and job sets," if r3 else
             ", no third-round job,")
    m = re.match(r"PASS: (\d+)/(\d+) rows pass", total[-1]) if total else None
    verdict = (f"{int(m.group(1)):,} of {int(m.group(2)):,} rows pass" if m else
               (total[-1] if total else "no result"))
    return (f"`scripts/check_r2.py` against the host reference outputs over every "
            f"second-round job used here ({npi} Pi Zero jobs and "
            f"{len(files) - npi} complete ESP32 job sets){r3txt} the {len(r4)} fourth-round "
            f"Pi Zero 2 W jobs, and the {len(rp)} fourth-round RP2350 job sets used: "
            f"{verdict}. Every output equals the host's byte for "
            f"byte except {ndiff} two-core SHRINCS signatures in {len(dual)} job groups, where "
            f"Blockstream's dual-core grinding returned a different counter. {ver[True]} of "
            f"them (self-tests and stateless signing) verified; the other {ver[False]} are "
            f"SHRINCS-B stateful signatures made with the fixed key and SHRINCS-L signatures "
            f"at swn=96, which cannot be verified (independent verification, below).")


def openssl_note():
    """The second round's host reference against OpenSSL 3.5.7: SLH-DSA-SHA2-128s output
    hashes and the ML-DSA check (results/verification/, local only)."""
    _CUR[0] = "Appendix"
    ref = os.path.join(HOST, "reference-B.csv")
    oss = os.path.join(RES, "verification", "openssl_slh_dsa_sha2_128s_hashes.csv")
    mld = os.path.join(RES, "verification", "check_mldsa_openssl.txt")
    for p in (ref, oss, mld):
        use(p)
    host = dict()
    with open(ref) as f:
        for r in csv.DictReader(f):
            host[(r["op"], int(r["run"]))] = r["out_sha256"]
    same = collections.Counter()
    differ = 0
    with open(oss) as f:
        for r in csv.DictReader(f):
            k = (r["op"], int(r["run"]))
            if k in host:
                if host[k] == r["out_sha256"]:
                    same[r["op"]] += 1
                else:
                    differ += 1
    lines = open(mld).read().split("\n")
    ok = [ln for ln in lines if re.match(r"ML-DSA-\d+: public key matches; (\d+)/\1 signatures "
                                         r"identical to OpenSSL's; (\d+)/\2 verified", ln)]
    nsig = sum(int(re.search(r"(\d+)/\d+ signatures", ln).group(1)) for ln in ok)
    slh = (f"the second round's host reference outputs for SLH-DSA-SHA2-128s "
           f"({same['slh_dsa_sign']} signatures and {same['slh_dsa_keygen']} keys) equal "
           f"OpenSSL's" + (f", except {differ}" if differ else ""))
    ml = (f"OpenSSL 3.5.7 derives the same public keys and byte-identical "
          f"deterministic signatures for all {nsig} messages checked ({len(ok)} parameter "
          f"sets, messages 0 to 99) and verifies them")
    return slh, ml


def layout_data():
    """Pi Zero level-2 process-to-process spread (layout diagnostic,
    results/raw/pi0w/r2/diagnostics/)."""
    d = os.path.join(raw_dir("pi0w", "r2"), "diagnostics")

    def per_process(name):
        rs = [r for r in SUMM.read_rows(os.path.join(d, name))]
        use(os.path.join(d, name))
        cpu = [float(r["cpu_s"]) for r in rs]
        return [statistics.mean(cpu[i:i + 2]) for i in range(0, len(cpu), 2)]

    kg = per_process("r2L2-xmss_keygen.csv")
    r1l2 = per_process("r1L2-xmss_sign.csv")
    r1l3 = per_process("r1L3-xmss_sign.csv")
    r2l3 = per_process("r2L3-xmss_sign.csv")
    base2 = statistics.mean(float(r["cpu_s"]) for r in r1_rows(PI_R1[2], "xmss_sign", "B", ""))
    base3 = statistics.mean(float(r["cpu_s"]) for r in r1_rows(PI_R1[3], "xmss_sign", "B", ""))
    return kg, r1l2, r1l3, r2l3, base2, base3


def layout_note(data):
    kg, r1l2, r1l3, r2l3, base2, base3 = data

    def pct(x):
        return "less than 0.01%" if abs(x) < 0.01 else f"{abs(x):.2f}%"

    d2 = (statistics.mean(r1l2) / base2 - 1) * 100
    d3 = (statistics.mean(r1l3) / base3 - 1) * 100
    procs = (f"{len(r1l2)} processes each" if len(r1l2) == len(r1l3) else
             f"{len(r1l2)} and {len(r1l3)} processes")
    return (f"XMSS 2^10 key generation took {min(kg):.3f} to {max(kg):.3f} s of CPU time in "
            f"{len(kg)} processes of the same level-2 binary "
            f"({(max(kg) / min(kg) - 1) * 100:.1f}% apart). The first round's level-2 and "
            f"level-3 binaries, run again in {procs}, signed XMSS 2^10 within {pct(d2)} and "
            f"{pct(d3)} of their first-round mean CPU times. The second round's level-3 "
            f"binary signed XMSS 2^10 in {min(r2l3):.4f} to {max(r2l3):.4f} s of CPU time in "
            f"{len(r2l3)} processes, {(statistics.mean(r2l3) / base3 - 1) * 100:+.1f}% "
            f"against the first round's {base3:.4f} s, so that difference belongs to the new "
            f"binary.")


def layout_fn(data):
    kg = data[0]
    return (f"The Pi Zero's level-2 build runs at a speed that depends on the process: "
            f"XMSS 2^10 key generation took {min(kg):.3f} to {max(kg):.3f} s of CPU time in "
            f"{len(kg)} processes of one binary ({(max(kg) / min(kg) - 1) * 100:.1f}% apart), "
            f"and a 100-run job is one process, so its standard deviation leaves this "
            f"component out (Table D16a and the text after it).")


def write_csvs():
    """Writes results/derived/<name>.csv per CSV_ROWS entry; returns name -> Markdown link
    (relative to results/, where the draft lives)."""
    os.makedirs(S["csv_dir"], exist_ok=True)
    links = collections.OrderedDict()
    for name, rows in CSV_ROWS.items():
        if not rows:
            continue
        path = os.path.join(S["csv_dir"], f"{name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
        rp = os.path.relpath(path, ROOT)
        links[name] = f"[`{rp}`]({os.path.relpath(path, RES)})"
    return links


def l140_m10():
    """Mean WOTS+C attempts of messages 0 to 9 at swn=140, from the file of the Pi Zero's
    level-3 cell (the same messages on every board)."""
    c = cell(HASH_TAB["pi"], rkey("Signing", "SHRINCS-L, stateful, swn=140 (expected)"),
             hash_col_label("pi", 3))
    rs = [r for r in file_rows(c["src"]) if r["op"] == "shrincs_sign" and r["swn"] == "140"
          and r["run"] < 10]
    return f"{statistics.mean(FIT.grind(r)['wots'] + 1 for r in rs):,.0f}"


def pending_summary():
    by_tab = collections.Counter()
    by_flag = collections.Counter()
    for k, (tab, row, col, flag) in PEND.items():
        by_tab[tab] += 1
        by_flag[flag] += 1
    return by_tab, by_flag


def draft_status():
    by_tab, by_flag = pending_summary()
    if not PEND:
        return ("Generated by `scripts/report/fill.py` from the run logs; edit the template "
                "and the scripts, not this file.")
    parts = []
    if by_flag[R2_MARK]:
        parts.append(f"{by_flag[R2_MARK]} detail-table figures show the second round's value, "
                     f"marked {R2_MARK}")
    if by_flag[PENDING]:
        parts.append(f"{by_flag[PENDING]} read \"pending\"")
    return (f"Draft generated by `scripts/report/fill.py` from the raw files; not for "
            f"publication. Round 3 (verification and lattice reruns at 1 µs print resolution) "
            f"is not complete: " + " and ".join(parts) + " (Tables "
            + ", ".join(f"{t}: {n}" for t, n in sorted(by_tab.items()))
            + "). The next rebuild after round 3 fills them in.")


# ---------------------------------------------------------------- build

def build(L2, csv_dir=None):
    """Returns an ordered dict of placeholder name -> Markdown."""
    init(csv_dir)
    T = collections.OrderedDict()
    # Detail tables first: K1 and C1 quote them.
    for b in BOARDS:
        T[HASH_TAB[b]] = t_hash_board(HASH_TAB[b], b)
    T["HASH_RANGE"] = f"{HASH_TAB[BOARDS[0]]} to {HASH_TAB[BOARDS[-1]]}"
    T["D15_FROM"] = table_list([HASH_TAB[b] for b in DUAL_BOARDS] + ["D7"])
    T["D6"] = t_level_ratio_hash()
    T["D7"], st = t_stateless()
    for k, v in st.items():
        T[f"D7_{k.upper()}"] = v
    T["H4"] = t_blockstream(L2)
    T["D8a"] = t_verify("D8a", PI_BOARDS)
    T["D8b"] = t_verify("D8b", MCU_BOARDS)
    T["FN_VERIFY_DC"] = verify_dc_note()
    T["D9a"] = t_lattice("D9a", PI_BOARDS)
    T["D9b"] = t_lattice("D9b", MCU_BOARDS)
    T["FN_MLDSA_NOTE"], T["FN_FNDSA_SIGN"] = mldsa_note()
    T["D10"] = t_fndsa_keygen()
    T["FN_FNDSA_SEED"] = fndsa_seed_note()
    T["D13a"] = t_memory("D13a", PI_BOARDS)
    T["D13b"] = t_memory("D13b", MCU_BOARDS)
    T["D14a"] = t_memory_max("D14a", PI_BOARDS)
    T["D14b"] = t_memory_max("D14b", MCU_BOARDS)
    T["D11a"] = t_reduced_ram("D11a", PI_BOARDS)
    T["D11b"] = t_reduced_ram("D11b", MCU_BOARDS)
    T["D12"] = t_level_ratio_lattice()
    T["FN_S3_LATTICE"] = s3_level1_note()
    T["D15a"] = t_two_cores("D15a", tuple(b for b in DUAL_BOARDS if b in PI_BOARDS))
    T["D15b"] = t_two_cores("D15b", tuple(b for b in DUAL_BOARDS if b in MCU_BOARDS))
    for b, k in (("pi", "a"), ("p4", "b"), ("s3", "c")):
        T[f"D16{k}"], T[f"D16{k}_SUM"] = t_repro(b, f"D16{k}")
    T["FN_P4_SHIFT"] = p4_shift_note()
    _CUR[0] = "D16a"
    ld = layout_data()
    T["D9_LAYOUT"] = layout_note(ld)
    T["FN_LAYOUT"] = layout_fn(ld)
    rule = check_sizes()
    T["FN_SHRINCS_Q"] = shrincs_q_note(rule)
    T["BOARDS"] = t_boards()
    T["TESTED_BOARDS"] = tested_boards()
    T["HASH_TABLES"] = hash_tables(T)
    T["FN_PI2_CLOCK"] = pi2_clock()
    T["FN_RP_CM4"] = rp_cm4_note()
    T["FN_RP_L2DC"] = rp_l2_note()
    T["K1"], T["K1_NOTE"] = k1()
    T["TESTED_HASH"], T["TESTED_LATTICE"] = tested_schemes()
    T["H5"] = t_compare()
    T["C1"], T["FN_C1_METHOD"] = t_rank()
    T["DISC_SPEED"], T["DISC_FASTER"] = discussion(L2)
    _CUR[0] = "Appendix"
    use(os.path.join(HOST, "reference-B.csv"))
    use(os.path.join(HOST, "reference-L.csv"))
    T["CORRECTNESS"] = correctness()
    T["TIMING_PAUSES"] = pause_note()
    T["OPENSSL_SLH"], T["OPENSSL_MLDSA"] = openssl_note()
    T["L140_M10"] = l140_m10()
    T["E_WOTS_L140"] = f"{FIT.e_wots('L', 140):,.0f}"
    e = FIT.MLDSA_E_LIB
    T["MLDSA_E"] = f"{e['44']}, {e['65']}, and {e['87']}"
    links = write_csvs()
    T["CSV_FILES"] = " and ".join(links.values())
    T["CSV_STATELESS"] = links.get("stateless_fit", PENDING)
    T["CSV_MLDSA"] = links.get("mldsa_fit", PENDING)
    T["DRAFT_STATUS"] = draft_status()
    return T
