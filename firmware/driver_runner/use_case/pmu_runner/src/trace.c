/* QREAD trace (trace.h). */
#include "trace.h"

#include "npu_pmu_regs.h"
#include "pmu_session.h"

#define MAX_SAMPLE_WORDS (4U + (3U + PMU_SLOTS) * (1U + 2U * TRACE_MAX_ATTEMPTS))

typedef struct {
    uint32_t n, slots, attempts, rejected, unaccepted;
    uint32_t w[MAX_SAMPLE_WORDS];
} csample_t;

static volatile uint8_t *npu;
static uint32_t (*clock_now)(void);
static uint32_t buf[TRACE_BUFFER_WORDS];
static trace_stats_t st;
static uint32_t mode, interval, store_after, events, used, last_poll, last_store, last_qread;
static uint32_t job_qsize, job_qread, job_ev[PMU_SLOTS], held_valid, cur;
static csample_t smp[2];                         /* the current sample and the last one not stored, alternating */

#ifdef TRACE_SIM_READ
uint32_t TRACE_SIM_READ(uint32_t off);           /* host simulator only: a register file that can misbehave */
static uint32_t npu_word(uint32_t off) { return TRACE_SIM_READ(off); }
#else
static uint32_t npu_word(uint32_t off) { return *(volatile uint32_t *)(npu + off); }
#endif

static uint32_t checked(void) { return mode == TRACE_MODE_QREAD_CHECKED || mode == TRACE_MODE_QREAD_PMU_CHECKED; }

void trace_bind(volatile void *npu_base, uint32_t (*now)(void))
{
    npu = (volatile uint8_t *)npu_base;
    clock_now = now;
}

uint32_t trace_check(uint32_t word)
{
    uint32_t m = word & TRACE_MODE_MASK;
    if (word == TRACE_OFF) { return 0U; }
    if (word & ~TRACE_CONFIG_MASK) { return 1U; }
    if (m != TRACE_MODE_QREAD_ONLY && m != TRACE_MODE_QREAD_PMU && m != TRACE_MODE_QREAD_CHECKED
        && m != TRACE_MODE_QREAD_PMU_CHECKED) {
        return 2U;
    }
    return 0U;
}

void trace_begin(uint32_t word, uint32_t n_events)
{
    st = (trace_stats_t){0};
    st.config = word;
    used = 0U;
    held_valid = 0U;
    mode = (word == TRACE_OFF) ? 0U : (word & TRACE_MODE_MASK);
    interval = 1U << ((word >> TRACE_INTERVAL_SHIFT) & TRACE_FIELD_MASK);
    store_after = (word >> TRACE_STORE_SHIFT) & TRACE_FIELD_MASK;
    events = (mode == TRACE_MODE_QREAD_PMU || mode == TRACE_MODE_QREAD_PMU_CHECKED) ? n_events : 0U;
    if (checked()) {
        /* the sentinel: two reads of ID agree (a read returning its predecessor's data returns ID's own here) */
        uint32_t a = npu_word(NPU_OFF_ID), b = npu_word(NPU_OFF_ID);
        st.id = (a == b) ? b : npu_word(NPU_OFF_ID);
        st.words_per_sample = 4U + (3U + events) * 3U;   /* nominal: every slot accepted at the first read */
    } else {
        st.words_per_sample = (mode == 0U) ? 0U : TRACE_BASE_SAMPLE_WORDS + events;
    }
    last_qread = 0xFFFFFFFFU;
}

static void sample(int force)
{
    uint32_t w[TRACE_BASE_SAMPLE_WORDS + PMU_SLOTS];
    uint32_t ev[PMU_SLOTS];
    uint32_t k = 0U;
    w[k++] = clock_now();
    w[k++] = npu_word(NPU_OFF_QREAD);
    w[k++] = npu_word(NPU_OFF_STATUS);
    if (events != 0U) {
        (void)pmu_session_read_events(ev);
        for (uint32_t i = 0; i < events; i++) { w[k++] = ev[i]; }
    }
    w[k++] = npu_word(NPU_OFF_QREAD);
    w[k++] = clock_now();
    st.polls++;
    if (!force && store_after != 0U && w[k - 2U] == last_qread && w[0] - last_store < (1U << store_after)) {
        return;
    }
    if (used + k > TRACE_BUFFER_WORDS) { st.dropped++; return; }
    for (uint32_t i = 0; i < k; i++) { buf[used + i] = w[i]; }
    used += k;
    st.samples++;
    last_qread = w[k - 2U];
    last_store = w[0];
}

/* One checked slot: (ID, register) until an attempt is accepted or TRACE_MAX_ATTEMPTS were made; every attempt is
 * kept. lo/hi/align: the plausible range of the value. Returns the last value read. */
static uint32_t read_slot(csample_t *s, uint32_t off, uint32_t lo, uint32_t hi, uint32_t align)
{
    uint32_t d = s->n++, a = 0U, ok = 0U, v = 0U;
    while (a < TRACE_MAX_ATTEMPTS && ok == 0U) {
        uint32_t id = npu_word(NPU_OFF_ID);
        v = npu_word(off);
        s->w[s->n++] = id;
        s->w[s->n++] = v;
        a++;
        ok = (id == st.id && v != id && v >= lo && v <= hi && (v & align) == 0U) ? 1U : 0U;
    }
    s->w[d] = (ok << 20) | (a << 16) | off;
    s->slots++;
    s->attempts += a;
    s->rejected += a - ok;
    s->unaccepted += 1U - ok;
    return v;
}

static void store_checked(const csample_t *s)
{
    if (used + s->n > TRACE_BUFFER_WORDS) { st.dropped++; return; }
    for (uint32_t i = 0; i < s->n; i++) { buf[used + i] = s->w[i]; }
    used += s->n;
    st.samples++;
    st.words = used;
    st.rejected += s->rejected;
    st.unaccepted += s->unaccepted;
    last_store = s->w[1];
    held_valid = 0U;
}

static void seal(csample_t *s, uint32_t job, uint32_t final, uint32_t start)
{
    uint32_t x = TRACE_CHECK_SEED;
    s->w[s->n++] = clock_now();
    s->w[0] = (TRACE_CHECKED_MAGIC << 24) | (job << 23) | (final << 22) | (start << 21) | (s->slots << 8) | s->attempts;
    for (uint32_t i = 0; i < s->n; i++) { x ^= s->w[i]; }
    s->w[s->n++] = x;
}

static void begin_sample(csample_t *s)
{
    s->n = 1U;                                   /* the header, written by seal() */
    s->slots = s->attempts = s->rejected = s->unaccepted = 0U;
    s->w[s->n++] = clock_now();
}

/* The job's first sample: QSIZE, the bound of every QREAD after it. */
static void sample_start(void)
{
    csample_t s;
    begin_sample(&s);
    job_qsize = read_slot(&s, NPU_OFF_QSIZE, 4U, 0xFFFFFFFFU, 3U);
    if (s.unaccepted != 0U) { job_qsize = 0U; }  /* every QREAD of this job then fails its range check */
    job_qread = 0U;
    for (uint32_t i = 0; i < PMU_SLOTS; i++) { job_ev[i] = 0U; }
    seal(&s, 1U, 0U, 1U);
    store_checked(&s);
}

static void sample_checked(int force, uint32_t job)
{
    csample_t *s = &smp[cur];
    uint32_t q;
    begin_sample(s);
    if (job != 0U) {
        q = read_slot(s, NPU_OFF_QREAD, job_qread, job_qsize, 3U);
        if ((s->w[2] >> 20) & 1U) { job_qread = q; }
        (void)read_slot(s, NPU_OFF_STATUS, 0U, 0xFFFFFFFFU, 0U);
        for (uint32_t i = 0; i < events; i++) {
            uint32_t d = s->n;
            uint32_t v = read_slot(s, NPU_REG_PMEVCNTR_BASE + 4U * i, job_ev[i], 0xFFFFFFFFU, 0U);
            if ((s->w[d] >> 20) & 1U) { job_ev[i] = v; }
        }
        {
            uint32_t d = s->n;
            q = read_slot(s, NPU_OFF_QREAD, job_qread, job_qsize, 3U);
            if ((s->w[d] >> 20) & 1U) { job_qread = q; }
        }
    } else {
        (void)read_slot(s, NPU_OFF_QREAD, 0U, 0xFFFFFFFFU, 3U);
        (void)read_slot(s, NPU_OFF_STATUS, 0U, 0xFFFFFFFFU, 0U);
        for (uint32_t i = 0; i < events; i++) {
            (void)read_slot(s, NPU_REG_PMEVCNTR_BASE + 4U * i, 0U, 0xFFFFFFFFU, 0U);
        }
        q = read_slot(s, NPU_OFF_QREAD, 0U, 0xFFFFFFFFU, 3U);
    }
    seal(s, job, force ? 1U : 0U, 0U);
    st.polls++;
    if (force || store_after == 0U || s->rejected != 0U || s->unaccepted != 0U || q != last_qread
        || s->w[1] - last_store >= (1U << store_after)) {
        if (held_valid != 0U && q != last_qread) { store_checked(&smp[cur ^ 1U]); }  /* the last sample before the change */
        store_checked(s);
        last_qread = q;
    } else {
        held_valid = 1U;                         /* kept until the next sample; the next one is written in the other */
        cur ^= 1U;
    }
}

void trace_wait(volatile const uint8_t *count, uint32_t job)
{
    last_poll = clock_now() - interval;          /* the first pass samples at once */
    last_store = last_poll;
    if (checked() && job != 0U) {
        sample_start();
        held_valid = 0U;
        last_qread = 0xFFFFFFFFU;
    }
    while (*count == 0U) {
        st.hook_calls++;
        if (mode != 0U && clock_now() - last_poll >= interval) {
            last_poll = clock_now();
            if (checked()) { sample_checked(0, job); } else { sample(0); }
        }
    }
    if (mode != 0U) {                            /* the stream end, after the IRQ */
        if (checked()) { sample_checked(1, job); } else { sample(1); }
    }
}

trace_stats_t trace_stats(void)
{
    return st;
}

uint32_t trace_words(uint32_t first, uint32_t n, uint32_t *out)
{
    if (first >= used) { return 0U; }
    if (n > used - first) { n = used - first; }
    for (uint32_t i = 0; i < n; i++) { out[i] = buf[first + i]; }
    return n;
}
