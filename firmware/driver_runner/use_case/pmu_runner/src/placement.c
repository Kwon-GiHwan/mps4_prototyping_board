/* IFM/OFM placement (placement.h). */
#include "placement.h"

#include <string.h>

static volatile uint32_t active = PLACEMENT_DDR;

uint32_t placement_config_select(int index, uint32_t placement)
{
    switch (index) {
    case -1: return PLACEMENT_QCONFIG;
    case 0:  return placement == PLACEMENT_SRAM_W ? PLACEMENT_REGION0_SRAM : PLACEMENT_REGION0;
    case 1:  return (placement == PLACEMENT_SRAM || placement == PLACEMENT_SRAM_W) ? PLACEMENT_REGION1_SRAM
                                                                                    : PLACEMENT_REGION1_DDR;
    case 2: case 3: case 4: case 5: case 6: case 7: return PLACEMENT_REGION2_7;
    default: return PLACEMENT_REGION0;
    }
}

uint32_t placement_regioncfg(uint32_t n_base, uint32_t placement)
{
    uint32_t r = 0U;
    for (uint32_t i = 0; i < n_base && i < 8U; i++) {
        r |= placement_config_select((int)i, placement) << (2U * i);
    }
    return r;
}

uintptr_t placement_sram_arena(uintptr_t sram_free, uintptr_t sram_limit, uintptr_t model_base, uintptr_t ddr_arena,
                               uint32_t arena_len)
{
    const uintptr_t mask = (uintptr_t)PLACEMENT_SRAM_ALIGN - 1U;
    uintptr_t start = (sram_free + mask) & ~mask, arena;
    if ((model_base & mask) != 0U || ddr_arena < model_base || start < sram_free) { return 0U; }
    arena = start + (ddr_arena - model_base);
    if (arena < start || arena > sram_limit || arena_len > sram_limit - arena) { return 0U; }
    return arena;
}

static uint32_t pattern(uintptr_t a) { return (uint32_t)a ^ 0xA5C3F00FU; }

uint32_t placement_mem_check(uintptr_t base, uint32_t len, void (*sync)(void), uintptr_t *bad)
{
    volatile uint32_t *w = (volatile uint32_t *)base;
    const uint32_t n = len / 4U;
    for (uint32_t pass = 1U; pass <= 2U; pass++) {
        const uint32_t flip = pass == 1U ? 0U : 0xFFFFFFFFU;
        for (uint32_t i = 0; i < n; i++) { w[i] = pattern((uintptr_t)&w[i]) ^ flip; }
        sync();
        for (uint32_t i = 0; i < n; i++) {
            if (w[i] != (pattern((uintptr_t)&w[i]) ^ flip)) {
                *bad = (uintptr_t)&w[i];
                return pass;
            }
        }
    }
    return 0U;
}

void placement_set(uint32_t placement) { active = placement; }
uint32_t placement_get(void) { return active; }

static uintptr_t w_arena, w_limit, w_src, w_dst;
static uint32_t w_arena_len, w_len;

uintptr_t placement_weight_dst(uintptr_t arena, uint32_t arena_len, uintptr_t sram_limit, uintptr_t src, uint32_t len)
{
    const uintptr_t mask = (uintptr_t)PLACEMENT_SRAM_ALIGN - 1U;
    uintptr_t end = arena + arena_len, start, dst;
    if (src == 0U || len == 0U || end < arena) { return 0U; }
    start = (end + mask) & ~mask;
    dst = start + (src & mask);
    if (start < end || dst < start || dst > sram_limit || len > sram_limit - dst) { return 0U; }
    return dst;
}

void placement_weights_reset(uintptr_t arena, uint32_t arena_len, uintptr_t sram_limit)
{
    w_arena = arena; w_arena_len = arena_len; w_limit = sram_limit;
    w_src = 0U; w_len = 0U; w_dst = 0U;
}

uintptr_t placement_weights_prepare(uintptr_t src, uint32_t len, void (*sync)(void))
{
    uintptr_t dst;
    if (w_dst != 0U && src == w_src && len == w_len) { return w_dst; }
    w_dst = 0U;
    dst = placement_weight_dst(w_arena, w_arena_len, w_limit, src, len);
    if (dst == 0U) { return 0U; }
    memcpy((void *)dst, (const void *)src, len);
    sync();
    if (memcmp((const void *)dst, (const void *)src, len) != 0) { return 0U; }
    w_src = src; w_len = len; w_dst = dst;
    return dst;
}

uintptr_t placement_weights(void) { return w_dst; }

uint32_t placement_effective(void)
{
    return (active == PLACEMENT_SRAM_W && w_dst == 0U) ? PLACEMENT_SRAM : active;
}
