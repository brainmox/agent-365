"""Independent re-certification of Table 4 of Hexagon 2611.00174v1.

"The spinless modular bootstrap at large central charge" (Claude (Anthropic),
Hexagon 2611.00174v1, 2026-11-07) proves its attainment half (Theorem 5) modulo
a closed list of eleven numerical inequalities, Table 4, each certified with
Arb interval arithmetic. The paper publishes no code. This module rebuilds the
rows whose functions are fully defined in the paper's printed text, using only
those printed definitions, and certifies them with python-flint (Arb).

Every check returns a Check record. `certified` is True only when the interval
enclosure proves the inequality on the whole stated range; a value-only row has
`claim=None` and is reported, not certified.

Reconstruction notes (also in README.md):
  * x1* = arcsinh(1)/pi, so sinh(pi x1*) = 1 exactly and cosh(pi x1*) = sqrt 2.
  * Row 9 uses rho_U(y) proportional to arccosh(sinh(pi y)) (paper eq. 6.21);
    the prefactor cancels in the log-derivative.
  * Rows 1-2 use rho_inf of Lemma 7.8, eq. (7.26):
        rho_inf(x) = 1/2 * (|b0| / (x F'(v0)))^(1/2) * coth(pi x / 2) * |T_{x1*}(x)|^(2 n1)
    with the edge function F(v) = arcsinh(cosh(pi v))/pi (7.3), cosh(pi v0) = sinh(pi x),
    F'(v0) = sinh(pi v0)/cosh(pi x), b0 = v0 + i/2, T_{x'}(b) =
    (cosh pi b - cosh pi x')/(cosh pi b + cosh pi x') (appendix D), n1 = 7/4 (section 7.2).
    The PDF's text layer garbles "i/2" and "7/4"; the readings used here are the ones
    that reproduce the paper's printed anchors rho_inf(3) = 0.50271 and
    rho_inf(1.33) = 0.394 and its tip power 2 n1 - 1/4 = 13/4 (see tests).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict

from flint import arb, ctx

ctx.prec = 128


def iv(lo, hi) -> arb:
    """Ball enclosing the closed interval [lo, hi]."""
    return arb(lo).union(arb(hi))


def pi() -> arb:
    return arb.pi()


def x1() -> arb:
    return arb(1).asinh() / pi()


@dataclass
class Check:
    row: str
    name: str
    value: str            # enclosure (midpoint, 10 digits) or bound obtained
    claim: str | None     # e.g. "<= 0.95"; None for value-only rows
    printed: str          # what the paper prints for this quantity
    certified: bool | None
    method: str
    cells: int = 0
    notes: str = ""


def _fmt(a: arb, digits: int = 10) -> str:
    return a.str(digits, radius=False)


def _closed(row, name, val: arb, op, bound, printed, method="closed form, 128-bit ball arithmetic"):
    b = arb(bound)
    ok = {"<": val < b, "<=": val <= b, ">=": val >= b, ">": val > b}[op]
    return Check(row, name, _fmt(val), f"{op} {bound}", printed, bool(ok), method)


# ---------------------------------------------------------------------------
# Covering machinery
# ---------------------------------------------------------------------------

def cover_max(f, a, b, n, *, geometric=False, bound=None, max_depth=12):
    """Upper bound of f on [a, b] from n cells (uniform or geometric).

    If `bound` is given, a cell whose enclosure exceeds it (or is not finite)
    is bisected, up to `max_depth` times, before the covering is declared to
    fail. Returns (sup_upper: arb, cells_evaluated: int, failed_cells: list).
    """
    worst, count, failed, _ = cover_max_ex(f, a, b, n, geometric=geometric, bound=bound, max_depth=max_depth)
    return worst, count, failed


def cover_max_ex(f, a, b, n, *, geometric=False, bound=None, max_depth=12):
    """As cover_max, plus a rigorous LOWER bound on the true supremum (the
    largest lower endpoint of f evaluated at a cell midpoint), so a report can
    say: sup f on [a, b] lies in [floor, upper].
    Returns (sup_upper, cells_evaluated, failed_cells, floor)."""
    a, b = arb(a), arb(b)
    edges = []
    for i in range(n + 1):
        t = arb(i) / n
        e = a * (b / a) ** t if geometric else a + (b - a) * t
        edges.append(arb(e.mid()))
    edges[0], edges[-1] = a, b
    worst, count, failed, floor = None, 0, [], None
    stack = [(edges[i], edges[i + 1], 0) for i in range(n)]
    while stack:
        lo, hi, depth = stack.pop()
        val = f(iv(lo.lower(), hi.upper()))
        count += 1
        up = val.upper() if val.is_finite() else None
        bad = up is None or (bound is not None and not (up <= arb(bound)))
        if bad and depth < max_depth:
            mid = arb(((lo + hi) / 2).mid())
            stack += [(lo, mid, depth + 1), (mid, hi, depth + 1)]
            continue
        if bad:
            failed.append((_fmt(lo, 8), _fmt(hi, 8)))
            continue
        worst = up if worst is None or up > worst else worst
        pt = f(arb(((lo + hi) / 2).mid())).lower()
        floor = pt if floor is None or pt > floor else floor
    return worst, count, failed, floor


def cover_min(f, a, b, n, *, bound=None, max_depth=12):
    neg = lambda r: -f(r)
    w, count, failed = cover_max(neg, a, b, n, bound=None if bound is None else -arb(bound), max_depth=max_depth)
    return (None if w is None else -w), count, failed


# ---------------------------------------------------------------------------
# Functions from the paper's printed definitions
# ---------------------------------------------------------------------------

def dlog_rho_U(x: arb) -> arb:
    """(log rho_U)'(x) for rho_U proportional to arccosh(sinh(pi x)), x > x1*."""
    p = pi()
    s = (p * x).sinh()
    return p * (p * x).cosh() / ((s * s - 1).sqrt() * s.acosh())


def row9_first(r: arb) -> arb:
    return arb("1.3") * r * dlog_rho_U(x1() + r)


def row9_first_regularized(r: arb) -> arb:
    """1.3 r (log rho_U)'(x1*+r) in a form with no 0/0, valid on r in [0, 2^-10].

    With x = x1* + r, s = sinh(pi x), w = s - 1 = 2 cosh(pi(x1* + r/2)) sinh(pi r/2):
      sqrt(s^2 - 1) = sqrt(w (w + 2)),
      arccosh(1 + w) = 2 arcsinh(sqrt(w/2)) = sqrt(2w) g(w),
      g(w) = 2F1(1/2, 1/2; 3/2; -w/2) in [1 - w/12, 1] for 0 <= w < 2
        (alternating series with decreasing terms),
      r / w = 1 / (pi cosh(pi(x1* + r/2)) S(pi r/2)),  S(y) = sinh(y)/y in [1, cosh y].
    So 1.3 r (log rho_U)' = 1.3 cosh(pi x) / (cosh(pi(x1* + r/2)) S sqrt(2) sqrt(w + 2) g).
    `r` must be a ball inside [0, 2^-10].
    """
    p = pi()
    rlo, rhi = arb(r.lower()), arb(r.upper())
    if rlo < 0:
        rlo = arb(0)
    y_hi = p * rhi / 2
    S = iv(1, y_hi.cosh().upper())
    w_hi = (2 * (p * (x1() + rhi / 2)).cosh() * (p * rhi / 2).sinh()).upper()
    w = iv(0, w_hi)
    g = iv((1 - arb(w_hi) / 12).lower(), 1)
    x = x1() + iv(rlo, rhi)
    return arb("1.3") * (p * x).cosh() / ((p * (x1() + iv(rlo, rhi) / 2)).cosh() * S * arb(2).sqrt() * (w + 2).sqrt() * g)


def rho_inf(x: arb) -> arb:
    """rho_inf of Lemma 7.8, eq. (7.26), for x > x1*."""
    p = pi()
    s = (p * x).sinh()
    c = (p * x).cosh()                      # = sqrt(1 + s^2)
    sinh_v0 = (s * s - 1).sqrt()            # sinh(pi v0) with cosh(pi v0) = s
    v0 = s.acosh() / p
    Fp = sinh_v0 / c
    b0 = (v0 * v0 + arb(1) / 4).sqrt()      # |v0 + i/2|
    coth = 1 / (p * x / 2).tanh()
    ch1 = arb(2).sqrt()                      # cosh(pi x1*)
    T = (c - ch1) / (c + ch1)
    n1 = arb(7) / 4
    return (b0 / (x * Fp)).sqrt() * coth * T ** (2 * n1) / 2


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def constants() -> list[Check]:
    p, u1 = pi(), arb(1).asinh()
    xs = x1()
    xi = xs * xs / 3
    LV = 12 * p * p / (p * p + 4 * u1 * u1)
    out = [
        Check("Thm 1", "Lambda_V = 12 pi^2 / (pi^2 + 4 arcsinh^2 1)", _fmt(LV), None, "9.1266340", None, "128-bit ball arithmetic"),
        Check("Thm 1", "1 / (1/12 + xi1*), xi1* = x1*^2 / 3", _fmt(1 / (arb(1) / 12 + xi)), None, "9.1266340", None, "128-bit ball arithmetic"),
        Check("Thm 1", "x1* = arcsinh(1)/pi", _fmt(xs), None, "0.2805499", None, "128-bit ball arithmetic"),
        Check("Thm 1", "xi1* = x1*^2 / 3", _fmt(xi), None, "0.0262361", None, "128-bit ball arithmetic"),
        Check("ref", "kappa_tip = 4 * 2^(3/4) / (9 sqrt pi)", _fmt(4 * arb(2) ** (arb(3) / 4) / (9 * p.sqrt())), None, "0.4217111", None, "128-bit ball arithmetic", notes="not certified in the paper either"),
        Check("(4.18)", "A_opt = |a1| arcsinh(1) / (3 sqrt(2) pi^4)^(1/3), a1 = first zero of Ai", _fmt(abs(arb.airy_ai_zero(1)) * u1 / (3 * arb(2).sqrt() * p ** 4) ** (arb(1) / 3)), None, "0.27666", None, "128-bit ball arithmetic", notes="conjectured coefficient of c^(1/3); used by refit.py"),
    ]
    # Agreement of the two forms of Lambda_V: difference must contain 0 and be tiny.
    d = LV - 1 / (arb(1) / 12 + xi)
    out.append(Check("Thm 1", "|Lambda_V - 1/(1/12 + xi1*)|", _fmt(abs(d), 3), "< 1e-30", "equal", bool(abs(d) < arb("1e-30")), "128-bit ball arithmetic"))
    return out


def closed_form_rows() -> list[Check]:
    p = pi()
    L2, L3 = arb(2).log(), arb(3).log()
    I0 = 4 - 3 * L3 + 4 * L2
    u1 = arb(1).asinh()
    return [
        _closed("3", "mu1 = 17 e^4 / 1728 (value at the attained endpoint)", 17 * arb(4).exp() / 1728, ">=", "0.536", "0.53713"),
        _closed("6", "6 - 3 log 2 - 2 log 2pi (j = 1 upper extremum)", 6 - 3 * L2 - 2 * (2 * p).log(), "<=", "0.2449", "0.24480"),
        _closed("6", "I(0) - 2 log 2pi (j = 1 lower extremum)", I0 - 2 * (2 * p).log(), ">=", "-0.1991", "-0.19900"),
        _closed("7", "6 - 4 log 3", 6 - 4 * L3, "<=", "1.606", "1.60555"),
        _closed("7", "e^1.606", arb("1.606").exp(), "<", "5.0", "4.9828"),
        _closed("8", "I(0) = 4 - 3 log 3 + 4 log 2", I0, ">=", "3.476", "3.4767"),
        _closed("10(a)", "e1(0+) = sqrt(2)/24 (limit value only, not the covering)", arb(2).sqrt() / 24, ">=", "0.0589", "0.058926"),
        _closed("10(c)", "2 / sinh(2(u1 - 0.25)) (value at the left end)", 2 / (2 * (u1 - arb("0.25"))).sinh(), "<=", "1.24", "1.22992"),
    ]


def row9(n: int = 4000) -> list[Check]:
    out = []
    lo = arb(2) ** -10
    # [0, 2^-10] in the regularized form, 64 cells.
    reg_hi, reg_lo = None, None
    for i in range(64):
        cell = iv(lo * i / 64, lo * (i + 1) / 64)
        v = row9_first_regularized(cell)
        reg_hi = v.upper() if reg_hi is None or v.upper() > reg_hi else reg_hi
        reg_lo = v.lower() if reg_lo is None or v.lower() < reg_lo else reg_lo
    out.append(Check("9", "1.3 r (log rho_U)'(x1*+r), r in [0, 2^-10], regularized form",
                     f"[{_fmt(reg_lo, 6)}, {_fmt(reg_hi, 6)}]", "<= 0.95", "within 0.65 +- 0.002",
                     bool(reg_hi <= arb("0.95")), "regularized form (no 0/0), 64 cells", 64,
                     notes=f"enclosure inside 0.65 +- 0.002: {bool(reg_lo >= arb('0.648') and reg_hi <= arb('0.652'))}"))
    w, cnt, failed, fl = cover_max_ex(row9_first, lo, arb("0.64"), n, geometric=True, bound="0.95")
    out.append(Check("9", "1.3 r (log rho_U)'(x1*+r), r in [2^-10, 0.64]", f"sup in [{_fmt(fl, 8)}, {_fmt(w, 8)}]", "<= 0.95", "bound obtained 0.9212",
                     not failed and w <= arb("0.95"), f"{n} geometric cells, naive enclosure, adaptive bisection", cnt))
    w, cnt, failed, fl = cover_max_ex(lambda r: dlog_rho_U(x1() + r), arb("0.18"), arb(8), n, bound="3.10")
    out.append(Check("9", "(log rho_U)'(x1*+r), r in [0.18, 8]", f"sup in [{_fmt(fl, 8)}, {_fmt(w, 8)}]", "<= 3.10", "bound obtained 3.0656",
                     not failed and w <= arb("3.10"), f"{n} uniform cells, naive enclosure, adaptive bisection", cnt,
                     notes="r >= 8 is by hand in the paper (Lemma F.1(b)); not checked here"))
    return out


def rows_1_2(n: int = 20000) -> list[Check]:
    xs = x1()
    a = xs + arb("1e-3")
    w1, c1, f1, l1 = cover_max_ex(rho_inf, a, arb(3), n, bound="0.5029", max_depth=8)
    split = int(n * float(((arb("1.33") - a) / (3 - a)).mid()))
    w2, c2, f2, l2 = cover_max_ex(rho_inf, a, arb("1.33"), split, bound="0.41", max_depth=8)
    at3 = rho_inf(arb(3))
    at133 = rho_inf(arb("1.33"))
    return [
        Check("1", "rho_inf on [x1* + 1e-3, 3] (Lemma 7.8)", f"sup in [{_fmt(l1, 8)}, {_fmt(w1, 8)}]", "<= 0.5029", "bound obtained 0.502833",
              not f1 and w1 <= arb("0.5029"), f"{n} uniform cells, naive enclosure, adaptive bisection", c1,
              notes=f"rho_inf(3) = {_fmt(at3, 6)} (paper 0.50271); (x1*, x1* + 1e-3] and x >= 3 are by hand in the paper"),
        Check("2", "rho_inf on [x1* + 1e-3, 1.33]", f"sup in [{_fmt(l2, 8)}, {_fmt(w2, 8)}]", "<= 0.41", "bound obtained 0.39368",
              not f2 and w2 <= arb("0.41"), f"{split} uniform cells, naive enclosure, adaptive bisection", c2,
              notes=f"rho_inf(1.33) = {_fmt(at133, 6)} (paper 0.394)"),
    ]


def row10c(n: int = 2000) -> list[Check]:
    u1 = arb(1).asinh()
    f = lambda z: 2 / (2 * z).sinh()
    w, cnt, failed = cover_max(f, u1 - arb("0.25"), arb(4), n, bound="1.24")
    m, cnt2, failed2 = cover_min(f, u1 - arb("0.25"), arb(4), n)
    return [Check("10(c)", "(log tanh z)' = 2/sinh 2z on [u1 - 0.25, 4]", f"[{_fmt(m, 6)}, {_fmt(w, 6)}]", "in (0, 1.24]",
                  "1.22992 at the left end", not failed and w <= arb("1.24") and m > 0,
                  f"{n} uniform cells, naive enclosure", cnt + cnt2)]


def run_all(fast: bool = False) -> list[Check]:
    k = 4 if fast else 1
    return constants() + closed_form_rows() + row9(n=4000 // k) + rows_1_2(n=20000 // k) + row10c(n=2000 // k)


NOT_REBUILT = {
    "3 (mu4)": "needs h4- of (F.42); value 0.70097 not re-derived",
    "4": "Airy-variable cell functions (F.56)-(F.58)",
    "5": "far-left remainder e_L-hat (F.25), 136856 cells",
    "6 (j = 4)": "needs h4+- of appendix F",
    "8 (G_L, G_R)": "monotonicity coverings of two functions defined after (F.37); only I(0) re-checked",
    "10(a) covering": "e1(delta) on (0, 2] needs a second-order regularized form near 0 (margin 2.6e-5); only e1(0+) re-checked",
    "11": "vacuum ratio and lobe integral (G.15)-(G.17)",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fast", action="store_true", help="quarter the cell counts (still rigorous, looser bounds)")
    args = ap.parse_args(argv)
    checks = run_all(fast=args.fast)
    if args.json:
        print(json.dumps({"checks": [asdict(c) for c in checks], "not_rebuilt": NOT_REBUILT}, indent=2))
    else:
        for c in checks:
            status = "value" if c.certified is None else ("CERTIFIED" if c.certified else "NOT CERTIFIED")
            claim = f" claim {c.claim}" if c.claim else ""
            print(f"[{status:13}] row {c.row:6} {c.name}\n                {c.value}{claim}; paper: {c.printed}; {c.method}"
                  + (f"; {c.cells} cells" if c.cells else "") + (f"\n                note: {c.notes}" if c.notes else ""))
        print("\nNot rebuilt:")
        for k, v in NOT_REBUILT.items():
            print(f"  row {k}: {v}")
    claims = [c for c in checks if c.certified is not None]
    return 0 if all(c.certified for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
