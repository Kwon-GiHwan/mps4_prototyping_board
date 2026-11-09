/* The one owner of the NPU PMU in the driver runner (docs/plan/driver_runner_plan.md J3, J10).
 *
 * Registers are written directly at their TRM offsets (firmware/common/npu_pmu_regs.h, the map the legacy runner uses),
 * not through ETHOSU_PMU_Enable/Disable: in this driver (03567073) those call ethosu_request_power/release_power, which
 * would change the driver's power reference count and with it whether the next job soft-resets the NPU. Events are
 * selected by their hardware id (the host's numbers), not by the driver's enum. The 48-bit cycle counter is read
 * HI-LO-HI so a carry between the halves cannot tear the value (the driver's Get_CCNTR reads LO then HI once).
 *
 * Sequence per RUN: configure (no register access) -> arm (right before the NPU starts) -> snapshot at the IRQ ->
 * snapshot after the call. Platform independent: the NPU base comes from pmu_session_bind(). */
#ifndef DRV_PMU_SESSION_H
#define DRV_PMU_SESSION_H

#include <stdint.h>

#define PMU_SLOTS 8U

typedef struct {
    uint32_t count;                /* event slots used, 0..PMU_SLOTS */
    uint32_t codes[PMU_SLOTS];     /* hardware event ids (TRM pmu_event_t) */
    uint32_t pmccntr_cfg;          /* PMCCNTR_CFG word; 0 = no start/stop event (counts while enabled) */
} pmu_config_t;

typedef struct {
    uint64_t ccnt;
    uint32_t ccnt_stable;          /* 1 = HI agreed around LO */
    uint32_t ev[PMU_SLOTS];
    uint32_t ovf;                  /* PMOVSSET */
} pmu_snapshot_t;

void pmu_session_bind(volatile void *npu_base);
/* 0 = accepted; refuses more than PMU_SLOTS events or an id above 10 bits. Touches no register. */
uint32_t pmu_session_configure(const pmu_config_t *cfg);
/* Stop, clear overflow, program event types and PMCCNTR_CFG, reset all counters, enable the configured slots and the
 * cycle counter, keep PMCR.cnt_en set. Returns PMCR as read before the arm (the record keeps it). */
uint32_t pmu_session_arm(uint32_t *cnten_after);
void pmu_session_snapshot(pmu_snapshot_t *s);
/* Mask of armed slots plus the cycle counter: the overflow bits that make a snapshot unusable. */
uint32_t pmu_session_armed_mask(void);

#endif
