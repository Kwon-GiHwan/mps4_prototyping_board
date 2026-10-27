/* Raw 32-bit MMIO access, shared by every module that touches a device register. */
#ifndef COMMON_MMIO_H
#define COMMON_MMIO_H

#include <stdint.h>

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))

#endif
