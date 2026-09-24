"""Map trades to SIMM sensitivities and run the delta/vega margin pipeline.

Sensitivity proxies (since trades_sample.csv carries notional/maturity/vol,
not actual dealer risk-system Greeks):
- IR delta: PV01 proxy = notional * supervisory duration * 1bp, reusing
  saccr's own duration function so the same trade data drives both models.
  Allocated across the 1-2 nearest tenor vertices by linear interpolation
  (simm/risk_weights.py's allocate_to_tenor_vertices), not a full ladder.
- FX delta: signed notional exposure to the pair's non-USD currency (see
  _fx_delta_signed_exposure), not the naive Long/Short reading of the
  currency pair itself, all pairs in SIMM's single FX bucket (v2.6 para 66,
  no inter-bucket aggregation).
- FX vega: dollar vega = RiskWeight * implied_vol * BS_vega, volatility-weighted
  per ISDA SIMM's vega margin treatment, for the sample's one FX option trade.
  No IR options are in the sample, so IR vega is computed generically but
  evaluates to zero here.
"""
from dataclasses import dataclass
import math
from scipy.stats import norm

from saccr.engine import supervisory_duration
from saccr.trades import Trade

from .aggregation import Sensitivity, combine_delta_vega, combine_risk_classes, cross_bucket_margin, within_bucket_margin
from .params import SIMMParams
from .risk_weights import (
    IR_CROSS_CURRENCY_CORR, IR_FX_CROSS_CLASS_CORR, IR_VEGA_RISK_WEIGHT,
    FX_WITHIN_BUCKET_CORR, FX_VEGA_RISK_WEIGHT,
    allocate_to_tenor_vertices, fx_risk_weight, ir_risk_weight, tenor_correlation,
)

PV01_SHIFT = 0.0001  # 1 basis point
FX_BUCKET = "FX"  # SIMM v2.6 para 66: all FX sensitivities live in a single bucket


@dataclass
class SIMMResult:
    netting_set: str
    ir_delta_margin: float
    ir_vega_margin: float
    fx_delta_margin: float
    fx_vega_margin: float
    ir_margin: float
    fx_margin: float
    total_im: float


def _signed(trade: Trade) -> float:
    return trade.notional if trade.position == "Long" else -trade.notional


def _fx_delta_signed_exposure(trade: Trade) -> float:
    """Signed notional exposure to the pair's non-USD currency, not to the pair itself.

    SIMM's FX delta risk factor is exposure to each non-USD currency (v2.6
    para 66), not the quoted currency pair. hedging_set is a 6-character
    ticker "CCY1CCY2" (e.g. "EURUSD", "USDJPY"), and every pair in this book
    trades against USD (see module docstring). When USD is the base currency
    (CCY1, e.g. USDJPY), being Long the pair means long USD and short the
    quote currency, so the sign flips relative to the naive Long/Short
    reading: a Short USDJPY position is a LONG JPY exposure. When USD is the
    quote currency (CCY2, e.g. EURUSD), Long the pair already means long the
    non-USD currency, so no flip is needed.
    """
    pair = trade.hedging_set
    base_ccy = pair[:3]
    sign = 1.0 if trade.position == "Long" else -1.0
    if base_ccy == "USD":
        sign = -sign
    return sign * trade.notional


def _ir_delta_pv01(trade: Trade) -> float:
    return _signed(trade) * supervisory_duration(trade) * PV01_SHIFT


def _fx_vega_dollar(trade: Trade) -> float:
    """Volatility-weighted dollar vega: implied_vol * Black-Scholes vega * notional units.

    SIMM's vega margin weights the raw option vega by the risk factor's own
    implied volatility before the SIMM vega risk weight is applied (in
    _group_fx_vega_buckets), rather than treating vega as a flat dollar
    scaling. This uses the trade's own market implied volatility for that
    weighting step, as a proxy for the sigma ISDA SIMM's para 10(b)
    calibration implies for the published vega risk weight; it is not an
    exact reproduction of that calibration formula (see risk_weights.py).
    """
    if trade.style != "Option":
        return 0.0
    d1 = (
        math.log(trade.underlying_price / trade.strike)
        + 0.5 * trade.vol ** 2 * trade.maturity_m
    ) / (trade.vol * math.sqrt(trade.maturity_m))
    bs_vega = trade.underlying_price * norm.pdf(d1) * math.sqrt(trade.maturity_m)
    units = trade.notional / trade.underlying_price
    sign = 1.0 if trade.position == "Long" else -1.0
    return sign * bs_vega * units * trade.vol


def _group_ir_delta_buckets(trades: list[Trade]) -> dict:
    """currency -> list[Sensitivity]; PV01 allocated across nearby tenor vertices."""
    buckets: dict = {}
    for t in [t for t in trades if t.asset_class == "IR"]:
        pv01 = _ir_delta_pv01(t)
        bucket = buckets.setdefault(t.hedging_set, {})
        for tenor, weight in allocate_to_tenor_vertices(t.maturity_m):
            contribution = pv01 * weight
            rw = ir_risk_weight(t.hedging_set, tenor)
            existing = bucket.get(tenor)
            bucket[tenor] = (existing[0] + contribution if existing else contribution, rw)

    return {
        ccy: [Sensitivity(key=tenor, value=val, risk_weight=rw) for tenor, (val, rw) in tenors.items()]
        for ccy, tenors in buckets.items()
    }


def _group_fx_delta_buckets(trades: list[Trade]) -> dict:
    """Single FX bucket -> list[Sensitivity], one per currency pair (net notional).

    SIMM v2.6 para 66: all FX sensitivities sit in one bucket, so there is no
    cross-bucket aggregation step for FX (see _fx_risk_class_margin).
    """
    net: dict = {}
    for t in [t for t in trades if t.asset_class == "FX"]:
        net[t.hedging_set] = net.get(t.hedging_set, 0.0) + _fx_delta_signed_exposure(t)
    if not net:
        return {}
    return {
        FX_BUCKET: [Sensitivity(key=pair, value=val, risk_weight=fx_risk_weight(pair)) for pair, val in net.items()]
    }


def _group_fx_vega_buckets(trades: list[Trade]) -> dict:
    net: dict = {}
    for t in [t for t in trades if t.asset_class == "FX" and t.style == "Option"]:
        net[t.hedging_set] = net.get(t.hedging_set, 0.0) + _fx_vega_dollar(t)
    net = {pair: val for pair, val in net.items() if val != 0.0}
    if not net:
        return {}
    return {
        FX_BUCKET: [Sensitivity(key=pair, value=val, risk_weight=FX_VEGA_RISK_WEIGHT) for pair, val in net.items()]
    }


def _tenor_corr_fn(t1_label: str, t2_label: str) -> float:
    vertex_years = {label: years for label, years in [
        ("2w", 2 / 52), ("1m", 1 / 12), ("3m", 0.25), ("6m", 0.5), ("1y", 1.0),
        ("2y", 2.0), ("3y", 3.0), ("5y", 5.0), ("10y", 10.0), ("15y", 15.0), ("20y", 20.0), ("30y", 30.0),
    ]}
    return tenor_correlation(vertex_years[t1_label], vertex_years[t2_label])


def _fx_within_bucket_corr(key_i: str, key_j: str) -> float:
    """Correlation between two distinct FX currency-pair risk factors in the single FX bucket."""
    return FX_WITHIN_BUCKET_CORR


def _ir_risk_class_margin(buckets: dict, threshold: float, within_corr_fn, cross_corr: float) -> float:
    """IR delta margin: one bucket per currency, combined via cross-bucket aggregation (g_bc included)."""
    bucket_margins = [
        within_bucket_margin(sens, threshold, within_corr_fn, bucket=bucket_key)
        for bucket_key, sens in buckets.items()
    ]
    return cross_bucket_margin(bucket_margins, cross_corr)


def _fx_risk_class_margin(buckets: dict, threshold: float) -> float:
    """FX delta/vega margin: SIMM's single bucket (v2.6 para 66), so the margin
    is that one bucket's K directly - no cross-bucket aggregation step."""
    if not buckets:
        return 0.0
    sensitivities = buckets[FX_BUCKET]
    return within_bucket_margin(sensitivities, threshold, _fx_within_bucket_corr, bucket=FX_BUCKET).k


def compute_simm_im(trades: list[Trade], netting_set: str, params: SIMMParams = SIMMParams()) -> SIMMResult:
    ns_trades = [t for t in trades if t.netting_set == netting_set]

    ir_delta_margin = _ir_risk_class_margin(
        _group_ir_delta_buckets(ns_trades), params.ir_delta_concentration_threshold,
        _tenor_corr_fn, IR_CROSS_CURRENCY_CORR,
    )
    ir_vega_margin = 0.0  # no IR options in the sample portfolio

    fx_delta_margin = _fx_risk_class_margin(
        _group_fx_delta_buckets(ns_trades), params.fx_delta_concentration_threshold,
    )
    fx_vega_margin = _fx_risk_class_margin(
        _group_fx_vega_buckets(ns_trades), params.fx_vega_concentration_threshold,
    )

    ir_margin = combine_delta_vega(ir_delta_margin, ir_vega_margin)
    fx_margin = combine_delta_vega(fx_delta_margin, fx_vega_margin)
    total_im = combine_risk_classes(ir_margin, fx_margin, IR_FX_CROSS_CLASS_CORR)

    return SIMMResult(
        netting_set=netting_set,
        ir_delta_margin=ir_delta_margin, ir_vega_margin=ir_vega_margin,
        fx_delta_margin=fx_delta_margin, fx_vega_margin=fx_vega_margin,
        ir_margin=ir_margin, fx_margin=fx_margin, total_im=total_im,
    )
