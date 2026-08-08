/*
 * runner_v1_main.c -- host-driven "runner v1" firmware for the MPS4 FI101 board.
 *
 * Branched from the golden Selftest build (Makefile.gcc). Borrows from
 * Selftest/raw_rx_main.c ONLY the direct CMSDK UART register polling and the
 * diagnostic counters. GetLine(), the Selftest CLI parser and every
 * higher-level buffering layer are deliberately NOT used -- a proven
 * regression lives in that layer.
 *
 * ===========================================================================
 * WIRE FORMAT (UART0, 115200 8N1, little-endian throughout)
 * ===========================================================================
 *
 *   +--------------------- 16-byte header ---------------------+
 *   | magic          uint32  0x3152554E  ("NUR1" on the wire:  |
 *   |                                     4E 55 52 31)         |
 *   | version        uint8   1                                 |
 *   | command        uint8   see below                         |
 *   | flags          uint16  request: 0 / response: error code |
 *   | sequence       uint32  host-chosen, echoed in response    |
 *   | payload_length uint32  bytes of payload that follow      |
 *   +----------------------------------------------------------+
 *   | payload        payload_length bytes                      |
 *   +----------------------------------------------------------+
 *   | crc32          uint32                                    |
 *   +----------------------------------------------------------+
 *
 * CRC RANGE (host and firmware must agree exactly):
 *   CRC32 is computed over THE 16 HEADER BYTES FOLLOWED BY THE PAYLOAD BYTES,
 *   i.e. over exactly (16 + payload_length) bytes, and is transmitted as a
 *   trailing little-endian uint32 AFTER the payload. The CRC field itself is
 *   never part of the CRC input.
 *
 *   Standard reflected CRC-32, poly 0xEDB88320, init 0xFFFFFFFF, final XOR
 *   0xFFFFFFFF -- identical to Python's zlib.crc32(). A host implementation
 *   is therefore literally:
 *       zlib.crc32(header_bytes + payload_bytes) & 0xFFFFFFFF
 *
 * MAGIC CHOICE: "NUR1" has no proper prefix that is also a suffix, so the
 * byte-at-a-time resynchroniser below can restart on a mismatching byte by
 * testing that single byte against magic[0]. No backtracking is required.
 *
 * RESPONSES:
 *   ACK  : command = request_command | 0x80, flags = 0x0000
 *   NACK : command = 0xFF, flags = error code (never 0)
 *          NACK payload is always 4 bytes: { uint8 orig_command,
 *                                            uint8 state,
 *                                            uint16 reserved }
 *   Both echo the request's sequence. A frame whose magic never matched
 *   produces NO response at all (there is no sequence to echo); it only bumps
 *   bad_magic_count / parser_resync_count.
 *
 * HARD RULE: if payload_length exceeds RUNNER_MAX_PAYLOAD the NACK is sent
 * IMMEDIATELY, before any payload byte is read. The parser then returns to
 * magic hunting, because the announced length cannot be trusted to skip.
 *
 * ===========================================================================
 * KNOWN LIMITATIONS (v1, deliberate)
 * ===========================================================================
 *  - printf() inside the U85 test writes to THIS SAME UART (Serial/serial.c
 *    _write -> Driver_USART0). While RUN executes, human-readable test log
 *    lines are emitted on the wire between the RUN request and the RUN
 *    response. The host MUST resynchronise on the magic rather than assume
 *    the next bytes after a request are a frame header.
 *  - There is no receive timeout. A truncated frame blocks the parser until
 *    the remaining bytes arrive.
 *  - State RUNNING accepts no commands, and because the firmware is single
 *    threaded it is not even parsing while the test runs; bytes sent during
 *    RUN are lost and will show up as rx_overrun_count.
 */

#include <stdint.h>
#include <string.h>

#include "Driver_USART.h"
#include "serial.h"
#include "u85.h"

/* ------------------------------------------------------------------------ */
/* UART0 -- direct CMSDK APB register access, exactly as raw_rx_main.c       */
/* ------------------------------------------------------------------------ */

#define UART0_REGS ((volatile uint32_t *)0x59303000U)

#define REG_DATA    0U /* 0x000 */
#define REG_STATE   1U /* 0x004 */
#define REG_CTRL    2U /* 0x008 */
#define REG_BAUDDIV 4U /* 0x010 */

#define STATE_TXBF (1U << 0) /* TX buffer full */
#define STATE_RXBF (1U << 1) /* RX buffer full */
#define STATE_RXOR (1U << 3) /* RX overrun, write-1-to-clear */

extern ARM_DRIVER_USART Driver_USART0;

/* ------------------------------------------------------------------------ */
/* Protocol constants                                                        */
/* ------------------------------------------------------------------------ */

#define RUNNER_MAGIC   0x3152554EU /* "NUR1" little-endian: 4E 55 52 31 */
#define RUNNER_VERSION 1

#define RUNNER_HEADER_SIZE  16U
#define RUNNER_MAX_PAYLOAD  4096U

#define RESP_ACK_FLAG 0x80U
#define RESP_NACK_CMD 0xFFU

/* requests */
#define CMD_PING              0x01U
#define CMD_GET_STATE         0x02U
#define CMD_LOAD_MODEL_BEGIN  0x10U
#define CMD_LOAD_MODEL_CHUNK  0x11U
#define CMD_LOAD_MODEL_END    0x12U
#define CMD_LOAD_INPUT        0x20U
#define CMD_RUN               0x30U
#define CMD_GET_RESULT        0x40U
#define CMD_RESET_RUNNER      0x50U

/* error codes, carried in the NACK header's flags field */
#define ERR_NONE            0x0000U
#define ERR_BAD_VERSION     0x0001U
#define ERR_BAD_COMMAND     0x0002U
#define ERR_LENGTH          0x0003U
#define ERR_BAD_CRC         0x0004U
#define ERR_STATE           0x0005U
#define ERR_RANGE           0x0006U
#define ERR_CHUNK_MISMATCH  0x0007U
#define ERR_MODEL_CRC       0x0008U
#define ERR_PAYLOAD_FORMAT  0x0009U

/* model staging window in DDR */
#define STAGING_BASE 0x90120000U
#define STAGING_MAX  0x01000000U /* 16 MiB */

/* Linker-provided bounds of the NOLOAD .sec_noinit output section. Added to
 * LinkScripts/lnk.ld.S as symbols only -- they emit no bytes and move nothing.
 * GET_RESULT will only checksum regions inside these bounds. */
extern char __sec_noinit_start[];
extern char __sec_noinit_end[];

/* ------------------------------------------------------------------------ */
/* Diagnostic counters                                                       */
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
/* UART primitives                                                           */
/* ------------------------------------------------------------------------ */

static void put_raw(uint8_t byte)
{
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

/* Latch and clear STATE.RXOR exactly as raw_rx_main.c does. This is what lets
 * a future failure be split into "parser bug" vs "UART hardware". */
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
/* Little-endian accessors (the wire is LE regardless of struct packing)     */
/* ------------------------------------------------------------------------ */

static uint32_t rd_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint16_t rd_u16(const uint8_t *p)
{
    return (uint16_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8));
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

/* ========================================================================= */
/* STATE MACHINE -- defined before the command parser, on purpose            */
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

/* One bit per command, indexed by a dense command id. */
typedef enum {
    CB_PING = 0,
    CB_GET_STATE,
    CB_LOAD_MODEL_BEGIN,
    CB_LOAD_MODEL_CHUNK,
    CB_LOAD_MODEL_END,
    CB_LOAD_INPUT,
    CB_RUN,
    CB_GET_RESULT,
    CB_RESET_RUNNER,
    CB_INVALID
} cmd_bit_t;

static cmd_bit_t command_bit(uint8_t command)
{
    switch (command) {
    case CMD_PING:             return CB_PING;
    case CMD_GET_STATE:        return CB_GET_STATE;
    case CMD_LOAD_MODEL_BEGIN: return CB_LOAD_MODEL_BEGIN;
    case CMD_LOAD_MODEL_CHUNK: return CB_LOAD_MODEL_CHUNK;
    case CMD_LOAD_MODEL_END:   return CB_LOAD_MODEL_END;
    case CMD_LOAD_INPUT:       return CB_LOAD_INPUT;
    case CMD_RUN:              return CB_RUN;
    case CMD_GET_RESULT:       return CB_GET_RESULT;
    case CMD_RESET_RUNNER:     return CB_RESET_RUNNER;
    default:                   return CB_INVALID;
    }
}

#define M(bit) (1U << (bit))

/* Exactly the acceptance table from the specification. */
static const uint32_t state_accepts[ST_COUNT] = {
    /* ST_BOOT          */ 0U,
    /* ST_IDLE          */ M(CB_PING) | M(CB_GET_STATE) | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER),
    /* ST_MODEL_LOADING */ M(CB_PING) | M(CB_GET_STATE) | M(CB_LOAD_MODEL_CHUNK) |
                           M(CB_LOAD_MODEL_END) | M(CB_RESET_RUNNER),
    /* ST_MODEL_READY   */ M(CB_PING) | M(CB_GET_STATE) | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER),
    /* ST_INPUT_READY   */ M(CB_PING) | M(CB_GET_STATE) | M(CB_RUN) |
                           M(CB_LOAD_INPUT) | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER),
    /* ST_RUNNING       */ 0U,
    /* ST_RESULT_READY  */ M(CB_PING) | M(CB_GET_STATE) | M(CB_GET_RESULT) |
                           M(CB_RUN) | M(CB_LOAD_INPUT) | M(CB_RESET_RUNNER)};

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
static int      run_valid;

/* Stop-and-wait retransmission bookkeeping (last ACKed chunk). */
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
    run_valid           = 0;
    last_chunk_valid    = 0;
    last_chunk_sequence = 0;
    last_chunk_offset   = 0;
    last_chunk_length   = 0;
    last_chunk_data_crc = 0;
    runner_state        = ST_IDLE;
}

/* Overflow-safe containment test: is [base, base+len) inside [lo, hi)?
 * base + len is never evaluated, so nothing can wrap. */
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
/* Frame transmission                                                        */
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
/* Status payload (PING / GET_STATE): 40 bytes, little-endian                */
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
/* Phase 1 execution: the EXISTING U85 convolution test, nothing dynamic.    */
/* Replicates Selftest/main.c u85_convolution_test_wrapper() exactly.        */
/* ------------------------------------------------------------------------ */

static int32_t run_fixed_inference(void)
{
    struct u85_test_data_t d = {.name = "U85 Convolution test"};
    struct u85_test_meta_data_t m = {.u85_test_data = &d, .num_tests = 1};

    return (int32_t)apU85Conv_TEST(&m);
}

/* ------------------------------------------------------------------------ */
/* Command handlers                                                          */
/* ------------------------------------------------------------------------ */

static void handle_load_model_begin(uint32_t sequence, const uint8_t *payload,
                                    uint32_t payload_length)
{
    uint32_t total_length;
    uint32_t expected_crc;
    uint8_t resp[12];

    if (payload_length != 8U) {
        send_nack(CMD_LOAD_MODEL_BEGIN, sequence, ERR_PAYLOAD_FORMAT);
        return;
    }

    total_length = rd_u32(&payload[0]);
    expected_crc = rd_u32(&payload[4]);

    if (total_length == 0U || total_length > STAGING_MAX) {
        send_nack(CMD_LOAD_MODEL_BEGIN, sequence, ERR_RANGE);
        return;
    }

    model_total_length  = total_length;
    model_expected_crc  = expected_crc;
    model_bytes_staged  = 0;
    model_computed_crc  = 0;
    last_chunk_valid    = 0;
    runner_state        = ST_MODEL_LOADING;

    wr_u32(&resp[0], total_length);
    wr_u32(&resp[4], STAGING_BASE);
    wr_u32(&resp[8], STAGING_MAX);
    send_ack(CMD_LOAD_MODEL_BEGIN, sequence, resp, sizeof(resp));
}

static void handle_load_model_chunk(uint32_t sequence, const uint8_t *payload,
                                    uint32_t payload_length)
{
    uint32_t offset;
    uint32_t data_length;
    const uint8_t *data;
    uint32_t data_crc;
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

    /* Retransmission rule: a duplicate with the SAME sequence, offset and data
     * CRC is ACKed again without rewriting (idempotent). A duplicate with the
     * same sequence but different content is an error. */
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

    /* offset+data_length must sit inside both the declared model and the
     * 16 MiB staging window. Both tests are overflow-safe. */
    if (!range_inside(offset, data_length, 0U, model_total_length)) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_RANGE);
        return;
    }
    if (!range_inside(STAGING_BASE + offset, data_length, STAGING_BASE,
                      STAGING_BASE + STAGING_MAX)) {
        send_nack(CMD_LOAD_MODEL_CHUNK, sequence, ERR_RANGE);
        return;
    }

    memcpy((void *)(uintptr_t)(STAGING_BASE + offset), data, data_length);

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

    model_computed_crc =
        crc32_buffer((const void *)(uintptr_t)STAGING_BASE, model_total_length);

    wr_u32(&resp[0], model_computed_crc);
    wr_u32(&resp[4], model_expected_crc);
    wr_u32(&resp[8], model_total_length);

    if (model_computed_crc != model_expected_crc) {
        send_nack(CMD_LOAD_MODEL_END, sequence, ERR_MODEL_CRC);
        return;
    }

    /* Stage and verify only. The staged blob is deliberately NOT bound to any
     * NPU base pointer in this phase. */
    runner_state = ST_MODEL_READY;
    send_ack(CMD_LOAD_MODEL_END, sequence, resp, sizeof(resp));
}

static void handle_load_input(uint32_t sequence, uint32_t payload_length)
{
    uint8_t resp[4];

    /* Phase 1 runs a FIXED inference whose input is the built-in test3 stream.
     * LOAD_INPUT therefore only advances the state machine; the payload is
     * accepted and its length reported, but it is not bound to the NPU. */
    input_length = payload_length;
    runner_state = ST_INPUT_READY;

    wr_u32(&resp[0], payload_length);
    send_ack(CMD_LOAD_INPUT, sequence, resp, sizeof(resp));
}

static void handle_run(uint32_t sequence)
{
    uint8_t resp[4];

    runner_state = ST_RUNNING;
    run_rc       = run_fixed_inference();
    run_valid    = 1;
    runner_state = ST_RESULT_READY;

    wr_u32(&resp[0], (uint32_t)run_rc);
    send_ack(CMD_RUN, sequence, resp, sizeof(resp));
}

static void handle_get_result(uint32_t sequence, const uint8_t *payload,
                              uint32_t payload_length)
{
    uint32_t region_base;
    uint32_t region_len;
    uint32_t lo;
    uint32_t hi;
    uint8_t resp[16];

    if (payload_length != 8U) {
        send_nack(CMD_GET_RESULT, sequence, ERR_PAYLOAD_FORMAT);
        return;
    }

    region_base = rd_u32(&payload[0]);
    region_len  = rd_u32(&payload[4]);

    lo = (uint32_t)(uintptr_t)__sec_noinit_start;
    hi = (uint32_t)(uintptr_t)__sec_noinit_end;

    /* The host supplies the address from the map of THE BUILD UNDER TEST.
     * Firmware refuses anything outside .sec_noinit. Overflow-safe. */
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

static void handle_reset_runner(uint32_t sequence)
{
    /* Returns to IDLE and clears staging/model/input/result state WITHOUT
     * rebooting the board. The staged DDR bytes are intentionally not wiped;
     * only the bookkeeping that makes them reachable is cleared. */
    runner_reset_context();
    send_ack(CMD_RESET_RUNNER, sequence, (void *)0, 0);
}

static void dispatch(uint8_t command, uint32_t sequence, const uint8_t *payload,
                     uint32_t payload_length)
{
    uint8_t status[STATUS_PAYLOAD_SIZE];

    switch (command) {
    case CMD_PING:
    case CMD_GET_STATE:
        build_status(status);
        send_ack(command, sequence, status, sizeof(status));
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
    default:
        send_nack(command, sequence, ERR_BAD_COMMAND);
        break;
    }
}

/* ------------------------------------------------------------------------ */
/* Frame parser                                                              */
/* ------------------------------------------------------------------------ */

static uint8_t rx_payload[RUNNER_MAX_PAYLOAD];

/* Hunt for the 4 magic bytes. "NUR1" has no self-overlap, so a mismatching
 * byte only needs to be retested against magic[0]. */
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

        /* This byte is not the one we wanted: the candidate frame is junk. */
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
        return; /* payload cannot be trusted -> resynchronise */
    }

    /* HARD RULE: over-long payload is NACKed immediately, without waiting to
     * receive the payload. */
    if (payload_length > RUNNER_MAX_PAYLOAD) {
        length_error_count++;
        send_nack(command, sequence, ERR_LENGTH);
        return; /* announced length is untrustworthy -> resynchronise */
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

#define HW32_REG(ADDRESS) (*((volatile uint32_t *)(ADDRESS)))

/* Copied verbatim from Selftest/main.c: the U85 convolution test is only ever
 * known to pass in an environment where this has run. */
static void dbg_ena_sbrom(void)
{
    HW32_REG(0x5802125C) = 0xAAAAAAAA; /* Debug authentication enable */
    HW32_REG(0x500A0100) = 0x00005555; /* LCM_DCU_FORCE_DISABLE */
}

int main(void)
{
    runner_state = ST_BOOT;

    dbg_ena_sbrom();

    /* Baud rate and TX/RX enable through the normal driver, exactly as
     * raw_rx_main.c does; everything after this touches registers directly. */
    serial_init(&Driver_USART0, 115200);

    runner_reset_context(); /* BOOT -> IDLE */

    for (;;) {
        parse_one_frame();
    }
}
