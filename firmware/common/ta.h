/* FI101 NPU timing adapters (ta.c). Profiles: 1 = MLEK ta_config_u85_sys_dram_mid, 2 = pass-through. */
#ifndef COMMON_TA_H
#define COMMON_TA_H

#include <stdint.h>

#define TA_PROFILE_COUNT 2U

/* Write profile prof (1..TA_PROFILE_COUNT) to both adapters. Returns 0 when both report the supported version
 * and read back every written value. */
uint32_t ta_apply(uint32_t prof);

#endif
