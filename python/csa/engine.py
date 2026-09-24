"""Daily VM and IM margin call computation against a counterparty's CSA terms."""
from dataclasses import dataclass

from .terms import CSATerms


@dataclass
class MarginCallResult:
    netting_set: str
    counterparty: str
    exposure: float
    required_vm: float
    vm_delta: float
    vm_call: float
    model_im: float
    required_im: float
    im_delta: float
    im_call: float


def compute_vm_call(exposure: float, terms: CSATerms) -> tuple:
    """Two-way symmetric VM required against the (unmargined) threshold, then
    a call/return against what's already posted.

    `exposure` is the GROSS current exposure (V), not already net of
    collateral - this function does that subtraction itself via posted_vm,
    so callers must not pre-net V by C before passing it in (that would
    double-count the posted collateral).

    required_vm > 0 means we should be holding that much collateral from the
    counterparty; required_vm < 0 means we should have posted that much to
    them. Both sides of the threshold band are handled, so a call (we take
    in more) and a return/reverse call (we give back, or post new collateral
    to them) both fall out of the same delta-vs-MTA check.
    """
    if exposure > terms.threshold:
        required = exposure - terms.threshold
    elif exposure < -terms.threshold:
        required = exposure + terms.threshold
    else:
        required = 0.0
    delta = required - terms.posted_vm
    call = delta if abs(delta) >= terms.mta else 0.0
    return required, delta, call


def compute_im_call(model_im: float, terms: CSATerms) -> tuple:
    """required_im = max(model IM, contractual IA floor); call fires only if the delta clears MTA."""
    required = max(model_im, terms.independent_amount)
    delta = required - terms.posted_im
    call = delta if abs(delta) >= terms.mta else 0.0
    return required, delta, call


def compute_margin_call(exposure: float, model_im: float, terms: CSATerms) -> MarginCallResult:
    required_vm, vm_delta, vm_call = compute_vm_call(exposure, terms)
    required_im, im_delta, im_call = compute_im_call(model_im, terms)

    return MarginCallResult(
        netting_set=terms.netting_set,
        counterparty=terms.counterparty,
        exposure=exposure,
        required_vm=required_vm, vm_delta=vm_delta, vm_call=vm_call,
        model_im=model_im, required_im=required_im, im_delta=im_delta, im_call=im_call,
    )
