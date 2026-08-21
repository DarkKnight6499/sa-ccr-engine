"""BA-CVA tests.

Unlike test_against_excel.py, there is no external reference workbook here.
Each formula piece is checked against an independently hand-derived value
(not just re-calling the function under test), and the end-to-end SCVA/
K_reduced numbers are recomputed with plain arithmetic in the test itself.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pytest import approx

from ba_cva.aggregation import ba_cva_capital_charge, k_reduced
from ba_cva.counterparty import SAMPLE_COUNTERPARTIES
from ba_cva.engine import compute_scva, discount_factor, effective_maturity
from ba_cva.params import BACVAParams
from run_saccr import DATA_PATH, build_scenarios
from saccr.trades import load_trades

TOL = 1e-6


def test_discount_factor_limit_at_zero_maturity():
    assert discount_factor(0) == 1.0


def test_discount_factor_known_value_at_one_year():
    # DF(1) = (1 - exp(-0.05)) / 0.05, computed independently here.
    expected = (1 - math.exp(-0.05)) / 0.05
    assert discount_factor(1.0) == approx(expected, rel=TOL)


def test_effective_maturity_ns_a_notional_weighted():
    trades = load_trades(DATA_PATH)
    # Hand-summed from trades_sample.csv NS-A rows: sum(notional*M) / sum(notional), in millions.
    # IR: 50*5 + 30*2 + 20*7 = 250+60+140 = 450
    # FX: 15*1 + 10*0.5 + 8*0.75 = 15+5+6 = 26
    # Credit: 12*3 + 25*5 = 36+125 = 161
    # Equity: 6*2 + 10*1 = 12+10 = 22
    # Commodity: 5*1 + 4*2 = 5+8 = 13
    sum_products = 450 + 26 + 161 + 22 + 13
    sum_notional = 50 + 30 + 20 + 15 + 10 + 8 + 12 + 25 + 6 + 10 + 5 + 4
    expected = sum_products / sum_notional
    assert effective_maturity(trades, "NS-A") == approx(expected, rel=TOL)


def test_effective_maturity_ns_b_notional_weighted():
    trades = load_trades(DATA_PATH)
    # IR: 40*10 + 25*3 = 400+75 = 475
    # FX: 18*2 + 12*1 = 36+12 = 48
    # Credit: 15*4 = 60
    # Equity: 20*3 = 60
    sum_products = 475 + 48 + 60 + 60
    sum_notional = 40 + 25 + 18 + 12 + 15 + 20
    expected = sum_products / sum_notional
    assert effective_maturity(trades, "NS-B") == approx(expected, rel=TOL)


def test_scva_and_capital_charge_recomputed_independently():
    trades = load_trades(DATA_PATH)
    scenarios = {(s.netting_set, s.label): s for s in build_scenarios(DATA_PATH)}
    params = BACVAParams()

    actual = {
        "NS-A": scenarios[("Netting Set A (CORP-001)", "Actual - Unmargined")],
        "NS-B": scenarios[("Netting Set B (BANK-001)", "Actual - Margined")],
    }

    scva_values = []
    for cpty in SAMPLE_COUNTERPARTIES:
        ead_ns = actual[cpty.netting_set].ead
        m_ns = effective_maturity(trades, cpty.netting_set)
        df_ns = (1 - math.exp(-0.05 * m_ns)) / (0.05 * m_ns)
        rw_c = params.rw(cpty.sector, cpty.credit_quality)
        expected_scva = (1 / params.alpha) * rw_c * (m_ns * ead_ns * df_ns)

        actual_scva = compute_scva(cpty, trades, ead_ns, params)
        assert actual_scva == approx(expected_scva, rel=TOL)
        scva_values.append(expected_scva)

    expected_k = math.sqrt(
        (params.rho * sum(scva_values)) ** 2
        + (1 - params.rho ** 2) * sum(v ** 2 for v in scva_values)
    )
    expected_charge = params.discount_scalar * expected_k

    assert k_reduced(scva_values, params) == approx(expected_k, rel=TOL)
    assert ba_cva_capital_charge(scva_values, params) == approx(expected_charge, rel=TOL)
