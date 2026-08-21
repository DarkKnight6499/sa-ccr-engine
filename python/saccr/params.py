"""Supervisory parameters from BIS d279, Annex 4.

Mirrors the Supervisory_Params sheet in SACCR_EAD_Calculator.xlsx. Defaults
match that workbook exactly; override the dataclass fields for what-if
analysis the same way the Excel's blue editable cells are used.
"""
from dataclasses import dataclass, field
import math


@dataclass
class SupervisoryParams:
    # Supervisory factors (SF), keyed by (asset_class, sub_category). BIS d279 Annex 4, Table 2.
    supervisory_factor: dict = field(default_factory=lambda: {
        ("IR", "NA"): 0.005,             # Flat factor, all currencies/tenors
        ("FX", "NA"): 0.04,              # Flat factor, all currency pairs
        ("Credit", "BBB"): 0.0054,       # Single-name, investment grade (BBB)
        ("Credit", "IG_Index"): 0.0038,  # Credit index, investment grade
        ("Credit", "SubIG_Index"): 0.0106,  # Credit index, sub-investment grade
        ("Equity", "SingleName"): 0.32,
        ("Equity", "Index"): 0.20,
        ("Commodity", "Oil_Gas"): 0.18,
        ("Commodity", "Metal"): 0.18,
    })

    # Regulatory constants
    alpha: float = 1.4                    # BIS d279 para 121
    multiplier_floor: float = 0.05        # BIS d279 para 149

    # IR cross-bucket correlation coefficients, applied doubled (2x) directly
    # in the sum-of-squares expansion, matching the Excel's SQRT formula.
    ir_adjacent_bucket_corr: float = 0.7      # raw correlation, buckets 1-2 / 2-3
    ir_far_bucket_corr: float = 0.3           # raw correlation, buckets 1-3

    # Single-name vs index correlation, credit/equity. BIS d279 para 188 (credit), 190 (equity).
    rho_single_name: float = 0.5
    rho_index: float = 0.8
    rho_commodity: float = 0.4                # BIS d279 para 192, all commodity types

    mpor_floor_bd: int = 10                   # MPOR floor, business days. BIS d279 para 164.
    unmargined_maturity_floor_bd: int = 10    # Unmargined maturity floor, business days. BIS d279 para 159.
    business_days_per_year: int = 250

    @property
    def ir_adjacent_bucket_coef(self) -> float:
        return 2 * self.ir_adjacent_bucket_corr

    @property
    def ir_far_bucket_coef(self) -> float:
        return 2 * self.ir_far_bucket_corr

    @property
    def unmargined_maturity_floor_yrs(self) -> float:
        return self.unmargined_maturity_floor_bd / self.business_days_per_year

    @property
    def mpor_floor_yrs(self) -> float:
        return self.mpor_floor_bd / self.business_days_per_year

    @property
    def maturity_factor_margined(self) -> float:
        """Flat MF for all margined trades: 1.5 x sqrt(MPOR/1yr)."""
        return 1.5 * math.sqrt(self.mpor_floor_yrs)

    def sf(self, asset_class: str, sub_category: str) -> float:
        return self.supervisory_factor[(asset_class, sub_category)]
