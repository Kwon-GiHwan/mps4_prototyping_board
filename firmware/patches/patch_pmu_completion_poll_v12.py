"""Generate PMU_COMPLETION_POLL_DIAG_V12 sources from frozen inputs."""

from __future__ import annotations

import argparse
import hashlib
import os

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
SCHEMA_VERSION = 12
BUILD_ID = 0x32314950


class PatchError(SystemExit):
    pass


def fail(message: str) -> PatchError:
    return PatchError("FAIL %s" % message)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def sub_once(text: str, old: str, new: str, what: str) -> tuple[str, int]:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new), count


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


_RUNNER_SCHEMA_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif"""

_RUNNER_SCHEMA_V12 = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U
#define V12_POLL_SUCCESS 1U
#define V12_POLL_TIMEOUT 2U
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif"""

_RUNNER_EXTERN_STOCK = "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;\n"
_RUNNER_EXTERN_V12 = """static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
#if defined(PMU_QUAL_SCHEMA_V12)
extern volatile uint32_t pmu_completion_poll_v12_t_submit_after_cmd;
extern volatile uint32_t pmu_completion_poll_v12_t_poll_entry;
extern volatile uint32_t pmu_completion_poll_v12_t_status_completion_seen;
extern volatile uint32_t pmu_completion_poll_v12_t_poll_exit;
extern volatile uint32_t pmu_completion_poll_v12_t_poll_result;
extern volatile uint32_t pmu_completion_poll_v12_t_poll_status_at_success;
extern volatile uint32_t pmu_completion_poll_v12_t_installed_vector;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_enabled_before_submit;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_after_initial_clear;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_active_before_submit;
extern volatile uint32_t pmu_completion_poll_v12_t_irq_triggered_before_submit;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_before_final_clear;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_after_final_clear;
extern volatile uint32_t pmu_completion_poll_v12_t_nvic_active_after_cleanup;
extern volatile uint32_t pmu_completion_poll_v12_t_irq_triggered_after_cleanup;
#endif
"""

_RUNNER_RECORD_STOCK = """    pmu_diag_snapshot_t internal_pre_release;
    pmu_diag_snapshot_t internal_post_disable;
    pmu_diag_snapshot_t after_return;
#else
    pmu_diag_snapshot_t post;         /* after call, BEFORE disable         */
    pmu_diag_snapshot_t post_disable; /* after disable + DSB + readback     */
#endif"""

_RUNNER_RECORD_V12 = """    pmu_diag_snapshot_t internal_pre_release;
    pmu_diag_snapshot_t internal_post_disable;
    pmu_diag_snapshot_t after_return;
#if defined(PMU_QUAL_SCHEMA_V12)
    uint32_t t_submit_after_cmd;
    uint32_t t_poll_entry;
    uint32_t t_status_completion_seen;
    uint32_t t_poll_exit;
    uint32_t poll_result;
    uint32_t status_at_success;
    uint32_t installed_vector;
    uint32_t nvic_enabled_before_submit;
    uint32_t nvic_pending_after_initial_clear;
    uint32_t nvic_active_before_submit;
    uint32_t irq_triggered_before_submit;
    uint32_t nvic_pending_before_final_clear;
    uint32_t nvic_pending_after_final_clear;
    uint32_t nvic_active_after_cleanup;
    uint32_t irq_triggered_after_cleanup;
#endif
#else
    pmu_diag_snapshot_t post;         /* after call, BEFORE disable         */
    pmu_diag_snapshot_t post_disable; /* after disable + DSB + readback     */
#endif"""

_RUNNER_FIELD_COUNT_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif"""

_RUNNER_FIELD_COUNT_V12 = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 15U)
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif"""

_RUNNER_ASSERTS_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
/* The wire shape, asserted at compile time rather than trusted. The host
 * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch
 * here would otherwise surface as an unparseable board run. */
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_QUAL: a snapshot must be exactly 8 words on the wire");
_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,
               "PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,
               "PMU_QUAL: total is 8 header + 85 body = 93 words");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,
               "PMU_QUAL: payload is 93 * 4 = 372 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,
               "PMU_QUAL: the v8 record must declare schema version 8");
#endif"""

_RUNNER_ASSERTS_V12 = """#if defined(PMU_QUAL_SCHEMA_V12)
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_COMPLETION_POLL_DIAG_V12: snapshot must remain 8 words");
_Static_assert(PMU_DIAG_FIELD_COUNT == 100U,
               "PMU_COMPLETION_POLL_DIAG_V12: v8 body plus fifteen fields");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 108U,
               "PMU_COMPLETION_POLL_DIAG_V12: 8 header plus 100 body");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 432U,
               "PMU_COMPLETION_POLL_DIAG_V12: payload is 108 * 4 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 12U,
               "PMU_COMPLETION_POLL_DIAG_V12: schema must be 12");
_Static_assert(RUNNER_FIRMWARE_BUILD_ID == PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID,
               "PMU_COMPLETION_POLL_DIAG_V12: build id must be 0x32314950");
#elif defined(PMU_QUAL_SCHEMA_V8)
/* The wire shape, asserted at compile time rather than trusted. The host
 * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch
 * here would otherwise surface as an unparseable board run. */
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_QUAL: a snapshot must be exactly 8 words on the wire");
_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,
               "PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,
               "PMU_QUAL: total is 8 header + 85 body = 93 words");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,
               "PMU_QUAL: payload is 93 * 4 = 372 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,
               "PMU_QUAL: the v8 record must declare schema version 8");
#endif"""

_RUNNER_CLEAR_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
    /* Same freshness rule as the two result gates above, and for the same
     * reason: a hook count or an LR left over from the previous run would be
     * indistinguishable from this run's evidence. */
    pmu_qual_reset_hook_state();
#endif
"""

_RUNNER_CLEAR_V12 = """#if defined(PMU_QUAL_SCHEMA_V8)
    /* Same freshness rule as the two result gates above, and for the same
     * reason: a hook count or an LR left over from the previous run would be
     * indistinguishable from this run's evidence. */
    pmu_qual_reset_hook_state();
#endif
#if defined(PMU_QUAL_SCHEMA_V12)
    pmu_completion_poll_v12_t_submit_after_cmd              = 0U;
    pmu_completion_poll_v12_t_poll_entry                    = 0U;
    pmu_completion_poll_v12_t_status_completion_seen        = 0U;
    pmu_completion_poll_v12_t_poll_exit                     = 0U;
    pmu_completion_poll_v12_t_poll_result                   = V12_POLL_TIMEOUT;
    pmu_completion_poll_v12_t_poll_status_at_success        = 0U;
    pmu_completion_poll_v12_t_installed_vector              = 0U;
    pmu_completion_poll_v12_t_nvic_enabled_before_submit    = 0U;
    pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = 0U;
    pmu_completion_poll_v12_t_nvic_active_before_submit     = 0U;
    pmu_completion_poll_v12_t_irq_triggered_before_submit   = 0U;
    pmu_completion_poll_v12_t_nvic_pending_before_final_clear = 0U;
    pmu_completion_poll_v12_t_nvic_pending_after_final_clear  = 0U;
    pmu_completion_poll_v12_t_nvic_active_after_cleanup     = 0U;
    pmu_completion_poll_v12_t_irq_triggered_after_cleanup   = 0U;
#endif
"""

_RUNNER_SERIALIZE_STOCK = """    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->internal_pre_release);
    put_diag_snapshot(&c, &d->internal_post_disable);
    put_diag_snapshot(&c, &d->after_return);
#else
    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->post);
    put_diag_snapshot(&c, &d->post_disable);
#endif"""

_RUNNER_SERIALIZE_V12 = """    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->internal_pre_release);
    put_diag_snapshot(&c, &d->internal_post_disable);
    put_diag_snapshot(&c, &d->after_return);
#if defined(PMU_QUAL_SCHEMA_V12)
    put32(&c, d->t_submit_after_cmd);
    put32(&c, d->t_poll_entry);
    put32(&c, d->t_status_completion_seen);
    put32(&c, d->t_poll_exit);
    put32(&c, d->poll_result);
    put32(&c, d->status_at_success);
    put32(&c, d->installed_vector);
    put32(&c, d->nvic_enabled_before_submit);
    put32(&c, d->nvic_pending_after_initial_clear);
    put32(&c, d->nvic_active_before_submit);
    put32(&c, d->irq_triggered_before_submit);
    put32(&c, d->nvic_pending_before_final_clear);
    put32(&c, d->nvic_pending_after_final_clear);
    put32(&c, d->nvic_active_after_cleanup);
    put32(&c, d->irq_triggered_after_cleanup);
#endif
#else
    put_diag_snapshot(&c, &d->pre);
    put_diag_snapshot(&c, &d->post);
    put_diag_snapshot(&c, &d->post_disable);
#endif"""

_RUNNER_COPY_STOCK = """        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;
        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;
        d.internal_pre_release          = pmu_qual_internal_pre_release;
        d.internal_post_disable         = pmu_qual_internal_post_disable;
#else
        /* Post-call snapshot BEFORE the disable, cycle first -- contract. */
        pmu_diag_capture_post_order(&d.post);
"""

_RUNNER_COPY_V12 = """        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;
        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;
        d.internal_pre_release          = pmu_qual_internal_pre_release;
        d.internal_post_disable         = pmu_qual_internal_post_disable;
#if defined(PMU_QUAL_SCHEMA_V12)
        d.t_submit_after_cmd              = pmu_completion_poll_v12_t_submit_after_cmd;
        d.t_poll_entry                    = pmu_completion_poll_v12_t_poll_entry;
        d.t_status_completion_seen        = pmu_completion_poll_v12_t_status_completion_seen;
        d.t_poll_exit                     = pmu_completion_poll_v12_t_poll_exit;
        d.poll_result                     = pmu_completion_poll_v12_t_poll_result;
        d.status_at_success               = pmu_completion_poll_v12_t_poll_status_at_success;
        d.installed_vector                = pmu_completion_poll_v12_t_installed_vector;
        d.nvic_enabled_before_submit      = pmu_completion_poll_v12_t_nvic_enabled_before_submit;
        d.nvic_pending_after_initial_clear = pmu_completion_poll_v12_t_nvic_pending_after_initial_clear;
        d.nvic_active_before_submit       = pmu_completion_poll_v12_t_nvic_active_before_submit;
        d.irq_triggered_before_submit     = pmu_completion_poll_v12_t_irq_triggered_before_submit;
        d.nvic_pending_before_final_clear = pmu_completion_poll_v12_t_nvic_pending_before_final_clear;
        d.nvic_pending_after_final_clear  = pmu_completion_poll_v12_t_nvic_pending_after_final_clear;
        d.nvic_active_after_cleanup       = pmu_completion_poll_v12_t_nvic_active_after_cleanup;
        d.irq_triggered_after_cleanup     = pmu_completion_poll_v12_t_irq_triggered_after_cleanup;
        if (d.poll_result != V12_POLL_SUCCESS) {
            d.t_status_completion_seen = 0U;
            d.t_poll_exit              = 0U;
            d.status_at_success        = 0U;
        }
#endif
#else
        /* Post-call snapshot BEFORE the disable, cycle first -- contract. */
        pmu_diag_capture_post_order(&d.post);
"""

_VENDOR_DEFS_ANCHOR = "#define TEST_CPM 1"
_VENDOR_DEFS_V12 = """#define TEST_CPM 1

volatile uint32_t pmu_completion_poll_v12_t_submit_after_cmd;
volatile uint32_t pmu_completion_poll_v12_t_poll_entry;
volatile uint32_t pmu_completion_poll_v12_t_status_completion_seen;
volatile uint32_t pmu_completion_poll_v12_t_poll_exit;
volatile uint32_t pmu_completion_poll_v12_t_poll_result;
volatile uint32_t pmu_completion_poll_v12_t_poll_status_at_success;
volatile uint32_t pmu_completion_poll_v12_t_installed_vector;
volatile uint32_t pmu_completion_poll_v12_t_nvic_enabled_before_submit;
volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_after_initial_clear;
volatile uint32_t pmu_completion_poll_v12_t_nvic_active_before_submit;
volatile uint32_t pmu_completion_poll_v12_t_irq_triggered_before_submit;
volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_before_final_clear;
volatile uint32_t pmu_completion_poll_v12_t_nvic_pending_after_final_clear;
volatile uint32_t pmu_completion_poll_v12_t_nvic_active_after_cleanup;
volatile uint32_t pmu_completion_poll_v12_t_irq_triggered_after_cleanup;"""

_VENDOR_HELPER_ANCHOR = """static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{"""

_VENDOR_HELPER_V12 = """__attribute__((noinline))
static uint32_t v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status = 0U;

    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;
    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }

    return 0U;
}

static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{"""

_VENDOR_LOCALS_STOCK = """\tint ret_code;
    int read_val;

\t/* Init locals */
\tret_code =0;
\tread_val =0;
"""

_VENDOR_LOCALS_V12 = """\tint ret_code;
    int read_val;
    uint32_t status_at_success;

\t/* Init locals */
\tret_code =0;
\tread_val =0;
    status_at_success = 0U;
"""

_VENDOR_ENABLE_STOCK = "    NVIC_EnableIRQ(NPU0_IRQn);\n"
_VENDOR_ENABLE_V12 = """    irq_triggered = false;
    NVIC_DisableIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
    pmu_completion_poll_v12_t_irq_triggered_before_submit = irq_triggered ? 1U : 0U;

    if ((pmu_completion_poll_v12_t_installed_vector != (uint32_t)&u85_irq_handler) ||
        (pmu_completion_poll_v12_t_nvic_enabled_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_nvic_pending_after_initial_clear != 0U) ||
        (pmu_completion_poll_v12_t_nvic_active_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_irq_triggered_before_submit != 0U)) {
        return 1;
    }
"""

_VENDOR_COMMAND_STOCK = """\t  //Start NPU
\t  read_val = read_reg(NPU_REG_CMD);
\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);
\t  //Clear IRQ
\t  wait_for_irq();
\t  // Read QREAD register
\t  read_val = read_reg(NPU_REG_QREAD);
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  if(read_val == u32CmdQueueSize) {
\t    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t  }
\t  else {
\t    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t    ret_code = 1;
\t  }
\t  //Stop NPU
\t  write_reg(NPU_REG_CMD, 0x00000000);
\t  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
\t    printf("Testing CPM signals\\n");
\t    //Enable Program CLKQ and PWRQ interfaces
\t    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
\t    write_reg(NPU_REG_CMD, 0x0000000C);
#endif"""

_VENDOR_COMMAND_V12 = """\t  //Start NPU
\t  read_val = read_reg(NPU_REG_CMD);
\t  write_reg(NPU_REG_CMD, read_val | 0x00000001);
\t  pmu_completion_poll_v12_t_submit_after_cmd = DWT->CYCCNT;
\t  status_at_success = v12_poll_completion();
\t  pmu_completion_poll_v12_t_poll_result =
\t      V12_POLL_TIMEOUT - ((status_at_success & 0x02U) >> 1);
\t  if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {
\t    pmu_completion_poll_v12_t_poll_status_at_success = status_at_success;
\t    irq_history_mask = status_at_success >> 16;
\t    write_reg(NPU_REG_CMD, 0x00000002);
\t    read_val = read_reg(NPU_REG_QREAD);
\t    write_reg(NPU_REG_CMD, 0x00000002);
\t    if(read_val == u32CmdQueueSize) {
\t      printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t    }
\t    else {
\t      printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t      ret_code = 1;
\t    }
\t    goto v12_common_cleanup;
\t  }
\t  irq_never_triggered = true;
\t  printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\\n",
\t         read_reg(NPU_REG_STATUS));
\t  read_val = read_reg(NPU_REG_QREAD);
\t  write_reg(NPU_REG_CMD, 0x00000002);
\t  if(read_val == u32CmdQueueSize) {
\t    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \\n",u32CmdQueueSize);
\t  }
\t  else {
\t    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\\n",u32CmdQueueSize, read_val);
\t    ret_code = 1;
\t  }
v12_common_cleanup:
\t  pmu_completion_poll_v12_t_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
\t  NVIC_ClearPendingIRQ(NPU0_IRQn);
\t  pmu_completion_poll_v12_t_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
\t  pmu_completion_poll_v12_t_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
\t  pmu_completion_poll_v12_t_irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;
\t  //Stop NPU
\t  write_reg(NPU_REG_CMD, 0x00000000);
\t  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
\t    printf("Testing CPM signals\\n");
\t    //Enable Program CLKQ and PWRQ interfaces
\t    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
\t    write_reg(NPU_REG_CMD, 0x0000000C);
#endif"""


def patch_runner(text: str) -> tuple[str, dict[str, int]]:
    text = normalize_newlines(text)
    counts: dict[str, int] = {}
    if "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID" in text:
        raise fail("runner input already carries V12 build marker")
    text, counts["schema_version_branch"] = sub_once(
        text,
        _RUNNER_SCHEMA_STOCK,
        _RUNNER_SCHEMA_V12,
        "runner schema version branch",
    )
    text, counts["extern_v12_globals"] = sub_once(
        text,
        _RUNNER_EXTERN_STOCK,
        _RUNNER_EXTERN_V12,
        "runner V12 extern globals",
    )
    text, counts["record_append_fields"] = sub_once(
        text,
        _RUNNER_RECORD_STOCK,
        _RUNNER_RECORD_V12,
        "runner appended V12 wire fields",
    )
    text, counts["field_count_block"] = sub_once(
        text,
        _RUNNER_FIELD_COUNT_STOCK,
        _RUNNER_FIELD_COUNT_V12,
        "runner field count block",
    )
    text, counts["static_asserts"] = sub_once(
        text,
        _RUNNER_ASSERTS_STOCK,
        _RUNNER_ASSERTS_V12,
        "runner static asserts",
    )
    text, counts["reset_v12_globals"] = sub_once(
        text,
        _RUNNER_CLEAR_STOCK,
        _RUNNER_CLEAR_V12,
        "runner V12 reset globals",
    )
    text, counts["copy_v12_values"] = sub_once(
        text,
        _RUNNER_COPY_STOCK,
        _RUNNER_COPY_V12,
        "runner V12 record copy and timeout invalidation",
    )
    text, counts["serialize_v12_values"] = sub_once(
        text,
        _RUNNER_SERIALIZE_STOCK,
        _RUNNER_SERIALIZE_V12,
        "runner V12 serialization append",
    )
    return text, counts


def patch_vendor(text: str) -> tuple[str, dict[str, int]]:
    text = normalize_newlines(text)
    counts: dict[str, int] = {}
    if "v12_poll_completion(void)" in text:
        raise fail("vendor input already carries V12 helper")
    text, counts["global_defs"] = sub_once(
        text,
        _VENDOR_DEFS_ANCHOR,
        _VENDOR_DEFS_V12,
        "vendor V12 globals anchor",
    )
    text, counts["helper_insert"] = sub_once(
        text,
        _VENDOR_HELPER_ANCHOR,
        _VENDOR_HELPER_V12,
        "vendor V12 helper insertion",
    )
    text, counts["command_locals"] = sub_once(
        text,
        _VENDOR_LOCALS_STOCK,
        _VENDOR_LOCALS_V12,
        "vendor V12 command locals",
    )
    text, counts["runtime_enable_site"] = sub_once(
        text,
        _VENDOR_ENABLE_STOCK,
        _VENDOR_ENABLE_V12,
        "vendor V12 NVIC hard-bypass start block",
    )
    text, counts["command_wait_block"] = sub_once(
        text,
        _VENDOR_COMMAND_STOCK,
        _VENDOR_COMMAND_V12,
        "vendor V12 completion-poll command block",
    )
    return text, counts


def generate(runner_src: str, vendor_src: str, out_runner: str, out_vendor: str) -> dict[str, object]:
    if _sha256(runner_src) != RUNNER_SHA256:
        raise fail("runner hash mismatch")
    if _sha256(vendor_src) != VENDOR_SHA256:
        raise fail("vendor hash mismatch")
    with open(runner_src, "r", encoding="utf-8") as handle:
        runner = handle.read()
    with open(vendor_src, "r", encoding="utf-8") as handle:
        vendor = handle.read()
    runner_out, runner_counts = patch_runner(runner)
    vendor_out, vendor_counts = patch_vendor(vendor)
    os.makedirs(os.path.dirname(out_runner), exist_ok=True)
    os.makedirs(os.path.dirname(out_vendor), exist_ok=True)
    with open(out_runner, "w", encoding="utf-8") as handle:
        handle.write(runner_out)
    with open(out_vendor, "w", encoding="utf-8") as handle:
        handle.write(vendor_out)
    return {
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "runner_source_sha256": RUNNER_SHA256,
        "vendor_source_sha256": VENDOR_SHA256,
        "runner_patch_counts": runner_counts,
        "vendor_patch_counts": vendor_counts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-in", required=True)
    parser.add_argument("--vendor-in", required=True)
    parser.add_argument("--runner-out", required=True)
    parser.add_argument("--vendor-out", required=True)
    parser.add_argument("--expect-runner-sha256", default=RUNNER_SHA256)
    parser.add_argument("--expect-vendor-sha256", default=VENDOR_SHA256)
    args = parser.parse_args(argv)

    if _sha256(args.runner_in) != args.expect_runner_sha256:
        raise fail("runner hash mismatch")
    if _sha256(args.vendor_in) != args.expect_vendor_sha256:
        raise fail("vendor hash mismatch")

    with open(args.runner_in, "r", encoding="utf-8") as handle:
        runner_text = handle.read()
    with open(args.vendor_in, "r", encoding="utf-8") as handle:
        vendor_text = handle.read()

    runner_out, _ = patch_runner(runner_text)
    vendor_out, _ = patch_vendor(vendor_text)

    os.makedirs(os.path.dirname(args.runner_out), exist_ok=True)
    os.makedirs(os.path.dirname(args.vendor_out), exist_ok=True)
    with open(args.runner_out, "w", encoding="utf-8") as handle:
        handle.write(runner_out)
    with open(args.vendor_out, "w", encoding="utf-8") as handle:
        handle.write(vendor_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
