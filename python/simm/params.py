"""SIMM parameter bundle: concentration thresholds and scope flags.

Concentration thresholds below are illustrative: chosen to be the right
order of magnitude for a mid-size dealer book, not ISDA's published
per-currency/per-pair threshold table (ISDA SIMM v2.6, public methodology
document, isda.org, Section J). Unlike the risk weights and correlations in
simm/risk_weights.py (which use the real published v2.6 figures), the
concentration thresholds stay a simplification because this module derives
sensitivities from notional/maturity proxies, not the actual dealer
risk-system PV01/vega a real threshold lookup expects.
"""
from dataclasses import dataclass, field


@dataclass
class SIMMParams:
    # IR delta concentration threshold, in PV01 (dollars per 1bp), per currency bucket.
    ir_delta_concentration_threshold: float = 150_000.0
    # FX delta concentration threshold, in dollar notional, per currency-pair bucket.
    fx_delta_concentration_threshold: float = 50_000_000.0
    # Vega concentration thresholds, in dollar vega, per bucket.
    ir_vega_concentration_threshold: float = 50_000.0
    fx_vega_concentration_threshold: float = 500_000.0

    curvature_margin_in_scope: bool = False  # curvature risk is out of scope for this module


DEFAULT_PARAMS = SIMMParams()
