"""CSA margin call tests: hand-computed toy cases for the VM/IM call logic."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pytest import approx

from csa.engine import compute_im_call, compute_margin_call, compute_vm_call
from csa.terms import SAMPLE_CSA_TERMS, CSATerms

TOL = 1e-6


def _terms(threshold=0.0, mta=500_000.0, ia=0.0, posted_vm=0.0, posted_im=0.0):
    return CSATerms(
        netting_set="NS-T", counterparty="TEST-001", threshold=threshold, mta=mta,
        independent_amount=ia, posted_vm=posted_vm, posted_im=posted_im,
    )


def test_vm_call_fires_above_threshold_and_mta():
    terms = _terms(threshold=100_000.0, mta=50_000.0, posted_vm=0.0)
    required, delta, call = compute_vm_call(exposure=900_000.0, terms=terms)
    assert required == approx(800_000.0, rel=TOL)  # 900k - 100k threshold
    assert delta == approx(800_000.0, rel=TOL)
    assert call == approx(800_000.0, rel=TOL)


def test_vm_call_suppressed_when_delta_below_mta():
    terms = _terms(threshold=0.0, mta=500_000.0, posted_vm=1_000_000.0)
    required, delta, call = compute_vm_call(exposure=1_200_000.0, terms=terms)
    assert required == approx(1_200_000.0, rel=TOL)
    assert delta == approx(200_000.0, rel=TOL)
    assert call == 0.0  # 200k delta is below the 500k MTA


def test_vm_call_returns_collateral_when_exposure_drops():
    terms = _terms(threshold=0.0, mta=100_000.0, posted_vm=1_000_000.0)
    required, delta, call = compute_vm_call(exposure=200_000.0, terms=terms)
    assert delta == approx(-800_000.0, rel=TOL)
    assert call == approx(-800_000.0, rel=TOL)  # negative = collateral returned


def test_im_call_uses_ia_floor_when_model_im_is_lower():
    terms = _terms(mta=10_000.0, ia=300_000.0, posted_im=0.0)
    required, delta, call = compute_im_call(model_im=150_000.0, terms=terms)
    assert required == approx(300_000.0, rel=TOL)  # IA floor exceeds model IM
    assert call == approx(300_000.0, rel=TOL)


def test_im_call_uses_model_im_when_it_exceeds_ia_floor():
    terms = _terms(mta=10_000.0, ia=300_000.0, posted_im=0.0)
    required, delta, call = compute_im_call(model_im=450_000.0, terms=terms)
    assert required == approx(450_000.0, rel=TOL)
    assert call == approx(450_000.0, rel=TOL)


def test_compute_margin_call_combines_vm_and_im():
    terms = _terms(threshold=0.0, mta=10_000.0, ia=300_000.0, posted_vm=400_000.0, posted_im=0.0)
    result = compute_margin_call(exposure=1_000_000.0, model_im=250_000.0, terms=terms)
    assert result.vm_call == approx(600_000.0, rel=TOL)   # 1,000,000 - 400,000 posted
    assert result.im_call == approx(300_000.0, rel=TOL)   # max(250k model, 300k IA) - 0 posted


# --- regression test for the collateral double-count fix ---

def test_vm_call_does_not_double_count_posted_collateral_when_passed_gross_exposure():
    """compute_vm_call takes GROSS exposure (V) and nets posted_vm itself.

    Regression for the bug where run_simm.py pre-netted exposure to V-C and
    then compute_vm_call subtracted posted_vm again, understating the true
    delta by exactly the posted collateral amount. With V=470,000 (gross,
    matching NS-B's actual scenario MTM) and posted_vm=400,000, the correct
    delta is +70,000 (below MTA, no call) - not the doubled-subtraction
    -330,000 the old code produced.
    """
    terms = _terms(threshold=0.0, mta=500_000.0, posted_vm=400_000.0)
    required, delta, call = compute_vm_call(exposure=470_000.0, terms=terms)
    assert required == approx(470_000.0, rel=TOL)
    assert delta == approx(70_000.0, rel=TOL)
    assert call == 0.0  # 70,000 is below the 500,000 MTA


def test_no_csa_terms_configured_for_unmargined_netting_set():
    """NS-A is Unmargined in the actual SA-CCR scenario (no real CSA in
    place); it must not appear in SAMPLE_CSA_TERMS, so run_simm.py's report
    loop (which only iterates SAMPLE_CSA_TERMS) never fabricates a margin
    call for it."""
    netting_sets = {t.netting_set for t in SAMPLE_CSA_TERMS}
    assert "NS-A" not in netting_sets
    assert "NS-B" in netting_sets


def test_vm_call_two_way_when_exposure_swings_negative_beyond_threshold():
    """A large negative exposure (we're out of the money) should require
    posting collateral TO the counterparty, not just floor at returning
    whatever we currently hold - the old max(exposure - threshold, 0) formula
    could never go negative, so it was one-way."""
    terms = _terms(threshold=50_000.0, mta=100_000.0, posted_vm=200_000.0)
    required, delta, call = compute_vm_call(exposure=-500_000.0, terms=terms)
    assert required == approx(-450_000.0, rel=TOL)  # -500,000 + 50,000 threshold
    assert delta == approx(-650_000.0, rel=TOL)      # -450,000 - 200,000 posted
    assert call == approx(-650_000.0, rel=TOL)        # return the 200k held, then post 450k more
