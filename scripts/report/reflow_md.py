"""Reflow markdown prose paragraphs and list items (bulleted and numbered, nested by
indentation) at 90 columns; tables, headings, and fenced blocks are left as they are.
Usage: reflow_md.py FILE (rewritten in place)."""
import re
import sys
import textwrap

W = 90
ITEM = re.compile(r"^(\s*(?:- |\d+\. ))")
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
out, buf = [], []


def flush():
    if not buf:
        return
    if ITEM.match(buf[0]):
        items, cur = [], []
        for ln in buf:
            m = ITEM.match(ln)
            if m and cur:
                items.append(cur)
                cur = []
            cur.append(ln.strip() if cur else ln)
        items.append(cur)
        for it in items:
            marker = ITEM.match(it[0]).group(1)
            body = " ".join([it[0][len(marker):].strip()] + it[1:])
            out.extend(textwrap.wrap(body, W, initial_indent=marker,
                                     subsequent_indent=" " * len(marker),
                                     break_long_words=False, break_on_hyphens=False))
    else:
        out.extend(textwrap.wrap(" ".join(ln.strip() for ln in buf), W,
                                 break_long_words=False, break_on_hyphens=False))
    buf.clear()


fence = False
for ln in lines:
    if ln.startswith("```"):
        flush()
        fence = not fence
        out.append(ln)
    elif fence or not ln.strip() or ln.startswith("|") or ln.startswith("#"):
        flush()
        out.append(ln)
    else:
        buf.append(ln)
flush()
open(path, "w", encoding="utf-8").write("\n".join(out))
