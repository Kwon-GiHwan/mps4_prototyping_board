/*
 * raw_rx_main.c -- UART RX smoke test for the MPS4 FI101 board.
 *
 * Deliberately bypasses GetLine(), the Selftest CLI parser and every
 * higher-level buffering layer. Baud/enable configuration is done through the
 * normal driver so the hardware is set up exactly as the Selftest sets it up;
 * everything after that touches the CMSDK APB UART registers directly.
 *
 * Protocol (FPGA UART0, 115200 8N1):
 *   host  -> 55 AA 01 FE      board -> AA 55 01 FE                 (ping)
 *   host  -> 55 AA 02 FD      board -> AA 55 02 FD hi lo hi lo     (stats)
 *                                      rx_count[15:0], overruns[15:0]
 *
 * The CMSDK UART holds a single RX byte. STATE bit 3 (RXOR) latches when a
 * byte arrives before the previous one is read, so overruns are counted
 * rather than inferred.
 */

#include <stdint.h>

#include "Driver_USART.h"
#include "serial.h"

#define UART0_REGS ((volatile uint32_t *)0x59303000U)

#define REG_DATA  0U
#define REG_STATE 1U

#define STATE_TXBF (1U << 0) /* TX buffer full  */
#define STATE_RXBF (1U << 1) /* RX buffer full  */
#define STATE_RXOR (1U << 3) /* RX overrun      */

extern ARM_DRIVER_USART Driver_USART0;

static const uint8_t PING_REQ[4]  = {0x55, 0xAA, 0x01, 0xFE};
static const uint8_t PING_RESP[4] = {0xAA, 0x55, 0x01, 0xFE};
static const uint8_t STAT_REQ[4]  = {0x55, 0xAA, 0x02, 0xFD};
static const uint8_t STAT_RESP[4] = {0xAA, 0x55, 0x02, 0xFD};

static uint32_t rx_count;
static uint32_t overruns;

static void put_raw(uint8_t byte)
{
    while (UART0_REGS[REG_STATE] & STATE_TXBF) {
    }
    UART0_REGS[REG_DATA] = byte;
}

static void put_block(const uint8_t *data, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++) {
        put_raw(data[i]);
    }
}

int main(void)
{
    uint8_t window[4] = {0};

    /* Baud rate and TX/RX enable only -- no CLI, no line editing. */
    serial_init(&Driver_USART0, 115200);

    put_block((const uint8_t *)"RAWRX READY\n", 12);

    for (;;) {
        if (UART0_REGS[REG_STATE] & STATE_RXOR) {
            overruns++;
            UART0_REGS[REG_STATE] = STATE_RXOR; /* write-1-to-clear */
        }

        if (!(UART0_REGS[REG_STATE] & STATE_RXBF)) {
            continue;
        }

        uint8_t byte = (uint8_t)UART0_REGS[REG_DATA];
        rx_count++;

        window[0] = window[1];
        window[1] = window[2];
        window[2] = window[3];
        window[3] = byte;

        if (window[0] == PING_REQ[0] && window[1] == PING_REQ[1] &&
            window[2] == PING_REQ[2] && window[3] == PING_REQ[3]) {
            put_block(PING_RESP, 4);
        } else if (window[0] == STAT_REQ[0] && window[1] == STAT_REQ[1] &&
                   window[2] == STAT_REQ[2] && window[3] == STAT_REQ[3]) {
            put_block(STAT_RESP, 4);
            put_raw((uint8_t)(rx_count >> 8));
            put_raw((uint8_t)rx_count);
            put_raw((uint8_t)(overruns >> 8));
            put_raw((uint8_t)overruns);
        }
    }
}
