"""Aggregation across counterparties and the final BA-CVA capital charge."""
import math
from typing import Iterable

from .params import BACVAParams


def k_reduced(scva_values: Iterable[float], params: BACVAParams) -> float:
    """K_reduced = sqrt[(rho*sum SCVA_c)^2 + (1-rho^2)*sum SCVA_c^2]."""
    values = list(scva_values)
    sum_scva = sum(values)
    sum_scva_sq = sum(v ** 2 for v in values)
    return math.sqrt(
        (params.rho * sum_scva) ** 2 + (1 - params.rho ** 2) * sum_scva_sq
    )


def ba_cva_capital_charge(scva_values: Iterable[float], params: BACVAParams) -> float:
    """Final charge = discount_scalar * K_reduced."""
    return params.discount_scalar * k_reduced(scva_values, params)
