/* FI101 NPU timing adapters (TA_SRAM, TA_EXT): profile tables, apply and read back. */
#include <stdint.h>

#include "ta.h"

/* NPU timing adapters (MLEK platform mps4 CMakeLists: TA_SRAM_BASE 0x51102000, TA_EXT_BASE
 * 0x51102400; register map core-platform timing_adapter.c). Profile 1 = MLEK ta_config_u85_sys_dram_mid (Dedicated_Sram branch);
 * 2 = pass-through (no limits, no added latency, full speed). Values are stored pre-masked.
 * The PMWL header word 27 selects the profile (runner/pmwl.c); the study image applies profile 1. */
#define TA_VERSION 0x1117U /* timing_adapter.c TA_VERSION_SUPPORTED */
static const uint32_t ta_base[2] = {0x51102000U, 0x51102400U};  /* SRAM, EXT */
static const uint32_t ta_off[11] = {0x00U, 0x04U, 0x08U, 0x0CU, 0x10U, 0x14U, 0x18U, 0x1CU, 0x20U, 0x28U, 0x30U};
/* MAXR MAXW MAXRW RLATENCY WLATENCY PULSE_ON PULSE_OFF BWCAP PERFCTRL MODE HISTBIN */
static const uint32_t ta_val[2][2][11] = {
    {{8U, 8U, 0U, 32U, 32U, 3999U, 1U, 4000U, 0U, 1U, 0U},       /* 1 MLEK: SRAM */
     {0U, 32U, 0U, 500U, 250U, 4000U, 1000U, 3750U, 0U, 1U, 0U}}, /* 1 MLEK: EXT (MAXR 64 & 0x3F = 0) */
    {{0U, 0U, 0U, 0U, 0U, 0xFFFFU, 0U, 0U, 0U, 1U, 0U},           /* 2 pass-through: SRAM */
     {0U, 0U, 0U, 0U, 0U, 0xFFFFU, 0U, 0U, 0U, 1U, 0U}}};         /* 2 pass-through: EXT */
/* Returns 0 when both TAs report the supported version and read back every written value. */
uint32_t ta_apply(uint32_t prof)
{
    uint32_t p, k, bad = 0U;
    for (p = 0U; p < 2U; p++) {
        volatile uint32_t *ta = (volatile uint32_t *)(uintptr_t)ta_base[p];
        if (ta[0x38U / 4U] != TA_VERSION) { bad = 1U; continue; }
        for (k = 0U; k < 11U; k++) {
            ta[ta_off[k] / 4U] = ta_val[prof - 1U][p][k];
            if (ta[ta_off[k] / 4U] != ta_val[prof - 1U][p][k]) { bad = 1U; }
        }
    }
    return bad;
}
