/* DRWL workload parsing and MLEK's DDR placement rule (workload.h). */
#include "workload.h"

#include <stddef.h>

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int section_ok(uint32_t off, uint32_t len, uint32_t total, uint32_t table_end)
{
    return off % DRWL_ALIGN == 0U && len != 0U && off >= table_end && off <= total && len <= total - off;
}

uint32_t drwl_parse(const uint8_t *blob, uint32_t len, drwl_t *w)
{
    uint32_t n, table_end, k;
    if (len < 4U * DRWL_HEADER_WORDS) { return 1U; }
    if (rd32(blob) != DRWL_MAGIC || rd32(blob + 4) != DRWL_VERSION) { return 2U; }
    if (rd32(blob + 8) != len) { return 3U; }
    w->n_in = rd32(blob + 20);
    w->n_out = rd32(blob + 24);
    n = w->n_in + w->n_out;
    if (w->n_in < 1U || w->n_out < 1U || w->n_in > DRWL_IO_MAX || w->n_out > DRWL_IO_MAX) {
        return 4U;
    }
    table_end = 4U * (DRWL_IO_WORD + 2U * n);
    if (!section_ok(rd32(blob + 12), rd32(blob + 16), len, table_end)) { return 5U; }
    w->model.ptr = blob + rd32(blob + 12);
    w->model.len = rd32(blob + 16);
    for (k = 0U; k < n; k++) {
        uint32_t off = rd32(blob + 4U * (DRWL_IO_WORD + 2U * k)), sz = rd32(blob + 4U * (DRWL_IO_WORD + 2U * k + 1U));
        drwl_span_t *s = (k < w->n_in) ? &w->in[k] : &w->out[k - w->n_in];
        if (!section_ok(off, sz, len, table_end)) { return 6U; }
        s->ptr = blob + off;
        s->len = sz;
    }
    return 0U;
}

uintptr_t drwl_arena_after(uintptr_t model_base, uint32_t model_len, uint32_t arena_len, uintptr_t limit)
{
    uintptr_t arena = (model_base + model_len + (DRWL_ALIGN - 1U)) & ~(uintptr_t)(DRWL_ALIGN - 1U);
    if (arena < model_base || arena > limit || arena_len > limit - arena) { return 0U; }
    return arena;
}
