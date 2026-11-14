/* What the driver hooks observe during one inference (hooks.c fills it, runner.c reads it). Plain data, no driver
 * types, so the run logic can be tested off target. */
#ifndef DRV_PROBE_H
#define DRV_PROBE_H

#include <stdint.h>

#include "pmu_session.h"

#define WAIT_WFE  0U   /* the driver's own baremetal semaphore wait: while (count == 0) __WFE(); (MLEK) */
#define WAIT_BUSY 1U   /* the same loop without __WFE (the legacy runner's kind of wait) */
#define WAIT_TRACE 2U  /* the busy loop sampling QREAD (and events) on an interval: trace.c */
#define WAIT_MODES 3U
#define PROBE_BASES 8U
/* NPU registers read at the completion IRQ (core driver ethosu85_interface.h: QCONFIG 0x1C, REGIONCFG 0x3C) */
#define NPU_OFF_QCONFIG   0x1CU
#define NPU_OFF_REGIONCFG 0x3CU

typedef struct {
    uint32_t wait_mode;
    uint32_t arm_count, irq_count;
    uint32_t dwt_arm, dwt_irq;
    uint32_t pmcr_at_arm, cnten_at_arm;
    pmu_snapshot_t at_irq;
    uint32_t status_at_irq, qread_at_irq, qsize;
    uint32_t regioncfg_irq, qconfig_irq;   /* the job's region/port configuration, read at the IRQ */
    uint32_t job_result;            /* the driver's job result as the IRQ left it (0 = OK) */
    uint32_t power_requests;        /* the driver's power reference count at the arm */
    uint32_t n_base;
    uint32_t base[PROBE_BASES], base_size[PROBE_BASES];
} probe_t;

/* Pulls the driver hooks (hooks.c) into the link. The driver defines the same names weakly, so a static library would
 * otherwise never need hooks.o and the driver's defaults would run; build_driver_runner.sh checks the result. */
void hooks_install(void);

/* The probe of the RUN in progress; reset by probe_begin(). */
extern volatile probe_t probe;
void probe_begin(uint32_t wait_mode);

#endif
