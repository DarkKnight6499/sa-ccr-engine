"""CSA terms dataclass and the sample netting sets' terms.

Reuses the same CSA terms saccr's margined scenario already carries for
NS-B (actual), so the margin call report is consistent with the exposure
numbers run_saccr.py prints - not a new, disconnected set of assumptions.

NS-A's "Actual" scenario in run_saccr.py is Unmargined (c=0, no threshold/MTA
posted collateral) - it has no real CSA in place, so it is deliberately
absent from this list. A netting set without CSA terms configured should
never generate a margin call; run_simm.py only builds a report for the
netting sets present here.
"""
from dataclasses import dataclass


@dataclass
class CSATerms:
    netting_set: str
    counterparty: str
    threshold: float          # TH: uncollateralized exposure amount, VM leg
    mta: float                 # Minimum Transfer Amount, applies to both VM and IM calls
    independent_amount: float  # IA: contractual minimum IM floor, independent of the model IM
    posted_vm: float           # VM currently held (positive) or posted to the counterparty (negative) going into today
    posted_im: float           # IM currently held/posted going into today


SAMPLE_CSA_TERMS = [
    CSATerms(
        netting_set="NS-B", counterparty="BANK-001",
        threshold=0.0, mta=500_000.0, independent_amount=300_000.0,
        posted_vm=400_000.0, posted_im=0.0,
    ),
]
