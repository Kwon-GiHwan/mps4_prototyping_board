/* The protocol's byte transport on UART0 (uart.c). */
#ifndef DRV_UART_H
#define DRV_UART_H

#include <stdint.h>

int uart_getc(uint8_t *byte);
void uart_putc(uint8_t byte);
uint32_t uart_overruns(void);

#endif
