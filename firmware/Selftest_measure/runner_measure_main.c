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

#define U85_BASE_ADDRESS 0x50004000U
#define NPU_OFF_ID       0x00U
#define NPU_OFF_STATUS   0x04U
#define NPU_OFF_QREAD    0x18U
#define NPU_OFF_CONFIG   0x28U

static uint32_t npu_read(uint32_t offset)
{
    return REG32(U85_BASE_ADDRESS + offset);
}

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

/* unsolicited */
#define CMD_RUN_COMPLETE 0x31U

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
} measurement_record_t;

/* NOTE FOR THE HOST: this is 47, not the 42 it was, and not the "40" the
 * change request assumed. The pre-existing record already had 42 fields (the
 * struct and build_measurement_payload() agree at 42); five are appended here.
 * The ABI header's total_payload_words is the authority -- never hardcode. */
#define MEASUREMENT_FIELD_COUNT 47U
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
                  M(CB_GET_MEASUREMENT))

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
                           M(CB_RESET_RUNNER),
    /* ST_MODEL_LOADING */ M_ALWAYS | M(CB_LOAD_MODEL_CHUNK) |
                           M(CB_LOAD_MODEL_END) | M(CB_RESET_RUNNER),
    /* ST_MODEL_READY   */ M_ALWAYS | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER),
    /* ST_INPUT_READY   */ M_ALWAYS | M(CB_RUN) | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER) |
                           M_TEST_HOOKS,
    /* ST_RUNNING       */ 0U,
    /* ST_RESULT_READY  */ M_ALWAYS | M(CB_GET_RESULT) | M(CB_RUN) |
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

#define CAP_FIELD_COUNT 29U
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

    /* --- PMU: UNSUPPORTED THIS MILESTONE. All zero, by instruction. ---
     * The PMU registers are not even read: PMU work is a later milestone and
     * a zero here must be read as "not implemented", never as "measured 0". */
    put32(&c, 0U); /* PMU_TYPE                 -- unsupported */
    put32(&c, 0U); /* PMU_EVENT_COUNTER_COUNT  -- unsupported */
    put32(&c, 0U); /* PMU_COUNTER_WIDTH        -- unsupported */
    put32(&c, 0U); /* pmu_supported            -- 0 */

    /* --- clocks / boundary properties --- */
    put32(&c, SystemCoreClock);
    put32(&c, 0U); /* npu_clock_hz: no discoverable source, reported unknown */
    put32(&c, RUNNER_TX_DRAIN_US);
    put32(&c, RUNNER_TX_RESIDUAL_CHARS);

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
    measurement_record_t r;
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

    run_rc = run_fixed_inference();

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
}

/* ------------------------------------------------------------------------ */
/* Command handlers -- unchanged from runner_v1_main.c unless noted          */
/* ------------------------------------------------------------------------ */

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

static void handle_reset_runner(uint32_t sequence)
{
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
        handle_get_measurement(sequence);
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
        handle_run(sequence);
        break;
    case CMD_GET_RESULT:
        handle_get_result(sequence, payload, payload_length);
        break;
    case CMD_RESET_RUNNER:
        handle_reset_runner(sequence);
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

int __wrap_printf(const char *fmt, ...)
{
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
