/* CPU cycle timestamps from DWT CYCCNT (timing.c), and a bounded busy-wait. */
#ifndef COMMON_TIMING_H
#define COMMON_TIMING_H

#include <stdint.h>
#include "mmio.h"

/* ------------------------------------------------------------------------ */
/* Debug / trace unit -- raw addresses, matching this file's register style. */
/* Using literals avoids depending on whether the CMSIS version in use calls  */
/* the block CoreDebug or DCB.                                               */
/* ------------------------------------------------------------------------ */

#define DEMCR_ADDR     0xE000EDFCU
#define DEMCR_TRCENA   (1U << 24)
#define DWT_CTRL_ADDR  0xE0001000U
#define DWT_CYCCNT_ADDR 0xE0001004U
#define DWT_LAR_ADDR   0xE0001FB0U
#define DWT_LAR_KEY    0xC5ACCE55U
#define DWT_CTRL_CYCCNTENA (1U << 0)

uint32_t timestamp_source_ready(void);
void timing_wait_cycles(uint32_t cycles);

static inline uint32_t read_timestamp(void)
{
    return REG32(DWT_CYCCNT_ADDR);
}

#endif
