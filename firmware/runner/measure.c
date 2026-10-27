/* One measured RUN: the window, the PMU programming and read-back, the record, RUN_COMPLETE, capabilities. */
#include "runner.h"

#define PMU_EVENTS_POWER_GUARD_CYCLES 65536U /* = PMU_DIAG_POWER_GUARD_CYCLES */
#define PMU_EVENTS_RESET_GUARD_CYCLES 65536U /* = PMU_DIAG_RESET_GUARD_CYCLES */

instrumentation_config_t instr_cfg;

/* ------------------------------------------------------------------------ */
/* Measurement state                                                         */
/*                                                                           */
/* measurement_active is the single gate the log wrappers consult. It is      */
/* volatile because the wrappers may be reached from an ISR.                 */
/* ------------------------------------------------------------------------ */

volatile uint32_t measurement_active;
/* Tier B read seam (amendment 7): filled inside __wrap_printf at the vendor's
 * "Testing CPM signals" printf, i.e. after CMD=0 and before CMD=0xC. */
volatile int32_t last_vendor_rc; /* Tier C: test_u85's own rc, set by __wrap_test_u85 */
volatile uint32_t seam_status, seam_qread; /* NPU STATUS / QREAD at the CPM seam */
volatile uint32_t ofm_mm_count, ofm_mm_max, ofm_mm_first; /* model OFM vs reference */
volatile uint32_t seam_power_ctrl; /* POWER_CTRL at the CPM seam (runner-gap A/B) */
volatile uint32_t seam_fired, seam_cycle_lo, seam_cycle_hi, seam_cycle_stable,
                         seam_cycle_retries, seam_ovf, seam_ev[RUNNER_MAX_NPU_EVENT_COUNTERS];

/* Counted by the wrappers (Contract 3) and by put_raw (Contract 2). */
volatile uint32_t suppressed_printf_calls;
volatile uint32_t suppressed_write_calls;
volatile uint32_t uart_bytes_during_measurement;

/* Populated by runner_u85_irq_wrapper. See "KNOWN, DELIBERATE" note 1: on this
 * build u85.c reinstalls its own vector at the top of test_u85(), so the
 * wrapper is not reached and these stay zero. That is REPORTED, not assumed:
 * npu_vector_hijack_survived carries the evidence. */
static volatile uint32_t sample_isr_entry_timestamp;
static volatile uint32_t sample_isr_exit_timestamp;
static volatile uint32_t sample_qread;
static volatile uint32_t sample_irq_status;
static volatile uint32_t measurement_complete;

/* Contract B step 2: once the final pre-window frame is fully written, all
 * further UART writes are forbidden until the window closes. */
volatile uint32_t uart_tx_forbidden;

static measurement_record_t last_measurement;

int32_t  run_rc;

/* RENAMED from run_valid. "valid" was vague; the predicate this actually holds
 * is "the most recent handle_run() reached its end". GET_RESULT names it
 * directly now. */
int      last_run_completed;

/* CHANGE 2/3 latched run state. last_valid_flags is the single gate
 * GET_RESULT consults; it is cleared at the TOP of every handle_run so a run
 * that dies partway can never leave a stale "valid" behind. */
static uint32_t run_sequence_counter;
uint32_t last_run_sequence;

/* The sequence of the last run that COMPLETED, which is NOT the same thing as
 * last_run_sequence. last_run_sequence is stamped at the TOP of handle_run, so
 * mid-run it already names a run with no result. last_completed_sequence is
 * written only at the very end, next to last_run_completed, so the pair can
 * never disagree. GET_RESULT compares the host's expected_run_sequence against
 * THIS one. Zero is never a valid value: run_sequence_counter is
 * pre-incremented, so real sequences start at 1. */
uint32_t last_completed_sequence;

uint32_t last_valid_flags;
uint32_t last_poison_crc;
uint32_t last_output_crc;
uint32_t last_result_region_crc;

/* ------------------------------------------------------------------------ */
/* CHANGE 2: poison bounds for the NPU OUTPUT region.                        */
/*                                                                           */
/* .sec_noinit is NOLOAD, so it SURVIVES RESET. That is the whole hazard:    */
/* if a RUN silently fails, the previous run's output tensor is still sitting */
/* in DDR and a CRC over it still reproduces the golden value. The producer   */
/* must destroy that data before every run; no amount of host-side            */
/* cross-checking can substitute.                                            */
/*                                                                           */
/* The region is bounded by two GLOBAL symbols emitted by the u85 test        */
/* objects, NOT by hardcoded addresses -- if the layout ever shifts, these    */
/* follow it, and the build gate re-checks base/size independently:           */
/*                                                                           */
/*   90020900 B test2_out_data_0   first output block  -> region START       */
/*   90020f90 B test0_out_data_0   zero-size end marker -> region END        */
/*                                                                           */
/* SCOPE: the OUTPUT region only (1680 B), NOT the 2304 B scratch buffer at   */
/* 0x90020000..0x90020900. Scratch is regenerated by the NPU on every run, so */
/* poisoning it buys no additional detection while widening the blast radius. */
/*                                                                           */
/* test3_out_data_0 (the Convolution output the golden CRC covers) is         */
/* `static` and has no external linkage. It does not need one: it lies INSIDE */
/* [test2_out_data_0, test0_out_data_0), so poisoning the region covers it,   */
/* and GET_RESULT receives base+len from the host anyway. */
extern uint8_t test2_out_data_0[];
extern uint8_t test0_out_data_0[];

/* ------------------------------------------------------------------------ */
/* CONTRACT A: NPU completion IRQ wrapper.                                   */
/*                                                                           */
/* The stock u85_irq_handler reads NPU_REG_STATUS, then writes NPU_REG_CMD=2 */
/* to clear the IRQ. Anything we want from the NPU must therefore be sampled */
/* BEFORE it runs -- afterwards the status is gone. Hence: snapshot first,   */
/* then chain, then take the exit timestamp.                                 */
/* ------------------------------------------------------------------------ */

typedef void (*irq_handler_t)(void);

static irq_handler_t original_u85_handler;

__attribute__((noinline))
static void runner_u85_irq_wrapper(void)
{
    if (measurement_active) {
        /* Instrumentation FIRST, before the stock handler destroys state. */
        sample_isr_entry_timestamp = read_timestamp();
        sample_qread               = npu_read(NPU_OFF_QREAD);
        sample_irq_status          = npu_read(NPU_OFF_STATUS);
        /* PMU snapshot slot -- stubbed OFF this milestone. */
    }

    if (original_u85_handler != (irq_handler_t)0) {
        original_u85_handler();
    }

    if (measurement_active) {
        sample_isr_exit_timestamp = read_timestamp();
        measurement_complete      = 1U;
    }
}

/* Install guard: a repeated install must NEVER capture the wrapper as its own
 * original, which would produce infinite recursion on the next IRQ. */
static void install_u85_irq_wrapper(void)
{
    irq_handler_t current = (irq_handler_t)NVIC_GetVector(NPU0_IRQn);

    if (current == &runner_u85_irq_wrapper) {
        return; /* already installed -- do not re-capture */
    }

    original_u85_handler = current;
    NVIC_SetVector(NPU0_IRQn, (uint32_t)(uintptr_t)&runner_u85_irq_wrapper);
    __DSB();
    __ISB();
}

static void restore_u85_irq_vector(void)
{
    if (original_u85_handler != (irq_handler_t)0) {
        NVIC_SetVector(NPU0_IRQn, (uint32_t)(uintptr_t)original_u85_handler);
        __DSB();
        __ISB();
    }
}

/* ------------------------------------------------------------------------ */
/* Measurement configuration identity (Contract 1)                          */
/*                                                                          */
/* A CRC over the values that actually define the measurement configuration */
/* compiled into THIS binary. Two builds whose measurement setup differs in */
/* any of these respects cannot produce the same id, so A/B/C results can   */
/* never be silently mixed. Deterministic: no timestamps, no addresses that */
/* vary between identical rebuilds.                                         */
/* ------------------------------------------------------------------------ */

static uint32_t compute_measurement_config_id(void)
{
    uint8_t buf[64];
    wcur_t c = {buf, 0};

    put32(&c, RUNNER_CAPABILITY_SCHEMA_VERSION);
    put32(&c, RUNNER_BUILD_PROFILE);
    put32(&c, RUNNER_FIRMWARE_BUILD_ID);
    put32(&c, RUNNER_MEASURE_ENABLE_PMU);
    put32(&c, RUNNER_TX_DRAIN_US);
    put32(&c, RUNNER_EXPECTED_TEST19_CRC32);
    put32(&c, sym_u32(__runner_staging_start__));
    put32(&c, sym_u32(__runner_staging_end__));
    put32(&c, sym_u32(__runner_result_start__));
    put32(&c, sym_u32(__runner_result_end__));
    put32(&c, RUNNER_UART_CHAR_US);
    put32(&c, RUNNER_TX_RESIDUAL_CHARS);
    /* Which IRQ line the boundary masks, and which it deliberately leaves on. */
    put32(&c, (uint32_t)UART0_RX_IRQn);
    put32(&c, (uint32_t)NPU0_IRQn);

    return crc32_buffer(buf, c.used);
}


/* ------------------------------------------------------------------------ */
/* CONTRACT 1: GET_CAPABILITIES                                             */
/* Raw register values are always reported. Where a field is derived, BOTH   */
/* the raw register and the interpretation are present.                      */
/* ------------------------------------------------------------------------ */



/* cache_mode interpretation, derived from SCB->CCR */
#define CACHE_MODE_NONE 0U
#define CACHE_MODE_I    1U
#define CACHE_MODE_D    2U
#define CACHE_MODE_ID   3U

void build_capabilities(uint8_t *out)
{
    wcur_t c = {out, 0};

    uint32_t ccr      = SCB->CCR;
    uint32_t mpu_type = MPU->TYPE;
    uint32_t cache_mode = CACHE_MODE_NONE;

    if (ccr & SCB_CCR_IC_Msk) {
        cache_mode |= CACHE_MODE_I;
    }
    if (ccr & SCB_CCR_DC_Msk) {
        cache_mode |= CACHE_MODE_D;
    }

    /* --- identity --- */
    put32(&c, RUNNER_FIRMWARE_BUILD_ID);
    put32(&c, RUNNER_VERSION);
    put32(&c, RUNNER_CAPABILITY_SCHEMA_VERSION);
    put32(&c, RUNNER_BUILD_PROFILE);
    put32(&c, compute_measurement_config_id());

    /* --- memory windows, straight from the linker --- */
    put32(&c, sym_u32(__runner_staging_start__));
    put32(&c, (uint32_t)(__runner_staging_end__ - __runner_staging_start__));
    put32(&c, sym_u32(__runner_result_start__));
    put32(&c, (uint32_t)(__runner_result_end__ - __runner_result_start__));
    put32(&c, RUNNER_EXPECTED_TEST19_CRC32);

    /* --- CPU, raw then derived --- */
    put32(&c, SCB->CPUID);            /* raw */
    put32(&c, ccr);                   /* raw */
    put32(&c, MEMSYSCTL->MSCR);       /* raw */
    put32(&c, MPU->CTRL);             /* raw */
    put32(&c, mpu_type);              /* raw */
    put32(&c, (mpu_type & MPU_TYPE_DREGION_Msk) >> MPU_TYPE_DREGION_Pos);
                                      /* derived: MPU_REGION_COUNT */
    put32(&c, cache_mode);            /* derived from CCR */

    /* --- NPU, raw --- */
    put32(&c, npu_read(NPU_OFF_ID));      /* raw NPU_ID */
    put32(&c, npu_read(NPU_OFF_CONFIG));  /* raw NPU_CONFIG */
    put32(&c, npu_read(NPU_OFF_STATUS));  /* raw, snapshot at call time */

    /* --- NPU PMU discovery -------------------------------------------
     * This DOES touch the PMU, deliberately. The OFF contract is scoped to the
     * RUN PATH, not to the whole session: capabilities is a discovery call
     * made outside any measurement window, and pmu_probe_performed says so.
     * Reporting a hardware count needs the hardware to be asked. */
    pmu_probe();
    put32(&c, pmu_reg_read(NPU_REG_PMCR));  /* raw PMCR */
    put32(&c, pmu_hw_event_counters);       /* PMCR.num_event_cnt */
    put32(&c, NPU_PMU_EVENT_COUNTER_WIDTH); /* 32, event counters */
    put32(&c, pmu_present);

    /* --- clocks / boundary properties --- */
    put32(&c, SystemCoreClock);
    put32(&c, 0U); /* npu_clock_hz: no discoverable source, reported unknown */
    put32(&c, RUNNER_TX_DRAIN_US);
    put32(&c, RUNNER_TX_RESIDUAL_CHARS);
    /* --- appended: the three capacities kept apart, plus what OFF/END_ONLY
     * this build actually supports. ABI capacity is a wire-format property;
     * hardware capacity is what the device reports; effective is the only one
     * that bounds a configuration request. */
    put32(&c, pmu_probe_performed);
    put32(&c, RUNNER_MAX_NPU_EVENT_COUNTERS);   /* abi_event_slot_count */
    put32(&c, pmu_effective_event_slots());
    put32(&c, NPU_PMU_CYCLE_COUNTER_WIDTH);     /* 48, not 64 */
    put32(&c, (1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY) | (1U << INSTRUMENTATION_EVENTS));

    /* completion_wait_mode == BUSY_POLL. u85.c defines BUSY_SLEEP, so
     * wait_for_irq() spins instead of using __WFI(). This is NOT cosmetic:
     * the CPU stays fully active during NPU execution, CPU and NPU contend for
     * DDR and interconnect, system power differs from an idle-wait
     * implementation, and submit->IRQ is a polling path rather than a sleep
     * latency. wait_for_irq() is deliberately NOT modified -- a WFI variant
     * would be a separate experiment configuration, never part of the golden
     * comparison. */
    put32(&c, COMPLETION_WAIT_MODE_BUSY_POLL);
}

/* ------------------------------------------------------------------------ */
/* CHANGE 2: poisoning the NPU output region                                 */
/* ------------------------------------------------------------------------ */

/* Sequence-derived, never a constant. A fixed fill could in principle be what
 * a genuine output happens to contain; a value that changes every run cannot
 * be coincidentally reproduced by a stale buffer. */
static uint32_t poison_word(uint32_t sequence, size_t index)
{
    return 0xA5C30000u ^ sequence ^ (uint32_t)(index * 0x9E3779B9u);
}

static uint8_t *poison_region_base(void)
{
    return test2_out_data_0;
}

static uint32_t poison_region_length(void)
{
    /* Symbol-derived. If the layout ever inverts these, produce 0 rather than
     * a colossal length -- the build gate is what actually catches a move. */
    if (test0_out_data_0 <= test2_out_data_0) {
        return 0U;
    }
    return (uint32_t)(test0_out_data_0 - test2_out_data_0);
}

/* D-cache maintenance around the poison stores and the NPU's writes.
 *
 * CURRENTLY INERT ON THIS PLATFORM, BY MEASUREMENT OF THE SOURCE TREE: nothing
 * in this image calls SCB_EnableDCache() and the MPU is left unconfigured, so
 * CCR.DC is clear and both helpers below do nothing at runtime today. They are
 * written guarded on the live CCR.DC bit rather than omitted so that enabling
 * the cache later cannot silently reintroduce a coherency hazard between the
 * CPU's poison stores and the NPU's DMA writes to the same region. */
static void poison_cache_clean(void *base, uint32_t len)
{
#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    if (SCB->CCR & SCB_CCR_DC_Msk) {
        SCB_CleanDCache_by_Addr((uint32_t *)base, (int32_t)len);
    }
#else
    (void)base;
    (void)len;
#endif
}

static void poison_cache_invalidate(void *base, uint32_t len)
{
#if defined(__DCACHE_PRESENT) && (__DCACHE_PRESENT == 1U)
    if (SCB->CCR & SCB_CCR_DC_Msk) {
        SCB_InvalidateDCache_by_Addr((uint32_t *)base, (int32_t)len);
    }
#else
    (void)base;
    (void)len;
#endif
}

/* Destroy the previous run's output and return the CRC of what we wrote.
 * Returns 0 length -> caller must not set RUN_VALID_OUTPUT_CHANGED. */
static uint32_t poison_output_region(uint32_t sequence)
{
    uint8_t *base = poison_region_base();
    uint32_t len  = poison_region_length();
    uint32_t words = len / 4U;

    for (uint32_t i = 0; i < words; i++) {
        wr_u32(base + (i * 4U), poison_word(sequence, (size_t)i));
    }

    poison_cache_clean(base, len);
    return crc32_buffer(base, len);
}


/* noinline is load-bearing, not cosmetic: the denylist checker locates the measured path by
 * symbol name in the linked ELF; inlined into handle_run the root would disappear and the check
 * fails closed. */
__attribute__((noinline))
static int32_t run_fixed_inference(void)
{
    struct u85_test_data_t d = {.name = "U85 Convolution test"};
    struct u85_test_meta_data_t m = {.u85_test_data = &d, .num_tests = 1};
    int32_t rc;


    rc = (int32_t)apU85Conv_TEST(&m);
    return rc;
}

/* ------------------------------------------------------------------------ */
/* CONTRACT 2: the measurement boundary                                      */
/* ------------------------------------------------------------------------ */

/* CONTRACT B. Transmit-empty is not observable on this peripheral, so a fixed
 * drain delay based on blocking-write completion and assumed hardware residual
 * depth is applied -- a conservative time bound, NOT a detected condition.
 *
 * TXBF is NOT consulted here. It means "buffer full", not "UART empty", and
 * using it as a drain check would be exactly the error this contract forbids.
 *
 * Preconditions, established by the caller before this runs:
 *   1. every byte of the final frame was written by put_raw, which blocks on
 *      TXBF before each store, and that loop ran to completion;
 *   2. uart_tx_forbidden is already set, so nothing can refill the holding
 *      register while we wait;
 *   3. there is no software TX queue to confirm empty -- put_raw is
 *      synchronous.
 * This function supplies only step 4: the time bound. */
static void uart_tx_drain_fixed_delay(uint32_t ts_valid)
{
    if (ts_valid && SystemCoreClock != 0U) {
        uint32_t cycles = (SystemCoreClock / 1000000U) * RUNNER_TX_DRAIN_US;
        uint32_t start  = read_timestamp();
        while ((read_timestamp() - start) < cycles) {
        }
    } else {
        for (volatile uint32_t i = 0; i < RUNNER_TX_DRAIN_FALLBACK_LOOPS; i++) {
        }
    }
}

static void build_measurement_payload(uint8_t *out);
static void build_run_complete_payload(uint8_t *out);

static uint32_t popcount32(uint32_t v)
{
    uint32_t n = 0;

    while (v) {
        v &= (v - 1U);
        n++;
    }
    return n;
}

void handle_run(uint32_t sequence)
{
    /* Zero-initialised: the 30 fields appended for the PMU candidate are
     * not all assigned yet, and an unassigned field must serialise as 0,
     * never as whatever was on the stack. */
    measurement_record_t r = {0};
    uint8_t accept[4];
    uint8_t resp[RUN_COMPLETE_PAYLOAD_SIZE];
    uint32_t ispr_open[3];
    uint32_t ispr_close[3];
    uint32_t ts_valid;
    uint32_t uart_rx_was_enabled;
    uint32_t state_after;
    uint32_t poison_crc;
    uint32_t output_crc;
    uint32_t result_region_crc;
    uint32_t poison_len;
    uint32_t flags;

    memset(&r, 0, sizeof(r));

    /* --- CHANGE 2/3: invalidate the previous result FIRST. ----------------
     * Everything below can fail. If it does, the firmware must not be able to
     * present the previous run's data as this run's, so the gate GET_RESULT
     * consults is cleared before anything else happens. */
    last_run_completed      = 0;
    last_completed_sequence = 0;
    last_valid_flags        = 0;

    run_sequence_counter++;
    last_run_sequence = run_sequence_counter;

    /* --- Destroy the stale output, then record what we wrote. -------------
     * .sec_noinit is NOLOAD and survives reset: without this, a silently
     * failed run leaves the previous output in place and its CRC still
     * reproduces the golden value. */
    poison_len = poison_region_length();
    poison_crc = poison_output_region(last_run_sequence);

    /* --- Program the PMU. Deliberately a no-op: PMU is OFF. --------------- */

    /* --- Timestamp source ready BEFORE the window, not inside it. -------- */
    ts_valid = timestamp_source_ready();

    /* --- Capture pre-window IRQ configuration. --------------------------- */
    r.systick_ctrl            = SysTick->CTRL;
    r.systick_enabled         = (SysTick->CTRL & SysTick_CTRL_ENABLE_Msk) ? 1U : 0U;
    r.npu_irq_priority        = NVIC_GetPriority(NPU0_IRQn);
    r.uart_rx_irq_priority    = NVIC_GetPriority(UART0_RX_IRQn);
    uart_rx_was_enabled       = (NVIC_GetEnableIRQ(UART0_RX_IRQn) != 0U) ? 1U : 0U;
    r.uart_rx_irq_was_enabled = uart_rx_was_enabled;
    r.npu_vector_before       = NVIC_GetVector(NPU0_IRQn);

    /* --- RUN_ACCEPTED, transmitted while TX is still legal. -------------- */
    runner_state = ST_RUNNING;
    wr_u32(&accept[0], 0U); /* 0 == accepted */
    send_ack(CMD_RUN, sequence, accept, sizeof(accept));

    /* --- Contract B, in order. -------------------------------------------
     * 1. send_ack above used the blocking writer and has returned, so every
     *    byte of RUN_ACCEPTED has been written to completion.
     * 2. forbid all further UART writes from this point.
     * 3. no software TX queue exists (put_raw is synchronous).
     * 4. burn the fixed, conservative drain bound. */
    uart_tx_forbidden = 1U;
    __DSB();
    uart_tx_drain_fixed_delay(ts_valid);

    /* --- Block RX at the NVIC. NOT BASEPRI: that would mask NPU0 too and
     *     u85.c's busy-poll on the ISR flag would never complete. --------- */
    NVIC_DisableIRQ(UART0_RX_IRQn);
    NVIC_DisableIRQ(UART0_IRQn);
    NVIC_DisableIRQ(UART_OVFL_IRQn);
    __DSB();
    __ISB();

    /* --- Install the instrumentation wrapper (guarded against re-capture).
     *     u85.c overwrites this at the top of test_u85(); we read the vector
     *     back after the window so the outcome is evidence, not assumption. */
    sample_isr_entry_timestamp = 0;
    sample_isr_exit_timestamp  = 0;
    sample_qread               = 0;
    sample_irq_status          = 0;
    measurement_complete       = 0;
    install_u85_irq_wrapper();
    r.npu_vector_installed = NVIC_GetVector(NPU0_IRQn);

    /* --- Clear any stale RX condition so post-window sampling is honest. - */
    if (UART0_REGS[REG_STATE] & STATE_RXBF) {
        (void)UART0_REGS[REG_DATA];
    }
    UART0_REGS[REG_STATE] = STATE_RXOR;

    ispr_open[0] = NVIC->ISPR[0];
    ispr_open[1] = NVIC->ISPR[1];
    ispr_open[2] = NVIC->ISPR[2];

    r.primask_at_open = __get_PRIMASK();
    r.basepri_at_open = __get_BASEPRI();

    /* Ordering barrier: every poison store above must be observable before the
     * NPU is submitted to, otherwise the device could read pre-poison data. */
    __DMB();
    __DSB();

    /* ================= WINDOW OPENS ================= */
    seam_fired = 0U; seam_cycle_lo = 0U; seam_cycle_hi = 0U; seam_cycle_stable = 0U;
    seam_cycle_retries = 0U; seam_ovf = 0U;
    last_vendor_rc = -1; seam_status = 0U; seam_qread = 0U;
    ofm_mm_count = 0U; ofm_mm_max = 0U; ofm_mm_first = 0xFFFFFFFFU; seam_power_ctrl = 0U;
    for (unsigned k = 0; k < RUNNER_MAX_NPU_EVENT_COUNTERS; k++) { seam_ev[k] = 0U; }
    measurement_active = 1U;
    __DSB();
    __ISB();

    r.ts_open = read_timestamp();

    /* A COPY of the configuration, taken before anything runs. Changing the
     * mode after this point must not rewrite this run's record. */
    {
        const instrumentation_config_t cfg = instr_cfg;
        const uint32_t pmu_r0 = pmu_mmio_read_count;
        const uint32_t pmu_w0 = pmu_mmio_write_count;
        uint32_t ts_prog_start, ts_prog_end;
        uint32_t cycle_stable = 0U, cycle_retries = 0U, ovf = 0U;
        uint64_t cycles = 0U;
        unsigned i;

        r.record_schema_version          = 1U;
        r.instrumentation_mode_requested = cfg.mode;
        r.event_set_id                   = cfg.event_set_id;
        r.configuration_sequence         = cfg.configuration_sequence;
        r.abi_event_slot_count           = RUNNER_MAX_NPU_EVENT_COUNTERS;
        r.expected_hw_event_counter_count = NPU_PMU_EVENT_COUNTERS_MAX;
        r.requested_event_count          = cfg.event_count;
        r.completion_wait_mode           = COMPLETION_WAIT_MODE_BUSY_POLL;
        for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
            r.event_codes[i] = cfg.event_codes[i];
        }

        ts_prog_start = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {
            uint32_t cnten;

            /* PMCR.cnt_en is a GLOBAL gate; it does not arm any counter.
             * npu_pmu_reset_counters() clears PMCNTEN for everything, so the
             * cycle counter must be armed explicitly afterwards. Skipping this
             * is what produced window_cycles == 0 with every other flag green. */
            if (cfg.mode == INSTRUMENTATION_EVENTS) {
                /* Tier B (amendment 8). The previous test released clock/power with
                 * CMD=0xC; PMU writes made in that state land in the register file
                 * and never engage the counters (boots 5-8). Hold both Q interfaces
                 * first, let it settle, then reset+enable under held power, wait,
                 * then do the final programming -- the sequence PMU_DIAG/QUAL proved. */
                npu_write(NPU_OFF_CMD, 0U);
                __DSB(); __ISB();
                timing_wait_cycles(PMU_EVENTS_POWER_GUARD_CYCLES);
                npu_pmu_disable();
                pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
                pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
                pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);
                pmu_reg_write(NPU_REG_PMCR, NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK
                                            | NPU_PMCR_CYCLE_CNT_RST_MSK);
                __DSB(); __ISB();
                timing_wait_cycles(PMU_EVENTS_RESET_GUARD_CYCLES);
                pmu_reg_write(NPU_REG_PMCNTENSET,
                              NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U));
                for (i = 0; i < cfg.event_count; i++) {
                    pmu_reg_write(NPU_REG_PMEVTYPER_BASE + 4U * i, cfg.event_codes[i] & 0x3FFU);
                }
                __DSB();
            } else {
                npu_pmu_disable();
                npu_pmu_reset_counters();
                pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);
            }
            cnten = pmu_reg_read(NPU_REG_PMCNTENSET);
            r.cycle_counter_armed =
                (cnten & NPU_PMU_PMCNTEN_CYCLE_MASK) ? 1U : 0U;

            r.npu_pmu_present          = pmu_present;
            r.pmu_probe_performed      = pmu_probe_performed;
            r.hw_event_counter_count   = pmu_hw_event_counters;
            r.effective_event_slot_count = pmu_effective_event_slots();
        }
        ts_prog_end = read_timestamp();
        r.t_pmu_programming = ts_prog_end - ts_prog_start;

        __DSB();
        __ISB();

        r.t_pmu_enable = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {
            uint32_t pmcr;

            npu_pmu_enable();
            pmcr = pmu_reg_read(NPU_REG_PMCR);
            /* "Armed" and "globally enabled" are separate facts, and neither is
             * implied by a successful register read. Both are recorded. */
            r.cycle_global_enable_verified =
                (pmcr & NPU_PMCR_CNT_EN_MSK) ? 1U : 0U;
            __DSB();
        }

        r.t_inference_call_enter = read_timestamp();
        run_rc = run_fixed_inference();
        r.t_inference_call_return = read_timestamp();

        /* Disable FIRST, snapshot second: stopping the counter as close to the
         * return as possible bounds what the window can contain, and a stopped
         * counter cannot tear. The stable read stays regardless, because the
         * ordering of the disable against the MMIO read is not guaranteed. */
        if (cfg.mode == INSTRUMENTATION_END_ONLY || cfg.mode == INSTRUMENTATION_EVENTS) {
            /* Order matters and is not negotiable:
             *   clear enable -> DSB -> PMCR readback -> cycle -> overflow.
             * The DSB makes the disable write observable before any snapshot
             * read is issued; the readback confirms the block accepted it.
             * Both cost one MMIO access each and are part of the EXPECTED
             * END_ONLY access count, not accidental traffic.
             * Overflow is snapshotted AFTER the counters and is never cleared
             * here -- clearing before the snapshot would destroy the evidence
             * that decides cycle_valid. It is cleared at the START of the next
             * run instead. */
            npu_pmu_disable();
            __DSB();
            r.pmcr_at_disable = pmu_reg_read(NPU_REG_PMCR);
            r.t_pmu_disable = read_timestamp();
            cycles = npu_pmu_read_cycles(&cycle_stable, &cycle_retries);
            ovf    = npu_pmu_overflow_status();

            r.npu_pmu_window_cycles_lo = (uint32_t)(cycles & 0xFFFFFFFFU);
            r.npu_pmu_window_cycles_hi = (uint32_t)(cycles >> 32);
            r.npu_pmu_cycle_overflow   = (ovf & NPU_PMU_PMOVS_CYCLE_OVF_MASK) ? 1U : 0U;
            r.npu_pmu_cycle_read_retry_count = cycle_retries;
            r.cycle_read_stable   = cycle_stable ? 1U : 0U;
            r.pmu_sample_valid    = 1U;
            /* These are DIFFERENT facts and the milestone-1 defect proved it:
             * the counter read cleanly, was never armed, and still reported
             * valid. Validity now requires every one of them. Progress is
             * tracked separately -- a zero-cycle window is not universally
             * illegal, so the test-19 gate demands progress explicitly rather
             * than folding it into validity here. */
            r.cycle_progress_observed =
                (r.npu_pmu_window_cycles_lo || r.npu_pmu_window_cycles_hi) ? 1U : 0U;
            r.npu_pmu_cycle_valid =
                (r.pmu_sample_valid && r.cycle_counter_armed
                 && r.cycle_global_enable_verified && r.cycle_read_stable
                 && !r.npu_pmu_cycle_overflow) ? 1U : 0U;
            if (cfg.mode == INSTRUMENTATION_EVENTS) {
                /* Tier B (amendment 7): the vendor test releases clock/power (CMD=0xC)
                 * before returning, so the reads above saw a dead PMU. The read seam in
                 * __wrap_printf snapshotted the live counters just before that release;
                 * the record carries the snapshot and recomputes validity from it. */
                uint32_t armed = (1U << cfg.event_count) - 1U;
                r.npu_pmu_window_cycles_lo = seam_cycle_lo;
                r.npu_pmu_window_cycles_hi = seam_cycle_hi;
                r.cycle_read_stable        = seam_cycle_stable ? 1U : 0U;
                r.npu_pmu_cycle_read_retry_count = seam_cycle_retries;
                r.npu_pmu_cycle_overflow   = (seam_ovf & NPU_PMU_PMOVS_CYCLE_OVF_MASK) ? 1U : 0U;
                r.cycle_progress_observed  = (seam_cycle_lo || seam_cycle_hi) ? 1U : 0U;
                r.npu_pmu_cycle_valid =
                    (r.pmu_sample_valid && r.cycle_counter_armed
                     && r.cycle_global_enable_verified && r.cycle_read_stable
                     && !r.npu_pmu_cycle_overflow) ? 1U : 0U;
                for (i = 0; i < cfg.event_count; i++) {
                    r.event_values[i] = seam_ev[i];
                }
                r.event_overflow_mask = seam_ovf & 0xFFU;
                r.applied_event_count = cfg.event_count;
                r.event_valid_mask    = armed & ~r.event_overflow_mask;
                r.read_seam_fired     = seam_fired;
                r.vendor_rc           = (uint32_t)last_vendor_rc;
                r.seam_npu_status     = seam_status;
                r.seam_npu_qread      = seam_qread;
                r.ofm_mismatch_count  = ofm_mm_count;
                r.ofm_max_abs_diff    = ofm_mm_max;
                r.ofm_first_mismatch  = ofm_mm_first;
            } else {
                /* END_ONLY, unchanged: no event slot is ever armed. */
                r.event_valid_mask    = 0U;
                r.event_overflow_mask = 0U;
                r.applied_event_count = 0U;
                r.read_seam_fired     = 0U;
                r.vendor_rc           = 0U;
                r.seam_npu_status     = 0U;
                r.seam_npu_qread      = 0U;
                r.ofm_mismatch_count  = 0U;
                r.ofm_max_abs_diff    = 0U;
                r.ofm_first_mismatch  = 0xFFFFFFFFU;
            }
        } else {
            r.t_pmu_disable = read_timestamp();
        }

        r.instrumentation_mode_applied = cfg.mode;
        r.cpu_call_window_cycles =
            r.t_inference_call_return - r.t_inference_call_enter;
        r.cpu_return_to_pmu_disable_cycles =
            r.t_pmu_disable - r.t_inference_call_return;
        /* The runtime half of the OFF contract: in OFF this must be 0/0. */
        r.pmu_mmio_read_count_delta  = pmu_mmio_read_count - pmu_r0;
        r.pmu_mmio_write_count_delta = pmu_mmio_write_count - pmu_w0;
        r.pmu_mmio_read_count_total  = pmu_mmio_read_count;
        r.pmu_mmio_write_count_total = pmu_mmio_write_count;
    }

    r.ts_close = read_timestamp();

    /* --- CHANGE 2/3: decide validity while the window is still shut. ------
     * Timing is already captured (ts_close above), and measurement_active is
     * still 1 here, so the no-transmit guarantee covers the CRC work too.
     *
     * The invalidate is inert today (D-cache disabled); it exists so that the
     * NPU's DMA writes cannot be masked by stale cache lines if the cache is
     * ever turned on. */
    poison_cache_invalidate(poison_region_base(), poison_len);
    __DSB();

    output_crc        = crc32_buffer(poison_region_base(), poison_len);
    result_region_crc = crc32_buffer(
        (const void *)(uintptr_t)__sec_noinit_start,
        (uint32_t)(__sec_noinit_end - __sec_noinit_start));

    flags = RUN_VALID_RUN_COMPLETED;
    if (run_rc == 0) {
        flags |= RUN_VALID_RUN_RC_OK;
    }
    /* The load-bearing test. A zero-length region cannot prove anything, so it
     * deliberately does NOT set the flag. */
    if (poison_len != 0U && output_crc != poison_crc) {
        flags |= RUN_VALID_OUTPUT_CHANGED;
    }
    /* COARSE by name and by nature: it only asserts that the timestamp source
     * was live and that some time passed. It is not a plausibility bound on
     * the duration. */
    if (ts_valid && (r.ts_close - r.ts_open) != 0U) {
        flags |= RUN_VALID_COARSE_WINDOW;
    }
    /* CRC over the WHOLE .sec_noinit, NOT over the 256-byte golden window.
     * Corroborating evidence only -- never the 0x27084C4C judgement. See the
     * flag's definition. */
    if (result_region_crc == RUNNER_EXPECTED_TEST19_CRC32) {
        flags |= RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH;
    }

    __DSB();
    __ISB();
    measurement_active = 0U;
    /* ================= WINDOW CLOSED ================ */

    /* Everything from here on -- CRC, comparison, serialisation, UART TX --
     * happens strictly after measurement_active has been cleared. */

    ispr_close[0] = NVIC->ISPR[0];
    ispr_close[1] = NVIC->ISPR[1];
    ispr_close[2] = NVIC->ISPR[2];

    r.npu_vector_at_close = NVIC_GetVector(NPU0_IRQn);
    r.npu_vector_hijack_survived =
        (r.npu_vector_at_close == r.npu_vector_installed) ? 1U : 0U;
    /* The wrapper only produces timestamps if it actually ran. */
    r.isr_ts_valid = (measurement_complete && r.npu_vector_hijack_survived)
                         ? 1U : 0U;

    r.npu_status_at_close = npu_read(NPU_OFF_STATUS);
    r.npu_qread_at_close  = npu_read(NPU_OFF_QREAD);

    /* Restore the original NPU vector, then restore the UART IRQ enables to
     * EXACTLY their prior state. */
    restore_u85_irq_vector();
    if (uart_rx_was_enabled) {
        NVIC_EnableIRQ(UART0_RX_IRQn);
    }
    __DSB();
    __ISB();
    r.uart_rx_irq_masked_during = 1U;

    /* --- Sample what arrived while we were not listening. ---------------- */
    /* The CMSDK APB UART has a ONE-BYTE receive buffer. We can therefore
     * observe "at least one byte arrived" (RXBF) and "more than one arrived"
     * (RXOR). We CANNOT count the true number of bytes the host sent. The
     * overrun flag is the meaningful signal here, not the byte count. */
    state_after = UART0_REGS[REG_STATE];
    r.rx_bytes_during_measurement   = (state_after & STATE_RXBF) ? 1U : 0U;
    r.rx_overrun_during_measurement = (state_after & STATE_RXOR) ? 1U : 0U;
    if (state_after & STATE_RXBF) {
        (void)UART0_REGS[REG_DATA]; /* discard: NOT parsed, per contract */
    }
    if (state_after & STATE_RXOR) {
        UART0_REGS[REG_STATE] = STATE_RXOR;
        rx_overrun_count++;
    }

    /* --- Unexpected IRQ evidence. ---------------------------------------- */
    /* This is a PENDING-BIT DELTA, not a true count. An interrupt that fired
     * AND was serviced inside the window leaves no pending bit and is missed.
     * Since every line except NPU0 is disabled here, a set bit is real
     * evidence; a clear bit is weaker evidence. Reported as such. */
    r.unexpected_irq_mask0 =
        (ispr_close[0] & ~ispr_open[0]) & ~(1U << ((uint32_t)NPU0_IRQn & 31U));
    r.unexpected_irq_mask1 = ispr_close[1] & ~ispr_open[1];
    r.unexpected_irq_mask2 = ispr_close[2] & ~ispr_open[2];
    r.unexpected_irq_count = popcount32(r.unexpected_irq_mask0) +
                             popcount32(r.unexpected_irq_mask1) +
                             popcount32(r.unexpected_irq_mask2);

    /* --- Fill the rest of the record. ------------------------------------ */
    r.valid                         = 1U;
    r.run_rc                        = (uint32_t)run_rc;
    r.ts_elapsed                    = r.ts_close - r.ts_open;
    r.ts_source_valid               = ts_valid;
    r.isr_entry_ts                  = sample_isr_entry_timestamp;
    r.isr_exit_ts                   = sample_isr_exit_timestamp;
    r.measurement_complete          = measurement_complete;
    r.npu_qread_at_irq              = sample_qread;
    r.npu_irq_status_at_irq         = sample_irq_status;
    r.uart_bytes_during_measurement = uart_bytes_during_measurement;
    r.suppressed_printf_calls       = suppressed_printf_calls;
    r.suppressed_write_calls        = suppressed_write_calls;
    r.cpu_clock_hz                  = SystemCoreClock;
    r.npu_clock_hz                  = 0U; /* unknown, see build_capabilities */
    r.demcr                         = REG32(DEMCR_ADDR);
    r.dwt_ctrl                      = REG32(DWT_CTRL_ADDR);
    r.pmu_enabled                   = RUNNER_MEASURE_ENABLE_PMU;
    r.measurement_config_id         = compute_measurement_config_id();
    r.build_profile                 = RUNNER_BUILD_PROFILE;
    r.run_sequence                  = last_run_sequence;
    r.valid_flags                   = flags;
    r.poison_crc                    = poison_crc;
    r.output_crc                    = output_crc;
    r.result_region_crc             = result_region_crc;

    /* Close of window -> record complete. Serialisation and UART TX follow
     * this point and are deliberately outside every timing field. */
    r.t_result_processing = read_timestamp() - r.ts_close;

    last_measurement       = r;
    last_valid_flags       = flags;
    last_poison_crc        = poison_crc;
    last_output_crc        = output_crc;
    last_result_region_crc = result_region_crc;
    /* Written together, at the very end, so "a run completed" and "which run"
     * can never disagree. GET_RESULT reads exactly this pair. */
    last_completed_sequence = last_run_sequence;
    last_run_completed      = 1;
    runner_state           = ST_RESULT_READY;

    /* Only now is transmitting legal again. */
    uart_tx_forbidden = 0U;
    __DSB();

    /* --- Serialise and transmit, strictly outside the window. ------------ */
    build_run_complete_payload(resp);
    send_frame(CMD_RUN_COMPLETE, ERR_NONE, sequence, resp, sizeof(resp));
}

/* CHANGE 1: RUN_COMPLETE = 8-word ABI header followed by the measurement
 * fields. GET_MEASUREMENT deliberately keeps the bare, header-less field
 * array; only the unsolicited RUN_COMPLETE frame carries the ABI header. */
static void build_run_complete_payload(uint8_t *out)
{
    wcur_t c = {out, 0};
    uint32_t crc;

    put32(&c, RUN_COMPLETE_ABI_MAGIC);
    put32(&c, RUN_COMPLETE_ABI_VERSION);
    put32(&c, RUN_COMPLETE_TOTAL_WORDS);
    put32(&c, RUN_COMPLETE_HEADER_WORDS);
    put32(&c, last_run_sequence);
    put32(&c, last_valid_flags);
    put32(&c, (uint32_t)run_rc);
    put32(&c, 0U); /* payload_crc32 placeholder, filled in below */

    build_measurement_payload(out + (RUN_COMPLETE_HEADER_WORDS * 4U));

    /* CRC RANGE -- READ THIS BEFORE IMPLEMENTING THE HOST SIDE.
     * Covers run_sequence (word 4) through the FINAL measurement field
     * (word total_payload_words-1) INCLUSIVE, EXCLUDING the payload_crc32
     * word (word 7) itself. The range is therefore NOT contiguous: it is two
     * chunks, words 4..6 and words 8..total-1, fed to one running CRC.
     * Little-endian; matches Python zlib.crc32 over those two slices
     * concatenated. */
    crc = crc32_update(CRC32_INIT, out + (4U * 4U), 3U * 4U);
    crc = crc32_update(crc, out + (RUN_COMPLETE_HEADER_WORDS * 4U),
                       MEASUREMENT_PAYLOAD_SIZE);
    crc = crc32_final(crc);

    wr_u32(out + (RUN_COMPLETE_CRC_WORD_INDEX * 4U), crc);
}

static void build_measurement_payload(uint8_t *out)
{
    const measurement_record_t *r = &last_measurement;
    wcur_t c = {out, 0};

    put32(&c, r->valid);
    put32(&c, r->run_rc);
    put32(&c, r->ts_open);
    put32(&c, r->ts_close);
    put32(&c, r->ts_elapsed);
    put32(&c, r->ts_source_valid);
    put32(&c, r->isr_entry_ts);
    put32(&c, r->isr_exit_ts);
    put32(&c, r->isr_ts_valid);
    put32(&c, r->measurement_complete);
    put32(&c, r->npu_qread_at_irq);
    put32(&c, r->npu_irq_status_at_irq);
    put32(&c, r->rx_bytes_during_measurement);
    put32(&c, r->rx_overrun_during_measurement);
    put32(&c, r->unexpected_irq_count);
    put32(&c, r->unexpected_irq_mask0);
    put32(&c, r->unexpected_irq_mask1);
    put32(&c, r->unexpected_irq_mask2);
    put32(&c, r->uart_bytes_during_measurement);
    put32(&c, r->suppressed_printf_calls);
    put32(&c, r->suppressed_write_calls);
    put32(&c, r->systick_ctrl);
    put32(&c, r->systick_enabled);
    put32(&c, r->npu_irq_priority);
    put32(&c, r->uart_rx_irq_priority);
    put32(&c, r->uart_rx_irq_was_enabled);
    put32(&c, r->uart_rx_irq_masked_during);
    put32(&c, r->primask_at_open);
    put32(&c, r->basepri_at_open);
    put32(&c, r->cpu_clock_hz);
    put32(&c, r->npu_clock_hz);
    put32(&c, r->npu_status_at_close);
    put32(&c, r->npu_qread_at_close);
    put32(&c, r->npu_vector_before);
    put32(&c, r->npu_vector_installed);
    put32(&c, r->npu_vector_at_close);
    put32(&c, r->npu_vector_hijack_survived);
    put32(&c, r->demcr);
    put32(&c, r->dwt_ctrl);
    put32(&c, r->pmu_enabled);
    put32(&c, r->measurement_config_id);
    put32(&c, r->build_profile);
    /* appended by CHANGE 2/3 -- see MEASUREMENT_FIELD_COUNT */
    put32(&c, r->run_sequence);
    put32(&c, r->valid_flags);
    put32(&c, r->poison_crc);
    put32(&c, r->output_crc);
    put32(&c, r->result_region_crc);
    /* appended for the PMU candidate, milestone 1 */
    put32(&c, r->record_schema_version);
    put32(&c, r->instrumentation_mode_requested);
    put32(&c, r->instrumentation_mode_applied);
    put32(&c, r->event_set_id);
    put32(&c, r->configuration_sequence);
    put32(&c, r->npu_pmu_present);
    put32(&c, r->pmu_probe_performed);
    put32(&c, r->hw_event_counter_count);
    put32(&c, r->expected_hw_event_counter_count);
    put32(&c, r->abi_event_slot_count);
    put32(&c, r->effective_event_slot_count);
    put32(&c, r->requested_event_count);
    put32(&c, r->applied_event_count);
    put32(&c, r->event_valid_mask);
    put32(&c, r->event_overflow_mask);
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        put32(&c, r->event_codes[i]);
    }
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        put32(&c, r->event_values[i]);
    }
    put32(&c, r->npu_pmu_window_cycles_lo);
    put32(&c, r->npu_pmu_window_cycles_hi);
    put32(&c, r->npu_pmu_cycle_valid);
    put32(&c, r->npu_pmu_cycle_overflow);
    put32(&c, r->npu_pmu_cycle_read_retry_count);
    put32(&c, r->pmu_sample_valid);
    put32(&c, r->completion_wait_mode);
    put32(&c, r->t_pmu_enable);
    put32(&c, r->t_inference_call_enter);
    put32(&c, r->t_inference_call_return);
    put32(&c, r->t_pmu_disable);
    put32(&c, r->t_pmu_programming);
    put32(&c, r->cpu_call_window_cycles);
    put32(&c, r->cpu_return_to_pmu_disable_cycles);
    put32(&c, r->t_result_processing);
    put32(&c, r->pmu_mmio_read_count_total);
    put32(&c, r->pmu_mmio_write_count_total);
    put32(&c, r->pmu_mmio_read_count_delta);
    put32(&c, r->pmu_mmio_write_count_delta);
    put32(&c, r->pmcr_at_disable);
    put32(&c, r->cycle_counter_armed);
    put32(&c, r->cycle_global_enable_verified);
    put32(&c, r->cycle_read_stable);
    put32(&c, r->cycle_progress_observed);
    put32(&c, r->read_seam_fired);
    put32(&c, r->vendor_rc);
    put32(&c, r->seam_npu_status);
    put32(&c, r->seam_npu_qread);
    put32(&c, r->ofm_mismatch_count);
    put32(&c, r->ofm_max_abs_diff);
    put32(&c, r->ofm_first_mismatch);
}

void handle_get_measurement(uint32_t sequence)
{
    uint8_t resp[MEASUREMENT_PAYLOAD_SIZE];

    if (!last_measurement.valid) {
        send_nack(CMD_GET_MEASUREMENT, sequence, ERR_NO_MEASUREMENT);
        return;
    }

    build_measurement_payload(resp);
    send_ack(CMD_GET_MEASUREMENT, sequence, resp, sizeof(resp));
}

/* ------------------------------------------------------------------------ */
/* CMD_SET_INSTRUMENTATION_MODE                                              */
/*                                                                           */
/* Payload, 44 bytes:                                                        */
/*   u32 mode              OFF | END_ONLY (PER_LAYER -> ERR_UNSUPPORTED)     */
/*   u32 event_set_id                                                        */
/*   u32 event_count                                                         */
/*   u32 event_codes[8]                                                      */
/*                                                                           */
/* The reply reports REQUESTED and APPLIED separately. A request that cannot  */
/* be honoured is refused, never silently clamped -- a host that asked for    */
/* more counters than exist must find out, not receive a quiet subset.        */
void handle_set_instrumentation_mode(uint32_t sequence,
                                            const uint8_t *payload,
                                            uint32_t payload_length)
{
    uint8_t  resp[16];
    uint32_t mode, set_id, count, effective;
    uint32_t codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    unsigned i;

    if (payload_length != (12U + (RUNNER_MAX_NPU_EVENT_COUNTERS * 4U))) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_LENGTH);
        return;
    }

    mode   = rd_u32(&payload[0]);
    set_id = rd_u32(&payload[4]);
    count  = rd_u32(&payload[8]);
    for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        codes[i] = rd_u32(&payload[12U + (i * 4U)]);
    }

    if (mode != INSTRUMENTATION_OFF && mode != INSTRUMENTATION_END_ONLY
        && mode != INSTRUMENTATION_EVENTS) {
        /* PER_LAYER and anything else: well-formed but not implemented here.
         * Distinct from BAD_COMMAND so the host can tell them apart. */
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_UNSUPPORTED);
        return;
    }

    effective = pmu_effective_event_slots();
    if (count > RUNNER_MAX_NPU_EVENT_COUNTERS || count > effective) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_RANGE);
        return;
    }
    /* Milestone 1 is cycle-only. Event programming lands in milestone 2, and
     * accepting a count now would report event slots that were never armed. */
    if (count != 0U && mode != INSTRUMENTATION_EVENTS) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_UNSUPPORTED);
        return;
    }

    instr_cfg.mode         = mode;
    instr_cfg.event_set_id = set_id;
    instr_cfg.event_count  = count;
    for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        /* Unused slots are zeroed, but a zero is never how a slot is judged --
         * event_valid_mask is the authority, because code 0 can be real. */
        instr_cfg.event_codes[i] = (i < count) ? codes[i] : 0U;
    }
    instr_cfg.configuration_sequence++;

    wr_u32(&resp[0], mode);                            /* requested */
    wr_u32(&resp[4], instr_cfg.mode);                  /* applied   */
    wr_u32(&resp[8], instr_cfg.event_count);
    wr_u32(&resp[12], instr_cfg.configuration_sequence);
    send_ack(CMD_SET_INSTRUMENTATION_MODE, sequence, resp, sizeof(resp));
}

void handle_reset_runner(uint32_t sequence)
{
    /* RESET_RUNNER returns instrumentation to a DEFINED default, so a run can
     * never inherit a configuration the host forgot it set. Chosen for
     * reproducibility: the host must state the mode before every measurement
     * rather than rely on what a previous session left behind.
     *   mode = OFF, event_count = 0, PMU disabled, overflow cleared.
     * The teardown runs only if the counters were ever armed -- in a session
     * that never left OFF there is nothing to tear down and touching the
     * block would be an access with no purpose. */
    /* UNCONDITIONAL, and deliberately so. Conditioning the teardown on a
     * software flag cannot recover the cases that matter: an enable that
     * landed before a fault skipped the flag update, a debugger or a previous
     * image leaving the block armed, or a warm handoff. Reset must leave the
     * PMU in a known state no matter what the history was.
     *
     * This costs PMU MMIO accesses, which is fine: the OFF contract is scoped
     * to the RUN PATH, not to RESET_RUNNER. */
    {
        uint32_t pmcr = pmu_reg_read(NPU_REG_PMCR);

        if (pmcr & NPU_PMCR_CNT_EN_MSK) {
            pmu_reg_write(NPU_REG_PMCR, pmcr & ~NPU_PMCR_CNT_EN_MSK);
        }
        __DSB();
        (void)pmu_reg_read(NPU_REG_PMCR);      /* readback: the clear landed */
        pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);  /* overflow evidence */
        pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU); /* counter enables  */
        pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);   /* overflow IRQs    */
        __DSB();
    }

    instr_cfg.mode        = INSTRUMENTATION_OFF;
    instr_cfg.event_count = 0U;
    for (unsigned i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        instr_cfg.event_codes[i] = 0U;
    }
    pmu_ever_enabled = 0U;

    runner_reset_context();
    send_ack(CMD_RESET_RUNNER, sequence, (void *)0, 0);
}
