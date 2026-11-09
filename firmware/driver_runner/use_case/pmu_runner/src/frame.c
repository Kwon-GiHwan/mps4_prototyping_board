/* Runner protocol frames (frame.h). */
#include "frame.h"

#include <string.h>

static const uint32_t crc_nibble[16] = {
    0x00000000U, 0x1DB71064U, 0x3B6E20C8U, 0x26D930ACU, 0x76DC4190U, 0x6B6B51F4U, 0x4DB26158U, 0x5005713CU,
    0xEDB88320U, 0xF00F9344U, 0xD6D6A3E8U, 0xCB61B38CU, 0x9B64C2B0U, 0x86D3D2D4U, 0xA00AE278U, 0xBDBDF21CU};

uint32_t crc32_update(uint32_t crc, const void *data, uint32_t len)
{
    const uint8_t *p = data;
    while (len--) {
        crc ^= *p++;
        crc = (crc >> 4) ^ crc_nibble[crc & 0xFU];
        crc = (crc >> 4) ^ crc_nibble[crc & 0xFU];
    }
    return crc;
}

uint32_t crc32_of(const void *data, uint32_t len)
{
    return crc32_update(0xFFFFFFFFU, data, len) ^ 0xFFFFFFFFU;
}

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void wr32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

/* Receive buffer: one frame at most (header + payload + crc). */
static uint8_t rx[FRAME_HEADER_SIZE + FRAME_MAX_PAYLOAD + 4U];
static uint32_t rx_used;

static void drop(uint32_t n)
{
    memmove(rx, rx + n, rx_used - n);
    rx_used -= n;
}

/* Header at rx[0..]: 0 = need more bytes, 1 = complete and valid frame, -1 = not a frame here (drop one byte). */
static int check(frame_t *f, frame_errors_t *err)
{
    uint32_t len, total;
    if (rx_used < 4U) { return 0; }
    if (rd32(rx) != FRAME_MAGIC) { err->bad_magic++; return -1; }
    if (rx_used < FRAME_HEADER_SIZE) { return 0; }
    if (rx[4] != FRAME_VERSION) { err->bad_version++; return -1; }
    len = rd32(rx + 12);
    if (len > FRAME_MAX_PAYLOAD) { err->length_error++; return -1; }
    total = FRAME_HEADER_SIZE + len + 4U;
    if (rx_used < total) { return 0; }
    if (crc32_of(rx, FRAME_HEADER_SIZE + len) != rd32(rx + FRAME_HEADER_SIZE + len)) { err->bad_crc++; return -1; }
    f->command  = rx[5];
    f->flags    = (uint16_t)(rx[6] | (rx[7] << 8));
    f->sequence = rd32(rx + 8);
    f->length   = len;
    memcpy(f->payload, rx + FRAME_HEADER_SIZE, len);
    drop(total);
    return 1;
}

int frame_poll(const frame_io_t *io, frame_t *f, frame_errors_t *err)
{
    uint8_t b;
    for (;;) {
        int r = check(f, err);
        if (r == 1) { return 1; }
        if (r == -1) { err->resync++; drop(1U); continue; }
        if (rx_used == sizeof rx) { err->resync++; drop(1U); continue; }   /* cannot happen: a full buffer is a frame */
        if (!io->getc(&b)) { return 0; }
        rx[rx_used++] = b;
    }
}

void frame_send(const frame_io_t *io, uint8_t command, uint16_t flags, uint32_t sequence,
                const void *payload, uint32_t length)
{
    uint8_t h[FRAME_HEADER_SIZE], c[4];
    const uint8_t *p = payload;
    uint32_t crc;
    wr32(h, FRAME_MAGIC);
    h[4] = FRAME_VERSION; h[5] = command; h[6] = (uint8_t)flags; h[7] = (uint8_t)(flags >> 8);
    wr32(h + 8, sequence);
    wr32(h + 12, length);
    crc = crc32_update(0xFFFFFFFFU, h, FRAME_HEADER_SIZE);
    crc = crc32_update(crc, p, length) ^ 0xFFFFFFFFU;
    wr32(c, crc);
    for (uint32_t i = 0; i < FRAME_HEADER_SIZE; i++) { io->putc(h[i]); }
    for (uint32_t i = 0; i < length; i++) { io->putc(p[i]); }
    for (uint32_t i = 0; i < 4U; i++) { io->putc(c[i]); }
}
