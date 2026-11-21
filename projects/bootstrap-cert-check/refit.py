"""Refit of Hexagon 2611.00174v1 Table 2 against the 2019 fits (arXiv:1903.06272).

Two different things get fitted with the 2019 paper's three forms
(c/A + B1, c/A + B1 + B2/c, c/Lambda + gamma log c + const):

  * the DATA: the 24 rows of Table 2 (Delta_1 extrapolated to P = infinity);
  * the LAW: the paper's conjectured two-term law c/Lambda_V + A_opt c^(1/3),
    sampled densely, with no data at all. This is what the paper's section 5.2
    fits ("not to data but to the exact two-term law") to explain 9.08.

Both are reported side by side with the published 2019 values. Plain numpy
least squares; no claim of rigor (this half is numerics, not certification).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LAMBDA_V = 12 * math.pi ** 2 / (math.pi ** 2 + 4 * math.asinh(1) ** 2)
A_OPT = 0.27666                       # (4.18), printed value
XI1 = (math.asinh(1) / math.pi) ** 2 / 3

# arXiv:1903.06272, Table 1 / section 5.2, window 300 <= c <= 700.
PUBLISHED_2019 = {"const": 9.01, "inv": 9.04, "log": 9.08, "log_gamma": 0.439, "log_const": -0.896}
# Hexagon 2611.00174v1 section 5.2: the same forms fitted to the exact law.
PAPER_LAW_FIT = {"const": 9.004, "inv": 9.043, "log": 9.085, "log_gamma": 0.48,
                 "drift": {"[20,300]": (9.02, 0.28), "[500,4000]": (9.11, 0.71)}}
PAPER_SLOPE_FIT = {"xi1_meas": 0.026240, "xi1_err": 0.000025, "Lambda_meas": 9.1263, "Lambda_err": 0.002}


def load_table2(path: Path | None = None):
    data = json.loads((path or HERE / "data" / "table2.json").read_text())
    rows = data["rows"]
    c = np.array([r["c"] for r in rows], float)
    d = np.array([r["delta1"] for r in rows], float)
    s = np.array([r["sigma"] for r in rows], float)
    return c, d, s


def _design(form: str, c: np.ndarray) -> np.ndarray:
    one = np.ones_like(c)
    cols = {"const": [c, one], "inv": [c, one, 1 / c], "log": [c, np.log(c), one], "cube": [c, c ** (1 / 3), one]}[form]
    return np.vstack(cols).T


def fit_form(c, d, form, lo=-np.inf, hi=np.inf):
    """Fit Delta = c/A + ... on lo <= c <= hi. Returns (A, coefficients, n)."""
    m = (c >= lo) & (c <= hi)
    co = np.linalg.lstsq(_design(form, c[m]), d[m], rcond=None)[0]
    return 1 / co[0], co, int(m.sum())


def law(c):
    return c / LAMBDA_V + A_OPT * c ** (1 / 3)


def law_fit(form, lo, hi, n=4001):
    c = np.linspace(lo, hi, n)
    return fit_form(c, law(c), form)


def slope_fit(c, d, lo=-np.inf, weights=None):
    """Paper (5.2): least squares of t1/c in the basis {1, c^-2/3, c^-1, c^-4/3}.

    t1 = Delta_1 - c/12 up to a constant; any constant shift is absorbed by the
    c^-1 column, so the fitted intercept xi1 does not depend on it.
    """
    m = c >= lo
    cc = c[m]
    y = (d[m] - cc / 12) / cc
    X = np.vstack([np.ones_like(cc), cc ** (-2 / 3), 1 / cc, cc ** (-4 / 3)]).T
    if weights is not None:
        w = weights[m]
        X, y = X * w[:, None], y * w
    xi = np.linalg.lstsq(X, y, rcond=None)[0][0]
    return xi, 1 / (1 / 12 + xi), int(m.sum())


def report():
    c, d, s = load_table2()
    out = {"lambda_v": LAMBDA_V}
    rows = []
    for form in ("const", "inv", "log"):
        A, co, n = fit_form(c, d, form, 300, 700)
        LA, lco, _ = law_fit(form, 300, 700)
        rows.append({"form": form, "published_2019": PUBLISHED_2019[form], "data_fit": A, "law_fit": LA,
                     "paper_law_fit": PAPER_LAW_FIT[form], "n_data": n,
                     **({"gamma_2019": PUBLISHED_2019["log_gamma"], "gamma_data": co[1], "gamma_law": lco[1],
                         "gamma_paper_law": PAPER_LAW_FIT["log_gamma"]} if form == "log" else {})})
    out["window_300_700"] = rows
    drift = []
    for lo, hi in ((24, 300), (300, 700), (700, 2048), (24, 2048)):
        Al, cl, n = fit_form(c, d, "log", lo, hi)
        Ac, _, _ = fit_form(c, d, "cube", lo, hi)
        drift.append({"window": [lo, hi], "n": n, "log_slope": Al, "log_gamma": cl[1], "cube_slope": Ac})
    out["data_window_drift"] = drift
    out["law_window_drift"] = [{"window": [lo, hi], "log_slope": law_fit("log", lo, hi)[0], "log_gamma": law_fit("log", lo, hi)[1][1]}
                               for lo, hi in ((20, 300), (300, 700), (500, 4000))]
    m = (c >= 300) & (c <= 700)
    curve = c / PUBLISHED_2019["log"] + PUBLISHED_2019["log_gamma"] * np.log(c) + PUBLISHED_2019["log_const"]
    out["curve_2019_minus_data_in_window"] = {int(k): float(v) for k, v in zip(c[m], (curve - d)[m])}
    out["curve_2019_minus_data_at_2048"] = float((curve - d)[-1])
    out["slope_fit"] = [{"c_min": lo, **dict(zip(("xi1", "Lambda", "n"), slope_fit(c, d, lo)))} for lo in (24, 48, 64, 96, 128, 192, 256)]
    out["slope_fit_sigma_weighted"] = dict(zip(("xi1", "Lambda", "n"), slope_fit(c, d, weights=c / s)))
    out["paper_slope_fit"] = PAPER_SLOPE_FIT
    out["remainder"] = {int(k): float(v) for k, v in zip(c, d - law(c))}
    out["strict_2019_c1800"] = {"strict_bound": 1800 / 8.956, "table2": float(d[c == 1800][0])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = report()
    if args.json:
        print(json.dumps(r, indent=2))
        return 0
    print(f"Lambda_V = {r['lambda_v']:.7f}\n")
    print("2019 fitting forms on 300 <= c <= 700 (slope A, and gamma for the log form):")
    print(f"  {'form':6} {'2019 published':>15} {'fit to DATA':>12} {'fit to LAW':>11} {'paper (LAW)':>12}")
    for x in r["window_300_700"]:
        print(f"  {x['form']:6} {x['published_2019']:>15.3f} {x['data_fit']:>12.3f} {x['law_fit']:>11.3f} {x['paper_law_fit']:>12.3f}")
        if "gamma_data" in x:
            print(f"  {'gamma':6} {x['gamma_2019']:>15.3f} {x['gamma_data']:>12.3f} {x['gamma_law']:>11.3f} {x['gamma_paper_law']:>12.3f}")
    print("\nWindow drift of the DATA fits (log form vs c^(1/3) form):")
    for x in r["data_window_drift"]:
        print(f"  [{x['window'][0]},{x['window'][1]}] n={x['n']:2}: log slope {x['log_slope']:.3f} (gamma {x['log_gamma']:.3f}), c^(1/3) slope {x['cube_slope']:.3f}")
    print("Window drift of the LAW fits (paper: (9.02, 0.28) on [20,300], about (9.11, 0.71) on [500,4000]):")
    for x in r["law_window_drift"]:
        print(f"  [{x['window'][0]},{x['window'][1]}]: log slope {x['log_slope']:.3f}, gamma {x['log_gamma']:.3f}")
    v = r["curve_2019_minus_data_in_window"]
    print(f"\n2019 curve minus Table 2 on its own window: {min(v.values()):+.3f} to {max(v.values()):+.3f}; at c = 2048: {r['curve_2019_minus_data_at_2048']:+.3f} (paper: 0.22)")
    print("\nSlope fit (5.2), basis {1, c^-2/3, c^-1, c^-4/3}, by lower end of the window (paper: 9.1263 +- 0.002, spread over forms and lower end):")
    for x in r["slope_fit"]:
        print(f"  c >= {x['c_min']:4}: n={x['n']:2}  xi1 = {x['xi1']:.6f}  Lambda = {x['Lambda']:.4f}")
    w = r["slope_fit_sigma_weighted"]
    print(f"  sigma-weighted, all rows: Lambda = {w['Lambda']:.4f}")
    st = r["strict_2019_c1800"]
    print(f"\n2019 strict bound at c = 1800: {st['strict_bound']:.3f} >= Table 2 value {st['table2']:.3f}: {st['strict_bound'] >= st['table2']}")
    rem = r["remainder"]
    print(f"Remainder Delta_1 - c/Lambda_V - A_opt c^(1/3): {rem[24]:+.3f} at c=24, {rem[1800]:+.3f} at 1800, {rem[2048]:+.3f} at 2048")
    return 0


if __name__ == "__main__":
    sys.exit(main())
