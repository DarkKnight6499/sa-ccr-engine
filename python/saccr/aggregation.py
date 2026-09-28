"""AddOn aggregation per asset class. Mirrors the AddOn_Aggregation sheet."""
from dataclasses import dataclass, field
import math

from .engine import TradeCalc
from .params import SupervisoryParams


@dataclass
class AddOnBreakdown:
    ir: float = 0.0
    fx: float = 0.0
    credit: float = 0.0
    equity: float = 0.0
    commodity: float = 0.0

    @property
    def aggregate(self) -> float:
        return self.ir + self.fx + self.credit + self.equity + self.commodity


def _eff_notional(tc: TradeCalc, margined: bool) -> float:
    return tc.eff_notional_margined if margined else tc.eff_notional_unmargined


def _ir_addon(trade_calcs: list[TradeCalc], margined: bool, params: SupervisoryParams) -> float:
    """3 maturity buckets (<1y, 1-5y, >5y) per currency hedging set, cross-bucket correlation."""
    ir_trades = [tc for tc in trade_calcs if tc.asset_class == "IR"]
    currencies = sorted({tc.hedging_set for tc in ir_trades})

    total = 0.0
    for ccy in currencies:
        ccy_trades = [tc for tc in ir_trades if tc.hedging_set == ccy]
        sf = ccy_trades[0].sf
        b1 = sum(_eff_notional(tc, margined) for tc in ccy_trades if tc.maturity_m < 1)
        b2 = sum(_eff_notional(tc, margined) for tc in ccy_trades if 1 <= tc.maturity_m <= 5)
        b3 = sum(_eff_notional(tc, margined) for tc in ccy_trades if tc.maturity_m > 5)

        eff_d = math.sqrt(
            b1 ** 2 + b2 ** 2 + b3 ** 2
            + params.ir_adjacent_bucket_coef * b1 * b2
            + params.ir_adjacent_bucket_coef * b2 * b3
            + params.ir_far_bucket_coef * b1 * b3
        )
        total += sf * eff_d
    return total


def _fx_addon(trade_calcs: list[TradeCalc], margined: bool) -> float:
    """Sum by currency-pair hedging set: SF x |sum(EffNotional)| per pair."""
    fx_trades = [tc for tc in trade_calcs if tc.asset_class == "FX"]
    pairs = sorted({tc.hedging_set for tc in fx_trades})

    total = 0.0
    for pair in pairs:
        pair_trades = [tc for tc in fx_trades if tc.hedging_set == pair]
        sf = pair_trades[0].sf
        net_eff = sum(_eff_notional(tc, margined) for tc in pair_trades)
        total += sf * abs(net_eff)
    return total


def _correlated_addon(trade_calcs: list[TradeCalc], asset_class: str, margined: bool) -> float:
    """sqrt[(sum rho_i*SF_i*NetEff_i)^2 + sum((1-rho_i^2)*(SF_i*NetEff_i)^2)].
    Credit/Equity only. Per BIS CRE52, Credit and Equity are each a single
    hedging set per netting set, sub-divided by reference entity; entities
    are netted first, then this correlated formula combines them, recognising
    diversification between entities via rho. (Commodity looks superficially
    similar but is NOT this formula - see _commodity_addon.)"""
    class_trades = [tc for tc in trade_calcs if tc.asset_class == asset_class]
    if not class_trades:
        return 0.0

    hedging_sets = sorted({tc.hedging_set for tc in class_trades})

    sum_rho_sf_eff = 0.0
    sum_unrho_sf_eff2 = 0.0
    for hs in hedging_sets:
        hs_trades = [tc for tc in class_trades if tc.hedging_set == hs]
        rho = hs_trades[0].rho
        sf = hs_trades[0].sf
        net_eff = sum(_eff_notional(tc, margined) for tc in hs_trades)
        sf_eff = sf * net_eff
        sum_rho_sf_eff += rho * sf_eff
        sum_unrho_sf_eff2 += (1 - rho ** 2) * sf_eff ** 2

    return math.sqrt(sum_rho_sf_eff ** 2 + sum_unrho_sf_eff2)


def _commodity_addon(trade_calcs: list[TradeCalc], margined: bool) -> float:
    """Sum by commodity-type hedging set: SF x |NetEff| per hedging set, summed
    across hedging sets with NO diversification benefit between them. Per BIS
    CRE52, Commodity's hierarchy differs from Credit/Equity: hedging sets are
    defined by commodity type (Energy, Metals, Agricultural, Other), trades
    are netted within a hedging set, and hedging-set add-ons are then simply
    summed - not combined via the correlated sqrt formula, which would give
    Oil_Gas and Metal an unearned diversification benefit against each other."""
    class_trades = [tc for tc in trade_calcs if tc.asset_class == "Commodity"]
    hedging_sets = sorted({tc.hedging_set for tc in class_trades})

    total = 0.0
    for hs in hedging_sets:
        hs_trades = [tc for tc in class_trades if tc.hedging_set == hs]
        sf = hs_trades[0].sf
        net_eff = sum(_eff_notional(tc, margined) for tc in hs_trades)
        total += sf * abs(net_eff)
    return total


def aggregate_addon(trade_calcs: list[TradeCalc], margined: bool, params: SupervisoryParams) -> AddOnBreakdown:
    return AddOnBreakdown(
        ir=_ir_addon(trade_calcs, margined, params),
        fx=_fx_addon(trade_calcs, margined),
        credit=_correlated_addon(trade_calcs, "Credit", margined),
        equity=_correlated_addon(trade_calcs, "Equity", margined),
        commodity=_commodity_addon(trade_calcs, margined),
    )
