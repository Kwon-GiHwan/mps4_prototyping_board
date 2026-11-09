/* Record v2 serialisation (record.h). */
#include "record.h"

#include "frame.h"

static void wr32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

void record_serialise(const drv_record_t *r, uint32_t run_sequence, uint32_t valid_flags, uint32_t run_rc,
                      uint8_t *out)
{
    uint32_t w = RECORD_HEADER_WORDS, crc;
#define DRV_FIELD_PUT(name) wr32(out + 4U * w++, r->name);
    DRV_RECORD_FIELDS(DRV_FIELD_PUT)
#undef DRV_FIELD_PUT
    wr32(out, RECORD_MAGIC);
    wr32(out + 4, RECORD_ABI_VERSION);
    wr32(out + 8, RECORD_TOTAL_WORDS);
    wr32(out + 12, RECORD_HEADER_WORDS);
    wr32(out + 16, run_sequence);
    wr32(out + 20, valid_flags);
    wr32(out + 24, run_rc);
    /* words 4..end without word 7 (the CRC itself), as the v1 record and measurement_payload_crc() */
    crc = crc32_update(0xFFFFFFFFU, out + 16, 12U);
    crc = crc32_update(crc, out + 32, 4U * (RECORD_TOTAL_WORDS - RECORD_HEADER_WORDS)) ^ 0xFFFFFFFFU;
    wr32(out + 28, crc);
}
