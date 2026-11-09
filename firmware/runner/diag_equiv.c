/* Equivalence experiment A read-backs (diag_equiv.h). Empty unless built with -DRUNNER_DIAG_EQUIV. */
#include "runner.h"

#ifdef RUNNER_DIAG_EQUIV
#define NPU_OFF_CFG_SRAM_CAP 0x60U   /* interface.h NPU_REG_CFG_SRAM_CAP (vendor u85.c writes 0x00021F3F) */
#define NPU_OFF_CFG_EXT_CAP  0x64U   /* interface.h NPU_REG_CFG_EXT_CAP */
#define TA_EXT_MAXR_ADDR     0x51102400U   /* TA_EXT base + MAXR (offset 0) */
#define MLEK_TA_EXT_MAXR     64U           /* ta_config_u85_sys_dram_mid EXT MAXR */

uint32_t diag_equiv[DIAG_EQUIV_FIELDS];
static uint32_t diag_runs;

void diag_equiv_entry(void)
{
    for (unsigned k = 1U; k < DIAG_EQUIV_FIELDS; k++) { diag_equiv[k] = 0xFFFFFFFFU; }
    diag_equiv[0] = ++diag_runs;
    diag_equiv[1] = npu_read(NPU_OFF_CFG_SRAM_CAP);
    diag_equiv[2] = npu_read(NPU_OFF_CFG_EXT_CAP);
}

void diag_equiv_seam(void)
{
    diag_equiv[3] = npu_read(NPU_OFF_CFG_SRAM_CAP);
    diag_equiv[4] = npu_read(NPU_OFF_CFG_EXT_CAP);
}

void diag_equiv_end(void)
{
    diag_equiv[5] = npu_read(NPU_OFF_CFG_SRAM_CAP);
    diag_equiv[6] = npu_read(NPU_OFF_CFG_EXT_CAP);
}

/* After the profile is applied and verified: write MLEK's 64, read, put the profile's value back, read. */
void diag_equiv_ta_probe(uint32_t profile)
{
    volatile uint32_t *maxr = (volatile uint32_t *)(uintptr_t)TA_EXT_MAXR_ADDR;
    uint32_t keep = *maxr;

    (void)profile;
    *maxr = MLEK_TA_EXT_MAXR;
    diag_equiv[7] = *maxr;
    *maxr = keep;
    diag_equiv[8] = *maxr;
    if (diag_equiv[8] != keep) { pmwl_knob_bad = 1U; }   /* the restore must hold, or the RUN is not profile 1 */
}
#endif
