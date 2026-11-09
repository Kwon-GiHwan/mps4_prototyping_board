/* Wire frames of the runner protocol (the host's host/lib/runner_proto.py; the same format as the legacy runner):
 *   header  magic u32 'NUR1' | version u8 | command u8 | flags u16 | sequence u32 | payload length u32   (16 bytes)
 *   payload
 *   crc32   zlib CRC-32 over header and payload
 * An ACK is the request id | 0x80 with the request's sequence; a NACK is command 0xFF, flags = error code, payload
 * [request id, runner state]. Platform independent: bytes come and go through frame_io_t. */
#ifndef DRV_FRAME_H
#define DRV_FRAME_H

#include <stdint.h>

#define FRAME_MAGIC        0x3152554EU
#define FRAME_VERSION      1U
#define FRAME_HEADER_SIZE  16U
#define FRAME_MAX_PAYLOAD  4096U
#define FRAME_ACK_FLAG     0x80U
#define FRAME_NACK_CMD     0xFFU

typedef struct {
    int  (*getc)(uint8_t *byte);   /* 1 = a byte was read, 0 = none waiting */
    void (*putc)(uint8_t byte);
} frame_io_t;

typedef struct {
    uint8_t  command;
    uint16_t flags;
    uint32_t sequence;
    uint32_t length;
    uint8_t  payload[FRAME_MAX_PAYLOAD];
} frame_t;

typedef struct {
    uint32_t bad_magic, bad_version, bad_crc, length_error, resync;
} frame_errors_t;

uint32_t crc32_update(uint32_t crc, const void *data, uint32_t len);   /* crc starts at 0xFFFFFFFF, final ^ 0xFFFFFFFF */
uint32_t crc32_of(const void *data, uint32_t len);

/* Reads what is waiting; returns 1 when f holds one complete, CRC-checked frame. Never blocks. A candidate that fails
 * a check costs one byte and the search goes on (the UART may carry boot text). */
int frame_poll(const frame_io_t *io, frame_t *f, frame_errors_t *err);
void frame_send(const frame_io_t *io, uint8_t command, uint16_t flags, uint32_t sequence,
                const void *payload, uint32_t length);

#endif
