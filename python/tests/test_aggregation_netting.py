"""Unit tests for per-hedging-set netting in AddOn aggregation (BIS CRE52):
_correlated_addon (Credit/Equity) and _commodity_addon (Commodity - a
different cross-hedging-set rule, see its docstring). The existing
golden-Excel tests in test_against_excel.py barely exercise either path: the
sample portfolio has exactly one trade per hedging set in every asset class
here, so within-hedging-set netting is a no-op there, and NS-A's two
commodity hedging sets (Oil_Gas, Metal) only reveal a cross-hedging-set bug,
not a within-hedging-set one. These tests use multiple trades per hedging set
so the netting/correlation behavior actually gets exercised.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pytest import approx

from saccr.aggregation import _correlated_addon, _commodity_addon
from saccr.engine import TradeCalc

SF = 0.0054
RHO = 0.5


def _tc(hedging_set, eff_notional, asset_class="Credit", sf=SF, rho=RHO):
    return TradeCalc(
        trade_id="x", netting_set="NS", asset_class=asset_class, hedging_set=hedging_set,
        maturity_m=3.0, delta=1.0, mf_unmargined=1.0, mf_margined=1.0,
        eff_notional_unmargined=eff_notional, eff_notional_margined=eff_notional,
        sf=sf, rho=rho,
    )


def test_offsetting_trades_in_same_hedging_set_net_before_correlation():
    trades = [_tc("Corp_ABC", 10_000_000), _tc("Corp_ABC", -9_000_000)]
    addon = _correlated_addon(trades, "Credit", margined=False)

    net_eff = 10_000_000 - 9_000_000  # netted within the hedging set first
    sf_eff = SF * net_eff
    expected = math.sqrt((RHO * sf_eff) ** 2 + (1 - RHO ** 2) * sf_eff ** 2)
    assert addon == approx(expected)

    # The bug: applying the correlated formula per-trade instead of per-
    # hedging-set is mathematically equivalent to putting each trade in its
    # own hedging set - confirm that gives a materially different (larger)
    # number, so this test would have caught the regression.
    unnetted_equivalent = [_tc("Corp_A", 10_000_000), _tc("Corp_B", -9_000_000)]
    addon_if_not_netted = _correlated_addon(unnetted_equivalent, "Credit", margined=False)
    assert addon_if_not_netted > addon * 5


def test_commodity_nets_within_hedging_set_and_sums_across_hedging_sets():
    """Real NS-A commodity book: one Oil_Gas trade, one Metal trade, SF=0.18
    both, rho=0.4. Per BIS CRE52, Commodity hedging sets (here, one per trade)
    are netted internally then simply summed - no cross-hedging-set
    diversification. Correct AddOn = 0.18*5,000,000 + 0.18*4,000,000 =
    1,620,000. The pre-fix code applied the Credit/Equity correlated formula
    here instead, understating it at 1,058,791.76 - about 35% too low."""
    trades = [
        _tc("Oil_Gas", 5_000_000, asset_class="Commodity", sf=0.18, rho=0.4),
        _tc("Metal", -4_000_000, asset_class="Commodity", sf=0.18, rho=0.4),
    ]
    addon = _commodity_addon(trades, margined=False)
    assert addon == approx(1_620_000.0)

    # Netting within a hedging set still happens: two offsetting Oil_Gas
    # trades should net to a small residual, not sum their absolute SF*Eff.
    netted_trades = [
        _tc("Oil_Gas", 5_000_000, asset_class="Commodity", sf=0.18, rho=0.4),
        _tc("Oil_Gas", -4_800_000, asset_class="Commodity", sf=0.18, rho=0.4),
    ]
    netted_addon = _commodity_addon(netted_trades, margined=False)
    assert netted_addon == approx(0.18 * 200_000)
