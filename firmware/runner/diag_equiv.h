/* Equivalence experiment A (docs/plan/equivalence_plan.md §5 A, §8): read-back of what the vendor path actually
 * leaves in CFG_SRAM_CAP / CFG_EXT_CAP (E1) and in TA_EXT MAXR when MLEK's value 64 is written (E2). Compiled only into
 * the diagnostic build (-DRUNNER_DIAG_EQUIV, BUILD=build_npu_runner_equiv); in every other build the calls expand to
 * nothing, so the measurement image is unchanged. Results are appended to the measurement record. */
#ifndef RUNNER_DIAG_EQUIV_H
#define RUNNER_DIAG_EQUIV_H

#include <stdint.h>

#ifdef RUNNER_DIAG_EQUIV
/* Record words, in order: RUN index since boot (1 = first), CAP SRAM/EXT at __wrap_test_u85 entry (before the vendor
 * writes them in this RUN; on RUN 1 = the reset value MLEK keeps), CAP SRAM/EXT at the POWER_CTRL printf (after the vendor
 * write), CAP SRAM/EXT at the CPM seam, TA_EXT MAXR read after writing 64, TA_EXT MAXR read after restoring the
 * profile value. */
#define DIAG_EQUIV_FIELDS 9U
extern uint32_t diag_equiv[DIAG_EQUIV_FIELDS];
void diag_equiv_entry(void);
void diag_equiv_seam(void);
void diag_equiv_end(void);
void diag_equiv_ta_probe(uint32_t profile);
#else
#define DIAG_EQUIV_FIELDS 0U
#define diag_equiv_entry() ((void)0)
#define diag_equiv_seam() ((void)0)
#define diag_equiv_end() ((void)0)
#define diag_equiv_ta_probe(profile) ((void)(profile))
#endif

#endif
