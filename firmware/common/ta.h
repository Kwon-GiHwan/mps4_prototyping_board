/* FI101 NPU timing adapters (ta.c). Profiles: 1 = MLEK ta_config_u85_sys_dram_mid, 2 = pass-through,
 * 3 = profile 1 with MODE bit 0 (dynamic clocking) off. */
#ifndef COMMON_TA_H
#define COMMON_TA_H

#include <stdint.h>

#define TA_PROFILE_COUNT 3U
#define TA_PERFCTRL_KNOB_MASK 0x3F3FU /* PMWL word 28: bits 5:0 TA_SRAM, bits 13:8 TA_EXT PERFCTRL */

/* Write profile prof (1..TA_PROFILE_COUNT) to both adapters. Returns 0 when both report the supported version
 * and read back every written value. */
uint32_t ta_apply(uint32_t prof);
/* Write both PERFCTRL fields of a knob word (TA_PERFCTRL_KNOB_MASK). Returns 0 when both adapters report the
 * supported version and read back the written value. */
uint32_t ta_perfctrl_apply(uint32_t knob);
/* Both PERFCTRL registers, packed as the knob word. */
uint32_t ta_perfctrl_read(void);
/* PERFCNT of adapter p (0 = TA_SRAM, 1 = TA_EXT). */
uint32_t ta_perfcnt(uint32_t p);

#endif
