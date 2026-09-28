"""Golden-value tests: the Python port must reproduce SACCR_EAD_Calculator.xlsx's
cached formula results exactly (within floating-point tolerance).

Expected values below were extracted directly from the workbook by loading it
with openpyxl(data_only=True) - i.e. Excel's own computed results, not
independently re-derived - so a pass here proves the Python port matches the
existing, already-correct Excel model.

Exception: NS-A's commodity AddOn (and the PFE/EAD values that depend on it)
were deliberately changed to values that do NOT match the Excel workbook.
The Excel model applies the Credit/Equity-style correlated-hedging-set formula
to Commodity too, which per BIS CRE52 is wrong for Commodity (see
_commodity_addon in saccr/aggregation.py) - it lets Oil_Gas and Metal diversify
against each other, which Basel does not allow. The Excel workbook has this
same bug and was NOT fixed, so this is a documented, intentional divergence
from the "reference" model, not a mismatch to chase.
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
    # pfe/ead independently recomputed post-fix - see module docstring
    assert s.pfe == approx(6_185_620.265725743, rel=TOL)
    assert s.ead == approx(9_324_868.372016039, rel=TOL)

    assert s.addon.ir == approx(1_411_132.159313427, rel=TOL)
    assert s.addon.fx == approx(1_009_309.2680523146, rel=TOL)
    assert s.addon.credit == approx(385_391.51222367765, rel=TOL)
    assert s.addon.equity == approx(1_759_787.3261363234, rel=TOL)
    # Independently recomputed (sum of hedging-set AddOns, no cross-hedging-set
    # diversification): Oil_Gas SF*|NetEff| = 0.18*5,000,000 = 900,000; Metal =
    # 0.18*4,000,000 = 720,000; sum = 1,620,000. Was 1,058,791.76 (Excel's
    # value) before the fix - see module docstring.
    assert s.addon.commodity == approx(1_620_000.0, rel=TOL)


def test_ns_a_hypothetical_margined():
    s = _scenarios()[("Netting Set A (CORP-001)", "Hypothetical - Margined")]
    assert s.rc == approx(475_000, rel=TOL)
    # pfe/ead independently recomputed post-fix - see module docstring
    assert s.pfe == approx(1_896_702.599245789, rel=TOL)
    assert s.ead == approx(3_320_383.6389441043, rel=TOL)


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
