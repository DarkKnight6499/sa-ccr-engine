"""Per-counterparty SCVA calculation.

SCVA_c = (1/alpha) * RW_c * sum_NS(M_NS * EAD_NS * DF_NS)
"""
import math
from typing import Iterable

from saccr.trades import Trade

from .counterparty import Counterparty
from .params import BACVAParams


def effective_maturity(trades: Iterable[Trade], netting_set: str) -> float:
    """Notional-weighted average trade maturity for a netting set.

    Proxy for the Basel cashflow-weighted effective maturity (Basel II Annex 4
    para 38-39), used because the sample data carries trade-level
    notional/maturity only, not a full cashflow schedule.
    """
    ns_trades = [t for t in trades if t.netting_set == netting_set]
    total_notional = sum(t.notional for t in ns_trades)
    return sum(t.notional * t.maturity_m for t in ns_trades) / total_notional


def discount_factor(maturity_m: float) -> float:
    """DF_NS = (1 - exp(-0.05*M)) / (0.05*M), non-IMM. Limit as M->0 is 1."""
    if maturity_m == 0:
        return 1.0
    return (1 - math.exp(-0.05 * maturity_m)) / (0.05 * maturity_m)


def compute_scva(
    counterparty: Counterparty,
    trades: Iterable[Trade],
    ead_ns: float,
    params: BACVAParams,
) -> float:
    m_ns = effective_maturity(trades, counterparty.netting_set)
    df_ns = discount_factor(m_ns)
    rw_c = params.rw(counterparty.sector, counterparty.credit_quality)
    return (1 / params.alpha) * rw_c * (m_ns * ead_ns * df_ns)
