# sa-ccr-engine

SA-CCR (Standardised Approach for Counterparty Credit Risk) EAD calculator, in
Python and Excel. Python is the primary, tested implementation; the Excel
workbook is the reference model it was validated against.

## Source

BIS d279, "Standardised approach for measuring counterparty credit risk
exposures", March 2014 (rev. April 2014). bis.org/publ/bcbs279.htm

## Formula

- `EAD = alpha x (RC + PFE)`, alpha = 1.4
- `RC unmargined = max(V - C, 0)`
- `RC margined = max(V - C, TH + MTA - NICA, 0)`
- `PFE = Multiplier x AddOn_aggregate`
- `Multiplier = min[1, Floor + (1-Floor) x exp((V-C) / (2 x (1-Floor) x AddOn_aggregate))]`, Floor = 5%
- `AddOn_aggregate` = sum of AddOn by asset class (IR, FX, Credit, Equity, Commodity)

**Trade-level waterfall** (`python/saccr/engine.py`):
1. Adjusted notional `d`: `notional x SD` for IR/Credit, `SD = [exp(-0.05*S) - exp(-0.05*E)] / 0.05`; notional directly for FX/Equity/Commodity
2. Supervisory delta: +/-1 linear; Black-Scholes `N(d1)` for options
3. Maturity factor: unmargined = `sqrt(min(M, 1))` floored at MPOR; margined = `1.5 x sqrt(MPOR/1yr)`, flat across all margined trades
4. Effective notional = `delta x d x MF`

**Aggregation** (`python/saccr/aggregation.py`):
- IR: 3 maturity buckets (<1y, 1-5y, >5y) per currency, cross-bucket correlation (1.4x adjacent buckets, 0.6x buckets 1 & 3), summed across currencies
- FX: `SF x |sum(EffNotional)|` per currency-pair hedging set, summed across pairs
- Credit / Equity / Commodity: `sqrt[(sum rho_i*SF_i*Eff_i)^2 + sum((1-rho_i^2)*(SF_i*Eff_i)^2)]`

## Structure

```
excel/
  SACCR_EAD_Calculator.xlsx   Reference Excel model (formulas + 18-trade sample, computed by hand first)
python/
  saccr/
    params.py       Supervisory factors, correlations, alpha, floors (SupervisoryParams dataclass)
    trades.py        Trade dataclass + CSV loader
    engine.py         Per-trade waterfall (duration, delta, maturity factor, effective notional)
    aggregation.py    AddOn build-up per asset class
    ead.py            RC, multiplier, PFE, EAD, and the scenario runner
  data/trades_sample.csv   18-trade / 2-netting-set sample portfolio (same as the Excel's Trade_Inputs sheet)
  tests/test_against_excel.py   Golden-value tests vs. the Excel workbook's own cached results
  run_saccr.py       CLI entry point
```

## Sample portfolio

- **NS-A (CORP-001):** unmargined, 12 trades, IR/FX/Credit/Equity/Commodity
- **NS-B (BANK-001):** CSA, TH=$0, MTA=$500k, NICA=$300k, 10bd MPOR, 6 trades

All notionals, MTMs, and CSA terms are illustrative placeholders, not real trade data. Each netting set is run twice: under its actual margin status and under the hypothetical opposite one, to show the margining impact on EAD.

## Scope / simplifications

- All trades start today (S=0); 250-business-day year for MF/MPOR floors
- MPOR = standard 10-business-day floor throughout (no 20-day large/illiquid override)
- FX notional = given USD leg, no separate FX-rate revaluation
- Basis/volatility add-ons and BA-CVA are out of scope

## Run

```
cd python
py -3 run_saccr.py
py -3 -m pytest tests/
```
