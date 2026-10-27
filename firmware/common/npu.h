/* Ethos-U85 register map used by the runner and the study images, and the two accessors.
 * Base and offsets as the vendor driver uses them (Drivers/u85_driver/u85.c, interface.h). */
#ifndef COMMON_NPU_H
#define COMMON_NPU_H

#include <stdint.h>
#include "mmio.h"

/* ------------------------------------------------------------------------ */
/* NPU -- same base and offsets the frozen driver uses                       */
/* Drivers/u85_driver/u85.c:  #define U85_BASE_ADDRESS 0x50004000            */
/* Drivers/u85_driver/interface.h: ID 0x00, STATUS 0x04, CMD 0x08,           */
/*                                 QREAD 0x18, CONFIG 0x28                   */
/* ------------------------------------------------------------------------ */

#define U85_BASE_ADDRESS 0x50004000U
#define NPU_OFF_ID       0x00U
#define NPU_OFF_STATUS   0x04U
#define NPU_OFF_QREAD    0x18U
#define NPU_OFF_CONFIG   0x28U
#define NPU_OFF_CMD 0x08U /* BASE.CMD; bits [3:2] = clock-Q / power-Q enables, 0 = hold */
#define NPU_OFF_POWER_CTRL 0x38U /* interface.h NPU_REG_POWER_CTRL */
#define NPU_OFF_REGIONCFG 0x3CU
#define NPU_OFF_QCONFIG   0x1CU /* interface.h NPU_REG_QCONFIG */
#define NPU_OFF_MEM_ATTR0 0x40U
#define NPU_OFF_AXI_SRAM  0x50U /* interface.h NPU_REG_AXI_SRAM */
#define NPU_OFF_AXI_EXT   0x54U /* interface.h NPU_REG_AXI_EXT  */

static inline uint32_t npu_read(uint32_t offset)
{
    return REG32(U85_BASE_ADDRESS + offset);
}

static inline void npu_write(uint32_t offset, uint32_t value)
{
    REG32(U85_BASE_ADDRESS + offset) = value;
}

#endif
