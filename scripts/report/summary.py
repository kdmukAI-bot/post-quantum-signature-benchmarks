"""results/summary.csv and results/raw/MANIFEST.csv. fill.py calls write() after the
tables are built, so both files come from the same loaded data as the report:

- summary.csv has one row per measured configuration that a table reads: (round, device,
  level, safeguards, variant, cores, operation, swn). Rounds 2 to 4 come from the
  generator's record of every cell it filled (round2.SUMMARY_LOG); the first round comes
  from levels2.py's files (the reproducibility comparison and the cost of safeguards) and
  the Jade firmware runs.
- MANIFEST.csv lists every file under results/raw/ with its device, round, parsed job
  fields, size, SHA-256, and the tables or report sections that read it.

Both are written, never edited by hand. The run logs under results/raw/ and the manifest
are local only (not in the repository); summary.csv is published."""
import collections
import csv
import glob
import hashlib
import os
import re
import statistics

JADE = "jade-hbs@f5c90a5e"
MLDSA = "mldsa-native@834a90d5"
FNDSA = "c-fn-dsa@1b858880"
SUMMARY_COLS = [
    "round", "device", "level", "safeguards", "family", "scheme", "parameter_set",
    "implementation", "operation", "variant", "swn", "cores", "n", "inputs", "statistic",
    "value_s", "mean_s", "median_s", "min_s", "max_s", "sd_s", "cpu_mean_s", "expected_s",
    "expected_se_s", "fit_model", "fit_e", "fit_max_residual_s", "stack_peak_bytes",
    "heap_peak_bytes", "memory_source", "memory_n", "verified", "matches_host"]
MANIFEST_COLS = ["path", "device", "round", "level", "variant", "cores", "job",
                 "n", "bytes", "sha256", "used_by"]


def scheme_of(op):
    """(family, scheme, parameter set, implementation, operation) of a harness op name."""
    m = re.match(r"(mldsa|fndsa)(\d+)(_lowram)?_(\w+)$", op)
    if m:
        if m.group(1) == "mldsa":
            impl = MLDSA + (" reduced-ram" if m.group(3) else "")
            return "lattice", "ML-DSA", m.group(2), impl, m.group(4)
        return "lattice", "FN-DSA", m.group(2), FNDSA, m.group(4)
    for prefix, scheme, ps in (("slh_dsa", "SLH-DSA", "SHA2-128s"),
                               ("sphincs40", "SPHINCS+", "2^40"),
                               ("shrincs", "SHRINCS", None), ("xmss", "XMSS", "2^10")):
        if op.startswith(prefix + "_"):
            return "hash-based", scheme, ps, JADE, op[len(prefix) + 1:]
    raise ValueError(op)


def fmt(x, nd=6):
    return "" if x is None else f"{x:.{nd}f}"


def run_ranges(runs):
    runs = sorted(set(runs))
    out = []
    start = prev = runs[0]
    for r in runs[1:] + [None]:
        if r is not None and r == prev + 1:
            prev = r
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if r is not None:
            start = prev = r
    return ",".join(out)


def verified_of(rs):
    v = [r.get("verified", "") for r in rs]
    ok = sum(1 for x in v if x == "1")
    if ok == len(v):
        return "all"
    return "n/a" if ok == 0 else f"{ok} of {len(v)}"


class Host:
    """The x86-64 host's reference outputs (results/raw/host/r2/reference-<B|L>.csv)."""

    def __init__(self, r2, fit):
        self.ref = dict()
        for v in ("B", "L"):
            for r in fit.rows(os.path.join(r2.HOST, f"reference-{v}.csv")):
                self.ref[(v, r["op"], r["swn"], r["run"])] = r["out_sha256"]

    def matches(self, rs, v, cores, op):
        vv = v or "B"
        pairs = [(r["out_sha256"], self.ref.get((vv, r["op"], r["swn"], r["run"])))
                 for r in rs if r.get("out_sha256")]
        pairs = [(a, b) for a, b in pairs if b]
        if not pairs:
            return "n/a"
        if all(a == b for a, b in pairs):
            return "yes"
        if cores == 2 and op.startswith("shrincs_sign"):
            return "dual-core-differs"
        return f"no ({sum(1 for a, b in pairs if a != b)} of {len(pairs)} differ)"


def plain_stats(rs):
    w = [r["wall_s"] for r in rs]
    cpu = []
    for r in rs:
        try:
            cpu.append(float(r.get("cpu_s", "")))
        except ValueError:
            pass
    return dict(mean_s=fmt(statistics.mean(w)), median_s=fmt(statistics.median(w)),
                min_s=fmt(min(w)), max_s=fmt(max(w)),
                sd_s=fmt(statistics.stdev(w)) if len(w) > 1 else "",
                cpu_mean_s=fmt(statistics.mean(cpu)) if len(cpu) == len(w) else "")


def summary_rows(r2, L2, fit):
    host = Host(r2, fit)
    res = r2.RES
    rows = collections.OrderedDict()

    def row_for(rnd, device, level, safeguards, op, v, swn, cores):
        family, scheme, ps, impl, operation = scheme_of(op)
        if family == "lattice":
            v = ""  # lattice code is the same in both SHRINCS builds
        if scheme == "SHRINCS":
            ps = v
        key = (rnd, device, str(level), safeguards, v, cores, op, swn)
        if key not in rows:
            rows[key] = dict((c, "") for c in SUMMARY_COLS)
            rows[key].update(round=rnd, device=device, level=level, safeguards=safeguards,
                             family=family, scheme=scheme, parameter_set=ps,
                             implementation=impl, operation=operation, variant=v,
                             swn=swn, cores=cores)
            rows[key]["_src"] = []
        return rows[key], v

    def add_timing(row, rs, v, cores, op, path):
        if row["n"]:
            return
        row.update(plain_stats(rs))
        row.update(n=len(rs), inputs=run_ranges(r["run"] for r in rs),
                   statistic=row["statistic"] or "mean",
                   verified=verified_of(rs), matches_host=host.matches(rs, v, cores, op))
        if row["statistic"] == "mean":
            row["value_s"] = row["mean_s"]
        row["_src"].append(path)

    for kind, board, level, op, v, swn, dc, rnd, path, rs, f in r2.SUMMARY_LOG:
        device = r2.DEVICE[board]
        cores = dc + 1
        swn = rs[0]["swn"] if op.startswith("shrincs") else ""
        row, vv = row_for(f"r{rnd}", device, level, "default", op, v, swn, cores)
        if kind == "time":
            add_timing(row, rs, vv, cores, op, path)
        elif kind == "fit":
            add_timing(row, rs, vv, cores, op, path)
            row.update(statistic="expected", value_s=fmt(f["expected"]),
                       expected_s=fmt(f["expected"]), expected_se_s=fmt(f["se"]),
                       fit_model=f["model"], fit_e=f["e"], fit_max_residual_s=fmt(f["resid"]))
        elif kind == "mem":
            st = [int(r["stack_peak_bytes"]) for r in rs if r.get("stack_peak_bytes")]
            hp = [int(r["heap_peak_bytes"]) for r in rs if r.get("heap_peak_bytes")]
            row.update(stack_peak_bytes=max(st) if st else "",
                       heap_peak_bytes=max(hp) if hp else "",
                       memory_source="memory-build" if board in ("pi", "pi2") else "timing-run",
                       memory_n=len(rs))
            if path not in row["_src"]:
                row["_src"].append(path)

    # first round: levels2's files, named <board>_<setting>
    first = dict((("pi_L1", ("pi0w", 1, "default", 1)), ("pi_L2", ("pi0w", 2, "default", 1)),
                  ("pi_L3", ("pi0w", 3, "default", 1)),
                  ("pi_L3_ssp_static", ("pi0w", 3, "static-ssp", 1)),
                  ("pi_L3_nossp_static", ("pi0w", 3, "static-nossp", 1))))
    for b in ("p4", "s3"):
        for lvl in (1, 2, 3):
            for c in (1, 2):
                first[f"{b}_L{lvl}c{c}"] = (f"esp32{b}", lvl, "default", c)
        for c in (1, 2):
            first[f"{b}_ssp_L3c{c}"] = (f"esp32{b}", 3, "ssp", c)
    for name, (device, lvl, safeguards, cores) in first.items():
        for (op, v, swn), rs in sorted(L2.rows_of.get(name, dict()).items()):
            row, vv = row_for("r1", device, lvl, safeguards, op, v, swn, cores)
            add_timing(row, rs, vv, cores, op, os.path.join(r2.ROOT, rs[0]["path"]))
            if op == "shrincs_sign" and v == "L" and swn == "140" and name in L2.swn140:
                x = L2.swn140[name]
                row.update(statistic="expected", value_s=fmt(x), expected_s=fmt(x),
                           fit_model="shrincs-l stateful, first-round fit "
                                     "(scripts/grind_fit_csv.py, scripts/grind_fit_logs.py)",
                           fit_e="swn=140")
    jade = collections.defaultdict(list)
    path = os.path.join(res, "jade_runs.csv")
    for r in csv.DictReader(open(path)):
        if r["seconds"]:
            jade[(r["op"], r["swn"])].append(dict(wall_s=float(r["seconds"]),
                                                  run=int(r["run"])))
    for (op, swn), rs in sorted(jade.items()):
        row, _ = row_for("r1", "jade-s3", "calibration", "default", op, "B", swn, 1)
        row.update(plain_stats(rs))
        row.update(n=len(rs), inputs=run_ranges(r["run"] for r in rs), statistic="mean",
                   verified="n/a", matches_host="n/a")
        row["value_s"] = row["mean_s"]
        row["_src"].append(path)

    out = []
    for row in rows.values():
        row.pop("_src")  # the run logs are local only, so the published table names none
        out.append(row)
    order = dict((d, i) for i, d in enumerate(("pi02w", "pi0w", "esp32p4", "esp32s3",
                                               "rp2350", "jade-s3")))
    out.sort(key=lambda r: (r["round"], order[r["device"]], str(r["level"]), r["safeguards"],
                            r["family"], r["scheme"], r["parameter_set"], r["operation"],
                            r["variant"], r["swn"], r["cores"]))
    return out


# ---------------------------------------------------------------- MANIFEST.csv

JOB_RES = [
    # round 2 and 3, Pi Zero: one op per file
    re.compile(r"^pi0w-r[23]-L(?P<level>\d)(?:-mem)?-shrincs(?P<variant>[BL])-.*?-"
               r"(?P<job>[a-z0-9_]+?)(?:-swn\d+)?-n(?P<n>\d+)-\d{8}_\d{6}\.csv$"),
    re.compile(r"^pi02w-r4-L(?P<level>\d)(?:-mem)?-shrincs(?P<variant>[BL])-.*?-"
               r"(?P<job>[a-z0-9_]+?)(?:-swn\d+)?-n(?P<n>\d+)-\d{8}_\d{6}\.csv$"),
    # ESP32 boards and the RP2350: one job set per log
    re.compile(r"^(?:s3|p4)-r[23]-L(?P<level>\d)-(?P<variant>[BL])-dc(?P<cores>[01])-"
               r"(?P<job>\w+?)-n(?P<n>\w+)-\d{8}_\d{6}\.log$"),
    re.compile(r"^rp2350-r4x?-L(?P<level>\d\w*?)-(?P<variant>[BL])-dc(?P<cores>[01])-"
               r"(?P<job>\w+?)-n(?P<n>\d+)-\d{8}_\d{6}\.log$"),
    # first round, ESP32 boards
    re.compile(r"^(?:s3|p4)-(?:opt-|optssp-)?(?P<variant>[BL])-\w+?-dc(?P<cores>[01])"
               r"(?:-\w+)?-r(?P<n>\d+)\.log$"),
]


def manifest_rows(r2, L2):
    res = r2.RES
    used = collections.defaultdict(set)
    for tab, paths in r2.SRC.items():
        for p in paths:
            p = os.path.join(r2.ROOT, p)
            for q in (sorted(glob.glob(p)) if glob.has_magic(p) else [p]):
                used[os.path.normpath(q)].add(tab)
    first_tabs = dict((("pi_L3", "D17a"), ("pi_L3_ssp_static", "D17a"),
                       ("pi_L3_nossp_static", "D17a"), ("s3_jade", "D18")))
    for b in ("p4", "s3"):
        for c in (1, 2):
            first_tabs[f"{b}_L3c{c}"] = "D17b"
            first_tabs[f"{b}_ssp_L3c{c}"] = "D17b"
    for name, tab in first_tabs.items():
        for p in L2.paths_of.get(name, []):
            used[os.path.normpath(os.path.join(r2.ROOT, p))].add(tab)
    # Read outside the generator: the first-round fits' host counters and reference
    # outputs (scripts/grind_fit_csv.py and grind_fit_logs.py, run by levels2.py) and the
    # host signatures the independent-verification scripts check.
    for pat, tab in (("host/r1/host-L-swn*.csv", "first-round fits"),
                     ("host/r1/host-sigs-L/*", "first-round fits"),
                     ("host/r1/host-sigs/*", "independent verification")):
        for q in glob.glob(os.path.join(r2.RAW, pat)):
            used[os.path.normpath(q)].add(tab)
    out = []
    for dp, dn, fs in os.walk(r2.RAW):
        dn.sort()
        for f in sorted(fs):
            if f == "MANIFEST.csv":
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, res)
            parts = os.path.relpath(path, r2.RAW).split(os.sep)
            fields = dict()
            for rx in JOB_RES:
                m = rx.match(f)
                if m:
                    fields = m.groupdict()
                    break
            h = hashlib.sha256(open(path, "rb").read()).hexdigest()
            cores = fields.get("cores")
            out.append(dict(
                path=rel, device=parts[0], round=parts[1] if len(parts) > 2 else "",
                level=fields.get("level", ""), variant=fields.get("variant", ""),
                cores=int(cores) + 1 if cores is not None else "",
                job=fields.get("job", ""), n=fields.get("n", ""),
                bytes=os.path.getsize(path), sha256=h,
                used_by=";".join(sorted(used.get(os.path.normpath(path), ())))))
    return out


def write(r2, L2, fit):
    """Writes both files; returns (summary rows, manifest rows)."""
    srows = summary_rows(r2, L2, fit)
    with open(os.path.join(r2.RES, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(srows)
    mrows = manifest_rows(r2, L2)
    with open(os.path.join(r2.RAW, "MANIFEST.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(mrows)
    return srows, mrows
