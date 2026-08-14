"""Generate PMU_COMPLETION_POLL_COUNT_DIAG_V13 sources from frozen raw inputs."""

from __future__ import annotations

import argparse
import pathlib

SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
POLL_LIMIT = 10000
POLL_REMAINING_INVALID = 0


class PatchError(RuntimeError):
    pass


def fail(message: str) -> PatchError:
    return PatchError("FAIL %s" % message)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1)


RUNNER_RAW_TARGET = """#if defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
}

void run_once(v13_t* d)
{
    d->t_pmu_disable = DWT->CYCCNT;
}
"""

RUNNER_V13 = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_SCHEMA_VERSION 13U
#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U
#define V13_POLL_SUCCESS 1U
#define V13_POLL_TIMEOUT 2U
#define PMU_DIAG_FIELD_COUNT 101U
#define PMU_DIAG_TOTAL_WORDS 109U
#define PMU_DIAG_PAYLOAD_SIZE 436U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
typedef struct {
    uint32_t poll_result;
    uint32_t poll_status_at_success;
    uint32_t poll_remaining_at_success;
} v13_wire_tail_t;
extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
    d->poll_result = V13_POLL_TIMEOUT;
    d->poll_status_at_success = 0U;
    d->poll_remaining_at_success = 0U;
}

void emit_record(v13_t* d, uint32_t *out_words)
{
    out_words[100] = d->poll_remaining_at_success;
}
"""

VENDOR_RAW_TARGET = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline uint32_t wait_for_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    for (uint32_t i = 0; i < 10000; ++i) {
        status = *status_reg;
        if (status & 0x02) {
            P1 = DWT;
            P2 = DWT;
            return status;
        }
    }

    return 0U;
}
"""

VENDOR_V13 = """uint32_t __attribute__((noinline)) v13_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t remaining = 10000U;
    uint32_t status;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (;;) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
            return status;
        }
        if (--remaining == 0U) {
            break;
        }
    }

    return 0U;
}
"""


def patch_runner(raw_runner_text: str) -> tuple[str, dict[str, object]]:
    text = normalize_newlines(raw_runner_text)
    if "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID" in text or "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID" in text:
        raise fail("generated runner input")
    if text.count(RUNNER_RAW_TARGET) != 1:
        raise fail("raw runner target count != 1")
    patched = replace_once(text, RUNNER_RAW_TARGET, RUNNER_V13, "raw runner target")
    return patched, {
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "poll_remaining_symbol": "pmu_completion_poll_v13_t_poll_remaining_at_success",
    }


def patch_vendor(raw_vendor_text: str) -> tuple[str, dict[str, object]]:
    text = normalize_newlines(raw_vendor_text)
    if "v12_poll_completion" in text or "v13_poll_completion" in text:
        raise fail("generated vendor input")
    if text.count(VENDOR_RAW_TARGET) != 1:
        raise fail("raw vendor target count != 1")
    patched = replace_once(text, VENDOR_RAW_TARGET, VENDOR_V13, "raw vendor target")
    return patched, {
        "helper_symbol": "v13_poll_completion",
        "poll_limit": POLL_LIMIT,
        "success_only_remaining_store": True,
    }


def _read_text(path: str) -> str:
    return pathlib.Path(path).read_text()


def _write_text(path: str, text: str) -> None:
    pathlib.Path(path).write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-in", required=True)
    parser.add_argument("--runner-out", required=True)
    parser.add_argument("--vendor-in", required=True)
    parser.add_argument("--vendor-out", required=True)
    args = parser.parse_args(argv)

    runner_out, _ = patch_runner(_read_text(args.runner_in))
    vendor_out, _ = patch_vendor(_read_text(args.vendor_in))
    _write_text(args.runner_out, runner_out)
    _write_text(args.vendor_out, vendor_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
