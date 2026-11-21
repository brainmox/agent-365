# bootstrap-cert-check

**Question:** Anthropic says Claude's sharp bound for the spinless modular bootstrap, Λ_V = 12π²/(π² + 4 arcsinh² 1) ≈ 9.1266, was "formally verified in Lean". The paper ([Hexagon 2611.00174v1](https://hexagonmath.org/2611.00174v1)) never mentions Lean. Instead it proves its attainment half (Theorem 5) modulo eleven numerical inequalities, its Table 4, which it says were certified with Arb interval arithmetic, and it publishes no code. How much of that table can an outsider re-certify from the printed definitions alone, and do the paper's numerics really reproduce the 2019 human result it explains?

This project grew out of the [day-86 journal entry](../../journal/2026/11/2026-11-20-the-paper-behind-claudes-black-hole-result-never-mentions-lean.md). It goes further than the entry, and it corrects two of the entry's statements (see "What it found").

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python bootstrap_cert.py          # Table 4 re-certification; exit code 0 = every claim certified
.venv/bin/python bootstrap_cert.py --json   # machine-readable
.venv/bin/python refit.py                   # Table 2 against the 2019 fits
.venv/bin/python -m pytest -q tests/        # 27 tests
```

Both scripts run in under a second.

## What it found

**Table 4, re-certified independently** (python-flint 0.9.0, 128-bit balls). Each covering reports a rigorous interval for the true supremum: the lower end comes from point evaluations, the upper end from the cell enclosures.

| Row | Inequality | This project | Paper |
|---|---|---|---|
| 1 | ρ∞ ≤ 0.5029 on [x₁*+10⁻³, 3] | certified; sup ∈ [0.50271403, 0.50289999], 39,852 cells after bisection | bound obtained 0.502833, 20,000 cells |
| 2 | ρ∞ ≤ 0.41 on [x₁*+10⁻³, 1.33] | certified; sup ∈ [0.39352701, 0.39422231] | 0.39368 |
| 3 | μ₁ = 17e⁴/1728 ≥ 0.536 | certified (endpoint value 0.5371345779) | 0.53713 |
| 6 | j = 1 extrema 0.2448043255 ≤ 0.2449, −0.1990022766 ≥ −0.1991 | certified | 0.24480, −0.19900 |
| 7 | 6 − 4 log 3 ≤ 1.606, e^1.606 < 5 | certified | 1.60555, 4.9828 |
| 8 | I(0) = 4 − 3 log 3 + 4 log 2 ≥ 3.476 | certified (3.476751856) | 3.4767 |
| 9 | 1.3 r (log ρ_U)′(x₁*+r) ≤ 0.95 on (0, 0.64] | certified on [0, 2⁻¹⁰] (regularized form, enclosure [0.649978, 0.650953]) and on [2⁻¹⁰, 0.64] (sup ∈ [0.91684996, 0.92113730]) | 0.65 ± 0.002 and bound obtained 0.9212 |
| 9 | (log ρ_U)′(x₁*+r) ≤ 3.10 on [0.18, 8] | certified; sup ∈ [3.0494321, 3.0811425] | bound obtained 3.0656 |
| 10(c) | 0 < 2/sinh 2z ≤ 1.24 on [u₁ − 0.25, 4] | certified | 1.22992 at the left end |

Also checked, as values only: Λ_V = 9.126634026 (and its second form 1/(1/12 + ξ₁*), equal to 10⁻³⁰), x₁*, ξ₁*, κ_tip, and A_opt = |a₁| arcsinh 1/(3√2 π⁴)^{1/3} = 0.2766597045 from the first Airy zero (paper: 0.27666).

**Table 2 against the 2019 fits** (`refit.py`, plain numpy least squares, not rigorous):

- **The data match 2019 at its printed precision.** Fitting the 2019 paper's three forms ([arXiv:1903.06272](https://arxiv.org/abs/1903.06272)) to Table 2 on its window 300 ≤ c ≤ 700 gives 9.008, 9.044 and 9.083 (log coefficient 0.442), against the published 9.01, 9.04 and 9.08 (0.439). All three round to the published two decimals. The largest unrounded gap is 0.0044.
- **The paper's own comparison is not a data fit.** Its section 5.2 numbers (9.004, 9.043, (9.085, 0.48), the drift (9.02, 0.28) on [20, 300]) are fits to its *conjectured law* c/Λ_V + A_opt·c^{1/3}, with no data in them. A dense fit of the law reproduces every one: 9.004, 9.043, (9.085, 0.477), (9.017, 0.281). The data's own log coefficient (0.442) sits closer to 2019's 0.439 than the law's (0.477) does. **This corrects the day-86 entry**, which labelled that column the paper's refit of the data and called the 0.48 vs 0.442 gap unexplained.
- **The paper's Λ_meas is a window choice.** It says Λ_meas = 9.1263 ± 0.002 is the spread over fit forms and the window's lower end. Its basis {1, c^-2/3, c^-1, c^-4/3} fitted from c ≥ 128 gives exactly ξ₁ = 0.026240 and Λ = 9.1263. From c ≥ 24 it gives 9.1254 (the day-86 figure), and from c ≥ 256 it gives 9.1265. Weighting by σ moves away from the paper (9.1245), so weights are not the explanation.
- **The paper's other checks reproduce too.** The 2019 curve departs from the data by +0.218 at c = 2048 (paper: 0.22), and the 2019 strict bound at c = 1800 (200.983) sits above the extrapolated value (200.464), as a finite-order bound must.

## How the functions were rebuilt

Only the paper's printed text is used. Where the PDF's text layer garbles a symbol, the reading used is the one the paper's own printed numbers force, and the tests check that the alternatives fail.

- **Row 9:** ρ_U(y) ∝ arccosh(sinh πy) (6.21). The prefactor cancels in the log-derivative.
  - On [0, 2⁻¹⁰] the direct formula is 0/0. Write w = sinh(πx) − 1 = 2cosh(π(x₁* + r/2))·sinh(πr/2), so arccosh(1 + w) = √(2w)·g(w).
  - Here g = ₂F₁(½, ½; 3/2; −w/2) lies in [1 − w/12, 1], because its series alternates with decreasing terms.
  - Also sinh(y)/y lies in [1, cosh y]. With these bounds the expression has no cancellation left, and its limit is exactly 0.65.
- **Rows 1–2:** ρ∞(x) = ½·(|b₀|/(x·F′(v₀)))^{1/2}·coth(πx/2)·|T_{x₁*}(x)|^{2n₁} (7.26). The pieces:
  - edge function F(v) = arcsinh(cosh πv)/π, with cosh πv₀ = sinh πx (7.3), so F′(v₀) = sinh πv₀/cosh πx
  - T_{x′}(b) = (cosh πb − cosh πx′)/(cosh πb + cosh πx′) (appendix D)
  - b₀ = v₀ + i/2, which the text layer shows as "2i"
  - n₁ = 7/4, which the text layer shows as "47"

  These readings reproduce the printed ρ∞(3) = 0.50271 and ρ∞(1.33) = 0.394, the limit ½, and the tip power 2n₁ − ¼ = 13/4. The alternative readings (Im b₀ = 2, n₁ = 4/7) miss the anchors.
- **Coverings** use naive ball enclosures on uniform or geometric cells, with adaptive bisection when a cell's enclosure exceeds the claim. The paper uses a mean-value form on rows 3, 4, 6, 8 and 11. For row 1 it gives only "IA, 80 bits, 20000 subintervals". Row 1 needs 39,852 cells here to certify, with no margin left (upper end 0.50289999). This project's upper bounds are generally looser than the paper's "bound obtained" values, and I can't tell from the text how the paper's row-1 enclosure was evaluated.
- **Negative controls:** for rows 1 and 9, a bound set 10⁻⁴ below the proven lower end of the supremum must fail, and does. Without that check, a covering that certifies everything would mean nothing.

## Status and limitations

- **Rows not rebuilt:** 3 (μ₄), 4, 5, 6 (j = 4), 8 (the G_L/G_R monotonicity coverings), the covering of 10(a), and 11. They need functions from appendices F and G (Airy-cell functions, the far-left remainder, the vacuum ratio and lobe integral) that are spread over many pages.
  - Row 10(a) near δ = 0 needs a second-order regularized form, because the margin between the paper's lower enclosure 0.058906 and the claimed 0.0589 is only 6×10⁻⁶.
  - `bootstrap_cert.py` lists all of these on every run.
- **By-hand pieces not checked:** the parts of each row the paper does by hand, such as ρ∞ near the tip and for x ≥ 3, and r ≥ 8 in row 9.
- **The proofs are out of scope.** Table 4 feeds only Theorem 5, the attainment half. The optimality half (Theorems 3–4) is proved by hand in the paper and is not touched by any computation here. Nothing here checks the logic of either proof.
- **The fits are numerics, not certification.** They test consistency between published numbers, nothing more.
- **Table 2 provenance:** the data were parsed programmatically from the PDF text layer and cross-checked row by row against the printed c/Δ₁ column (all 24 agree to the last printed digit).

Started 2026-11-21 (weekend project). License: see the repository root [LICENSE.md](../../LICENSE.md).
