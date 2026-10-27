/* One measured RUN (measure.c): instrumentation config, the PMU window, the measurement record, RUN_COMPLETE,
 * GET_CAPABILITIES, and the measurement-config commands. */
#ifndef RUNNER_MEASURE_H
#define RUNNER_MEASURE_H

#include <stdint.h>

/* ------------------------------------------------------------------------ */
/* Build profile                                                             */
/* ------------------------------------------------------------------------ */

#define BUILD_PROFILE_FUNCTIONAL      0U
#define BUILD_PROFILE_MEASURE_WRAPPED 1U
#define BUILD_PROFILE_MEASURE_CLEAN   2U

#define RUNNER_BUILD_PROFILE BUILD_PROFILE_MEASURE_CLEAN

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
/* Instrumentation mode. THE POINT OF THIS BUILD: configurations B and C are */
/* the same three BINs and differ only by this runtime value, so a B/C delta */
/* cannot be explained by code layout, vector addresses or linker placement. */
/* In OFF the PMU registers are never read and never written.               */
#define INSTRUMENTATION_OFF       0U
#define INSTRUMENTATION_END_ONLY  1U
#define INSTRUMENTATION_EVENTS    2U /* Tier B: END_ONLY + event slots */
#define RUNNER_MAX_NPU_EVENT_COUNTERS NPU_PMU_ABI_EVENT_SLOTS

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
    uint32_t read_seam_fired;              /* Tier B: CPM seam arrivals  */
    uint32_t vendor_rc;                    /* Tier C: test_u85's own rc  */
    uint32_t seam_npu_status;              /* STATUS at the CPM seam     */
    uint32_t seam_npu_qread;               /* QREAD at the CPM seam      */
    uint32_t ofm_mismatch_count;           /* OFM bytes != reference     */
    uint32_t ofm_max_abs_diff;             /* as int8                    */
    uint32_t ofm_first_mismatch;           /* index, 0xFFFFFFFF = none   */
} measurement_record_t;

/* NOTE FOR THE HOST: this is 47, not the 42 it was, and not the "40" the
 * change request assumed. The pre-existing record already had 42 fields (the
 * struct and build_measurement_payload() agree at 42); five are appended here.
 * The ABI header's total_payload_words is the authority -- never hardcode. */
/* 47 + 55 appended for milestone 1. The ABI header's total_payload_words
 * remains the authority; hosts skip trailing words they do not know. */
#define MEASUREMENT_FIELD_COUNT 109U
#define MEASUREMENT_PAYLOAD_SIZE (MEASUREMENT_FIELD_COUNT * 4U)

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

#define COMPLETION_WAIT_MODE_UNKNOWN   0U
#define COMPLETION_WAIT_MODE_BUSY_POLL 1U
#define COMPLETION_WAIT_MODE_WFI       2U

/* 29 + 5 appended for the PMU candidate. */
#define CAP_FIELD_COUNT 34U
#define CAP_PAYLOAD_SIZE (CAP_FIELD_COUNT * 4U)

extern instrumentation_config_t instr_cfg;
extern volatile uint32_t measurement_active;
extern volatile uint32_t suppressed_printf_calls;
extern volatile uint32_t suppressed_write_calls;
extern volatile uint32_t uart_bytes_during_measurement;
extern volatile uint32_t uart_tx_forbidden;
/* read seam (io_wrap.c) and PMWL path (pmwl.c) */
extern volatile int32_t last_vendor_rc;
extern volatile uint32_t seam_status, seam_qread;
extern volatile uint32_t ofm_mm_count, ofm_mm_max, ofm_mm_first;
extern volatile uint32_t seam_power_ctrl;
extern volatile uint32_t seam_fired, seam_cycle_lo, seam_cycle_hi, seam_cycle_stable,
                         seam_cycle_retries, seam_ovf, seam_ev[RUNNER_MAX_NPU_EVENT_COUNTERS];
/* run result, read by GET_RESULT and cleared by RESET_RUNNER (proto.c) */
extern int32_t  run_rc;
extern int      last_run_completed;
extern uint32_t last_run_sequence;
extern uint32_t last_completed_sequence;
extern uint32_t last_valid_flags;
extern uint32_t last_poison_crc;
extern uint32_t last_output_crc;
extern uint32_t last_result_region_crc;

void handle_run(uint32_t sequence);
void build_capabilities(uint8_t *out);
void handle_get_measurement(uint32_t sequence);
void handle_set_instrumentation_mode(uint32_t sequence, const uint8_t *payload, uint32_t payload_length);
void handle_reset_runner(uint32_t sequence);

#endif
