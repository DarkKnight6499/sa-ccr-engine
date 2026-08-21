"""Supervisory parameters for BA-CVA (Basic Approach for CVA).

Sources (cross-verified 2026-08-21):
- Clarus Financial Technology, "FRTB - Basic Approach for CVA"
  https://www.clarusft.com/frtb-basic-approach-for-cva/
- OSFI CAR 2026, Chapter 8 - Credit Valuation Adjustment (CVA) Risk
  https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/capital-adequacy-requirements-car-2026-chapter-8-credit-valuation-adjustment-cva-risk
"""
from dataclasses import dataclass, field


@dataclass
class BACVAParams:
    alpha: float = 1.4                  # Same supervisory constant as SA-CCR's EAD formula
    rho: float = 0.5                    # Supervisory correlation between any two counterparties' credit spreads
    discount_scalar: float = 0.65       # DS_BA-CVA, applied to K_reduced for the final capital charge

    # Risk weight (RW_c), keyed by (sector, credit_quality). credit_quality is "IG" or "HY_NR".
    risk_weight: dict = field(default_factory=lambda: {
        ("Sovereigns_CentralBanks", "IG"): 0.005,
        ("Sovereigns_CentralBanks", "HY_NR"): 0.020,
        ("LocalGovernment_Education", "IG"): 0.010,
        ("LocalGovernment_Education", "HY_NR"): 0.040,
        ("Financials", "IG"): 0.050,
        ("Financials", "HY_NR"): 0.120,
        ("BasicMaterials_Energy_Industrials", "IG"): 0.030,
        ("BasicMaterials_Energy_Industrials", "HY_NR"): 0.070,
        ("ConsumerGoods_Transportation", "IG"): 0.030,
        ("ConsumerGoods_Transportation", "HY_NR"): 0.085,
        ("Technology_Telecom", "IG"): 0.020,
        ("Technology_Telecom", "HY_NR"): 0.055,
        ("Healthcare_Utilities", "IG"): 0.015,
        ("Healthcare_Utilities", "HY_NR"): 0.050,
        ("Other", "IG"): 0.050,
        ("Other", "HY_NR"): 0.120,
    })

    def rw(self, sector: str, credit_quality: str) -> float:
        return self.risk_weight[(sector, credit_quality)]
