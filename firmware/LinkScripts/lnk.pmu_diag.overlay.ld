/* PMU_DIAG-only overlay -- the SINGLE build-contract source for the exact
 * golden window the diag record proves inference semantics against.
 *
 * 0x90020CC0..0x90020DC0 is the 256-byte test-19 output window the HOST
 * golden judgement has always used (GET_RESULT base/len in the production
 * acceptance flow). The diag image answers GET_RESULT with UNSUPPORTED, so
 * the window evidence moves into the diag record itself; the C code takes
 * BOTH values from these symbols and carries no address literal.
 *
 * The frozen lnk.measure.overlay.ld is deliberately NOT touched: it is part
 * of the MEASURE_SEQ qualification manifest. check_diag_case.py --map
 * verifies these symbols land at exactly the contract values, fail-closed.
 */
__pmu_diag_golden_window_base__ = 0x90020CC0;
__pmu_diag_golden_window_len__  = 0x100;
