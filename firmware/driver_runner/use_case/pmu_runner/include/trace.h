/* QREAD trace of the driver runner (docs/plan/driver_profiling_design.md §2): while the NPU runs, the driver waits in
 * ethosu_semaphore_take (hooks.c); in WAIT_TRACE that wait is trace_wait(), which samples QREAD, STATUS and, in
 * QREAD_PMU mode, the armed event counters, bracketed by the CPU cycle counter, into a static buffer. When the wait
 * ends (the completion IRQ has run) one final sample is always stored, outside the IRQ so it never interleaves with a
 * poll. The host reads the buffer with GET_TRACE after RUN_COMPLETE.
 * QREAD is the command completion position (TRM): not an operator start or end time.
 * host/lib/qread_trace.py declares the same layout (the sample and config word are the legacy runner's 2B-4 layout);
 * host/tests/test_driver_runner_contract.py checks both. Platform independent: the NPU base and the clock come from
 * trace_bind(). */
#ifndef DRV_TRACE_H
#define DRV_TRACE_H

#include <stdint.h>

/* Trace word (SET_RUN_OPTIONS word 2): bits 3:0 mode, 11:8 poll interval 2^n CPU cycles, 19:16 store policy
 * (0 = every poll, n >= 1 = only when QREAD changed or 2^n cycles since the last stored sample); other bits 0.
 * TRACE_OFF = no trace (any wait mode but WAIT_TRACE). */
#define TRACE_OFF              0xFFFFFFFFU
#define TRACE_MODE_QREAD_ONLY  1U
#define TRACE_MODE_QREAD_PMU   2U
/* Checked modes (Stage 2B operator-aware pilot): same registers, every read checked at read time (below). */
#define TRACE_MODE_QREAD_CHECKED      3U
#define TRACE_MODE_QREAD_PMU_CHECKED  4U
#define TRACE_MODE_MASK        0xFU
#define TRACE_INTERVAL_SHIFT   8U
#define TRACE_STORE_SHIFT      16U
#define TRACE_FIELD_MASK       0xFU
#define TRACE_CONFIG_MASK      (TRACE_MODE_MASK | (TRACE_FIELD_MASK << TRACE_INTERVAL_SHIFT) \
                                | (TRACE_FIELD_MASK << TRACE_STORE_SHIFT))

/* Sample: t_before, qread_before, status, event_0 .. event_{N-1}, qread_after, t_after (N = 0 in QREAD_ONLY). */
#define TRACE_BASE_SAMPLE_WORDS 5U
#define TRACE_BUFFER_WORDS      32768U
#define TRACE_GET_MAX_WORDS     1000U   /* words per GET_TRACE reply (4096-byte payload cap) */
#define CMD_GET_TRACE           0x41U

/* Checked sample (modes 3, 4; variable length). Every register read is preceded by a read of ID (a constant), so a
 * read that returns the previous read's data shows up as the ID value; a slot is re-read at most twice more:
 *   header      TRACE_CHECKED_MAGIC << 24 | job << 23 | final << 22 | start << 21 | slots << 8 | attempts (all slots)
 *   t_before
 *   per slot    descriptor accepted << 20 | attempts << 16 | register offset, then attempts x (ID read, value read)
 *   t_after
 *   checksum    TRACE_CHECK_SEED ^ every word above
 * job = the driver's inference semaphore (0: another take, e.g. ethosu_reserve_driver). start = the job's first
 * sample: one slot, QSIZE. Other samples: QREAD, STATUS, event_0 .. event_{N-1} (mode 4), QREAD. An attempt is accepted
 * when ID read = the RUN's ID, value != ID read, and value is plausible: QREAD 4-byte aligned, >= the last accepted QREAD
 * of the job, <= QSIZE; QSIZE aligned and > 0; an event counter >= its last accepted value of the job (range checks in
 * job samples only). Store policy n >= 1 also keeps the sample before every QREAD change and every sample with a
 * rejected attempt. */
#define TRACE_CHECKED_MAGIC   0x5AU
#define TRACE_CHECK_SEED      0xA5A5A5A5U
#define TRACE_MAX_ATTEMPTS    3U        /* the first read and at most two re-reads */

#define NPU_OFF_ID     0x00U
#define NPU_OFF_STATUS 0x04U
#define NPU_OFF_QREAD  0x18U
#define NPU_OFF_QSIZE  0x20U    /* core driver ethosu85_interface.h NPU_REG_QSIZE (0x24 is PROT) */

typedef struct {
    uint32_t config, words_per_sample, samples, dropped, polls, hook_calls;
    uint32_t words, rejected, unaccepted, id;   /* checked modes: buffer words, rejected attempts, unaccepted slots */
} trace_stats_t;

void trace_bind(volatile void *npu_base, uint32_t (*now)(void));
/* 0 = a valid trace word or TRACE_OFF; 1 = reserved bits, 2 = unknown mode. Touches no register. */
uint32_t trace_check(uint32_t word);
/* Start of a RUN: clear the buffer state; word = the RUN's trace word, events = the armed slot count. */
void trace_begin(uint32_t word, uint32_t events);
/* Wait until *count != 0, sampling on the configured interval, then store one final sample (the driver's semaphore
 * wait in WAIT_TRACE). job: this is the inference semaphore (checked modes flag the samples with it). */
void trace_wait(volatile const uint8_t *count, uint32_t job);
trace_stats_t trace_stats(void);
/* Buffer words [first, first + n) (n clipped to what is stored); returns the count copied into out. */
uint32_t trace_words(uint32_t first, uint32_t n, uint32_t *out);

#endif
