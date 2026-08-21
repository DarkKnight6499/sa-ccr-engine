"""Golden-value tests: the Python port must reproduce SACCR_EAD_Calculator.xlsx's
cached formula results exactly (within floating-point tolerance).

Expected values below were extracted directly from the workbook by loading it
with openpyxl(data_only=True) - i.e. Excel's own computed results, not
independently re-derived - so a pass here proves the Python port matches the
existing, already-correct Excel model.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pytest import approx

from run_saccr import build_scenarios

TOL = 1e-6


def _scenarios():
    return {(s.netting_set, s.label): s for s in build_scenarios()}


def test_ns_a_actual_unmargined():
    s = _scenarios()[("Netting Set A (CORP-001)", "Actual - Unmargined")]
    assert s.rc == approx(475_000, rel=TOL)
    assert s.pfe == approx(5_624_412.02995514, rel=TOL)
    assert s.ead == approx(8_539_176.841937196, rel=TOL)

    assert s.addon.ir == approx(1_411_132.159313427, rel=TOL)
    assert s.addon.fx == approx(1_009_309.2680523146, rel=TOL)
    assert s.addon.credit == approx(385_391.51222367765, rel=TOL)
    assert s.addon.equity == approx(1_759_787.3261363234, rel=TOL)
    assert s.addon.commodity == approx(1_058_791.7642293975, rel=TOL)


def test_ns_a_hypothetical_margined():
    s = _scenarios()[("Netting Set A (CORP-001)", "Hypothetical - Margined")]
    assert s.rc == approx(475_000, rel=TOL)
    assert s.pfe == approx(1_728_340.1285146084, rel=TOL)
    assert s.ead == approx(3_084_676.1799204517, rel=TOL)


def test_ns_b_actual_margined():
    s = _scenarios()[("Netting Set B (BANK-001)", "Actual - Margined")]
    assert s.rc == approx(200_000, rel=TOL)
    assert s.pfe == approx(2_138_880.2103552744, rel=TOL)
    assert s.ead == approx(3_274_432.2944973838, rel=TOL)


def test_ns_b_hypothetical_unmargined():
    s = _scenarios()[("Netting Set B (BANK-001)", "Hypothetical - Unmargined")]
    assert s.rc == approx(470_000, rel=TOL)
    assert s.pfe == approx(7_129_600.701184247, rel=TOL)
    assert s.ead == approx(10_639_440.981657945, rel=TOL)
