/* The driver's documented weak hooks (core driver 03567073), overridden to observe the inference without changing it
 * (docs/plan/driver_runner_plan.md J3, J5):
 *   ethosu_address_remap  identity remap; on the QBASE call (index -1, the first register write of
 *                         ethosu_dev_run_command_stream, after the soft-reset/power request and MLEK's begin callback,
 *                         right before REGIONCFG and CMD start) the PMU is armed and the job's base addresses recorded
 *   ethosu_irq_handler    reads the PMU, STATUS and QREAD first, then does exactly what the driver's default does
 *   ethosu_semaphore_*    the driver's baremetal semaphore, same semantics; take() waits with __WFE (WAIT_WFE, as the
 *                         default) or spins without it (WAIT_BUSY)
 * Nothing else of the driver or of MLEK is replaced. */
#include "ethosu_driver.h"
#include "probe.h"
#include "timing.h"

#include "RTE_Components.h"   /* CMSIS core: __WFE, __SEV */

#define NPU_OFF_STATUS 0x04U
#define NPU_OFF_QREAD  0x18U
#define NPU_OFF_QSIZE  0x20U  /* core driver ethosu85_interface.h NPU_REG_QSIZE (0x24 is PROT) */

extern struct ethosu_driver ethosu_drv;                                   /* MLEK ethosu_npu_init.c */
bool ethosu_dev_handle_interrupt(struct ethosu_device *dev);             /* core driver ethosu_device.h */

void hooks_install(void)
{
    probe_begin(WAIT_WFE);
}

static uint32_t npu_word(uint32_t off)
{
    return *(volatile uint32_t *)((uintptr_t)ethosu_drv.dev.reg + off);
}

uint64_t ethosu_address_remap(uint64_t address, int index)
{
    if (index == -1) {
        struct ethosu_job *j = &ethosu_drv.job;
        uint32_t cnten;
        probe.n_base = (uint32_t)((j->num_base_addr < (int)PROBE_BASES) ? j->num_base_addr : (int)PROBE_BASES);
        for (uint32_t i = 0; i < probe.n_base; i++) {
            probe.base[i] = (uint32_t)j->base_addr[i];
            probe.base_size[i] = (uint32_t)j->base_addr_size[i];
        }
        probe.power_requests = ethosu_drv.power_request_counter;
        probe.pmcr_at_arm = pmu_session_arm(&cnten);
        probe.cnten_at_arm = cnten;
        probe.arm_count++;
        probe.dwt_arm = read_timestamp();
    }
    return address;
}

void ethosu_irq_handler(struct ethosu_driver *drv)
{
    pmu_snapshot_t s;
    probe.dwt_irq = read_timestamp();
    pmu_session_snapshot(&s);
    probe.at_irq = s;
    probe.status_at_irq = npu_word(NPU_OFF_STATUS);
    probe.qread_at_irq = npu_word(NPU_OFF_QREAD);
    probe.qsize = npu_word(NPU_OFF_QSIZE);
    probe.irq_count++;

    /* the driver's default handler, unchanged */
    if (drv->job.result == ETHOSU_JOB_RESULT_TIMEOUT) {
        (void)ethosu_dev_handle_interrupt(&drv->dev);
        return;
    }
    drv->job.state  = ETHOSU_JOB_DONE;
    drv->job.result = ethosu_dev_handle_interrupt(&drv->dev) ? ETHOSU_JOB_RESULT_OK : ETHOSU_JOB_RESULT_ERROR;
    probe.job_result = (uint32_t)drv->job.result;
    ethosu_semaphore_give(drv->semaphore);
}

/* The driver's baremetal semaphore (same layout and semantics), from a static pool instead of malloc. */
typedef struct { volatile uint8_t count; } sem_t;
static sem_t sem_pool[4];
static uint32_t sem_used;

void *ethosu_semaphore_create(void)
{
    if (sem_used == sizeof sem_pool / sizeof sem_pool[0]) { return 0; }
    sem_pool[sem_used].count = 0U;
    return &sem_pool[sem_used++];
}

void ethosu_semaphore_destroy(void *sem)
{
    (void)sem;
}

int ethosu_semaphore_take(void *sem, uint64_t timeout)
{
    sem_t *s = sem;
    (void)timeout;
    if (probe.wait_mode == WAIT_BUSY) {
        while (s->count == 0U) {
        }
    } else {
        while (s->count == 0U) {
            __WFE();
        }
    }
    s->count--;
    return 0;
}

int ethosu_semaphore_give(void *sem)
{
    sem_t *s = sem;
    s->count++;
    __SEV();
    return 0;
}
