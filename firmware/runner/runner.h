/* Shared by every runner module: includes, the linker-defined memory windows, and the module headers. */
#ifndef RUNNER_RUNNER_H
#define RUNNER_RUNNER_H

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "ARMCM85.h"
#include "Driver_USART.h"
#include "serial.h"
#include "u85.h"

#include "mmio.h"
#include "npu.h"
#include "npu_pmu.h"
#include "ta.h"
#include "timing.h"

/* ------------------------------------------------------------------------ */
/* CONTRACT 1: capabilities come from LINKER SYMBOLS, never C constants.     */
/*                                                                           */
/* Re-declaring these as C constants is exactly how firmware drifts away     */
/* from its own map. Every address below is defined in LinkScripts/lnk.ld.S  */
/* and resolved at link time. There is no second source of truth.            */
/* ------------------------------------------------------------------------ */

extern const uint8_t __runner_staging_start__[];
extern const uint8_t __runner_staging_end__[];
extern const uint8_t __runner_result_start__[];
extern const uint8_t __runner_result_end__[];
/* NOTE: there is deliberately NO tight __runner_output_* pair. Bounding just
 * .bss.sec_output_data can only be expressed INSIDE the .sec_noinit output
 * section body, i.e. by editing the shared lnk.ld.S, and the C object
 * (test3_out_data_0 in Tests/u85_test/test3/test3_include.h) is declared
 * `static` so it cannot be referenced externally either. The shared script is
 * left untouched by choice; see MEASURE_PROVENANCE.txt. */

/* Retained from runner_v1_main.c so GET_RESULT keeps validating against the
 * exact same bounds it validated against in the frozen build. */
extern char __sec_noinit_start[];
extern char __sec_noinit_end[];

static inline uint32_t sym_u32(const uint8_t *p)
{
    return (uint32_t)(uintptr_t)p;
}

#include "proto.h"
#include "measure.h"
#include "pmwl.h"

#endif
