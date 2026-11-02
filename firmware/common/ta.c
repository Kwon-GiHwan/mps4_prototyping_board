/* FI101 NPU timing adapters (TA_SRAM, TA_EXT): profile tables, apply and read back. */
#include <stdint.h>

#include "ta.h"

/* NPU timing adapters (MLEK platform mps4 CMakeLists: TA_SRAM_BASE 0x51102000, TA_EXT_BASE
 * 0x51102400; register map core-platform timing_adapter.c). Profile 1 = MLEK ta_config_u85_sys_dram_mid (Dedicated_Sram branch);
 * 2 = pass-through (no limits, no added latency, full speed; MODE bit 0 still set); 3 = profile 1 with MODE bit 0
 * ("dynamic clocking to avoid underrun", core-platform timing_adapter.h) cleared. Values are stored pre-masked.
 * The PMWL header word 27 selects the profile (runner/pmwl.c); the study image applies profile 1. */
#define TA_VERSION 0x1117U /* timing_adapter.c TA_VERSION_SUPPORTED */
#define TA_PERFCTRL_OFF 0x20U /* timing_adapter.c register offsets */
#define TA_PERFCNT_OFF 0x24U
static const uint32_t ta_base[2] = {0x51102000U, 0x51102400U};  /* SRAM, EXT */
static const uint32_t ta_off[11] = {0x00U, 0x04U, 0x08U, 0x0CU, 0x10U, 0x14U, 0x18U, 0x1CU, 0x20U, 0x28U, 0x30U};
/* MAXR MAXW MAXRW RLATENCY WLATENCY PULSE_ON PULSE_OFF BWCAP PERFCTRL MODE HISTBIN */
static const uint32_t ta_val[3][2][11] = {
    {{8U, 8U, 0U, 32U, 32U, 3999U, 1U, 4000U, 0U, 1U, 0U},       /* 1 MLEK: SRAM */
     {0U, 32U, 0U, 500U, 250U, 4000U, 1000U, 3750U, 0U, 1U, 0U}}, /* 1 MLEK: EXT (MAXR 64 & 0x3F = 0) */
    {{0U, 0U, 0U, 0U, 0U, 0xFFFFU, 0U, 0U, 0U, 1U, 0U},           /* 2 pass-through: SRAM */
     {0U, 0U, 0U, 0U, 0U, 0xFFFFU, 0U, 0U, 0U, 1U, 0U}},          /* 2 pass-through: EXT */
    {{8U, 8U, 0U, 32U, 32U, 3999U, 1U, 4000U, 0U, 0U, 0U},       /* 3 profile 1, MODE 0: SRAM */
     {0U, 32U, 0U, 500U, 250U, 4000U, 1000U, 3750U, 0U, 0U, 0U}}};/* 3 profile 1, MODE 0: EXT */
static volatile uint32_t *ta_reg(uint32_t p) { return (volatile uint32_t *)(uintptr_t)ta_base[p]; }
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
uint32_t ta_perfctrl_apply(uint32_t knob)
{
    uint32_t p, v, bad = 0U;
    for (p = 0U; p < 2U; p++) {
        if (ta_reg(p)[0x38U / 4U] != TA_VERSION) { bad = 1U; continue; }
        v = (knob >> (8U * p)) & 0x3FU;
        ta_reg(p)[TA_PERFCTRL_OFF / 4U] = v;
        if (ta_reg(p)[TA_PERFCTRL_OFF / 4U] != v) { bad = 1U; }
    }
    return bad;
}
uint32_t ta_perfctrl_read(void)
{
    return (ta_reg(0U)[TA_PERFCTRL_OFF / 4U] & 0x3FU) | ((ta_reg(1U)[TA_PERFCTRL_OFF / 4U] & 0x3FU) << 8);
}
uint32_t ta_perfcnt(uint32_t p)
{
    return ta_reg(p)[TA_PERFCNT_OFF / 4U];
}
