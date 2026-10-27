/*
 * runner/main.c -- the measurement runner (RUNNER_V1_MEASURE lineage, EVENTS mode, PMWL workload blobs).
 *
 * Modules: proto.c (host protocol), measure.c (one measured RUN), pmwl.c (workload blob), io_wrap.c
 * (logging wrappers and the vendor printf seams); common/ (NPU registers, PMU, timing adapters, timestamps).
 * History below: the protocol deltas against the original functional runner, still in force.
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

#include "runner.h"

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
