/* Host protocol: UART, CRC-32, frames, state machine, model/input/result commands, dispatch, parser. */
#include "runner.h"

/* ------------------------------------------------------------------------ */
/* Diagnostic counters (unchanged set from v1)                               */
/* ------------------------------------------------------------------------ */

static uint32_t rx_bytes;
static uint32_t tx_bytes;
uint32_t rx_overrun_count;
static uint32_t bad_magic_count;
static uint32_t bad_version_count;
static uint32_t bad_crc_count;
static uint32_t length_error_count;
static uint32_t sequence_error_count;
static uint32_t parser_resync_count;

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


uint32_t crc32_update(uint32_t crc, const void *data, uint32_t len)
{
    const uint8_t *p = (const uint8_t *)data;

    for (uint32_t i = 0; i < len; i++) {
        crc ^= p[i];
        crc = (crc >> 4) ^ crc32_nibble_table[crc & 0x0FU];
        crc = (crc >> 4) ^ crc32_nibble_table[crc & 0x0FU];
    }
    return crc;
}

uint32_t crc32_final(uint32_t crc)
{
    return crc ^ 0xFFFFFFFFU;
}

uint32_t crc32_buffer(const void *data, uint32_t len)
{
    return crc32_final(crc32_update(CRC32_INIT, data, len));
}

/* ------------------------------------------------------------------------ */
/* Little-endian accessors                                                   */
/* ------------------------------------------------------------------------ */

uint32_t rd_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

void wr_u32(uint8_t *p, uint32_t v)
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



void put32(wcur_t *c, uint32_t v)
{
    wr_u32(c->base + c->used, v);
    c->used += 4U;
}

/* ========================================================================= */
/* STATE MACHINE                                                             */
/* ========================================================================= */


runner_state_t runner_state;

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
#define M_TEST_HOOKS 0U
#define M_EVENTS_MODEL M(CB_SET_INSTRUMENTATION_MODE)

static const uint32_t state_accepts[ST_COUNT] = {
    /* ST_BOOT          */ 0U,
    /* ST_IDLE          */ M_ALWAYS | M(CB_LOAD_MODEL_BEGIN) |
                           M(CB_RESET_RUNNER) |
                           M(CB_SET_INSTRUMENTATION_MODE),
    /* ST_MODEL_LOADING */ M_ALWAYS | M(CB_LOAD_MODEL_CHUNK) |
                           M(CB_LOAD_MODEL_END) | M(CB_RESET_RUNNER),
    /* ST_MODEL_READY   */ M_ALWAYS | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER),
    /* ST_INPUT_READY   */ M_ALWAYS | M(CB_RUN) | M(CB_LOAD_INPUT) |
                           M(CB_LOAD_MODEL_BEGIN) | M(CB_RESET_RUNNER) |
                           M_TEST_HOOKS | M_EVENTS_MODEL,
    /* ST_RUNNING       */ 0U,
    /* ST_RESULT_READY  */ M_ALWAYS | M(CB_GET_RESULT) | M(CB_RUN) |
                           M(CB_LOAD_INPUT) | M(CB_RESET_RUNNER) |
                           M_TEST_HOOKS | M_EVENTS_MODEL};

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

uint32_t model_total_length;
static uint32_t model_expected_crc;
static uint32_t model_bytes_staged;
static uint32_t model_computed_crc;
static uint32_t input_length;


static int      last_chunk_valid;
static uint32_t last_chunk_sequence;
static uint32_t last_chunk_offset;
static uint32_t last_chunk_length;
static uint32_t last_chunk_data_crc;

void runner_reset_context(void)
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

void send_frame(uint8_t command, uint16_t flags, uint32_t sequence,
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

void send_ack(uint8_t request_command, uint32_t sequence,
                     const void *payload, uint32_t payload_length)
{
    send_frame((uint8_t)(request_command | RESP_ACK_FLAG), ERR_NONE, sequence,
               payload, payload_length);
}

void send_nack(uint8_t request_command, uint32_t sequence, uint16_t error)
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
    case CMD_SET_INSTRUMENTATION_MODE:
        handle_set_instrumentation_mode(sequence, payload, payload_length);
        break;
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

void parse_one_frame(void)
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
