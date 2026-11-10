/* Off-target simulator of the driver runner (host tests only): the platform-independent core (runner.c, frame.c,
 * workload.c, record.c, pmu_session.c, probe.c) compiled for the host with fake ports. Frames come on stdin and go to
 * stdout, so host/lib/runner_proto.py talks to it exactly as to the board.
 *
 * Fake pieces: the NPU register block is an array (pmu_session writes into it; the fake "inference" then puts known
 * counter values there and takes the IRQ snapshot, as hooks.c does on target); the model is a tiny "SIMM" container
 * instead of a TFLM model: magic 'SIMM', n_in, n_out, input lengths, output lengths; output k byte j = (input 0 byte
 * (j mod len0)) + k + 1. Behaviour switches (environment): SIM_INVOKE_FAIL, SIM_NO_IRQ, SIM_TWO_IRQ, SIM_OVF. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "caps.h"
#include "npu_pmu_regs.h"
#include "pmu_session.h"
#include "probe.h"
#include "trace.h"
#include "record.h"
#include "runner.h"

#define SIM_STAGING (32u << 20)
#define SIM_DDR     (8u << 20)
#define SIM_ARENA   0x10000u
#define SIMM_MAGIC  0x4D4D4953u

static uint8_t *staging, *ddr;
static uint32_t npu_regs[0x2000 / 4];
static uint32_t n_in, n_out, in_len[8], out_len[8];
static uint8_t *in_buf[8], *out_buf[8];
static uint32_t clock_now = 1000u;
static int eof;

#define REG(off) npu_regs[(off) / 4]

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }

static void place_model(uintptr_t dst, const uint8_t *src, uint32_t len) { memcpy((void *)dst, src, len); }

static uint32_t model_load(uintptr_t base, uint32_t len, uintptr_t arena, uint32_t arena_len)
{
    const uint8_t *m = (const uint8_t *)base;
    uint32_t at = 0;
    if (len < 12 || rd32(m) != SIMM_MAGIC) { return 1u; }
    n_in = rd32(m + 4); n_out = rd32(m + 8);
    if (n_in < 1 || n_out < 1 || n_in > 8 || n_out > 8 || len < 12 + 4 * (n_in + n_out)) { return 2u; }
    for (uint32_t i = 0; i < n_in + n_out; i++) {
        uint32_t n = rd32(m + 12 + 4 * i);
        uint8_t *p = (uint8_t *)arena + at;
        at += (n + 15u) & ~15u;
        if (at > arena_len) { return 3u; }
        if (i < n_in) { in_len[i] = n; in_buf[i] = p; } else { out_len[i - n_in] = n; out_buf[i - n_in] = p; }
    }
    return 0u;
}

static void model_counts(uint32_t *a, uint32_t *b) { *a = n_in; *b = n_out; }

static uint32_t model_io(uint32_t output, uint32_t i, uint8_t **p, uint32_t *n)
{
    if (output ? i >= n_out : i >= n_in) { return 1u; }
    *p = output ? out_buf[i] : in_buf[i];
    *n = output ? out_len[i] : in_len[i];
    return 0u;
}

/* What the driver + hooks.c do on target: arm at the QBASE remap, run, snapshot at the IRQ. */
static void sim_irq(void)
{
    pmu_snapshot_t s;
    probe.dwt_irq = clock_now;
    pmu_session_snapshot(&s);
    probe.at_irq = s;
    probe.status_at_irq = 0xFFFF0020u;
    probe.qread_at_irq = 4096u;
    probe.qsize = 4096u;
    probe.irq_count++;
}

/* WAIT_TRACE: the driver waits in trace_wait() while the "NPU" moves QREAD over a 4096-byte stream (SIM_CMS_LEN) in 16-byte steps,
 * one step per 64 clock cycles, counts events, and raises the completion IRQ at the stream end. The clock advances 7
 * cycles per read, so every poll is real progress. */
static volatile uint8_t sim_sem;
static uint32_t trace_t0, cms_len = 4096u;
static uint32_t sim_now(void)
{
    uint32_t q;
    clock_now += 7u;
    q = ((clock_now - trace_t0) / 64u) * 16u;
    if (q > cms_len) { q = cms_len; }
    REG(0x18u) = q;
    REG(0x04u) = (q < cms_len) ? 0x1u : 0x0u;
    if (q < cms_len) {
        for (uint32_t i = getenv("SIM_TRACE_SLOT0") ? 0u : 1u; i < PMU_SLOTS; i++) {   /* slot 0 fixed unless asked */
            REG(NPU_REG_PMEVCNTR_BASE + 4 * i) += i + 1u;
        }
    }
    if (q == cms_len && sim_sem == 0u) { sim_irq(); sim_sem = 1u; }
    return clock_now;
}

static uint32_t invoke(void)
{
    uint32_t cnten;
    if (getenv("SIM_INVOKE_FAIL")) { return 0u; }
    probe.n_base = 3;
    probe.base[0] = 0x70000010u; probe.base[1] = 0x70100000u; probe.base[2] = 0x31000000u;
    probe.base_size[0] = 100u; probe.base_size[1] = 200u; probe.base_size[2] = 300u;
    probe.power_requests = 2u;
    probe.pmcr_at_arm = pmu_session_arm(&cnten);
    probe.cnten_at_arm = cnten;
    probe.arm_count++;
    probe.dwt_arm = clock_now;
    /* the NPU "runs": counters as a register file would hold them; the arm wrote EVTYPER and the enable mask */
    clock_now += 777u;
    for (uint32_t i = 0; i < PMU_SLOTS; i++) {
        REG(NPU_REG_PMEVCNTR_BASE + 4 * i) = REG(NPU_REG_PMEVTYPER_BASE + 4 * i) * 10u + i;
    }
    REG(NPU_REG_PMCCNTR) = 5000u;
    REG(NPU_REG_PMCCNTR_HI) = 1u;
    REG(NPU_REG_PMOVSSET) = getenv("SIM_OVF") ? 0x1u : 0u;
    for (uint32_t k = 0; k < n_out; k++) {
        for (uint32_t j = 0; j < out_len[k]; j++) { out_buf[k][j] = (uint8_t)(in_buf[0][j % in_len[0]] + k + 1u); }
    }
    if (probe.wait_mode == WAIT_TRACE) {
        sim_sem = 0u; trace_t0 = clock_now; REG(0x18u) = 0u;
        trace_wait(&sim_sem);
    } else {
        if (!getenv("SIM_NO_IRQ")) { sim_irq(); }
        if (getenv("SIM_TWO_IRQ")) { sim_irq(); }
    }
    clock_now += 100u;
    return 1u;
}

static uint32_t dwt(void) { return clock_now += 3u; }
static uint32_t one(void) { return 1u; }
static uint32_t zero(void) { return 0u; }

static uint32_t capabilities(uint8_t *out, uint32_t max, uint32_t load_status)
{
    uint32_t w[CAPS_FIELD_COUNT];
    for (uint32_t i = 0; i < CAPS_FIELD_COUNT; i++) { w[i] = 0xC0000000u + i; }
    w[0] = CAPS_MAGIC; w[1] = RECORD_SCHEMA; w[3] = RECORD_FIELD_COUNT; w[17] = load_status;
    if (sizeof w > max) { return 0u; }
    memcpy(out, w, sizeof w);
    return (uint32_t)sizeof w;
}

static int sim_getc(uint8_t *b)
{
    fflush(stdout);
    if (eof) { return 0; }
    if (read(0, b, 1) != 1) { eof = 1; return 0; }
    return 1;
}

static void sim_putc(uint8_t b) { fputc(b, stdout); }

int main(void)
{
    static const frame_io_t io = {sim_getc, sim_putc};
    staging = calloc(SIM_STAGING, 1);
    ddr = calloc(SIM_DDR, 1);
    REG(NPU_REG_PMCR) = 0x2001u;     /* as MLEK leaves it: cnt_en, 4 event counters reported in num_event_cnt */
    if (getenv("SIM_CMS_LEN")) { cms_len = (uint32_t)strtoul(getenv("SIM_CMS_LEN"), 0, 0); }
    trace_bind(npu_regs, sim_now);
    const runner_ports_t ports = {staging, SIM_STAGING, (uintptr_t)ddr, (uintptr_t)ddr + SIM_DDR, SIM_ARENA,
                                  place_model, model_load, model_counts, model_io, invoke, dwt, one, zero,
                                  capabilities};
    pmu_session_bind(npu_regs);
    runner_init(&ports, &io, 0x44525652u);
    while (!eof) { (void)runner_poll(); }
    fflush(stdout);
    /* expose the register file the arm left, for the test's eyes: EVTYPER, PMCCNTR_CFG, PMCNTENSET, PMCR */
    fprintf(stderr, "REGS evtyper=%u,%u pmccntr_cfg=0x%x cntenset=0x%x pmcr=0x%x\n", REG(NPU_REG_PMEVTYPER_BASE),
            REG(NPU_REG_PMEVTYPER_BASE + 4), REG(NPU_REG_PMCCNTR_CFG), REG(NPU_REG_PMCNTENSET), REG(NPU_REG_PMCR));
    return 0;
}
