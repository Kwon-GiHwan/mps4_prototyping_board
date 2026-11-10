/* QREAD trace (trace.h). */
#include "trace.h"

#include "pmu_session.h"

static volatile uint8_t *npu;
static uint32_t (*clock_now)(void);
static uint32_t buf[TRACE_BUFFER_WORDS];
static trace_stats_t st;
static uint32_t mode, interval, store_after, events, used, last_poll, last_store, last_qread;

static uint32_t npu_word(uint32_t off) { return *(volatile uint32_t *)(npu + off); }

void trace_bind(volatile void *npu_base, uint32_t (*now)(void))
{
    npu = (volatile uint8_t *)npu_base;
    clock_now = now;
}

uint32_t trace_check(uint32_t word)
{
    if (word == TRACE_OFF) { return 0U; }
    if (word & ~TRACE_CONFIG_MASK) { return 1U; }
    if ((word & TRACE_MODE_MASK) != TRACE_MODE_QREAD_ONLY && (word & TRACE_MODE_MASK) != TRACE_MODE_QREAD_PMU) {
        return 2U;
    }
    return 0U;
}

void trace_begin(uint32_t word, uint32_t n_events)
{
    st = (trace_stats_t){0};
    st.config = word;
    used = 0U;
    mode = (word == TRACE_OFF) ? 0U : (word & TRACE_MODE_MASK);
    interval = 1U << ((word >> TRACE_INTERVAL_SHIFT) & TRACE_FIELD_MASK);
    store_after = (word >> TRACE_STORE_SHIFT) & TRACE_FIELD_MASK;
    events = (mode == TRACE_MODE_QREAD_PMU) ? n_events : 0U;
    st.words_per_sample = (mode == 0U) ? 0U : TRACE_BASE_SAMPLE_WORDS + events;
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

void trace_wait(volatile const uint8_t *count)
{
    last_poll = clock_now() - interval;          /* the first pass samples at once */
    last_store = last_poll;
    while (*count == 0U) {
        st.hook_calls++;
        if (mode != 0U && clock_now() - last_poll >= interval) {
            last_poll = clock_now();
            sample(0);
        }
    }
    if (mode != 0U) { sample(1); }              /* the stream end, after the IRQ */
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
