/* Logging wrappers (--wrap=printf ...): inert, plus the two printf seams of the vendor test_u85. */
#include "runner.h"

/* ------------------------------------------------------------------------ */
/* CONTRACT 3: logging wrappers                                              */
/*                                                                           */
/* WRAPPED profile: forward to __real_* unless measurement_active.           */
/* CLEAN profile:   unconditionally inert, and CRUCIALLY they never          */
/*                  reference any __real_* symbol -- so newlib's stdio is    */
/*                  not pulled in and no denylist symbol is reachable from   */
/*                  the measured path at all.                                */
/*                                                                           */
/* THE CLEAN PROFILE THEREFORE EMITS NO HUMAN-READABLE OUTPUT ANYWHERE,      */
/* not just during the window. That is intended for a measurement build.     */
/* ------------------------------------------------------------------------ */


int __wrap_printf(const char *fmt, ...)
{
    /* Tier B read seam (amendment 7). Exactly one printf in the vendor test
     * carries this format, between its STOP (CMD=0) and its clock/power
     * release (CMD=0xC). Counted on every arrival so a double fire is visible. */
    if (measurement_active && instr_cfg.mode == INSTRUMENTATION_EVENTS
        && strcmp(fmt, "Testing CPM signals\n") == 0) {
        uint32_t st = 0U, rt = 0U;
        uint64_t cyc = npu_pmu_read_cycles(&st, &rt);
        seam_cycle_lo = (uint32_t)(cyc & 0xFFFFFFFFU);
        seam_cycle_hi = (uint32_t)(cyc >> 32);
        seam_cycle_stable = st; seam_cycle_retries = rt;
        seam_ovf = npu_pmu_overflow_status();
        for (unsigned k = 0; k < instr_cfg.event_count; k++) {
            seam_ev[k] = pmu_reg_read(NPU_REG_PMEVCNTR_BASE + 4U * k);
        }
        seam_status = npu_read(NPU_OFF_STATUS);
        seam_qread  = npu_read(NPU_OFF_QREAD);
        seam_power_ctrl = npu_read(NPU_OFF_POWER_CTRL);
        seam_fired++;
    }
    /* Tier C step 2 apply seam: right after the vendor wrote REGIONCFG/QCONFIG/MEM_ATTR,
     * right before it starts the NPU. Every override is read back. */
    if (measurement_active && pmwl_knob_pending
        && strcmp(fmt, "Updating POWER_CTRL register with MAC_RAMP_VAR=%d \n") == 0) {
        static const uint32_t off[8] = {NPU_OFF_REGIONCFG, NPU_OFF_QCONFIG, NPU_OFF_MEM_ATTR0,
                                        NPU_OFF_MEM_ATTR0 + 4U, NPU_OFF_MEM_ATTR0 + 8U, NPU_OFF_MEM_ATTR0 + 12U,
                                        NPU_OFF_AXI_SRAM, NPU_OFF_AXI_EXT};
        for (unsigned k = 0; k < 8U; k++) {
            if (pmwl_knob[k] != PMWL_OFF) {
                npu_write(off[k], pmwl_knob[k]);
                if (npu_read(off[k]) != pmwl_knob[k]) { pmwl_knob_bad = 1U; }
            }
        }
        pmwl_knob_pending = 0U;
    }
    (void)fmt;
    suppressed_printf_calls++;
    return 0;
}

int __wrap_vprintf(const char *fmt, va_list ap)
{
    (void)fmt;
    (void)ap;
    suppressed_printf_calls++;
    return 0;
}

int __wrap_puts(const char *s)
{
    (void)s;
    suppressed_printf_calls++;
    return 0;
}

int __wrap_putchar(int c)
{
    suppressed_printf_calls++;
    return c;
}

int __wrap__write(int fd, const void *buf, size_t n)
{
    (void)fd;
    (void)buf;
    suppressed_write_calls++;
    return (int)n;
}

int __wrap_fputc(int c, void *stream)
{
    (void)stream;
    suppressed_printf_calls++;
    return c;
}

void __wrap_serial_print(char *s)
{
    (void)s;
    suppressed_printf_calls++;
}


/* These have no legitimate caller in this project. They are wrapped in BOTH
 * profiles and hard-suppressed, so that if one ever appears it is diverted
 * away from the UART instead of silently bypassing the wrap set. */
int __wrap_fprintf(void *stream, const char *fmt, ...)
{
    (void)stream;
    (void)fmt;
    suppressed_printf_calls++;
    return 0;
}

int __wrap_vfprintf(void *stream, const char *fmt, va_list ap)
{
    (void)stream;
    (void)fmt;
    (void)ap;
    suppressed_printf_calls++;
    return 0;
}

size_t __wrap_fwrite(const void *p, size_t sz, size_t n, void *stream)
{
    (void)p;
    (void)sz;
    (void)stream;
    suppressed_write_calls++;
    return n;
}

int __wrap__write_r(void *reent, int fd, const void *buf, size_t n)
{
    (void)reent;
    (void)fd;
    (void)buf;
    suppressed_write_calls++;
    return (int)n;
}
