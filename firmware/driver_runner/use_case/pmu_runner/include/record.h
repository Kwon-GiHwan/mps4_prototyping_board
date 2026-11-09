/* Measurement record v2 of the driver runner, sent in RUN_COMPLETE. The field list below is the only definition on
 * this side; host/lib/record_v2.py declares the same names in the same order and host/tests/
 * test_driver_runner_contract.py parses this list to check them.
 *
 * Payload: header words magic 'RME2', abi version 2, total words, header words (8), run sequence, valid flags, run rc,
 * crc32 (over words 4..end without word 7, as the v1 record), then the fields in this order.
 * Windows (docs/plan/driver_runner_plan.md 1.3, 2.3): the PMU is reset and enabled at the arm hook, right before the NPU
 * starts; *_irq values are read at the completion IRQ's entry; *_post after the inference call returned. */
#ifndef DRV_RECORD_H
#define DRV_RECORD_H

#include <stdint.h>

#define RECORD_MAGIC        0x32454D52U   /* 'RME2' */
#define RECORD_ABI_VERSION  2U
#define RECORD_HEADER_WORDS 8U
#define RECORD_SCHEMA       2U

#define DRV_EV8(X, p) X(p##0) X(p##1) X(p##2) X(p##3) X(p##4) X(p##5) X(p##6) X(p##7)

#define DRV_RECORD_FIELDS(X) \
    X(schema) X(build_id) X(instr_mode) X(event_set_id) X(event_count) DRV_EV8(X, event_code) X(config_seq) \
    X(wait_mode) X(pmccntr_cfg) X(dcache_on) X(invoke_ok) X(job_result) X(irq_count) X(arm_count) \
    X(power_requests) X(status_at_irq) X(qread_at_irq) X(qsize) X(pmcr_at_arm) X(cnten_at_arm) \
    X(ccnt_irq_lo) X(ccnt_irq_hi) DRV_EV8(X, ev_irq) X(ovf_irq) \
    X(ccnt_post_lo) X(ccnt_post_hi) DRV_EV8(X, ev_post) X(ovf_post) \
    X(dwt_invoke) X(dwt_arm) X(dwt_irq) X(dwt_return) \
    X(ofm_mismatch) X(ofm_max_diff) X(ofm_first) \
    X(model_base) X(model_len) X(arena_base) X(arena_len) X(n_base) DRV_EV8(X, base) DRV_EV8(X, base_size) \
    X(samples) X(sample_dropped)

#define DRV_FIELD_DECL(name) uint32_t name;
typedef struct { DRV_RECORD_FIELDS(DRV_FIELD_DECL) } drv_record_t;

#define DRV_FIELD_ONE(name) +1U
#define RECORD_FIELD_COUNT (0U DRV_RECORD_FIELDS(DRV_FIELD_ONE))
#define RECORD_TOTAL_WORDS (RECORD_HEADER_WORDS + RECORD_FIELD_COUNT)

/* valid_flags */
enum {
    REC_COMPLETED    = 1u << 0,   /* the RUN reached its end */
    REC_INVOKE_OK    = 1u << 1,   /* the inference call returned success */
    REC_ONE_ARM      = 1u << 2,   /* the PMU was armed exactly once */
    REC_ONE_IRQ      = 1u << 3,   /* exactly one completion IRQ */
    REC_NO_OVERFLOW  = 1u << 4,   /* no armed counter overflowed by the IRQ read */
    REC_OUTPUT_MATCH = 1u << 5,   /* every output tensor equals its golden */
};

/* Serialises header + fields into out (RECORD_TOTAL_WORDS * 4 bytes). */
void record_serialise(const drv_record_t *r, uint32_t run_sequence, uint32_t valid_flags, uint32_t run_rc,
                      uint8_t *out);

#endif
