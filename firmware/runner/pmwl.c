/* PMWL workload blob: a Vela output staged by LOAD_MODEL replaces the vendor's test3 tensors. */
#include "runner.h"

/* Tier C step 0b. Step 0 showed the EXT AXI port cannot serve the 0x9000_0000
 * 'Dev Access' alias. Copy the vendor's own tensors to S DRAM (IDAU 7), let the
 * vendor run and judge them there, copy the output back to its own buffer.
 * Sizes are the linked symbol sizes; the gate checks them against nm -S. */
#define EXT_DRAM_BASE      0x70100000U
int __real_test_u85(const u85_eTest eTest, const uint32_t irq_mask, const uint32_t out_size,
                    const uint32_t qsize, struct u85_warp_data_t *w);
/* Tier C step 1: a PMWL workload blob staged by LOAD_MODEL replaces test3. Header = 16 u32:
 * magic ver cms_off cms_len const_off const_len arena fast ifm_aoff ifm_len ifm_doff
 * ofm_aoff ofm_len golden_off irq_mask total. The vendor's memcmp against the reference
 * OFM (tflite_runtime on the original model) decides correctness. Version 4 adds an IO table
 * at word 32 for models with several IFMs/OFMs: n_in n_out, then (aoff len doff) per IFM and
 * (aoff len golden_off) per OFM; entry 0 of each list repeats the header words. Every IFM is
 * copied, every OFM poisoned and compared; the vendor's memcmp still sees OFM 0. */
/* v2 knobs, applied at the vendor's POWER_CTRL printf (see __wrap_printf). */
volatile uint32_t pmwl_knob_pending, pmwl_knob_bad;
uint32_t pmwl_knob[8]; /* regioncfg qconfig mem_attr0..3 axi_sram axi_ext */
/* runner-gap A/B: POWER_CTRL from header word 25 (OFF = vendor MAC_RAMP_VAR). The vendor copy
 * calls this hook for the value it writes just before starting the NPU. */
#define PMWL_VENDOR_MAC_RAMP 2U /* u85.c MAC_RAMP_VAR */
/* runner-gap: header word 26 = absolute base of fast scratch in on-chip SRAM (MLEK places its
 * .bss.NoInit.ethos_u_cache there). Must lie above the runner's own SRAM image and inside SRAM. */
#define PMWL_SRAM_END 0x31400000U /* lnk.ld SRAM ORIGIN 0x31000000 + LENGTH 0x00400000 */
extern char __StackTop[];
static uint32_t pmwl_power_ctrl = PMWL_OFF;
uint32_t u85_power_ctrl_value(uint32_t v)
{
    return (pmwl_power_ctrl == PMWL_OFF) ? v : pmwl_power_ctrl;
}
static uint32_t pmwl_al256(uint32_t n) { return (n + 255U) & ~255U; }
/* 1 = the region's traffic goes to the EXT port (default: USE_AXI_EXT makes every MEM_ATTR EXT). */
static uint32_t pmwl_is_ext(uint32_t attr_index)
{
    uint32_t a = pmwl_knob[2U + attr_index];
    return (a == PMWL_OFF) ? 1U : ((a >> 2) & 1U);
}
static uint32_t pmwl_region_ext(uint32_t region)
{
    return (pmwl_knob[0] == PMWL_OFF) ? 1U : pmwl_is_ext((pmwl_knob[0] >> (2U * region)) & 3U);
}
int __wrap_test_u85(const u85_eTest eTest, const uint32_t irq_mask, const uint32_t out_size,
                    const uint32_t qsize, struct u85_warp_data_t *w)
{
    const uint8_t *s = __runner_staging_start__;
    uint8_t *dram = (uint8_t *)(uintptr_t)EXT_DRAM_BASE;
    uint8_t *near; /* SRAM-port side: staging window after the blob */
    struct u85_warp_data_t x = *w;
    uint32_t h[32], i, cmd_ext;
    uint32_t io[2U + 3U * PMWL_IO_MAX], k, e, at;
    uint8_t *cmd, *cst, *arena, *fast;
    int rc;
    (void)irq_mask; (void)qsize;
    memcpy(h, s, 16U * 4U);
    if (h[0] != PMWL_MAGIC || h[1] < 1U || h[1] > 4U || h[15] != model_total_length) {
        return PMWL_REFUSED;  /* no blob: never fall back to test3 silently */
    }
    for (i = 16U; i < 32U; i++) { h[i] = PMWL_OFF; }
    if (h[1] >= 2U) { memcpy(&h[16], s + 64U, ((h[1] >= 3U) ? 16U : 8U) * 4U); }
    if (h[1] == 2U) { h[23] = PMWL_OFF; }   /* v2 word 23 was reserved */
    if (h[1] == 4U) {
        memcpy(io, s + 128U, sizeof io);
        if (io[0] < 1U || io[1] < 1U || io[1] > PMWL_IO_MAX || io[0] > PMWL_IO_MAX - io[1]
            || io[2] != h[8] || io[3] != h[9] || io[4] != h[10]
            || io[2U + 3U * io[0]] != h[11] || io[3U + 3U * io[0]] != h[12] || io[4U + 3U * io[0]] != h[13]) {
            return PMWL_REFUSED;  /* entry 0 of each list must be the header's IFM / OFM */
        }
    } else {
        io[0] = 1U; io[1] = 1U;
        for (i = 0U; i < 6U; i++) { io[2U + i] = h[8U + i]; }
    }
    for (k = 0U; k < io[0] + io[1]; k++) {
        e = 2U + 3U * k;
        if (io[e + 1U] > h[6] || io[e] > h[6] - io[e + 1U] || io[e + 1U] > h[15] || io[e + 2U] > h[15] - io[e + 1U]) {
            return PMWL_REFUSED;  /* every tensor inside the arena, every data block inside the blob */
        }
    }
    for (i = 0U; i < 8U; i++) { pmwl_knob[i] = h[17U + i]; }
    pmwl_power_ctrl = h[25];
    near = (uint8_t *)s + pmwl_al256(h[15]);
    cmd_ext = (pmwl_knob[1] == PMWL_OFF) ? 1U : pmwl_is_ext(pmwl_knob[1] & 3U);
    /* placement follows the port: EXT regions in S DRAM, SRAM-port regions in staging */
    cmd = cmd_ext ? dram : (uint8_t *)s + h[2];
    if (cmd_ext) { memcpy(cmd, s + h[2], h[3]); dram += pmwl_al256(h[3]); }
    if (pmwl_region_ext(0U)) { cst = dram; memcpy(cst, s + h[4], h[5]); dram += pmwl_al256(h[5]); }
    else { cst = (uint8_t *)s + h[4]; }
    if (pmwl_region_ext(1U)) { arena = dram; dram += pmwl_al256(h[6]); } else { arena = near; near += pmwl_al256(h[6]); }
    if (pmwl_region_ext(2U)) { fast = dram; } else { fast = near; }
    if (h[26] != PMWL_OFF) {
        if (pmwl_region_ext(2U) || (h[26] & 0xFFU) != 0U
            || h[26] < (uint32_t)(uintptr_t)__StackTop || h[26] > PMWL_SRAM_END
            || h[7] > PMWL_SRAM_END - h[26]) {
            return PMWL_REFUSED;  /* on-chip fast scratch must be SRAM-port, aligned, free SRAM */
        }
        fast = (uint8_t *)(uintptr_t)h[26];
    }
    for (k = 0U; k < io[1]; k++) {  /* poison every OFM, then copy every IFM (they may overlap) */
        e = 2U + 3U * (io[0] + k);
        memset(arena + io[e], 0xA5, io[e + 1U]);
    }
    for (k = 0U; k < io[0]; k++) {
        e = 2U + 3U * k;
        memcpy(arena + io[e], s + io[e + 2U], io[e + 1U]);
    }
    __DSB();
    pmwl_knob_bad = 0U;
    if (h[27] != PMWL_OFF) {
        if (h[27] < 1U || h[27] > TA_PROFILE_COUNT) { return PMWL_REFUSED; }
        if (ta_apply(h[27]) != 0U) { pmwl_knob_bad = 1U; }
    }
    if (h[16] != PMWL_OFF) {
        pmu_reg_write(NPU_REG_PMCAXI_CHAN_ABS, h[16]);
        if (pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS) != h[16]) { pmwl_knob_bad = 1U; }
    }
    pmwl_knob_pending = 0U;
    for (i = 0U; i < 8U; i++) { if (pmwl_knob[i] != PMWL_OFF) { pmwl_knob_pending = 1U; } }
    x.cmd_st         = cmd;
    x.weights        = cst;
    x.scratch_buffer = arena;
    x.in_data_0      = fast;
    x.out_data_0     = arena + h[11];
    x.out_ver_data_0 = s + h[13];
    rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);
    at = 0U;  /* how far every OFM is from its reference, as int8; the index runs over all OFMs in order */
    for (k = 0U; k < io[1]; k++) {
        const int8_t *o, *g;
        e = 2U + 3U * (io[0] + k);
        o = (const int8_t *)(arena + io[e]);
        g = (const int8_t *)(s + io[e + 2U]);
        for (i = 0U; i < io[e + 1U]; i++, at++) {
            int32_t dd = (int32_t)o[i] - (int32_t)g[i];
            if (dd != 0) {
                if (ofm_mm_count == 0U) { ofm_mm_first = at; }
                ofm_mm_count++;
                if (dd < 0) { dd = -dd; }
                if ((uint32_t)dd > ofm_mm_max) { ofm_mm_max = (uint32_t)dd; }
            }
        }
    }
    if (pmwl_knob_pending) { pmwl_knob_bad = 1U; }  /* the apply seam never fired */
    if (seam_power_ctrl != ((pmwl_power_ctrl == PMWL_OFF) ? PMWL_VENDOR_MAC_RAMP : pmwl_power_ctrl)) {
        pmwl_knob_bad = 1U;  /* POWER_CTRL at the seam is not the requested (or vendor) value */
    }
    pmwl_knob_pending = 0U;
    last_vendor_rc = rc;
    memcpy(w->out_data_0, arena + h[11], (h[12] < out_size) ? h[12] : out_size);
    return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;
}
