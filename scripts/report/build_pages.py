"""Render results/combined_draft.md (written by fill.py) as the report's two HTML pages in
the analysis series' style: index.html (results) and methods.html (the draft's appendix),
at the repository root, which GitHub Pages serves. The pages link assets/series.css and
assets/fonts.css.

It also writes assets/social-card.html, the source of the share preview image
(assets/social-card.jpg, rendered by scripts/report/social_card.py), from the same chart
data as Table 1, and puts Open Graph and Twitter card tags on both pages.

Run from the repository root, after fill.py:
    .venv/bin/python -I scripts/report/build_pages.py
"""

import html
import posixpath
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

ROOT = Path(__file__).resolve().parents[2]
# The published site, for the share tags, which need absolute URLs.
SITE_URL = "https://kdmukai-bot.github.io/post-quantum-signature-benchmarks/"
CARD_IMAGE = "assets/social-card.jpg"
CARD_SRC = ROOT / "assets" / "social-card.html"
# Table 1's chart as summary_chart drew it, for the share card and its alt text.
CARD = dict()
SRC = ROOT / "results" / "combined_draft.md"
OUT = ROOT / "index.html"
# The masthead's Updated date: bump it with every substantive change to the published
# pages, in the same edit as its entry in the corrections section.
UPDATED = "2026-11-25"

# The part break goes before the first second-level heading that matches this pattern:
# everything above it is for a general reader, everything below it is detail to check.
PARTBREAK_AT = re.compile(r"^(\d+\.?\s*)?(Detailed results|Detail)", re.I)

# Table layout: one alignment per column, and no line breaks inside a
# value. A column is numeric when every cell that holds a value starts with a number;
# cells that hold no value (empty, n/a, pending, a dash) do not decide it. Numeric
# columns, header included, are right-aligned and never wrap, except that a trailing
# footnote marker may move to a second line. Row labels and headers break only after a
# comma or colon, before a parenthesis, and (headers) between "Pi Zero 2" and its "W".
VALUE_CELL = re.compile(r"^[~<>≈±+\-−]?\s*\.?\d")
NEUTRAL_CELL = re.compile(r"^(n/a|pending|[-−–—]|)$", re.I)
TRAIL_FN = re.compile(r'((?:\s*<a class="fnref" href="#fn-\d+">\[\d+\]</a>)+)\s*$')
LABEL_BREAKS = r"((?<=[,:]) | (?=\())"
HEAD_BREAKS = r"((?<=[,:]) | (?=\()|(?<=Pi Zero 2) (?=W\b))"
VALUE_MAX = 24  # a longer cell is a description (a clock with notes), so its column wraps
LABEL_SEG_MAX = 40  # longer unbreakable stretches wrap normally instead
HEAD_SEG_MAX = 30

EXTRA_CSS = """
/* Page width: 55rem, close to GitHub's 980px content width at the laptop font size;
   phones are unaffected, since the column already fills the screen there. */
:root{ --measure:55rem; }
.tablewrap td.num, .tablewrap th.num{ text-align:right; }
.tablewrap th{ white-space:normal; font-family:var(--sans); font-size:.86rem;
  letter-spacing:0; text-transform:none; color:var(--ink); font-weight:650;
  line-height:1.3; vertical-align:bottom; }
.tablewrap .nw{ white-space:nowrap; }
.tablewrap tr.gap td{ height:1.1rem; padding:0; border:0; background:none; }
.tablewrap td.child{ padding-left:1.9rem; }
.tablewrap.summary{ max-width:36rem; }
.tablewrap.summary table{ font-size:1.12rem; }
.tablewrap.summary td{ padding:.6rem 1rem; vertical-align:baseline; }
.tablewrap.summary td.child{ padding-left:2rem; }
.tablewrap.summary td.num{ font-family:var(--sans); font-size:1.4rem; font-weight:700;
  color:var(--ink); font-variant-numeric:tabular-nums; }
:root{ --gain:#00875a; --loss:#d64545; }
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){ --gain:#1fa37f;
  --loss:#e35d5d; } }
:root[data-theme="dark"]{ --gain:#1fa37f; --loss:#e35d5d; }
.cbars{ margin:1.6rem 0; }
.cbar-title{ font-family:var(--sans); font-size:1.12rem; font-weight:700; line-height:1.35;
  color:var(--ink); padding:.7rem .75rem .65rem; background:var(--raised);
  border-top:3px solid var(--accent); }
.cbar-grid{ display:grid; grid-template-columns:max-content 1fr; }
.cbar-row{ display:contents; }
.cbar-name, .cbar-plot{ border-bottom:1px solid var(--rule); }
.cbar-name{ padding:.55rem .75rem; font-size:1.04rem; line-height:1.3; white-space:nowrap;
  display:flex; align-items:center; }
.cbar-plot{ position:relative; min-height:2.6rem; }
.cbar-plot::before{ content:""; position:absolute; top:0; bottom:-1px; left:var(--x0);
  margin-left:-1px; border-left:2px solid var(--ink); }
.cbar-axis .cbar-name, .cbar-axis .cbar-plot{ border-bottom:1px solid var(--rule-strong); }
.cbar-axis .cbar-plot{ min-height:2rem; }
@media (max-width:560px){
  .cbar-grid{ grid-template-columns:1fr; }
  .cbar-name{ white-space:normal; border-bottom:0; padding:.5rem .5rem 0; }
  .cbar-axis .cbar-name{ display:none; }
  .cbar-plot{ min-height:2.3rem; }
}
.cbar{ position:absolute; top:50%; height:20px; margin-top:-10px; }
.cbar.up{ background:var(--gain); border-radius:0 4px 4px 0; }
.cbar.down{ background:var(--loss); border-radius:4px 0 0 4px; }
.cbar-break{ position:absolute; top:-4px; bottom:-4px; width:6px; margin-left:-3px;
  background:var(--ground); transform:skewX(-24deg); }
.cbar-val, .cbar-dir{ position:absolute; top:50%; transform:translateY(-50%);
  white-space:nowrap; }
.cbar-val{ font-weight:700; font-size:1.12rem; color:var(--ink);
  font-variant-numeric:tabular-nums; }
.cbar-val.muted{ font-weight:400; color:var(--muted); font-size:1rem; }
.cbar-dir{ font-size:.82rem; color:var(--muted); }
.cbar-note{ font-size:.82rem; color:var(--muted); margin:.6rem 0 .3rem; }
.cbar-table summary{ cursor:pointer; font-size:.86rem; color:var(--muted); }
.tablewrap.summary td.num.up{ color:var(--pass); }
.tablewrap.summary td.num.down{ color:var(--accent); }
.tablewrap.summary th{ font-size:1rem; }
.tablewrap.summary caption{ font-size:1.12rem; }
.tablewrap caption{ caption-side:top; text-align:left; font-family:var(--sans);
  font-size:1rem; font-weight:700; line-height:1.35; color:var(--ink);
  padding:.7rem .75rem .65rem; background:var(--raised);
  border-top:3px solid var(--accent); }
.tablewrap tr.group td{ background:var(--raised); color:var(--ink); padding-top:.5rem;
  padding-bottom:.5rem; border-top:1px solid var(--rule-strong);
  border-bottom:1px solid var(--rule-strong); }
.tablewrap .fnwrap{ white-space:normal; }
section.footnotes{ margin-top:3rem; font-size:.86rem; color:var(--muted); }
section.footnotes ol{ padding-left:1.4rem; }
hr.footnotes-sep{ border:0; border-top:1px solid var(--rule); margin:3rem 0 1rem; }
.footnote-ref a, .footnote-backref{ text-decoration:none; }
"""


def slugify(text, used):
    """GitHub's heading anchors, which the draft's in-page links use: lowercase, drop
    everything but letters, digits, underscores, spaces, and hyphens, spaces to hyphens,
    and -1, -2 on repeats."""
    base = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-") or "section"
    slug, n = base, 1
    while slug in used:
        slug, n = f"{base}-{n}", n + 1
    used.add(slug)
    return slug


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def render(md_text):
    md = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin)
    body = md.render(md_text)

    # Title and standfirst: the first h1 and the first paragraph after it.
    title = "Draft"
    m = re.search(r"<h1>(.*?)</h1>\s*", body, re.S)
    if m:
        title = strip_tags(m.group(1))
        body = body[: m.start()] + body[m.end():]
    standfirst = ""
    m = re.match(r"\s*<p>(.*?)</p>\s*", body, re.S)
    if m:
        standfirst = m.group(1)
        body = body[m.end():]

    # Numbered, self-linking h2 headings; a contents list; the part break.
    used, toc, part = set(), [], 1
    counter = [0]

    def h2(match):
        text = match.group(1)
        plain = strip_tags(text)
        numm = re.match(r"^(\d+)\.?\s+", plain)
        plain_nonum = re.sub(r"^\d+(\.\d+)*\.?\s+", "", plain)
        text_nonum = re.sub(r"^\d+(\.\d+)*\.?\s+", "", text)
        # Keep the draft's own section numbers (its text cites them); count otherwise.
        counter[0] = int(numm.group(1)) if numm else counter[0] + 1
        slug = slugify(plain, used)
        brk = ""
        nonlocal part
        if part == 1 and PARTBREAK_AT.match(plain_nonum):
            part = 2
            brk = (
                '<div class="partbreak">\n  <p class="eyebrow">Detail</p>\n'
                '  <h2 class="parttitle">The measurements in full</h2>\n'
                "  <p>Everything above is the summary. What follows is every measured figure"
                " with its run count and inputs, written to be checked rather"
                " than read.</p>\n</div>\n"
            )
        toc.append((part, slug, plain_nonum, counter[0]))
        return (
            f'{brk}<h2 id="{slug}"><a class="anchor" href="#{slug}">'
            f'<span class="num">{counter[0]}</span>{text_nonum}</a></h2>'
        )

    body = re.sub(r"<h2>(.*?)</h2>", h2, body, flags=re.S)

    def h3(match):
        text = match.group(1)
        slug = slugify(strip_tags(text), used)
        return f'<h3 id="{slug}"><a class="anchor" href="#{slug}">{text}</a></h3>'

    body = re.sub(r"<h3>(.*?)</h3>", h3, body, flags=re.S)

    def h4(match):
        slug = slugify(strip_tags(match.group(1)), used)
        return f'<h4 id="{slug}">{match.group(1)}</h4>'

    body = re.sub(r"<h4>(.*?)</h4>", h4, body, flags=re.S)

    # Footnotes are a list of "[n] ..." items under the Footnotes heading: give each an
    # id, then link every other "[n]" marker to it.
    body = re.sub(r"<li>\[(\d{1,3})\]", r'<li id="fn-\1">[\1]', body)
    body = re.sub(r"(?<!<li id=\"fn-)(?<![\w>])\[(\d{1,3})\](?!\()",
                  r'<a class="fnref" href="#fn-\1">[\1]</a>', body)
    # Undo the link inside each footnote's own label.
    body = re.sub(r'(<li id="fn-\d+">)<a class="fnref" href="#fn-\d+">(\[\d+\])</a>',
                  r"\1\2", body)

    # Tables: scroll wrapper, wide layout past five columns, layout rules above.
    def split_marks(inner):
        m = TRAIL_FN.search(inner)
        return (inner[: m.start()], m.group(1).strip()) if m else (inner, "")

    def with_marks(core, marks):
        return core + (f'<span class="fnwrap"> {marks}</span>' if marks else "")

    def keep_together(inner, breaks, seg_max):
        """Wrap inner in no-wrap spans, allowing a line break only where breaks matches in
        text outside any element; leave inner alone if a stretch would exceed seg_max."""
        segs, cur, depth = [], "", 0
        for part in re.split(r"(<[^>]+>)", inner):
            if part.startswith("<"):
                cur += part
                if part.startswith("</"):
                    depth -= 1
                elif not part.endswith("/>") and not re.match(r"<(br|img|hr|wbr)\b", part):
                    depth += 1
            elif depth:
                cur += part
            else:
                bits = re.split(breaks, part)
                for k, b in enumerate(bits):
                    if k % 2:
                        segs += [cur, b]
                        cur = ""
                    else:
                        cur += b
        segs.append(cur)
        if max(len(strip_tags(s)) for s in segs[::2]) > seg_max:
            return inner
        return "".join(f'<span class="nw">{s}</span>' if k % 2 == 0 and s else s
                       for k, s in enumerate(segs))

    def cell_value(inner):
        s = re.sub(r"\[\d+\]", "", strip_tags(inner)).replace("*", "").replace("†", "")
        return s.strip()

    def table(match):
        t = match.group(0)
        head = re.search(r"<thead>(.*?)</thead>", t, re.S)
        heads = re.findall(r"<th([^>]*)>(.*?)</th>", head.group(1), re.S) if head else []
        ncols = len(heads)
        body = re.search(r"<tbody>(.*?)</tbody>", t, re.S)
        rows = [re.findall(r"<td([^>]*)>(.*?)</td>", r, re.S)
                for r in re.findall(r"<tr>(.*?)</tr>", body.group(1), re.S)] if body else []

        def is_group(cells):
            return (len(cells) > 1 and cells[0][1].strip().startswith("<strong>")
                    and not any(strip_tags(c[1]) for c in cells[1:]))

        numeric = [False] * ncols
        for j in range(1, ncols):
            vals = [cell_value(r[j][1]) for r in rows if len(r) > j and not is_group(r)]
            numeric[j] = (any(VALUE_CELL.match(v) for v in vals)
                          and all((VALUE_CELL.match(v) and len(v) <= VALUE_MAX)
                                  or NEUTRAL_CELL.match(v) for v in vals))

        def th_html(j, attrs, inner):
            core, marks = split_marks(inner)
            core = keep_together(core, HEAD_BREAKS, HEAD_SEG_MAX)
            cls = ' class="num"' if numeric[j] else ""
            return f"<th{attrs}{cls}>{with_marks(core, marks)}</th>"

        def td_html(j, attrs, inner, child=False):
            core, marks = split_marks(inner)
            if numeric[j]:
                # Summary ranking: + (faster than the baseline) green, − (slower) red.
                sign = strip_tags(core).strip()[:1]
                tone = (" up" if summary and sign == "+" else
                        " down" if summary and sign in "−-" and sign else "")
                return f'<td{attrs} class="num{tone}">{with_marks(core, marks)}</td>'
            # Labels and short text cells (a chip and clock, a source and date) break only
            # after a comma or colon; prose cells with longer stretches wrap normally.
            core = keep_together(core, LABEL_BREAKS, LABEL_SEG_MAX)
            if j == 0 and child:
                attrs += ' class="child"'
            return f"<td{attrs}>{with_marks(core, marks)}</td>"

        out = ["<table>"]
        cap = re.search(r"<caption>(.*?)</caption>", t, re.S)
        # Table 1 is the summary ranking for casual readers: drawn as a chart.
        summary = bool(cap and re.match(r"\s*Table 1\.", strip_tags(cap.group(1))))
        if cap:
            out.append(f"<caption>{cap.group(1)}</caption>")
        if head:
            out.append("<thead>\n<tr>\n" + "\n".join(
                th_html(j, a, i) for j, (a, i) in enumerate(heads)) + "\n</tr>\n</thead>")
        if body:
            out.append("<tbody>")
            in_group = False  # rows under a category heading are indented
            for k, r in enumerate(rows):
                if is_group(r):
                    if k:
                        out.append(f'<tr class="gap" aria-hidden="true"><td colspan="{ncols}">'
                                   "</td></tr>")
                    out.append(f'<tr class="group"><td colspan="{ncols}">{r[0][1]}</td></tr>')
                    in_group = True
                else:
                    # A baseline row stands on its own, between the groups.
                    child = in_group and not strip_tags(r[0][1]).endswith("(baseline)")
                    out.append("<tr>\n" + "\n".join(
                        td_html(j, a, i, child) for j, (a, i) in enumerate(r)) + "\n</tr>")
            out.append("</tbody>")
        out.append("</table>")
        # Values never wrap, so a table of four or more columns gets the wide layout.
        cls = ("tablewrap summary" if summary else
               "tablewrap wide" if ncols >= 4 else "tablewrap")
        table_html = f'<div class="{cls}">' + "\n".join(out) + "</div>"
        if summary:
            return summary_chart(cap.group(1), heads, rows, is_group, table_html)
        return table_html

    # Table titles: a paragraph that is only a bold "Table X. ..."
    # line, directly above a table, becomes the table's caption, so the title (processor,
    # what, unit, configuration) sits inside the table's frame and a screenshot of the
    # table carries it.
    body = re.sub(r"<p><strong>(Table \w+\.(?:(?!</strong>).)*)</strong></p>\s*<table>",
                  r"<table><caption>\1</caption>", body, flags=re.S)
    body = re.sub(r"<table>.*?</table>", table, body, flags=re.S)
    return title, standfirst, body, toc


def summary_chart(title, heads, rows, is_group, table_html):
    """Table 1 as a diverging bar chart: one row per device, a vertical
    line at the baseline (1.0x), faster devices as green bars growing right, slower ones as
    red bars growing left. The scale is linear: a bar runs from 1.0x to its value, so
    "+13x" is twelve units long and "-2.1x" is 1.1 units long, the same units on both
    sides. A bar far longer than the next longest (the Pi Zero 2 W) is cut short with a
    break mark and a one-line note. Every value is printed at its bar's tip in text color;
    the table stays available behind a disclosure for screen readers and copying.

    Bar geometry is CSS calc, so the value labels keep fixed room at both ends at any
    width: --pl and --pr hold the labels, --u is one unit of the scale, --x0 is the line."""
    items = []
    for r in rows:
        if is_group(r) or len(r) < 2:
            continue
        name, val = r[0][1], strip_tags(r[1][1]).strip()
        m = re.match(r"^([+−-]?)\s*([\d.]+)x$", val)
        if not m:
            items.append(dict(name=name, kind="pending", w=0.0, val=val))
            continue
        n = float(m.group(2))
        kind = "up" if m.group(1) == "+" else "down" if m.group(1) in "−-" and m.group(1) else "base"
        items.append(dict(name=name, kind=kind, w=n - 1 if kind != "base" else 0.0, val=val))
    # Cut the longest bar short when it is over 1.5 times the next longest, so it does not
    # squeeze every other bar: it is drawn a quarter longer than the next one, with the
    # break mark midway along that extra length.
    bars = sorted([it for it in items if it["kind"] in ("up", "down")], key=lambda it: -it["w"])
    cut = None
    if len(bars) > 1 and bars[0]["w"] > 1.5 * bars[1]["w"]:
        cut = bars[0]
        cut["drawn"] = bars[1]["w"] * 1.25
        cut["brk"] = bars[1]["w"] * 1.125
    for it in items:
        it.setdefault("drawn", it["w"])
    reach_up = max([it["drawn"] for it in items if it["kind"] == "up"] or [0.0])
    reach_down = max([it["drawn"] for it in items if it["kind"] == "down"] or [0.0])
    span = reach_up + reach_down

    def u(x):
        return f"var(--u) * {x:.4f}"

    def plain(name):
        return re.sub(r"\s*\(baseline\)$", "", strip_tags(name))

    base_name = plain(next((it["name"] for it in items if it["kind"] == "base"), "the baseline"))
    marks = " ".join(re.findall(r'<a class="fnref"[^>]*>\[\d+\]</a>',
                                heads[1][1] if len(heads) > 1 else ""))
    geo = (f"--pl:4.3rem; --pr:3.8rem; --u:calc((100% - var(--pl) - var(--pr)) / {span:.4f}); "
           f"--x0:calc(var(--pl) + {u(reach_down)})")
    out = [f'<figure class="cbars" style="{geo}">',
           f'<figcaption class="cbar-title">{title}{" " + marks if marks else ""}</figcaption>',
           '<div class="cbar-grid">',
           '<div class="cbar-row cbar-axis" aria-hidden="true"><div class="cbar-name"></div>'
           '<div class="cbar-plot">'
           '<span class="cbar-dir" style="right:calc(100% - var(--x0) + .5rem)">'
           "&larr; slower</span>"
           '<span class="cbar-dir" style="left:calc(var(--x0) + .5rem)">faster &rarr;</span>'
           "</div></div>"]
    for it in items:
        who, kind, val, d = plain(it["name"]), it["kind"], it["val"], it["drawn"]
        note = " (bar cut short to fit)" if it is cut else ""
        if kind in ("up", "down"):
            tip = (f"{who}: {val[1:]} as fast as the {base_name}{note}" if kind == "up" else
                   f"{who}: takes {val[1:]} as long as the {base_name}{note}")
            brk = ""
            if it is cut:
                at = it["brk"] / d * 100 if kind == "up" else 100 - it["brk"] / d * 100
                brk = f'<span class="cbar-break" style="left:{at:.2f}%"></span>'
            side = "left" if kind == "up" else "right"
            anchor = "var(--x0)" if kind == "up" else "calc(100% - var(--x0))"
            plot = (f'<span class="cbar {kind}" style="{side}:{anchor};width:calc({u(d)})" '
                    f'title="{html.escape(tip)}">{brk}</span>'
                    f'<span class="cbar-val" style="{side}:calc({anchor} + {u(d)} + .45rem)">'
                    f"{val}</span>")
        else:
            cls = "cbar-val muted" if kind == "pending" else "cbar-val"
            plot = f'<span class="{cls}" style="left:calc(var(--x0) + .45rem)">{val}</span>'
        out.append(f'<div class="cbar-row"><div class="cbar-name"><span>{it["name"]}</span>'
                   f'</div><div class="cbar-plot">{plot}</div></div>')
    out.append("</div>")
    CARD.update(title=strip_tags(title), geo=geo, grid="\n".join(out[2:]),
                items=[(re.sub(r"\s*\[\d+\]", "", plain(it["name"])), it["val"])
                       for it in items])
    if cut:
        out.append(f'<p class="cbar-note">The {plain(cut["name"])} bar is cut short to fit.</p>')
    out.append(f"<details class=\"cbar-table\"><summary>Show as a table</summary>{table_html}"
               "</details>")
    out.append("</figure>")
    return "\n".join(out)


def toc_html(toc, labels=None):
    if not toc:
        return ""
    out = ['<nav class="toc">', '  <span class="tag">Contents</span>']
    current = None
    for part, slug, text, num in toc:
        if part != current:
            if current is not None:
                out.append("  </ol>")
            if labels:
                out.append(f'  <p class="tocpart">{labels[part]}</p>')
            out.append(f'  <ol start="{num}">')
            current = part
        out.append(f'    <li><a href="#{slug}">{html.escape(text)}</a></li>')
    out.append("  </ol>")
    out.append("</nav>")
    return "\n".join(out)


def share_tags(title, description, url, alt):
    """Open Graph and Twitter card tags: the page's title and description, and the share
    card image (1200x630) with its alt text."""
    image = SITE_URL + CARD_IMAGE
    tags = [("name", "description", description), ("property", "og:type", "article"),
            ("property", "og:title", title), ("property", "og:description", description),
            ("property", "og:url", url), ("property", "og:image", image),
            ("property", "og:image:width", "1200"),
            ("property", "og:image:height", "630"), ("property", "og:image:alt", alt),
            ("name", "twitter:card", "summary_large_image"),
            ("name", "twitter:image", image), ("name", "twitter:image:alt", alt)]
    return "\n".join(f'<meta {k}="{v}" content="{html.escape(c)}">' for k, v, c in tags)


def page(title, standfirst, body, toc, meta, provenance="", toc_labels=None, share=""):
    """One page as the published site will show it: no preview banner, no build details.
    meta is a list of (label, html) pairs for the masthead's facts row; share is the
    head's share tags."""
    meta_html = "\n".join(f"    <div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in meta)
    stand = f'  <p class="standfirst">{standfirst}</p>\n' if standfirst else ""
    prov = (f'  <div class="note"><span class="tag">Provenance</span>\n  <p>{provenance}</p>'
            "</div>\n" if provenance else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{share}
<link rel="stylesheet" href="assets/fonts.css">
<link rel="stylesheet" href="assets/series.css">
<style>{EXTRA_CSS}</style>
</head>
<body>
<button class="themetoggle" type="button" aria-label="Toggle light and dark theme">&#9681;</button>
<div class="wrap">

<header class="masthead">
  <p class="eyebrow">Benchmark &middot; Post-quantum signatures on signing-device hardware</p>
  <h1>{html.escape(title)}</h1>
{stand}  <dl class="meta">
{meta_html}
  </dl>
{prov}</header>

{toc_html(toc, toc_labels)}

{body}

<footer></footer>
</div>
<script>
(function () {{
  var b = document.querySelector('.themetoggle');
  if (!b) return;
  b.addEventListener('click', function () {{
    var cur = document.documentElement.getAttribute('data-theme');
    if (!cur) cur = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
  }});
}})();
</script>
</body>
</html>
"""

# The share card: 1200x630, mostly seen at about a third of that size, so nothing is set
# below 19px. It follows the analysis series' cards (an accent bar down the left edge, the
# write-up's title set large, a footer with the address) and uses the page's own fonts,
# colors, and chart CSS, with only the sizes changed.
CARD_CSS = """
html, body{ margin:0; padding:0; background:var(--ground); }
body{ width:1200px; height:630px; overflow:hidden; box-sizing:border-box;
  position:relative; padding:38px 60px 30px 68px; display:grid;
  grid-template-rows:auto 1fr auto;
  font-family:var(--sans); color:var(--ink); }
body::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:8px;
  background:var(--accent); }
h1{ font-size:50px; line-height:1.04; letter-spacing:-.015em; font-weight:650;
  margin:0 0 16px; text-wrap:balance; }
.cbars{ margin:0; align-self:center; --pl:84px; --pr:76px; }
.chart-label{ font-size:23px; font-weight:600; color:var(--muted); margin:0 0 4px; }
.cbar-name{ font-size:21px; padding:0 22px 0 0; }
.cbar-plot{ min-height:32px; }
.cbar-axis .cbar-plot{ min-height:25px; }
.cbar-row:last-child > *{ border-bottom:0; }
.cbar{ height:18px; margin-top:-9px; }
.cbar-val{ font-size:22px; }
.cbar-dir{ font-size:19px; }
.foot{ display:flex; justify-content:space-between; align-items:baseline;
  border-top:1px solid var(--rule); padding-top:12px; margin-top:10px;
  font-family:var(--mono); font-size:19px; color:var(--muted); }
.foot b{ font-weight:400; color:var(--faint); }
"""


def social_card_html(page_title, n_boards):
    """assets/social-card.html: the page title, then Table 1's chart under the chart's own
    title, with a footer giving the board count and the site address. Dark by default;
    ?theme=light renders the light version from the same file, and ?scale=2 renders it at
    twice the size."""
    chart_title = re.sub(r"^Table \S+\.\s*", "", CARD["title"])
    grid = re.sub(r'\s*<a class="fnref"[^>]*>\[\d+\]</a>', "", CARD["grid"])
    geo = re.sub(r"--pl:[^;]*; --pr:[^;]*; ", "", CARD["geo"])
    facts = "Benchmark" + (f" &middot; {n_boards} boards" if n_boards else "")
    host, path = SITE_URL.split("://", 1)[1].rstrip("/").split("/", 1)
    return f"""<!doctype html>
<!-- Source of assets/social-card.jpg (1200x630), written by scripts/report/build_pages.py
     from Table 1's chart; render it with scripts/report/social_card.py. -->
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<title>{html.escape(page_title)}: share card</title>
<script>
  var q = new URLSearchParams(location.search);
  document.documentElement.setAttribute('data-theme',
    q.get('theme') === 'light' ? 'light' : 'dark');
  // ?scale=2 lays the card out at twice the size, for a sharper render to downsample.
  if (q.get('scale')) document.documentElement.style.zoom = q.get('scale');
</script>
<link rel="stylesheet" href="fonts.css">
<link rel="stylesheet" href="series.css">
<style>{EXTRA_CSS}{CARD_CSS}</style>
</head>
<body>
<h1>{html.escape(page_title)}</h1>
<figure class="cbars" style="{geo}">
<p class="chart-label">{html.escape(chart_title)}</p>
{grid}
</figure>
<div class="foot"><span>{facts}</span><span><b>{host}/</b>{path}</span></div>
</body>
</html>
"""


def results_links(body):
    """The draft lives in results/ and links files relative to it; the pages sit at the
    repository root, so those links gain the results/ prefix."""
    def fix(m):
        target = m.group(1)
        if re.match(r"(https?:|mailto:|#|index\.html|methods\.html|assets/)", target):
            return m.group(0)
        return f'href="{posixpath.normpath("results/" + target)}"'
    return re.sub(r'href="([^"]+)"', fix, body)


def split_draft(text):
    """The draft as the published site divides it: the results page, its provenance
    statement (masthead), and the methods page (the draft's appendix). The draft's opening
    status line is internal and is dropped."""
    main_md, _, methods_md = text.partition("\n## Appendix")
    head, sep, rest = main_md.partition("\n## ")
    paras = re.split(r"\n\s*\n", head)
    provenance = ""
    kept = []
    for p in paras:
        if p.strip().startswith("Generated by `scripts/report/fill.py`"):
            continue
        if p.strip().startswith("Provenance:"):
            provenance = " ".join(p.strip()[len("Provenance:"):].split())
            provenance = provenance[:1].upper() + provenance[1:]
            continue
        kept.append(p)
    main_md = "\n\n".join(kept) + sep + rest
    methods_md = methods_md.split("\n", 1)[1] if methods_md else ""
    methods_md = re.sub(r"^###", "##", methods_md, flags=re.M)
    methods_md = "# Methods\n\n" + methods_md
    return main_md, provenance, methods_md


def board_count(md_text):
    m = re.search(r"^\| Board(?: \[\d+\])? \| Processor \|.*\n\|[-| :]+\|\n((?:\|.*\n)+)",
                  md_text, re.M)
    return len(m.group(1).strip().split("\n")) if m else None


def cross_link(body, own_ids, other_ids, other_page, aliases):
    """Point in-page links whose target lives on the other page at that page."""
    def fix(m):
        target = m.group(1)
        if target in aliases:
            return f'href="{aliases[target]}"'
        if target not in own_ids and target in other_ids:
            return f'href="{other_page}#{target}"'
        return m.group(0)
    return re.sub(r'href="#([^"]+)"', fix, body)


def main():
    main_md, provenance, methods_md = split_draft(SRC.read_text())
    title, standfirst, body, toc = render(main_md)
    m_title, _, m_body, m_toc = render(methods_md)
    ids = set(re.findall(r'id="([^"]+)"', body))
    m_ids = set(re.findall(r'id="([^"]+)"', m_body))
    to_methods = dict((i, "methods.html") for i in re.findall(r'href="#(appendix[^"]*)"', body))
    body = results_links(cross_link(body, ids, m_ids, "methods.html", to_methods))
    m_body = results_links(cross_link(m_body, m_ids, ids, "index.html", {}))
    prov = MarkdownIt("commonmark").renderInline(provenance) if provenance else ""
    updated = UPDATED
    rev = "<span data-deploy-rev>working copy</span>"
    pages = '<a href="index.html">Results</a> &middot; <a href="methods.html">Methods</a>'
    n = board_count(main_md)
    meta = ([("Updated", updated), ("Revision", rev)] + ([("Boards", str(n))] if n else [])
            + [("Pages", pages)])
    cap = re.sub(r"^Table \S+\.\s*", "", CARD.get("title", ""))
    alt = (f"Bar chart: {cap[:1].lower() + cap[1:]}. "
           + "; ".join(f"{who} {val}" for who, val in CARD.get("items", [])) + ".")
    words = "one two three four five six seven eight nine ten".split()
    count = words[n - 1] if n and n <= len(words) else str(n)
    desc = (f"Post-quantum signature schemes timed on {count} boards in the SeedSigner "
            "ecosystem and compared with the hardware wallets in Blockstream's tests.")
    m_desc = ("How the post-quantum signature benchmarks were built, run, timed, and "
              "checked.")
    OUT.write_text(page(title, standfirst, body, toc, meta, prov,
                        {1: "Summary", 2: "Detail"},
                        share_tags(title, desc, SITE_URL, alt)))
    m_meta = [("Updated", updated), ("Revision", rev), ("Pages", pages)]
    m_full = f"{m_title}: {title}"
    (OUT.parent / "methods.html").write_text(
        page(m_full, "", m_body, m_toc, m_meta, prov,
             share=share_tags(m_full, m_desc, SITE_URL + "methods.html", alt)))
    CARD_SRC.write_text(social_card_html(title, n))
    unresolved = sorted(set(
        re.findall(r'href="#([^"]+)"', body)) - ids) + sorted(set(
        re.findall(r'href="#([^"]+)"', m_body)) - m_ids)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(toc)} sections, {body.count('<table>')} "
          f"tables) and methods.html ({len(m_toc)} sections, {m_body.count('<table>')} "
          f"tables); in-page links that resolve nowhere: {unresolved or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
