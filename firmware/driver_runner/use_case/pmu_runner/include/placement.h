/* IFM/OFM placement of the Stage 4 placement comparison (docs/plan/stage4_memory_placement_plan.md F2, F3, F5).
 * Platform independent, so the host simulator tests it:
 *   PLACEMENT_DDR   the TFLM arena (region 1 = IFM + OFM) after the model in DDR, region 1 on the EXT port (MLEK
 *                   Dedicated_Sram, the default and the only behaviour before this file existed)
 *   PLACEMENT_SRAM  the same arena in on-chip SRAM after the driver's fast memory, region 1 on the SRAM port
 *                   (MEM_ATTR index 0, the value MLEK Shared_Sram uses for region 1); every other region unchanged */
#ifndef DRV_PLACEMENT_H
#define DRV_PLACEMENT_H

#include <stdint.h>

#define PLACEMENT_DDR    0U
#define PLACEMENT_SRAM   1U
/* PLACEMENT_SRAM_W (Stage 6B-E2E-D): PLACEMENT_SRAM plus region 0 (weights, scale/bias) read from a copy in on-chip
 * SRAM on the SRAM port (ethosu_address_remap index 0); QBASE (command stream) and QCONFIG unchanged. Without a valid
 * copy it falls back to PLACEMENT_SRAM (placement_effective), which REGIONCFG and the REGIONCFG_MATCH flag show. */
#define PLACEMENT_SRAM_W 2U
#define PLACEMENT_MODES  3U

/* SRAM arena alignment: 64 KiB, so the arena's low 16 address bits equal the DDR arena's (model_base is 64 KiB aligned). */
#define PLACEMENT_SRAM_ALIGN 0x10000U

/* MLEK Dedicated_Sram (source/hal/source/components/npu/CMakeLists.txt): QCONFIG 3, REGIONCFG_0 3, REGIONCFG_1 3,
 * regions 2-7 1. The value the driver writes for index (-1 = QCONFIG, 0..7 = region); PLACEMENT_SRAM changes index 1 only.
 * An index outside -1..7 gets region 0's value, as the driver's weak default does. */
#define PLACEMENT_QCONFIG      3U
#define PLACEMENT_REGION0      3U
#define PLACEMENT_REGION1_DDR  3U
#define PLACEMENT_REGION1_SRAM 0U
#define PLACEMENT_REGION0_SRAM 0U
#define PLACEMENT_REGION2_7    1U
uint32_t placement_config_select(int index, uint32_t placement);

/* REGIONCFG for a job with n_base base addresses, as the driver ORs placement_config_select() into it. */
uint32_t placement_regioncfg(uint32_t n_base, uint32_t placement);

/* The SRAM arena: (sram_free rounded up to PLACEMENT_SRAM_ALIGN) + (ddr_arena - model_base). 0 if model_base is not
 * aligned, ddr_arena < model_base, or [arena, arena + arena_len) does not fit below sram_limit. */
uintptr_t placement_sram_arena(uintptr_t sram_free, uintptr_t sram_limit, uintptr_t model_base, uintptr_t ddr_arena,
                               uint32_t arena_len);

/* Write-and-read-back of [base, base + len) (word aligned): an address-dependent pattern, then its complement, each
 * written in full, pushed out of the D-cache by sync() and read back. 0 = every word read back; else 1 (first pattern)
 * or 2 (complement), with the first failing address in *bad. Leaves the complement pattern in memory. */
uint32_t placement_mem_check(uintptr_t base, uint32_t len, void (*sync)(void), uintptr_t *bad);

/* The placement of the loaded workload, read by the driver hook (hooks.c ethosu_config_select). */
void placement_set(uint32_t placement);
uint32_t placement_get(void);

/* PLACEMENT_SRAM_W region 0 copy: (arena + arena_len rounded up to PLACEMENT_SRAM_ALIGN) + (src's low 16 bits); 0 if
 * src or len is 0, the address wraps, or [dst, dst + len) does not fit below sram_limit. */
uintptr_t placement_weight_dst(uintptr_t arena, uint32_t arena_len, uintptr_t sram_limit, uintptr_t src, uint32_t len);

/* The copy of the loaded workload. reset: at every load, no copy. prepare: [src, src + len) copied to
 * placement_weight_dst, sync() (D-cache clean), compared byte for byte; returns the copy address, 0 if it does not fit
 * or differs. A repeat with the same src and len keeps the existing copy without copying again. weights: the copy
 * address, 0 if there is none. effective: PLACEMENT_SRAM_W without a copy is PLACEMENT_SRAM. */
void placement_weights_reset(uintptr_t arena, uint32_t arena_len, uintptr_t sram_limit);
uintptr_t placement_weights_prepare(uintptr_t src, uint32_t len, void (*sync)(void));
uintptr_t placement_weights(void);
uint32_t placement_effective(void);

#endif
