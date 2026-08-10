"""Generate the v9 runner/vendor copies from pinned frozen inputs."""

from __future__ import annotations

import argparse
import hashlib
import os
import re

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"


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


def patch_runner(text: str) -> tuple[str, dict]:
    counts = {}
    text, counts["schema_version_branch"] = sub_once(
        text,
        "#if defined(PMU_QUAL_SCHEMA_V8)\n#define PMU_DIAG_SCHEMA_VERSION 8U\n#else\n#define PMU_DIAG_SCHEMA_VERSION 7U\n#endif",
        "#if defined(PMU_INTERVAL_DIAG_V9)\n#define PMU_DIAG_SCHEMA_VERSION 9U\n"
        "#elif defined(PMU_QUAL_SCHEMA_V8)\n#define PMU_DIAG_SCHEMA_VERSION 8U\n"
        "#else\n#define PMU_DIAG_SCHEMA_VERSION 7U\n#endif",
        "schema version branch",
    )
    text, counts["extern_checkpoint_globals"] = sub_once(
        text,
        "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;\n",
        "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;\n"
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "extern volatile uint32_t pmu_interval_v9_t_submit_before_cmd;\n"
        "extern volatile uint32_t pmu_interval_v9_t_submit_after_cmd;\n"
        "extern volatile uint32_t pmu_interval_v9_t_irq_status_seen;\n"
        "#endif\n",
        "runner extern checkpoint globals",
    )
    text, counts["private_driver_boundary"] = sub_once(
        text,
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)\n"
        "#error \"PMU_QUAL: schema v8 must link the reference vendor u85.c\"\n"
        "#endif",
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_INTERVAL_DIAG_V9)\n"
        "#error \"PMU_QUAL: schema v8 must link the reference vendor u85.c\"\n"
        "#endif",
        "v9 private-driver boundary",
    )
    text, counts["s1_s2_private_driver_boundary"] = sub_once(
        text,
        "#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)\n"
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)\n"
        "#error \"PMU_DIAG: S1/S2 must link the reference vendor u85.c\"\n"
        "#endif\n"
        "#endif",
        "#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)\n"
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_INTERVAL_DIAG_V9)\n"
        "#error \"PMU_DIAG: S1/S2 must link the reference vendor u85.c\"\n"
        "#endif\n"
        "#endif",
        "v9 S1/S2 private-driver boundary",
    )
    text, counts["record_append_fields"] = sub_once(
        text,
        "    pmu_diag_snapshot_t internal_post_disable;\n"
        "    pmu_diag_snapshot_t after_return;\n"
        "#else\n",
        "    pmu_diag_snapshot_t internal_post_disable;\n"
        "    pmu_diag_snapshot_t after_return;\n"
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "    uint32_t t_submit_before_cmd;\n"
        "    uint32_t t_submit_after_cmd;\n"
        "    uint32_t t_irq_status_seen;\n"
        "#endif\n"
        "#else\n",
        "runner appended fields",
    )
    text, counts["field_count_block"] = sub_once(
        text,
        "#if defined(PMU_QUAL_SCHEMA_V8)\n#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))\n#else\n#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))\n#endif",
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 3U)\n"
        "#elif defined(PMU_QUAL_SCHEMA_V8)\n"
        "#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))\n"
        "#else\n#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))\n#endif",
        "field count block",
    )
    text, counts["static_asserts"] = sub_once(
        text,
        "#if defined(PMU_QUAL_SCHEMA_V8)\n/* The wire shape, asserted at compile time rather than trusted. The host\n"
        " * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch\n"
        " * here would otherwise surface as an unparseable board run. */\n"
        "_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,\n"
        "               \"PMU_QUAL: a snapshot must be exactly 8 words on the wire\");\n"
        "_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,\n"
        "               \"PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words\");\n"
        "_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,\n"
        "               \"PMU_QUAL: total is 8 header + 85 body = 93 words\");\n"
        "_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,\n"
        "               \"PMU_QUAL: payload is 93 * 4 = 372 bytes\");\n"
        "_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,\n"
        "               \"PMU_QUAL: the v8 record must declare schema version 8\");\n#endif",
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,\n"
        "               \"PMU_INTERVAL_DIAG_V9: a snapshot must be exactly 8 words on the wire\");\n"
        "_Static_assert(PMU_DIAG_FIELD_COUNT == 88U,\n"
        "               \"PMU_INTERVAL_DIAG_V9: body is v8 plus three appended checkpoints\");\n"
        "_Static_assert(PMU_DIAG_TOTAL_WORDS == 96U,\n"
        "               \"PMU_INTERVAL_DIAG_V9: total is 8 header + 88 body = 96 words\");\n"
        "_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 384U,\n"
        "               \"PMU_INTERVAL_DIAG_V9: payload is 96 * 4 = 384 bytes\");\n"
        "_Static_assert(PMU_DIAG_SCHEMA_VERSION == 9U,\n"
        "               \"PMU_INTERVAL_DIAG_V9: the v9 record must declare schema version 9\");\n"
        "#elif defined(PMU_QUAL_SCHEMA_V8)\n"
        "/* The wire shape, asserted at compile time rather than trusted. The host\n"
        " * refuses anything that is not exactly 93 words / 372 bytes, so a mismatch\n"
        " * here would otherwise surface as an unparseable board run. */\n"
        "_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,\n"
        "               \"PMU_QUAL: a snapshot must be exactly 8 words on the wire\");\n"
        "_Static_assert(PMU_DIAG_FIELD_COUNT == 85U,\n"
        "               \"PMU_QUAL: body is 40 prefix + 13 hook + 4x8 snapshot = 85 words\");\n"
        "_Static_assert(PMU_DIAG_TOTAL_WORDS == 93U,\n"
        "               \"PMU_QUAL: total is 8 header + 85 body = 93 words\");\n"
        "_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 372U,\n"
        "               \"PMU_QUAL: payload is 93 * 4 = 372 bytes\");\n"
        "_Static_assert(PMU_DIAG_SCHEMA_VERSION == 8U,\n"
        "               \"PMU_QUAL: the v8 record must declare schema version 8\");\n"
        "#endif",
        "static asserts",
    )
    text, counts["clear_globals"] = sub_once(
        text,
        "#if defined(PMU_QUAL_SCHEMA_V8)\n    /* Same freshness rule as the two result gates above, and for the same\n"
        "     * reason: a hook count or an LR left over from the previous run would be\n"
        "     * indistinguishable from this run's evidence. */\n"
        "    pmu_qual_reset_hook_state();\n#endif\n",
        "#if defined(PMU_QUAL_SCHEMA_V8)\n    /* Same freshness rule as the two result gates above, and for the same\n"
        "     * reason: a hook count or an LR left over from the previous run would be\n"
        "     * indistinguishable from this run's evidence. */\n"
        "    pmu_qual_reset_hook_state();\n#endif\n"
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "    pmu_interval_v9_t_submit_before_cmd = 0U;\n"
        "    pmu_interval_v9_t_submit_after_cmd  = 0U;\n"
        "    pmu_interval_v9_t_irq_status_seen   = 0U;\n"
        "#endif\n",
        "clear v9 globals",
    )
    text, counts["serialize_append"] = sub_once(
        text,
        "    put_diag_snapshot(&c, &d->internal_post_disable);\n"
        "    put_diag_snapshot(&c, &d->after_return);\n"
        "#else\n",
        "    put_diag_snapshot(&c, &d->internal_post_disable);\n"
        "    put_diag_snapshot(&c, &d->after_return);\n"
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "    put32(&c, d->t_submit_before_cmd);\n"
        "    put32(&c, d->t_submit_after_cmd);\n"
        "    put32(&c, d->t_irq_status_seen);\n"
        "#endif\n"
        "#else\n",
        "serialize appended checkpoints",
    )
    text, counts["copy_record_values"] = sub_once(
        text,
        "        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;\n"
        "        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;\n"
        "        d.internal_pre_release          = pmu_qual_internal_pre_release;\n"
        "        d.internal_post_disable         = pmu_qual_internal_post_disable;\n",
        "        d.hook_pmu_mmio_read_count      = pmu_qual_hook_pmu_reads;\n"
        "        d.hook_pmu_mmio_write_count     = pmu_qual_hook_pmu_writes;\n"
        "        d.internal_pre_release          = pmu_qual_internal_pre_release;\n"
        "        d.internal_post_disable         = pmu_qual_internal_post_disable;\n"
        "#if defined(PMU_INTERVAL_DIAG_V9)\n"
        "        d.t_submit_before_cmd           = pmu_interval_v9_t_submit_before_cmd;\n"
        "        d.t_submit_after_cmd            = pmu_interval_v9_t_submit_after_cmd;\n"
        "        d.t_irq_status_seen             = pmu_interval_v9_t_irq_status_seen;\n"
        "#endif\n",
        "copy checkpoint globals into record",
    )
    return text, counts


def patch_vendor(text: str) -> tuple[str, dict]:
    counts = {}
    text, counts["global_defs"] = sub_once(
        text,
        "#define TEST_CPM 1",
        "#define TEST_CPM 1\n\n"
        "volatile uint32_t pmu_interval_v9_t_submit_before_cmd;\n"
        "volatile uint32_t pmu_interval_v9_t_submit_after_cmd;\n"
        "volatile uint32_t pmu_interval_v9_t_irq_status_seen;\n",
        "vendor checkpoint globals",
    )
    start_pat = re.compile(
        r"(?P<indent>[ \t]*)read_val\s*=\s*read_reg\s*\(\s*NPU_REG_CMD\s*\);\n"
        r"(?P=indent)write_reg\s*\(\s*NPU_REG_CMD\s*,(?P<value>[^;]+)\);\n"
        r"(?P<comment>[ \t]*//Clear IRQ\n)"
        r"(?P=indent)wait_for_irq\s*\(\s*\);",
        re.M,
    )
    match = start_pat.search(text)
    if not match:
        raise fail("vendor submit/write/wait sequence not found")
    repl = (
        f"{match.group('indent')}/* PMU_INTERVAL_V9_T1 */\n"
        f"{match.group('indent')}pmu_interval_v9_t_submit_before_cmd = DWT->CYCCNT;\n"
        f"{match.group('indent')}read_val = read_reg(NPU_REG_CMD);\n"
        f"{match.group('indent')}write_reg(NPU_REG_CMD,{match.group('value')});\n"
        f"{match.group('indent')}/* PMU_INTERVAL_V9_T2 */\n"
        f"{match.group('indent')}pmu_interval_v9_t_submit_after_cmd = DWT->CYCCNT;\n"
        f"{match.group('comment')}"
        f"{match.group('indent')}wait_for_irq();"
    )
    text = start_pat.sub(repl, text, count=1)
    counts["submit_wait_block"] = 1

    status_pat = re.compile(
        r"(?P<ifline>[ \t]*if\s*\(\(status_register\s*&\s*0x02\)\)\{\n)",
        re.M,
    )
    match = status_pat.search(text)
    if not match:
        raise fail("vendor ISR status/flag block not found")
    repl = (f"{match.group('ifline')}"
            "        /* PMU_INTERVAL_V9_T3 */\n"
            "        pmu_interval_v9_t_irq_status_seen = DWT->CYCCNT;\n")
    text = status_pat.sub(repl, text, count=1)
    counts["irq_status_block"] = 1
    return text, counts


def generate(runner_src: str, vendor_src: str, out_runner: str, out_vendor: str) -> dict:
    if _sha256(runner_src) != RUNNER_SHA256:
        raise fail("runner hash mismatch")
    if _sha256(vendor_src) != VENDOR_SHA256:
        raise fail("vendor hash mismatch")
    with open(runner_src) as handle:
        runner = handle.read()
    with open(vendor_src) as handle:
        vendor = handle.read()
    runner_out, runner_counts = patch_runner(runner)
    vendor_out, vendor_counts = patch_vendor(vendor)
    os.makedirs(os.path.dirname(out_runner), exist_ok=True)
    os.makedirs(os.path.dirname(out_vendor), exist_ok=True)
    with open(out_runner, "w") as handle:
        handle.write(runner_out)
    with open(out_vendor, "w") as handle:
        handle.write(vendor_out)
    return {
        "runner_sha256": RUNNER_SHA256,
        "vendor_sha256": VENDOR_SHA256,
        "runner_patch_counts": runner_counts,
        "vendor_patch_counts": vendor_counts,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner-src", required=True)
    ap.add_argument("--vendor-src", required=True)
    ap.add_argument("--out-runner", required=True)
    ap.add_argument("--out-vendor", required=True)
    args = ap.parse_args()
    result = generate(args.runner_src, args.vendor_src, args.out_runner, args.out_vendor)
    print(result)


if __name__ == "__main__":
    main()
