"""Rebuild results/combined_draft.md from the raw result files: levels2.py gives the first
round's tables (cost of safeguards, Jade firmware calibration), round2.py everything else
(second and third rounds, round 4 on the Pi Zero 2 W and the RP2350, key results, the
comparison with other reports, footnote texts); both are inserted into draft_template.md,
footnotes are numbered by first reference, the result is reflowed at 90 columns, and every
figure in Tables K1 and C1 is checked: ours against its detail-table cell in the final
text, other reports' against their transcription files.

Usage, from the repository root:
    .venv/bin/python -I scripts/report/fill.py [--out FILE] [--csv-dir DIR]
--out      the draft (default results/combined_draft.md)
--csv-dir  generated CSV files the draft links (default results/derived)
Intermediate table dumps go to scripts/report/out/ (not committed).

Edit draft_template.md and the scripts, never the output. Footnotes: the template defines
each one in a paragraph that starts with {{fndef:name}} and cites it with {{fn:name}};
generated text may cite them too."""
import argparse
import collections
import csv
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.chdir(ROOT)  # levels2.py reads its files relative to the repository root

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join(ROOT, "results", "combined_draft.md"))
ap.add_argument("--csv-dir", default=os.path.join(ROOT, "results", "derived"))
args = ap.parse_args()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


levels2 = load("levels2")  # writes out/tables2.md
parts = re.split(r"^## (\S+)\n\n", open(os.path.join(HERE, "out", "tables2.md")).read(),
                 flags=re.M)
tables = dict((parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2))
round2 = load("round2")
gen = round2.build(levels2, args.csv_dir)
with open(os.path.join(HERE, "out", "tables.md"), "w") as f:
    for k, v in gen.items():
        f.write(f"## {k}\n\n{v}\n\n")
tables.update(gen)

t = open(os.path.join(HERE, "draft_template.md")).read()
for k, v in tables.items():
    t = t.replace("{{" + k + "}}", v)

# Footnotes: collect the definitions, number them by first citation, list them.
defs = collections.OrderedDict()


def take(m):
    defs[m.group(1)] = " ".join(m.group(2).split())
    return ""


t = re.sub(r"^\{\{fndef:([\w-]+)\}\}(.*?)(?:\n[ \t]*\n|\Z)", take, t, flags=re.M | re.S)
order = []
for name in re.findall(r"\{\{fn:([\w-]+)\}\}", t):
    if name not in order:
        order.append(name)
undefined = [n for n in order if n not in defs]
unused = [n for n in defs if n not in order]
assert not undefined, f"footnotes cited but not defined: {undefined}"
assert not unused, f"footnotes defined but not cited: {unused}"
number = dict((n, i) for i, n in enumerate(order, 1))
t = re.sub(r"\{\{fn:([\w-]+)\}\}", lambda m: f" [{number[m.group(1)]}]", t)
t = re.sub(r" +\[(\d+)\]", r" [\1]", t)
t = t.replace("{{FOOTNOTES}}", "\n".join(f"- [{number[n]}] {defs[n]}" for n in order))
left = re.findall(r"\{\{[\w:-]+\}\}", t)
assert not left, left
t = re.sub(r"\n{3,}", "\n\n", t).rstrip() + "\n"

os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
open(args.out, "w").write(t)
subprocess.run([sys.executable, "-I", os.path.join(HERE, "reflow_md.py"), args.out], check=True)
final = open(args.out).read()


# Reconciliation: every figure Table K1 or Table C1 shows is recomputed here from the
# final text and the transcription files. Ours: the detail-table cell as displayed,
# rounded with numfmt.rsig() as the quote says, must give the shown figure and its round-3
# mark.
# Other reports' (C1): the transcribed figure, read here from its file under
# results/published/, converted to the column's unit (cycle counts divided by the stated
# clock) and rounded the same way, must give the shown figure. Each quote must also appear
# in its table cell.
NF = round2.NF
MARK = round2.R2_MARK
PUB = os.path.join(ROOT, "results", "published")


def norm(s):
    s = re.sub(r"\s*\[\d+\]", "", s.replace("**", ""))
    return s.strip()


# A table is labeled by the bold line just above it: "**Table X.**" followed by text, or a
# title line "**Table X. title**".
TABLE_RE = re.compile(r"^\*\*Table (\w+)\.(?:\*\*| )")


def parse_tables(text):
    cells, cur = dict(), None
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = TABLE_RE.match(ln)
        if m:
            cur = m.group(1)
        if ln.startswith("|") and cur:
            head = [norm(c) for c in ln.strip().strip("|").split("|")]
            i += 2
            group = ""
            while i < len(lines) and lines[i].startswith("|"):
                cs = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if cs[0].startswith("**") and not any(cs[1:]):
                    group = norm(cs[0])
                else:
                    lab = norm(cs[0])
                    key = f"{group}/{lab}" if group else lab
                    for h, c in zip(head[1:], cs[1:]):
                        cells[(cur, key, h)] = c
                i += 1
            cur = None
            continue
        i += 1
    return cells


def number_of(s):
    m = re.match(r"\s*([+\-]?[\d,]*\.?\d+)", s)
    return m.group(1) if m else None


def pub_figure(name, match, column, factor, per):
    with open(os.path.join(PUB, name)) as f:
        rows = list(csv.DictReader(ln for ln in f if not ln.startswith("#")))
    rs = [r for r in rows if all(r.get(k, "") == v for k, v in match.items())]
    if len(rs) != 1:
        return None
    x = NF.dnum(rs[0][column]) * NF.dnum(factor)
    return x / (NF.dnum(rs[0][per]) * 1000000) if per else x


tabs = parse_tables(final)
problems = []
count = collections.Counter()
for r in round2.REFS:
    if r["kind"] in ("factor", "factor1", "c1-spread", "quote", "bound"):
        continue  # Table C1's multipliers and section 1's figures, checked below
    where = tuple(r["where"])
    if r["kind"] == "pub":
        x = pub_figure(r["file"], r["match"], r["column"], r["factor"], r["per"])
        want = NF.rsig(x, r["sig"], "round", 1, cap=False) if x is not None else None
        count[f"{where[0]} from published files"] += 1
    else:
        src = []
        for key in r["keys"]:
            c = tabs.get(tuple(key))
            if c is None or number_of(c) is None:
                problems.append(f"{where}: no figure in {key}")
                break
            src.append((number_of(c), MARK in c))
        else:
            want = NF.rsig(src[0][0], r["sig"], r["mode"], r["scale"])
            want += MARK if any(f for _, f in src) else ""
        if len(src) != len(r["keys"]):
            continue
        count[f"{where[0]} from detail tables"] += 1
    if want != r["text"]:
        problems.append(f"{where}: quotes {r['text']}, its source gives {want}")
    c = tabs.get(where)
    if c is None or number_of(c) != r["text"].rstrip(MARK) or (MARK in c) != (MARK in r["text"]):
        problems.append(f"{where[0]} {where[1:]} reads {c}, expected {r['text']}")



# Table C1: each factor is recomputed from its inputs as displayed (our detail cells in
# the final text, Blockstream's figures from its transcription file): each scheme's time
# over the fastest device's, then the geometric mean of the two ratios, to two significant
# figures ("1" for the fastest). The intro's order check and largest ratio spread are
# recomputed the same way.
def input_value(spec):
    if spec["kind"] == "cell":
        c = tabs.get(tuple(spec["key"]))
        return NF.dnum(number_of(c)) if c and number_of(c) else None
    return pub_figure(spec["file"], spec["match"], spec["column"], spec["factor"], spec["per"])


factors = [r for r in round2.REFS if r["kind"] == "factor"]
fvals = dict((r["where"][1], [input_value(s) for s in r["inputs"]]) for r in factors)
if any(None in v for v in fvals.values()):
    problems.append(f"C1: an input is missing: {fvals}")
else:
    best = [min(v[i] for v in fvals.values()) for i in range(2)]
    ratios = dict((k, [x / b for x, b in zip(v, best)]) for k, v in fvals.items())
    # Each factor against the baseline's (the Jade Plus): "+N" for N times as fast, U+2212
    # "N" for N times as long, "1.0" for the baseline itself; the cell adds "x".
    fac = dict((k, (rs[0] * rs[1]).sqrt()) for k, rs in ratios.items())
    base = [r["where"][1] for r in factors if r.get("baseline")]
    if len(base) != 1:
        problems.append(f"C1: expected one baseline row, found {base}")
    else:
        fb = fac[base[0]]
        for r in factors:
            where = tuple(r["where"])
            f = fac[where[1]]
            want = ("1.0" if r.get("baseline") else
                    "+" + NF.rsig(fb / f, 2, "round", 1, cap=False) if f < fb else
                    "\u2212" + NF.rsig(f / fb, 2, "round", 1, cap=False))
            count["C1 factors"] += 1
            if want != r["text"]:
                problems.append(f"{where}: shows {r['text']}, its inputs give {want}")
            c = tabs.get(where)
            if c is None or norm(c) != r["text"] + "x":
                problems.append(f"C1 {where[1:]} reads {c}, expected {r['text']}x")
    spread = dict((k, max(v) / min(v)) for k, v in ratios.items())
    # the row label, without a group or a (baseline) tag
    worst = re.sub(r" \(baseline\)$", "",
                   max(spread, key=lambda k: spread[k]).split("/")[-1])
    worst_key = max(spread, key=lambda k: spread[k])
    orders = [[k for k, _ in sorted(ratios.items(), key=lambda kv: kv[1][i])] for i in range(2)]
    nswap = sum(1 for i, a in enumerate(orders[0]) for b in orders[0][i + 1:]
                if orders[1].index(a) > orders[1].index(b))
    vals = [NF.rsig(x, 2, "round", 1, cap=False)
            for x in (spread[worst_key], ratios[worst_key][0], ratios[worst_key][1])]
    want = "|".join(vals + [str(nswap)])
    fns = [ln for ln in final.split("\n- [") if "Relative to the Jade Plus: each device" in ln]
    intro = " ".join(fns[0].split()) if len(fns) == 1 else ""
    for r in round2.REFS:
        if r["kind"] != "c1-spread":
            continue
        count["C1 footnote figures"] += 1
        if r["text"] != want or r["device"] != worst:
            problems.append(f"C1 footnote: states {r['device']} {r['text']}, inputs give {worst} "
                            f"{want}")
        same = "same order" in intro
        # The intro states the order and the largest spread (vals[0]); the device and its
        # two ratios are checked above against r["device"] and r["text"].
        if (nswap == 0) != same or vals[0] not in intro:
            problems.append(f"C1 footnote does not match its figures: {intro[:200]}")

# Table C1's single-scheme rows: the baseline's time for that scheme over the row's, "+N"
# when faster, U+2212 "N" when slower, two significant figures; the cell adds "x".
for r in round2.REFS:
    if r["kind"] != "factor1":
        continue
    where = tuple(r["where"])
    xs = [input_value(s) for s in r["inputs"]]
    count["C1 single-scheme rows"] += 1
    if None in xs:
        problems.append(f"{where}: an input is missing")
        continue
    rel = xs[1] / xs[0]
    want = ("+" + NF.rsig(rel, 2, "round", 1, cap=False) if rel > 1 else
            "\u2212" + NF.rsig(1 / rel, 2, "round", 1, cap=False))
    if want != r["text"]:
        problems.append(f"{where}: shows {r['text']}, its inputs give {want}")
    c = tabs.get(where)
    if c is None or norm(c) != r["text"] + "x":
        problems.append(f"C1 {where[1:]} reads {c}, expected {r['text']}x")

# Section 1's discussion: every quoted figure recomputed from its inputs as displayed, and
# found in section 1's text.
sec1 = " ".join(final.split("\n## 1. ", 1)[1].split("\n## 2. ", 1)[0].split())
for r in round2.REFS:
    if r["kind"] not in ("quote", "bound"):
        continue
    xs = [input_value(s) for s in r["inputs"]]
    if None in xs:
        problems.append(f"section 1: an input of {r['text']!r} is missing")
        continue
    if r["kind"] == "bound":
        count["section 1 bounds"] += 1
        if not max(xs) < NF.dnum(r["limit"]):
            problems.append(f"section 1: {r['text']!r} no longer holds (max {max(xs)})")
    else:
        count["section 1 figures"] += 1
        op = r["op"]
        x = (xs[0] if op == "value" else xs[0] / xs[1] if op == "ratio" else min(xs)
             if op == "min" else max(xs) if op == "max" else
             (xs[0] * xs[1]).sqrt() / (xs[2] * xs[3]).sqrt())
        want = NF.rsig(x, r["sig"], r["mode"], 1, cap=False)
        if want != r["text"]:
            problems.append(f"section 1: quotes {r['text']}, its inputs give {want} ({op})")
    if r["text"] not in sec1:
        problems.append(f"section 1: {r['text']!r} not found in the text")

pend = round2.PEND
by_tab = collections.Counter(v[0] for v in pend.values())
by_flag = collections.Counter(v[3] for v in pend.values())
assert all(round2.r3_eligible(k[0], k[1], k[2], k[4]) for k in pend), "non-round-3 pending"
shown_mark = final.count(round2.R2_MARK)


def pending_cells(text):
    """Every table cell reading "pending" in the text, as (header, row label): the
    RP2350's (its column header or row label names it, or the table is the RP2350's own,
    titled with its name first) and any other."""
    rp, other = [], []
    head = None
    own = False
    for ln in text.split("\n"):
        m = TABLE_RE.match(ln)
        if m:
            own = ln.startswith(f"**Table {m.group(1)}. RP2350")
        if not ln.startswith("|"):
            head = None
            continue
        cs = [c.strip() for c in ln.strip().strip("|").split("|")]
        if head is None:
            head = cs
            continue
        if set(ln.replace("|", "").strip()) <= set("-: "):
            continue
        for h, c in zip(head, cs):
            if c == round2.PENDING:
                (rp if own or "RP2350" in h or "RP2350" in cs[0] else other).append((h, cs[0]))
    return rp, other


rp_pending, other_pending = pending_cells(final)
shown_pending = len(other_pending)
print(f"wrote {os.path.relpath(args.out, ROOT)}; cells pending: {len(pend)} (round-3 cells: "
      f"{by_flag[round2.R2_MARK]} showing the round-2 value, {by_flag[round2.PENDING]} with no "
      f"value; by table: " + ", ".join(f"{k} {v}" for k, v in sorted(by_tab.items())) + ")")
print(f"in the text: {shown_mark} {round2.R2_MARK} marks (detail cells, derived ratios, K1, "
      f"C1), {shown_pending} table cells reading 'pending' other than the RP2350's")
if round2.RP2350_DATA:
    if rp_pending:
        sys.exit("RP2350 data is switched on, yet RP2350 cells still read 'pending'")
else:
    print(f"RP2350 cells pending: {len(rp_pending)} (allowed while round2.RP2350_DATA is "
          f"False)")
print(f"reconciliation: {len(round2.REFS)} figures checked ("
      + ", ".join(f"{n} in {k}" for k, n in sorted(count.items())) + f"), {len(problems)} "
      f"mismatches")
for p in problems:
    print("  MISMATCH " + p)
if problems:
    sys.exit(1)
# The Pi Zero 2 W has one round (round 4): a cell its run plans cover but no complete file
# fills would read "pending", which the template's captions do not allow for.
if round2.MISSING_R4:
    sys.exit("Pi Zero 2 W (round 4) files missing for " + ", ".join(
        "/".join(str(x) for x in k) for k in sorted(round2.MISSING_R4)))
print(f"Pi Zero 2 W: {len(round2.S['pi2'])} round-4 files indexed, none missing")
# The RP2350 likewise: a job set its run plans list but no complete log fills.
if round2.MISSING_RP:
    sys.exit("RP2350 (round 4) logs missing for " + ", ".join(
        "/".join(str(x) for x in k) for k in sorted(round2.MISSING_RP, key=str)))
if round2.RP2350_DATA:
    print(f"RP2350: {len(round2.S['rp'])} round-4 logs indexed, none missing")
# The template describes round 3 as complete on every board, so a cell that still shows a
# round-2 value or "pending" means a round-3 file is missing.
if pend or shown_mark or shown_pending:
    sys.exit("round-3 data missing: the template's captions and footnote no longer hold")

# results/summary.csv and results/raw/MANIFEST.csv, from the data the tables used.
summary = load("summary")
srows, mrows = summary.write(round2, levels2, round2.FIT)
print(f"summary: {len(srows)} rows in results/summary.csv; manifest: {len(mrows)} files in "
      f"results/raw/MANIFEST.csv, {sum(1 for r in mrows if r['used_by'])} read by the report")
unread = [r["path"] for r in mrows if not r["used_by"]]
if unread:
    print(f"raw files the report does not read ({len(unread)}): " + ", ".join(unread[:5])
          + (" ..." if len(unread) > 5 else ""))
