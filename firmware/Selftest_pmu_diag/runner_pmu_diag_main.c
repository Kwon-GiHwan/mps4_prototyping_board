/*
 * runner_measure_main.c -- RUNNER_V1_MEASURE, a measurement-clean variant of
 * the frozen RUNNER_V1_FUNCTIONAL firmware (Selftest/runner_v1_main.c).
 *
 * Copied from runner_v1_main.c and modified. The wire protocol, the frame
 * parser, the CRC range and the state machine are UNCHANGED except for the
 * additions documented under "PROTOCOL DELTA" below.
 *
 * ===========================================================================
 * PROTOCOL DELTA vs RUNNER_V1_FUNCTIONAL (all additive except RUN)
 * ===========================================================================
 *  + CMD_GET_CAPABILITIES 0x03 -- static capability descriptor, read from
 *                                 LINKER SYMBOLS and RAW REGISTERS.
 *  + CMD_GET_MEASUREMENT  0x04 -- telemetry of the most recent measured run.
 *  + CMD_RUN_COMPLETE     0x31 -- UNSOLICITED frame emitted after the measured
 *                                 window closes, echoing the RUN sequence.
 *
 *  ! CMD_RUN 0x30 semantics CHANGED, and this is unavoidable. Contract 2
 *    requires the RUN_ACCEPTED frame to be fully transmitted BEFORE the
 *    measured window opens. In RUNNER_V1_FUNCTIONAL the RUN ACK was sent
 *    AFTER the inference completed. Now:
 *        host -> RUN
 *        fw   -> ACK(RUN)            "RUN_ACCEPTED", payload = 4B accept code
 *        fw   -> ...measured window, total radio silence...
 *        fw   -> RUN_COMPLETE        payload = rc + full telemetry
 *    The host must resynchronise on the magic, which the v1 host already had
 *    to do. PING/GET_STATE/GET_RESULT/LOAD_* are byte-for-byte unchanged.
 *
 * PING is deliberately NOT extended: it stays liveness + protocol version +
 * counters. Capabilities live in GET_CAPABILITIES, telemetry in
 * GET_MEASUREMENT.
 *
 * ===========================================================================
 * PROTOCOL DELTA v2 -- STALE-OUTPUT HAZARD (breaking, deliberate)
 * ===========================================================================
 * THE HAZARD: .sec_noinit is NOLOAD, so it SURVIVES RESET. If a RUN silently
 * fails, the previous run's output tensor is still in DDR and a CRC over it
 * still returns 0x27084C4C -- indistinguishable from success. No amount of
 * host-side cross-checking can fix this. The PRODUCER must destroy the data.
 *
 *  ! RUN_COMPLETE 0x31 payload now carries an 8-word ABI HEADER before the
 *    measurement fields (magic "RME1", abi_version, total_payload_words,
 *    header_words, run_sequence, valid_flags, run_rc, payload_crc32).
 *    Hosts must read header_words/total_payload_words and skip unknown
 *    trailing words rather than assuming a fixed length.
 *    GET_MEASUREMENT 0x04 is NOT given the header: it keeps the bare field
 *    array. Only the unsolicited frame is self-describing.
 *
 *  ! Every CMD_RUN now POISONS the NPU output region with a sequence-derived
 *    pattern before opening the window, so a stale buffer can never
 *    coincidentally match. See "CHANGE 2" below.
 *
 *  ! GET_RESULT 0x40 now REFUSES with ERR_RESULT_NOT_VALID (0x000B) unless
 *    the most recent RUN completed, run_rc == 0, the required valid_flags are
 *    set, and output_crc != poison_crc. It NEVER returns stale bytes.
 *
 * ===========================================================================
 * PROTOCOL DELTA v3 -- MEASURE-ONLY, BREAKING vs RUNNER_V1_FUNCTIONAL
 * ===========================================================================
 *  ! GET_RESULT 0x40 REQUEST FORM: the 12-byte form is now the ONLY accepted
 *    form in this MEASURE image.
 *
 *        12 bytes: base(u32), len(u32), expected_run_sequence(u32)
 *
 *    The 8-byte form (base, len) is REJECTED with ERR_LENGTH (0x0003).
 *    RUNNER_V1_FUNCTIONAL keeps both forms; this image does not. A separate
 *    MEASURE artifact has no host compatibility to preserve, and the loose
 *    form weakened the only guarantee that matters here: that the bytes
 *    returned belong to the RUN the host is asking about. An 8-byte request
 *    could not carry that question, so it was answered without it.
 *
 *  ! CMD_TEST_SKIP_NEXT_NPU 0x7E -- exists ONLY in a build compiled with
 *    -DRUNNER_TEST_ONLY_HOOKS. Absent from every normal artifact, and the
 *    build gate FAILS a normal build in which its handler is reachable.
 *    See "TEST-ONLY HOOKS" below.
 *
 *  ! RUN_VALID_EXPECTED_CRC_MATCH was RENAMED to
 *    RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH. Bit value 0x10 is unchanged and
 *    it is still reported but NOT required. See the flag's own comment for why
 *    the old name was actively misleading.
 *
 *  ! The measurement field array grew from 42 to 47 words (five appended at
 *    the END; existing order untouched). NOTE: the change request described
 *    this array as "40 fields"; it was already 42 before this work.
 *
 * ===========================================================================
 * MEASUREMENT BOUNDARY (Contract 2)
 * ===========================================================================
 *   send RUN_ACCEPTED
 *   -> software TX queue empty          (put_raw is synchronous; no SW queue)
 *   -> USART TXBF == 0                  (TX holding register drained)
 *   -> bounded delay >= 1 character time (SEE "TX DRAIN" CAVEAT BELOW)
 *   -> snapshot + disable UART RX IRQs at the NVIC
 *   -> measurement_active = true
 *   -> DSB / ISB
 *   -> CPU timestamp (DWT CYCCNT)
 *   -> NPU submit  == apU85Conv_TEST()
 *   -> CPU timestamp
 *   -> measurement_active = false
 *   -> restore NVIC RX IRQ state EXACTLY as it was
 *   -> sample pending RX byte + hardware overrun
 *   -> serialise and transmit RUN_COMPLETE
 *
 * TX DRAIN -- READ THIS BEFORE TRUSTING THE NUMBERS:
 *   TXBF means "transmit buffer FULL", i.e. TXBF == 0 only means the holding
 *   register can accept another byte. It is NOT a drain / transmit-empty
 *   indication and is deliberately NOT used as one here.
 *
 *   "TRANSMIT-EMPTY IS NOT OBSERVABLE ON THIS PERIPHERAL, SO A FIXED DRAIN
 *    DELAY BASED ON BLOCKING-WRITE COMPLETION AND ASSUMED HARDWARE RESIDUAL
 *    DEPTH IS APPLIED -- A CONSERVATIVE TIME BOUND, NOT A DETECTED CONDITION."
 *
 *   The basis, in order:
 *     1. every byte of the final frame is written with the blocking writer
 *        (put_raw spins on TXBF before each store) and that loop runs to
 *        completion before we proceed;
 *     2. all further UART writes are then FORBIDDEN (uart_tx_forbidden), so
 *        nothing can re-fill the holding register behind our back;
 *     3. there is no software TX queue in this firmware -- put_raw is
 *        synchronous -- so there is nothing else to confirm empty;
 *     4. a fixed delay sized to the maximum bytes that can still be resident
 *        in hardware is burned.
 *
 *   SIZING: Drivers/cmsdk_apb_uart_driver/cmsdk_apb_uart.h defines the whole
 *   STATE register as exactly four bits -- RXOR[3], TXOR[2], RXBF[1],
 *   TXBF[0]. There is no FIFO level field, no FIFO depth field and no
 *   transmit-idle bit, and no CMSDK UART TRM is present in this image.
 *   We therefore CANNOT establish that the transmit path is at most a
 *   holding + shift pair. Per the stricter contract we assume up to FOUR
 *   resident characters: 4 x 86.8 us = 347.2 us, rounded to 348 us.
 *   (200 us was the earlier value and covered only ~2 characters; it was
 *   raised precisely because the 2-stage assumption is unproven.)
 *
 *   The load-bearing runtime evidence remains uart_bytes_during_measurement
 *   == 0, counted at the single function that writes the UART DATA register.
 *
 *   DSB/ISB are ordering barriers for the CPU's own memory accesses. They say
 *   NOTHING about whether a UART has finished shifting bits out. The status
 *   poll and the barriers are separate, independent steps and are written as
 *   such below.
 *
 * IRQ MASKING CHOICE -- why NVIC-level and not BASEPRI:
 *   u85.c's wait_for_irq() busy-polls a flag that is set by the NPU0 ISR.
 *   Raising BASEPRI high enough to mask the UART would also mask NPU0 and the
 *   firmware would deadlock. We therefore disable ONLY the UART RX interrupt
 *   lines at the NVIC and leave NPU0 enabled. PRIMASK and BASEPRI are recorded
 *   as observed, never modified.
 *
 * ===========================================================================
 * KNOWN, DELIBERATE, UNRESOLVED IN THIS DELIVERABLE
 * ===========================================================================
 *  1. ISR-ENTRY TIMESTAMPING DOES NOT WORK IN THIS BUILD, BY CONSTRUCTION.
 *     Drivers/u85_driver/u85.c line 329 executes
 *         NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
 *     as the FIRST statement of test_u85(), and apU85Conv_TEST() calls
 *     test_u85(). So any handler we install before the window is overwritten
 *     at the top of the very call we are measuring, before the NPU is even
 *     reset -- let alone submitted to. There is no seam between "driver
 *     initialised" and "work submitted" reachable from outside u85.c.
 *     We still install the chain (measure_npu_irq) and then READ THE VECTOR
 *     BACK after the window, reporting npu_vector_hijack_survived so the
 *     operator gets EVIDENCE instead of a plausible-looking wrong number.
 *     Expected value on this build: 0. isr_entry_ts_valid will be 0 and
 *     isr_entry_ts must be treated as meaningless.
 *     Fixing this requires a measure-private u85.c, deliberately deferred.
 *
 *  2. PMU counters are NOT programmed. RUNNER_MEASURE_ENABLE_PMU is 0.
 *     Every PMU field is reported as a raw ID register read or zero.
 *
 *  3. wait_for_irq() busy-polls (BUSY_SLEEP is #defined in u85.c) rather than
 *     using __WFI(). The CPU is therefore spinning at full rate for the whole
 *     window. Recorded as a known property; deliberately NOT changed.
 */

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "ARMCM85.h"
#include "Driver_USART.h"
#include "serial.h"
#include "u85.h"

/* ------------------------------------------------------------------------ */
/* Build profile                                                             */
/* ------------------------------------------------------------------------ */

#define BUILD_PROFILE_FUNCTIONAL      0U
#define BUILD_PROFILE_MEASURE_WRAPPED 1U
#define BUILD_PROFILE_MEASURE_CLEAN   2U

#if defined(MEASUREMENT_BUILD)
#define RUNNER_BUILD_PROFILE BUILD_PROFILE_MEASURE_CLEAN
#elif defined(MEASUREMENT_WRAPPED_BUILD)
#define RUNNER_BUILD_PROFILE BUILD_PROFILE_MEASURE_WRAPPED
#else
#error "runner_measure_main.c requires -DMEASUREMENT_BUILD or -DMEASUREMENT_WRAPPED_BUILD"
#endif

#ifndef RUNNER_FIRMWARE_BUILD_ID
#error "RUNNER_FIRMWARE_BUILD_ID must be supplied by the Makefile"
#endif

/* PMU stays OFF for this deliverable. Contract 3 explicitly defers it. */
#define RUNNER_MEASURE_ENABLE_PMU 0

#define RUNNER_CAPABILITY_SCHEMA_VERSION 1U
#define RUNNER_EXPECTED_TEST19_CRC32     0x27084C4CU

/* One character at 115200 8N1 is 10 bits = 86.8 us; we use 87 us. The
 * resident-character assumption is 4 because the transmit path depth is NOT
 * establishable from the header or any TRM in this image. See TX DRAIN above. */
#define RUNNER_UART_CHAR_US      87U
#define RUNNER_TX_RESIDUAL_CHARS 4U
#define RUNNER_TX_DRAIN_US       (RUNNER_UART_CHAR_US * RUNNER_TX_RESIDUAL_CHARS)

/* Fallback spin count used only when DWT CYCCNT is unavailable. Deliberately
 * far too large rather than too small: over-waiting costs nothing here. */
#define RUNNER_TX_DRAIN_FALLBACK_LOOPS 200000U

/* ------------------------------------------------------------------------ */
/* UART0 -- direct CMSDK APB register access, exactly as runner_v1_main.c    */
/* ------------------------------------------------------------------------ */

#define UART0_REGS ((volatile uint32_t *)0x59303000U)

#define REG_DATA    0U /* 0x000 */
#define REG_STATE   1U /* 0x004 */
#define REG_CTRL    2U /* 0x008 */
#define REG_BAUDDIV 4U /* 0x010 */

#define STATE_TXBF (1U << 0) /* TX buffer full */
#define STATE_RXBF (1U << 1) /* RX buffer full */
#define STATE_TXOR (1U << 2) /* TX overrun, write-1-to-clear */
#define STATE_RXOR (1U << 3) /* RX overrun, write-1-to-clear */

extern ARM_DRIVER_USART Driver_USART0;

/* ------------------------------------------------------------------------ */
/* Debug / trace unit -- raw addresses, matching this file's register style. */
/* Using literals avoids depending on whether the CMSIS version in use calls  */
/* the block CoreDebug or DCB.                                               */
/* ------------------------------------------------------------------------ */

#define DEMCR_ADDR     0xE000EDFCU
#define DEMCR_TRCENA   (1U << 24)
#define DWT_CTRL_ADDR  0xE0001000U
#define DWT_CYCCNT_ADDR 0xE0001004U
#define DWT_LAR_ADDR   0xE0001FB0U
#define DWT_LAR_KEY    0xC5ACCE55U
#define DWT_CTRL_CYCCNTENA (1U << 0)

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))

/* ------------------------------------------------------------------------ */
/* NPU -- same base and offsets the frozen driver uses                       */
/* Drivers/u85_driver/u85.c:  #define U85_BASE_ADDRESS 0x50004000            */
/* Drivers/u85_driver/interface.h: ID 0x00, STATUS 0x04, CMD 0x08,           */
/*                                 QREAD 0x18, CONFIG 0x28                   */
/* ------------------------------------------------------------------------ */

#include "npu_pmu_regs.h"

/* ------------------------------------------------------------------------ */
/* Instrumentation mode constants, INHERITED from the PMU candidate where    */
/* they select a runtime OFF/END_ONLY branch. In THIS image they are inert:  */
/* the A/B/C identity is COMPILE-TIME (see the PMU_DIAG block below) and     */
/* CMD_SET_INSTRUMENTATION_MODE answers UNSUPPORTED. Kept because shared     */
/* code (capabilities, reset) still names them.                              */
#define INSTRUMENTATION_OFF       0U
#define INSTRUMENTATION_END_ONLY  1U
#define RUNNER_MAX_NPU_EVENT_COUNTERS NPU_PMU_EVENT_COUNTERS_MAX

/* ======================================================================== */
/* RUNNER_V1_PMU_DIAG -- DIAGNOSTIC IMAGE, NEVER A PERFORMANCE CANDIDATE.   */
/*                                                                          */
/* Derived from Selftest_pmu/runner_pmu_main.c (which is NOT modified).     */
/* Purpose: decide why PMCCNTR reads 0 while armed and globally enabled,    */
/* via three build-time cases that differ ONLY in PMCCNTR_CFG handling:     */
/*   case A: no PMCCNTR_CFG write of any kind (reset/default state)         */
/*   case B: CFG = generated START=CYCLE / STOP=NO_EVENT value              */
/*   case C: CFG = explicit generated NO_EVENT/NO_EVENT (numeric zero)      */
/* The case is COMPILE-TIME so each deployment has an unambiguous identity  */
/* and case A provably contains no CFG-write call at all (the preprocessing */
/* gate in check_diag_case.py counts the write calls in this TU).           */
/*                                                                          */
/* In this image CMD_RUN, CMD_GET_RESULT, CMD_GET_MEASUREMENT and           */
/* CMD_SET_INSTRUMENTATION_MODE all answer ERR_UNSUPPORTED: the ONLY        */
/* diagnostic path is CMD_RUN_PMU_DIAG / GET_PMU_DIAG_RESULT, so nothing    */
/* this image emits can be mistaken for production data. The semantic-drift */
/* guard survives inside the diag record itself: poison -> OUTPUT_CHANGED   */
/* plus the exact 256-byte test-19 output-window CRC. The whole-region CRC   */
/* is corroboration only because residual scratch is boot-variant.           */
/* ======================================================================== */
#if (defined(PMU_DIAG_CASE_A) + defined(PMU_DIAG_CASE_B) + defined(PMU_DIAG_CASE_C)) != 1
#error "PMU_DIAG: exactly one of PMU_DIAG_CASE_{A,B,C} must be defined"
#endif

#if defined(PMU_DIAG_CASE_A)
#define PMU_DIAG_CASE_ID 1U
#elif defined(PMU_DIAG_CASE_B)
#define PMU_DIAG_CASE_ID 2U
#else
#define PMU_DIAG_CASE_ID 3U
#endif

/* Firmware negative controls. Each is a deliberate SINGLE defect injected
 * into a case-B build so host-side classification can be proven to separate
 * the four failure classes (CFG write omitted / START=NO_EVENT / arm omitted
 * / forced overflow). They only combine with case B, and each lands in its
 * own build directory. */
#if defined(PMU_DIAG_NC_SKIP_CFG_WRITE) || defined(PMU_DIAG_NC_START_NO_EVENT) \
    || defined(PMU_DIAG_NC_SKIP_ARM) || defined(PMU_DIAG_NC_FORCE_OVERFLOW)
#ifndef PMU_DIAG_CASE_B
#error "PMU_DIAG negative controls require PMU_DIAG_CASE_B"
#endif
#endif
/* Fail closed at the SOURCE level too: the Makefile selects one control,
 * but a hand-driven compile must not be able to stack defects and produce
 * an artifact no expectation table describes. */
#if (defined(PMU_DIAG_NC_SKIP_CFG_WRITE) + defined(PMU_DIAG_NC_START_NO_EVENT) \
     + defined(PMU_DIAG_NC_SKIP_ARM) + defined(PMU_DIAG_NC_FORCE_OVERFLOW)) > 1
#error "PMU_DIAG: at most one negative control may be defined"
#endif
#if defined(PMU_DIAG_NC_SKIP_CFG_WRITE)
#define PMU_DIAG_NC_ID 1U
#elif defined(PMU_DIAG_NC_START_NO_EVENT)
#define PMU_DIAG_NC_ID 2U
#elif defined(PMU_DIAG_NC_SKIP_ARM)
#define PMU_DIAG_NC_ID 3U
#elif defined(PMU_DIAG_NC_FORCE_OVERFLOW)
#define PMU_DIAG_NC_ID 4U
#else
#define PMU_DIAG_NC_ID 0U
#endif

/* Case C / NC_START_NO_EVENT configuration: START and STOP both set to the
 * generated NO_EVENT number. Numerically zero, but COMPOSED from the
 * extracted macros -- no literal, the same rule as NPU_PMU_CYCLE_CFG_VALUE. */
#define NPU_PMU_DIAG_CFG_NO_EVENT \
    (((NPU_PMU_EVENT_NO_EVENT << NPU_PMU_PMCCNTR_CFG_START_SHIFT) & NPU_PMU_PMCCNTR_CFG_START_MASK) | \
     ((NPU_PMU_EVENT_NO_EVENT << NPU_PMU_PMCCNTR_CFG_STOP_SHIFT)  & NPU_PMU_PMCCNTR_CFG_STOP_MASK))

#define U85_BASE_ADDRESS 0x50004000U
#define NPU_OFF_ID       0x00U
#define NPU_OFF_STATUS   0x04U
#define NPU_OFF_CMD      0x08U
#define NPU_OFF_QREAD    0x18U
#define NPU_OFF_CONFIG   0x28U

static uint32_t npu_read(uint32_t offset)
{
    return REG32(U85_BASE_ADDRESS + offset);
}

static void npu_write(uint32_t offset, uint32_t value)
{
    REG32(U85_BASE_ADDRESS + offset) = value;
}

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
static volatile uint32_t pmu_mmio_read_count;
static volatile uint32_t pmu_mmio_write_count;

static uint32_t pmu_reg_read(uint32_t offset)
{
    pmu_mmio_read_count++;
    return REG32(U85_BASE_ADDRESS + offset);
}

static void pmu_reg_write(uint32_t offset, uint32_t value)
{
    pmu_mmio_write_count++;
    REG32(U85_BASE_ADDRESS + offset) = value;
}

/* --- three DISTINCT capacities, never conflated ------------------------- */
/*   ABI capacity       : RUNNER_MAX_NPU_EVENT_COUNTERS, fixed at 8 slots.    */
/*   hardware capacity  : PMCR.num_event_cnt, the device answering for itself.*/
/*   effective capacity : min(the two). Only this bounds a configuration.     */
/* The vendor header's constant 8 is a BUILD-TIME claim and is recorded only  */
/* as expected_hw_event_counter_count, for a provenance warning if the device */
/* disagrees. A mismatch does not kill the run; it bounds what can be asked   */
/* for and is reported. */
static uint32_t pmu_probe_performed;
static uint32_t pmu_present;
static uint32_t pmu_hw_event_counters;

/* Set the first time the counters are armed. RESET_RUNNER uses it to
 * decide whether there is any PMU state to tear down: in a session that
 * never left OFF there is nothing to clean, and touching the block would
 * be an access with no purpose. */
static uint32_t pmu_ever_enabled;

/* Discovery only. Outside the RUN path by contract -- see the accessor note. */
static void pmu_probe(void)
{
    uint32_t pmcr = pmu_reg_read(NPU_REG_PMCR);

    pmu_hw_event_counters =
        (pmcr & NPU_PMCR_NUM_EVENT_CNT_MSK) >> NPU_PMCR_NUM_EVENT_CNT_POS;
    /* All-ones or all-zeros PMCR means the block did not answer. */
    pmu_present = (pmcr != 0xFFFFFFFFU && pmcr != 0U) ? 1U : 0U;
    pmu_probe_performed = 1U;
}

static uint32_t pmu_effective_event_slots(void)
{
    if (!pmu_probe_performed) {
        pmu_probe();
    }
    return (pmu_hw_event_counters < RUNNER_MAX_NPU_EVENT_COUNTERS)
               ? pmu_hw_event_counters
               : RUNNER_MAX_NPU_EVENT_COUNTERS;
}

static void npu_pmu_disable(void)
{
    pmu_reg_write(NPU_REG_PMCR,
                  pmu_reg_read(NPU_REG_PMCR) & ~NPU_PMCR_CNT_EN_MSK);
}

static void npu_pmu_enable(void)
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
static void npu_pmu_reset_counters(void)
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
 * reserved bits. The earlier 1<<RUNNER_MAX_NPU_EVENT_COUNTERS read a reserved
 * bit that is always zero, so a wrapped counter reported "no overflow" -- a
 * false negative that would have promoted a torn sample to a measurement. */
static uint32_t npu_pmu_overflow_status(void)
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

static uint64_t npu_pmu_read_cycles(uint32_t *stable_out, uint32_t *retries_out)
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

/* ------------------------------------------------------------------------ */
/* Instrumentation configuration. handle_run() takes a COPY of this before it  */
/* does anything else, so changing the mode after a run cannot rewrite that    */
/* run's record.                                                              */
typedef struct {
    uint32_t mode;
    uint32_t event_set_id;
    uint32_t event_count;
    uint32_t event_codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    uint32_t configuration_sequence;
} instrumentation_config_t;

static instrumentation_config_t instr_cfg;


/* The frozen u85 driver waits for completion by polling, so the CPU is active
 * throughout NPU execution. Results from a future WFI variant describe a
 * different machine state and must not be pooled with these. The constant is
 * COMPLETION_WAIT_MODE_BUSY_POLL, declared with the capability enums below --
 * one name for one concept. */

/* ------------------------------------------------------------------------ */
/* Protocol constants                                                        */
/* ------------------------------------------------------------------------ */

#define RUNNER_MAGIC   0x3152554EU /* "NUR1" little-endian: 4E 55 52 31 */
#define RUNNER_VERSION 1

#define RUNNER_HEADER_SIZE 16U
#define RUNNER_MAX_PAYLOAD 4096U

#define RESP_ACK_FLAG 0x80U
#define RESP_NACK_CMD 0xFFU

/* requests */
#define CMD_PING              0x01U
#define CMD_GET_STATE         0x02U
#define CMD_GET_CAPABILITIES  0x03U
#define CMD_GET_MEASUREMENT   0x04U
#define CMD_LOAD_MODEL_BEGIN  0x10U
#define CMD_LOAD_MODEL_CHUNK  0x11U
#define CMD_LOAD_MODEL_END    0x12U
#define CMD_LOAD_INPUT        0x20U
#define CMD_RUN               0x30U
#define CMD_GET_RESULT        0x40U
#define CMD_RESET_RUNNER      0x50U
#define CMD_SET_INSTRUMENTATION_MODE 0x05U

/* unsolicited */
#define CMD_RUN_COMPLETE 0x31U

/* PMU_DIAG commands. 0x60/0x61 sit far above every production id (max 0x50)
 * and below the reserved 0x7E/0x7F top; their ACKs 0xE0/0xE1 collide with
 * nothing. CMD_PMU_DIAG_COMPLETE 0x62 is unsolicited, the diag analogue of
 * CMD_RUN_COMPLETE 0x31. */
#define CMD_RUN_PMU_DIAG        0x60U
#define CMD_GET_PMU_DIAG_RESULT 0x61U
#define CMD_PMU_DIAG_COMPLETE   0x62U



/* ------------------------------------------------------------------------ */
/* TEST-ONLY COMMAND. Compiled in ONLY under -DRUNNER_TEST_ONLY_HOOKS.       */
/*                                                                           */
/* WHY IT EXISTS: INJECT_SKIP_NPU_EXECUTION is compile-time and skips EVERY  */
/* run, so an artifact built with it can never produce the sequence that      */
/* actually matters -- a SUCCESSFUL run followed by a FAILED run in the SAME  */
/* boot session. That pair is the only direct proof that the second run       */
/* cannot hand back the first run's CRC out of NOLOAD .sec_noinit.            */
/* CMD_TEST_SKIP_NEXT_NPU arms a ONE-SHOT skip, so a single image can do:     */
/*   RUN (real, succeeds) -> TEST_SKIP_NEXT_NPU -> RUN (skipped, fails)       */
/*                                                                           */
/* ID CHOICE 0x7E, and why it is not arbitrary:                              */
/*   - request ids must be <= 0x7F: an ACK is (request | RESP_ACK_FLAG 0x80). */
/*   - 0x7F is excluded: 0x7F | 0x80 == 0xFF == RESP_NACK_CMD, so its ACK     */
/*     would be indistinguishable from a NACK frame.                          */
/*   - 0x7E is therefore the highest usable id, deliberately far above every  */
/*     production id (max 0x50) and adjacent to the reserved top of the       */
/*     space. Its ACK is 0xFE, which collides with nothing.                   */
/*   - it is free: command_bit() maps no other command to it.                 */
/*                                                                           */
/* CONTAINMENT: check_measure_symbols.py FAILS any normal build in which      */
/* handle_test_skip_next_npu exists or is reachable from dispatch(), exactly  */
/* as it already does for the INJECT_SKIP_NPU marker. It cannot ship.         */
/* ------------------------------------------------------------------------ */
#ifdef RUNNER_TEST_ONLY_HOOKS
#define CMD_TEST_SKIP_NEXT_NPU 0x7EU
#endif

/* error codes, carried in the NACK header's flags field */
#define ERR_NONE           0x0000U
#define ERR_BAD_VERSION    0x0001U
#define ERR_BAD_COMMAND    0x0002U
#define ERR_LENGTH         0x0003U
#define ERR_BAD_CRC        0x0004U
#define ERR_STATE          0x0005U
#define ERR_RANGE          0x0006U
#define ERR_CHUNK_MISMATCH 0x0007U
#define ERR_MODEL_CRC      0x0008U
#define ERR_PAYLOAD_FORMAT 0x0009U
#define ERR_NO_MEASUREMENT 0x000AU
/* GET_RESULT refused because the latched result cannot be proven fresh.
 * DISTINCT from every other error precisely so the host can tell "the run did
 * not produce a trustworthy result" apart from "bad request". Returning this
 * is ALWAYS preferred to returning bytes that might be a previous run's. */
#define ERR_RESULT_NOT_VALID 0x000BU

/* A well-formed request for something this build does not implement --
 * distinct from BAD_COMMAND (unknown id) and from RANGE (out of bounds).
 * PER_LAYER instrumentation returns this. */
#define ERR_UNSUPPORTED      0x000CU

/* ------------------------------------------------------------------------ */
/* CONTRACT 1: capabilities come from LINKER SYMBOLS, never C constants.     */
/*                                                                           */
/* Re-declaring these as C constants is exactly how firmware drifts away     */
/* from its own map. Every address below is defined in LinkScripts/lnk.ld.S  */
/* and resolved at link time. There is no second source of truth.            */
/* ------------------------------------------------------------------------ */

extern const uint8_t __runner_staging_start__[];
extern const uint8_t __runner_staging_end__[];
extern const uint8_t __runner_result_start__[];
extern const uint8_t __runner_result_end__[];
/* NOTE: there is deliberately NO tight __runner_output_* pair. Bounding just
 * .bss.sec_output_data can only be expressed INSIDE the .sec_noinit output
 * section body, i.e. by editing the shared lnk.ld.S, and the C object
 * (test3_out_data_0 in Tests/u85_test/test3/test3_include.h) is declared
 * `static` so it cannot be referenced externally either. The shared script is
 * left untouched by choice; see MEASURE_PROVENANCE.txt. */

/* Retained from runner_v1_main.c so GET_RESULT keeps validating against the
 * exact same bounds it validated against in the frozen build. */
extern char __sec_noinit_start[];
extern char __sec_noinit_end[];

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

static uint32_t sym_u32(const uint8_t *p)
{
    return (uint32_t)(uintptr_t)p;
}

/* ------------------------------------------------------------------------ */
/* Diagnostic counters (unchanged set from v1)                               */
/* ------------------------------------------------------------------------ */

static uint32_t rx_bytes;
static uint32_t tx_bytes;
static uint32_t rx_overrun_count;
static uint32_t bad_magic_count;
static uint32_t bad_version_count;
static uint32_t bad_crc_count;
static uint32_t length_error_count;
static uint32_t sequence_error_count;
static uint32_t parser_resync_count;

/* ------------------------------------------------------------------------ */
/* Measurement state                                                         */
/*                                                                           */
/* measurement_active is the single gate the log wrappers consult. It is      */
/* volatile because the wrappers may be reached from an ISR.                 */
/* ------------------------------------------------------------------------ */

volatile uint32_t measurement_active;

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
static volatile uint32_t uart_tx_forbidden;

typedef struct {
    uint32_t valid;
    uint32_t run_rc;
    uint32_t ts_open;
    uint32_t ts_close;
    uint32_t ts_elapsed;
    uint32_t ts_source_valid;
    uint32_t isr_entry_ts;
    uint32_t isr_exit_ts;
    uint32_t isr_ts_valid;
    uint32_t measurement_complete;
    uint32_t npu_qread_at_irq;
    uint32_t npu_irq_status_at_irq;
    uint32_t rx_bytes_during_measurement;
    uint32_t rx_overrun_during_measurement;
    uint32_t unexpected_irq_count;
    uint32_t unexpected_irq_mask0;
    uint32_t unexpected_irq_mask1;
    uint32_t unexpected_irq_mask2;
    uint32_t uart_bytes_during_measurement;
    uint32_t suppressed_printf_calls;
    uint32_t suppressed_write_calls;
    uint32_t systick_ctrl;
    uint32_t systick_enabled;
    uint32_t npu_irq_priority;
    uint32_t uart_rx_irq_priority;
    uint32_t uart_rx_irq_was_enabled;
    uint32_t uart_rx_irq_masked_during;
    uint32_t primask_at_open;
    uint32_t basepri_at_open;
    uint32_t cpu_clock_hz;
    uint32_t npu_clock_hz;
    uint32_t npu_status_at_close;
    uint32_t npu_qread_at_close;
    uint32_t npu_vector_before;
    uint32_t npu_vector_installed;
    uint32_t npu_vector_at_close;
    uint32_t npu_vector_hijack_survived;
    uint32_t demcr;
    uint32_t dwt_ctrl;
    uint32_t pmu_enabled;
    uint32_t measurement_config_id;
    uint32_t build_profile;
    /* --- appended by CHANGE 2/3. Existing field ORDER above is untouched. -- */
    uint32_t run_sequence;      /* sequence of the CMD_RUN this record is for */
    uint32_t valid_flags;       /* RUN_VALID_* bitmask, same value as hdr w5  */
    uint32_t poison_crc;        /* CRC of the output region AFTER poisoning   */
    uint32_t output_crc;        /* CRC of the output region AFTER the run     */
    uint32_t result_region_crc; /* CRC of the WHOLE .sec_noinit after the run */
    /* --- appended for the PMU candidate, milestone 1. Order above untouched. */
    uint32_t record_schema_version;
    /* requested vs applied: a request that was clamped or refused must be
     * visible, not silently normalised away. */
    uint32_t instrumentation_mode_requested;
    uint32_t instrumentation_mode_applied;
    uint32_t event_set_id;
    uint32_t configuration_sequence;
    uint32_t npu_pmu_present;
    uint32_t pmu_probe_performed;
    uint32_t hw_event_counter_count;        /* PMCR.num_event_cnt            */
    uint32_t expected_hw_event_counter_count; /* vendor header claim (8)     */
    uint32_t abi_event_slot_count;          /* fixed 8: ABI capacity         */
    uint32_t effective_event_slot_count;    /* min(abi, hardware)            */
    uint32_t requested_event_count;
    uint32_t applied_event_count;
    /* event code 0 may be a real event OR a disabled encoding, so a slot is
     * NEVER judged by its value. The mask is the only authority. */
    uint32_t event_valid_mask;
    uint32_t event_overflow_mask;
    uint32_t event_codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    uint32_t event_values[RUNNER_MAX_NPU_EVENT_COUNTERS];
    /* 48-bit cycle counter, split for the wire. NAMED "window", not
     * "execution": the snapshot is taken after run_fixed_inference() returns,
     * because u85.c reinstalls its own NPU vector and the completion ISR is
     * therefore unreachable. The value can include driver entry, busy-poll,
     * completion handling and the return path. Promote the name only after a
     * PMCCNTR_CFG hardware start/stop boundary has been cross-checked. */
    uint32_t npu_pmu_window_cycles_lo;
    uint32_t npu_pmu_window_cycles_hi;
    uint32_t npu_pmu_cycle_valid;
    uint32_t npu_pmu_cycle_overflow;
    uint32_t npu_pmu_cycle_read_retry_count;
    uint32_t pmu_sample_valid;              /* the PMU path ran at all       */
    uint32_t completion_wait_mode;          /* BUSY_POLL on this build       */
    /* four CPU timestamps, so what the PMU window contains stays analysable */
    uint32_t t_pmu_enable;
    uint32_t t_inference_call_enter;
    uint32_t t_inference_call_return;
    uint32_t t_pmu_disable;
    uint32_t t_pmu_programming;
    uint32_t cpu_call_window_cycles;
    uint32_t cpu_return_to_pmu_disable_cycles;
    uint32_t t_result_processing;
    /* Runtime proof of the OFF contract, scoped to the RUN path. */
    /* Totals are session-cumulative and may be non-zero purely because
     * GET_CAPABILITIES probed, or because an earlier run used END_ONLY.
     * THE DELTA IS THE AUTHORITY for the OFF contract; the totals are
     * context. */
    uint32_t pmu_mmio_read_count_total;
    uint32_t pmu_mmio_write_count_total;
    uint32_t pmu_mmio_read_count_delta;
    uint32_t pmu_mmio_write_count_delta;
    uint32_t pmcr_at_disable;   /* readback proving the disable landed */
    /* Independent evidence, each answering a different question. */
    uint32_t cycle_counter_armed;          /* PMCNTENSET readback       */
    uint32_t cycle_global_enable_verified; /* PMCR readback after enable*/
    uint32_t cycle_read_stable;            /* HI/LO/HI agreed           */
    uint32_t cycle_progress_observed;      /* the counter actually moved*/
} measurement_record_t;

/* NOTE FOR THE HOST: this is 47, not the 42 it was, and not the "40" the
 * change request assumed. The pre-existing record already had 42 fields (the
 * struct and build_measurement_payload() agree at 42); five are appended here.
 * The ABI header's total_payload_words is the authority -- never hardcode. */
/* 47 + 55 appended for milestone 1. The ABI header's total_payload_words
 * remains the authority; hosts skip trailing words they do not know. */
#define MEASUREMENT_FIELD_COUNT 102U
#define MEASUREMENT_PAYLOAD_SIZE (MEASUREMENT_FIELD_COUNT * 4U)

static measurement_record_t last_measurement;

/* ------------------------------------------------------------------------ */
/* CHANGE 1: RUN_COMPLETE payload ABI                                        */
/*                                                                           */
/* word 0  magic 0x524D4531 "RME1"                                           */
/* word 1  abi_version                                                       */
/* word 2  total_payload_words                                               */
/* word 3  header_words (8)                                                  */
/* word 4  run_sequence                                                      */
/* word 5  valid_flags                                                       */
/* word 6  run_rc                                                            */
/* word 7  payload_crc32                                                     */
/* word 8+ the measurement fields, order unchanged                           */
/*                                                                           */
/* Forward compatibility: the host reads header_words and                    */
/* total_payload_words and skips any trailing words it does not know, so      */
/* appending fields later stays safe. */
#define RUN_COMPLETE_ABI_MAGIC      0x524D4531U
#define RUN_COMPLETE_ABI_VERSION    1U
#define RUN_COMPLETE_HEADER_WORDS   8U
#define RUN_COMPLETE_CRC_WORD_INDEX 7U
#define RUN_COMPLETE_TOTAL_WORDS \
    (RUN_COMPLETE_HEADER_WORDS + MEASUREMENT_FIELD_COUNT)
#define RUN_COMPLETE_PAYLOAD_SIZE (RUN_COMPLETE_TOTAL_WORDS * 4U)

/* ------------------------------------------------------------------------ */
/* PMU_DIAG result ABI -- separate from the measurement ABI on purpose.      */
/* Same 8-word header SHAPE and the same two-slice CRC rule as               */
/* RUN_COMPLETE, so the host reuses one integrity code path, but its own     */
/* magic and its own schema version: the production schema gains no fields.  */
/* ------------------------------------------------------------------------ */
#define PMU_DIAG_ABI_MAGIC      0x31474450U /* "PDG1" little-endian */
/* v6 held the NPU clock/power Q interfaces before touching the PMU and used a
 * diag-private u85_diag.c to defer the driver's terminal release. It bundled
 * THREE interventions, so it never isolated the minimum seam.
 *
 * v7 splits them. All three seam images carry the SAME case-B cycle config,
 * so PMCCNTR_CFG is held constant and power_seam_id is the only variable:
 *
 *   S1  reference vendor driver (TEST_CPM=1), pre-hold only, no re-hold.
 *       Its terminal CMD=0xC lands INSIDE test_u85(), before our post
 *       snapshot -- this measures what that release costs us.
 *   S2  reference vendor driver, and the FIRST action after the inference
 *       returns is a CMD=0 re-hold. No driver copy anywhere.
 *   S3  the v6 configuration (diag-private driver, terminal release after
 *       the post snapshot) re-measured under v7 instrumentation, as the
 *       known-good control.
 *
 * v1-v6 payloads are invalid evidence for this experiment and the host
 * parser refuses them. */
/*
 * v8 is a different QUESTION, not a bigger v7. v7 asked where the counter
 * state was lost; v8 asks whether one sample is publishable. The host has a
 * separate parser and a separate classifier for it, and each refuses the
 * other's schema outright -- so the version word below is the ABI boundary,
 * and it is the only thing the two records share besides the magic. */
#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif
#define PMU_DIAG_HEADER_WORDS   8U
#define PMU_DIAG_CRC_WORD_INDEX 7U

/* Sequence identity is evidence, not an implementation comment. */
#define PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM 4U
#define PMU_DIAG_POWER_GUARD_CYCLES 65536U
#define PMU_DIAG_RESET_GUARD_CYCLES 65536U
#define PMU_DIAG_STABILITY_SAMPLES 8U
#define PMU_DIAG_STABILITY_GAP_CYCLES 1024U
/* Same bound as the entry hold: that value is the one already proven to let
 * a power request settle, so the re-hold does not introduce a second,
 * unvalidated timing constant. */
#define PMU_DIAG_REHOLD_GUARD_CYCLES 65536U

/* Exactly one seam must be selected. The Makefile forces case B for every
 * seam build, so the CFG variable is held constant across S1/S2/S3. */
#if (defined(PMU_DIAG_SEAM_S1) + defined(PMU_DIAG_SEAM_S2) \
     + defined(PMU_DIAG_SEAM_S3)) != 1
#error "PMU_DIAG: exactly one of PMU_DIAG_SEAM_{S1,S2,S3} must be defined"
#endif
#if defined(PMU_DIAG_SEAM_S1)
#define PMU_DIAG_POWER_SEAM_ID 1U
#elif defined(PMU_DIAG_SEAM_S2)
#define PMU_DIAG_POWER_SEAM_ID 2U
#else
#define PMU_DIAG_POWER_SEAM_ID 3U
#endif
/* S1 and S2 link the reference vendor driver byte-for-byte, so nothing may
 * skip its terminal release; only S3 owns that write. */
#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)
#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)
#error "PMU_DIAG: S1/S2 must link the reference vendor u85.c"
#endif
#endif

/* ------------------------------------------------------------------------ */
/* SCHEMA v8 (PMU_QUAL) COMPILE-TIME BOUNDARY                                */
/*                                                                           */
/* Everything schema v8 adds lives behind PMU_QUAL_SCHEMA_V8. Without that   */
/* macro this file compiles to EXACTLY the v7 diagnostic image it was: the   */
/* v7 A/B/C, NC1-4 and S1/S2/S3 matrices are rebuilt as a required gate and  */
/* must reproduce their recorded hashes, so the isolation below is proven,   */
/* not asserted.                                                             */
/*                                                                           */
/* The refusals are not defensive noise. Each one names a configuration that */
/* would still COMPILE and would still produce a plausible-looking record,   */
/* while measuring something other than what the record claims.              */
/* ------------------------------------------------------------------------ */
#if defined(PMU_QUAL_SCHEMA_V8)

#if (defined(PMU_QUAL_MODE_Q0) + defined(PMU_QUAL_MODE_Q1)) != 1
#error "PMU_QUAL: exactly one of PMU_QUAL_MODE_{Q0,Q1} must be defined"
#endif

/* Q0 is the hook-disabled baseline, Q1 the H-PRINTF candidate. The mode is
 * compile-time only: an image cannot be talked into the other role at run
 * time, and the build id carried beside it is a second, independent witness. */
#if defined(PMU_QUAL_MODE_Q0)
#define PMU_QUAL_MODE_ID 0U
#else
#define PMU_QUAL_MODE_ID 1U
#endif

/* The candidate hooks the REFERENCE driver's own printf callsite. A private
 * driver copy would be a different callsite with different provenance, which
 * is the whole reason H-COPY was not the chosen candidate. */
#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)
#error "PMU_QUAL: schema v8 must link the reference vendor u85.c"
#endif

/* Case A only. v8's validity contract is that NO PMCCNTR_CFG write exists;
 * under case B or C the classifier's cfg terms would be judging a programmed
 * configuration and the no-CFG evidence would be vacuous. */
#if !defined(PMU_DIAG_CASE_A) && !defined(PMU_QUAL_CFG_EXPERIMENT)
#error "PMU_QUAL: schema v8 writes no PMCCNTR_CFG; build PMU_DIAG_CASE_A"
#endif

/* S1 is the only v7 seam whose SHAPE v8 needs: reference driver, no re-hold,
 * and no runner-issued terminal release -- the vendor keeps its own CMD=0xC,
 * which is precisely the instruction the hook must run before. S2 would
 * cancel that release; S3 would defer it behind a private driver. */
#if !defined(PMU_DIAG_SEAM_S1)
#error "PMU_QUAL: schema v8 requires PMU_DIAG_SEAM_S1"
#endif
#if defined(PMU_DIAG_SEAM_S2) || defined(PMU_DIAG_SEAM_S3)
#error "PMU_QUAL: schema v8 refuses the S2 re-hold and the S3 private-driver seam"
#endif

/* The negative controls exist to break the v7 CFG/arm/overflow classes. A v8
 * image that carried one would report a deliberately broken PMU program while
 * still claiming a qualification build id. */
#if defined(PMU_DIAG_NC_SKIP_CFG_WRITE) || defined(PMU_DIAG_NC_START_NO_EVENT) \
    || defined(PMU_DIAG_NC_SKIP_ARM) || defined(PMU_DIAG_NC_FORCE_OVERFLOW)
#error "PMU_QUAL: schema v8 admits no negative-control macro"
#endif

/* The hook is reached FROM the printf wrapper. Under the wrapped profile that
 * wrapper forwards to real stdio, so the measured window would carry UART
 * traffic and the hook would be re-entering the logging path it must not
 * touch. Qualification images are clean-profile only. */
#if RUNNER_BUILD_PROFILE != BUILD_PROFILE_MEASURE_CLEAN
#error "PMU_QUAL: schema v8 qualification images are clean-profile only"
#endif

/* v8 runs no seam experiment. The three retained seam slots are pinned to
 * this shape so a v7 seam image can never be decoded as a v8 record. */
#define PMU_QUAL_POWER_SEAM_ID 4U

#endif /* PMU_QUAL_SCHEMA_V8 */

/* Exact golden window bounds. Link-time symbols from
 * LinkScripts/lnk.pmu_diag.overlay.ld -- no address literal in C, and the
 * map gate re-checks the values fail-closed. */
extern const uint8_t __pmu_diag_golden_window_base__[];
extern const uint8_t __pmu_diag_golden_window_len__[];

/* One raw register snapshot. The capture ORDER differs pre vs post (the
 * contract fixes it; see the two capture functions), but the FIELD order on
 * the wire is always this one. */
typedef struct {
    uint32_t pmcr;
    uint32_t pmcntenset;
    uint32_t pmccntr_cfg;
    uint32_t cycle_lo;
    uint32_t cycle_hi;
    uint32_t cycle_read_stable;
    uint32_t cycle_read_retries;
    uint32_t pmovsset;
} pmu_diag_snapshot_t;

#define PMU_DIAG_SNAPSHOT_WORDS 8U

typedef struct {
    uint32_t schema_version;
    uint32_t build_id;        /* RUNNER_FIRMWARE_BUILD_ID (PDGA/PDGB/PDGC)  */
    uint32_t diag_case;       /* 1=A 2=B 3=C, compile-time                  */
    uint32_t nc_control_id;   /* 0=normal, 1..4 = negative control          */
    uint32_t run_sequence;
    uint32_t cfg_write_performed;
    uint32_t cfg_write_value;
    uint32_t cfg_readback_after_write;
    uint32_t run_rc;
    uint32_t valid_flags;     /* RUN_VALID_* -- same bits as production     */
    uint32_t poison_crc;
    uint32_t output_crc;
    uint32_t result_region_crc;
    uint32_t ts_source_valid;
    uint32_t t_call_enter;
    uint32_t t_call_return;
    uint32_t t_pmu_disable;
    uint32_t pmcr_readback_after_disable;
    uint32_t pmu_mmio_read_count_delta;
    uint32_t pmu_mmio_write_count_delta;
    /* --- schema 6 additions, BEFORE the snapshots ----------------------- */
    uint32_t start_sequence_id;
    uint32_t power_guard_cycles;
    uint32_t npu_cmd_before_power_request;
    uint32_t npu_cmd_after_power_request;
    uint32_t npu_status_after_power_request;
    uint32_t reset_guard_cycles;
    uint32_t pmcr_after_reset_guard;
    uint32_t pmcr_after_program;
    uint32_t armed_after_program;
    uint32_t program_stability_reads;
    uint32_t program_stable;
#if defined(PMU_QUAL_SCHEMA_V8)
    /* SAME 40-word prefix SLOT as v7's npu_cmd_after_power_release, renamed
     * because in v8 it carries a different fact: v8's runner issues no power
     * release at all, so this is the read taken after test_u85() returns,
     * proving the VENDOR reached its own terminal CMD=0xC. */
    uint32_t npu_cmd_after_return;
#else
    uint32_t npu_cmd_after_power_release;
#endif
    /* --- schema 7 additions, still BEFORE the snapshots ----------------- */
    uint32_t power_seam_id;            /* 1=S1 2=S2 3=S3, compile-time      */
    uint32_t power_rehold_performed;   /* S2 only                           */
    uint32_t rehold_guard_cycles;
    /* Read AFTER the seam action, never before it: pre-restore telemetry
     * would itself change the race S2 exists to measure. */
    uint32_t npu_cmd_after_seam;
    uint32_t npu_status_after_seam;
    uint32_t golden_window_base;       /* from the overlay symbols          */
    uint32_t golden_window_len;
    uint32_t golden_window_crc;        /* CRC32 over exactly that window    */
#if defined(PMU_QUAL_SCHEMA_V8)
    /* --- the 13 appended hook words, in EXACT wire order ---------------
     * This order is the ABI. The host dataclass, the parser and the schema-v8
     * unit suite are all written against this numbered list, so a field added
     * or reordered here is a silent re-interpretation of every later word.
     * Append only, and only with the host changed in the same step. */
    uint32_t qualification_mode;          /*  1  0=Q0 baseline, 1=Q1        */
    uint32_t hook_armed;                  /*  2  arm was SET before submit  */
    uint32_t hook_arm_consumed;           /*  3  target detection took it   */
    uint32_t hook_detected_count;         /*  4  must be exactly 1          */
    uint32_t hook_fired_count;            /*  5  Q0: 0. Q1: exactly 1       */
    uint32_t hook_snapshot_valid;         /*  6  latched last, inside hook  */
    uint32_t hook_callsite_lr_observed;   /*  7  normalized, Thumb bit clear*/
    uint32_t hook_entry_timestamp;        /*  8                             */
    uint32_t hook_exit_timestamp;         /*  9                             */
    uint32_t npu_cmd_at_hook;             /* 10  release not issued yet: 0  */
    uint32_t pmcr_disable_readback_at_hook;/* 11 the one disable's ack      */
    uint32_t hook_pmu_mmio_read_count;    /* 12  SUBSET of the window total */
    uint32_t hook_pmu_mmio_write_count;   /* 13  SUBSET of the window total */
#endif
    pmu_diag_snapshot_t pre;          /* after CFG/arm/enable, before call  */
#if defined(PMU_QUAL_SCHEMA_V8)
    /* The authoritative v8 pair is (pre, internal_pre_release) and nothing
     * else. internal_post_disable corroborates the single in-hook disable;
     * after_return is EXPECTED to read wiped, because the vendor release
     * clears the bank, and is excluded from every validity term. */
    pmu_diag_snapshot_t internal_pre_release;
    pmu_diag_snapshot_t internal_post_disable;
    pmu_diag_snapshot_t after_return;
#else
    pmu_diag_snapshot_t post;         /* after call, BEFORE disable         */
    pmu_diag_snapshot_t post_disable; /* after disable + DSB + readback     */
#endif
} pmu_diag_record_t;

#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif
#define PMU_DIAG_TOTAL_WORDS (PMU_DIAG_HEADER_WORDS + PMU_DIAG_FIELD_COUNT)
#define PMU_DIAG_PAYLOAD_SIZE (PMU_DIAG_TOTAL_WORDS * 4U)

#if defined(PMU_QUAL_SCHEMA_V8)
/* The wire shape, asserted at compile time rather than trusted. The host
 * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch
 * here would otherwise surface as an unparseable board run. */
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_QUAL: a snapshot must be exactly 8 words on the wire");
_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,
               "PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,
               "PMU_QUAL: total is 8 header + 85 body = 93 words");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,
               "PMU_QUAL: payload is 93 * 4 = 372 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,
               "PMU_QUAL: the v8 record must declare schema version 8");
#endif

static pmu_diag_record_t last_pmu_diag;
/* The GET_PMU_DIAG_RESULT gate, latched only at the very end of a diag run
 * and cleared at the top of the next one -- the same freshness discipline
 * as last_run_completed. */
static uint32_t pmu_diag_completed;

/* ------------------------------------------------------------------------ */
/* CHANGE 3: run validity flags                                              */
/* ------------------------------------------------------------------------ */

enum {
    RUN_VALID_RUN_COMPLETED  = 1u << 0,
    RUN_VALID_RUN_RC_OK      = 1u << 1,
    RUN_VALID_OUTPUT_CHANGED = 1u << 2, /* output_crc != poison_crc */
    RUN_VALID_COARSE_WINDOW  = 1u << 3,

    /* RENAMED from RUN_VALID_EXPECTED_CRC_MATCH. Bit value 0x10 UNCHANGED --
     * this is a naming fix on the wire documentation, not an ABI change.
     *
     * ################# THIS FLAG IS NOT THE GOLDEN JUDGEMENT #################
     *
     * It is set when a CRC32 over the WHOLE of .sec_noinit
     * ([__sec_noinit_start, __sec_noinit_end) == 0x90020000 + 0xF90, i.e. 3984
     * bytes covering NPU scratch AND every test's output block) equals
     * RUNNER_EXPECTED_TEST19_CRC32.
     *
     * The golden acceptance test is a DIFFERENT computation over a DIFFERENT
     * range: the HOST issues GET_RESULT(base=0x90020cc0, len=0x100) and
     * compares the returned CRC against 0x27084C4C. 256 bytes, not 3984.
     *
     * Same constant, different evidence. The old name invited reading a set
     * bit as "the golden test passed", which it does not mean, and a clear bit
     * as "the golden test failed", which it also does not mean. A run can
     * legitimately clear this flag (different model, different scratch
     * contents) while the 256-byte golden window is byte-perfect.
     *
     * MUST NEVER be used as the 0x27084C4C judgement. That judgement belongs
     * to the host, from the payload of GET_RESULT(0x90020cc0, 0x100), and to
     * nothing else. This flag is reported as corroborating evidence only.
     * ####################################################################### */
    RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH = 1u << 4,
};

/* What GET_RESULT demands before it will serve result bytes: 0x0F.
 *
 * RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH (0x10) is deliberately NOT in this
 * mask, and the rename does not change that. It says "the whole .sec_noinit
 * hashed to the one value we happen to know", which is a statement about THIS
 * TEST, not about whether the data is fresh. Requiring it would make
 * GET_RESULT refuse every legitimate run of any other model. The firmware
 * reports both the flag and the computed CRC; the host does the final judging
 * from GET_RESULT(0x90020cc0, 0x100). */
#define RUN_VALID_REQUIRED_MASK                                \
    (RUN_VALID_RUN_COMPLETED | RUN_VALID_RUN_RC_OK |           \
     RUN_VALID_OUTPUT_CHANGED | RUN_VALID_COARSE_WINDOW)

/* ------------------------------------------------------------------------ */
/* UART primitives                                                           */
/* ------------------------------------------------------------------------ */

/* put_raw is the ONLY function in this firmware that writes UART DATA.
 * If measurement_active is set when it is reached, that is a contract
 * violation and it is COUNTED rather than silently performed-or-dropped:
 * we still refuse the write, so a violation can never corrupt the window. */
static void put_raw(uint8_t byte)
{
    if (measurement_active || uart_tx_forbidden) {
        /* Counted as low as possible: this is the ONLY function that writes
         * the CMSDK UART DATA register, so this counter catches every route
         * including indirect Driver_USART0.Send calls that the static
         * denylist check cannot see. */
        uart_bytes_during_measurement++;
        return;
    }
    while (UART0_REGS[REG_STATE] & STATE_TXBF) {
    }
    UART0_REGS[REG_DATA] = byte;
    tx_bytes++;
}

static void put_block(const uint8_t *data, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++) {
        put_raw(data[i]);
    }
}

static void poll_overrun(void)
{
    if (UART0_REGS[REG_STATE] & STATE_RXOR) {
        rx_overrun_count++;
        UART0_REGS[REG_STATE] = STATE_RXOR; /* write-1-to-clear */
    }
}

static uint8_t get_raw(void)
{
    for (;;) {
        poll_overrun();
        if (UART0_REGS[REG_STATE] & STATE_RXBF) {
            uint8_t byte = (uint8_t)UART0_REGS[REG_DATA];
            rx_bytes++;
            return byte;
        }
    }
}

/* ------------------------------------------------------------------------ */
/* CRC-32 (reflected, poly 0xEDB88320) -- matches Python zlib.crc32()        */
/* ------------------------------------------------------------------------ */

static const uint32_t crc32_nibble_table[16] = {
    0x00000000U, 0x1DB71064U, 0x3B6E20C8U, 0x26D930ACU,
    0x76DC4190U, 0x6B6B51F4U, 0x4DB26158U, 0x5005713CU,
    0xEDB88320U, 0xF00F9344U, 0xD6D6A3E8U, 0xCB61B38CU,
    0x9B64C2B0U, 0x86D3D2D4U, 0xA00AE278U, 0xBDBDF21CU};

#define CRC32_INIT 0xFFFFFFFFU

static uint32_t crc32_update(uint32_t crc, const void *data, uint32_t len)
{
    const uint8_t *p = (const uint8_t *)data;

    for (uint32_t i = 0; i < len; i++) {
        crc ^= p[i];
        crc = (crc >> 4) ^ crc32_nibble_table[crc & 0x0FU];
        crc = (crc >> 4) ^ crc32_nibble_table[crc & 0x0FU];
    }
    return crc;
}

static uint32_t crc32_final(uint32_t crc)
{
    return crc ^ 0xFFFFFFFFU;
}

static uint32_t crc32_buffer(const void *data, uint32_t len)
{
    return crc32_final(crc32_update(CRC32_INIT, data, len));
}

/* ------------------------------------------------------------------------ */
/* Little-endian accessors                                                   */
/* ------------------------------------------------------------------------ */

static uint32_t rd_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static void wr_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static void wr_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

/* Sequential little-endian writer, so a 38-field payload cannot acquire an
 * off-by-one offset bug during editing. */
typedef struct {
    uint8_t *base;
    uint32_t used;
} wcur_t;

static void put32(wcur_t *c, uint32_t v)
{
    wr_u32(c->base + c->used, v);
    c->used += 4U;
}

/* ========================================================================= */
/* STATE MACHINE                                                             */
/* ========================================================================= */

typedef enum {
    ST_BOOT          = 0,
    ST_IDLE          = 1,
    ST_MODEL_LOADING = 2,
    ST_MODEL_READY   = 3,
    ST_INPUT_READY   = 4,
    ST_RUNNING       = 5,
    ST_RESULT_READY  = 6,
    ST_COUNT         = 7
} runner_state_t;

static runner_state_t runner_state;

typedef enum {
    CB_PING = 0,
    CB_GET_STATE,
    CB_GET_CAPABILITIES,
    CB_GET_MEASUREMENT,
    CB_LOAD_MODEL_BEGIN,
    CB_LOAD_MODEL_CHUNK,
    CB_LOAD_MODEL_END,
    CB_LOAD_INPUT,
    CB_RUN,
    CB_GET_RESULT,
    CB_RESET_RUNNER,
    CB_SET_INSTRUMENTATION_MODE,
    CB_RUN_PMU_DIAG,
    CB_GET_PMU_DIAG_RESULT,
#ifdef RUNNER_TEST_ONLY_HOOKS
    /* Appended AFTER every production bit on purpose: every existing CB_ value
     * therefore keeps its number, so state_accepts[] rows mean the same thing
     * in a test-hooks build as in a normal one. */
    CB_TEST_SKIP_NEXT_NPU,
#endif
    CB_INVALID
} cmd_bit_t;

static cmd_bit_t command_bit(uint8_t command)
{
    switch (command) {
    case CMD_PING:             return CB_PING;
    case CMD_GET_STATE:        return CB_GET_STATE;
    case CMD_GET_CAPABILITIES: return CB_GET_CAPABILITIES;
    case CMD_GET_MEASUREMENT:  return CB_GET_MEASUREMENT;
    case CMD_LOAD_MODEL_BEGIN: return CB_LOAD_MODEL_BEGIN;
    case CMD_LOAD_MODEL_CHUNK: return CB_LOAD_MODEL_CHUNK;
    case CMD_LOAD_MODEL_END:   return CB_LOAD_MODEL_END;
    case CMD_LOAD_INPUT:       return CB_LOAD_INPUT;
    case CMD_RUN:              return CB_RUN;
    case CMD_GET_RESULT:       return CB_GET_RESULT;
    case CMD_RESET_RUNNER:     return CB_RESET_RUNNER;
    case CMD_SET_INSTRUMENTATION_MODE: return CB_SET_INSTRUMENTATION_MODE;
    case CMD_RUN_PMU_DIAG:        return CB_RUN_PMU_DIAG;
    case CMD_GET_PMU_DIAG_RESULT: return CB_GET_PMU_DIAG_RESULT;
#ifdef RUNNER_TEST_ONLY_HOOKS
    case CMD_TEST_SKIP_NEXT_NPU: return CB_TEST_SKIP_NEXT_NPU;
#endif
    default:                   return CB_INVALID;
    }
}

#define M(bit) (1U << (bit))

/* GET_CAPABILITIES and GET_MEASUREMENT are pure reads of static/latched data
 * and are accepted wherever PING is, including BOOT-adjacent states. They are
 * added to every row that already accepted PING; no existing bit is removed,
 * so the frozen acceptance behaviour is preserved exactly. */
#define M_ALWAYS (M(CB_PING) | M(CB_GET_STATE) | M(CB_GET_CAPABILITIES) | \
                  M(CB_GET_MEASUREMENT) | M(CB_GET_PMU_DIAG_RESULT))

/* TEST-ONLY. Accepted in exactly the two states that also accept CB_RUN, and
 * nowhere else: arming a one-shot skip is only meaningful when a RUN can
 * actually follow. In a normal build this expands to nothing, so every row is
 * bit-for-bit what it was. */
#ifdef RUNNER_TEST_ONLY_HOOKS
#define M_TEST_HOOKS M(CB_TEST_SKIP_NEXT_NPU)
#else
#define M_TEST_HOOKS 0U
#endif

static const uint32_t state_accepts[ST_COUNT] = {
    /* ST_BOOT          */ 0U,
    /* ST_IDLE          */ M_ALWAYS | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER) |
                           M(CB_SET_INSTRUMENTATION_MODE),
    /* ST_MODEL_LOADING */ M_ALWAYS | M(CB_LOAD_MODEL_CHUNK) |
                           M(CB_LOAD_MODEL_END) | M(CB_RESET_RUNNER),
    /* ST_MODEL_READY   */ M_ALWAYS | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER),
    /* ST_INPUT_READY   */ M_ALWAYS | M(CB_RUN) | M(CB_RUN_PMU_DIAG) |
                           M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER) |
                           M_TEST_HOOKS,
    /* ST_RUNNING       */ 0U,
    /* ST_RESULT_READY  */ M_ALWAYS | M(CB_GET_RESULT) | M(CB_RUN) |
                           M(CB_RUN_PMU_DIAG) |
                           M(CB_LOAD_INPUT) | M(CB_RESET_RUNNER) |
                           M_TEST_HOOKS};

static int command_allowed(runner_state_t state, uint8_t command)
{
    cmd_bit_t bit = command_bit(command);

    if (bit == CB_INVALID || state >= ST_COUNT) {
        return 0;
    }
    return (state_accepts[state] & M(bit)) != 0U;
}

/* ------------------------------------------------------------------------ */
/* Runner context                                                            */
/* ------------------------------------------------------------------------ */

static uint32_t model_total_length;
static uint32_t model_expected_crc;
static uint32_t model_bytes_staged;
static uint32_t model_computed_crc;
static uint32_t input_length;
static int32_t  run_rc;

/* RENAMED from run_valid. "valid" was vague; the predicate this actually holds
 * is "the most recent handle_run() reached its end". GET_RESULT names it
 * directly now. */
static int      last_run_completed;

/* CHANGE 2/3 latched run state. last_valid_flags is the single gate
 * GET_RESULT consults; it is cleared at the TOP of every handle_run so a run
 * that dies partway can never leave a stale "valid" behind. */
static uint32_t run_sequence_counter;
static uint32_t last_run_sequence;

/* The sequence of the last run that COMPLETED, which is NOT the same thing as
 * last_run_sequence. last_run_sequence is stamped at the TOP of handle_run, so
 * mid-run it already names a run with no result. last_completed_sequence is
 * written only at the very end, next to last_run_completed, so the pair can
 * never disagree. GET_RESULT compares the host's expected_run_sequence against
 * THIS one. Zero is never a valid value: run_sequence_counter is
 * pre-incremented, so real sequences start at 1. */
static uint32_t last_completed_sequence;

static uint32_t last_valid_flags;
static uint32_t last_poison_crc;
static uint32_t last_output_crc;
static uint32_t last_result_region_crc;

#ifdef RUNNER_TEST_ONLY_HOOKS
/* TEST-ONLY one-shot. Armed by CMD_TEST_SKIP_NEXT_NPU, consumed and cleared by
 * the very next run_fixed_inference(). volatile because run_fixed_inference()
 * reads it inside the measured window, where the compiler has no reason to
 * expect the value to have changed since the handler wrote it. */
static volatile uint32_t test_skip_next_npu_armed;
#endif

static int      last_chunk_valid;
static uint32_t last_chunk_sequence;
static uint32_t last_chunk_offset;
static uint32_t last_chunk_length;
static uint32_t last_chunk_data_crc;

static void runner_reset_context(void)
{
    model_total_length  = 0;
    model_expected_crc  = 0;
    model_bytes_staged  = 0;
    model_computed_crc  = 0;
    input_length        = 0;
    run_rc              = 0;
    last_run_completed  = 0;
    /* run_sequence_counter is deliberately NOT reset: it must keep increasing
     * across a soft reset so a poison pattern can never repeat. */
    last_run_sequence       = 0;
    last_completed_sequence = 0;
    last_valid_flags        = 0;
    last_poison_crc         = 0;
    last_output_crc         = 0;
    last_result_region_crc  = 0;
    pmu_diag_completed      = 0U;
#ifdef RUNNER_TEST_ONLY_HOOKS
    /* A pending one-shot must not survive a RESET_RUNNER: the host would then
     * see a run fail with no record of having armed it. */
    test_skip_next_npu_armed = 0U;
#endif
    last_chunk_valid    = 0;
    last_chunk_sequence = 0;
    last_chunk_offset   = 0;
    last_chunk_length   = 0;
    last_chunk_data_crc = 0;
    runner_state        = ST_IDLE;
}

static int range_inside(uint32_t base, uint32_t len, uint32_t lo, uint32_t hi)
{
    if (len == 0U) {
        return 0;
    }
    if (base < lo || base >= hi) {
        return 0;
    }
    return len <= (hi - base);
}

/* ------------------------------------------------------------------------ */
/* Frame transmission -- the ONLY permitted transmit path, and it is only    */
/* ever invoked with measurement_active == 0.                                */
/* ------------------------------------------------------------------------ */

static void send_frame(uint8_t command, uint16_t flags, uint32_t sequence,
                       const void *payload, uint32_t payload_length)
{
    uint8_t header[RUNNER_HEADER_SIZE];
    uint32_t crc;
    uint8_t crc_bytes[4];

    wr_u32(&header[0], RUNNER_MAGIC);
    header[4] = RUNNER_VERSION;
    header[5] = command;
    wr_u16(&header[6], flags);
    wr_u32(&header[8], sequence);
    wr_u32(&header[12], payload_length);

    crc = crc32_update(CRC32_INIT, header, RUNNER_HEADER_SIZE);
    if (payload_length != 0U) {
        crc = crc32_update(crc, payload, payload_length);
    }
    crc = crc32_final(crc);
    wr_u32(crc_bytes, crc);

    put_block(header, RUNNER_HEADER_SIZE);
    if (payload_length != 0U) {
        put_block((const uint8_t *)payload, payload_length);
    }
    put_block(crc_bytes, 4);
}

static void send_ack(uint8_t request_command, uint32_t sequence,
                     const void *payload, uint32_t payload_length)
{
    send_frame((uint8_t)(request_command | RESP_ACK_FLAG), ERR_NONE, sequence,
               payload, payload_length);
}

static void send_nack(uint8_t request_command, uint32_t sequence, uint16_t error)
{
    uint8_t payload[4];

    payload[0] = request_command;
    payload[1] = (uint8_t)runner_state;
    payload[2] = 0;
    payload[3] = 0;

    send_frame(RESP_NACK_CMD, error, sequence, payload, sizeof(payload));
}

/* ------------------------------------------------------------------------ */
/* Status payload (PING / GET_STATE): 40 bytes -- UNCHANGED from v1.         */
/* Deliberately not extended. Capabilities live in GET_CAPABILITIES.         */
/* ------------------------------------------------------------------------ */

#define STATUS_PAYLOAD_SIZE 40U

static void build_status(uint8_t *out)
{
    out[0] = (uint8_t)runner_state;
    out[1] = RUNNER_VERSION;
    wr_u16(&out[2], 0);
    wr_u32(&out[4], rx_bytes);
    wr_u32(&out[8], tx_bytes);
    wr_u32(&out[12], rx_overrun_count);
    wr_u32(&out[16], bad_magic_count);
    wr_u32(&out[20], bad_version_count);
    wr_u32(&out[24], bad_crc_count);
    wr_u32(&out[28], length_error_count);
    wr_u32(&out[32], sequence_error_count);
    wr_u32(&out[36], parser_resync_count);
}

/* ------------------------------------------------------------------------ */
/* Timestamp source: DWT CYCCNT                                              */
/* ------------------------------------------------------------------------ */

static uint32_t timestamp_source_ready(void)
{
    uint32_t before;
    uint32_t after;

    /* ARMv8.1-M may implement a software lock on the DWT. Unlocking is
     * harmless where it is not implemented (the register RAZ/WI). */
    REG32(DWT_LAR_ADDR) = DWT_LAR_KEY;
    REG32(DEMCR_ADDR) |= DEMCR_TRCENA;
    REG32(DWT_CTRL_ADDR) |= DWT_CTRL_CYCCNTENA;

    __DSB();
    __ISB();

    /* Do not assume it worked -- prove the counter advances. */
    before = REG32(DWT_CYCCNT_ADDR);
    for (volatile uint32_t i = 0; i < 64U; i++) {
    }
    after = REG32(DWT_CYCCNT_ADDR);

    return (after != before) ? 1U : 0U;
}

static uint32_t read_timestamp(void)
{
    return REG32(DWT_CYCCNT_ADDR);
}

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
#if RUNNER_MEASURE_ENABLE_PMU
#error "PMU programming is out of scope for this milestone"
#endif
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

#define COMPLETION_WAIT_MODE_UNKNOWN   0U
#define COMPLETION_WAIT_MODE_BUSY_POLL 1U
#define COMPLETION_WAIT_MODE_WFI       2U

/* 29 + 5 appended for the PMU candidate. */
#define CAP_FIELD_COUNT 34U
#define CAP_PAYLOAD_SIZE (CAP_FIELD_COUNT * 4U)

/* cache_mode interpretation, derived from SCB->CCR */
#define CACHE_MODE_NONE 0U
#define CACHE_MODE_I    1U
#define CACHE_MODE_D    2U
#define CACHE_MODE_ID   3U

static void build_capabilities(uint8_t *out)
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
    put32(&c, (1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY));

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

/* ------------------------------------------------------------------------ */
/* Phase 1 execution: the EXISTING U85 convolution test, nothing dynamic.    */
/* ------------------------------------------------------------------------ */

#ifdef RUNNER_INJECT_DENYLIST_VIOLATION
/* NEGATIVE CONTROL 1 (DIRECT) -- never enabled in a real build.
 * Calling __real_printf directly is precisely the "bypasses --wrap" class of
 * defect the checker exists to catch: the wrap set does not see it, so only a
 * call-graph check over the LINKED ELF can find it. Expected: checker FAILS. */
extern int __real_printf(const char *fmt, ...);
#endif

#ifdef INJECT_SKIP_NPU_EXECUTION
/* "SKIP" in ASCII. Non-zero, so RUN_VALID_RUN_RC_OK cannot be set either. */
#define RUNNER_ERR_INJECTED_SKIP ((int32_t)0x534B4950)
/* Artifact-visible marker. check_measure_symbols.py FAILS any normal build in
 * which a runner_inject_* symbol exists, so this injection cannot reach a
 * shipped BIN even if the -D leaked into CFLAGS by accident.
 *
 * IT MUST BE REFERENCED FROM run_fixed_inference() TO SURVIVE, and that is why
 * the store below exists. This build uses -fdata-sections with
 * -Wl,--gc-sections, so an unreferenced variable is discarded at link time and
 * never reaches the ELF. Observed, not theorised: the first version of this
 * gate reported "no markers present" for a build that WAS injected, and
 * __attribute__((used, retain)) did NOT fix it -- readelf showed the section
 * flags as WA, with no SHF_GNU_RETAIN, so the attribute was silently inert on
 * this toolchain. An honest reference is the only thing that actually works. */
volatile uint32_t runner_inject_skip_npu_marker = 0x534B4950U;
#endif

#ifdef RUNNER_TEST_ONLY_HOOKS
/* "SNXP" in ASCII -- Skip Next. Non-zero, so a skipped run cannot set
 * RUN_VALID_RUN_RC_OK and therefore cannot satisfy RUN_VALID_REQUIRED_MASK.
 * Deliberately DIFFERENT from RUNNER_ERR_INJECTED_SKIP so a host can tell a
 * one-shot host-armed skip apart from a compile-time skipped image. */
#define RUNNER_ERR_TEST_SKIPPED_NPU ((int32_t)0x534E5850)

/* Artifact-visible marker, named with the runner_inject_ prefix ON PURPOSE so
 * that the pre-existing marker gate in check_measure_symbols.py fails a normal
 * build carrying it, in addition to the new reachability gate. Two independent
 * gates, one leak.
 *
 * IT MUST BE REFERENCED FROM LIVE CODE TO SURVIVE. This build uses
 * -fdata-sections with -Wl,--gc-sections, so an unreferenced variable is
 * discarded at link time and never reaches the ELF. That is not theory: the
 * first version of the skip-npu gate reported "no markers present" for a build
 * that WAS injected, and __attribute__((used, retain)) did NOT fix it --
 * readelf showed the section flags as WA with no SHF_GNU_RETAIN, so the
 * attribute was silently inert on this toolchain. The honest stores below, in
 * run_fixed_inference() and in the command handler, are the only thing that
 * actually works. */
volatile uint32_t runner_inject_test_skip_next_marker = 0x534E5850U;
#endif

#ifdef RUNNER_INJECT_INDIRECT_VIOLATION
/* NEGATIVE CONTROL 2 (INDIRECT) -- never enabled in a real build.
 * Transmits by calling through the Driver_USART0 function-pointer struct.
 * No denylisted SYMBOL is referenced, so a symbol/call-graph check CANNOT
 * see it. Expected: checker reports INCOMPLETE (not PASS), and the runtime
 * counter uart_bytes_during_measurement is what actually catches it. */
#endif

/* noinline is load-bearing, not cosmetic: the denylist checker locates the
 * measured path by symbol name in the linked ELF. If the compiler inlines this
 * into handle_run the root disappears and the check can no longer prove
 * anything (it fails closed, by design). Keeping it a real symbol also keeps
 * the measured region stable and identifiable in the disassembly. */
__attribute__((noinline))
static int32_t run_fixed_inference(void)
{
#ifdef RUNNER_INJECT_DENYLIST_VIOLATION
    __real_printf("deliberate denylist violation inside the measured path\n");
#endif
#ifdef RUNNER_INJECT_INDIRECT_VIOLATION
    Driver_USART0.Send("indirect", 8);
#endif
    struct u85_test_data_t d = {.name = "U85 Convolution test"};
    struct u85_test_meta_data_t m = {.u85_test_data = &d, .num_tests = 1};
    int32_t rc;

#ifdef RUNNER_TEST_ONLY_HOOKS
    /* TEST-ONLY ONE-SHOT SKIP. Consumed here, inside the measured window, by
     * the very next run after CMD_TEST_SKIP_NEXT_NPU armed it.
     *
     * What this reproduces that INJECT_SKIP_NPU cannot: a SUCCESSFUL run
     * followed by a FAILED run in the SAME boot session. .sec_noinit is NOLOAD
     * and survives reset, so the first run's output tensor is physically still
     * there when the second run starts. handle_run() has already poisoned the
     * output region before this point; because apU85Conv_TEST() is not called,
     * NOTHING overwrites the poison, so afterwards:
     *     output_crc == poison_crc
     *  -> RUN_VALID_OUTPUT_CHANGED stays CLEAR
     *  -> RUN_VALID_REQUIRED_MASK unsatisfied
     *  -> run_rc != 0, so RUN_VALID_RUN_RC_OK is clear too
     *  -> GET_RESULT must refuse with ERR_RESULT_NOT_VALID rather than hand
     *     back run N-1's 0x27084C4C.
     *
     * The flag is cleared BEFORE returning, so exactly one run is affected;
     * a third run in the same boot behaves normally. */
    if (test_skip_next_npu_armed) {
        test_skip_next_npu_armed = 0U;
        /* Load-bearing, not decorative: this store is what keeps the marker
         * symbol out of --gc-sections' jaws so the build gate can see it. */
        runner_inject_test_skip_next_marker = 0x534E5850U;
        (void)m;
        return RUNNER_ERR_TEST_SKIPPED_NPU;
    }
#endif

#ifdef INJECT_SKIP_NPU_EXECUTION
    /* NEGATIVE CONTROL 3 (STALE HAZARD) -- never enabled in a real build.
     * Skips the NPU entirely, which is exactly the "RUN silently failed"
     * scenario. The output region therefore still holds the poison written
     * before the window, output_crc == poison_crc, RUN_VALID_OUTPUT_CHANGED
     * stays clear, and GET_RESULT must refuse with ERR_RESULT_NOT_VALID
     * instead of handing back the previous run's 0x27084C4C.
     * Gated by check_measure_symbols.py: the marker symbol below must be
     * absent from, and apU85Conv_TEST present in, any normal artifact. */
    (void)m;
    /* Load-bearing: this store is what keeps the marker symbol out of
     * --gc-sections' jaws, so the build gate can actually see it. */
    runner_inject_skip_npu_marker = 0x534B4950U;
    rc = RUNNER_ERR_INJECTED_SKIP;
#else
    rc = (int32_t)apU85Conv_TEST(&m);
#endif
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

static void handle_run(uint32_t sequence)
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
#if RUNNER_MEASURE_ENABLE_PMU
#error "PMU programming is out of scope for this deliverable"
#endif

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
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            uint32_t cnten;

            /* PMCR.cnt_en is a GLOBAL gate; it does not arm any counter.
             * npu_pmu_reset_counters() clears PMCNTEN for everything, so the
             * cycle counter must be armed explicitly afterwards. Skipping this
             * is what produced window_cycles == 0 with every other flag green. */
            npu_pmu_disable();
            npu_pmu_reset_counters();
            pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);
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
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
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
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
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
            /* Milestone 1 arms no event counters: every slot stays invalid. */
            r.event_valid_mask    = 0U;
            r.event_overflow_mask = 0U;
            r.applied_event_count = 0U;
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
}

/* ------------------------------------------------------------------------ */
/* Command handlers -- unchanged from runner_v1_main.c unless noted          */
/* ------------------------------------------------------------------------ */

/* ======================================================================== */
/* PMU_DIAG implementation                                                   */
/* ======================================================================== */

/* Contract order, pre-call: PMCR / PMCNTENSET / PMCCNTR_CFG /
 * PMCCNTR HI-LO-HI / PMOVSSET. Also used for the post-disable snapshot. */
static void pmu_diag_capture_pre_order(pmu_diag_snapshot_t *s)
{
    uint64_t cycles;

    s->pmcr        = pmu_reg_read(NPU_REG_PMCR);
    s->pmcntenset  = pmu_reg_read(NPU_REG_PMCNTENSET);
    s->pmccntr_cfg = pmu_reg_read(NPU_REG_PMCCNTR_CFG);
    cycles = npu_pmu_read_cycles(&s->cycle_read_stable, &s->cycle_read_retries);
    s->cycle_lo = (uint32_t)(cycles & 0xFFFFFFFFU);
    s->cycle_hi = (uint32_t)(cycles >> 32);
    s->pmovsset = pmu_reg_read(NPU_REG_PMOVSSET);
}

/* Contract order, post-call and BEFORE the disable: the cycle counter is
 * read FIRST so the window it describes ends as close to the inference
 * return as an MMIO read allows. */
static void pmu_diag_capture_post_order(pmu_diag_snapshot_t *s)
{
    uint64_t cycles;

    cycles = npu_pmu_read_cycles(&s->cycle_read_stable, &s->cycle_read_retries);
    s->cycle_lo = (uint32_t)(cycles & 0xFFFFFFFFU);
    s->cycle_hi = (uint32_t)(cycles >> 32);
    s->pmcr        = pmu_reg_read(NPU_REG_PMCR);
    s->pmcntenset  = pmu_reg_read(NPU_REG_PMCNTENSET);
    s->pmccntr_cfg = pmu_reg_read(NPU_REG_PMCCNTR_CFG);
    s->pmovsset = pmu_reg_read(NPU_REG_PMOVSSET);
}

static void pmu_diag_wait_cycles(uint32_t ts_valid, uint32_t cycles)
{
    if (ts_valid) {
        const uint32_t start = read_timestamp();
        while ((read_timestamp() - start) < cycles) {
        }
    } else {
        for (volatile uint32_t n = 0U; n < cycles; n++) {
        }
    }
}

#if defined(PMU_DIAG_SEAM_S2)
/* S2's whole point: the re-hold must be the FIRST thing that happens after
 * run_fixed_inference() returns -- before any NPU read, any PMU read and
 * even the DWT timestamp. Anything sampled first would change the very race
 * being measured, so this function contains exactly one action and the
 * static gate proves nothing precedes its call.
 *
 * noinline is load-bearing: check_diag_case.py locates the call in the
 * disassembly of handle_run_pmu_diag and requires it to be the first `bl`
 * after the call to run_fixed_inference. */
static __attribute__((noinline)) void pmu_diag_rehold_power(void)
{
    npu_write(NPU_OFF_CMD, 0U);
    __DSB();
    __ISB();
}
#endif

#if defined(PMU_QUAL_SCHEMA_V8)
/* ======================================================================== */
/* H-PRINTF qualification hook                                               */
/*                                                                           */
/* The seam v7 proved we need is INSIDE the vendor driver: after its own     */
/* CMD=0 stop and before its own terminal CMD=0xC release. No runner code    */
/* runs there, and the driver is not modified, so the only way in is the     */
/* one call the driver already makes at exactly that point --                */
/* printf("Testing CPM signals\n") under TEST_CPM=1 -- which the linker's    */
/* --wrap=printf already routes through this file.                           */
/*                                                                           */
/* That makes the callsite a HIDDEN dependency: nothing in C names it, and   */
/* string presence proves nothing about lowering, inlining or wrapping.      */
/* check_pmu_qual.py therefore re-derives it from the final ELF and pins the */
/* expected return address in the build manifest, and the host compares that */
/* against the LR recorded below. Neither side trusts the other's word.      */
/* ======================================================================== */

/* Arm/observation state. volatile throughout: every one of these is written
 * or read from inside the measured window, reached from vendor code the
 * compiler cannot see through. */
static volatile uint32_t pmu_qual_hook_armed;
static volatile uint32_t pmu_qual_hook_arm_requested;
static volatile uint32_t pmu_qual_hook_arm_consumed;
static volatile uint32_t pmu_qual_hook_detected_count;
static volatile uint32_t pmu_qual_hook_fired_count;
static volatile uint32_t pmu_qual_hook_snapshot_valid;
static volatile uint32_t pmu_qual_hook_callsite_lr;
static volatile uint32_t pmu_qual_hook_entry_timestamp;
static volatile uint32_t pmu_qual_hook_exit_timestamp;
static volatile uint32_t pmu_qual_npu_cmd_at_hook;
static volatile uint32_t pmu_qual_pmcr_disable_readback;
static volatile uint32_t pmu_qual_hook_pmu_reads;
static volatile uint32_t pmu_qual_hook_pmu_writes;
static pmu_diag_snapshot_t pmu_qual_internal_pre_release;
static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

static void pmu_qual_reset_hook_state(void)
{
    pmu_qual_hook_armed            = 0U;
    pmu_qual_hook_arm_requested    = 0U;
    pmu_qual_hook_arm_consumed     = 0U;
    pmu_qual_hook_detected_count   = 0U;
    pmu_qual_hook_fired_count      = 0U;
    pmu_qual_hook_snapshot_valid   = 0U;
    pmu_qual_hook_callsite_lr      = 0U;
    pmu_qual_hook_entry_timestamp  = 0U;
    pmu_qual_hook_exit_timestamp   = 0U;
    pmu_qual_npu_cmd_at_hook       = 0U;
    pmu_qual_pmcr_disable_readback = 0U;
    pmu_qual_hook_pmu_reads        = 0U;
    pmu_qual_hook_pmu_writes       = 0U;
    memset(&pmu_qual_internal_pre_release, 0,
           sizeof(pmu_qual_internal_pre_release));
    memset(&pmu_qual_internal_post_disable, 0,
           sizeof(pmu_qual_internal_post_disable));
}

/* Match the vendor format string by CONTENT. It is anonymous rodata, so its
 * ADDRESS moves between links and pointer identity would be meaningless.
 *
 * Written as explicit indexed character constants, which looks worse than a
 * strcmp and is the only correct spelling here, for two independent reasons:
 *
 *   - a second copy of the literal in this file would be a second callsite
 *     argument that reconstructs to the target bytes. The ELF gate counts the
 *     unique target callsite by reconstructing exactly that argument, so one
 *     more copy would break the term that makes the whole hook trustworthy.
 *   - strcmp/memcmp/strlen would be a libc call made FROM the printf wrapper,
 *     inside the measured window. The design forbids the hook path from
 *     reaching any wrapped or logging function; this is the same rule one
 *     level up.
 *
 * No loop and no recursion: the comparison is a fixed, fully unrolled chain.
 * && short-circuits, so a shorter string stops at its NUL and is never read
 * past. "Testing CPM signals\n" is 20 characters plus the terminator, and all
 * 21 positions are compared -- a prefix or an extended string both fail. */
static int pmu_qual_is_target_format(const char *fmt)
{
    if (fmt == (const char *)0) {
        return 0;
    }
    return fmt[0]  == 'T' && fmt[1]  == 'e' && fmt[2]  == 's'
        && fmt[3]  == 't' && fmt[4]  == 'i' && fmt[5]  == 'n'
        && fmt[6]  == 'g' && fmt[7]  == ' ' && fmt[8]  == 'C'
        && fmt[9]  == 'P' && fmt[10] == 'M' && fmt[11] == ' '
        && fmt[12] == 's' && fmt[13] == 'i' && fmt[14] == 'g'
        && fmt[15] == 'n' && fmt[16] == 'a' && fmt[17] == 'l'
        && fmt[18] == 's' && fmt[19] == '\n' && fmt[20] == '\0';
}

#if defined(PMU_QUAL_MODE_Q1)
/* The pre-release side effect. Q1 only -- Q0 must not carry this symbol at
 * all, and the ELF gate checks both directions.
 *
 * It runs between the vendor's STOP and the vendor's release, so every access
 * below is inside the measured window and is counted in the window totals;
 * the hook-local deltas are reported as a SUBSET of those, which is why the
 * host requires window >= hook rather than equality.
 *
 * It must not printf, puts, serial_print or write UART: it is reached FROM
 * the printf wrapper, so any of those is re-entrancy, and any UART traffic
 * contaminates the window this hook exists to close.
 *
 * noinline is load-bearing twice: the symbol is itself a gate term, and the
 * ordering below has to survive as one block rather than being interleaved
 * into the wrapper. */
static __attribute__((noinline)) void pmu_qual_pre_release_hook(void)
{
    const uint32_t hook_r0 = pmu_mmio_read_count;
    const uint32_t hook_w0 = pmu_mmio_write_count;

    /* Entry timestamp and the normalized caller LR are already captured by
     * the wrapper, before this call -- they describe the callsite, not this
     * function's own entry. */

    /* The vendor has issued its STOP and has NOT yet issued its release, so
     * this must read exactly 0. Recorded, never branched on: the firmware
     * reports raw evidence and the host decides validity. */
    pmu_qual_npu_cmd_at_hook = npu_read(NPU_OFF_CMD);

    /* Cycle counter FIRST -- post-capture order. This snapshot is the END of
     * the measured window, so it must sit as close to the vendor's release as
     * an MMIO read allows. */
    pmu_diag_capture_post_order(&pmu_qual_internal_pre_release);

    /* EXACTLY ONE disable, here. After test_u85() returns the runner only
     * reads: a second disable would make the window's MMIO write count mean
     * two different things and would destroy the after-return evidence. */
    npu_pmu_disable();
    __DSB();
    pmu_qual_pmcr_disable_readback = pmu_reg_read(NPU_REG_PMCR);

    pmu_diag_capture_pre_order(&pmu_qual_internal_post_disable);

    pmu_qual_hook_exit_timestamp = read_timestamp();

    pmu_qual_hook_pmu_reads  = pmu_mmio_read_count - hook_r0;
    pmu_qual_hook_pmu_writes = pmu_mmio_write_count - hook_w0;

    /* Latched LAST, and only here. A hook that faulted or was cut short must
     * never present as a complete one. */
    pmu_qual_hook_snapshot_valid = 1U;
}
#endif /* PMU_QUAL_MODE_Q1 */
#endif /* PMU_QUAL_SCHEMA_V8 */

static void put_diag_snapshot(wcur_t *c, const pmu_diag_snapshot_t *s)
{
    put32(c, s->pmcr);
    put32(c, s->pmcntenset);
    put32(c, s->pmccntr_cfg);
    put32(c, s->cycle_lo);
    put32(c, s->cycle_hi);
    put32(c, s->cycle_read_stable);
    put32(c, s->cycle_read_retries);
    put32(c, s->pmovsset);
}

static void build_pmu_diag_payload(uint8_t *out)
{
    const pmu_diag_record_t *d = &last_pmu_diag;
    wcur_t c = {out, 0};
    uint32_t crc;

    put32(&c, PMU_DIAG_ABI_MAGIC);
    put32(&c, PMU_DIAG_SCHEMA_VERSION);
    put32(&c, PMU_DIAG_TOTAL_WORDS);
    put32(&c, PMU_DIAG_HEADER_WORDS);
    put32(&c, d->run_sequence);
    put32(&c, d->valid_flags);
    put32(&c, d->run_rc);
    put32(&c, 0U); /* payload_crc32 placeholder, filled in below */

    put32(&c, d->schema_version);
    put32(&c, d->build_id);
    put32(&c, d->diag_case);
    put32(&c, d->nc_control_id);
    put32(&c, d->run_sequence);
    put32(&c, d->cfg_write_performed);
    put32(&c, d->cfg_write_value);
    put32(&c, d->cfg_readback_after_write);
    put32(&c, d->run_rc);
    put32(&c, d->valid_flags);
    put32(&c, d->poison_crc);
    put32(&c, d->output_crc);
    put32(&c, d->result_region_crc);
    put32(&c, d->ts_source_valid);
    put32(&c, d->t_call_enter);
    put32(&c, d->t_call_return);
    put32(&c, d->t_pmu_disable);
    put32(&c, d->pmcr_readback_after_disable);
    put32(&c, d->pmu_mmio_read_count_delta);
    put32(&c, d->pmu_mmio_write_count_delta);
    put32(&c, d->start_sequence_id);
    put32(&c, d->power_guard_cycles);
    put32(&c, d->npu_cmd_before_power_request);
    put32(&c, d->npu_cmd_after_power_request);
    put32(&c, d->npu_status_after_power_request);
    put32(&c, d->reset_guard_cycles);
    put32(&c, d->pmcr_after_reset_guard);
    put32(&c, d->pmcr_after_program);
    put32(&c, d->armed_after_program);
    put32(&c, d->program_stability_reads);
    put32(&c, d->program_stable);
#if defined(PMU_QUAL_SCHEMA_V8)
    put32(&c, d->npu_cmd_after_return);   /* same slot, v8 meaning */
#else
    put32(&c, d->npu_cmd_after_power_release);
#endif
    put32(&c, d->power_seam_id);
    put32(&c, d->power_rehold_performed);
    put32(&c, d->rehold_guard_cycles);
    put32(&c, d->npu_cmd_after_seam);
    put32(&c, d->npu_status_after_seam);
    put32(&c, d->golden_window_base);
    put32(&c, d->golden_window_len);
    put32(&c, d->golden_window_crc);
#if defined(PMU_QUAL_SCHEMA_V8)
    /* The 13 appended hook words, in the numbered wire order the host
     * dataclass and the schema-v8 ABI tests are written against. */
    put32(&c, d->qualification_mode);
    put32(&c, d->hook_armed);
    put32(&c, d->hook_arm_consumed);
    put32(&c, d->hook_detected_count);
    put32(&c, d->hook_fired_count);
    put32(&c, d->hook_snapshot_valid);
    put32(&c, d->hook_callsite_lr_observed);
    put32(&c, d->hook_entry_timestamp);
    put32(&c, d->hook_exit_timestamp);
    put32(&c, d->npu_cmd_at_hook);
    put32(&c, d->pmcr_disable_readback_at_hook);
    put32(&c, d->hook_pmu_mmio_read_count);
    put32(&c, d->hook_pmu_mmio_write_count);
    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->internal_pre_release);
    put_diag_snapshot(&c, &d->internal_post_disable);
    put_diag_snapshot(&c, &d->after_return);
#else
    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->post);
    put_diag_snapshot(&c, &d->post_disable);
#endif

    /* Two-slice CRC, EXACTLY the RUN_COMPLETE rule: words 4..6 and words
     * 8..total-1, excluding the CRC word itself. One host code path. */
    crc = crc32_update(CRC32_INIT, out + (4U * 4U), 3U * 4U);
    crc = crc32_update(crc, out + (PMU_DIAG_HEADER_WORDS * 4U),
                       PMU_DIAG_FIELD_COUNT * 4U);
    crc = crc32_final(crc);
    wr_u32(out + (PMU_DIAG_CRC_WORD_INDEX * 4U), crc);
}

/* The ONLY run path in this image. Mirrors handle_run()'s window discipline
 * -- poison first, ACK before the window, TX forbidden, RX masked at the
 * NVIC, output CRC guard after -- and differs inside the window only in the
 * PMU programming and the three raw snapshots the contract demands.
 *
 * It never latches the production GET_RESULT gate and never touches
 * last_measurement: every production presentation path in this image
 * answers UNSUPPORTED, and the diag record carries its own CRC evidence.
 *
 * The u85 ISR wrapper IS installed and restored, exactly as handle_run
 * does and strictly OUTSIDE the window -- both for production parity and
 * because the frozen denylist gate roots on runner_u85_irq_wrapper. What is
 * deliberately NOT carried over from handle_run is the RECORD surface: the
 * ISPR deltas, vector-survival evidence and IRQ-priority fields are
 * production-record concerns; the diag record answers one question (what
 * did the five PMU registers hold at the three contract points) and every
 * extra MMIO access widens the window. */
static void handle_run_pmu_diag(uint32_t sequence)
{
    pmu_diag_record_t d = {0};
    uint8_t accept[4];
    uint8_t resp[PMU_DIAG_PAYLOAD_SIZE];
    uint32_t ts_valid;
    uint32_t uart_rx_was_enabled;
    uint32_t state_after;
    uint32_t poison_crc;
    uint32_t output_crc;
    uint32_t result_region_crc;
    uint32_t poison_len;
    uint32_t flags;
    int32_t  rc;

    memset(&d, 0, sizeof(d));

    /* Invalidate BOTH result gates first, same rule as handle_run: nothing
     * below may fail in a way that leaves a stale result presentable. */
    last_run_completed      = 0;
    last_completed_sequence = 0;
    last_valid_flags        = 0;
    pmu_diag_completed      = 0U;
    last_measurement.valid  = 0U;
#if defined(PMU_QUAL_SCHEMA_V8)
    /* Same freshness rule as the two result gates above, and for the same
     * reason: a hook count or an LR left over from the previous run would be
     * indistinguishable from this run's evidence. */
    pmu_qual_reset_hook_state();
#endif

    run_sequence_counter++;
    last_run_sequence = run_sequence_counter;

    poison_len = poison_region_length();
    poison_crc = poison_output_region(last_run_sequence);

    ts_valid = timestamp_source_ready();

    uart_rx_was_enabled = (NVIC_GetEnableIRQ(UART0_RX_IRQn) != 0U) ? 1U : 0U;

    runner_state = ST_RUNNING;
    wr_u32(&accept[0], 0U); /* 0 == accepted */
    send_ack(CMD_RUN_PMU_DIAG, sequence, accept, sizeof(accept));

    /* Contract B, same order as handle_run. */
    uart_tx_forbidden = 1U;
    __DSB();
    uart_tx_drain_fixed_delay(ts_valid);

    NVIC_DisableIRQ(UART0_RX_IRQn);
    NVIC_DisableIRQ(UART0_IRQn);
    NVIC_DisableIRQ(UART_OVFL_IRQn);
    __DSB();
    __ISB();

    if (UART0_REGS[REG_STATE] & STATE_RXBF) {
        (void)UART0_REGS[REG_DATA];
    }
    UART0_REGS[REG_STATE] = STATE_RXOR;

    /* Install the instrumentation wrapper exactly as handle_run does --
     * OUTSIDE the window, so it cannot touch any snapshot. On this build
     * u85.c reinstalls its own vector at the top of test_u85(), so the
     * wrapper is not reached; it is kept because it is part of the audited
     * measured path (the frozen denylist gate roots on it) and because the
     * diag window should differ from production ONLY in PMU programming. */
    sample_isr_entry_timestamp = 0;
    sample_isr_exit_timestamp  = 0;
    sample_qread               = 0;
    sample_irq_status          = 0;
    measurement_complete       = 0;
    install_u85_irq_wrapper();

    /* Every poison store must be observable before the NPU is submitted to. */
    __DMB();
    __DSB();

    /* ================= WINDOW OPENS ================= */
    measurement_active = 1U;
    __DSB();
    __ISB();

    {
        const uint32_t pmu_r0 = pmu_mmio_read_count;
        const uint32_t pmu_w0 = pmu_mmio_write_count;
        uint32_t expected_cfg = 0U;
        uint32_t expected_arm;

        d.schema_version  = PMU_DIAG_SCHEMA_VERSION;
        d.build_id        = RUNNER_FIRMWARE_BUILD_ID;
        d.diag_case       = PMU_DIAG_CASE_ID;
        d.nc_control_id   = PMU_DIAG_NC_ID;
        d.run_sequence    = last_run_sequence;
        d.ts_source_valid = ts_valid;
#if defined(PMU_QUAL_SCHEMA_V8)
        /* v8 runs no seam experiment; the retained slot is pinned so a v7
         * seam image can never be decoded as a v8 record. */
        d.power_seam_id      = PMU_QUAL_POWER_SEAM_ID;
        d.qualification_mode = PMU_QUAL_MODE_ID;
#else
        d.power_seam_id   = PMU_DIAG_POWER_SEAM_ID;
#endif

        /* Boot6/v5 proved the missing boundary: this selftest driver leaves
         * the NPU clock/power Q interfaces enabled for shutdown between runs,
         * while the vendor core-driver explicitly requests power BEFORE PMU
         * enable. Hold both interfaces first (CMD[3:2]=0), let that request
         * settle, and only then touch PMU state. */
        d.start_sequence_id = PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM;
        d.npu_cmd_before_power_request = npu_read(NPU_OFF_CMD);
        npu_write(NPU_OFF_CMD, 0U);
        __DSB();
        __ISB();
        d.power_guard_cycles = PMU_DIAG_POWER_GUARD_CYCLES;
        pmu_diag_wait_cycles(ts_valid, PMU_DIAG_POWER_GUARD_CYCLES);
        d.npu_cmd_after_power_request = npu_read(NPU_OFF_CMD);
        d.npu_status_after_power_request = npu_read(NPU_OFF_STATUS);

        /* v1-v4 also proved that reset-bit readback and immediate programming
         * readback are too early. Launch reset+enable while power is held,
         * then wait a second bounded interval before final programming. */
        npu_pmu_disable();
        pmu_reg_write(NPU_REG_PMOVSCLR, 0xFFFFFFFFU);
        pmu_reg_write(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
        pmu_reg_write(NPU_REG_PMINTCLR, 0xFFFFFFFFU);
        pmu_reg_write(NPU_REG_PMCR,
                      NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK
                                            | NPU_PMCR_CYCLE_CNT_RST_MSK);
        __DSB();
        __ISB();
        d.reset_guard_cycles = PMU_DIAG_RESET_GUARD_CYCLES;
        pmu_diag_wait_cycles(ts_valid, PMU_DIAG_RESET_GUARD_CYCLES);
        d.pmcr_after_reset_guard = pmu_reg_read(NPU_REG_PMCR);

        /* Final programming happens only after the guard. No reset write is
         * permitted below this point. */
        pmu_ever_enabled = 1U;
        pmu_reg_write(NPU_REG_PMCR, NPU_PMCR_CNT_EN_MSK);

        /* Case-specific PMCCNTR_CFG handling -- the ONLY difference between
         * the three images. Case A performs NO write of any kind; the
         * preprocessing gate proves the write call is absent from its
         * translation unit. */
#if defined(PMU_DIAG_CASE_B)
# if defined(PMU_DIAG_NC_SKIP_CFG_WRITE)
        /* negative control 1: the B image with the CFG write omitted */
        d.cfg_write_performed = 0U;
# elif defined(PMU_DIAG_NC_START_NO_EVENT)
        /* negative control 2: configured never to start */
        pmu_reg_write(NPU_REG_PMCCNTR_CFG, NPU_PMU_DIAG_CFG_NO_EVENT);
        d.cfg_write_performed      = 1U;
        d.cfg_write_value          = NPU_PMU_DIAG_CFG_NO_EVENT;
        d.cfg_readback_after_write = pmu_reg_read(NPU_REG_PMCCNTR_CFG);
# else
        pmu_reg_write(NPU_REG_PMCCNTR_CFG, NPU_PMU_CYCLE_CFG_VALUE);
        d.cfg_write_performed      = 1U;
        d.cfg_write_value          = NPU_PMU_CYCLE_CFG_VALUE;
        d.cfg_readback_after_write = pmu_reg_read(NPU_REG_PMCCNTR_CFG);
        expected_cfg               = NPU_PMU_CYCLE_CFG_VALUE;
# endif
#elif defined(PMU_DIAG_CASE_C)
        /* Explicit zero-config write: the positive control for the CFG
         * write/readback PATH even though the counter never starts. */
        pmu_reg_write(NPU_REG_PMCCNTR_CFG, NPU_PMU_DIAG_CFG_NO_EVENT);
        d.cfg_write_performed      = 1U;
        d.cfg_write_value          = NPU_PMU_DIAG_CFG_NO_EVENT;
        d.cfg_readback_after_write = pmu_reg_read(NPU_REG_PMCCNTR_CFG);
#else /* PMU_DIAG_CASE_A: no PMCCNTR_CFG write of ANY kind */
        d.cfg_write_performed = 0U;
#endif

#if !defined(PMU_DIAG_NC_SKIP_ARM)
        /* PMCR.cnt_en is a GLOBAL gate; the cycle counter must be armed
         * explicitly -- the same lesson the candidate image already paid
         * for. */
        pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);
        expected_arm = 1U;
#else
        expected_arm = 0U;
#endif
        __DSB();
        __ISB();
        d.pmcr_after_program = pmu_reg_read(NPU_REG_PMCR);
        d.armed_after_program =
            (pmu_reg_read(NPU_REG_PMCNTENSET) & NPU_PMU_PMCNTEN_CYCLE_MASK)
                ? 1U : 0U;

        /* Spaced persistence proof: a one-off successful readback was the
         * v4 trap. Every sample must retain the final programmed state. */
        d.program_stable = 1U;
        for (uint32_t n = 1U; n <= PMU_DIAG_STABILITY_SAMPLES; n++) {
            pmu_diag_wait_cycles(ts_valid, PMU_DIAG_STABILITY_GAP_CYCLES);
            __DSB();
            __ISB();
            d.program_stability_reads = n;
            if ((pmu_reg_read(NPU_REG_PMCR) & NPU_PMCR_CNT_EN_MSK) == 0U ||
                (((pmu_reg_read(NPU_REG_PMCNTENSET) & NPU_PMU_PMCNTEN_CYCLE_MASK)
                    ? 1U : 0U) != expected_arm) ||
                pmu_reg_read(NPU_REG_PMCCNTR_CFG) != expected_cfg) {
                d.program_stable = 0U;
                break;
            }
        }
#if defined(PMU_DIAG_NC_FORCE_OVERFLOW)
        /* negative control 4: PMOVSSET is a set register, so writing the
         * cycle bit plants the sticky overflow flag the validity logic
         * must refuse to measure through. */
        pmu_reg_write(NPU_REG_PMOVSSET, NPU_PMU_PMOVS_CYCLE_OVF_MASK);
#endif
        __DSB();
        __ISB();

        pmu_diag_capture_pre_order(&d.pre);

        d.t_call_enter = read_timestamp();
#if defined(PMU_QUAL_SCHEMA_V8)
        /* Armed as the LAST action before submission, so the interval between
         * arming and the vendor's own callsite contains nothing else that
         * could reach the wrapper. hook_armed is the live one-shot flag;
         * hook_arm_requested is the RECORD of having armed, which survives
         * the detection that consumes the flag. */
        pmu_qual_hook_arm_requested = 1U;
        pmu_qual_hook_armed         = 1U;
        __DSB();
#endif
        rc = run_fixed_inference();

        /* ---- SEAM. Nothing may be sampled before this point. ------------
         * S2 re-holds power as its first action; S1 and S3 do nothing here.
         * The t_call_return timestamp deliberately moved BELOW the seam so
         * that in S2 the CMD=0 write is provably the first access of any
         * kind after the return. For S2 the interval therefore includes
         * rehold_guard_cycles, which is why that bound is reported. */
#if defined(PMU_DIAG_SEAM_S2)
        pmu_diag_rehold_power();
        d.power_rehold_performed = 1U;
        d.rehold_guard_cycles    = PMU_DIAG_REHOLD_GUARD_CYCLES;
        pmu_diag_wait_cycles(ts_valid, PMU_DIAG_REHOLD_GUARD_CYCLES);
#endif
        d.t_call_return = read_timestamp();

        /* Post-seam telemetry: legal here because the seam has already run.
         * Identical placement in all three images so the rows compare. */
        d.npu_cmd_after_seam    = npu_read(NPU_OFF_CMD);
        d.npu_status_after_seam = npu_read(NPU_OFF_STATUS);

#if defined(PMU_QUAL_SCHEMA_V8)
        /* AFTER THE RETURN, v8 ONLY READS.
         *
         * The one PMU disable already happened inside the hook, before the
         * vendor's release. v7 disabled here because its POST snapshot was
         * here; v8's authoritative end-of-window snapshot is the hook's
         * internal_pre_release, so a disable at this point would be a SECOND
         * one -- it would double the window's PMU write count and it would
         * overwrite the only state that shows what the release did.
         *
         * The bank is expected to read wiped below. That is corroboration
         * that the release happened, not a measurement, and the classifier
         * excludes after_return from every validity term. */
        pmu_diag_capture_pre_order(&d.after_return);

        d.pmcr_readback_after_disable = pmu_qual_pmcr_disable_readback;
        d.t_pmu_disable               = pmu_qual_hook_exit_timestamp;

        /* Hook evidence, copied out once the window is quiet. */
        d.hook_armed                    = pmu_qual_hook_arm_requested;
        d.hook_arm_consumed             = pmu_qual_hook_arm_consumed;
        d.hook_detected_count           = pmu_qual_hook_detected_count;
        d.hook_fired_count              = pmu_qual_hook_fired_count;
        d.hook_snapshot_valid           = pmu_qual_hook_snapshot_valid;
        d.hook_callsite_lr_observed     = pmu_qual_hook_callsite_lr;
        d.hook_entry_timestamp          = pmu_qual_hook_entry_timestamp;
        d.hook_exit_timestamp           = pmu_qual_hook_exit_timestamp;
        d.npu_cmd_at_hook               = pmu_qual_npu_cmd_at_hook;
        d.pmcr_disable_readback_at_hook = pmu_qual_pmcr_disable_readback;
        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;
        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;
        d.internal_pre_release          = pmu_qual_internal_pre_release;
        d.internal_post_disable         = pmu_qual_internal_post_disable;
#else
        /* Post-call snapshot BEFORE the disable, cycle first -- contract. */
        pmu_diag_capture_post_order(&d.post);

        npu_pmu_disable();
        __DSB();
        d.pmcr_readback_after_disable = pmu_reg_read(NPU_REG_PMCR);
        d.t_pmu_disable = read_timestamp();

        pmu_diag_capture_pre_order(&d.post_disable);
#endif

        /* Overflow deliberately NOT cleared here: the snapshots above are
         * the evidence and clearing now would destroy it. */

        /* The window totals INCLUDE the hook's own PMU accesses, because the
         * hook ran inside run_fixed_inference(). The hook-local counts are
         * therefore a subset, and the host requires total >= hook rather
         * than equality. */
        d.pmu_mmio_read_count_delta  = pmu_mmio_read_count - pmu_r0;
        d.pmu_mmio_write_count_delta = pmu_mmio_write_count - pmu_w0;

        /* Restore the board's terminal state once every PMU read is done.
         * S3's private u85_diag.c skipped the driver's own CMD=0xC, and S2
         * cancelled it with a re-hold, so both owe the board that release
         * here. S1 never disturbed it -- the reference driver already issued
         * the release inside test_u85() -- so S1 only READS the register.
         * All three therefore leave the board in the same terminal state and
         * report the same readback. */
#if defined(PMU_DIAG_SEAM_S2) || defined(PMU_DIAG_SEAM_S3)
        npu_write(NPU_OFF_CMD, 0x0000000CU);
        __DSB();
        __ISB();
#endif
#if defined(PMU_QUAL_SCHEMA_V8)
        /* v8 is S1-shaped: the reference driver issued its own terminal
         * release inside test_u85(), so the runner only READS it back. Bits
         * 3:2 == 0xC here is the proof that the hook did not displace or
         * skip the vendor's release. */
        d.npu_cmd_after_return = npu_read(NPU_OFF_CMD);
#else
        d.npu_cmd_after_power_release = npu_read(NPU_OFF_CMD);
#endif
    }

    poison_cache_invalidate(poison_region_base(), poison_len);
    __DSB();

    output_crc        = crc32_buffer(poison_region_base(), poison_len);
    result_region_crc = crc32_buffer(
        (const void *)(uintptr_t)__sec_noinit_start,
        (uint32_t)(__sec_noinit_end - __sec_noinit_start));

    /* The exact 256-byte golden window, straight from the overlay symbols.
     * THIS is the semantic-drift judgement in the diag image; the
     * whole-region CRC above stays corroboration only -- the A/B boot1/2
     * runs proved it varies with residual scratch content across boots. */
    d.golden_window_base = (uint32_t)(uintptr_t)__pmu_diag_golden_window_base__;
    d.golden_window_len  = (uint32_t)(uintptr_t)__pmu_diag_golden_window_len__;
    d.golden_window_crc  = crc32_buffer(
        (const void *)(uintptr_t)d.golden_window_base, d.golden_window_len);

    flags = RUN_VALID_RUN_COMPLETED;
    if (rc == 0) {
        flags |= RUN_VALID_RUN_RC_OK;
    }
    if (poison_len != 0U && output_crc != poison_crc) {
        flags |= RUN_VALID_OUTPUT_CHANGED;
    }
    if (ts_valid && (d.t_call_return - d.t_call_enter) != 0U) {
        flags |= RUN_VALID_COARSE_WINDOW;
    }
    if (result_region_crc == RUNNER_EXPECTED_TEST19_CRC32) {
        flags |= RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH;
    }

    __DSB();
    __ISB();
    measurement_active = 0U;
    /* ================= WINDOW CLOSED ================ */

    /* Restore the original NPU vector, then the UART IRQ enables, in the
     * same order as handle_run. */
    restore_u85_irq_vector();
    if (uart_rx_was_enabled) {
        NVIC_EnableIRQ(UART0_RX_IRQn);
    }
    __DSB();
    __ISB();

    state_after = UART0_REGS[REG_STATE];
    if (state_after & STATE_RXBF) {
        (void)UART0_REGS[REG_DATA]; /* discard: NOT parsed, per contract */
    }
    if (state_after & STATE_RXOR) {
        UART0_REGS[REG_STATE] = STATE_RXOR;
        rx_overrun_count++;
    }

    d.run_rc            = (uint32_t)rc;
    d.valid_flags       = flags;
    d.poison_crc        = poison_crc;
    d.output_crc        = output_crc;
    d.result_region_crc = result_region_crc;

    /* The production latches stay CLEARED (they were invalidated at the
     * top): GET_RESULT and GET_MEASUREMENT answer UNSUPPORTED here, and a
     * latch nothing can present is one more place for confusion to hide.
     * Only the diag gate is set, at the very end, all together. */
    run_rc             = rc;
    last_pmu_diag      = d;
    pmu_diag_completed = 1U;
    runner_state       = ST_RESULT_READY;

    /* Only now is transmitting legal again. */
    uart_tx_forbidden = 0U;
    __DSB();

    build_pmu_diag_payload(resp);
    send_frame(CMD_PMU_DIAG_COMPLETE, ERR_NONE, sequence, resp, sizeof(resp));
}

static void handle_get_pmu_diag_result(uint32_t sequence)
{
    uint8_t resp[PMU_DIAG_PAYLOAD_SIZE];

    if (!pmu_diag_completed) {
        send_nack(CMD_GET_PMU_DIAG_RESULT, sequence, ERR_NO_MEASUREMENT);
        return;
    }
    build_pmu_diag_payload(resp);
    send_ack(CMD_GET_PMU_DIAG_RESULT, sequence, resp, sizeof(resp));
}

static void handle_load_model_begin(uint32_t sequence, const uint8_t *payload,
                                    uint32_t payload_length)
{
    uint32_t total_length;
    uint32_t expected_crc;
    uint32_t staging_base;
    uint32_t staging_size;
    uint8_t resp[12];

    if (payload_length != 8U) {
        send_nack(CMD_LOAD_MODEL_BEGIN, sequence, ERR_PAYLOAD_FORMAT);
        return;
    }

    total_length = rd_u32(&payload[0]);
    expected_crc = rd_u32(&payload[4]);

    /* CONTRACT 1: the staging window comes from the linker, not a #define. */
    staging_base = sym_u32(__runner_staging_start__);
    staging_size = (uint32_t)(__runner_staging_end__ - __runner_staging_start__);

    if (total_length == 0U || total_length > staging_size) {
        send_nack(CMD_LOAD_MODEL_BEGIN, sequence, ERR_RANGE);
        return;
    }

    model_total_length = total_length;
    model_expected_crc = expected_crc;
    model_bytes_staged = 0;
    model_computed_crc = 0;
    last_chunk_valid   = 0;
    runner_state       = ST_MODEL_LOADING;

    wr_u32(&resp[0], total_length);
    wr_u32(&resp[4], staging_base);
    wr_u32(&resp[8], staging_size);
    send_ack(CMD_LOAD_MODEL_BEGIN, sequence, resp, sizeof(resp));
}

static void handle_load_model_chunk(uint32_t sequence, const uint8_t *payload,
                                    uint32_t payload_length)
{
    uint32_t offset;
    uint32_t data_length;
    const uint8_t *data;
    uint32_t data_crc;
    uint32_t staging_base;
    uint32_t staging_size;
    uint8_t resp[12];

    if (payload_length < 4U) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_PAYLOAD_FORMAT);
        return;
    }

    offset      = rd_u32(&payload[0]);
    data        = &payload[4];
    data_length = payload_length - 4U;

    if (data_length == 0U) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_PAYLOAD_FORMAT);
        return;
    }

    data_crc = crc32_buffer(data, data_length);

    if (last_chunk_valid && sequence == last_chunk_sequence) {
        if (offset == last_chunk_offset && data_length == last_chunk_length &&
            data_crc == last_chunk_data_crc) {
            wr_u32(&resp[0], offset);
            wr_u32(&resp[4], data_length);
            wr_u32(&resp[8], model_bytes_staged);
            send_ack(CMD_LOAD_MODEL_CHUNK, sequence, resp, sizeof(resp));
            return;
        }
        sequence_error_count++;
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_CHUNK_MISMATCH);
        return;
    }

    staging_base = sym_u32(__runner_staging_start__);
    staging_size = (uint32_t)(__runner_staging_end__ - __runner_staging_start__);

    if (!range_inside(offset, data_length, 0U, model_total_length)) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_RANGE);
        return;
    }
    if (!range_inside(staging_base + offset, data_length, staging_base,
                      staging_base + staging_size)) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_RANGE);
        return;
    }

    memcpy((void *)(uintptr_t)(staging_base + offset), data, data_length);

    model_bytes_staged += data_length;
    last_chunk_valid    = 1;
    last_chunk_sequence = sequence;
    last_chunk_offset   = offset;
    last_chunk_length   = data_length;
    last_chunk_data_crc = data_crc;

    wr_u32(&resp[0], offset);
    wr_u32(&resp[4], data_length);
    wr_u32(&resp[8], model_bytes_staged);
    send_ack(CMD_LOAD_MODEL_CHUNK, sequence, resp, sizeof(resp));
}

static void handle_load_model_end(uint32_t sequence)
{
    uint8_t resp[12];

    model_computed_crc = crc32_buffer(
        (const void *)(uintptr_t)sym_u32(__runner_staging_start__),
        model_total_length);

    wr_u32(&resp[0], model_computed_crc);
    wr_u32(&resp[4], model_expected_crc);
    wr_u32(&resp[8], model_total_length);

    if (model_computed_crc != model_expected_crc) {
        send_nack(CMD_LOAD_MODEL_END, sequence, ERR_MODEL_CRC);
        return;
    }

    runner_state = ST_MODEL_READY;
    send_ack(CMD_LOAD_MODEL_END, sequence, resp, sizeof(resp));
}

static void handle_load_input(uint32_t sequence, uint32_t payload_length)
{
    uint8_t resp[4];

    input_length = payload_length;
    runner_state = ST_INPUT_READY;

    wr_u32(&resp[0], payload_length);
    send_ack(CMD_LOAD_INPUT, sequence, resp, sizeof(resp));
}

static void handle_get_result(uint32_t sequence, const uint8_t *payload,
                              uint32_t payload_length)
{
    uint32_t region_base;
    uint32_t region_len;
    uint32_t requested_sequence;
    uint32_t lo;
    uint32_t hi;
    uint8_t resp[16];

    /* ---- MEASURE-ONLY: ONE accepted request form. -------------------------
     *   12 bytes: base(u32), len(u32), expected_run_sequence(u32)
     *
     * The 8-byte form (base, len) that RUNNER_V1_FUNCTIONAL still accepts is
     * REJECTED here. ERR_LENGTH (0x0003) is the chosen error: the request is
     * the wrong length for the only form this image has, and that is exactly
     * what ERR_LENGTH already means everywhere else in this protocol. A new
     * error code was deliberately NOT minted -- it would add wire surface to
     * say something the existing code already says precisely.
     *
     * WHY THE LOOSE FORM IS GONE, not just discouraged: an 8-byte request
     * cannot state which run it is asking about, so the firmware had no choice
     * but to answer without checking. Every other gate below is about whether
     * the latched result is trustworthy; only this one is about whether it is
     * the result the HOST means. Keeping an opt-in that silently skips it left
     * the strongest guarantee in the protocol at the host's discretion. In a
     * separate MEASURE image there is no compatibility reason to allow that.
     *
     * NOTE FOR THE HOST: this returns ERR_LENGTH, NOT ERR_PAYLOAD_FORMAT. The
     * previous code answered ERR_PAYLOAD_FORMAT for any length that was
     * neither 8 nor 12. A host that sends 8 bytes now gets ERR_LENGTH, and a
     * host that sees ERR_LENGTH from GET_RESULT is talking to a MEASURE image
     * with an obsolete request builder. */
    if (payload_length != 12U) {
        send_nack(CMD_GET_RESULT, sequence, ERR_LENGTH);
        return;
    }

    requested_sequence = rd_u32(&payload[8]);

    /* ---- MANDATORY freshness gate. Refuse BEFORE touching the region. -----
     * ALL five conditions must hold. Any failure returns ERR_RESULT_NOT_VALID
     * with NO payload and NO read of the result region -- the region is not
     * even addressed, let alone CRC'd, so there is no path by which a refused
     * request can leak a previous run's bytes.
     *
     * They are separate `if`s rather than one expression so that each reason
     * stands on its own and cannot be weakened by an edit to another. */

    /* 1. A run must have COMPLETED. Cleared at the top of every handle_run, so
     *    a run that dies partway leaves this false. */
    if (!last_run_completed) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RESULT_NOT_VALID);
        return;
    }
    /* 2. It must be the run the host is asking about. Compared against
     *    last_completed_sequence, NOT last_run_sequence: the latter is stamped
     *    at the start of a run and would match a run that never finished. */
    if (requested_sequence != last_completed_sequence) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RESULT_NOT_VALID);
        return;
    }
    /* 3. It must have succeeded. Read from the live variable, not from
     *    RUN_VALID_RUN_RC_OK, so a future edit to the flag logic cannot
     *    quietly weaken the requirement. */
    if (run_rc != 0) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RESULT_NOT_VALID);
        return;
    }
    /* 4. The required valid_flags mask (0x0F) must be satisfied.
     *    RUN_VALID_FULL_OUTPUT_EXPECTED_CRC_MATCH (0x10) is NOT in the mask
     *    and is NOT consulted here -- see its definition. */
    if ((last_valid_flags & RUN_VALID_REQUIRED_MASK) != RUN_VALID_REQUIRED_MASK) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RESULT_NOT_VALID);
        return;
    }
    /* 5. The poison must actually have been overwritten. This is the one that
     *    catches a skipped NPU: nothing wrote the region, so it still holds
     *    what handle_run() poisoned it with. Stated explicitly as well as via
     *    RUN_VALID_OUTPUT_CHANGED in the mask above, for the same reason as
     *    (3). */
    if (last_output_crc == last_poison_crc) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RESULT_NOT_VALID);
        return;
    }

    region_base = rd_u32(&payload[0]);
    region_len  = rd_u32(&payload[4]);

    /* Bounds identical to the frozen build: the whole .sec_noinit section. */
    lo = (uint32_t)(uintptr_t)__sec_noinit_start;
    hi = (uint32_t)(uintptr_t)__sec_noinit_end;

    if (!range_inside(region_base, region_len, lo, hi)) {
        send_nack(CMD_GET_RESULT, sequence, ERR_RANGE);
        return;
    }

    wr_u32(&resp[0], (uint32_t)run_rc);
    wr_u32(&resp[4], region_base);
    wr_u32(&resp[8], region_len);
    wr_u32(&resp[12],
           crc32_buffer((const void *)(uintptr_t)region_base, region_len));

    send_ack(CMD_GET_RESULT, sequence, resp, sizeof(resp));
}

static void handle_get_measurement(uint32_t sequence)
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
static void handle_set_instrumentation_mode(uint32_t sequence,
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

    if (mode != INSTRUMENTATION_OFF && mode != INSTRUMENTATION_END_ONLY) {
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
    if (count != 0U) {
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

static void handle_reset_runner(uint32_t sequence)
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

#ifdef RUNNER_TEST_ONLY_HOOKS
/* TEST-ONLY handler for CMD_TEST_SKIP_NEXT_NPU (0x7E). Arms a ONE-SHOT flag;
 * the next RUN skips apU85Conv_TEST(), fails, and clears it. See
 * run_fixed_inference() for what that proves and why.
 *
 * Request payload: 0 bytes. Anything else -> ERR_LENGTH.
 * ACK payload    : 4 bytes, the armed flag value (always 1).
 *
 * noinline is load-bearing, exactly as it is on run_fixed_inference() and
 * dispatch(): check_measure_symbols.py proves a NORMAL build cannot reach this
 * function by looking it up BY NAME in the linked ELF. If the compiler inlined
 * it away the gate would have nothing to find, and a gate that silently
 * verifies nothing is worse than no gate. Keeping it a real symbol is what
 * makes the negative control meaningful. */
__attribute__((noinline))
static void handle_test_skip_next_npu(uint32_t sequence, uint32_t payload_length)
{
    uint8_t resp[4];

    if (payload_length != 0U) {
        send_nack(CMD_TEST_SKIP_NEXT_NPU, sequence, ERR_LENGTH);
        return;
    }

    test_skip_next_npu_armed = 1U;
    /* Second honest reference to the marker, so it survives --gc-sections even
     * if run_fixed_inference()'s store is ever restructured. */
    runner_inject_test_skip_next_marker = 0x534E5850U;

    wr_u32(&resp[0], 1U);
    send_ack(CMD_TEST_SKIP_NEXT_NPU, sequence, resp, sizeof(resp));
}
#endif

/* noinline is load-bearing: check_measure_symbols.py uses dispatch() as the
 * ROOT for the test-only-hook reachability gate, and locates it by name in the
 * linked ELF. If GCC inlined it into parse_one_frame() the root would vanish
 * and the gate could no longer prove that handle_test_skip_next_npu is
 * unreachable. The checker fails closed on a missing root, so this attribute
 * is what keeps a normal build green for the right reason. */
__attribute__((noinline))
static void dispatch(uint8_t command, uint32_t sequence, const uint8_t *payload,
                     uint32_t payload_length)
{
    uint8_t status[STATUS_PAYLOAD_SIZE];
    uint8_t caps[CAP_PAYLOAD_SIZE];

    switch (command) {
    case CMD_PING:
    case CMD_GET_STATE:
        build_status(status);
        send_ack(command, sequence, status, sizeof(status));
        break;
    case CMD_GET_CAPABILITIES:
        build_capabilities(caps);
        send_ack(command, sequence, caps, sizeof(caps));
        break;
    case CMD_GET_MEASUREMENT:
        /* DIAG IMAGE: the production measurement path answers UNSUPPORTED so
         * nothing this image returns can be read as performance data. */
        send_nack(command, sequence, ERR_UNSUPPORTED);
        break;
    case CMD_LOAD_MODEL_BEGIN:
        handle_load_model_begin(sequence, payload, payload_length);
        break;
    case CMD_LOAD_MODEL_CHUNK:
        handle_load_model_chunk(sequence, payload, payload_length);
        break;
    case CMD_LOAD_MODEL_END:
        handle_load_model_end(sequence);
        break;
    case CMD_LOAD_INPUT:
        handle_load_input(sequence, payload_length);
        break;
    case CMD_RUN:
        /* DIAG IMAGE: CMD_RUN_PMU_DIAG is the only run path. */
        send_nack(command, sequence, ERR_UNSUPPORTED);
        break;
    case CMD_RUN_PMU_DIAG:
        handle_run_pmu_diag(sequence);
        break;
    case CMD_GET_PMU_DIAG_RESULT:
        handle_get_pmu_diag_result(sequence);
        break;
    case CMD_GET_RESULT:
        /* DIAG IMAGE: no production result presentation. The drift guard is
         * the diag record's poison/OUTPUT_CHANGED + result_region_crc. */
        send_nack(command, sequence, ERR_UNSUPPORTED);
        break;
    case CMD_RESET_RUNNER:
        handle_reset_runner(sequence);
        break;
    case CMD_SET_INSTRUMENTATION_MODE:
        /* DIAG IMAGE: instrumentation configuration is compile-time here. */
        send_nack(command, sequence, ERR_UNSUPPORTED);
        break;
#ifdef RUNNER_TEST_ONLY_HOOKS
    case CMD_TEST_SKIP_NEXT_NPU:
        handle_test_skip_next_npu(sequence, payload_length);
        break;
#endif
    default:
        send_nack(command, sequence, ERR_BAD_COMMAND);
        break;
    }
}

/* ------------------------------------------------------------------------ */
/* Frame parser -- byte-for-byte the frozen v1 parser                        */
/* ------------------------------------------------------------------------ */

static uint8_t rx_payload[RUNNER_MAX_PAYLOAD];

static void sync_to_magic(void)
{
    static const uint8_t magic[4] = {0x4E, 0x55, 0x52, 0x31};
    uint32_t matched = 0;

    while (matched < 4U) {
        uint8_t byte = get_raw();

        if (byte == magic[matched]) {
            matched++;
            continue;
        }

        bad_magic_count++;
        parser_resync_count++;
        matched = (byte == magic[0]) ? 1U : 0U;
    }
}

static void parse_one_frame(void)
{
    uint8_t header[RUNNER_HEADER_SIZE];
    uint8_t crc_bytes[4];
    uint8_t version;
    uint8_t command;
    uint32_t sequence;
    uint32_t payload_length;
    uint32_t crc_received;
    uint32_t crc_calculated;

    sync_to_magic();

    wr_u32(&header[0], RUNNER_MAGIC);
    for (uint32_t i = 4; i < RUNNER_HEADER_SIZE; i++) {
        header[i] = get_raw();
    }

    version        = header[4];
    command        = header[5];
    sequence       = rd_u32(&header[8]);
    payload_length = rd_u32(&header[12]);

    if (version != RUNNER_VERSION) {
        bad_version_count++;
        send_nack(command, sequence, ERR_BAD_VERSION);
        return;
    }

    if (payload_length > RUNNER_MAX_PAYLOAD) {
        length_error_count++;
        send_nack(command, sequence, ERR_LENGTH);
        return;
    }

    for (uint32_t i = 0; i < payload_length; i++) {
        rx_payload[i] = get_raw();
    }
    for (uint32_t i = 0; i < 4U; i++) {
        crc_bytes[i] = get_raw();
    }

    crc_received   = rd_u32(crc_bytes);
    crc_calculated = crc32_update(CRC32_INIT, header, RUNNER_HEADER_SIZE);
    if (payload_length != 0U) {
        crc_calculated = crc32_update(crc_calculated, rx_payload, payload_length);
    }
    crc_calculated = crc32_final(crc_calculated);

    if (crc_received != crc_calculated) {
        bad_crc_count++;
        send_nack(command, sequence, ERR_BAD_CRC);
        return;
    }

    if (command_bit(command) == CB_INVALID) {
        send_nack(command, sequence, ERR_BAD_COMMAND);
        return;
    }

    if (!command_allowed(runner_state, command)) {
        send_nack(command, sequence, ERR_STATE);
        return;
    }

    dispatch(command, sequence, rx_payload, payload_length);
}

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

#if RUNNER_BUILD_PROFILE == BUILD_PROFILE_MEASURE_WRAPPED

extern int __real_vprintf(const char *fmt, va_list ap);
extern int __real_puts(const char *s);
extern int __real_putchar(int c);
extern int __real__write(int fd, const void *buf, size_t n);
extern int __real_fputc(int c, void *stream);
extern void __real_serial_print(char *s);

int __wrap_printf(const char *fmt, ...)
{
    va_list ap;
    int rc;

    if (measurement_active) {
        suppressed_printf_calls++;
        return 0;
    }
    va_start(ap, fmt);
    rc = __real_vprintf(fmt, ap);
    va_end(ap);
    return rc;
}

int __wrap_vprintf(const char *fmt, va_list ap)
{
    if (measurement_active) {
        suppressed_printf_calls++;
        return 0;
    }
    return __real_vprintf(fmt, ap);
}

int __wrap_puts(const char *s)
{
    if (measurement_active) {
        suppressed_printf_calls++;
        return 0;
    }
    return __real_puts(s);
}

int __wrap_putchar(int c)
{
    if (measurement_active) {
        suppressed_printf_calls++;
        return 0;
    }
    return __real_putchar(c);
}

int __wrap__write(int fd, const void *buf, size_t n)
{
    if (measurement_active) {
        suppressed_write_calls++;
        return (int)n;
    }
    return __real__write(fd, buf, n);
}

int __wrap_fputc(int c, void *stream)
{
    if (measurement_active) {
        suppressed_printf_calls++;
        return 0;
    }
    return __real_fputc(c, stream);
}

void __wrap_serial_print(char *s)
{
    if (measurement_active) {
        suppressed_printf_calls++;
        return;
    }
    __real_serial_print(s);
}

#else /* BUILD_PROFILE_MEASURE_CLEAN */

/* noinline: the qualification gate requires this symbol to survive in the
 * final ELF, because an inlined wrapper has no call boundary to attest and
 * __builtin_return_address(0) would no longer name the vendor callsite. */
__attribute__((noinline))
int __wrap_printf(const char *fmt, ...)
{
#if defined(PMU_QUAL_SCHEMA_V8)
    /* The qualification branch, ahead of the pre-existing suppression path
     * and WITHOUT changing it. Exactly one printf in the whole image can take
     * it: the vendor's own "Testing CPM signals\n" between its STOP and its
     * terminal release. Every other printf -- before, during and after the
     * window -- falls through to the same counting behaviour it had before
     * H-PRINTF existed, so a failed match changes nothing for anyone else. */
    if (measurement_active && pmu_qual_is_target_format(fmt)) {
        /* Counted on EVERY arrival, armed or not. Detecting the target twice
         * has to be visible as a failure, and it only is if the second
         * arrival is counted -- so the count is outside the arm check and the
         * side effects are inside it. */
        pmu_qual_hook_detected_count++;
        if (pmu_qual_hook_armed) {
            pmu_qual_hook_entry_timestamp = read_timestamp();
            /* Thumb bit cleared so this compares against a link-time address.
             * The firmware RECORDS it and never knows what to expect: the
             * expected value lives only in the build manifest, and the host
             * compares the two. Hardcoding it here would let the image
             * approve itself. */
            pmu_qual_hook_callsite_lr =
                ((uint32_t)(uintptr_t)__builtin_return_address(0)) & ~1U;
            /* One-shot: the arm is consumed here, so a later arrival takes
             * the count-only path above. */
            pmu_qual_hook_armed        = 0U;
            pmu_qual_hook_arm_consumed = 1U;
#if defined(PMU_QUAL_MODE_Q1)
            pmu_qual_hook_fired_count++;
            pmu_qual_pre_release_hook();
#endif
        }
    }
#endif
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

#endif

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

/* ------------------------------------------------------------------------ */

#define HW32_REG(ADDRESS) (*((volatile uint32_t *)(ADDRESS)))

static void dbg_ena_sbrom(void)
{
    HW32_REG(0x5802125C) = 0xAAAAAAAA; /* Debug authentication enable */
    HW32_REG(0x500A0100) = 0x00005555; /* LCM_DCU_FORCE_DISABLE */
}

int main(void)
{
    runner_state = ST_BOOT;

    dbg_ena_sbrom();

    serial_init(&Driver_USART0, 115200);

    (void)timestamp_source_ready();

    runner_reset_context(); /* BOOT -> IDLE */

    for (;;) {
        parse_one_frame();
    }
}
