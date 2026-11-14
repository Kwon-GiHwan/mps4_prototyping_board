/* Off-target simulator of the driver runner (host tests only): the platform-independent core (runner.c, frame.c,
 * workload.c, record.c, pmu_session.c, probe.c) compiled for the host with fake ports. Frames come on stdin and go to
 * stdout, so host/lib/runner_proto.py talks to it exactly as to the board.
 *
 * Fake pieces: the NPU register block is an array (pmu_session writes into it; the fake "inference" then puts known
 * counter values there and takes the IRQ snapshot, as hooks.c does on target); the model is a tiny "SIMM" container
 * instead of a TFLM model: magic 'SIMM', n_in, n_out, input lengths, output lengths; output k byte j = (input 0 byte
 * (j mod len0)) + k + 1. Behaviour switches (environment): SIM_INVOKE_FAIL, SIM_NO_IRQ, SIM_TWO_IRQ, SIM_OVF, SIM_CMS_LEN,
 * SIM_TRACE_SLOT0, SIM_STALE_AT, SIM_STALE_EVERY, SIM_QREAD_DIP, SIM_RESERVE, and for the placement (placement.h):
 *   SIM_NO_WRITE      the "NPU" leaves the outputs as they are (an output it did not write)
 *   SIM_REGIONCFG=v   the REGIONCFG register reads v at the IRQ instead of what the driver wrote (a port setting not applied)
 *   SIM_QCONFIG=v     the same for QCONFIG
 *   SIM_BAD_SRAM=off  the SRAM word at byte offset off does not keep what is written (a missing or aliased memory)
 *   SIM_FAST=n        the fast memory is n bytes (default 0x6000), the free SRAM starts after it
 *   SIM_IFM_FLIP      the IFM read-back after the load copy differs in one byte
 * Fake memories: "DDR" (model + arena) and "SRAM" (fast memory + free window), both 64 KiB aligned; the stderr line at exit
 * prints both bases so the test can place the arena. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "caps.h"
#include "placement.h"
#include "npu_pmu_regs.h"
#include "pmu_session.h"
#include "probe.h"
#include "trace.h"
#include "record.h"
#include "runner.h"

#define SIM_STAGING (32u << 20)
#define SIM_DDR     (8u << 20)
#define SIM_ARENA   0x10000u
#define SIM_SRAM    0x40000u
#define SIMM_MAGIC  0x4D4D4953u

static uint8_t *staging, *ddr, *sram;
static uint32_t fast_size = 0x6000u;
static uint32_t npu_regs[0x2000 / 4];
static uint32_t n_in, n_out, in_len[8], out_len[8];
static uint8_t *in_buf[8], *out_buf[8];
static uint32_t clock_now = 1000u;
static int eof;

#define REG(off) npu_regs[(off) / 4]

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }

static void place_model(uintptr_t dst, const uint8_t *src, uint32_t len) { memcpy((void *)dst, src, len); }

static void sram_window(uintptr_t *free_base, uintptr_t *limit)
{
    *free_base = (uintptr_t)sram + fast_size;
    *limit = (uintptr_t)sram + SIM_SRAM;
}

/* The D-cache "sync" is where the fake memories misbehave: SIM_BAD_SRAM=off flips a bit of the SRAM word at byte offset
 * off (a memory that does not keep what was written); SIM_IFM_FLIP flips IFM 0 byte 0 once after a model load. */
static int flip_pending;
static void dcache_sync(void)
{
    const char *e = getenv("SIM_BAD_SRAM");
    if (e) { *(volatile uint32_t *)(sram + strtoul(e, 0, 0)) ^= 0x00010000u; }
    if (flip_pending) { in_buf[0][0] ^= 1u; flip_pending = 0; }
}

static uint32_t model_load(uintptr_t base, uint32_t len, uintptr_t arena, uint32_t arena_len)
{
    fprintf(stderr, "LOAD arena=%#lx sram=%#lx ddr=%#lx\n", (unsigned long)arena, (unsigned long)sram,
            (unsigned long)ddr);
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
    flip_pending = getenv("SIM_IFM_FLIP") != 0;
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
    probe.regioncfg_irq = getenv("SIM_REGIONCFG") ? (uint32_t)strtoul(getenv("SIM_REGIONCFG"), 0, 0) : REG(0x3Cu);
    probe.qconfig_irq = getenv("SIM_QCONFIG") ? (uint32_t)strtoul(getenv("SIM_QCONFIG"), 0, 0) : REG(0x1Cu);
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

/* Register reads of trace.c (built with -DTRACE_SIM_READ=sim_npu_read) can return the previous read's data, as the
 * board's yolo traces showed (P0 of the operator-aware pilot); reads are counted from 1 over the process.
 * SIM_STALE_AT=n[,k]: reads n .. n+k-1; SIM_STALE_EVERY=n[,k]: k reads from every n-th (k = 1 unless given). */
static uint32_t sim_reads, sim_last;
static void stale_spec(const char *name, uint32_t *n, uint32_t *k)
{
    const char *e = getenv(name);
    char *end;
    *n = *k = 0u;
    if (e) {
        *n = (uint32_t)strtoul(e, &end, 0);
        *k = (*end == ',') ? (uint32_t)strtoul(end + 1, 0, 0) : 1u;
    }
}
uint32_t sim_npu_read(uint32_t off)
{
    uint32_t v = REG(off), n, k;
    sim_reads++;
    stale_spec("SIM_STALE_AT", &n, &k);
    if (n && sim_reads >= n && sim_reads < n + k) { v = sim_last; }
    stale_spec("SIM_STALE_EVERY", &n, &k);
    if (n && sim_reads % n < k) { v = sim_last; }
    if (off == 0x18u) {                          /* SIM_QREAD_DIP=n: the n-th QREAD read is 16 B behind (plausible, low) */
        static uint32_t qreads;
        const char *e = getenv("SIM_QREAD_DIP");
        if (++qreads == (e ? (uint32_t)strtoul(e, 0, 0) : 0u) && v >= 16u) { v -= 16u; }
    }
    sim_last = v;
    return v;
}

static uint32_t invoke(void)
{
    uint32_t cnten;
    if (getenv("SIM_INVOKE_FAIL")) { return 0u; }
    probe.n_base = 3;
    probe.base[0] = 0x70000010u; probe.base[1] = 0x70100000u; probe.base[2] = 0x31000000u;
    probe.base_size[0] = 100u; probe.base_size[1] = 200u; probe.base_size[2] = 300u;
    /* the driver: QCONFIG and REGIONCFG from ethosu_config_select (hooks.c on target) for QBASE and the 3 bases */
    REG(0x1Cu) = placement_config_select(-1, placement_get());
    REG(0x3Cu) = 0u;
    for (int i = 0; i < 3; i++) { REG(0x3Cu) |= placement_config_select(i, placement_get()) << (2 * i); }
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
    for (uint32_t k = 0; k < n_out && !getenv("SIM_NO_WRITE"); k++) {
        for (uint32_t j = 0; j < out_len[k]; j++) { out_buf[k][j] = (uint8_t)(in_buf[0][j % in_len[0]] + k + 1u); }
    }
    if (probe.wait_mode == WAIT_TRACE) {
        static volatile uint8_t reserve;
        reserve = 1u;
        if (getenv("SIM_RESERVE")) { trace_wait(&reserve, 0u); }   /* ethosu_reserve_driver's take, as on target */
        sim_sem = 0u; trace_t0 = clock_now; REG(0x18u) = 0u; REG(0x20u) = cms_len;
        trace_wait(&sim_sem, 1u);
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
    ddr = aligned_alloc(0x10000u, SIM_DDR);
    sram = aligned_alloc(0x10000u, SIM_SRAM);
    if (getenv("SIM_FAST")) { fast_size = (uint32_t)strtoul(getenv("SIM_FAST"), 0, 0); }
    REG(NPU_REG_PMCR) = 0x2001u;     /* as MLEK leaves it: cnt_en, 4 event counters reported in num_event_cnt */
    REG(0x00u) = 0x20007001u;        /* ID as the board's capabilities report it */
    if (getenv("SIM_CMS_LEN")) { cms_len = (uint32_t)strtoul(getenv("SIM_CMS_LEN"), 0, 0); }
    trace_bind(npu_regs, sim_now);
    const runner_ports_t ports = {staging, SIM_STAGING, (uintptr_t)ddr, (uintptr_t)ddr + SIM_DDR, SIM_ARENA,
                                  place_model, model_load, model_counts, model_io, invoke, dwt, one, zero,
                                  capabilities, sram_window, dcache_sync};
    pmu_session_bind(npu_regs);
    runner_init(&ports, &io, 0x44525652u);
    while (!eof) { (void)runner_poll(); }
    fflush(stdout);
    /* expose the register file the arm left, for the test's eyes: EVTYPER, PMCCNTR_CFG, PMCNTENSET, PMCR */
    fprintf(stderr, "REGS evtyper=%u,%u pmccntr_cfg=0x%x cntenset=0x%x pmcr=0x%x\n", REG(NPU_REG_PMEVTYPER_BASE),
            REG(NPU_REG_PMEVTYPER_BASE + 4), REG(NPU_REG_PMCCNTR_CFG), REG(NPU_REG_PMCNTENSET), REG(NPU_REG_PMCR));
    return 0;
}
