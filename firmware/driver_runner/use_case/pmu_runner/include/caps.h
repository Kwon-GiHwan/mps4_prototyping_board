/* GET_CAPABILITIES payload of the driver runner: what the MLEK platform and the driver actually set, read back from
 * the registers (TA, NPU AXI/MEM_ATTR/CAP/POWER_CTRL, PMU, cache) -- the R2 "settings applied" evidence. One u32 per
 * field in this order; host/lib/record_v2.py declares the same names (contract-tested). */
#ifndef DRV_CAPS_H
#define DRV_CAPS_H

#include <stdint.h>

#define CAPS_MAGIC 0x31435244U   /* 'DRC1' */

#define DRV_TA11(X, p) X(p##maxr) X(p##maxw) X(p##maxrw) X(p##rlatency) X(p##wlatency) X(p##pulse_on) \
    X(p##pulse_off) X(p##bwcap) X(p##perfctrl) X(p##mode) X(p##histbin)

#define DRV_CAPS_FIELDS(X) \
    X(magic) X(schema) X(build_id) X(record_fields) X(driver_version) X(npu_id) X(npu_config) X(power_requests) \
    X(pmcr) X(scb_ccr) X(fast_base) X(fast_size) X(model_base) X(ddr_limit) X(staging_base) X(staging_size) \
    X(arena_len) X(load_status) X(ta_sram_version) X(ta_ext_version) DRV_TA11(X, ta_sram_) DRV_TA11(X, ta_ext_) \
    X(cfg_sram_cap) X(cfg_ext_cap) X(axi_sram) X(axi_ext) X(mem_attr0) X(mem_attr1) X(mem_attr2) X(mem_attr3) \
    X(power_ctrl) X(regioncfg) X(qconfig)

#define DRV_CAPS_ONE(name) +1U
#define CAPS_FIELD_COUNT (0U DRV_CAPS_FIELDS(DRV_CAPS_ONE))

#endif
