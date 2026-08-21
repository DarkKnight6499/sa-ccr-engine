# sa-ccr-engine

SA-CCR (Standardised Approach for Counterparty Credit Risk) EAD calculator,
in Python and Excel, extended with a BA-CVA (Basic Approach for CVA) capital
charge calculator that consumes the SA-CCR EAD output directly. Python is the
primary, tested implementation; the Excel workbook is a parallel reference
model with the same formulas.

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
  SACCR_EAD_Calculator.xlsx   Reference Excel model: SA-CCR sheets + BACVA_Params/Counterparties/Calc/Summary sheets
python/
  saccr/
    params.py       Supervisory factors, correlations, alpha, floors (SupervisoryParams dataclass)
    trades.py        Trade dataclass + CSV loader
    engine.py         Per-trade waterfall (duration, delta, maturity factor, effective notional)
    aggregation.py    AddOn build-up per asset class
    ead.py            RC, multiplier, PFE, EAD, and the scenario runner
  ba_cva/
    params.py       Alpha, rho, discount scalar, risk-weight table (BACVAParams dataclass)
    counterparty.py  Counterparty dataclass + sector/credit-quality assignment for the sample netting sets
    engine.py         Effective maturity, discount factor, per-counterparty SCVA
    aggregation.py    K_reduced and the final BA-CVA capital charge
  data/trades_sample.csv   18-trade / 2-netting-set sample portfolio (same as the Excel's Trade_Inputs sheet)
  tests/
    test_against_excel.py   SA-CCR golden-value tests vs. the Excel workbook's own cached results
    test_ba_cva.py            BA-CVA tests, each formula piece checked against an independently hand-derived value
  run_saccr.py       SA-CCR CLI entry point
  run_ba_cva.py      BA-CVA CLI entry point, consumes run_saccr.py's EAD output directly
```

## Sample portfolio

- **NS-A (CORP-001):** unmargined, 12 trades, IR/FX/Credit/Equity/Commodity
- **NS-B (BANK-001):** CSA, TH=$0, MTA=$500k, NICA=$300k, 10bd MPOR, 6 trades

All notionals, MTMs, and CSA terms are illustrative placeholders, not real trade data. Each netting set is run twice: under its actual margin status and under the hypothetical opposite one, to show the margining impact on EAD.

## Scope / simplifications

Same as the Excel model:
- All trades start today (S=0); 250-business-day year for MF/MPOR floors
- MPOR = standard 10-business-day floor throughout (no 20-day large/illiquid override)
- FX notional = given USD leg, no separate FX-rate revaluation
- Basis/volatility add-ons are out of scope

## BA-CVA (Basic Approach for CVA capital charge)

`ba_cva/` implements the Reduced BA-CVA variant of the Basel III CVA risk framework finalization, feeding `saccr`'s EAD output directly into a capital charge calculation instead of a separate exposure model.

Source (cross-verified against two independent references):
- [FRTB - Basic Approach for CVA (Clarus Financial Technology)](https://www.clarusft.com/frtb-basic-approach-for-cva/)
- [OSFI CAR 2026 Chapter 8 - Credit Valuation Adjustment (CVA) Risk](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/capital-adequacy-requirements-car-2026-chapter-8-credit-valuation-adjustment-cva-risk)

Per counterparty:
```
SCVA_c = (1/alpha) x RW_c x sum_NS(M_NS x EAD_NS x DF_NS), alpha = 1.4
DF_NS = (1 - exp(-0.05*M_NS)) / (0.05*M_NS)
```

Aggregation across counterparties:
```
K_reduced = sqrt[(rho x sum SCVA_c)^2 + (1-rho^2) x sum SCVA_c^2)], rho = 0.5
BA-CVA capital charge = discount_scalar x K_reduced, discount_scalar = 0.65
```

Risk weight by sector x credit quality (IG vs. high-yield/not-rated):

| Sector | IG | HY/NR |
|---|---|---|
| Sovereigns/central banks | 0.5% | 2.0% |
| Local government/education | 1.0% | 4.0% |
| Financials | 5.0% | 12.0% |
| Basic materials/energy/industrials | 3.0% | 7.0% |
| Consumer goods/transportation | 3.0% | 8.5% |
| Technology/telecom | 2.0% | 5.5% |
| Healthcare/utilities | 1.5% | 5.0% |
| Other sector | 5.0% | 12.0% |

### BA-CVA scope and simplifications

- Reduced BA-CVA only. The Full BA-CVA variant, which recognizes eligible CVA hedges, is out of scope.
- Effective maturity `M_NS` is a notional-weighted average of trade maturities per netting set, computed directly from `trades_sample.csv`. Basel's own definition uses a cashflow-weighted average (Basel II Annex 4 para 38-39), which needs a cashflow schedule the sample data does not carry. This is a documented proxy, not a hidden assumption.
- `EAD_NS` is taken from each netting set's actual margin-status scenario in `saccr` (NS-A unmargined, NS-B margined), matching a bank's real CSA status rather than the hypothetical comparison scenario `saccr` also produces.
- Counterparty sector and credit quality are new assumptions layered on the existing sample netting sets, illustrative like the rest of the sample data: CORP-001 is assigned Basic materials/energy/industrials, IG; BANK-001 is assigned Financials, IG.

## Run

```
cd python
py -3 run_saccr.py
py -3 run_ba_cva.py
py -3 -m pytest tests/
```
