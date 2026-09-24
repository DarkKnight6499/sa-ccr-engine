"""SIMM tests.

No external reference exists for these illustrative parameters, so these are
sanity checks (non-negativity, linear scaling below the concentration
threshold) plus a hand-computable toy case for each aggregation formula,
matching the independently-recomputed-value pattern in test_ba_cva.py.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pytest import approx

from run_saccr import DATA_PATH
from saccr.trades import Trade, load_trades
from simm.aggregation import Sensitivity, concentration_risk_factor, cross_bucket_margin, within_bucket_margin
from simm.engine import compute_simm_im
from simm.params import SIMMParams

TOL = 1e-6


def _fx_trade(trade_id, notional, position="Long", hedging_set="EURUSD", maturity_m=1.0):
    return Trade(
        trade_id=trade_id, netting_set="NS-X", asset_class="FX", hedging_set=hedging_set,
        position=position, style="Linear", opt_type=None, notional=notional,
        start_s=0.0, maturity_m=maturity_m, underlying_price=None, strike=None,
        vol=None, mtm=0.0, sub_category="NA",
    )


def _ir_trade(trade_id, notional, position="Long", hedging_set="USD", maturity_m=5.0):
    return Trade(
        trade_id=trade_id, netting_set="NS-X", asset_class="IR", hedging_set=hedging_set,
        position=position, style="Linear", opt_type=None, notional=notional,
        start_s=0.0, maturity_m=maturity_m, underlying_price=None, strike=None,
        vol=None, mtm=0.0, sub_category="NA",
    )


# --- aggregation formula toy cases, hand-computed independently ---

def test_within_bucket_margin_two_factor_toy_case():
    # s1=100 RW1=50 -> WS1=5000; s2=-40 RW2=50 -> WS2=-2000; corr=0.5; CR=1 (below threshold).
    sensitivities = [
        Sensitivity(key="a", value=100.0, risk_weight=50.0),
        Sensitivity(key="b", value=-40.0, risk_weight=50.0),
    ]
    result = within_bucket_margin(sensitivities, threshold=1e12, corr_fn=lambda i, j: 0.5)
    expected_k = math.sqrt(5000.0 ** 2 + (-2000.0) ** 2 + 2 * 0.5 * 5000.0 * -2000.0)
    assert result.k == approx(expected_k, rel=TOL)
    assert result.cr == approx(1.0, rel=TOL)


def test_concentration_risk_factor_above_and_below_threshold():
    below = [Sensitivity(key="a", value=500.0, risk_weight=1.0)]
    above = [Sensitivity(key="a", value=5000.0, risk_weight=1.0)]
    assert concentration_risk_factor(below, threshold=1000.0) == approx(1.0, rel=TOL)
    assert concentration_risk_factor(above, threshold=1000.0) == approx(math.sqrt(5.0), rel=TOL)


def test_within_bucket_margin_concentration_scales_k():
    # Concentration risk factor amplifies K above the threshold: K = |RW*s*CR|, CR > 1.
    threshold = 1000.0
    single = [Sensitivity(key="a", value=4000.0, risk_weight=1.0)]
    result = within_bucket_margin(single, threshold=threshold, corr_fn=lambda i, j: 0.0)
    cr = math.sqrt(4000.0 / threshold)
    assert result.cr == approx(cr, rel=TOL)
    assert result.k == approx(4000.0 * cr, rel=TOL)
    assert result.k > 4000.0  # concentration amplifies the margin above the flat RW*s baseline


def test_cross_bucket_margin_two_bucket_toy_case():
    from simm.aggregation import BucketMargin
    b1 = BucketMargin(bucket="1", k=100.0, s=80.0, cr=1.0)
    b2 = BucketMargin(bucket="2", k=60.0, s=-30.0, cr=1.0)
    result = cross_bucket_margin([b1, b2], cross_corr=0.25)
    expected = math.sqrt(100.0 ** 2 + 60.0 ** 2 + 2 * 0.25 * 80.0 * -30.0)
    assert result == approx(expected, rel=TOL)


# --- engine-level sanity checks ---

def test_simm_im_non_negative_on_sample_portfolio():
    trades = load_trades(DATA_PATH)
    for ns in ("NS-A", "NS-B"):
        result = compute_simm_im(trades, ns)
        assert result.total_im >= 0.0
        assert result.ir_margin >= 0.0
        assert result.fx_margin >= 0.0


def test_simm_im_zero_for_empty_book():
    result = compute_simm_im([], "NS-EMPTY")
    assert result.total_im == 0.0


def test_fx_delta_margin_scales_linearly_below_concentration_threshold():
    params = SIMMParams(fx_delta_concentration_threshold=1e12)  # stays below threshold, CR pinned at 1
    small = [_fx_trade("t1", 1_000_000.0)]
    large = [_fx_trade("t2", 3_000_000.0)]
    r_small = compute_simm_im(small, "NS-X", params)
    r_large = compute_simm_im(large, "NS-X", params)
    assert r_large.fx_delta_margin == approx(3.0 * r_small.fx_delta_margin, rel=TOL)


def test_ir_delta_margin_zero_for_perfectly_offsetting_position():
    # Two identical trades, opposite direction, same tenor bucket -> net PV01 is zero.
    trades = [_ir_trade("t1", 10_000_000.0, "Long"), _ir_trade("t2", 10_000_000.0, "Short")]
    result = compute_simm_im(trades, "NS-X")
    assert result.ir_delta_margin == approx(0.0, abs=1e-6)


# --- regression tests for the reviewer-confirmed bug fixes ---

def test_fx_delta_is_a_single_bucket_with_cross_pair_correlation():
    """Two different FX pairs must land in ONE bucket (SIMM v2.6 para 66: no
    inter-bucket aggregation for FX), so their cross term uses the real
    within-bucket correlation, not the old per-pair-bucket 0-correlation path.
    """
    from simm.engine import _fx_risk_class_margin, _group_fx_delta_buckets
    from simm.risk_weights import FX_WITHIN_BUCKET_CORR, fx_risk_weight

    trades = [_fx_trade("t1", 10_000_000.0, hedging_set="EURUSD"),
              _fx_trade("t2", 6_000_000.0, hedging_set="GBPUSD")]
    buckets = _group_fx_delta_buckets(trades)
    assert list(buckets.keys()) == ["FX"]  # single bucket, not one per pair
    assert len(buckets["FX"]) == 2

    threshold = 1e12  # keep CR pinned at 1 so the hand-computation below is exact
    margin = _fx_risk_class_margin(buckets, threshold)

    rw = fx_risk_weight("EURUSD")
    ws1, ws2 = rw * 10_000_000.0, rw * 6_000_000.0
    expected = math.sqrt(ws1 ** 2 + ws2 ** 2 + 2 * FX_WITHIN_BUCKET_CORR * ws1 * ws2)
    assert margin == approx(expected, rel=TOL)
    # Sanity: this cross-correlated single-bucket margin is strictly less than
    # the sum of the two legs taken independently (diversification benefit
    # that the old one-bucket-per-pair, zero-within-corr model couldn't show).
    assert margin < ws1 + ws2


def test_fx_delta_sign_flips_when_usd_is_the_base_currency():
    """Short USD/JPY is a LONG JPY exposure, not a short-the-pair reading.

    hedging_set "USDJPY" quotes USD as the base currency, so a Short position
    in the pair means short USD and long JPY: the signed exposure to the
    non-USD currency must come out positive even though trade.position is
    Short. A pair quoted the other way round (USD as the quote currency, e.g.
    EURUSD) needs no flip: Long EURUSD already means long EUR.
    """
    from simm.engine import _fx_delta_signed_exposure

    short_usdjpy = _fx_trade("t1", 10_000_000.0, position="Short", hedging_set="USDJPY")
    assert _fx_delta_signed_exposure(short_usdjpy) == approx(10_000_000.0, rel=TOL)

    long_usdjpy = _fx_trade("t2", 10_000_000.0, position="Long", hedging_set="USDJPY")
    assert _fx_delta_signed_exposure(long_usdjpy) == approx(-10_000_000.0, rel=TOL)

    long_eurusd = _fx_trade("t3", 10_000_000.0, position="Long", hedging_set="EURUSD")
    assert _fx_delta_signed_exposure(long_eurusd) == approx(10_000_000.0, rel=TOL)

    short_eurusd = _fx_trade("t4", 10_000_000.0, position="Short", hedging_set="EURUSD")
    assert _fx_delta_signed_exposure(short_eurusd) == approx(-10_000_000.0, rel=TOL)


def test_cross_bucket_margin_concentration_scaler_g_bc():
    """g_bc = min(CR_b, CR_c) / max(CR_b, CR_c) must dampen the cross term
    when the two buckets carry different concentration risk factors."""
    from simm.aggregation import BucketMargin

    b1 = BucketMargin(bucket="1", k=100.0, s=80.0, cr=2.0)
    b2 = BucketMargin(bucket="2", k=60.0, s=-30.0, cr=1.0)
    result = cross_bucket_margin([b1, b2], cross_corr=0.25)
    g_bc = min(2.0, 1.0) / max(2.0, 1.0)  # 0.5
    expected = math.sqrt(100.0 ** 2 + 60.0 ** 2 + 2 * 0.25 * g_bc * 80.0 * -30.0)
    assert result == approx(expected, rel=TOL)
    # Confirm it actually differs from the (wrong) no-scaler formula.
    unscaled = math.sqrt(100.0 ** 2 + 60.0 ** 2 + 2 * 0.25 * 80.0 * -30.0)
    assert result != approx(unscaled, rel=TOL)


def test_fx_vega_is_volatility_weighted_not_flat_scaling():
    """VR = RiskWeight x implied_vol x vega: doubling implied vol on an
    otherwise-identical option must roughly double its FX vega margin
    contribution (raw BS vega also shifts slightly with vol, so this checks
    direction and rough magnitude rather than an exact 2x)."""
    from saccr.trades import Trade

    def _fx_option(vol):
        return Trade(
            trade_id="opt", netting_set="NS-X", asset_class="FX", hedging_set="EURUSD",
            position="Long", style="Option", opt_type="Call", notional=10_000_000.0,
            start_s=0.0, maturity_m=1.0, underlying_price=1.10, strike=1.10,
            vol=vol, mtm=0.0, sub_category="NA",
        )

    low = compute_simm_im([_fx_option(0.08)], "NS-X")
    high = compute_simm_im([_fx_option(0.16)], "NS-X")
    assert high.fx_vega_margin > low.fx_vega_margin
    assert high.fx_vega_margin > 1.5 * low.fx_vega_margin  # scales with vol, not a flat constant
