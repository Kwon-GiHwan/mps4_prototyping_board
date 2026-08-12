"""Generate PMU_COMPLETION_POLL_DIAG_V12 sources from frozen inputs."""

from __future__ import annotations

import argparse
import hashlib
import os

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"

_CANONICAL_VENDOR = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline void wait_for_irq(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        /* V12_STOCK_IRQ_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        /* V12_STOCK_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    /* V12_P0 */
    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        /* V12_HELPER_STATUS_READ */
        status = *status_reg;
        /* V12_HELPER_STATUS_TEST */
        if ((status & 0x02U) != 0U) {
            /* V12_P1 */
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            /* V12_P2 */
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }

    return 0U;
}

void test_u85(void)
{
    /* V12_RUNTIME_VECTOR_INSTALL */
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);

    /* V12_RUNTIME_NVIC_PREPARE */
    irq_triggered = false;
    /* V12_RUNTIME_DISABLE */
    NVIC_DisableIRQ(NPU0_IRQn);
    /* V12_RUNTIME_CLEAR_PENDING */
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    /* V12_RUNTIME_VECTOR_LOAD */
    pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);
    /* V12_RUNTIME_ENABLE_READ */
    pmu_completion_poll_v12_t_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
    /* V12_RUNTIME_PENDING_READ */
    pmu_completion_poll_v12_t_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    /* V12_RUNTIME_ACTIVE_READ */
    pmu_completion_poll_v12_t_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
    /* V12_RUNTIME_IRQ_TRIGGERED_READ */
    pmu_completion_poll_v12_t_irq_triggered_before_submit = irq_triggered ? 1U : 0U;

    if ((pmu_completion_poll_v12_t_nvic_enabled_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_nvic_pending_after_initial_clear != 0U) ||
        (pmu_completion_poll_v12_t_nvic_active_before_submit != 0U) ||
        (pmu_completion_poll_v12_t_irq_triggered_before_submit != 0U)) {
        return;
    }
}

void test_commands(void)
{
    uint32_t status_at_success;

    /* V12_SUBMIT_READ */
    read_val = read_reg(NPU_REG_CMD);
    /* V12_SUBMIT_WRITE */
    write_reg(NPU_REG_CMD, read_val | 0x00000001);
    /* V12_SUBMIT_T2 */
    pmu_completion_poll_v12_t_t2 = DWT->CYCCNT;

    /* V12_WAIT_CALL */
    status_at_success = v12_poll_completion();
    /* V12_WAIT_RESULT_STORE */
    pmu_completion_poll_v12_t_poll_result = (status_at_success & 0x02U) ? V12_POLL_SUCCESS : V12_POLL_TIMEOUT;

    if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {
        /* V12_SUCCESS_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_at_success >> 16);
        pmu_completion_poll_v12_t_poll_status_at_success = status_at_success;

        /* V12_SUCCESS_CMD2_1 */
        write_reg(NPU_REG_CMD, 0x00000002);

        /* V12_SUCCESS_QREAD_READ */
        read_val = read_reg(NPU_REG_QREAD);
        /* V12_SUCCESS_CMD2_2 */
        write_reg(NPU_REG_CMD, 0x00000002);
        if ((read_val & 0x0FU) == 0x03U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }
        if (pmu_completion_poll_v12_t_success_qread_verified == 1U) {
            pmu_completion_poll_v12_t_success_qread_verified = 1U;
        }

    } else {
        /* V12_TIMEOUT_REPORT */
        /* V12_TIMEOUT_TRIGGERED */
        irq_never_triggered = true;
        status_register = read_reg(NPU_REG_STATUS);
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n", status_register);

        /* V12_TIMEOUT_QREAD_READ */
        read_val = read_reg(NPU_REG_QREAD);
        if ((read_val & 0x0FU) == 0x03U) {
            pmu_completion_poll_v12_t_timeout_qread_verified = 1U;
        }

        /* V12_TIMEOUT_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }

v12_common_cleanup:
    /* common cleanup after both QREAD verification blocks */
    /* V12_FINAL_PENDING_BEFORE_CLEAR */
    pmu_completion_poll_v12_t_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);
    /* V12_FINAL_PENDING_AFTER_CLEAR */
    pmu_completion_poll_v12_t_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    /* V12_FINAL_ACTIVE_AFTER_CLEAR */
    pmu_completion_poll_v12_t_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
    /* V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR */
    pmu_completion_poll_v12_t_irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;

    /* V12_CMD0 */
    write_reg(NPU_REG_CMD, 0x00000000);
    if (TEST_CPM) {
        /* V12_HPRINTF_SEAM */
        printf("V12: completed\n");
    }

    /* V12_CMD0C */
    write_reg(NPU_REG_CMD, 0x0000000CU);
}

void u85_irq_handler(void)
{
    /* V12_ISR_STATUS_READ */
    status_register = read_reg(NPU_REG_STATUS);
    /* V12_ISR_TRIGGER_TEST */
    if ((status_register & 0x02U)) {
        /* V12_ISR_HISTORY_STORE */
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        /* V12_ISR_CMD2 */
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}
"""


class PatchError(RuntimeError):
    pass


def fail(message: str) -> PatchError:
    return PatchError("FAIL %s" % message)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def patch_runner(text: str) -> tuple[str, dict]:
    counts = {
        "schema_marker": 0,
        "build_id_marker": 0,
        "internal_snapshot_marker": 0,
    }
    if "PMU_COMPLETION_POLL_DIAG_V12" not in text:
        raise fail("runner is not the frozen V12 Chunk1 fixture yet")
    counts["schema_marker"] = text.count("PMU_COMPLETION_POLL_DIAG_V12")
    counts["build_id_marker"] = text.count("PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID")
    counts["internal_snapshot_marker"] = text.count("pmu_completion_poll_v12_internal_post_disable")
    return text, counts


def patch_vendor(text: str) -> tuple[str, dict]:
    required = (
        "#define BUSY_SLEEP",
        "#define VERIFY_OUTPUT 1",
        "#define TEST_CPM 1",
        "#define BUSY_SLEEP_TIMEOUT 10000",
        "void u85_irq_handler(void)",
        "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
        "write_reg(NPU_REG_CMD, read_val | 0x00000001);",
        "wait_for_irq();",
    )
    for needle in required:
        if needle not in text:
            raise fail("vendor fixture missing %r" % needle)
    counts = {
        "runtime_vector_install": 1,
        "helper_symbol": 1,
        "success_cmd2_count": 2,
        "timeout_cmd2_count": 1,
    }
    return _CANONICAL_VENDOR, counts


def _run(argv: list[str]) -> None:
    import subprocess

    subprocess.run(argv, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-in")
    parser.add_argument("--vendor-in")
    parser.add_argument("--runner-out")
    parser.add_argument("--vendor-out")
    parser.add_argument("--expect-runner-sha256", default=RUNNER_SHA256)
    parser.add_argument("--expect-vendor-sha256", default=VENDOR_SHA256)
    args = parser.parse_args(argv)

    if _sha256(args.runner_in) != args.expect_runner_sha256:
        raise fail("runner sha256 mismatch")
    if _sha256(args.vendor_in) != args.expect_vendor_sha256:
        raise fail("vendor sha256 mismatch")

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
