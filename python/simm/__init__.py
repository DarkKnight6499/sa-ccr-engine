"""Simplified ISDA SIMM (Standard Initial Margin Model) calculator.

Implements delta and vega margin for the Interest Rate and FX risk classes
only (Credit, Equity, Commodity, and curvature margin are out of scope).

IMPORTANT CALIBRATION CAVEAT: this module implements the ISDA SIMM public
methodology STRUCTURE (bucket-level weighted sensitivities, within-bucket and
cross-bucket correlation aggregation, concentration risk factor, product-class
combination) as documented in ISDA's own public SIMM methodology overviews and
academic literature on non-cleared margin methodologies. The actual risk
weight, correlation, and concentration threshold VALUES are licensed ISDA
calibration data available only to ISDA members/subscribers. This module uses
illustrative parameter values chosen to be the right order of magnitude and to
exercise every formula path, not the real ISDA calibration. See
`simm/params.py` and the README for the full caveat.
"""
