"""SIMM (Standard Initial Margin Model) calculator - CLI entry point.

Loads the same sample portfolio SA-CCR uses, computes IR/FX delta and vega
margin per netting set, and prints the SIMM IM alongside a daily CSA margin
call report for each netting set.

Risk weight/correlation/threshold VALUES here are illustrative, not the
licensed ISDA SIMM calibration - see simm/__init__.py and the README.

Usage:
    py -3 run_simm.py
"""
import os

from csa.engine import compute_margin_call
from csa.report import format_margin_call_report
from csa.terms import SAMPLE_CSA_TERMS
from run_saccr import build_scenarios
from simm.engine import compute_simm_im
from simm.params import SIMMParams
from saccr.trades import load_trades

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trades_sample.csv")
NETTING_SETS = ["NS-A", "NS-B"]
ACTUAL_LABELS = {"NS-A": "Actual - Unmargined", "NS-B": "Actual - Margined"}
NS_DISPLAY = {"NS-A": "Netting Set A (CORP-001)", "NS-B": "Netting Set B (BANK-001)"}


def build_simm_results(csv_path: str = DATA_PATH, params: SIMMParams = SIMMParams()):
    trades = load_trades(csv_path)
    return {ns: compute_simm_im(trades, ns, params) for ns in NETTING_SETS}


def print_simm_summary(results: dict):
    header = f"{'Netting Set':<12}{'IR Delta':>14}{'IR Vega':>12}{'FX Delta':>14}{'FX Vega':>12}{'IR Margin':>14}{'FX Margin':>14}{'Total IM':>16}"
    print(header)
    print("-" * len(header))
    for ns, r in results.items():
        print(
            f"{ns:<12}{r.ir_delta_margin:>14,.2f}{r.ir_vega_margin:>12,.2f}"
            f"{r.fx_delta_margin:>14,.2f}{r.fx_vega_margin:>12,.2f}"
            f"{r.ir_margin:>14,.2f}{r.fx_margin:>14,.2f}{r.total_im:>16,.2f}"
        )


def print_margin_call_reports(simm_results: dict):
    """One report per SAMPLE_CSA_TERMS entry - NS-A carries no CSA terms (it's
    Unmargined in the actual scenario), so it's excluded, not just zeroed out.

    Passes the GROSS exposure (V) into compute_margin_call; the CSA engine
    nets off posted collateral itself via terms.posted_vm. Passing V-C here
    would double-subtract the same collateral SA-CCR's own `c` already nets
    (they're the same posted VM figure by construction, see csa/terms.py).
    """
    exposures = {(s.netting_set, s.label): s for s in build_scenarios(DATA_PATH)}
    print()
    for terms in SAMPLE_CSA_TERMS:
        scenario = exposures[(NS_DISPLAY[terms.netting_set], ACTUAL_LABELS[terms.netting_set])]
        exposure = scenario.v
        model_im = simm_results[terms.netting_set].total_im
        result = compute_margin_call(exposure, model_im, terms)
        print(format_margin_call_report(result))
        print()


if __name__ == "__main__":
    simm_results = build_simm_results()
    print_simm_summary(simm_results)
    print_margin_call_reports(simm_results)
