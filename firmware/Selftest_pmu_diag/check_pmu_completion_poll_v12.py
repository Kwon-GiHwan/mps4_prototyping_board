"""Static gate for PMU_COMPLETION_POLL_DIAG_V12 generated sources."""

from __future__ import annotations

import json
import re

BUILD_ID = 0x32314950
SCHEMA_VERSION = 12
VARIANT = "PMU_COMPLETION_POLL_DIAG_V12"

EXPECTED_MANIFEST_KEYS = (
    "runtime_vector_install_site_address",
    "runtime_disable_site_address",
    "runtime_clear_pending_site_address",
    "runtime_enable_read_address",
    "runtime_pending_read_address",
    "runtime_active_read_address",
    "runtime_irq_triggered_read_address",
    "helper_status_read_address",
    "helper_status_test_address",
    "poll_helper_p0_address",
    "poll_helper_p1_address",
    "poll_helper_p2_address",
    "submit_read_address",
    "submit_write_address",
    "submit_t2_address",
    "wait_call_address",
    "wait_result_store_address",
    "success_history_mask_store_address",
    "success_cmd2_1_store_address",
    "success_qread_load_address",
    "success_cmd2_2_store_address",
    "timeout_report_address",
    "timeout_qread_load_address",
    "timeout_cmd2_store_address",
    "cmd0_store_address",
    "hprintf_callsite_address",
    "terminal_cmd0c_store_address",
    "final_pending_before_clear_address",
    "final_pending_after_clear_address",
    "final_active_after_cleanup_address",
    "final_irq_triggered_after_cleanup_address",
    "irq_status_read_address",
    "irq_trigger_test_address",
    "irq_history_mask_store_address",
    "irq_cmd2_store_address",
)


class GateError(RuntimeError):
    pass


def fail(message: str) -> GateError:
    return GateError("FAIL %s" % message)


def count_once(text: str, needle: str, what: str) -> int:
    count = text.count(needle)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return count


def _section(text: str, start: str, end: str) -> str:
    left = text.find(start)
    right = text.find(end, left)
    if left < 0 or right < 0 or not (left < right):
        raise fail("section %s -> %s not found" % (start, end))
    return text[left:right]


def _validate_helper(vendor_text: str) -> None:
    helper = _section(
        vendor_text,
        "uint32_t __attribute__((noinline)) v12_poll_completion(void)",
        "void test_u85(void)",
    )
    count_once(helper, "/* V12_P0 */", "helper P0")
    count_once(helper, "/* V12_HELPER_STATUS_READ */", "helper status read marker")
    count_once(helper, "/* V12_HELPER_STATUS_TEST */", "helper status test marker")
    count_once(helper, "/* V12_P1 */", "helper P1")
    count_once(helper, "/* V12_P2 */", "helper P2")
    count_once(helper, "status = *status_reg;", "helper status load")
    count_once(helper, "if ((status & 0x02U) != 0U) {", "helper completion mask")
    count_once(helper, "return status;", "helper success return")
    count_once(helper, "return 0U;", "helper timeout return")
    for forbidden in (
        "write_reg(",
        "read_reg(",
        "NVIC_",
        "printf(",
        "pmu_interval_v11a_",
        "pmu_interval_v10_",
        "pmu_qual_",
        "__asm",
        "dsb",
        "isb",
        "0x20000000U",
    ):
        if forbidden in helper:
            raise fail("helper contains forbidden operation %r" % forbidden)
    order = [
        "/* V12_P0 */",
        "/* V12_HELPER_STATUS_READ */",
        "/* V12_HELPER_STATUS_TEST */",
        "/* V12_P1 */",
        "/* V12_P2 */",
        "return status;",
    ]
    positions = [helper.find(needle) for needle in order]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise fail("helper ordering violated")


def _validate_runtime_path(vendor_text: str) -> None:
    count_once(vendor_text, "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);", "runtime vector target")
    if "v11a_u85_irq_entry_veneer" in vendor_text:
        raise fail("runtime vector still reaches V11 veneer")
    if "NVIC_EnableIRQ(NPU0_IRQn)" in vendor_text or "0xE000E100U" in vendor_text:
        raise fail("NVIC enable path remains reachable")
    if "pmu_interval_v11a_" in vendor_text:
        raise fail("V11 marker remains reachable in V12 source")
    order = [
        "/* V12_RUNTIME_VECTOR_INSTALL */",
        "/* V12_RUNTIME_NVIC_PREPARE */",
        "/* V12_RUNTIME_DISABLE */",
        "/* V12_RUNTIME_CLEAR_PENDING */",
        "/* V12_RUNTIME_VECTOR_LOAD */",
        "/* V12_RUNTIME_ENABLE_READ */",
        "/* V12_RUNTIME_PENDING_READ */",
        "/* V12_RUNTIME_ACTIVE_READ */",
        "/* V12_RUNTIME_IRQ_TRIGGERED_READ */",
    ]
    positions = [vendor_text.find(needle) for needle in order]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise fail("runtime hard-bypass ordering violated")


def _validate_success_timeout_paths(vendor_text: str) -> None:
    commands = _section(vendor_text, "void test_commands(void)", "void u85_irq_handler(void)")
    count_once(commands, "status_at_success = v12_poll_completion();", "wait helper call")
    count_once(commands, "pmu_completion_poll_v12_t_poll_result = (status_at_success & 0x02U) ? V12_POLL_SUCCESS : V12_POLL_TIMEOUT;", "poll result store")
    success = _section(
        commands,
        "if (pmu_completion_poll_v12_t_poll_result == V12_POLL_SUCCESS) {",
        "} else {",
    )
    timeout = _section(
        commands,
        "} else {",
        "v12_common_cleanup:",
    )
    if success.count("write_reg(NPU_REG_CMD, 0x00000002);") != 2:
        raise fail("success path CMD=2 count != 2")
    if timeout.count("write_reg(NPU_REG_CMD, 0x00000002);") != 1:
        raise fail("timeout path CMD=2 count != 1")
    success_order = [
        "status_at_success = v12_poll_completion();",
        "/* V12_SUCCESS_HISTORY_STORE */",
        "pmu_completion_poll_v12_t_poll_status_at_success = status_at_success;",
        "/* V12_SUCCESS_CMD2_1 */",
        "/* V12_SUCCESS_QREAD_READ */",
        "/* V12_SUCCESS_CMD2_2 */",
    ]
    success_positions = [commands.find(needle) for needle in success_order]
    if any(pos < 0 for pos in success_positions) or success_positions != sorted(success_positions):
        raise fail("success path ordering violated")
    timeout_order = [
        "/* V12_TIMEOUT_REPORT */",
        "/* V12_TIMEOUT_QREAD_READ */",
        "/* V12_TIMEOUT_CMD2 */",
    ]
    timeout_positions = [timeout.find(needle) for needle in timeout_order]
    if any(pos < 0 for pos in timeout_positions) or timeout_positions != sorted(timeout_positions):
        raise fail("timeout path ordering violated")
    if "status_at_success = read_reg(NPU_REG_STATUS);" in commands:
        raise fail("status_at_success comes from a reread")
    if "irq_history_mask = 0xABCDU;" in commands:
        raise fail("history mask lost single-source status dataflow")
    count_once(
        success,
        "if ((read_val & 0x0FU) == 0x03U) {\n            pmu_completion_poll_v12_t_success_qread_verified = 1U;\n        }",
        "success qread verify body",
    )
    count_once(
        timeout,
        "if ((read_val & 0x0FU) == 0x03U) {\n            pmu_completion_poll_v12_t_timeout_qread_verified = 1U;\n        }",
        "timeout qread verify body",
    )
    active_paths = helperless_commands(commands)
    if "irq_triggered = true;" in active_paths:
        raise fail("measured path reintroduces irq_triggered=true")
    cleanup_order = [
        "v12_common_cleanup:",
        "/* V12_FINAL_PENDING_BEFORE_CLEAR */",
        "/* V12_FINAL_PENDING_AFTER_CLEAR */",
        "/* V12_FINAL_ACTIVE_AFTER_CLEAR */",
        "/* V12_FINAL_IRQ_TRIGGERED_AFTER_CLEAR */",
        "/* V12_CMD0 */",
        "/* V12_HPRINTF_SEAM */",
        "/* V12_CMD0C */",
    ]
    cleanup_positions = [commands.find(needle) for needle in cleanup_order]
    if any(pos < 0 for pos in cleanup_positions) or cleanup_positions != sorted(cleanup_positions):
        raise fail("cleanup ordering violated")


def helperless_commands(commands: str) -> str:
    return commands.replace("void test_commands(void)", "")


def verify_generated_sources(runner_text: str, vendor_text: str) -> dict:
    counts = {}
    if "PMU_COMPLETION_POLL_DIAG_V12" not in runner_text:
        raise fail("runner schema marker missing")
    count_once(runner_text, "PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U", "runner build id")
    count_once(runner_text, "pmu_completion_poll_v12_internal_post_disable", "runner internal snapshot")
    counts["PMU_COMPLETION_POLL_V12_HELPER"] = count_once(
        vendor_text,
        "uint32_t __attribute__((noinline)) v12_poll_completion(void)",
        "poll helper symbol",
    )
    _validate_helper(vendor_text)
    _validate_runtime_path(vendor_text)
    _validate_success_timeout_paths(vendor_text)
    count_once(vendor_text, "void u85_irq_handler(void)", "stock handler")
    if vendor_text.count("irq_triggered = true;") != 2:
        raise fail("unexpected reachable irq_triggered=true count")
    count_once(vendor_text, "/* V12_ISR_STATUS_READ */", "ISR status read marker")
    count_once(vendor_text, "/* V12_ISR_TRIGGER_TEST */", "ISR trigger test marker")
    count_once(vendor_text, "/* V12_ISR_HISTORY_STORE */", "ISR history marker")
    count_once(vendor_text, "/* V12_ISR_CMD2 */", "ISR cmd2 marker")
    return counts


def _marker_addr(disassembly_text: str, marker: str) -> int:
    pattern = re.compile(r"^\s*([0-9a-fA-F]+):.*;\s*%s\s*$" % re.escape(marker), re.M)
    hit = pattern.search(disassembly_text)
    if hit is None:
        raise fail("disassembly marker missing: %s" % marker)
    return int(hit.group(1), 16)


def verify_callsite_trace(runner_text: str, vendor_text: str, disassembly_text: str, nm_text: str) -> dict:
    del runner_text
    del vendor_text
    count_once(disassembly_text, "00001000 <v12_poll_completion>:", "helper function in disassembly")
    count_once(disassembly_text, "1210:\tbl\tv12_poll_completion", "direct helper callsite")
    count_once(nm_text, " T v12_poll_completion", "helper symbol in nm")
    count_once(nm_text, " T u85_irq_handler", "stock handler symbol in nm")
    if "blx\tr3" in disassembly_text:
        raise fail("indirect helper branch present")
    if "dsb" in _section(disassembly_text, "00001000 <v12_poll_completion>:", "00001100 <test_u85>:"):
        raise fail("helper disassembly contains forbidden barrier")
    if _marker_addr(disassembly_text, "V12_P0") >= _marker_addr(disassembly_text, "V12_HELPER_STATUS_READ"):
        raise fail("P0 must precede helper status read")
    if _marker_addr(disassembly_text, "V12_HELPER_STATUS_READ") >= _marker_addr(disassembly_text, "V12_HELPER_STATUS_TEST"):
        raise fail("helper status read/test ordering violated")
    if _marker_addr(disassembly_text, "V12_HELPER_STATUS_TEST") >= _marker_addr(disassembly_text, "V12_P1"):
        raise fail("P1 must occur after completion test")
    if _marker_addr(disassembly_text, "V12_P1") >= _marker_addr(disassembly_text, "V12_P2"):
        raise fail("P1/P2 ordering violated")
    if "loop-back" in disassembly_text:
        raise fail("success path loops after P1/P2")
    if _marker_addr(disassembly_text, "V12_SUCCESS_CMD2_1") >= _marker_addr(disassembly_text, "V12_SUCCESS_QREAD_READ"):
        raise fail("success CMD2 #1 must precede QREAD")
    if _marker_addr(disassembly_text, "V12_SUCCESS_QREAD_READ") >= _marker_addr(disassembly_text, "V12_SUCCESS_CMD2_2"):
        raise fail("success CMD2 #2 must follow QREAD")
    if _marker_addr(disassembly_text, "V12_FINAL_PENDING_BEFORE_CLEAR") >= _marker_addr(disassembly_text, "V12_CMD0"):
        raise fail("cleanup must precede CMD0")
    if _marker_addr(disassembly_text, "V12_CMD0") >= _marker_addr(disassembly_text, "V12_HPRINTF_SEAM"):
        raise fail("CMD0/HPRINTF ordering violated")
    if _marker_addr(disassembly_text, "V12_HPRINTF_SEAM") >= _marker_addr(disassembly_text, "V12_CMD0C"):
        raise fail("HPRINTF/CMD0xC ordering violated")
    return {
        "helper_symbol": "v12_poll_completion",
        "runtime_vector_symbol": "u85_irq_handler",
    }


def validate_artifact_contract(manifest_json: str) -> dict:
    doc = json.loads(manifest_json)
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise fail("schema_version mismatch")
    if doc.get("build_id") != "0x%08X" % BUILD_ID:
        raise fail("build_id mismatch")
    if doc.get("parser_sha256") in (None, "", "DRIFTED"):
        raise fail("parser provenance drift")
    for key in EXPECTED_MANIFEST_KEYS:
        value = doc.get(key)
        if not isinstance(value, str) or not value.startswith("0x"):
            raise fail("manifest key missing or not address-like: %s" % key)
    return doc
