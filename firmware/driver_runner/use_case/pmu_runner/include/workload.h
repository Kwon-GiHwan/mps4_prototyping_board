/* DRWL workload (host/lib/drwl.py declares the same layout; host/tests/test_driver_runner_contract.py checks both).
 * Little-endian u32: header words 0..15 = magic 'DRWL', version, total_len, model_off, model_len, n_in, n_out, rest 0;
 * from word 16 the IO table: per input (data_off, len), then per output (golden_off, len); every section 16-B aligned.
 * Platform independent: addresses come in as arguments. */
#ifndef DRV_WORKLOAD_H
#define DRV_WORKLOAD_H

#include <stdint.h>

#define DRWL_MAGIC        0x4C575244U
#define DRWL_VERSION      1U
#define DRWL_HEADER_WORDS 16U
#define DRWL_IO_WORD      16U
#define DRWL_IO_MAX       8U
#define DRWL_ALIGN        16U

typedef struct {
    const uint8_t *ptr;
    uint32_t len;
} drwl_span_t;

typedef struct {
    drwl_span_t model;
    uint32_t n_in, n_out;
    drwl_span_t in[DRWL_IO_MAX];
    drwl_span_t out[DRWL_IO_MAX];
} drwl_t;

/* 0 = accepted. Refuses what host/lib/drwl.py parse() refuses. */
uint32_t drwl_parse(const uint8_t *blob, uint32_t len, drwl_t *w);

/* MLEK's DDR placement (mps4-sse-320.gnu.ld, .ddr.at_ddr): nn_model at the region base, the tensor arena at the next
 * 16-byte boundary after it. Returns the arena address, or 0 if model + arena do not fit below limit. */
uintptr_t drwl_arena_after(uintptr_t model_base, uint32_t model_len, uint32_t arena_len, uintptr_t limit);

#endif
