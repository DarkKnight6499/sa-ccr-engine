"""CRIF round trip, dispute reconciliation, trade allocation and compression tests.

The load-bearing checks: SIMM run from CRIF equals SIMM run from trades (same sensitivities, same
answer), and compression never changes the dealer's net book risk.
"""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest
from pytest import approx

from run_saccr import DATA_PATH
from saccr.trades import Trade, load_trades
from simm.crif import CRIF_COLUMNS, compute_simm_im_from_crif, read_crif, trades_to_crif_rows, write_crif
from simm.engine import compute_simm_im
from simm.optimization import (
    compress_multilateral, net_book_sensitivities, rank_netting_sets_for_trade, reconcile_crif,
)

TOL = 1e-9
NETTING_SETS = ["NS-A", "NS-B"]


def _trade(trade_id, netting_set, asset_class, hedging_set, position, notional, maturity_m):
    return Trade(
        trade_id=trade_id, netting_set=netting_set, asset_class=asset_class, hedging_set=hedging_set,
        position=position, style="Linear", opt_type=None, notional=notional, start_s=0.0,
        maturity_m=maturity_m, underlying_price=None, strike=None, vol=None, mtm=0.0, sub_category="NA",
    )


def test_crif_im_matches_trade_level_im_for_sample_book():
    trades = load_trades(DATA_PATH)
    rows = trades_to_crif_rows(trades)
    for ns in NETTING_SETS:
        assert compute_simm_im_from_crif(rows, ns).total_im == approx(compute_simm_im(trades, ns).total_im, rel=TOL)


def test_crif_file_round_trip_preserves_im(tmp_path):
    trades = load_trades(DATA_PATH)
    path = str(tmp_path / "crif.csv")
    write_crif(trades_to_crif_rows(trades), path)
    reread = read_crif(path)
    for ns in NETTING_SETS:
        assert compute_simm_im_from_crif(reread, ns).total_im == approx(compute_simm_im(trades, ns).total_im, rel=TOL)


def test_crif_skips_out_of_scope_asset_classes():
    trades = load_trades(DATA_PATH)
    rows = trades_to_crif_rows(trades)
    in_scope = {t.trade_id for t in trades if t.asset_class in ("IR", "FX")}
    assert {r.trade_id for r in rows} == in_scope


def test_crif_carries_fx_vega_row_only_for_the_option():
    rows = trades_to_crif_rows(load_trades(DATA_PATH))
    vega_rows = [r for r in rows if r.risk_type == "Risk_FXVol"]
    assert [r.trade_id for r in vega_rows] == ["FXOPT-USDJPY-9M"]


def test_read_crif_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(",".join(CRIF_COLUMNS[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="AmountUSD"):
        read_crif(str(path))


def test_reconcile_identical_crifs_has_no_breaks():
    rows = trades_to_crif_rows(load_trades(DATA_PATH))
    result = reconcile_crif(rows, rows, "NS-A")
    assert result.breaks == []
    assert result.im_difference == approx(0.0, abs=TOL)


def test_reconcile_finds_a_notional_mismatch_and_a_missing_trade():
    trades = load_trades(DATA_PATH)
    cp = [t for t in trades if t.trade_id != "IRS-EUR-7Y"]
    cp = [replace(t, notional=40_000_000) if t.trade_id == "IRS-USD-5Y" else t for t in cp]
    result = reconcile_crif(trades_to_crif_rows(trades), trades_to_crif_rows(cp), "NS-A")
    keys = {(b.risk_type, b.qualifier) for b in result.breaks}
    assert ("Risk_IRCurve", "EUR") in keys and ("Risk_IRCurve", "USD") in keys
    usd_5y = next(b for b in result.breaks if b.qualifier == "USD" and b.label1 == "5y")
    assert usd_5y.counterparty_amount == approx(usd_5y.own_amount * 0.8, rel=TOL)  # 40M vs 50M
    assert result.im_difference > 0


def test_rank_puts_the_offsetting_netting_set_first():
    trades = [_trade("A1", "NS-A", "IR", "USD", "Long", 50e6, 5.0), _trade("B1", "NS-B", "IR", "USD", "Short", 50e6, 5.0)]
    candidate = _trade("NEW", "", "IR", "USD", "Short", 20e6, 5.0)
    ranking = rank_netting_sets_for_trade(trades, candidate, NETTING_SETS)
    assert ranking[0][0] == "NS-A" and ranking[0][1] < 0 < ranking[1][1]


def test_compression_tears_up_an_offsetting_pair_and_keeps_net_risk_flat():
    a = _trade("A1", "NS-A", "IR", "USD", "Long", 50e6, 5.0)
    b = _trade("B1", "NS-B", "IR", "USD", "Short", 50e6, 5.0)
    keep = _trade("A2", "NS-A", "IR", "USD", "Long", 10e6, 2.0)
    book = [a, b, keep]
    result = compress_multilateral(book, NETTING_SETS)
    assert [(x, y) for x, y, _ in result.torn_up_pairs] == [("A1", "B1")]
    assert [t.trade_id for t in result.remaining_trades] == ["A2"]
    assert result.im_saving > 0
    before, after = net_book_sensitivities(book), net_book_sensitivities(result.remaining_trades)
    for key in set(before) | set(after):
        assert before.get(key, 0.0) == approx(after.get(key, 0.0), abs=1e-6)


def test_compression_saving_matches_independent_recompute():
    a = _trade("A1", "NS-A", "IR", "USD", "Long", 50e6, 5.0)
    b = _trade("B1", "NS-B", "IR", "USD", "Short", 50e6, 5.0)
    result = compress_multilateral([a, b], NETTING_SETS)
    expected = compute_simm_im([a], "NS-A").total_im + compute_simm_im([b], "NS-B").total_im
    assert result.im_before == approx(expected, rel=TOL)
    assert result.im_after == approx(0.0, abs=TOL)


def test_compression_leaves_non_offsetting_book_alone():
    book = [_trade("A1", "NS-A", "IR", "USD", "Long", 50e6, 5.0), _trade("B1", "NS-B", "IR", "USD", "Long", 50e6, 5.0)]
    result = compress_multilateral(book, NETTING_SETS)
    assert result.torn_up_pairs == [] and result.im_saving == approx(0.0, abs=TOL)


def test_compression_never_pairs_within_one_netting_set():
    book = [_trade("A1", "NS-A", "IR", "USD", "Long", 50e6, 5.0), _trade("A2", "NS-A", "IR", "USD", "Short", 50e6, 5.0)]
    assert compress_multilateral(book, NETTING_SETS).torn_up_pairs == []
