"""Counterparty sector/credit-quality assignment.

Not part of the original SA-CCR sample data (which only carries per-trade
notional/maturity/MTM), so this is a new, clearly illustrative assumption
layered on top of the existing sample netting sets - same spirit as that
sample's own "all notionals, MTMs, and CSA terms are illustrative
placeholders" disclaimer.
"""
from dataclasses import dataclass


@dataclass
class Counterparty:
    netting_set: str
    name: str
    sector: str
    credit_quality: str  # "IG" or "HY_NR"


SAMPLE_COUNTERPARTIES = [
    Counterparty("NS-A", "CORP-001", "BasicMaterials_Energy_Industrials", "IG"),
    Counterparty("NS-B", "BANK-001", "Financials", "IG"),
]
