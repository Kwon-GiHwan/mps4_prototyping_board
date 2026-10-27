/* DWT CYCCNT timestamp source. */
#include <stdint.h>

#include "ARMCM85.h"
#include "timing.h"

/* ------------------------------------------------------------------------ */
/* Timestamp source: DWT CYCCNT                                              */
/* ------------------------------------------------------------------------ */

uint32_t timestamp_source_ready(void)
{
    uint32_t before;
    uint32_t after;

    /* ARMv8.1-M may implement a software lock on the DWT. Unlocking is
     * harmless where it is not implemented (the register RAZ/WI). */
    REG32(DWT_LAR_ADDR) = DWT_LAR_KEY;
    REG32(DEMCR_ADDR) |= DEMCR_TRCENA;
    REG32(DWT_CTRL_ADDR) |= DWT_CTRL_CYCCNTENA;

    __DSB();
    __ISB();

    /* Do not assume it worked -- prove the counter advances. */
    before = REG32(DWT_CYCCNT_ADDR);
    for (volatile uint32_t i = 0; i < 64U; i++) {
    }
    after = REG32(DWT_CYCCNT_ADDR);

    return (after != before) ? 1U : 0U;
}

/* Bounded busy-wait, copied from pmu_diag_wait_cycles(). */
void timing_wait_cycles(uint32_t cycles)
{
    if (timestamp_source_ready()) {
        const uint32_t start = read_timestamp();
        while ((read_timestamp() - start) < cycles) {
        }
    } else {
        for (volatile uint32_t n = 0U; n < cycles; n++) {
        }
    }
}
