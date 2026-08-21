"""RC, multiplier, PFE, EAD, and the scenario runner that ties the pipeline together."""
from dataclasses import dataclass
import math

from .aggregation import AddOnBreakdown, aggregate_addon
from .engine import TradeCalc
from .params import SupervisoryParams


@dataclass
class ScenarioResult:
    label: str
    netting_set: str
    margined: bool
    v: float
    c: float
    addon: AddOnBreakdown
    multiplier: float
    rc: float
    pfe: float
    ead: float


def replacement_cost(v: float, c: float, th: float, mta: float, nica: float, margined: bool) -> float:
    if margined:
        return max(v - c, th + mta - nica, 0.0)
    return max(v - c, 0.0)


def multiplier(v: float, c: float, addon_aggregate: float, params: SupervisoryParams) -> float:
    if addon_aggregate <= 0:
        return 1.0
    floor = params.multiplier_floor
    exponent = (v - c) / (2 * (1 - floor) * addon_aggregate)
    return min(1.0, floor + (1 - floor) * math.exp(exponent))


def run_scenario(
    label: str,
    netting_set: str,
    trade_calcs: list[TradeCalc],
    v: float,
    c: float,
    th: float,
    mta: float,
    nica: float,
    margined: bool,
    params: SupervisoryParams,
) -> ScenarioResult:
    addon = aggregate_addon(trade_calcs, margined, params)
    mult = multiplier(v, c, addon.aggregate, params)
    rc = replacement_cost(v, c, th, mta, nica, margined)
    pfe = mult * addon.aggregate
    ead = params.alpha * (rc + pfe)

    return ScenarioResult(
        label=label, netting_set=netting_set, margined=margined,
        v=v, c=c, addon=addon, multiplier=mult, rc=rc, pfe=pfe, ead=ead,
    )
