/* The driver runner's ports on the MLEK platform (runner.h): TFLM through MLEK's own TestModel (the inference_runner
 * path: TFLM ethos-u op -> ethosu_invoke_v3), MLEK's DDR placement, the D-cache MLEK enabled, and the read-back of
 * what the platform and the driver set (caps.h). MainLoop() is MLEK's entry into the use case (Main.cc). */
extern "C" {
#include "caps.h"
#include "probe.h"
#include "ethosu_driver.h"
#include "mmio.h"
#include "pmu_session.h"
#include "record.h"
#include "runner.h"
#include "timing.h"
#include "trace.h"
#include "uart.h"
}

#include "hal.h"
#include "mlek/fwk/tflm/TestModel.hpp"
#include "RTE_Components.h"

#include <cstring>
#include <new>

extern "C" struct ethosu_driver ethosu_drv;   /* MLEK ethosu_npu_init.c */

namespace {

/* MLEK mps4-sse-320.gnu.ld: DDR region 0x70000000, length 0x02000000; nn_model first, the arena after it. */
constexpr uintptr_t kModelBase = 0x70000000U;
constexpr uintptr_t kDdrLimit  = 0x72000000U;
/* Staging: DDR4 block 1 (secure 0x90000000; mem_regions.h -- another physical block than 0x70000000). The NPU never
 * reads it; the CPU copies the model out of it. */
uint8_t *const kStaging = reinterpret_cast<uint8_t *>(0x90000000U);
constexpr uint32_t kStagingSize = 0x04000000U;
constexpr uintptr_t kTaBase[2] = {0x51102000U, 0x51102400U};   /* MLEK mps4 CMakeLists TA_SRAM_BASE / TA_EXT_BASE */
constexpr uint32_t kTaOff[11] = {0x00U, 0x04U, 0x08U, 0x0CU, 0x10U, 0x14U, 0x18U, 0x1CU, 0x20U, 0x28U, 0x30U};
constexpr uint32_t kTaVersion = 0x38U;

using Model = arm::app::fwk::tflm::TestModel;
alignas(Model) uint8_t model_storage[sizeof(Model)];
Model *model = nullptr;

uint32_t npu(uint32_t off) { return REG32(reinterpret_cast<uintptr_t>(ethosu_drv.dev.reg) + off); }
bool dcache_enabled() { return (SCB->CCR & SCB_CCR_DC_Msk) != 0U; }

void place_model(uintptr_t dst, const uint8_t *src, uint32_t len)
{
    std::memcpy(reinterpret_cast<void *>(dst), src, len);
    if (dcache_enabled()) {
        SCB_CleanDCache();   /* the NPU reads the model from memory, not from the CPU's cache */
    }
}

uint32_t model_load(uintptr_t base, uint32_t len, uintptr_t arena, uint32_t arena_len)
{
    if (model != nullptr) {
        model->~Model();
        model = nullptr;
    }
    model = new (model_storage) Model();
    arm::app::fwk::iface::MemoryRegion compute{reinterpret_cast<uint8_t *>(arena), arena_len};
    arm::app::fwk::iface::MemoryRegion nn{reinterpret_cast<uint8_t *>(base), len};
    if (!model->Init(compute, nn)) { return 1U; }
    return model->ContainsEthosUOperator() ? 0U : 2U;
}

void model_counts(uint32_t *n_in, uint32_t *n_out)
{
    *n_in = static_cast<uint32_t>(model->GetNumInputs());
    *n_out = static_cast<uint32_t>(model->GetNumOutputs());
}

uint32_t model_io(uint32_t output, uint32_t index, uint8_t **ptr, uint32_t *len)
{
    auto t = output ? model->GetOutputTensor(index) : model->GetInputTensor(index);
    if (!t) { return 1U; }
    *ptr = t->GetData<uint8_t>();
    *len = static_cast<uint32_t>(t->Bytes());
    return 0U;
}

uint32_t invoke() { return model->RunInference() ? 1U : 0U; }
uint32_t dwt() { return read_timestamp(); }
uint32_t dcache_on() { return dcache_enabled() ? 1U : 0U; }

uint32_t capabilities(uint8_t *out, uint32_t max, uint32_t load_status)
{
#define CAPS_DECL(name) uint32_t name;
    struct { DRV_CAPS_FIELDS(CAPS_DECL) } c{};
#undef CAPS_DECL
    uint32_t *ta_sram = &c.ta_sram_maxr, *ta_ext = &c.ta_ext_maxr;
    c.magic = CAPS_MAGIC; c.schema = RECORD_SCHEMA; c.build_id = DRV_BUILD_ID; c.record_fields = RECORD_FIELD_COUNT;
    c.driver_version = (ETHOSU_DRIVER_VERSION_MAJOR << 16) | (ETHOSU_DRIVER_VERSION_MINOR << 8)
                       | ETHOSU_DRIVER_VERSION_PATCH;
    c.npu_id = npu(0x00U); c.npu_config = npu(0x28U); c.power_requests = ethosu_drv.power_request_counter;
    c.pmcr = npu(0x1180U); c.scb_ccr = SCB->CCR;
    c.fast_base = static_cast<uint32_t>(ethosu_drv.fast_memory);
    c.fast_size = static_cast<uint32_t>(ethosu_drv.fast_memory_size);
    c.model_base = kModelBase; c.ddr_limit = kDdrLimit;
    c.staging_base = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(kStaging)); c.staging_size = kStagingSize;
    c.arena_len = ACTIVATION_BUF_SZ; c.load_status = load_status;
    c.ta_sram_version = REG32(kTaBase[0] + kTaVersion); c.ta_ext_version = REG32(kTaBase[1] + kTaVersion);
    for (uint32_t k = 0; k < 11U; k++) {
        ta_sram[k] = REG32(kTaBase[0] + kTaOff[k]);
        ta_ext[k] = REG32(kTaBase[1] + kTaOff[k]);
    }
    c.cfg_sram_cap = npu(0x60U); c.cfg_ext_cap = npu(0x64U); c.axi_sram = npu(0x50U); c.axi_ext = npu(0x54U);
    c.mem_attr0 = npu(0x40U); c.mem_attr1 = npu(0x44U); c.mem_attr2 = npu(0x48U); c.mem_attr3 = npu(0x4CU);
    c.power_ctrl = npu(0x38U); c.regioncfg = npu(0x3CU); c.qconfig = npu(0x1CU);
    const uint32_t n = static_cast<uint32_t>(sizeof c);
    if (n > max) { return 0U; }
    std::memcpy(out, &c, n);   /* little-endian target: the struct is the wire format */
    return n;
}

const runner_ports_t ports = {kStaging, kStagingSize, kModelBase, kDdrLimit, ACTIVATION_BUF_SZ, place_model, model_load,
                              model_counts, model_io, invoke, dwt, dcache_on, uart_overruns, capabilities};
const frame_io_t uart_io = {uart_getc, uart_putc};

}  // namespace

void MainLoop()
{
    (void)timestamp_source_ready();
    hooks_install();
    pmu_session_bind(ethosu_drv.dev.reg);
    trace_bind(ethosu_drv.dev.reg, dwt);
    runner_init(&ports, &uart_io, DRV_BUILD_ID);
    for (;;) {
        (void)runner_poll();
    }
}
