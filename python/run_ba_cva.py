"""BA-CVA capital charge calculator - CLI entry point.

Loads the same sample portfolio SA-CCR uses, takes each netting set's actual
margin-status EAD from run_saccr.py, computes SCVA per counterparty, and
prints the aggregated Reduced BA-CVA capital charge.

Usage:
    py -3 run_ba_cva.py
"""
from ba_cva.aggregation import ba_cva_capital_charge, k_reduced
from ba_cva.counterparty import SAMPLE_COUNTERPARTIES
from ba_cva.engine import compute_scva, discount_factor, effective_maturity
from ba_cva.params import BACVAParams
from run_saccr import DATA_PATH, build_scenarios
from saccr.trades import load_trades

ACTUAL_LABELS = {"NS-A": "Actual - Unmargined", "NS-B": "Actual - Margined"}


def build_scva_results(csv_path: str = DATA_PATH):
    trades = load_trades(csv_path)
    scenarios = {(s.netting_set, s.label): s for s in build_scenarios(csv_path)}
    params = BACVAParams()

    ns_to_label = {"NS-A": "Netting Set A (CORP-001)", "NS-B": "Netting Set B (BANK-001)"}
    results = []
    for cpty in SAMPLE_COUNTERPARTIES:
        scenario = scenarios[(ns_to_label[cpty.netting_set], ACTUAL_LABELS[cpty.netting_set])]
        ead_ns = scenario.ead
        m_ns = effective_maturity(trades, cpty.netting_set)
        df_ns = discount_factor(m_ns)
        scva = compute_scva(cpty, trades, ead_ns, params)
        results.append({
            "counterparty": cpty,
            "ead_ns": ead_ns,
            "m_ns": m_ns,
            "df_ns": df_ns,
            "scva": scva,
        })
    return results, params


def print_summary(results, params: BACVAParams):
    header = f"{'Counterparty':<14}{'Sector':<32}{'RW':>7}{'M (yrs)':>10}{'EAD ($)':>16}{'SCVA ($)':>16}"
    print(header)
    print("-" * len(header))
    for r in results:
        cpty = r["counterparty"]
        rw = params.rw(cpty.sector, cpty.credit_quality)
        print(
            f"{cpty.name:<14}{cpty.sector:<32}{rw:>6.2%}{r['m_ns']:>10.2f}"
            f"{r['ead_ns']:>16,.2f}{r['scva']:>16,.2f}"
        )

    scva_values = [r["scva"] for r in results]
    k = k_reduced(scva_values, params)
    charge = ba_cva_capital_charge(scva_values, params)
    print("-" * len(header))
    print(f"K_reduced: {k:,.2f}")
    print(f"BA-CVA capital charge (discount scalar {params.discount_scalar}): {charge:,.2f}")


if __name__ == "__main__":
    results, params = build_scva_results()
    print_summary(results, params)
