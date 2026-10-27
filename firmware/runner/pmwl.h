/* PMWL workload blob (pmwl.c): header, knobs and IO table, placement, knob apply/read-back, OFM comparison.
 * The host declares the same layout independently in host/lib/pmwl.py; host/tests/test_pmwl_firmware_contract.py
 * requires the two to agree. */
#ifndef RUNNER_PMWL_H
#define RUNNER_PMWL_H

#include <stdint.h>

#define PMWL_MAGIC 0x4C574D50U
#define PMWL_IO_MAX 10U
#define PMWL_REFUSED 0x7E
#define PMWL_KNOB_NOT_HONOURED 0x7D
#define PMWL_OFF 0xFFFFFFFFU

/* v2 knobs, applied at the vendor's POWER_CTRL printf (io_wrap.c __wrap_printf). */
extern volatile uint32_t pmwl_knob_pending, pmwl_knob_bad;
extern uint32_t pmwl_knob[8]; /* regioncfg qconfig mem_attr0..3 axi_sram axi_ext */

#endif
