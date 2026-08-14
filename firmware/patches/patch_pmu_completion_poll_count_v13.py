"""Generate PMU_COMPLETION_POLL_COUNT_DIAG_V13 sources from frozen inputs."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from patches import patch_pmu_completion_poll_v12 as v12
else:
    from patches import patch_pmu_completion_poll_v12 as v12

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
POLL_REMAINING_INVALID = 0


class PatchError(SystemExit):
    pass


def fail(message: str) -> PatchError:
    return PatchError("FAIL %s" % message)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sub_once(text: str, old: str, new: str, what: str) -> tuple[str, int]:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1), count


def _rename_v12_identity(text: str) -> str:
    return (
        text.replace("PMU_COMPLETION_POLL_DIAG_V12", "PMU_COMPLETION_POLL_DIAG_V13")
        .replace("PMU_QUAL_SCHEMA_V12", "PMU_QUAL_SCHEMA_V13")
        .replace("pmu_completion_poll_v12", "pmu_completion_poll_v13")
        .replace("V12_", "V13_")
        .replace("schema must be 12", "schema must be 13")
        .replace("0x32314950", "0x33314950")
    )


_RUNNER_SCHEMA_V13 = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_SCHEMA_VERSION 13U
#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U
#define V13_POLL_SUCCESS 1U
#define V13_POLL_TIMEOUT 2U
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_SCHEMA_VERSION 8U
#else
#define PMU_DIAG_SCHEMA_VERSION 7U
#endif"""

_RUNNER_EXTERN_V13 = _rename_v12_identity(v12._RUNNER_EXTERN_V12).replace(
    "extern volatile uint32_t pmu_completion_poll_v13_t_poll_status_at_success;\n",
    "extern volatile uint32_t pmu_completion_poll_v13_t_poll_status_at_success;\n"
    "extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;\n",
    1,
)

_RUNNER_RECORD_V13 = _rename_v12_identity(v12._RUNNER_RECORD_V12).replace(
    "    uint32_t irq_triggered_after_cleanup;\n",
    "    uint32_t irq_triggered_after_cleanup;\n"
    "    uint32_t poll_remaining_at_success;\n",
    1,
)

_RUNNER_FIELD_COUNT_V13 = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 16U)
#elif defined(PMU_QUAL_SCHEMA_V8)
#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))
#else
#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))
#endif"""

_RUNNER_ASSERTS_V13 = """#if defined(PMU_QUAL_SCHEMA_V13)
_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: snapshot must remain 8 words");
_Static_assert(PMU_DIAG_FIELD_COUNT == 101U,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: v12 body plus one remaining word");
_Static_assert(PMU_DIAG_TOTAL_WORDS == 109U,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: 8 header plus 101 body");
_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 436U,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: payload is 109 * 4 bytes");
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 13U,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: schema must be 13");
_Static_assert(RUNNER_FIRMWARE_BUILD_ID == PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID,
               "PMU_COMPLETION_POLL_COUNT_DIAG_V13: build id must be 0x33314950");
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

_RUNNER_PRIVATE_DRIVER_SEAM_V13 = _rename_v12_identity(v12._RUNNER_PRIVATE_DRIVER_SEAM_V12)
_RUNNER_PRIVATE_DRIVER_V13 = _rename_v12_identity(v12._RUNNER_PRIVATE_DRIVER_V12)

_RUNNER_CLEAR_V13 = _rename_v12_identity(v12._RUNNER_CLEAR_V12).replace(
    "    pmu_completion_poll_v13_t_poll_status_at_success        = 0U;\n",
    "    pmu_completion_poll_v13_t_poll_status_at_success        = 0U;\n"
    "    pmu_completion_poll_v13_t_poll_remaining_at_success     = 0U;\n",
    1,
)

_RUNNER_SERIALIZE_V13 = _rename_v12_identity(v12._RUNNER_SERIALIZE_V12).replace(
    "    put32(&c, d->irq_triggered_after_cleanup);\n",
    "    put32(&c, d->irq_triggered_after_cleanup);\n"
    "    put32(&c, d->poll_remaining_at_success);\n",
    1,
)

_RUNNER_COPY_V13 = _rename_v12_identity(v12._RUNNER_COPY_V12).replace(
    "        d.irq_triggered_after_cleanup     = pmu_completion_poll_v13_t_irq_triggered_after_cleanup;\n",
    "        d.irq_triggered_after_cleanup     = pmu_completion_poll_v13_t_irq_triggered_after_cleanup;\n"
    "        d.poll_remaining_at_success       = pmu_completion_poll_v13_t_poll_remaining_at_success;\n",
    1,
).replace(
    "            d.status_at_success        = 0U;\n",
    "            d.status_at_success        = 0U;\n"
    "            d.poll_remaining_at_success = 0U;\n",
    1,
)

_VENDOR_DEFS_V13 = _rename_v12_identity(v12._VENDOR_DEFS_V12).replace(
    "volatile uint32_t pmu_completion_poll_v13_t_poll_status_at_success;\n",
    "volatile uint32_t pmu_completion_poll_v13_t_poll_status_at_success;\n"
    "volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;\n",
    1,
)

_VENDOR_HELPER_V13 = """__attribute__((noinline))
static uint32_t v13_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status = 0U;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;
    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U - i;
            return status;
        }
    }

    return 0U;
}

__attribute__((noinline))
static int test_commands( const u85_eTest eTest,
\t\t                  const uint32_t u32CmdQueueSize,
\t\t                  struct u85_warp_data_t *pu85_warp_data_st)
{"""

_VENDOR_LOCALS_V13 = _rename_v12_identity(v12._VENDOR_LOCALS_V12)
_VENDOR_ENABLE_V13 = _rename_v12_identity(v12._VENDOR_ENABLE_V12)
_VENDOR_COMMAND_V13 = _rename_v12_identity(v12._VENDOR_COMMAND_V12).replace(
    "\t  status_at_success = v12_poll_completion();\n",
    "\t  status_at_success = v13_poll_completion();\n",
    1,
).replace(
    "\t    goto v12_common_cleanup;\n",
    "\t    goto v13_common_cleanup;\n",
    1,
).replace(
    "v12_common_cleanup:\n",
    "v13_common_cleanup:\n",
    1,
)


def patch_runner(text: str) -> tuple[str, dict[str, int]]:
    text = normalize_newlines(text)
    if "PMU_INTERVAL_ENTRY_DIAG_V11A" in text or "pmu_interval_v11a_" in text:
        raise fail("runner input already carries V11 marker")
    if "PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID" in text:
        raise fail("runner input already carries V13 build marker")
    if "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID" in text:
        raise fail("runner input already carries V12 build marker")
    counts: dict[str, int] = {}
    runner_v13, counts["schema_version_branch"] = sub_once(
        text,
        v12._RUNNER_SCHEMA_STOCK,
        _RUNNER_SCHEMA_V13,
        "runner schema version branch",
    )
    runner_v13, counts["extern_v13_globals"] = sub_once(
        runner_v13,
        v12._RUNNER_EXTERN_STOCK,
        _RUNNER_EXTERN_V13,
        "runner V13 extern globals",
    )
    runner_v13, counts["record_append_fields"] = sub_once(
        runner_v13,
        v12._RUNNER_RECORD_STOCK,
        _RUNNER_RECORD_V13,
        "runner appended V13 wire fields",
    )
    runner_v13, counts["field_count_block"] = sub_once(
        runner_v13,
        v12._RUNNER_FIELD_COUNT_STOCK,
        _RUNNER_FIELD_COUNT_V13,
        "runner V13 field count block",
    )
    runner_v13, counts["static_asserts"] = sub_once(
        runner_v13,
        v12._RUNNER_ASSERTS_STOCK,
        _RUNNER_ASSERTS_V13,
        "runner V13 static asserts",
    )
    runner_v13, counts["private_driver_seam_exemption"] = sub_once(
        runner_v13,
        v12._RUNNER_PRIVATE_DRIVER_SEAM_STOCK,
        _RUNNER_PRIVATE_DRIVER_SEAM_V13,
        "runner V13 private-driver seam exemption",
    )
    runner_v13, counts["private_driver_v8_exemption"] = sub_once(
        runner_v13,
        v12._RUNNER_PRIVATE_DRIVER_V8_STOCK,
        _RUNNER_PRIVATE_DRIVER_V13,
        "runner V13 private-driver v8 exemption",
    )
    runner_v13, counts["reset_v13_globals"] = sub_once(
        runner_v13,
        v12._RUNNER_CLEAR_STOCK,
        _RUNNER_CLEAR_V13,
        "runner V13 reset globals",
    )
    runner_v13, counts["copy_v13_values"] = sub_once(
        runner_v13,
        v12._RUNNER_COPY_STOCK,
        _RUNNER_COPY_V13,
        "runner V13 record copy and timeout invalidation",
    )
    runner_v13, counts["serialize_v13_values"] = sub_once(
        runner_v13,
        v12._RUNNER_SERIALIZE_STOCK,
        _RUNNER_SERIALIZE_V13,
        "runner V13 serialization append",
    )
    return runner_v13, counts


def patch_vendor(text: str) -> tuple[str, dict[str, int]]:
    text = normalize_newlines(text)
    if "PMU_INTERVAL_ENTRY_DIAG_V11A" in text or "pmu_interval_v11a_" in text or "v11a_u85_irq_entry_veneer" in text:
        raise fail("vendor input already carries V11 marker")
    if "v13_poll_completion(void)" in text:
        raise fail("vendor input already carries V13 helper")
    if "v12_poll_completion(void)" in text:
        raise fail("vendor input already carries V12 helper")
    counts: dict[str, int] = {}
    vendor_v13, counts["global_defs"] = sub_once(
        text,
        v12._VENDOR_DEFS_ANCHOR,
        _VENDOR_DEFS_V13,
        "vendor V13 globals anchor",
    )
    vendor_v13, counts["helper_insert"] = sub_once(
        vendor_v13,
        v12._VENDOR_HELPER_ANCHOR,
        _VENDOR_HELPER_V13,
        "vendor V13 helper insertion",
    )
    vendor_v13, counts["command_locals"] = sub_once(
        vendor_v13,
        v12._VENDOR_LOCALS_STOCK,
        _VENDOR_LOCALS_V13,
        "vendor V13 command locals",
    )
    vendor_v13, counts["runtime_enable_site"] = sub_once(
        vendor_v13,
        v12._VENDOR_ENABLE_STOCK,
        _VENDOR_ENABLE_V13,
        "vendor V13 NVIC hard-bypass start block",
    )
    vendor_v13, counts["command_wait_block"] = sub_once(
        vendor_v13,
        v12._VENDOR_COMMAND_STOCK,
        _VENDOR_COMMAND_V13,
        "vendor V13 completion-poll command block",
    )
    return vendor_v13, counts


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
        "poll_remaining_invalid": POLL_REMAINING_INVALID,
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
