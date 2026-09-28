"""Initial margin optimization and dispute analysis on top of the SIMM engine.

- reconcile_crif: compare two parties' CRIFs for one portfolio, break the IM gap down by risk factor.
- rank_netting_sets_for_trade: incremental IM of adding a new trade to each candidate netting set,
  cheapest first (trade allocation to optimize margin utilization).
- compress_multilateral: find offsetting trade pairs across netting sets and tear up the ones that
  save IM while leaving the dealer's net risk unchanged.

Compression here is greedy pair tear-up on this engine's IR/FX SIMM, not an LP over a
multi-dealer compression cycle; savings are as good as the illustrative SIMM calibration.
"""
from dataclasses import dataclass, replace

from saccr.trades import Trade

from .crif import CRIFRow, compute_simm_im_from_crif, trades_to_crif_rows
from .engine import compute_simm_im
from .params import SIMMParams

BREAK_TOLERANCE = 1e-6


@dataclass
class FactorBreak:
    risk_type: str
    qualifier: str
    label1: str
    own_amount: float
    counterparty_amount: float

    @property
    def difference(self) -> float:
        return self.own_amount - self.counterparty_amount


@dataclass
class ReconciliationResult:
    portfolio_id: str
    own_im: float
    counterparty_im: float
    breaks: list  # FactorBreak, largest absolute difference first

    @property
    def im_difference(self) -> float:
        return self.own_im - self.counterparty_im


def _net_amounts(rows: list[CRIFRow], portfolio_id: str) -> dict:
    net: dict = {}
    for r in rows:
        if r.portfolio_id == portfolio_id:
            net[r.factor_key] = net.get(r.factor_key, 0.0) + r.amount
    return net


def reconcile_crif(own: list[CRIFRow], counterparty: list[CRIFRow], portfolio_id: str,
                   params: SIMMParams = SIMMParams()) -> ReconciliationResult:
    """Root-cause an IM dispute: net each side's sensitivities per risk factor and list every factor
    where they differ, plus factors present on only one side (a missing or unbooked trade)."""
    own_net, cp_net = _net_amounts(own, portfolio_id), _net_amounts(counterparty, portfolio_id)
    breaks = [
        FactorBreak(rt, q, l1, own_net.get((rt, q, l1), 0.0), cp_net.get((rt, q, l1), 0.0))
        for (rt, q, l1) in sorted(set(own_net) | set(cp_net))
        if abs(own_net.get((rt, q, l1), 0.0) - cp_net.get((rt, q, l1), 0.0)) > BREAK_TOLERANCE
    ]
    breaks.sort(key=lambda b: abs(b.difference), reverse=True)
    return ReconciliationResult(
        portfolio_id,
        compute_simm_im_from_crif(own, portfolio_id, params).total_im,
        compute_simm_im_from_crif(counterparty, portfolio_id, params).total_im,
        breaks,
    )


def rank_netting_sets_for_trade(trades: list[Trade], candidate: Trade, netting_sets: list[str],
                                params: SIMMParams = SIMMParams()) -> list:
    """(netting_set, incremental IM) for booking `candidate` into each netting set, lowest first."""
    ranking = []
    for ns in netting_sets:
        before = compute_simm_im(trades, ns, params).total_im
        after = compute_simm_im(trades + [replace(candidate, netting_set=ns)], ns, params).total_im
        ranking.append((ns, after - before))
    return sorted(ranking, key=lambda item: item[1])


@dataclass
class CompressionResult:
    torn_up_pairs: list      # (trade_id_a, trade_id_b, im_saving)
    im_before: float
    im_after: float
    remaining_trades: list

    @property
    def im_saving(self) -> float:
        return self.im_before - self.im_after


def _total_im(trades: list[Trade], netting_sets: list[str], params: SIMMParams) -> float:
    return sum(compute_simm_im(trades, ns, params).total_im for ns in netting_sets)


def _offsets(a: Trade, b: Trade) -> bool:
    """Same instrument, opposite direction, different netting sets: the dealer is flat on the pair."""
    return (
        a.netting_set != b.netting_set and a.asset_class == b.asset_class
        and a.asset_class in ("IR", "FX") and a.hedging_set == b.hedging_set
        and a.style == b.style == "Linear" and a.position != b.position
        and a.notional == b.notional and a.maturity_m == b.maturity_m
    )


def net_book_sensitivities(trades: list[Trade]) -> dict:
    """Dealer-level net risk per factor across every netting set, used to prove compression is risk-neutral."""
    net: dict = {}
    for r in trades_to_crif_rows(trades):
        net[r.factor_key] = net.get(r.factor_key, 0.0) + r.amount
    return net


def compress_multilateral(trades: list[Trade], netting_sets: list[str],
                          params: SIMMParams = SIMMParams()) -> CompressionResult:
    """Greedily tear up the offsetting cross-netting-set pair with the largest IM saving, repeat
    until no pair saves margin. The dealer's net book risk is unchanged by construction."""
    book = list(trades)
    im_before = im_now = _total_im(book, netting_sets, params)
    torn_up = []
    while True:
        best = None
        for i, a in enumerate(book):
            for b in book[i + 1:]:
                if not _offsets(a, b):
                    continue
                remaining = [t for t in book if t is not a and t is not b]
                saving = im_now - _total_im(remaining, netting_sets, params)
                if saving > BREAK_TOLERANCE and (best is None or saving > best[0]):
                    best = (saving, a, b, remaining)
        if best is None:
            break
        saving, a, b, book = best
        torn_up.append((a.trade_id, b.trade_id, saving))
        im_now -= saving
    return CompressionResult(torn_up, im_before, im_now, book)
