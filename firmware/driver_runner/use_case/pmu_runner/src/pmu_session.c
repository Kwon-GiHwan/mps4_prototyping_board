/* NPU PMU ownership (pmu_session.h). */
#include "pmu_session.h"

#include "npu_pmu_regs.h"

#define EVENT_ID_MASK 0x3FFU

static volatile uint8_t *npu;
static pmu_config_t cfg;

static volatile uint32_t *reg(uint32_t off) { return (volatile uint32_t *)(npu + off); }

void pmu_session_bind(volatile void *npu_base)
{
    npu = (volatile uint8_t *)npu_base;
}

uint32_t pmu_session_configure(const pmu_config_t *c)
{
    if (c->count > PMU_SLOTS) { return 1U; }
    for (uint32_t i = 0; i < c->count; i++) {
        if (c->codes[i] & ~EVENT_ID_MASK) { return 2U; }
    }
    cfg = *c;
    return 0U;
}

uint32_t pmu_session_armed_mask(void)
{
    return NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.count) - 1U);
}

static uint32_t mask_en;

void pmu_session_set_mask_en(uint32_t on)
{
    mask_en = on ? NPU_PMCR_MASK_EN_MSK : 0U;
}

uint32_t pmu_session_arm(uint32_t *cnten_after, uint32_t *pmcr_after)
{
    uint32_t pmcr = *reg(NPU_REG_PMCR);
    *reg(NPU_REG_PMCNTENCLR) = 0xFFFFFFFFU;
    *reg(NPU_REG_PMOVSCLR) = 0xFFFFFFFFU;
    for (uint32_t i = 0; i < cfg.count; i++) {
        *reg(NPU_REG_PMEVTYPER_BASE + 4U * i) = cfg.codes[i];
    }
    *reg(NPU_REG_PMCCNTR_CFG) = cfg.pmccntr_cfg;
    *reg(NPU_REG_PMCR) = (pmcr & ~(NPU_PMCR_EVENT_CNT_RST_MSK | NPU_PMCR_CYCLE_CNT_RST_MSK | NPU_PMCR_MASK_EN_MSK))
                         | NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK | NPU_PMCR_CYCLE_CNT_RST_MSK | mask_en;
    *pmcr_after = *reg(NPU_REG_PMCR);
    *reg(NPU_REG_PMCNTENSET) = pmu_session_armed_mask();
    *cnten_after = *reg(NPU_REG_PMCNTENSET);
    return pmcr;
}

void pmu_session_snapshot(pmu_snapshot_t *s)
{
    uint32_t hi1 = 0U, lo = 0U, hi2 = 1U;
    s->ccnt_stable = 0U;
    for (uint32_t t = 0; t < 4U && !s->ccnt_stable; t++) {
        hi1 = *reg(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        lo  = *reg(NPU_REG_PMCCNTR);
        hi2 = *reg(NPU_REG_PMCCNTR_HI) & 0xFFFFU;
        s->ccnt_stable = (hi1 == hi2) ? 1U : 0U;
    }
    s->ccnt = ((uint64_t)hi2 << 32) | lo;
    for (uint32_t i = 0; i < PMU_SLOTS; i++) {
        s->ev[i] = (i < cfg.count) ? *reg(NPU_REG_PMEVCNTR_BASE + 4U * i) : 0U;
    }
    s->ovf = *reg(NPU_REG_PMOVSSET);
}

uint32_t pmu_session_read_events(uint32_t ev[PMU_SLOTS])
{
    for (uint32_t i = 0; i < cfg.count; i++) {
        ev[i] = *reg(NPU_REG_PMEVCNTR_BASE + 4U * i);
    }
    return cfg.count;
}
