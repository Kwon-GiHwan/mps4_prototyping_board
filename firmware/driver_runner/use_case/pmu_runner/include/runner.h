/* Driver runner core: protocol state machine and the measured RUN. Platform independent -- everything that touches
 * MLEK, TFLM, the driver or the board goes through runner_ports_t (platform.cc on target, fakes in the host tests). */
#ifndef DRV_RUNNER_H
#define DRV_RUNNER_H

#include <stdint.h>

#include "frame.h"

/* request ids (host/lib/runner_proto.py; the legacy runner uses the same ids for the same meaning) */
#define CMD_PING              0x01U
#define CMD_GET_STATE         0x02U
#define CMD_GET_CAPABILITIES  0x03U
#define CMD_SET_INSTRUMENTATION_MODE 0x05U
#define CMD_SET_RUN_OPTIONS   0x06U   /* driver runner only: wait mode, PMCCNTR_CFG */
#define CMD_LOAD_MODEL_BEGIN  0x10U
#define CMD_LOAD_MODEL_CHUNK  0x11U
#define CMD_LOAD_MODEL_END    0x12U
#define CMD_LOAD_INPUT        0x20U
#define CMD_RUN               0x30U
#define CMD_RUN_COMPLETE      0x31U
#define CMD_RESET_RUNNER      0x50U

/* NACK codes (the legacy runner's numbering) */
#define ERR_BAD_COMMAND    0x0002U
#define ERR_LENGTH         0x0003U
#define ERR_STATE          0x0005U
#define ERR_RANGE          0x0006U
#define ERR_CHUNK_MISMATCH 0x0007U
#define ERR_MODEL_CRC      0x0008U
#define ERR_PAYLOAD_FORMAT 0x0009U

#define INSTRUMENTATION_OFF    0U
#define INSTRUMENTATION_EVENTS 2U

typedef enum { ST_BOOT, ST_IDLE, ST_MODEL_LOADING, ST_MODEL_READY, ST_INPUT_READY, ST_RUNNING, ST_RESULT_READY,
               ST_COUNT } runner_state_t;

/* load status codes reported in a LOAD_MODEL_END NACK payload and in the capabilities */
#define LOAD_OK          0U
#define LOAD_BAD_DRWL    0x100U   /* + drwl_parse() code */
#define LOAD_NO_ROOM     0x200U
#define LOAD_MODEL_INIT  0x300U   /* + port code */
#define LOAD_IO_COUNT    0x400U
#define LOAD_IO_SIZE     0x500U

typedef struct {
    uint8_t *staging;
    uint32_t staging_size;
    uintptr_t model_base;           /* MLEK nn_model address */
    uintptr_t ddr_limit;            /* end of MLEK's DDR region */
    uint32_t arena_len;             /* MLEK ACTIVATION_BUF_SZ */
    void (*place_model)(uintptr_t dst, const uint8_t *src, uint32_t len);   /* copy + D-cache clean */
    uint32_t (*model_load)(uintptr_t model, uint32_t len, uintptr_t arena, uint32_t arena_len);   /* 0 = ok */
    void (*model_counts)(uint32_t *n_in, uint32_t *n_out);
    uint32_t (*model_io)(uint32_t output, uint32_t index, uint8_t **ptr, uint32_t *len);          /* 0 = ok */
    uint32_t (*invoke)(void);                                                                     /* 1 = ok */
    uint32_t (*dwt)(void);
    uint32_t (*dcache_on)(void);
    uint32_t (*rx_overruns)(void);
    uint32_t (*capabilities)(uint8_t *out, uint32_t max, uint32_t load_status);                   /* bytes */
} runner_ports_t;

void runner_init(const runner_ports_t *ports, const frame_io_t *io, uint32_t build_id);
/* Handles at most one request; returns 1 if one was handled. */
int runner_poll(void);
runner_state_t runner_state(void);

#endif
