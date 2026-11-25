"""Number format for the report: at most four significant figures, and
no digit finer than the leading digit of the uncertainty a figure carries (the standard
error of a mean or of a fit) or the print resolution of its timings, whichever is
coarser. Expected values carry their standard error, to one significant figure, after
" ± ". Every function takes values already scaled to the table's unit."""
import decimal
import math

EPS = 1e-9


def lead(x):
    """10 to the power of the position of the leading digit of x (x > 0)."""
    return 10.0 ** math.floor(math.log10(x) + EPS)


def step(x, u=None, q=None, sig=4):
    """Rounding step for x: the coarser of sig significant figures and the leading digit
    of u (uncertainty) or q (print resolution)."""
    s = lead(abs(x)) / 10 ** (sig - 1) if x else (q or 1.0)
    for e in (u, q):
        if e is not None and e > 0 and not math.isnan(e):
            s = max(s, lead(e))
    return s


def at_step(x, s):
    if s >= 1 - EPS:
        return f"{round(x / s) * s:,.0f}"
    nd = int(round(-math.log10(s)))
    return f"{x:,.{nd}f}"


def num(x, u=None, q=None, sig=4):
    """x rounded by step(); thousands separated by commas."""
    s = step(x, u, q, sig)
    out = at_step(x, s)
    # Rounding can add a digit (9.9996 to 10.000); round again from the rounded value.
    y = float(out.replace(",", ""))
    if y and step(y, u, q, sig) > s:
        out = at_step(y, step(y, u, q, sig))
    return out


def se(u):
    """A standard error to one significant figure."""
    s = lead(u)
    v = round(u / s) * s
    return at_step(v, lead(v))


def pm(x, u, q=None, sig=4):
    """Value and standard error, "x ± u"; returns (value text, full text)."""
    v = num(x, u, q, sig)
    if u is None or math.isnan(u) or u <= 0:
        return v, v
    return v, f"{v} ± {se(u)}"


def ratio(x, sig=3):
    return num(x, sig=sig)


# Rounding for Table K1 and the findings: they quote detail-table figures rounded further,
# so these functions take the number as displayed in the detail table (a string such as
# "1,099" or "45.65") and never recompute it. fill.py's reconciliation uses the same
# functions on the final text.
_MODES = dict((("round", decimal.ROUND_HALF_UP), ("ceil", decimal.ROUND_CEILING),
               ("floor", decimal.ROUND_FLOOR)))


def dnum(x):
    """A displayed number (thousands separators allowed) as a Decimal."""
    if isinstance(x, decimal.Decimal):
        return x
    if isinstance(x, str):
        return decimal.Decimal(x.replace(",", ""))
    return decimal.Decimal(repr(x))


def rsig(x, sig=3, mode="round", scale=1, cap=True):
    """x rounded to sig significant figures after multiplying by scale; mode "round" (half
    up), "ceil" (for "at most"), or "floor". sig None: two significant figures, or every
    integer digit when there are more. With cap, a displayed string keeps at most its own
    decimals, so rounding never adds precision."""
    d = dnum(x) * dnum(scale)
    dec = None
    if cap and isinstance(x, str) and scale == 1:
        s = x.replace(",", "")
        dec = len(s.split(".")[1]) if "." in s else 0
    if d == 0:
        return "0"
    lead = d.adjusted()
    n = sig if sig else max(2, lead + 1)
    exp = lead - (n - 1)
    if dec is not None:
        exp = max(exp, -dec)
    q = d.quantize(decimal.Decimal(1).scaleb(exp), rounding=_MODES[mode])
    if q.adjusted() > lead and not sig:
        n = max(2, q.adjusted() + 1)
    if q.adjusted() > lead:  # 9.96 to 10.0: keep sig figures at the new leading digit
        exp = max(exp, q.adjusted() - (n - 1))
        q = d.quantize(decimal.Decimal(1).scaleb(exp), rounding=_MODES[mode])
    if exp >= 0:
        return f"{int(q):,}"
    return f"{q:,.{-exp}f}"
