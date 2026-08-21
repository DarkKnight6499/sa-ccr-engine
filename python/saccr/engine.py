"""Per-trade SA-CCR waterfall. Mirrors the Calc_Engine sheet.

Pure functions over a Trade + SupervisoryParams -> TradeCalc, no I/O, so each
step (duration, delta, maturity factor) is independently testable.
"""
from dataclasses import dataclass
import math
from scipy.stats import norm

from .params import SupervisoryParams
from .trades import Trade

DURATION_ASSET_CLASSES = ("IR", "Credit")


@dataclass
class TradeCalc:
    trade_id: str
    netting_set: str
    asset_class: str
    hedging_set: str
    maturity_m: float
    delta: float
    mf_unmargined: float
    mf_margined: float
    eff_notional_unmargined: float
    eff_notional_margined: float
    sf: float
    rho: float


def supervisory_duration(trade: Trade) -> float:
    """SD = [exp(-0.05*S) - exp(-0.05*E)] / 0.05. IR/Credit only."""
    return (math.exp(-0.05 * trade.start_s) - math.exp(-0.05 * trade.maturity_m)) / 0.05


def adjusted_notional(trade: Trade) -> float:
    """d = notional x SD for IR/Credit; notional directly for FX/Equity/Commodity."""
    if trade.asset_class in DURATION_ASSET_CLASSES:
        return trade.notional * supervisory_duration(trade)
    return trade.notional


def supervisory_delta(trade: Trade) -> float:
    """+/-1 linear; Black-Scholes N(d1) for options. BIS d279 Annex 4 para 157."""
    if trade.style == "Linear":
        return 1.0 if trade.position == "Long" else -1.0

    d1 = (
        math.log(trade.underlying_price / trade.strike)
        + 0.5 * trade.vol ** 2 * trade.maturity_m
    ) / (trade.vol * math.sqrt(trade.maturity_m))

    if trade.opt_type == "Call":
        return norm.cdf(d1) if trade.position == "Long" else -norm.cdf(d1)
    if trade.opt_type == "Put":
        return -norm.cdf(-d1) if trade.position == "Long" else norm.cdf(-d1)
    raise ValueError(f"Unknown opt_type {trade.opt_type!r} for option trade {trade.trade_id}")


def maturity_factor_unmargined(trade: Trade, params: SupervisoryParams) -> float:
    """MF = sqrt(min(max(M, unmargined_floor), 1))."""
    floored = max(trade.maturity_m, params.unmargined_maturity_floor_yrs)
    return math.sqrt(min(floored, 1.0))


def sf_lookup(trade: Trade, params: SupervisoryParams) -> float:
    return params.sf(trade.asset_class, trade.sub_category)


def rho_lookup(trade: Trade, params: SupervisoryParams) -> float:
    if trade.asset_class in ("IR", "FX"):
        return 0.0
    if trade.asset_class == "Commodity":
        return params.rho_commodity
    return params.rho_index if "Index" in trade.sub_category else params.rho_single_name


def compute_trade_calc(trade: Trade, params: SupervisoryParams) -> TradeCalc:
    d = adjusted_notional(trade)
    delta = supervisory_delta(trade)
    mf_unmarg = maturity_factor_unmargined(trade, params)
    mf_marg = params.maturity_factor_margined

    return TradeCalc(
        trade_id=trade.trade_id,
        netting_set=trade.netting_set,
        asset_class=trade.asset_class,
        hedging_set=trade.hedging_set,
        maturity_m=trade.maturity_m,
        delta=delta,
        mf_unmargined=mf_unmarg,
        mf_margined=mf_marg,
        eff_notional_unmargined=delta * d * mf_unmarg,
        eff_notional_margined=delta * d * mf_marg,
        sf=sf_lookup(trade, params),
        rho=rho_lookup(trade, params),
    )
