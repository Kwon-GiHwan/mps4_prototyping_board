/* CMSDK UART0 by register, non-blocking receive. The same UART (0x59303000, MLEK's UART0_BASE for mps4 sse-320 secure)
 * that MLEK's stdout already initialised at 115200 8N1; this module only moves bytes. */
#include "uart.h"

#include "mmio.h"

#define UART0_BASE   0x59303000U
#define UART_DATA    (UART0_BASE + 0x0U)
#define UART_STATE   (UART0_BASE + 0x4U)
#define STATE_TXBF   (1U << 0)
#define STATE_RXBF   (1U << 1)
#define STATE_RXOR   (1U << 3)

static uint32_t overruns;

int uart_getc(uint8_t *byte)
{
    uint32_t st = REG32(UART_STATE);
    if (st & STATE_RXOR) {
        overruns++;
        REG32(UART_STATE) = STATE_RXOR;   /* write-1-to-clear */
    }
    if ((st & STATE_RXBF) == 0U) { return 0; }
    *byte = (uint8_t)REG32(UART_DATA);
    return 1;
}

void uart_putc(uint8_t byte)
{
    while (REG32(UART_STATE) & STATE_TXBF) {
    }
    REG32(UART_DATA) = byte;
}

uint32_t uart_overruns(void) { return overruns; }
