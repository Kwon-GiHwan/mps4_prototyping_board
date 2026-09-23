# Amendment 1 to the PMU EV_TYPE sweep contract (2026-09-23, before any data)

`RULE_VERDICT_UNCLASSIFIABLE` is withdrawn. The four verdicts are exhaustive by
construction: for readback bits lo=[9:0], hi=[31:10] and written ev,
lo==ev splits on hi (ACCEPTED / UPPER_BITS_SET) and lo!=ev splits on lo==0
(COERCED_TO_ZERO / COERCED_OTHER). No (ev, readback) pair falls through, so the
rule could never fire -- a check that cannot fail. Caught by the parser's own
rule-coverage test before any capture existed. Nothing else changes.
