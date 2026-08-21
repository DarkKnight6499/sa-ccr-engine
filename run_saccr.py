"""SA-CCR EAD calculator - CLI entry point.

Loads the sample portfolio, runs all 4 scenarios (actual + hypothetical
opposite margin status per netting set), and prints a Summary-style
comparison table matching the Excel model's Summary sheet.

Usage:
    py -3 run_saccr.py
"""
import os

from saccr.ead import run_scenario
from saccr.engine import compute_trade_calc
from saccr.params import SupervisoryParams
from saccr.trades import load_trades

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trades_sample.csv")


def build_scenarios(csv_path: str = DATA_PATH):
    params = SupervisoryParams()
    trades = load_trades(csv_path)
    trade_calcs = [compute_trade_calc(t, params) for t in trades]

    def calcs_for(netting_set: str):
        return [tc for tc in trade_calcs if tc.netting_set == netting_set]

    def mtm_for(netting_set: str):
        return sum(t.mtm for t in trades if t.netting_set == netting_set)

    v_a = mtm_for("NS-A")
    v_b = mtm_for("NS-B")

    return [
        run_scenario("Actual - Unmargined", "Netting Set A (CORP-001)", calcs_for("NS-A"),
                     v=v_a, c=0, th=0, mta=0, nica=0, margined=False, params=params),
        run_scenario("Hypothetical - Margined", "Netting Set A (CORP-001)", calcs_for("NS-A"),
                     v=v_a, c=0, th=0, mta=250_000, nica=0, margined=True, params=params),
        run_scenario("Actual - Margined", "Netting Set B (BANK-001)", calcs_for("NS-B"),
                     v=v_b, c=400_000, th=0, mta=500_000, nica=300_000, margined=True, params=params),
        run_scenario("Hypothetical - Unmargined", "Netting Set B (BANK-001)", calcs_for("NS-B"),
                     v=v_b, c=0, th=0, mta=0, nica=0, margined=False, params=params),
    ]


def print_summary(scenarios):
    header = f"{'Netting Set':<28}{'Margin Status':<26}{'RC ($)':>15}{'PFE ($)':>18}{'EAD ($)':>18}"
    print(header)
    print("-" * len(header))
    for s in scenarios:
        print(f"{s.netting_set:<28}{s.label:<26}{s.rc:>15,.2f}{s.pfe:>18,.2f}{s.ead:>18,.2f}")


if __name__ == "__main__":
    print_summary(build_scenarios())
