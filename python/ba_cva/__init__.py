"""BA-CVA (Basic Approach for CVA) capital charge calculator.

Implements the "Reduced BA-CVA" variant (no eligible-hedge recognition) of the
Basel III CVA risk framework finalization. Consumes EAD directly from the
`saccr` package (SA-CCR EAD calculator) rather than re-deriving exposure.
"""
