"""Format a MarginCallResult as a daily margin call report."""
from .engine import MarginCallResult


def _direction(call: float, delta: float, leg: str) -> str:
    if call == 0:
        return f"No {leg} call (delta {delta:,.2f} within MTA)"
    if call > 0:
        return f"CALL counterparty for {leg} of {call:,.2f}"
    return f"RETURN {leg} of {-call:,.2f} to counterparty"


def format_margin_call_report(result: MarginCallResult) -> str:
    lines = [
        f"Margin call report - {result.counterparty} ({result.netting_set})",
        f"  Exposure (V, gross MTM): {result.exposure:,.2f}",
        f"  VM required: {result.required_vm:,.2f}  |  VM delta: {result.vm_delta:,.2f}",
        f"  -> {_direction(result.vm_call, result.vm_delta, 'VM')}",
        f"  Model IM: {result.model_im:,.2f}  |  IM required (incl. IA floor): {result.required_im:,.2f}  |  IM delta: {result.im_delta:,.2f}",
        f"  -> {_direction(result.im_call, result.im_delta, 'IM')}",
    ]
    return "\n".join(lines)
