# Boot 9 -- POST_HOC_DESCRIPTIVE notes (not preregistered; no verdict depends on them)

- `CYCLE_EVENT_VS_PMCCNTR` is **FAIL** under the preregistered +/-1 % ratio and stays FAIL.
  Descriptively: cycle_event - PMCCNTR = [249, 249, 249] cycles on the three id-17 runs -- a constant
  offset. At the CPM seam the snapshot reads PMCCNTR (stable HI-LO-HI) first and PMEVCNTR
  afterwards while both keep counting; a constant offset is what read-order skew looks like.
  Windows are short (3967..9297 cycles), so 249 cycles exceeds 1 %. A future contract
  could preregister an absolute tolerance or read the cycle slot first; this one does not.
- Rep 1 of every set has a larger window than reps 2-3 (first RUN after RESET+prime).
- INCONSISTENT (3): axi_latency_64/512/1024 with a single 1 among zeros -- threshold events
  at count 0/1, recorded as INCONSISTENT per the closed verdict set.
- COUNTED_ZERO carries no attribution: ext_rd/wr data beats zero with ext_enabled_cycles nonzero
  (the fixed test's regions are SRAM-side), ecc_* zero, sram2_*/sram3_* zero (no such port at
  1024 MACs). None of these zeros is upgraded to "absent" or "not supported".
