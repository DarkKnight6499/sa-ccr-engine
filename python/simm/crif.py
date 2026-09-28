"""CRIF (Common Risk Interchange Format) generation, parsing, and SIMM-from-CRIF.

CRIF is the flat file both counterparties exchange so each side can run SIMM on the same
sensitivities and reconcile any initial margin difference. One row per trade per risk factor.

Simplifications versus the full ISDA CRIF spec: only ProductClass RatesFX and the risk types
Risk_IRCurve, Risk_FX and Risk_FXVol are produced; the IR sub-curve (Label2) is left blank since
the engine models one curve per currency; the FX Qualifier carries the currency pair, the
engine's own risk-factor key, rather than a single currency; every amount is USD.
"""
import csv
from dataclasses import dataclass

from saccr.trades import Trade

from .engine import (
    FX_BUCKET, SIMMResult, _fx_delta_signed_exposure, _fx_vega_dollar, _ir_delta_pv01,
    compute_simm_im_from_buckets,
)
from .aggregation import Sensitivity
from .params import SIMMParams
from .risk_weights import FX_VEGA_RISK_WEIGHT, allocate_to_tenor_vertices, fx_risk_weight, ir_risk_weight

PRODUCT_CLASS = "RatesFX"
RISK_IR = "Risk_IRCurve"
RISK_FX = "Risk_FX"
RISK_FX_VOL = "Risk_FXVol"
AMOUNT_CURRENCY = "USD"
CRIF_COLUMNS = [
    "TradeID", "PortfolioID", "ProductClass", "RiskType", "Qualifier", "Bucket",
    "Label1", "Label2", "Amount", "AmountCurrency", "AmountUSD",
]


@dataclass(frozen=True)
class CRIFRow:
    trade_id: str
    portfolio_id: str
    product_class: str
    risk_type: str
    qualifier: str
    bucket: str
    label1: str
    label2: str
    amount: float

    def as_dict(self) -> dict:
        return {
            "TradeID": self.trade_id, "PortfolioID": self.portfolio_id,
            "ProductClass": self.product_class, "RiskType": self.risk_type,
            "Qualifier": self.qualifier, "Bucket": self.bucket, "Label1": self.label1,
            "Label2": self.label2, "Amount": repr(float(self.amount)),
            "AmountCurrency": AMOUNT_CURRENCY, "AmountUSD": repr(float(self.amount)),
        }

    @property
    def factor_key(self) -> tuple:
        return (self.risk_type, self.qualifier, self.label1)


def trades_to_crif_rows(trades: list[Trade]) -> list[CRIFRow]:
    """One CRIF row per trade per SIMM risk factor. Credit/Equity/Commodity trades are skipped
    (out of scope for this SIMM implementation)."""
    rows = []
    for t in trades:
        if t.asset_class == "IR":
            pv01 = _ir_delta_pv01(t)
            for tenor, weight in allocate_to_tenor_vertices(t.maturity_m):
                rows.append(CRIFRow(t.trade_id, t.netting_set, PRODUCT_CLASS, RISK_IR,
                                    t.hedging_set, t.hedging_set, tenor, "", pv01 * weight))
        elif t.asset_class == "FX":
            rows.append(CRIFRow(t.trade_id, t.netting_set, PRODUCT_CLASS, RISK_FX,
                                t.hedging_set, FX_BUCKET, "", "", _fx_delta_signed_exposure(t)))
            vega = _fx_vega_dollar(t)
            if vega != 0.0:
                rows.append(CRIFRow(t.trade_id, t.netting_set, PRODUCT_CLASS, RISK_FX_VOL,
                                    t.hedging_set, FX_BUCKET, "", "", vega))
    return rows


def write_crif(rows: list[CRIFRow], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CRIF_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def read_crif(path: str) -> list[CRIFRow]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(CRIF_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CRIF file is missing required columns: {sorted(missing)}")
        return [
            CRIFRow(r["TradeID"], r["PortfolioID"], r["ProductClass"], r["RiskType"], r["Qualifier"],
                    r["Bucket"], r["Label1"], r["Label2"], float(r["AmountUSD"]))
            for r in reader
        ]


def _net_by_factor(rows: list[CRIFRow], risk_type: str) -> dict:
    net: dict = {}
    for r in rows:
        if r.risk_type == risk_type:
            net[(r.bucket, r.qualifier, r.label1)] = net.get((r.bucket, r.qualifier, r.label1), 0.0) + r.amount
    return net


def compute_simm_im_from_crif(rows: list[CRIFRow], portfolio_id: str, params: SIMMParams = SIMMParams()) -> SIMMResult:
    """SIMM IM for one portfolio straight from CRIF rows: the same sensitivities a counterparty
    would run SIMM on, so it reproduces compute_simm_im exactly for the same trades."""
    rows = [r for r in rows if r.portfolio_id == portfolio_id]

    ir_buckets: dict = {}
    for (ccy, _, tenor), value in _net_by_factor(rows, RISK_IR).items():
        ir_buckets.setdefault(ccy, []).append(Sensitivity(tenor, value, ir_risk_weight(ccy, tenor)))

    def fx_bucket(risk_type: str, weight_fn) -> dict:
        sens = [Sensitivity(pair, value, weight_fn(pair)) for (_, pair, _), value in _net_by_factor(rows, risk_type).items()]
        return {FX_BUCKET: sens} if sens else {}

    return compute_simm_im_from_buckets(
        portfolio_id, ir_buckets, fx_bucket(RISK_FX, fx_risk_weight),
        fx_bucket(RISK_FX_VOL, lambda pair: FX_VEGA_RISK_WEIGHT), params,
    )
