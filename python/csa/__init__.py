"""CSA (Credit Support Annex) margin call logic.

Takes a counterparty's CSA terms (threshold, MTA, IA) and a current exposure
and required IM figure (from `saccr`'s RC/EAD or `simm`'s IM), and computes
the variation margin and IM calls that would go out for that day.
"""
