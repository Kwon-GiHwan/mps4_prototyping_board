/* Ethos-U85 PMU access (npu_pmu.c). Every PMU register access goes through pmu_reg_read/pmu_reg_write. */
#ifndef COMMON_NPU_PMU_H
#define COMMON_NPU_PMU_H

#include <stdint.h>
#include "npu_pmu_regs.h"

/* ABI capacity: event slots in the wire format, fixed at 8 (the vendor header's count). */
#define NPU_PMU_ABI_EVENT_SLOTS NPU_PMU_EVENT_COUNTERS_MAX
/* PMCAXI_CHAN, absolute offset: PMU block 0x1180 + 0x2C. */
#define NPU_REG_PMCAXI_CHAN_ABS 0x11ACU

extern volatile uint32_t pmu_mmio_read_count;
extern volatile uint32_t pmu_mmio_write_count;
extern uint32_t pmu_probe_performed;
extern uint32_t pmu_present;
extern uint32_t pmu_hw_event_counters;
extern uint32_t pmu_ever_enabled;

uint32_t pmu_reg_read(uint32_t offset);
void pmu_reg_write(uint32_t offset, uint32_t value);
void pmu_probe(void);
uint32_t pmu_effective_event_slots(void);
void npu_pmu_disable(void);
void npu_pmu_enable(void);
void npu_pmu_reset_counters(void);
uint32_t npu_pmu_overflow_status(void);
uint64_t npu_pmu_read_cycles(uint32_t *stable_out, uint32_t *retries_out);

#endif
