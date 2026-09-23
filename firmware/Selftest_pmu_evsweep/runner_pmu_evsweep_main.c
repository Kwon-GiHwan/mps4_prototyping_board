/* PMU EV_TYPE acceptance sweep (Tier A). Contract:
 *   docs/superpowers/specs/2026-09-23-pmu-evsweep-contract.md
 *
 * Boots, prints a header, writes every 10-bit EV_TYPE into PMEVTYPER and reads
 * it back, prints one line per cell, prints a footer, then idles forever.
 * No inference. No model. No protocol. Nothing here is a runner.
 */

#include <stdint.h>
#include "ARMCM85.h"
#include "Driver_USART.h"
#include "serial.h"
#include "npu_pmu_regs.h"

#ifndef RUNNER_FIRMWARE_BUILD_ID
#error "RUNNER_FIRMWARE_BUILD_ID must be supplied by the Makefile"
#endif

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))

#define U85_BASE_ADDRESS 0x50004000U
#define NPU_OFF_CONFIG   0x28U

#define EV_TYPE_MASK     0x3FFU
#define EV_TYPE_COUNT    1024U
#define SLOT_COUNT       8U

extern ARM_DRIVER_USART Driver_USART0;

static uint32_t pmu_rd(uint32_t off)            { return REG32(U85_BASE_ADDRESS + off); }
static void     pmu_wr(uint32_t off, uint32_t v) { REG32(U85_BASE_ADDRESS + off) = v; }

/* --- tiny formatting; no stdio in this image --------------------------- */
static void put_hex32(char *b, uint32_t v)
{
    static const char d[] = "0123456789abcdef";
    int i;
    for (i = 7; i >= 0; i--) { b[i] = d[v & 0xFU]; v >>= 4; }
    b[8] = 0;
}
static int put_dec(char *b, uint32_t v)
{
    char t[11]; int n = 0, i;
    do { t[n++] = (char)('0' + v % 10U); v /= 10U; } while (v);
    for (i = 0; i < n; i++) b[i] = t[n - 1 - i];
    b[n] = 0; return n;
}

/* --- CRC-32 (IEEE, zlib-compatible) over EV lines ----------------------- */
static uint32_t crc;
static void crc_init(void) { crc = 0xFFFFFFFFU; }
static void crc_feed(const char *s)
{
    while (*s) {
        uint32_t c = crc ^ (uint8_t)*s++; int k;
        for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320U & (0U - (c & 1U)));
        crc = c;
    }
}
static uint32_t crc_final(void) { return crc ^ 0xFFFFFFFFU; }

static void say(const char *s) { serial_print((char *)s); }

static uint32_t ev_lines;

/* One cell: write ev to slot, readback, print "EV,<pass>,<slot>,<ev>,<rb>\n". */
static void cell(char pass, uint32_t slot, uint32_t ev)
{
    char line[40]; char *p = line; uint32_t rb;

    pmu_wr(NPU_REG_PMEVTYPER_BASE + 4U * slot, ev & EV_TYPE_MASK);
    __DSB();
    rb = pmu_rd(NPU_REG_PMEVTYPER_BASE + 4U * slot);

    *p++ = 'E'; *p++ = 'V'; *p++ = ','; *p++ = pass; *p++ = ',';
    *p++ = (char)('0' + slot); *p++ = ',';
    p += put_dec(p, ev); *p++ = ',';
    put_hex32(p, rb); p += 8;
    *p++ = '\n'; *p = 0;

    crc_feed(line); ev_lines++;
    say(line);
}

static void set_cnt_en(uint32_t on)
{
    uint32_t v = pmu_rd(NPU_REG_PMCR) & ~NPU_PMCR_CNT_EN_MSK;
    pmu_wr(NPU_REG_PMCR, on ? (v | NPU_PMCR_CNT_EN_MSK) : v);
    __DSB();
}

static void dbg_ena_sbrom(void)
{
    REG32(0x5802125CU) = 0xAAAAAAAAU; /* Debug authentication enable */
    REG32(0x500A0100U) = 0x00005555U; /* LCM_DCU_FORCE_DISABLE */
}

int main(void)
{
    char h[12]; uint32_t pmcr, cfg, slot, ev;

    dbg_ena_sbrom();
    serial_init(&Driver_USART0, 115200);

    /* Header: the device answering for itself, before anything is written. */
    pmcr = pmu_rd(NPU_REG_PMCR);
    cfg  = REG32(U85_BASE_ADDRESS + NPU_OFF_CONFIG);
    say("EVSWEEP-HDR,");
    put_hex32(h, (uint32_t)RUNNER_FIRMWARE_BUILD_ID); say(h); say(",");
    put_hex32(h, pmcr); say(h); say(",");
    put_hex32(h, cfg);  say(h); say(",");
    put_dec(h, (pmcr & NPU_PMCR_NUM_EVENT_CNT_MSK) >> NPU_PMCR_NUM_EVENT_CNT_POS);
    say(h); say("\n");

    crc_init(); ev_lines = 0U;

    /* P0: cnt_en = 0, slot 0 only. Control for the TRM "not guaranteed" note. */
    set_cnt_en(0U);
    for (ev = 0; ev < EV_TYPE_COUNT; ev++) cell('0', 0U, ev);

    /* P1: cnt_en = 1, every slot. The citable pass. */
    set_cnt_en(1U);
    for (slot = 0; slot < SLOT_COUNT; slot++)
        for (ev = 0; ev < EV_TYPE_COUNT; ev++) cell('1', slot, ev);

    /* Leave the block as we found it: no event selected, nothing armed. */
    for (slot = 0; slot < SLOT_COUNT; slot++) pmu_wr(NPU_REG_PMEVTYPER_BASE + 4U * slot, 0U);
    pmu_wr(NPU_REG_PMCNTENCLR, 0xFFFFFFFFU);
    set_cnt_en(0U);

    say("EVSWEEP-END,");
    put_dec(h, ev_lines); say(h); say(",");
    put_hex32(h, crc_final()); say(h); say("\n");

    for (;;) { __WFI(); }
}
