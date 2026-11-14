/* Driver runner core (runner.h): request handling and the measured RUN. */
#include "runner.h"

#include <string.h>

#include "placement.h"
#include "pmu_session.h"
#include "probe.h"
#include "record.h"
#include "trace.h"
#include "workload.h"

static const runner_ports_t *P;
static frame_io_t io;                 /* the port's io, wrapped to count traffic */
static const frame_io_t *raw_io;
static uint32_t build_id;
static runner_state_t state = ST_BOOT;
static frame_t req;
static frame_errors_t ferr;
static uint32_t rx_bytes, tx_bytes, sequence_errors;

static uint32_t total_len, expected_crc, staged, load_status;
static drwl_t wl;
static uintptr_t arena_base;
static pmu_config_t pmu_cfg;
static uint32_t instr_mode, event_set_id, config_seq, wait_mode = WAIT_WFE, trace_word = TRACE_OFF, run_seq;

static int count_getc(uint8_t *b) { int r = raw_io->getc(b); rx_bytes += (uint32_t)r; return r; }
static void count_putc(uint8_t b) { tx_bytes++; raw_io->putc(b); }

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void wr32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static void ack(const void *payload, uint32_t len)
{
    frame_send(&io, (uint8_t)(req.command | FRAME_ACK_FLAG), 0U, req.sequence, payload, len);
}

static void nack(uint16_t error, uint32_t detail)
{
    uint8_t p[8] = {req.command, (uint8_t)state, 0U, 0U};
    wr32(p + 4, detail);
    frame_send(&io, FRAME_NACK_CMD, error, req.sequence, p, sizeof p);
}

static int known(uint8_t cmd)
{
    return cmd == CMD_PING || cmd == CMD_GET_STATE || cmd == CMD_GET_CAPABILITIES || cmd == CMD_SET_INSTRUMENTATION_MODE
           || cmd == CMD_SET_RUN_OPTIONS || cmd == CMD_LOAD_MODEL_BEGIN || cmd == CMD_LOAD_MODEL_CHUNK
           || cmd == CMD_LOAD_MODEL_END || cmd == CMD_LOAD_INPUT || cmd == CMD_RUN || cmd == CMD_RESET_RUNNER
           || cmd == CMD_GET_TRACE || cmd == CMD_GET_OUTPUT;
}

/* Which requests each state accepts (the legacy runner's table, plus SET_RUN_OPTIONS where SET_MODE is accepted). */
static int allowed(uint8_t cmd)
{
    const int always = cmd == CMD_PING || cmd == CMD_GET_STATE || cmd == CMD_GET_CAPABILITIES;
    const int config = cmd == CMD_SET_INSTRUMENTATION_MODE || cmd == CMD_SET_RUN_OPTIONS;
    switch (state) {
    case ST_IDLE:          return always || config || cmd == CMD_LOAD_MODEL_BEGIN || cmd == CMD_RESET_RUNNER;
    case ST_MODEL_LOADING: return always || cmd == CMD_LOAD_MODEL_CHUNK || cmd == CMD_LOAD_MODEL_END
                                  || cmd == CMD_RESET_RUNNER;
    case ST_MODEL_READY:   return always || config || cmd == CMD_LOAD_INPUT || cmd == CMD_LOAD_MODEL_BEGIN
                                  || cmd == CMD_RESET_RUNNER;
    case ST_INPUT_READY:   return always || config || cmd == CMD_RUN || cmd == CMD_LOAD_INPUT
                                  || cmd == CMD_LOAD_MODEL_BEGIN || cmd == CMD_RESET_RUNNER;
    case ST_RESULT_READY:  return always || config || cmd == CMD_RUN || cmd == CMD_LOAD_INPUT
                                  || cmd == CMD_LOAD_MODEL_BEGIN || cmd == CMD_RESET_RUNNER || cmd == CMD_GET_TRACE
                                  || cmd == CMD_GET_OUTPUT;
    default:               return 0;
    }
}

static void status_payload(void)
{
    uint8_t p[40] = {(uint8_t)state, FRAME_VERSION};
    const uint32_t v[9] = {rx_bytes, tx_bytes, P->rx_overruns(), ferr.bad_magic, ferr.bad_version, ferr.bad_crc,
                           ferr.length_error, sequence_errors, ferr.resync};
    for (uint32_t i = 0; i < 9U; i++) { wr32(p + 4U + 4U * i, v[i]); }
    ack(p, sizeof p);
}

static void capabilities(void)
{
    static uint8_t out[512];
    ack(out, P->capabilities(out, sizeof out, load_status));
}

static void set_mode(void)
{
    uint8_t out[16];
    pmu_config_t c = {0};
    uint32_t mode, count;
    if (req.length != 12U + 4U * PMU_SLOTS) { nack(ERR_LENGTH, 0U); return; }
    mode = rd32(req.payload);
    count = rd32(req.payload + 8);
    if ((mode != INSTRUMENTATION_EVENTS && mode != INSTRUMENTATION_OFF) || (mode == INSTRUMENTATION_OFF && count != 0U)) {
        nack(ERR_RANGE, mode); return;
    }
    c.count = count;   /* pmu_session_configure() owns the slot limit and the id range */
    for (uint32_t i = 0; i < count && i < PMU_SLOTS; i++) { c.codes[i] = rd32(req.payload + 12U + 4U * i); }
    c.pmccntr_cfg = pmu_cfg.pmccntr_cfg;
    if (pmu_session_configure(&c) != 0U) { nack(ERR_RANGE, 1U); return; }
    pmu_cfg = c;
    instr_mode = mode;
    event_set_id = rd32(req.payload + 4);
    config_seq++;
    wr32(out, mode); wr32(out + 4, mode); wr32(out + 8, count); wr32(out + 12, config_seq);
    ack(out, sizeof out);
}

/* Payload: wait mode, PMCCNTR_CFG, trace word (TRACE_OFF unless the wait mode is WAIT_TRACE). */
static void set_run_options(void)
{
    uint8_t out[12];
    pmu_config_t c = pmu_cfg;
    uint32_t w, tw;
    if (req.length != 12U) { nack(ERR_LENGTH, 0U); return; }
    w = rd32(req.payload);
    tw = rd32(req.payload + 8);
    if (w >= WAIT_MODES) { nack(ERR_RANGE, w); return; }
    if (trace_check(tw) != 0U) { nack(ERR_RANGE, 3U); return; }
    if ((w == WAIT_TRACE) != (tw != TRACE_OFF)) { nack(ERR_RANGE, 4U); return; }
    c.pmccntr_cfg = rd32(req.payload + 4);
    if (pmu_session_configure(&c) != 0U) { nack(ERR_RANGE, 2U); return; }
    pmu_cfg = c;
    wait_mode = w;
    trace_word = tw;
    wr32(out, wait_mode); wr32(out + 4, pmu_cfg.pmccntr_cfg); wr32(out + 8, trace_word);
    ack(out, sizeof out);
}

/* Payload: first word, word count; reply: up to TRACE_GET_MAX_WORDS words of the last RUN's trace buffer. */
static void get_trace(void)
{
    static uint32_t words[TRACE_GET_MAX_WORDS];
    static uint8_t out[TRACE_GET_MAX_WORDS * 4U];
    uint32_t n;
    if (req.length != 8U) { nack(ERR_LENGTH, 0U); return; }
    n = rd32(req.payload + 4);
    if (n > TRACE_GET_MAX_WORDS) { n = TRACE_GET_MAX_WORDS; }
    n = trace_words(rd32(req.payload), n, words);
    for (uint32_t i = 0; i < n; i++) { wr32(out + 4U * i, words[i]); }
    ack(out, 4U * n);
}

/* Payload: first byte, byte count over the output tensors one after another (model order). Count 0: reply the zlib CRC-32
 * of all of them and their total length; else up to OUTPUT_GET_MAX_BYTES bytes from first (clipped to the end). */
static void get_output(void)
{
    static uint8_t out[OUTPUT_GET_MAX_BYTES];
    uint32_t first, n, at = 0U, got = 0U, crc = 0xFFFFFFFFU;
    if (req.length != 8U) { nack(ERR_LENGTH, 0U); return; }
    first = rd32(req.payload);
    n = rd32(req.payload + 4);
    if (n > OUTPUT_GET_MAX_BYTES) { n = OUTPUT_GET_MAX_BYTES; }
    for (uint32_t i = 0; i < wl.n_out; i++) {
        uint8_t *o;
        uint32_t len;
        (void)P->model_io(1U, i, &o, &len);
        if (n == 0U) {
            crc = crc32_update(crc, o, len);
        } else {
            for (uint32_t k = 0; k < len && got < n; k++) {
                if (at + k >= first) { out[got++] = o[k]; }
            }
        }
        at += len;
    }
    if (n == 0U) {
        uint8_t r[8];
        wr32(r, crc ^ 0xFFFFFFFFU); wr32(r + 4, at);
        ack(r, sizeof r);
    } else {
        ack(out, got);
    }
}

static void load_begin(void)
{
    uint8_t out[12];
    if (req.length != 8U) { nack(ERR_LENGTH, 0U); return; }
    total_len = rd32(req.payload);
    expected_crc = rd32(req.payload + 4);
    if (total_len == 0U || total_len > P->staging_size) { nack(ERR_RANGE, total_len); state = ST_IDLE; return; }
    staged = 0U;
    load_status = LOAD_OK;
    state = ST_MODEL_LOADING;
    wr32(out, total_len); wr32(out + 4, (uint32_t)(uintptr_t)P->staging); wr32(out + 8, P->staging_size);
    ack(out, sizeof out);
}

static void load_chunk(void)
{
    uint8_t out[12];
    uint32_t off, n;
    if (req.length < 4U) { nack(ERR_LENGTH, 0U); return; }
    off = rd32(req.payload);
    n = req.length - 4U;
    if (off > staged || n > total_len - off) { nack(ERR_CHUNK_MISMATCH, off); return; }   /* append or re-send */
    memcpy(P->staging + off, req.payload + 4, n);
    if (off + n > staged) { staged = off + n; }
    wr32(out, staged); wr32(out + 4, total_len); wr32(out + 8, off);
    ack(out, sizeof out);
}

/* Load-time checks (never in the RUN): every output tensor filled with OFM_POISON, so an output the NPU did not write
 * cannot match its golden in the first RUN after the load; every IFM copied in and read back. */
#define OFM_POISON 0x5AU
static uint32_t prepare_io(void)
{
    for (uint32_t i = 0; i < wl.n_out; i++) {
        uint8_t *o;
        uint32_t len;
        (void)P->model_io(1U, i, &o, &len);
        memset(o, OFM_POISON, len);
    }
    for (uint32_t i = 0; i < wl.n_in; i++) {
        uint8_t *p;
        uint32_t len;
        (void)P->model_io(0U, i, &p, &len);
        memcpy(p, wl.in[i].ptr, len);
    }
    P->dcache_sync();
    for (uint32_t i = 0; i < wl.n_in; i++) {
        uint8_t *p;
        uint32_t len;
        (void)P->model_io(0U, i, &p, &len);
        if (memcmp(p, wl.in[i].ptr, len) != 0) { return LOAD_IFM_CHECK + i; }
    }
    return LOAD_OK;
}

/* The arena of the workload's placement (placement.h); 0 if it does not fit. */
static uintptr_t arena_of(uint32_t *status)
{
    uintptr_t ddr = drwl_arena_after(P->model_base, wl.model.len, P->arena_len, P->ddr_limit), free_base, limit;
    *status = LOAD_NO_ROOM;
    if (ddr == 0U || wl.placement == PLACEMENT_DDR) { return ddr; }
    *status = LOAD_SRAM_NO_ROOM;
    P->sram_window(&free_base, &limit);
    return placement_sram_arena(free_base, limit, P->model_base, ddr, P->arena_len);
}

/* Model in place and loaded; returns a LOAD_* status. */
static uint32_t place_and_load(void)
{
    uint32_t r, n_in, n_out;
    uintptr_t bad;
    placement_set(PLACEMENT_DDR);
    if ((r = drwl_parse(P->staging, total_len, &wl)) != 0U) { return LOAD_BAD_DRWL + r; }
    if ((arena_base = arena_of(&r)) == 0U) { return r; }
    if ((r = placement_mem_check(arena_base, P->arena_len, P->dcache_sync, &bad)) != 0U) { return LOAD_MEM_CHECK + r; }
    P->place_model(P->model_base, wl.model.ptr, wl.model.len);
    if ((r = P->model_load(P->model_base, wl.model.len, arena_base, P->arena_len)) != 0U) { return LOAD_MODEL_INIT + r; }
    P->model_counts(&n_in, &n_out);
    if (n_in != wl.n_in || n_out != wl.n_out) { return LOAD_IO_COUNT; }
    for (uint32_t k = 0; k < n_in + n_out; k++) {
        uint8_t *p;
        uint32_t len;
        const uint32_t output = k >= n_in, i = output ? k - n_in : k;
        if (P->model_io(output, i, &p, &len) != 0U || len != (output ? wl.out[i].len : wl.in[i].len)) {
            return LOAD_IO_SIZE + k;
        }
    }
    if ((r = prepare_io()) != LOAD_OK) { return r; }
    placement_set(wl.placement);
    return LOAD_OK;
}

static void load_end(void)
{
    uint8_t out[16];
    uint32_t crc;
    if (staged != total_len) { nack(ERR_CHUNK_MISMATCH, staged); return; }
    crc = crc32_of(P->staging, total_len);
    if (crc != expected_crc) { state = ST_IDLE; nack(ERR_MODEL_CRC, crc); return; }
    load_status = place_and_load();
    if (load_status != LOAD_OK) { state = ST_IDLE; nack(ERR_PAYLOAD_FORMAT, load_status); return; }
    state = ST_MODEL_READY;
    wr32(out, crc); wr32(out + 4, expected_crc); wr32(out + 8, total_len); wr32(out + 12, load_status);
    ack(out, sizeof out);
}

static void load_input(void)
{
    uint8_t out[4] = {0};
    state = ST_INPUT_READY;     /* the IFMs come with the workload; LOAD_INPUT only completes the state walk */
    ack(out, sizeof out);
}

/* OFM bytes against the goldens, as int8, in output order (the legacy runner's three numbers). */
static void compare_outputs(drv_record_t *r)
{
    uint32_t at = 0U;
    r->ofm_first = 0xFFFFFFFFU;
    for (uint32_t i = 0; i < wl.n_out; i++) {
        uint8_t *o;
        uint32_t len;
        (void)P->model_io(1U, i, &o, &len);
        for (uint32_t k = 0; k < len; k++, at++) {
            int32_t d = (int32_t)(int8_t)o[k] - (int32_t)(int8_t)wl.out[i].ptr[k];
            if (d != 0) {
                if (r->ofm_mismatch == 0U) { r->ofm_first = at; }
                r->ofm_mismatch++;
                if (d < 0) { d = -d; }
                if ((uint32_t)d > r->ofm_max_diff) { r->ofm_max_diff = (uint32_t)d; }
            }
        }
    }
}

static void fill_from_probe(drv_record_t *r, const probe_t *p)
{
    r->irq_count = p->irq_count; r->arm_count = p->arm_count; r->power_requests = p->power_requests;
    r->job_result = p->job_result; r->status_at_irq = p->status_at_irq; r->qread_at_irq = p->qread_at_irq;
    r->qsize = p->qsize; r->pmcr_at_arm = p->pmcr_at_arm; r->cnten_at_arm = p->cnten_at_arm;
    r->dwt_arm = p->dwt_arm; r->dwt_irq = p->dwt_irq;
    r->ccnt_irq_lo = (uint32_t)p->at_irq.ccnt; r->ccnt_irq_hi = (uint32_t)(p->at_irq.ccnt >> 32);
    r->ovf_irq = p->at_irq.ovf;
    r->ev_irq0 = p->at_irq.ev[0]; r->ev_irq1 = p->at_irq.ev[1]; r->ev_irq2 = p->at_irq.ev[2];
    r->ev_irq3 = p->at_irq.ev[3]; r->ev_irq4 = p->at_irq.ev[4]; r->ev_irq5 = p->at_irq.ev[5];
    r->ev_irq6 = p->at_irq.ev[6]; r->ev_irq7 = p->at_irq.ev[7];
    r->n_base = p->n_base;
    r->base0 = p->base[0]; r->base1 = p->base[1]; r->base2 = p->base[2]; r->base3 = p->base[3];
    r->base4 = p->base[4]; r->base5 = p->base[5]; r->base6 = p->base[6]; r->base7 = p->base[7];
    r->base_size0 = p->base_size[0]; r->base_size1 = p->base_size[1]; r->base_size2 = p->base_size[2];
    r->base_size3 = p->base_size[3]; r->base_size4 = p->base_size[4]; r->base_size5 = p->base_size[5];
    r->base_size6 = p->base_size[6]; r->base_size7 = p->base_size[7];
    r->regioncfg_irq = p->regioncfg_irq; r->qconfig_irq = p->qconfig_irq;
}

static void fill_config(drv_record_t *r)
{
    r->schema = RECORD_SCHEMA; r->build_id = build_id; r->instr_mode = instr_mode; r->event_set_id = event_set_id;
    r->event_count = pmu_cfg.count; r->config_seq = config_seq; r->wait_mode = wait_mode;
    r->pmccntr_cfg = pmu_cfg.pmccntr_cfg;
    r->event_code0 = pmu_cfg.codes[0]; r->event_code1 = pmu_cfg.codes[1]; r->event_code2 = pmu_cfg.codes[2];
    r->event_code3 = pmu_cfg.codes[3]; r->event_code4 = pmu_cfg.codes[4]; r->event_code5 = pmu_cfg.codes[5];
    r->event_code6 = pmu_cfg.codes[6]; r->event_code7 = pmu_cfg.codes[7];
    r->model_base = (uint32_t)P->model_base; r->model_len = wl.model.len;
    r->arena_base = (uint32_t)arena_base; r->arena_len = P->arena_len; r->placement = wl.placement;
}

static uint32_t flags_of(const drv_record_t *r)
{
    uint32_t f = REC_COMPLETED;
    if (r->invoke_ok) { f |= REC_INVOKE_OK; }
    if (r->arm_count == 1U) { f |= REC_ONE_ARM; }
    if (r->irq_count == 1U) { f |= REC_ONE_IRQ; }
    if ((r->ovf_irq & pmu_session_armed_mask()) == 0U) { f |= REC_NO_OVERFLOW; }
    if (r->ofm_mismatch == 0U && r->invoke_ok) { f |= REC_OUTPUT_MATCH; }
    if (r->irq_count != 0U && r->regioncfg_irq == placement_regioncfg(r->n_base, r->placement)
        && r->qconfig_irq == placement_config_select(-1, r->placement)) {
        f |= REC_REGIONCFG_MATCH;
    }
    return f;
}

static void run(void)
{
    static uint8_t out[RECORD_TOTAL_WORDS * 4U];
    drv_record_t r = {0};
    pmu_snapshot_t post;
    probe_t seen;
    ack(0, 0U);                                   /* ACK first, RUN_COMPLETE when done (the measure-v2 protocol) */
    state = ST_RUNNING;
    run_seq++;
    fill_config(&r);
    for (uint32_t i = 0; i < wl.n_in; i++) {
        uint8_t *p;
        uint32_t len;
        (void)P->model_io(0U, i, &p, &len);
        memcpy(p, wl.in[i].ptr, len);
    }
    r.dcache_on = P->dcache_on();
    probe_begin(wait_mode);
    trace_begin(trace_word, pmu_cfg.count);
    r.dwt_invoke = P->dwt();
    r.invoke_ok = P->invoke();
    r.dwt_return = P->dwt();
    pmu_session_snapshot(&post);
    memcpy(&seen, (const void *)&probe, sizeof seen);
    fill_from_probe(&r, &seen);
    {
        trace_stats_t t = trace_stats();
        r.trace_config = t.config; r.trace_words_per_sample = t.words_per_sample; r.samples = t.samples;
        r.sample_dropped = t.dropped; r.trace_polls = t.polls; r.trace_hook_calls = t.hook_calls;
        r.trace_words = t.words; r.trace_rejected = t.rejected; r.trace_unaccepted = t.unaccepted; r.trace_id = t.id;
    }
    r.ccnt_post_lo = (uint32_t)post.ccnt; r.ccnt_post_hi = (uint32_t)(post.ccnt >> 32); r.ovf_post = post.ovf;
    r.ev_post0 = post.ev[0]; r.ev_post1 = post.ev[1]; r.ev_post2 = post.ev[2]; r.ev_post3 = post.ev[3];
    r.ev_post4 = post.ev[4]; r.ev_post5 = post.ev[5]; r.ev_post6 = post.ev[6]; r.ev_post7 = post.ev[7];
    compare_outputs(&r);
    record_serialise(&r, run_seq, flags_of(&r), r.invoke_ok ? 0U : 1U, out);
    state = ST_RESULT_READY;
    frame_send(&io, CMD_RUN_COMPLETE, 0U, req.sequence, out, sizeof out);
}

static void reset_runner(void)
{
    total_len = staged = 0U;
    state = ST_IDLE;
    ack(0, 0U);
}

void runner_init(const runner_ports_t *ports, const frame_io_t *port_io, uint32_t id)
{
    P = ports;
    raw_io = port_io;
    io.getc = count_getc;
    io.putc = count_putc;
    build_id = id;
    state = ST_IDLE;
}

runner_state_t runner_state(void) { return state; }

int runner_poll(void)
{
    if (!frame_poll(&io, &req, &ferr)) { return 0; }
    if (!known(req.command)) { nack(ERR_BAD_COMMAND, 0U); return 1; }
    if (!allowed(req.command)) { nack(ERR_STATE, 0U); return 1; }
    switch (req.command) {
    case CMD_PING:
    case CMD_GET_STATE:                status_payload(); break;
    case CMD_GET_CAPABILITIES:         capabilities(); break;
    case CMD_SET_INSTRUMENTATION_MODE: set_mode(); break;
    case CMD_SET_RUN_OPTIONS:          set_run_options(); break;
    case CMD_LOAD_MODEL_BEGIN:         load_begin(); break;
    case CMD_LOAD_MODEL_CHUNK:         load_chunk(); break;
    case CMD_LOAD_MODEL_END:           load_end(); break;
    case CMD_LOAD_INPUT:               load_input(); break;
    case CMD_RUN:                      run(); break;
    case CMD_RESET_RUNNER:             reset_runner(); break;
    case CMD_GET_TRACE:                get_trace(); break;
    case CMD_GET_OUTPUT:               get_output(); break;
    default:                           nack(ERR_BAD_COMMAND, 0U); break;
    }
    return 1;
}
