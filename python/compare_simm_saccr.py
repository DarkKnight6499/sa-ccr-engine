"""Side-by-side comparison of SIMM Initial Margin vs. SA-CCR's PFE add-on, same book.

SIMM (ISDA's bilateral non-cleared margin model) and SA-CCR (BIS d279's
regulatory capital exposure measure) both size counterparty risk off the same
portfolio, but for different purposes: SIMM sizes collateral to post/receive
against potential future exposure; SA-CCR's PFE add-on sizes a capital
exposure measure. They are not expected to match, and the ratio between them
is the interesting number, not either figure alone.

Trade population caveat: this module's SIMM implementation only covers IR and
FX trades (see simm/aggregation.py's docstring for what else is out of
scope), while SA-CCR's full-book PFE/EAD includes every trade in the netting
set - Credit, Equity, and Commodity too. NS-A has 6 non-IR/FX trades out of
12; NS-B has 2 out of 6. Comparing SIMM's IR/FX-only IM against the full-book
PFE would overstate how much smaller SIMM looks relative to SA-CCR, since
part of that gap is just missing risk classes, not model calibration.

To keep the comparison like-for-like, this module recomputes a second SA-CCR
PFE/EAD using ONLY the IR/FX trades in each netting set (same CSA terms -
margined status, threshold, MTA, NICA - as the actual scenario, since those
apply at the netting-set level, not per trade). The full-book PFE/EAD is
still shown alongside it for context, clearly labeled as covering a larger
trade population.

Usage:
    py -3 compare_simm_saccr.py
"""
from saccr.ead import run_scenario
from saccr.engine import compute_trade_calc
from saccr.params import SupervisoryParams
from saccr.trades import load_trades
from run_saccr import DATA_PATH, build_scenarios
from run_simm import ACTUAL_LABELS, NETTING_SETS, NS_DISPLAY, build_simm_results

IR_FX_ASSET_CLASSES = {"IR", "FX"}


def _ir_fx_scenario(netting_set: str, actual_scenario, csv_path: str = DATA_PATH):
    """Rerun the actual scenario's SA-CCR waterfall restricted to IR/FX trades only.

    Reuses the actual scenario's own CSA terms (margined flag, c, threshold,
    MTA, NICA) since those are netting-set-level facts, not something that
    changes with which subset of trades you're looking at; only the trade
    population feeding the add-on aggregation and MTM sum is filtered.
    """
    params = SupervisoryParams()
    trades = [t for t in load_trades(csv_path) if t.netting_set == netting_set and t.asset_class in IR_FX_ASSET_CLASSES]
    trade_calcs = [compute_trade_calc(t, params) for t in trades]
    v = sum(t.mtm for t in trades)
    return run_scenario(
        label=f"{actual_scenario.label} (IR/FX only)",
        netting_set=netting_set,
        trade_calcs=trade_calcs,
        v=v, c=actual_scenario.c, th=0, mta=0, nica=0,
        margined=actual_scenario.margined,
        params=params,
    )


def build_comparison(csv_path: str = DATA_PATH):
    saccr_scenarios = {(s.netting_set, s.label): s for s in build_scenarios(csv_path)}
    simm_results = build_simm_results(csv_path)

    rows = []
    for ns in NETTING_SETS:
        saccr_full = saccr_scenarios[(NS_DISPLAY[ns], ACTUAL_LABELS[ns])]
        saccr_ir_fx = _ir_fx_scenario(ns, saccr_full, csv_path)
        simm = simm_results[ns]
        rows.append({
            "netting_set": ns,
            "saccr_pfe_full": saccr_full.pfe,
            "saccr_ead_full": saccr_full.ead,
            "saccr_pfe_ir_fx": saccr_ir_fx.pfe,
            "saccr_ead_ir_fx": saccr_ir_fx.ead,
            "simm_im": simm.total_im,
            "ratio_im_to_pfe_ir_fx": simm.total_im / saccr_ir_fx.pfe if saccr_ir_fx.pfe else float("nan"),
            "ratio_im_to_pfe_full": simm.total_im / saccr_full.pfe if saccr_full.pfe else float("nan"),
        })
    return rows


def print_comparison(rows):
    print("SIMM covers IR/FX trades only. Two SA-CCR PFE/EAD figures are shown:")
    print("  IR/FX subset  - same trade population as SIMM, the like-for-like comparison.")
    print("  Full book     - every trade in the netting set (adds Credit/Equity/Commodity); NOT like-for-like with SIMM IM.")
    print()
    header = (
        f"{'Netting Set':<12}{'SIMM IM':>14}"
        f"{'PFE (IR/FX)':>16}{'EAD (IR/FX)':>16}{'IM/PFE (IR/FX)':>16}"
        f"{'PFE (Full)':>16}{'EAD (Full)':>16}{'IM/PFE (Full)':>16}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['netting_set']:<12}{r['simm_im']:>14,.2f}"
            f"{r['saccr_pfe_ir_fx']:>16,.2f}{r['saccr_ead_ir_fx']:>16,.2f}{r['ratio_im_to_pfe_ir_fx']:>16.2f}"
            f"{r['saccr_pfe_full']:>16,.2f}{r['saccr_ead_full']:>16,.2f}{r['ratio_im_to_pfe_full']:>16.2f}"
        )


if __name__ == "__main__":
    print_comparison(build_comparison())
