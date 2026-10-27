/* Host protocol (proto.c): UART, CRC-32, frames, the state machine and the model/input/result commands. */
#ifndef RUNNER_PROTO_H
#define RUNNER_PROTO_H

#include <stdint.h>

/* ------------------------------------------------------------------------ */
/* UART0 -- direct CMSDK APB register access, exactly as runner_v1_main.c    */
/* ------------------------------------------------------------------------ */

#define UART0_REGS ((volatile uint32_t *)0x59303000U)

#define REG_DATA    0U /* 0x000 */
#define REG_STATE   1U /* 0x004 */
#define REG_CTRL    2U /* 0x008 */
#define REG_BAUDDIV 4U /* 0x010 */

#define STATE_TXBF (1U << 0) /* TX buffer full */
#define STATE_RXBF (1U << 1) /* RX buffer full */
#define STATE_TXOR (1U << 2) /* TX overrun, write-1-to-clear */
#define STATE_RXOR (1U << 3) /* RX overrun, write-1-to-clear */

extern ARM_DRIVER_USART Driver_USART0;

/* ------------------------------------------------------------------------ */
/* Protocol constants                                                        */
/* ------------------------------------------------------------------------ */

#define RUNNER_MAGIC   0x3152554EU /* "NUR1" little-endian: 4E 55 52 31 */
#define RUNNER_VERSION 1

#define RUNNER_HEADER_SIZE 16U
#define RUNNER_MAX_PAYLOAD 4096U

#define RESP_ACK_FLAG 0x80U
#define RESP_NACK_CMD 0xFFU

/* requests */
#define CMD_PING              0x01U
#define CMD_GET_STATE         0x02U
#define CMD_GET_CAPABILITIES  0x03U
#define CMD_GET_MEASUREMENT   0x04U
#define CMD_LOAD_MODEL_BEGIN  0x10U
#define CMD_LOAD_MODEL_CHUNK  0x11U
#define CMD_LOAD_MODEL_END    0x12U
#define CMD_LOAD_INPUT        0x20U
#define CMD_RUN               0x30U
#define CMD_GET_RESULT        0x40U
#define CMD_RESET_RUNNER      0x50U
#define CMD_SET_INSTRUMENTATION_MODE 0x05U

/* unsolicited */
#define CMD_RUN_COMPLETE 0x31U



/* ------------------------------------------------------------------------ */
/* TEST-ONLY COMMAND. Compiled in ONLY under -DRUNNER_TEST_ONLY_HOOKS.       */
/*                                                                           */
/* WHY IT EXISTS: INJECT_SKIP_NPU_EXECUTION is compile-time and skips EVERY  */
/* run, so an artifact built with it can never produce the sequence that      */
/* actually matters -- a SUCCESSFUL run followed by a FAILED run in the SAME  */
/* boot session. That pair is the only direct proof that the second run       */
/* cannot hand back the first run's CRC out of NOLOAD .sec_noinit.            */
/* CMD_TEST_SKIP_NEXT_NPU arms a ONE-SHOT skip, so a single image can do:     */
/*   RUN (real, succeeds) -> TEST_SKIP_NEXT_NPU -> RUN (skipped, fails)       */
/*                                                                           */
/* ID CHOICE 0x7E, and why it is not arbitrary:                              */
/*   - request ids must be <= 0x7F: an ACK is (request | RESP_ACK_FLAG 0x80). */
/*   - 0x7F is excluded: 0x7F | 0x80 == 0xFF == RESP_NACK_CMD, so its ACK     */
/*     would be indistinguishable from a NACK frame.                          */
/*   - 0x7E is therefore the highest usable id, deliberately far above every  */
/*     production id (max 0x50) and adjacent to the reserved top of the       */
/*     space. Its ACK is 0xFE, which collides with nothing.                   */
/*   - it is free: command_bit() maps no other command to it.                 */
/*                                                                           */
/* CONTAINMENT: check_measure_symbols.py FAILS any normal build in which      */
/* handle_test_skip_next_npu exists or is reachable from dispatch(), exactly  */
/* as it already does for the INJECT_SKIP_NPU marker. It cannot ship.         */
/* ------------------------------------------------------------------------ */

/* error codes, carried in the NACK header's flags field */
#define ERR_NONE           0x0000U
#define ERR_BAD_VERSION    0x0001U
#define ERR_BAD_COMMAND    0x0002U
#define ERR_LENGTH         0x0003U
#define ERR_BAD_CRC        0x0004U
#define ERR_STATE          0x0005U
#define ERR_RANGE          0x0006U
#define ERR_CHUNK_MISMATCH 0x0007U
#define ERR_MODEL_CRC      0x0008U
#define ERR_PAYLOAD_FORMAT 0x0009U
#define ERR_NO_MEASUREMENT 0x000AU
/* GET_RESULT refused because the latched result cannot be proven fresh.
 * DISTINCT from every other error precisely so the host can tell "the run did
 * not produce a trustworthy result" apart from "bad request". Returning this
 * is ALWAYS preferred to returning bytes that might be a previous run's. */
#define ERR_RESULT_NOT_VALID 0x000BU

/* A well-formed request for something this build does not implement --
 * distinct from BAD_COMMAND (unknown id) and from RANGE (out of bounds).
 * PER_LAYER instrumentation returns this. */
#define ERR_UNSUPPORTED      0x000CU

#define CRC32_INIT 0xFFFFFFFFU

/* Sequential little-endian writer, so a 38-field payload cannot acquire an
 * off-by-one offset bug during editing. */
typedef struct {
    uint8_t *base;
    uint32_t used;
} wcur_t;

typedef enum {
    ST_BOOT          = 0,
    ST_IDLE          = 1,
    ST_MODEL_LOADING = 2,
    ST_MODEL_READY   = 3,
    ST_INPUT_READY   = 4,
    ST_RUNNING       = 5,
    ST_RESULT_READY  = 6,
    ST_COUNT         = 7
} runner_state_t;

extern runner_state_t runner_state;
extern uint32_t rx_overrun_count;
extern uint32_t model_total_length;

uint32_t crc32_update(uint32_t crc, const void *data, uint32_t len);
uint32_t crc32_final(uint32_t crc);
uint32_t crc32_buffer(const void *data, uint32_t len);
uint32_t rd_u32(const uint8_t *p);
void wr_u32(uint8_t *p, uint32_t v);
void put32(wcur_t *c, uint32_t v);
void send_frame(uint8_t command, uint16_t flags, uint32_t sequence,
                const void *payload, uint32_t payload_length);
void send_ack(uint8_t request_command, uint32_t sequence,
              const void *payload, uint32_t payload_length);
void send_nack(uint8_t request_command, uint32_t sequence, uint16_t error);
void runner_reset_context(void);
void parse_one_frame(void);

#endif
