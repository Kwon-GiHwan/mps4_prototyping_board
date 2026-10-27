/* Ethos-U85 PMU: register access, discovery, enable/disable/reset, overflow and the 48-bit cycle read. */
#include <stdint.h>

#include "npu.h"
#include "npu_pmu.h"

/* ------------------------------------------------------------------------ */
/* EVERY PMU register access goes through these two accessors, and nothing     */
/* else in this file dereferences a PMU offset. The counters are what makes    */
/* the OFF contract checkable at RUNTIME: a run in INSTRUMENTATION_OFF must    */
/* report a delta of zero on both. A static gate can show the OFF branch has   */
/* no call edge into the PMU helpers, but only these counters can catch a      */
/* regression that reintroduces a raw dereference somewhere else.              */
/*                                                                             */
/* SCOPE OF THE OFF CONTRACT: the RUN PATH, not the whole session.             */
/* GET_CAPABILITIES probes PMCR deliberately -- discovery happens outside the  */
/* measurement window and is reported via pmu_probe_performed.                 */
volatile uint32_t pmu_mmio_read_count;
volatile uint32_t pmu_mmio_write_count;

uint32_t pmu_reg_read(uint32_t offset)
{
    pmu_mmio_read_count++;
    return REG32(U85_BASE_ADDRESS + offset);
}

void pmu_reg_write(uint32_t offset, uint32_t value)
{
    pmu_mmio_write_count++;
    REG32(U85_BASE_ADDRESS + offset) = value;
}

/* --- three DISTINCT capacities, never conflated ------------------------- */
/*   ABI capacity       : NPU_PMU_ABI_EVENT_SLOTS, fixed at 8 slots.    */
/*   hardware capacity  : PMCR.num_event_cnt, the device answering for itself.*/
/*   effective capacity : min(the two). Only this bounds a configuration.     */
/* The vendor header's constant 8 is a BUILD-TIME claim and is recorded only  */
/* as expected_hw_event_counter_count, for a provenance warning if the device */
/* disagrees. A mismatch does not kill the run; it bounds what can be asked   */
/* for and is reported. */
uint32_t pmu_probe_performed;
uint32_t pmu_present;
uint32_t pmu_hw_event_counters;

/* Set the first time the counters are armed. RESET_RUNNER uses it to
 * decide whether there is any PMU state to tear down: in a session that
 * never left OFF there is nothing to clean, and touching the block would
 * be an access with no purpose. */
uint32_t pmu_ever_enabled;

/* Discovery only. Outside the RUN path by contract -- see the accessor note. */
void pmu_probe(void)
{
    uint32_t pmcr = pmu_reg_read(NPU_REG_PMCR);

    pmu_hw_event_counters =
        (pmcr & NPU_PMCR_NUM_EVENT_CNT_MSK) >> NPU_PMCR_NUM_EVENT_CNT_POS;
    /* All-ones or all-zeros PMCR means the block did not answer. */
    pmu_present = (pmcr != 0xFFFFFFFFU && pmcr != 0U) ? 1U : 0U;
    pmu_probe_performed = 1U;
}

uint32_t pmu_effective_event_slots(void)
{
    if (!pmu_probe_performed) {
        pmu_probe();
    }
    return (pmu_hw_event_counters < NPU_PMU_ABI_EVENT_SLOTS)
               ? pmu_hw_event_counters
               : NPU_PMU_ABI_EVENT_SLOTS;
}

void npu_pmu_disable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) & ~NPU_PMCR_CNT_EN_MSK);
}

void npu_pmu_enable(void)
{
    /* Set BEFORE the enable write, never after: if the counter is armed and
     * the very next step faults, the flag must already say there is hardware
     * state to tear down. */
    pmu_ever_enabled = 1U;
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CNT_EN_MSK);
}

/* Clear every overflow flag, disable every counter, then reset the counters.
 * Stale state from a previous run must never be attributable to this one. */
void npu_pmu_reset_counters(void)
{
    pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) | NPU_PMCR_CYCLE_CNT_RST_MSK
                                             | NPU_PMCR_EVENT_CNT_RST_MSK);
}

/* The cycle overflow bit is NPU_PMU_PMOVS_CYCLE_OVF_MASK, extracted from
 * pmovsset_r. It is bit 31, NOT bit 8: eight event bits are followed by 23
 * reserved bits. The earlier 1<<NPU_PMU_ABI_EVENT_SLOTS read a reserved
 * bit that is always zero, so a wrapped counter reported "no overflow" -- a
 * false negative that would have promoted a torn sample to a measurement. */
uint32_t npu_pmu_overflow_status(void)
{
    return pmu_reg_read(NPU_REG_PMOVSSET);
}

/* The cycle counter is 48 bits across two registers and the vendor header
 * documents NO latch or atomic-read semantics -- the reference driver just
 * reads LO then HI, which can tear if LO wraps between the two reads. Read
 * HI, LO, HI and retry while HI moved. The bound is small because HI can
 * advance at most once per 2^32 NPU cycles. */
#define NPU_PMU_CYCLE_READ_TRIES 4U

#define NPU_PMU_CYCLE_MASK48 ((1ULL << NPU_PMU_CYCLE_COUNTER_WIDTH) - 1ULL)

uint64_t npu_pmu_read_cycles(uint32_t *stable_out, uint32_t *retries_out)
{
    uint32_t hi1, lo, hi2;
    uint32_t tries;

    lo  = 0U;
    hi2 = 0U;
    for (tries = 0U; tries < NPU_PMU_CYCLE_READ_TRIES; tries++) {
        hi1 = pmu_reg_read(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        lo  = pmu_reg_read(NPU_REG_PMCCNTR);
        hi2 = pmu_reg_read(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        if (hi1 == hi2) {
            if (stable_out != 0) {
                *stable_out = 1U;
            }
            if (retries_out != 0) {
                *retries_out = tries;
            }
            return (((uint64_t)hi1 << 32) | (uint64_t)lo) & NPU_PMU_CYCLE_MASK48;
        }
    }
    /* Reported, never papered over: the caller sets cycle_valid = 0 and the
     * host must treat the value as absent rather than as a measurement. */
    if (stable_out != 0) {
        *stable_out = 0U;
    }
    if (retries_out != 0) {
        *retries_out = tries;
    }
    return (((uint64_t)hi2 << 32) | (uint64_t)lo) & NPU_PMU_CYCLE_MASK48;
}
