"""SIMM CRIF export, IM dispute reconciliation, trade allocation and multilateral compression demo.

Uses the sample portfolio (data/trades_sample.csv) plus a few clearly labelled illustrative trades
added in this script: offsetting trades for the compression demo, and a counterparty CRIF that
omits one trade and mis-books another notional for the dispute demo.

Usage:
    py -3 run_im_optimization.py
"""
import os
from dataclasses import replace

from run_saccr import DATA_PATH
from saccr.trades import Trade, load_trades
from simm.crif import trades_to_crif_rows, write_crif
from simm.optimization import compress_multilateral, net_book_sensitivities, rank_netting_sets_for_trade, reconcile_crif

NETTING_SETS = ["NS-A", "NS-B"]
CRIF_OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crif_own.csv")


def _offset_of(trade: Trade, netting_set: str) -> Trade:
    return replace(
        trade, trade_id=trade.trade_id + "-OFFSET", netting_set=netting_set,
        position="Short" if trade.position == "Long" else "Long", mtm=-trade.mtm,
    )


def build_demo_book() -> list:
    base = load_trades(DATA_PATH)
    by_id = {t.trade_id: t for t in base}
    return base + [_offset_of(by_id["IRS-USD-5Y"], "NS-B"), _offset_of(by_id["FXFWD-EURUSD-1Y"], "NS-B")]


def main():
    book = build_demo_book()

    rows = trades_to_crif_rows(book)
    write_crif(rows, CRIF_OUT_PATH)
    print(f"CRIF: {len(rows)} sensitivity rows written to {CRIF_OUT_PATH}\n")

    print("IM dispute reconciliation, NS-A (counterparty omits IRS-EUR-7Y, books IRS-USD-5Y at 40M not 50M):")
    cp_trades = [t for t in book if t.trade_id != "IRS-EUR-7Y"]
    cp_trades = [replace(t, notional=40_000_000) if t.trade_id == "IRS-USD-5Y" else t for t in cp_trades]
    result = reconcile_crif(rows, trades_to_crif_rows(cp_trades), "NS-A")
    print(f"  own IM {result.own_im:,.2f}  counterparty IM {result.counterparty_im:,.2f}  gap {result.im_difference:,.2f}")
    for b in result.breaks[:5]:
        print(f"  {b.risk_type:<13}{b.qualifier:<8}{b.label1:<5}own {b.own_amount:>14,.2f}  cpty {b.counterparty_amount:>14,.2f}  diff {b.difference:>14,.2f}")

    print("\nTrade allocation, new 20M USD 5Y swap (Short), incremental IM by netting set:")
    candidate = Trade("NEW-IRS-USD-5Y", "", "IR", "USD", "Short", "Linear", None, 20_000_000, 0.0, 5.0,
                      None, None, None, 0.0, "NA")
    for ns, incremental in rank_netting_sets_for_trade(book, candidate, NETTING_SETS):
        print(f"  {ns}: {incremental:>+14,.2f}")

    print("\nMultilateral compression (offsetting cross-netting-set pairs):")
    before_risk = net_book_sensitivities(book)
    comp = compress_multilateral(book, NETTING_SETS)
    after_risk = net_book_sensitivities(comp.remaining_trades)
    for a, b, saving in comp.torn_up_pairs:
        print(f"  tear up {a} + {b}: IM saving {saving:,.2f}")
    print(f"  total IM {comp.im_before:,.2f} -> {comp.im_after:,.2f} (saving {comp.im_saving:,.2f})")
    drift = max((abs(before_risk.get(k, 0.0) - after_risk.get(k, 0.0)) for k in set(before_risk) | set(after_risk)), default=0.0)
    print(f"  max net book sensitivity change after compression: {drift:.6f}")


if __name__ == "__main__":
    main()
