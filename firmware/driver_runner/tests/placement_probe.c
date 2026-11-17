/* Host-only probe of placement.c (host/tests/test_placement.py): prints what the functions return for the inputs the
 * test names, one "name value" line each, so the expected values stay in the Python test. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "placement.h"

static uint32_t mem[4096];
static int fault;   /* 1: word 100 reads all ones; 2: the upper half aliases the lower half; 3: word 100 keeps only the
                       first value written to it (the complement pass must catch it) */
static uint32_t kept;
static int syncs;

static uint8_t *corrupt_at;
static void corrupt(void) { if (corrupt_at) { corrupt_at[5] ^= 0xFFu; } }

static void sync(void)
{
    if (fault == 1) { mem[100] = 0xFFFFFFFFu; }
    if (fault == 2) { memcpy(&mem[2048], &mem[0], 2048 * sizeof mem[0]); }
    if (fault == 3) {
        if (syncs == 0) { kept = mem[100]; } else { mem[100] = kept; }
    }
    if (fault == 4) { corrupt(); }
    syncs++;
}

int main(void)
{
    for (uint32_t p = 0; p < 3; p++) {
        for (int i = -2; i <= 8; i++) { printf("select_%u_%d %u\n", p, i, placement_config_select(i, p)); }
        for (uint32_t n = 0; n <= 9; n++) { printf("regioncfg_%u_%u %#x\n", p, n, placement_regioncfg(n, p)); }
    }
    /* sram_free, sram_limit, model_base, ddr_arena, arena_len */
    static const unsigned long long a[][5] = {
        {0x31060000u, 0x31400000u, 0x70000000u, 0x700015C0u, 0x200000u},   /* conv_base on FI101 */
        {0x31060001u, 0x31400000u, 0x70000000u, 0x700015C0u, 0x200000u},   /* free base not aligned: next 64 KiB */
        {0x31060000u, 0x31400000u, 0x70000100u, 0x700015C0u, 0x200000u},   /* model base not aligned */
        {0x31060000u, 0x31400000u, 0x70000000u, 0x6FFFFFF0u, 0x200000u},   /* arena below the model */
        {0x31060000u, 0x31400000u, 0x70000000u, 0x700015C0u, 0x39EA41u},   /* one byte too long */
        {0x31060000u, 0x31400000u, 0x70000000u, 0x700015C0u, 0x39EA40u},   /* ends exactly at the limit */
        {0x31400000u, 0x31400000u, 0x70000000u, 0x700015C0u, 0x10u},       /* empty window */
        {0xFFFF0001u, 0xFFFFFFFFu, 0x70000000u, 0x700015C0u, 0x10u},       /* round-up wraps */
    };
    for (unsigned k = 0; k < sizeof a / sizeof a[0]; k++) {
        printf("arena_%u %#lx\n", k, (unsigned long)placement_sram_arena((uintptr_t)a[k][0], (uintptr_t)a[k][1],
                                                                          (uintptr_t)a[k][2], (uintptr_t)a[k][3],
                                                                          (uint32_t)a[k][4]));
    }
    for (fault = 0; fault <= 3; fault++) {
        uintptr_t bad = 0;
        syncs = 0;
        uint32_t r = placement_mem_check((uintptr_t)mem, sizeof mem, sync, &bad);
        printf("check_%d %u %ld\n", fault, r, r ? (long)((uint32_t *)bad - mem) : -1L);
    }
    placement_set(1u);
    printf("get %u\n", placement_get());
    /* region 0 copy address: arena, arena_len, sram_limit, src, len */
    static const unsigned long long w[][5] = {
        {0x31076770u, 0x200000u, 0x31400000u, 0x70000420u, 0x16090u},   /* E2E-B B3 on FI101 */
        {0x31076770u, 0x200000u, 0x31400000u, 0x70000420u, 0x17FBE0u},  /* ends exactly at the limit */
        {0x31076770u, 0x200000u, 0x31400000u, 0x70000420u, 0x17FBE1u},  /* one byte too long */
        {0x31070000u, 0x200000u, 0x31400000u, 0x70000420u, 0x10u},      /* arena end already aligned */
        {0x31076770u, 0x200000u, 0x31400000u, 0u, 0x10u},               /* no source */
        {0x31076770u, 0x200000u, 0x31400000u, 0x70000420u, 0u},         /* empty */
        {0xFFFF0000u, 0x20000u, 0xFFFFFFFFu, 0x70000420u, 0x10u},       /* arena end wraps */
    };
    for (unsigned k = 0; k < sizeof w / sizeof w[0]; k++) {
        printf("wdst_%u %#lx\n", k, (unsigned long)placement_weight_dst((uintptr_t)w[k][0], (uint32_t)w[k][1],
                                                                       (uintptr_t)w[k][2], (uintptr_t)w[k][3],
                                                                       (uint32_t)w[k][4]));
    }
    /* copy into a host buffer: arena = buffer start - 64 KiB (aligned buffer), so dst = buffer + (src & 0xFFFF) */
    {
        static uint8_t srcbuf[0x30000], winbuf[0x40000];
        uint8_t *src = (uint8_t *)(((uintptr_t)srcbuf + 0xFFFFu) & ~(uintptr_t)0xFFFFu);
        uint8_t *win = (uint8_t *)(((uintptr_t)winbuf + 0xFFFFu) & ~(uintptr_t)0xFFFFu);   /* 64 KiB aligned */
        uintptr_t arena = (uintptr_t)win, lim = (uintptr_t)win + 0x30000u, s0 = (uintptr_t)src + 0x420u, d;
        for (unsigned k = 0; k < 0x20000u; k++) { src[k] = (uint8_t)(k * 7u + 1u); }
        fault = 0; syncs = 0;
        placement_set(2u);
        printf("eff_nocopy %u\n", placement_effective());
        placement_weights_reset(arena, 0x10000u, lim);
        d = placement_weights_prepare(s0, 0x1000u, sync);
        printf("prep_off %ld\n", d ? (long)(d - (uintptr_t)win) : -1L);
        printf("prep_same %d\n", d ? memcmp((void *)d, (void *)s0, 0x1000u) == 0 : -1);
        printf("prep_weights %d %d\n", placement_weights() == d, syncs);
        printf("eff_copy %u\n", placement_effective());
        printf("prep_again %d %d\n", placement_weights_prepare(s0, 0x1000u, sync) == d, syncs);
        printf("prep_other %d\n", placement_weights_prepare(s0 + 16u, 0x1000u, sync) == d + 16u);
        placement_weights_reset(arena, 0x10000u, lim);
        printf("reset %lu %u\n", (unsigned long)placement_weights(), placement_effective());
        printf("prep_toolong %lu %u\n", (unsigned long)placement_weights_prepare(s0, 0x20000u, sync),
               placement_effective());
        placement_set(1u);
        printf("eff_mode1 %u\n", placement_effective());
        placement_set(2u);
        placement_weights_reset(arena, 0x10000u, lim);
        corrupt_at = win + 0x10420u;
        fault = 4;                                /* the copy does not hold: sync corrupts one byte of it */
        d = placement_weights_prepare(s0, 0x1000u, sync);
        printf("prep_corrupt %lu %u\n", (unsigned long)d, placement_effective());
    }
    return 0;
}
