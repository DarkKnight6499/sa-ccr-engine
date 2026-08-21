"""Trade input model. Mirrors the Trade_Inputs sheet in SACCR_EAD_Calculator.xlsx."""
from dataclasses import dataclass
from typing import Optional
import csv


@dataclass
class Trade:
    trade_id: str
    netting_set: str
    asset_class: str          # IR | FX | Credit | Equity | Commodity
    hedging_set: str          # currency (IR), currency pair (FX), or issuer/index name
    position: str             # Long | Short
    style: str                # Linear | Option
    opt_type: Optional[str]   # Call | Put | None
    notional: float
    start_s: float            # years
    maturity_m: float         # years
    underlying_price: Optional[float]
    strike: Optional[float]
    vol: Optional[float]      # annualized, options only
    mtm: float
    sub_category: str         # SF/correlation lookup key, e.g. BBB, IG_Index, SingleName, Index, NA


def _parse_optional_float(value: str) -> Optional[float]:
    value = value.strip()
    return float(value) if value else None


def load_trades(csv_path: str) -> list[Trade]:
    trades = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trades.append(Trade(
                trade_id=row["trade_id"],
                netting_set=row["netting_set"],
                asset_class=row["asset_class"],
                hedging_set=row["hedging_set"],
                position=row["position"],
                style=row["style"],
                opt_type=row["opt_type"] if row["opt_type"] not in ("", "NA") else None,
                notional=float(row["notional"]),
                start_s=float(row["start_s"]),
                maturity_m=float(row["maturity_m"]),
                underlying_price=_parse_optional_float(row["underlying_price"]),
                strike=_parse_optional_float(row["strike"]),
                vol=_parse_optional_float(row["vol"]),
                mtm=float(row["mtm"]),
                sub_category=row["sub_category"],
            ))
    return trades
