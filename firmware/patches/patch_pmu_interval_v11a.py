"""Generate PMU_INTERVAL_ENTRY_DIAG_V11A sources from frozen runner/vendor inputs."""

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
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n#define PMU_DIAG_SCHEMA_VERSION 11U\n"
        "#elif defined(PMU_QUAL_SCHEMA_V8)\n#define PMU_DIAG_SCHEMA_VERSION 8U\n"
        "#else\n#define PMU_DIAG_SCHEMA_VERSION 7U\n#endif",
        "schema version branch",
    )
    text, counts["extern_checkpoint_globals"] = sub_once(
        text,
        "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;\n",
        "static pmu_diag_snapshot_t pmu_qual_internal_post_disable;\n"
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "extern volatile uint32_t pmu_interval_v10_t_submit_before_cmd;\n"
        "extern volatile uint32_t pmu_interval_v10_t_submit_after_cmd;\n"
        "extern volatile uint32_t pmu_interval_v11a_t_vector_probe;\n"
        "extern volatile uint32_t pmu_interval_v10_t_irq_handler_entry;\n"
        "extern volatile uint32_t pmu_interval_v10_t_irq_status_seen;\n"
        "extern volatile uint32_t pmu_interval_v10_i0_hit_count;\n"
        "extern volatile uint32_t pmu_interval_v10_t3_hit_count;\n"
        "#endif\n",
        "runner extern checkpoint globals",
    )
    text, counts["private_driver_boundary"] = sub_once(
        text,
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)\n"
        "#error \"PMU_QUAL: schema v8 must link the reference vendor u85.c\"\n"
        "#endif",
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "#error \"PMU_QUAL: schema v8 must link the reference vendor u85.c\"\n"
        "#endif",
        "v11a private-driver boundary",
    )
    text, counts["s1_s2_private_driver_boundary"] = sub_once(
        text,
        "#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)\n"
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER)\n"
        "#error \"PMU_DIAG: S1/S2 must link the reference vendor u85.c\"\n"
        "#endif\n"
        "#endif",
        "#if defined(PMU_DIAG_SEAM_S1) || defined(PMU_DIAG_SEAM_S2)\n"
        "#if defined(PMU_DIAG_USES_PRIVATE_DRIVER) && !defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "#error \"PMU_DIAG: S1/S2 must link the reference vendor u85.c\"\n"
        "#endif\n"
        "#endif",
        "v11a S1/S2 private-driver boundary",
    )
    text, counts["record_append_fields"] = sub_once(
        text,
        "    pmu_diag_snapshot_t internal_post_disable;\n"
        "    pmu_diag_snapshot_t after_return;\n"
        "#else\n",
        "    pmu_diag_snapshot_t internal_post_disable;\n"
        "    pmu_diag_snapshot_t after_return;\n"
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "    uint32_t t_submit_before_cmd;\n"
        "    uint32_t t_submit_after_cmd;\n"
        "    uint32_t t_vector_probe;\n"
        "    uint32_t t_irq_handler_entry;\n"
        "    uint32_t t_irq_status_seen;\n"
        "    uint32_t i0_hit_count;\n"
        "    uint32_t t3_hit_count;\n"
        "#endif\n"
        "#else\n",
        "runner appended fields",
    )
    text, counts["field_count_block"] = sub_once(
        text,
        "#if defined(PMU_QUAL_SCHEMA_V8)\n#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS))\n#else\n#define PMU_DIAG_FIELD_COUNT (40U + (3U * PMU_DIAG_SNAPSHOT_WORDS))\n#endif",
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "#define PMU_DIAG_FIELD_COUNT (40U + 13U + (4U * PMU_DIAG_SNAPSHOT_WORDS) + 7U)\n"
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
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "_Static_assert(sizeof(pmu_diag_snapshot_t) == PMU_DIAG_SNAPSHOT_WORDS * 4U,\n"
        "               \"PMU_INTERVAL_ENTRY_DIAG_V11A: snapshot must be 8 words\");\n"
        "_Static_assert(PMU_DIAG_FIELD_COUNT == 92U,\n"
        "               \"PMU_INTERVAL_ENTRY_DIAG_V11A: v8 body plus seven fields\");\n"
        "_Static_assert(PMU_DIAG_TOTAL_WORDS == 100U,\n"
        "               \"PMU_INTERVAL_ENTRY_DIAG_V11A: 8 header plus 92 body\");\n"
        "_Static_assert(PMU_DIAG_PAYLOAD_SIZE == 400U,\n"
        "               \"PMU_INTERVAL_ENTRY_DIAG_V11A: payload is 400 bytes\");\n"
        "_Static_assert(PMU_DIAG_SCHEMA_VERSION == 11U,\n"
        "               \"PMU_INTERVAL_ENTRY_DIAG_V11A: schema must be 11\");\n"
        "#elif defined(PMU_QUAL_SCHEMA_V8)\n/* The wire shape, asserted at compile time rather than trusted. The host\n"
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
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "    pmu_interval_v10_t_submit_before_cmd = 0U;\n"
        "    pmu_interval_v10_t_submit_after_cmd  = 0U;\n"
        "    pmu_interval_v11a_t_vector_probe     = 0U;\n"
        "    pmu_interval_v10_t_irq_handler_entry = 0U;\n"
        "    pmu_interval_v10_t_irq_status_seen   = 0U;\n"
        "    pmu_interval_v10_i0_hit_count        = 0U;\n"
        "    pmu_interval_v10_t3_hit_count        = 0U;\n"
        "#endif\n",
        "clear v11a globals",
    )
    text, counts["serialize_append"] = sub_once(
        text,
        "    put_diag_snapshot(&c, &d->internal_post_disable);\n"
        "    put_diag_snapshot(&c, &d->after_return);\n"
        "#else\n",
        "    put_diag_snapshot(&c, &d->internal_post_disable);\n"
        "    put_diag_snapshot(&c, &d->after_return);\n"
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "    put32(&c, d->t_submit_before_cmd);\n"
        "    put32(&c, d->t_submit_after_cmd);\n"
        "    put32(&c, d->t_vector_probe);\n"
        "    put32(&c, d->t_irq_handler_entry);\n"
        "    put32(&c, d->t_irq_status_seen);\n"
        "    put32(&c, d->i0_hit_count);\n"
        "    put32(&c, d->t3_hit_count);\n"
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
        "#if defined(PMU_INTERVAL_ENTRY_DIAG_V11A)\n"
        "        d.t_submit_before_cmd           = pmu_interval_v10_t_submit_before_cmd;\n"
        "        d.t_submit_after_cmd            = pmu_interval_v10_t_submit_after_cmd;\n"
        "        d.t_vector_probe                = pmu_interval_v11a_t_vector_probe;\n"
        "        d.t_irq_handler_entry           = pmu_interval_v10_t_irq_handler_entry;\n"
        "        d.t_irq_status_seen             = pmu_interval_v10_t_irq_status_seen;\n"
        "        d.i0_hit_count                  = pmu_interval_v10_i0_hit_count;\n"
        "        d.t3_hit_count                  = pmu_interval_v10_t3_hit_count;\n"
        "#endif\n",
        "copy checkpoint globals into record",
    )
    return text, counts


def patch_vendor(text: str) -> tuple[str, dict]:
    counts = {}
    text, counts["j0_global_defs"] = sub_once(
        text,
        "#define TEST_CPM 1",
        "#define TEST_CPM 1\n\n"
        "volatile uint32_t pmu_interval_v10_t_submit_before_cmd;\n"
        "volatile uint32_t pmu_interval_v10_t_submit_after_cmd;\n"
        "volatile uint32_t pmu_interval_v11a_t_vector_probe;\n"
        "volatile uint32_t pmu_interval_v10_t_irq_handler_entry;\n"
        "volatile uint32_t pmu_interval_v10_t_irq_status_seen;\n"
        "volatile uint32_t pmu_interval_v10_i0_hit_count;\n"
        "volatile uint32_t pmu_interval_v10_t3_hit_count;\n",
        "vendor checkpoint globals",
    )
    text, counts["veneer_extern_decl"] = sub_once(
        text,
        "#define BUSY_SLEEP_TIMEOUT 10000",
        "#define BUSY_SLEEP_TIMEOUT 10000\n"
        "extern void v11a_u85_irq_entry_veneer(void);",
        "veneer extern declaration",
    )
    text, counts["runtime_vector_install"] = sub_once(
        text,
        "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
        "NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);",
        "runtime vector install",
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
    text = start_pat.sub(
        f"{match.group('indent')}/* PMU_INTERVAL_V10_T1 */\n"
        f"{match.group('indent')}pmu_interval_v10_t_submit_before_cmd = DWT->CYCCNT;\n"
        f"{match.group('indent')}read_val = read_reg(NPU_REG_CMD);\n"
        f"{match.group('indent')}write_reg(NPU_REG_CMD,{match.group('value')});\n"
        f"{match.group('indent')}/* PMU_INTERVAL_V10_T2 */\n"
        f"{match.group('indent')}pmu_interval_v10_t_submit_after_cmd = DWT->CYCCNT;\n"
        f"{match.group('comment')}{match.group('indent')}wait_for_irq();",
        text,
        count=1,
    )
    counts["submit_wait_block"] = 1
    irq_pat = re.compile(r"(?P<hdr>u85_irq_handler\s*\([^)]*\)\s*\{\n)", re.M)
    match = irq_pat.search(text)
    if not match:
        raise fail("u85_irq_handler opening not found")
    text = irq_pat.sub(
        f"{match.group('hdr')}    /* PMU_INTERVAL_V10_I0 */\n"
        "    pmu_interval_v10_t_irq_handler_entry = DWT->CYCCNT;\n",
        text,
        count=1,
    )
    counts["irq_entry_block"] = 1
    status_pat = re.compile(r"(?P<ifline>[ \t]*if\s*\(\(status_register\s*&\s*0x02\)\)\{\n)", re.M)
    match = status_pat.search(text)
    if not match:
        raise fail("vendor completion-if block not found")
    text = status_pat.sub(
        f"{match.group('ifline')}        /* PMU_INTERVAL_V10_T3 */\n"
        "        pmu_interval_v10_t_irq_status_seen = DWT->CYCCNT;\n"
        "        pmu_interval_v10_t3_hit_count++;\n",
        text,
        count=1,
    )
    counts["irq_status_block"] = 1
    irq_tail = (
        "        write_reg(NPU_REG_CMD, 2);\n"
        "    }\n"
        "}\n"
    )
    irq_tail_v11a = (
        "        write_reg(NPU_REG_CMD, 2);\n"
        "    }\n"
        "    pmu_interval_v10_i0_hit_count++;\n"
        "}\n"
    )
    text, counts["irq_post_t3_counts"] = sub_once(
        text, irq_tail, irq_tail_v11a, "post-T3 ISR hit counters")
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
    print(generate(args.runner_src, args.vendor_src, args.out_runner, args.out_vendor))


if __name__ == "__main__":
    main()
