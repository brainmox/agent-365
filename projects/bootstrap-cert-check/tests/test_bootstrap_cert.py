"""Tests for bootstrap-cert-check. Run: python -m pytest -q tests/"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flint import arb  # noqa: E402

import bootstrap_cert as bc  # noqa: E402
import refit as rf  # noqa: E402


# --- constants -------------------------------------------------------------

def test_x1_is_exact_tip():
    s = (bc.pi() * bc.x1()).sinh()
    assert abs(s - 1) < arb("1e-35")


def test_lambda_v_value_and_two_forms_agree():
    checks = {c.name: c for c in bc.constants()}
    assert checks["Lambda_V = 12 pi^2 / (pi^2 + 4 arcsinh^2 1)"].value.startswith("9.1266340")
    assert checks["|Lambda_V - 1/(1/12 + xi1*)|"].certified is True


def test_a_opt_matches_printed():
    c = [x for x in bc.constants() if x.row == "(4.18)"][0]
    assert round(float(c.value), 5) == rf.A_OPT == 0.27666


def test_closed_form_rows_all_certify():
    rows = bc.closed_form_rows()
    assert len(rows) == 8
    assert all(r.certified for r in rows), [r.name for r in rows if not r.certified]


# --- reconstruction of rho_inf (rows 1-2) ------------------------------------

def test_rho_inf_reproduces_printed_anchors():
    assert abs(bc.rho_inf(arb(3)) - arb("0.50271")) < arb("5e-6")
    assert abs(bc.rho_inf(arb("1.33")) - arb("0.394")) < arb("5e-4")


def test_rho_inf_tends_to_half():
    assert abs(bc.rho_inf(arb(30)) - arb("0.5")) < arb("1e-4")


def test_rho_inf_tip_power_is_13_over_4():
    # rho_inf ~ K (x - x1*)^(2 n1 - 1/4); log-log slope between two tiny offsets.
    d1, d2 = arb("1e-6"), arb("1e-7")
    r1, r2 = bc.rho_inf(bc.x1() + d1), bc.rho_inf(bc.x1() + d2)
    slope = (r1.log() - r2.log()) / (d1.log() - d2.log())
    assert abs(slope - arb(13) / 4) < arb("1e-3")
    # and the paper's by-hand tip bound rho_inf <= 6 (x - x1*)^(13/4) holds there
    assert r1 <= 6 * d1 ** (arb(13) / 4)


def _rho_variant(x, edge_im, n1):
    p = bc.pi()
    s, c = (p * x).sinh(), (p * x).cosh()
    v0 = s.acosh() / p
    Fp = (s * s - 1).sqrt() / c
    b0 = (v0 * v0 + edge_im * edge_im).sqrt()
    T = (c - arb(2).sqrt()) / (c + arb(2).sqrt())
    return (b0 / (x * Fp)).sqrt() / (p * x / 2).tanh() * T ** (2 * n1) / 2


@pytest.mark.parametrize("edge_im,n1", [(arb(2), arb(7) / 4), (arb(1) / 2, arb(4) / 7), (arb(2), arb(4) / 7)])
def test_other_readings_of_garbled_text_fail_the_anchors(edge_im, n1):
    """The PDF text shows 'b0 = v0 + 2i' and 'n1 = 47'; only i/2 and 7/4 fit."""
    v3 = _rho_variant(arb(3), edge_im, n1)
    v133 = _rho_variant(arb("1.33"), edge_im, n1)
    assert not (abs(v3 - arb("0.50271")) < arb("5e-6") and abs(v133 - arb("0.394")) < arb("5e-4"))


# --- row 9 -------------------------------------------------------------------

def test_regularized_form_matches_direct_form_where_both_work():
    for r in (arb(2) ** -10, arb(2) ** -12, arb("1e-4")):
        direct = bc.row9_first(r)
        reg = bc.row9_first_regularized(r)
        assert reg.overlaps(direct) or abs(reg - direct) < arb("1e-3")
        assert reg.lower() <= direct.upper() + arb("1e-12") and direct.lower() <= reg.upper() + arb("1e-12")


def test_regularized_limit_is_065():
    v = bc.row9_first_regularized(bc.iv(0, arb("1e-12")))
    assert abs(v - arb("0.65")) < arb("1e-9")


def test_arccosh_series_bounds():
    # arccosh(1 + w) = sqrt(2w) g(w) with 1 - w/12 <= g <= 1 for 0 < w < 2
    for w in ("1e-6", "0.01", "0.5", "1.9"):
        w = arb(w)
        g = (1 + w).acosh() / (2 * w).sqrt()
        assert g <= 1 and g >= 1 - w / 12


def test_row9_all_certify():
    rows = bc.row9()
    assert len(rows) == 3 and all(r.certified for r in rows)


# --- coverings: positive and negative controls --------------------------------

def test_rows_1_2_and_10c_certify():
    assert all(r.certified for r in bc.rows_1_2(n=20000))
    assert all(r.certified for r in bc.row10c())


@pytest.mark.parametrize("f,a,b,n,geo", [
    (bc.rho_inf, None, arb(3), 4000, False),
    (bc.row9_first, arb(2) ** -10, arb("0.64"), 1000, True),
    (lambda r: bc.dlog_rho_U(bc.x1() + r), arb("0.18"), arb(8), 1000, False),
])
def test_covering_rejects_a_bound_below_the_true_sup(f, a, b, n, geo):
    """A bound below a rigorous lower bound of the sup must fail: the checker can say no."""
    a = bc.x1() + arb("1e-3") if a is None else a
    _, _, _, floor = bc.cover_max_ex(f, a, b, n, geometric=geo)
    too_low = floor - arb("1e-4")
    _, _, failed, _ = bc.cover_max_ex(f, a, b, n, geometric=geo, bound=too_low, max_depth=4)
    assert failed


def test_floor_is_below_upper():
    w, _, _, floor = bc.cover_max_ex(bc.rho_inf, bc.x1() + arb("1e-3"), arb(3), 2000)
    assert floor <= w


def test_cli_exit_code_zero():
    assert bc.main(["--fast", "--json"]) == 0


# --- refit -------------------------------------------------------------------

def test_table2_has_24_rows_consistent_with_printed_ratio():
    import json
    rows = json.loads((rf.HERE / "data" / "table2.json").read_text())["rows"]
    assert len(rows) == 24
    for r in rows:
        digits = len(r["c_over_delta1_printed"].split(".")[1])
        assert abs(r["c"] / r["delta1"] - float(r["c_over_delta1_printed"])) <= 10 ** -digits


def test_law_fit_reproduces_paper_section_5_2():
    for form, printed in (("const", 9.004), ("inv", 9.043), ("log", 9.085)):
        A, co, _ = rf.law_fit(form, 300, 700)
        assert round(A, 3) == printed
    _, co, _ = rf.law_fit("log", 300, 700)
    assert round(co[1], 2) == 0.48
    A, co, _ = rf.law_fit("log", 20, 300)
    assert (round(A, 2), round(co[1], 2)) == (9.02, 0.28)


def test_data_fit_reproduces_2019_at_its_printed_precision():
    """2019 printed two decimals; the data fits round to exactly those values.
    (The largest unrounded gap is 0.0044, on the c/A + B1 + B2/c form.)"""
    c, d, _ = rf.load_table2()
    gaps = []
    for form in ("const", "inv", "log"):
        A, _, n = rf.fit_form(c, d, form, 300, 700)
        assert n == 7 and round(A, 2) == rf.PUBLISHED_2019[form]
        gaps.append(abs(A - rf.PUBLISHED_2019[form]))
    assert 0.004 < max(gaps) < 0.005


def test_data_log_gamma_is_closer_to_2019_than_the_law():
    c, d, _ = rf.load_table2()
    _, co, _ = rf.fit_form(c, d, "log", 300, 700)
    _, lco, _ = rf.law_fit("log", 300, 700)
    assert abs(co[1] - 0.439) < abs(lco[1] - 0.439)


def test_slope_fit_from_c128_reproduces_paper_5_2():
    c, d, _ = rf.load_table2()
    xi, lam, n = rf.slope_fit(c, d, lo=128)
    assert round(xi, 6) == 0.026240 and round(lam, 4) == 9.1263


def test_2019_curve_departs_by_022_at_2048():
    r = rf.report()
    assert round(r["curve_2019_minus_data_at_2048"], 2) == 0.22
    assert all(0.0 < v < 0.03 for v in r["curve_2019_minus_data_in_window"].values())


def test_strict_2019_bound_sits_above_extrapolated_value():
    r = rf.report()["strict_2019_c1800"]
    assert r["strict_bound"] > r["table2"]
