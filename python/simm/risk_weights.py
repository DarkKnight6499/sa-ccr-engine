"""Risk weight and correlation lookups for the simplified SIMM IR/FX delta and vega margins.

Source: ISDA SIMM v2.6, public methodology document, isda.org
(isda.org/a/b4ugE/ISDA-SIMM_v2.6_PUBLIC.pdf). This document is freely
downloadable and publishes the full risk-weight and correlation tables; the
ISDA license restricts commercial USE and redistribution of the SIMM
calculation engine in a production margin system, not access to read and
implement the methodology from the public PDF. The values below were fetched
and cross-checked directly against that PDF (paragraphs 33-37 for interest
rate, 66-73 for FX, 88 for the cross-risk-class correlation table).

What is real v2.6 calibration:
- IR risk weights per tenor vertex, all three currency-volatility tables.
- IR vega risk weight (0.23) and IR cross-currency correlation gamma (32%).
- FX risk weight for a regular/regular currency pair (7.4) and FX vega risk
  weight (0.48).
- FX within-bucket cross-currency correlation for a regular/regular pair (50%).
- The IR-FX cross-risk-class correlation (psi = 14%).

What remains a simplification, documented honestly rather than overstated:
- Sensitivities are allocated across at most 2 tenor vertices by linear
  interpolation (simm/engine.py), not the full multi-vertex ladder a real
  risk system would produce from actual curve sensitivities.
- IR delta concentration thresholds (simm/params.py) are an illustrative
  order-of-magnitude figure, not ISDA's published per-currency threshold
  table (Section J), since this module works off notional/maturity proxies,
  not real dealer risk-system sensitivities.
- The FX high-volatility currency group (BRL, RUB, TRY) is modeled in
  ir_risk_weight's currency-group logic but the FX risk weight itself is
  currently a flat 7.4 (regular/regular), since the sample book holds no
  high-volatility-currency FX exposure to exercise the 14.7/21.4 cells.
- FX vega dollarizes each trade's Black-Scholes vega using that trade's own
  market implied volatility, then applies the flat published FX_VEGA_RISK_WEIGHT
  (0.48, para 71) on top. ISDA SIMM's own para 10(b) calibration formula
  (sigma = RW * sqrt(365/14) / alpha) implies a specific regulatory
  volatility for this step, around 9.2%, rather than whatever volatility a
  given trade happens to carry. Using the trade's market vol is a reasonable
  proxy, not an exact para 10(b) reproduction; treat FX_VEGA_RISK_WEIGHT
  itself (the 0.48 constant) as the real, exactly-sourced figure, and the
  vega dollarization step around it as the simplification.
"""
import math

# Standard SIMM tenor vertices (years).
TENOR_VERTICES = [
    ("2w", 2 / 52), ("1m", 1 / 12), ("3m", 0.25), ("6m", 0.5),
    ("1y", 1.0), ("2y", 2.0), ("3y", 3.0), ("5y", 5.0),
    ("10y", 10.0), ("15y", 15.0), ("20y", 20.0), ("30y", 30.0),
]
_TENOR_LABELS = [label for label, _ in TENOR_VERTICES]
_TENOR_YEARS = [years for _, years in TENOR_VERTICES]

# ISDA SIMM v2.6, Table 1: IR risk weights per vertex, regular-volatility currencies
# (USD, EUR, GBP, CHF, AUD, NZD, CAD, SEK, NOK, DKK, HKD, KRW, SGD, TWD).
IR_RISK_WEIGHT_REGULAR = dict(zip(_TENOR_LABELS, [
    109.0, 105.0, 90.0, 71.0, 66.0, 66.0, 64.0, 60.0, 60.0, 61.0, 61.0, 67.0,
]))
# ISDA SIMM v2.6, Table 2: low-volatility currencies (JPY only).
IR_RISK_WEIGHT_LOW_VOL = dict(zip(_TENOR_LABELS, [
    15.0, 18.0, 9.0, 11.0, 13.0, 15.0, 19.0, 23.0, 23.0, 22.0, 22.0, 23.0,
]))
# ISDA SIMM v2.6, Table 3: high-volatility currencies (all others).
IR_RISK_WEIGHT_HIGH_VOL = dict(zip(_TENOR_LABELS, [
    163.0, 109.0, 87.0, 89.0, 102.0, 96.0, 101.0, 97.0, 97.0, 102.0, 106.0, 101.0,
]))

IR_LOW_VOL_CURRENCIES = {"JPY"}
IR_REGULAR_CURRENCIES = {
    "USD", "EUR", "GBP", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK",
    "HKD", "KRW", "SGD", "TWD",
}
# Currencies not listed above default to the high-volatility table (v2.6 para 33(3)).

IR_CROSS_CURRENCY_CORR = 0.32   # ISDA SIMM v2.6 para 37, gamma for aggregating across IR currency buckets
IR_VEGA_RISK_WEIGHT = 0.23      # ISDA SIMM v2.6 para 35

# FX delta risk weight. ISDA SIMM v2.6 para 69: RW depends on the FX volatility
# group of both the currency and the calculation currency; regular/regular =
# 7.4 (percentage points), i.e. 0.074 as the fraction-of-notional this code
# multiplies sensitivities by. The sample book's calculation currency (USD)
# and every traded currency (EUR, GBP, JPY) are all in the "regular" group,
# so only that cell is exercised here; see module docstring.
FX_RISK_WEIGHT_REGULAR_REGULAR = 0.074
FX_HIGH_VOL_CURRENCIES = {"BRL", "RUB", "TRY"}  # ISDA SIMM v2.6 para 67

# FX within-bucket cross-currency correlation. ISDA SIMM v2.6 para 72, the
# regular-calculation-currency table, regular/regular cell = 50%. All FX risk
# factors live in a single SIMM bucket (para 66), so this is the correlation
# used between any two distinct currency risk factors within that one bucket.
FX_WITHIN_BUCKET_CORR = 0.50
FX_VEGA_RISK_WEIGHT = 0.48       # ISDA SIMM v2.6 para 71

IR_FX_CROSS_CLASS_CORR = 0.14    # ISDA SIMM v2.6 para 88, Interest Rate/FX cell


def allocate_to_tenor_vertices(maturity_years: float) -> list[tuple[str, float]]:
    """Allocate a sensitivity to the 1-2 nearest tenor vertices by linear interpolation.

    A closer approximation to SIMM's tenor ladder than dumping the whole
    sensitivity on the single nearest vertex: a trade maturing between two
    vertices gets split between them in proportion to distance. Still a
    simplification of a real risk system's per-vertex curve sensitivities
    (see module docstring).
    """
    if maturity_years <= _TENOR_YEARS[0]:
        return [(_TENOR_LABELS[0], 1.0)]
    if maturity_years >= _TENOR_YEARS[-1]:
        return [(_TENOR_LABELS[-1], 1.0)]
    for i in range(len(_TENOR_YEARS) - 1):
        lo_y, hi_y = _TENOR_YEARS[i], _TENOR_YEARS[i + 1]
        if lo_y <= maturity_years <= hi_y:
            span = hi_y - lo_y
            w_hi = (maturity_years - lo_y) / span if span > 0 else 0.0
            w_lo = 1.0 - w_hi
            return [(_TENOR_LABELS[i], w_lo), (_TENOR_LABELS[i + 1], w_hi)]
    return [(_TENOR_LABELS[-1], 1.0)]  # unreachable given the bounds checks above


def ir_vol_group(currency: str) -> str:
    if currency in IR_LOW_VOL_CURRENCIES:
        return "low"
    if currency in IR_REGULAR_CURRENCIES:
        return "regular"
    return "high"


def ir_risk_weight(currency: str, tenor_label: str) -> float:
    table = {
        "low": IR_RISK_WEIGHT_LOW_VOL,
        "regular": IR_RISK_WEIGHT_REGULAR,
        "high": IR_RISK_WEIGHT_HIGH_VOL,
    }[ir_vol_group(currency)]
    return table[tenor_label]


def fx_vol_group(currency: str) -> str:
    return "high" if currency in FX_HIGH_VOL_CURRENCIES else "regular"


def fx_risk_weight(pair: str, calc_currency: str = "USD") -> float:
    """FX delta risk weight for `pair` (e.g. "EURUSD") against `calc_currency`.

    Only the regular/regular cell (7.4) is implemented; see module docstring.
    """
    return FX_RISK_WEIGHT_REGULAR_REGULAR


def tenor_correlation(t1: float, t2: float) -> float:
    """Distance-decaying tenor correlation, floored at 0.05.

    Approximates the shape of SIMM's tenor correlation matrix (correlation
    falls off with tenor distance) as a closed-form curve rather than the
    full 12x12 published table (v2.6 para 36), which is not yet wired in.
    """
    if t1 == t2:
        return 1.0
    return max(0.05, math.exp(-0.03 * abs(t1 - t2)))
