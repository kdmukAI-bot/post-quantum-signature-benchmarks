#!/usr/bin/env python3
"""
Summarize benchmark result files into one table.

Accepts any mix of:
  - pq_bench CSV (Linux/Pi):
    board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified
  - harness/esp-idf serial logs: the same columns plus
    stack_peak_bytes,heap_min_free_bytes, with '#env' lines and console noise around them
  - round-2 rows (pq_bench CSV and harness/esp-idf logs alike): the pq_bench columns plus
    stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind
  - run_jade_bench.py CSV: utc,board,build,op,swn,run,seconds,reply_bytes

Usage: summarize.py [--markdown] [--csv OUT] FILE...
Groups by (board, build, op, swn) and reports n, mean, median, min, max, sample standard
deviation, the number of distinct output hashes for run 0 across groups (as a check), and
whether every run in the group verified, plus the largest peak stack and peak heap use in
the group where the rows carry them.
"""
import argparse
import collections
import csv
import statistics
import sys

PQ_COLS = ["board", "build", "op", "swn", "run", "wall_s", "cpu_s", "out_bytes", "out_sha256",
           "verified"]
ESP_COLS = PQ_COLS + ["stack_peak_bytes", "heap_min_free_bytes"]
R2_COLS = PQ_COLS + ["stack_peak_bytes", "heap_peak_bytes", "heap_min_free_bytes", "grind"]


def read_rows(path):
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    lines = [ln.strip("\r") for ln in text.split("\n")]
    if lines and lines[0].startswith("utc,board,build,op,"):
        for r in csv.DictReader(lines):
            if not r.get("seconds"):
                continue
            yield {
                "board": r["board"], "build": r["build"] or "jade-firmware", "op": r["op"],
                "swn": r["swn"], "run": int(r["run"]), "wall_s": float(r["seconds"]),
                "out_bytes": int(r["reply_bytes"]), "out_sha256": "", "verified": "",
                "stack_peak_bytes": "", "heap_peak_bytes": "", "timing": "host",
            }
        return
    for ln in lines:
        if not ln or ln.startswith("#") or ln.startswith("board,"):
            continue
        parts = ln.split(",")
        cols = dict(((len(c), c) for c in (PQ_COLS, ESP_COLS, R2_COLS))).get(len(parts))
        if not cols:
            continue
        r = dict(zip(cols, parts))
        try:
            r["run"] = int(r["run"])
            r["wall_s"] = float(r["wall_s"])
        except ValueError:
            continue
        r.setdefault("stack_peak_bytes", "")
        r.setdefault("heap_peak_bytes", "")
        r["timing"] = "device"
        yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--csv", help="write the summary as CSV to this path")
    args = ap.parse_args()

    groups = collections.OrderedDict()
    for path in args.files:
        for r in read_rows(path):
            key = (r["board"], r["build"], r["op"], r["swn"])
            groups.setdefault(key, []).append(r)

    out = []
    for (board, build, op, swn), rs in groups.items():
        w = [r["wall_s"] for r in rs]
        ver = set(r["verified"] for r in rs)
        if ver == {"1"}:
            verified = "all"
        elif "0" in ver:
            verified = "FAILED"
        elif ver <= {"-1", ""}:
            verified = "n/a"
        else:
            verified = "/".join(sorted(ver))
        run0 = [r["out_sha256"] for r in rs if r["run"] == 0 and r["out_sha256"]]
        stack = [int(r["stack_peak_bytes"]) for r in rs if r.get("stack_peak_bytes")]
        heap = [int(r["heap_peak_bytes"]) for r in rs if r.get("heap_peak_bytes")]
        out.append({
            "board": board, "build": build, "op": op, "swn": swn, "timing": rs[0]["timing"],
            "n": len(w), "mean_s": statistics.mean(w), "median_s": statistics.median(w),
            "min_s": min(w), "max_s": max(w),
            "sd_s": statistics.stdev(w) if len(w) > 1 else 0.0,
            "run0_sha256": run0[0][:16] if run0 else "", "verified": verified,
            "stack_peak_bytes": max(stack) if stack else "",
            "heap_peak_bytes": max(heap) if heap else "",
        })

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            wr.writeheader()
            for row in out:
                wr.writerow(dict((k, f"{v:.4f}" if isinstance(v, float) else v)
                                 for k, v in row.items()))

    if args.markdown:
        print("| Board | Build | Operation | swn | Timing | n | Mean (s) | Median (s) | Min (s) | "
              "Max (s) | SD (s) | Run 0 SHA-256 | Verified | Peak stack (B) | Peak heap (B) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for o in out:
            print(f"| {o['board']} | {o['build']} | {o['op']} | {o['swn']} | {o['timing']} | "
                  f"{o['n']} | {o['mean_s']:.3f} | {o['median_s']:.3f} | {o['min_s']:.3f} | "
                  f"{o['max_s']:.3f} | {o['sd_s']:.3f} | {o['run0_sha256']} | {o['verified']} | "
                  f"{o['stack_peak_bytes']} | {o['heap_peak_bytes']} |")
    else:
        for o in out:
            print(f"{o['board']:10s} {o['build'][:40]:40s} {o['op']:24s} {o['swn']:>4s} "
                  f"n={o['n']:3d} mean={o['mean_s']:9.4f} sd={o['sd_s']:7.4f} "
                  f"{o['run0_sha256']:16s} {o['verified']:6s} {o['stack_peak_bytes']} "
                  f"{o['heap_peak_bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
