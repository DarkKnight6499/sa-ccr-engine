"""SIMM aggregation formulas: concentration risk factor, within-bucket margin,
cross-bucket margin, and product-class combination.

Faithfully implemented, against ISDA SIMM v2.6 (public methodology document,
isda.org):
- The concentration risk factor CR_b = max(1, sqrt(|sum sensitivities| / threshold)).
- Within-bucket margin as sum-of-squares plus correlated cross-terms of the
  CR-amplified weighted sensitivities, K_b = sqrt(sum WS_k^2 + sum corr*WS_k*WS_l).
- Bucket net sensitivity S_b clipped to [-K_b, K_b] before it feeds cross-bucket
  aggregation.
- Cross-bucket aggregation including the concentration scaler
  g_bc = min(CR_b, CR_c) / max(CR_b, CR_c) on each cross term.
- Delta-then-vega combination within a risk class, then cross-risk-class
  combination via the published correlation matrix.
- Real v2.6 published risk weights, vega risk weights, and correlations
  (simm/risk_weights.py), not invented placeholders.

Remaining simplifications, not hidden:
- IR delta sensitivities are allocated across at most 2 tenor vertices by
  linear interpolation (simm/engine.py), not a full dealer-risk-system
  tenor ladder.
- No curvature margin (SIMM's second delta-adjacent margin component).
- Only Interest Rate and FX risk classes are implemented; Credit, Equity,
  and Commodity are out of scope.
- FX delta/vega use SIMM's real single-bucket structure (no inter-bucket
  aggregation, per v2.6 para 66), so cross_bucket_margin's g_bc term below
  only actually matters for the IR risk class, which has one bucket per
  currency.
"""
from dataclasses import dataclass
import math


@dataclass
class Sensitivity:
    key: str            # tenor label (IR) or pair name (FX); the risk factor identity within the bucket
    value: float         # signed sensitivity (PV01 for IR delta, notional for FX delta, dollar vega for vega)
    risk_weight: float


@dataclass
class BucketMargin:
    bucket: str
    k: float             # within-bucket margin K_b
    s: float              # bucket net weighted sensitivity, clipped to [-K_b, K_b]
    cr: float             # concentration risk factor applied


def concentration_risk_factor(sensitivities: list[Sensitivity], threshold: float) -> float:
    """CR_b = max(1, sqrt(|sum of raw sensitivities| / threshold))."""
    if threshold <= 0:
        return 1.0
    agg = sum(s.value for s in sensitivities)
    return max(1.0, math.sqrt(abs(agg) / threshold))


def within_bucket_margin(
    sensitivities: list[Sensitivity],
    threshold: float,
    corr_fn,
    bucket: str = "",
) -> BucketMargin:
    """K_b = sqrt(sum WS_k^2 + sum_{k!=l} corr_kl*WS_k*WS_l), WS_k = RW_k*s_k*CR_b.

    `corr_fn(key_i, key_j)` returns the within-bucket correlation between two
    risk factors identified by their Sensitivity.key. CR_b amplifies every
    weighted sensitivity in the bucket, so a concentrated bucket's margin
    grows faster than linearly in the aggregate sensitivity.
    """
    if not sensitivities:
        return BucketMargin(bucket=bucket, k=0.0, s=0.0, cr=1.0)

    cr = concentration_risk_factor(sensitivities, threshold)
    ws = [s.risk_weight * s.value * cr for s in sensitivities]

    sum_sq = sum(w ** 2 for w in ws)
    cross = 0.0
    for i in range(len(sensitivities)):
        for j in range(len(sensitivities)):
            if i == j:
                continue
            cross += corr_fn(sensitivities[i].key, sensitivities[j].key) * ws[i] * ws[j]

    k = math.sqrt(max(sum_sq + cross, 0.0))
    s_net = sum(ws)
    s_clipped = max(min(s_net, k), -k)
    return BucketMargin(bucket=bucket, k=k, s=s_clipped, cr=cr)


def _concentration_scaler(cr_b: float, cr_c: float) -> float:
    """g_bc = min(CR_b, CR_c) / max(CR_b, CR_c). Both CR values are >= 1 by construction."""
    hi = max(cr_b, cr_c)
    if hi <= 0:
        return 1.0
    return min(cr_b, cr_c) / hi


def cross_bucket_margin(bucket_margins: list[BucketMargin], cross_corr: float) -> float:
    """Margin = sqrt(sum K_b^2 + sum_{b!=c} cross_corr * g_bc * S_b * S_c).

    g_bc = min(CR_b, CR_c) / max(CR_b, CR_c) dampens the cross-bucket term
    when one bucket is far more concentrated than the other.
    """
    if not bucket_margins:
        return 0.0
    sum_sq = sum(b.k ** 2 for b in bucket_margins)
    cross = 0.0
    for i in range(len(bucket_margins)):
        for j in range(len(bucket_margins)):
            if i == j:
                continue
            g_bc = _concentration_scaler(bucket_margins[i].cr, bucket_margins[j].cr)
            cross += cross_corr * g_bc * bucket_margins[i].s * bucket_margins[j].s
    return math.sqrt(max(sum_sq + cross, 0.0))


def combine_delta_vega(delta_margin: float, vega_margin: float) -> float:
    """Risk-class margin = DeltaMargin + VegaMargin. Curvature margin is out of scope."""
    return delta_margin + vega_margin


def combine_risk_classes(margin_ir: float, margin_fx: float, cross_class_corr: float) -> float:
    """Product-class IM = sqrt(margin_ir^2 + margin_fx^2 + 2*corr*margin_ir*margin_fx)."""
    return math.sqrt(
        margin_ir ** 2 + margin_fx ** 2
        + 2 * cross_class_corr * margin_ir * margin_fx
    )
