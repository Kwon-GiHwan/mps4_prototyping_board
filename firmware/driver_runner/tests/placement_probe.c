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

static void sync(void)
{
    if (fault == 1) { mem[100] = 0xFFFFFFFFu; }
    if (fault == 2) { memcpy(&mem[2048], &mem[0], 2048 * sizeof mem[0]); }
    if (fault == 3) {
        if (syncs == 0) { kept = mem[100]; } else { mem[100] = kept; }
    }
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
    return 0;
}
