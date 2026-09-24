# sa-ccr-engine

SA-CCR (Standardised Approach for Counterparty Credit Risk) EAD calculator,
in Python and Excel, extended with a BA-CVA (Basic Approach for CVA) capital
charge calculator that consumes the SA-CCR EAD output directly, and a
simplified ISDA SIMM (Standard Initial Margin Model) calculator with a CSA
margin call module. Python is the primary, tested implementation; the Excel
workbook is a parallel reference model with the SA-CCR and BA-CVA formulas
(SIMM/CSA is Python only).

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
  simm/
    params.py         Concentration thresholds (SIMMParams dataclass)
    risk_weights.py    IR/FX risk weight, tenor, and correlation lookups (illustrative, see below)
    aggregation.py    Concentration risk factor, within-bucket and cross-bucket margin, risk-class combination
    engine.py           Maps trades to IR/FX delta and vega sensitivities, runs the SIMM IM pipeline
  csa/
    terms.py           CSATerms dataclass (threshold, MTA, IA, currently posted VM/IM) + sample terms
    engine.py           Daily VM and IM call computation against those terms
    report.py           Formats a MarginCallResult as a margin call report
  data/trades_sample.csv   18-trade / 2-netting-set sample portfolio (same as the Excel's Trade_Inputs sheet)
  tests/
    test_against_excel.py   SA-CCR golden-value tests vs. the Excel workbook's own cached results
    test_ba_cva.py            BA-CVA tests, each formula piece checked against an independently hand-derived value
    test_simm.py               SIMM sanity checks + hand-computable toy cases for each aggregation formula
    test_csa.py                 CSA margin call toy cases
  run_saccr.py       SA-CCR CLI entry point
  run_ba_cva.py      BA-CVA CLI entry point, consumes run_saccr.py's EAD output directly
  run_simm.py         SIMM CLI entry point: IM breakdown + CSA margin call report per netting set
  compare_simm_saccr.py   Side-by-side SIMM IM vs. SA-CCR PFE add-on report
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

## SIMM (Standard Initial Margin Model) and CSA margin calls

`simm/` implements a simplified version of ISDA SIMM, the industry-standard
sensitivity-based model banks use to calculate bilateral initial margin (IM)
for non-cleared derivatives under the Basel Committee/IOSCO margin
requirements (BCBS-IOSCO "Margin requirements for non-centrally cleared
derivatives"). Scope is the Interest Rate and FX risk classes' delta and vega
margin only; Credit, Equity, Commodity, and curvature margin are out of
scope.

**Parameter source:** the public ISDA SIMM v2.6 methodology document
(isda.org, `isda.org/a/b4ugE/ISDA-SIMM_v2.6_PUBLIC.pdf`) is freely
downloadable and publishes the full risk-weight and correlation tables. The
ISDA license restricts commercial use and redistribution of a SIMM
calculation engine in a production margin system, not access to read and
implement the methodology from that public PDF. `simm/risk_weights.py` uses
the real v2.6 figures, fetched and checked directly against that document:
the IR risk-weight-per-tenor tables for all three currency-volatility groups
(paras 33-34), the IR vega risk weight and cross-currency correlation (para
35, 37), the FX risk weight and within-bucket correlation for the
regular/regular currency-volatility cell (paras 67-72), the FX vega risk
weight (para 71), and the Interest Rate/FX cross-risk-class correlation
(para 88). What is still a simplification, documented in
`simm/aggregation.py` and `simm/risk_weights.py` rather than glossed over:

- IR delta sensitivities are allocated across the 1-2 nearest tenor vertices
  by linear interpolation (`allocate_to_tenor_vertices`), not the full
  multi-vertex ladder a real risk system's curve sensitivities would produce.
- Concentration thresholds (`simm/params.py`) stay an illustrative
  order-of-magnitude figure, not ISDA's published per-currency/per-pair
  threshold table, since this module derives sensitivities from
  notional/maturity proxies rather than real dealer risk-system Greeks.
- No curvature margin; only Interest Rate and FX risk classes are
  implemented (Credit, Equity, Commodity are out of scope).
- FX vega dollarizes the option's Black-Scholes vega using the trade's own
  market implied volatility, then applies the flat published para 71 vega
  risk weight (0.48). ISDA SIMM's own para 10(b) calibration implies a
  specific regulatory volatility for this step (roughly 9.2%, not the
  trade's live market vol), so this is a reasonable proxy, not an exact
  para 10(b) reproduction.

Core formulas (per risk class, IR and FX separately):
```
WS_k = RW_k x s_k x CR_b                    (weighted sensitivity, risk factor k in bucket b)
CR_b = max(1, sqrt(|sum_k s_k| / Threshold_b))   (concentration risk factor)
K_b = sqrt(sum_k WS_k^2 + sum_(k!=l) corr_kl x WS_k x WS_l)   (within-bucket margin)
DeltaMargin(IR) = sqrt(sum_b K_b^2 + sum_(b!=c) corr_bc x g_bc x S_b x S_c)   (cross-bucket, one bucket per currency; S_b = net WS_k clipped to [-K_b, K_b]; g_bc = min(CR_b,CR_c)/max(CR_b,CR_c))
DeltaMargin(FX) = K_b of the single FX bucket   (SIMM v2.6 para 66: all FX risk factors share one bucket, no cross-bucket step)
RiskClassMargin = DeltaMargin + VegaMargin   (curvature margin out of scope)
IM = sqrt(Margin_IR^2 + Margin_FX^2 + 2 x corr_IR_FX x Margin_IR x Margin_FX)
```

Sensitivity inputs are derived from the same `trades_sample.csv` portfolio,
not a new dataset: IR delta uses a PV01 proxy (`notional x supervisory
duration x 1bp`), reusing `saccr.engine.supervisory_duration` directly so the
same trade data drives both models, then splits that PV01 across nearby
tenor vertices; FX delta uses signed notional exposure to each pair's
non-USD currency, not the naive long/short direction of the quoted pair
(a short USDJPY position is a long JPY exposure), all pairs in SIMM's single
FX bucket; FX vega is volatility-weighted (`RiskWeight x implied_vol x
Black-Scholes vega`, using the trade's own market vol as a proxy for ISDA's
para 10(b) calibration, see caveats above) on the sample's one FX option
trade (no IR options are in the sample, so IR vega evaluates to zero).

`compare_simm_saccr.py` runs both models over the same book and prints SIMM
IM next to SA-CCR's PFE add-on and EAD. The two are not expected to match:
SIMM sizes collateral against potential future exposure for a bilateral
relationship, while SA-CCR's PFE add-on sizes a regulatory capital exposure
measure. **Trade population caveat:** this SIMM implementation only covers IR
and FX trades, while SA-CCR's full-book PFE/EAD includes every trade in the
netting set (Credit, Equity, Commodity too - NS-A has 6 non-IR/FX trades out
of 12, NS-B has 2 out of 6). Comparing SIMM's IR/FX-only IM against the
full-book PFE isn't like-for-like, so the report prints both: a PFE/EAD
recomputed on the IR/FX trade subset only (same population as SIMM, the
like-for-like figure) shown alongside the full-book PFE/EAD for context,
clearly labeled as covering a larger trade population.

`csa/` computes a daily VM (variation margin) and IM call against a
counterparty's CSA terms: threshold, MTA (Minimum Transfer Amount), and IA
(Independent Amount, a contractual floor under the model-based IM). VM
required is symmetric around the threshold band (a large negative exposure
can require posting collateral to the counterparty, not just returning what
we already hold), and a call only fires once the required-minus-posted delta
clears the MTA, matching how a real CSA call process works. `run_simm.py`
prints this report using each netting set's GROSS SA-CCR exposure (V) for
the VM leg and SIMM's IM for the IM leg; `csa/engine.py` nets off posted
collateral itself via `terms.posted_vm`, so the exposure passed in must not
already be pre-netted by collateral (that would subtract the same posted
amount twice). The report only covers NS-B: NS-A has no CSA in its actual
scenario (SA-CCR treats it as Unmargined), so it carries no entry in
`csa/terms.py`'s `SAMPLE_CSA_TERMS` and `run_simm.py` never fabricates a
margin call for it.

## Run

```
cd python
py -3 run_saccr.py
py -3 run_ba_cva.py
py -3 run_simm.py
py -3 compare_simm_saccr.py
py -3 -m pytest tests/
```
