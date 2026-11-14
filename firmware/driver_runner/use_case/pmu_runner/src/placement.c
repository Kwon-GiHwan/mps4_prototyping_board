/* IFM/OFM placement (placement.h). */
#include "placement.h"

static volatile uint32_t active = PLACEMENT_DDR;

uint32_t placement_config_select(int index, uint32_t placement)
{
    switch (index) {
    case -1: return PLACEMENT_QCONFIG;
    case 1:  return placement == PLACEMENT_SRAM ? PLACEMENT_REGION1_SRAM : PLACEMENT_REGION1_DDR;
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
