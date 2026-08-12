import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-68s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


RUNNER = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#else
#error "PMU_COMPLETION_POLL_DIAG_V12 requires PMU_QUAL_SCHEMA_V12"
#endif

#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U

#define PMU_COMPLETION_POLL_DIAG_V12_OK 0x00000001U
#define V12_POLL_SUCCESS 1U
#define V12_POLL_TIMEOUT 2U

static pmu_diag_snapshot_t pmu_completion_poll_v12_internal_post_disable;

void test_entry(v12_t* d, const config_t* cfg)
{
    pmu_diag_context_t c;
    d->t_submit_after_cmd = DWT->CYCCNT;
    d->poll_result = V12_POLL_TIMEOUT;
    d->poll_status_at_success = 0U;
    d->t_poll_entry = 0U;
    d->t_status_completion_seen = 0U;
    d->t_poll_exit = 0U;
}

void run_once(v12_t* d)
{
    d->t_submit_after_cmd = DWT->CYCCNT;
}
"""

RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
BUILD_ID = "0x32314950"
SCHEMA_VERSION = 12


VENDOR_STOCK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline void wait_for_irq(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

void test_u85(void)
{
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    NVIC_EnableIRQ(NPU0_IRQn);
}

void test_commands(void)
{
    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x00000001);

    wait_for_irq();

    read_val = read_reg(NPU_REG_QREAD);
    write_reg(NPU_REG_CMD, 0x00000002);
}

void u85_irq_handler(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}
"""

VENDOR_V12_OK = """#define BUSY_SLEEP
#define VERIFY_OUTPUT 1
#define TEST_CPM 1
#define BUSY_SLEEP_TIMEOUT 10000

static inline void wait_for_irq(void)
{
    status_register = read_reg(NPU_REG_STATUS);
    if ((status_register & 0x02U)) {
        irq_history_mask = (uint16_t)(status_register >> 16);
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 0x00000002);
    }
}

uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const npu_status =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;
    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *npu_status;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }
    return 0U;
}

void test_u85(void)
{
    nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);

    irq_triggered = false;
    NVIC_DisableIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);
    pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);
    nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
    irq_triggered_before_submit = irq_triggered ? 1U : 0U;

    if (nvic_enabled_before_submit || (nvic_pending_after_initial_clear != 0U) ||
        (nvic_active_before_submit != 0U) || (irq_triggered_before_submit != 0U)) {
        return;
    }
}

void test_commands(void)
{
    uint32_t status_at_success;
    uint32_t poll_result;

    read_val = read_reg(NPU_REG_CMD);
    write_reg(NPU_REG_CMD, read_val | 0x00000001);
    pmu_completion_poll_v12_t_t2 = DWT->CYCCNT;

    status_at_success = v12_poll_completion();
    poll_result = (status_at_success & 0x02U) ? V12_POLL_SUCCESS : V12_POLL_TIMEOUT;
    pmu_completion_poll_v12_t_poll_result = poll_result;

    if (poll_result == V12_POLL_SUCCESS) {
        irq_history_mask = (uint16_t)(status_at_success >> 16);
        pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
        write_reg(NPU_REG_CMD, 0x00000002);
        read_val = read_reg(NPU_REG_QREAD);
        write_reg(NPU_REG_CMD, 0x00000002);
        if ((read_val & 0x0FU) == 0x03U) {
            goto v12_common_cleanup;
        }
    } else {
        irq_never_triggered = true;
        status_register = read_reg(NPU_REG_STATUS);
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n", status_register);
        read_val = read_reg(NPU_REG_QREAD);
        write_reg(NPU_REG_CMD, 0x00000002);
        if ((read_val & 0x0FU) == 0x03U) {
            goto v12_common_cleanup;
        }
    }

v12_common_cleanup:
    v12_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);
    v12_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
    v12_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
    irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;
    write_reg(NPU_REG_CMD, 0x00000000);
    write_reg(NPU_REG_CMD, 0x0000000CU);
}
"""

DISASSEMBLY = """Disassembly of section .text:

00001000 <v12_poll_completion>:
   1000:\t4f10\tldr\tr7, [pc, #64] @ (1040 <v12_poll_completion+0x40>)
   1002:\t6d37\tldr\tr7, [r7, #80]
   1004:\te8d7\t100? ; store t_poll_entry
   1008:\t4d0f\tldr\tr5, [pc, #60]
   100a:\t2400\tmovs\tr4, #0
   100c:\tf8d5 2080\tldr.w\tr0, [r5]
   1010:\t... status load from 0x50004004
   1012:\t... branch compare and return
   101e:\t... loop back

00001100 <test_u85>:
   1100:\t4903\tldr\tr1, [pc, #12] ; 1110
   1102:\t6849\tldr\tr1, [r1, #4]
   1104:\t4802\tldr\tr0, [pc, #8] ; 1110
   1106:\tf7ff bffe\tbl\t1200 <NVIC_SetVector>
   1108:\t... false store
   110c:\t... NVIC_DisableIRQ / NVIC_ClearPendingIRQ
   1110:\t.. reads and verify stores

00001200 <test_commands>:
   1200:\t4b14\tldr\tr3, [pc, #80] ; read cmd
   1204:\tf00?\t... write cmd |= 1
   1208:\tf00?\t... t2 store
   120c:\tf7ff bffe\tbl\tv12_poll_completion
   1210:\t... poll_result store
   1218:\t... branch to success/timeout

00001300 <u85_irq_handler>:
   1300:\t4a14\tldr\tr2, [pc, #80]
   1302:\t680a\tldr\tr2, [r2, #0]
   1304:\t... status history_mask and irq_triggered true
"""

NM = """20002000 B pmu_completion_poll_v12_t_installed_vector
20002004 B nvic_enabled_before_submit
20002008 B v12_nvic_pending_after_initial_clear
2000200c B nvic_active_before_submit
20002010 B irq_triggered_before_submit
20002014 B pmu_completion_poll_v12_t_t2
20002018 B pmu_completion_poll_v12_t_poll_entry
2000201c B pmu_completion_poll_v12_t_status_completion_seen
20002020 B pmu_completion_poll_v12_t_poll_exit
20002024 B pmu_completion_poll_v12_t_poll_result
20002028 B irq_history_mask
2000202c B pmu_completion_poll_v12_t_p0
20002030 B pmu_completion_poll_v12_t_p1
20002034 B pmu_completion_poll_v12_t_p2
20002038 B irq_never_triggered
2000203c B v12_nvic_pending_before_final_clear
20002040 B v12_nvic_pending_after_final_clear
20002044 B v12_nvic_active_after_cleanup
20002048 B irq_triggered_after_cleanup
00001000 T v12_poll_completion
00001200 T test_commands
00001300 T u85_irq_handler
"""

MANIFEST_OK = {
    "schema_version": SCHEMA_VERSION,
    "build_id": BUILD_ID,
    "runner_source_sha256": RUNNER_SHA256,
    "vendor_source_sha256": VENDOR_SHA256,
    "manifest_sha256": "OKMANIFESTSHA",
    "artifact_sha256": "OKBINHASH",
    "parser_sha256": "OKPARSE",
}


# --- deliberate mutations for the 27 required rejection cases ----------------

def _mutate_vendor_missing_first_success_cmd2(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);\n    read_val = read_reg(NPU_REG_QREAD);", "read_val = read_reg(NPU_REG_QREAD);", 1)


def _mutate_vendor_missing_second_success_cmd2(v):
    first = v.replace("write_reg(NPU_REG_CMD, 0x00000002);\n    read_val = read_reg(NPU_REG_QREAD);", "write_reg(NPU_REG_CMD, 0x00000002);\n    read_val = read_reg(NPU_REG_QREAD);", 1)
    return first.replace("read_val = read_reg(NPU_REG_QREAD);\n    write_reg(NPU_REG_CMD, 0x00000002);", "read_val = read_reg(NPU_REG_QREAD);", 1)


def _mutate_vendor_three_success_cmd2(v):
    return v + "\n    /* third-path mutation */\n    write_reg(NPU_REG_CMD, 0x00000002);\n"


def _mutate_vendor_cmd2_after_qread(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);\n    read_val = read_reg(NPU_REG_QREAD);", "read_val = read_reg(NPU_REG_QREAD);\n    write_reg(NPU_REG_CMD, 0x00000002);", 1)


def _mutate_vendor_cmd2_before_qread(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);\n    read_val = read_reg(NPU_REG_QREAD);", "read_reg(NPU_REG_QREAD);\n    write_reg(NPU_REG_CMD, 0x00000002);", 1)


def _mutate_vendor_missing_timeout_cmd2(v):
    return v.replace("read_val = read_reg(NPU_REG_QREAD);\n        write_reg(NPU_REG_CMD, 0x00000002);", "read_val = read_reg(NPU_REG_QREAD);", 1)


def _mutate_vendor_two_timeout_cmd2(v):
    return v.replace("read_val = read_reg(NPU_REG_QREAD);\n        write_reg(NPU_REG_CMD, 0x00000002);",
                    "read_val = read_reg(NPU_REG_QREAD);\n        write_reg(NPU_REG_CMD, 0x00000002);\n        write_reg(NPU_REG_CMD, 0x00000002);", 1)


def _mutate_vendor_helper_cmd_write(v):
    insert_at = "        status = *npu_status;\n"
    return v.replace(insert_at, insert_at + "        write_reg(NPU_REG_CMD, 0x00000002);", 1)


def _mutate_vendor_insert_nvic_enable_active_path(v):
    return v.replace("read_val = read_reg(NPU_REG_CMD);\n    write_reg(NPU_REG_CMD, read_val | 0x00000001);", "NVIC_EnableIRQ(NPU0_IRQn);\n" + "read_val = read_reg(NPU_REG_CMD);\n    write_reg(NPU_REG_CMD, read_val | 0x00000001);", 1)


def _mutate_vendor_insert_iser_set(v):
    return v + "\n    *(volatile uint32_t *)(0xE000E100U) |= (1U << NPU0_IRQN);\n"


def _mutate_vendor_vector_v11_veneer(v):
    return v.replace("NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);",
                   "NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);")


def _mutate_vendor_reach_v11(v):
    return v + "\n    v11a_u85_irq_entry_veneer();\n\n" + "void test_commands(void) {\n    write_reg(NPU_REG_CMD, read_reg(NPU_REG_CMD) | 1U);\n    pmu_interval_v11a_t_j0 = DWT->CYCCNT;\n}\n"


def _mutate_vendor_success_status_reread(v):
    return v.replace("pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            return status;",
                     "pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            status = *npu_status;\n            return status;", 1)


def _mutate_vendor_status_from_reread(v):
    return v.replace("status_at_success = v12_poll_completion();", "status_at_success = read_reg(NPU_REG_STATUS);")


def _mutate_disassembly_loop_back(v):
    return v + "\n   1020:\tb\t1010 <v12_poll_completion> ; loop-back after success P1"


def _mutate_vendor_timeout_falls_into_success(v):
    return v.replace("} else {\n        irq_never_triggered = true;", "}\n    if ((status_at_success & 0x2U) != 0U) {\n        poll_result = V12_POLL_SUCCESS;\n", 1)


def _mutate_vendor_wrong_mask(v):
    return v.replace("if ((status & 0x02U) != 0U) {", "if ((status & 0x04U) != 0U) {")


def _mutate_vendor_extra_mmio_in_helper(v):
    return v.replace("status = *npu_status;", "status = read_reg(NPU_REG_PMU);\n        status = *npu_status;")


def _mutate_vendor_per_iter_store(v):
    return v.replace("status = *npu_status;", "debug_count = i;\n        status = *npu_status;")


def _mutate_manifest_schema_drift(v):
    bad = dict(v)
    bad["schema_version"] = 11
    return bad


def _mutate_vendor_enable_retained_before_disable(v):
    return v.replace("NVIC_DisableIRQ(NPU0_IRQn);\n    NVIC_ClearPendingIRQ(NPU0_IRQn);",
                   "NVIC_EnableIRQ(NPU0_IRQn);\n    NVIC_DisableIRQ(NPU0_IRQn);\n    NVIC_ClearPendingIRQ(NPU0_IRQn);")


def _mutate_vendor_reachable_true_store(v):
    return v.replace("irq_triggered = false;", "irq_triggered = false;\n    irq_triggered = true;\n")


def _mutate_vendor_history_wrong_source(v):
    return v.replace("irq_history_mask = (uint16_t)(status_at_success >> 16);",
                     "irq_history_mask = 0xABCDU;")


def _mutate_disassembly_inlined_helper(v):
    return v.replace("00001000 <v12_poll_completion>:\n", "")


def _mutate_vendor_merge_qread_verify(v):
    return v.replace("\n        if ((read_val & 0x0FU) == 0x03U) {\n            goto v12_common_cleanup;\n        }\n", "\n        if ((read_val & 0x0FU) == 0x03U) {}\n", 1)


def _mutate_vendor_indirect_cmd_store(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);",
                     "((void(*)(uint32_t, uint32_t))((uint32_t)write_reg))(NPU_REG_CMD, 0x00000002);")


def _mutate_vendor_it_predicated_cmd(v):
    return v.replace("write_reg(NPU_REG_CMD, 0x00000002);",
                     "__asm volatile(\"itt eq\\n\\tbeq.n label\\n\" : : :);\n        write_reg(NPU_REG_CMD, 0x00000002);")


def _mutate_disassembly_wrong_p_order(v):
    return v.replace("pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;",
                     "pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;\n            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;")


def _mutate_manifest_parser_drift(v):
    bad = dict(v)
    bad["parser_sha256"] = "DRIFTED"
    return bad


def _mutate_vendor_timeout_no_reread(v):
    return v.replace("status_register = read_reg(NPU_REG_STATUS);\n", "", 1)


def _mutate_vendor_no_v12_vector_verification(v):
    return v.replace("pmu_completion_poll_v12_t_installed_vector = NVIC_GetVector(NPU0_IRQn);", "")


def _mutate_disassembly_indirect_branch(v):
    return v.replace("bl\tv12_poll_completion", "blx\tr3")


MUTATION_FIXTURES = {
    "01_missing_success_cmd2_first": {
        "vendor": _mutate_vendor_missing_first_success_cmd2(VENDOR_V12_OK),
        "note": "missing success CMD2 #1",
    },
    "02_missing_success_cmd2_second": {
        "vendor": _mutate_vendor_missing_second_success_cmd2(VENDOR_V12_OK),
        "note": "missing success CMD2 #2",
    },
    "03_third_success_cmd2": {
        "vendor": _mutate_vendor_three_success_cmd2(VENDOR_V12_OK),
        "note": "extra third success CMD2",
    },
    "04_success_cmd2_#1_moved_after_qread": {
        "vendor": _mutate_vendor_cmd2_after_qread(VENDOR_V12_OK),
        "note": "success CMD2 #1 moved after QREAD",
    },
    "05_success_cmd2_#2_moved_before_qread": {
        "vendor": _mutate_vendor_cmd2_before_qread(VENDOR_V12_OK),
        "note": "success CMD2 #2 moved before QREAD",
    },
    "06_missing_timeout_cmd2": {
        "vendor": _mutate_vendor_missing_timeout_cmd2(VENDOR_V12_OK),
        "note": "missing timeout CMD2",
    },
    "07_two_timeout_cmd2": {
        "vendor": _mutate_vendor_two_timeout_cmd2(VENDOR_V12_OK),
        "note": "two timeout CMD2",
    },
    "08_helper_cmd2_injected": {
        "vendor": _mutate_vendor_helper_cmd_write(VENDOR_V12_OK),
        "note": "CMD write inside helper loop",
    },
    "09_active_path_nvic_enable": {
        "vendor": _mutate_vendor_insert_nvic_enable_active_path(VENDOR_V12_OK),
        "note": "NVIC_EnableIRQ on measured path",
    },
    "10_iser_write": {
        "vendor": _mutate_vendor_insert_iser_set(VENDOR_V12_OK),
        "note": "direct NVIC ISER bit write",
    },
    "11_v11_veneer_vector": {
        "vendor": _mutate_vendor_vector_v11_veneer(VENDOR_V12_OK),
        "note": "runtime vector changed to V11 veneer",
    },
    "12_reachable_j0_i0_t3": {
        "vendor": _mutate_vendor_reach_v11(VENDOR_V12_OK),
        "note": "V11 J0/I0/T3 path reachable",
    },
    "13_success_status_reread": {
        "vendor": _mutate_vendor_success_status_reread(VENDOR_V12_OK),
        "note": "successful path has status reread",
    },
    "14_status_at_success_from_reread": {
        "vendor": _mutate_vendor_status_from_reread(VENDOR_V12_OK),
        "note": "status_at_success not from branch-driving status load",
    },
    "15_loop_back_after_p1": {
        "disassembly": _mutate_disassembly_loop_back(DISASSEMBLY),
        "note": "loop-back edge after P1/P2",
    },
    "16_timeout_flows_to_success_cfg": {
        "vendor": _mutate_vendor_timeout_falls_into_success(VENDOR_V12_OK),
        "note": "timeout can execute success-only CMD order",
    },
    "17_wrong_completion_mask": {
        "vendor": _mutate_vendor_wrong_mask(VENDOR_V12_OK),
        "note": "completion mask changed from 0x02",
    },
    "18_extra_helper_mmio": {
        "vendor": _mutate_vendor_extra_mmio_in_helper(VENDOR_V12_OK),
        "note": "extra MMIO in helper",
    },
    "19_per_iteration_store": {
        "vendor": _mutate_vendor_per_iter_store(VENDOR_V12_OK),
        "note": "per-iteration SRAM store inside helper loop",
    },
    "20_broken_modular_identity": {
        "disassembly": _mutate_disassembly_wrong_p_order(DISASSEMBLY),
        "note": "timestamps violate modular-order identity",
    },
    "21_cross_schema_parser_manifest_drift": {
        "manifest": _mutate_manifest_schema_drift(MANIFEST_OK),
        "manifest_parser": _mutate_manifest_parser_drift(MANIFEST_OK),
        "note": "cross-schema/parser/manfiest mismatch",
    },
    "22_retain_enable_before_disable": {
        "vendor": _mutate_vendor_enable_retained_before_disable(VENDOR_V12_OK),
        "note": "frozen NVIC_EnableIRQ retained before disable",
    },
    "23_reachable_irq_true_then_false": {
        "vendor": _mutate_vendor_reachable_true_store(VENDOR_V12_OK),
        "note": "reachable irq_triggered=true on measured path",
    },
    "24_history_mask_not_from_success_status": {
        "vendor": _mutate_vendor_history_wrong_source(VENDOR_V12_OK),
        "note": "irq_history_mask not sourced from success status",
    },
    "25_helper_inlined_or_cloned_or_tailcall": {
        "disassembly": _mutate_disassembly_inlined_helper(DISASSEMBLY),
        "note": "helper inline/clone/tail-call",
    },
    "26_success_timeout_merge_before_qread": {
        "vendor": _mutate_vendor_merge_qread_verify(VENDOR_V12_OK),
        "note": "success and timeout merged before QREAD verify",
    },
    "27_indirect_or_it_predicated_cmd": {
        "vendor": _mutate_vendor_indirect_cmd_store(_mutate_vendor_it_predicated_cmd(VENDOR_V12_OK)),
        "disassembly": _mutate_vendor_timeout_no_reread(_mutate_disassembly_indirect_branch(DISASSEMBLY)),
        "note": "indirect branch/IT-predicated CMD store used",
    },
}


POSITIVE_SYMBOLS = {
    "helper_symbol": "v12_poll_completion",
    "runtime_vector_symbol": "u85_irq_handler",
    "status_load_address": "0x50004004",
    "mask": "0x02",
    "poll_result_symbol": "pmu_completion_poll_v12_t_poll_result",
    "p0_symbol": "pmu_completion_poll_v12_t_poll_entry",
    "p1_symbol": "pmu_completion_poll_v12_t_status_completion_seen",
    "p2_symbol": "pmu_completion_poll_v12_t_poll_exit",
    "cmd2_one": "pmu_completion_poll_v12_t_cmd2",
}


NEGATIVE_FIXTURE_NAMES = list(MUTATION_FIXTURES.keys())

if __name__ == "__main__":
    import check_pmu_completion_poll_v12 as gate
    import patches.patch_pmu_completion_poll_v12 as patcher

    check("runner fixture includes schema 12", SCHEMA_VERSION == 12)
    check("runner fixture pins build id", BUILD_ID == "0x32314950")
    check("runner fixture has frozen runner hash", RUNNER_SHA256 == "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b")
    check("vendor fixture includes stock vector install", "NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);" in VENDOR_STOCK)
    check("vendor fixture includes stock enable site", "NVIC_EnableIRQ(NPU0_IRQn);" in VENDOR_STOCK)
    check("vendor fixture includes wait_for_irq path", "wait_for_irq();" in VENDOR_STOCK)
    check("vendor fixture includes QREAD cmd2 tail", "read_val = read_reg(NPU_REG_QREAD);" in VENDOR_STOCK)

    runner_out, runner_counts = patcher.patch_runner(RUNNER)
    vendor_out, vendor_counts = patcher.patch_vendor(VENDOR_STOCK)
    check("runner patch emits v12 schema markers", "PMU_COMPLETION_POLL_DIAG_V12" in runner_out)
    check("vendor patch keeps stock ISR symbols", all(m in vendor_out for m in gate.VENDOR_MARKERS))

    counts = gate.verify_generated_sources(runner_out, vendor_out)
    check("gate accepts positive generated source", counts.get("PMU_COMPLETION_POLL_V12_HELPER") == 1)

    gate.verify_callsite_trace(runner_out, vendor_out, DISASSEMBLY, NM)
    print("mutations", len(NEGATIVE_FIXTURE_NAMES))

    for name in NEGATIVE_FIXTURE_NAMES:
        fix = MUTATION_FIXTURES[name]
        broken_vendor = fix.get("vendor", VENDOR_V12_OK)
        broken_disassembly = fix.get("disassembly", DISASSEMBLY)
        broken_manifest = fix.get("manifest", MANIFEST_OK)
        try:
            if "manifest" in fix and isinstance(broken_manifest, dict):
                gate.validate_artifact_contract(json.dumps(broken_manifest))
            try:
                gate.verify_generated_sources(runner_out, broken_vendor)
            except Exception:
                raise
            gate.verify_callsite_trace(runner_out, broken_vendor, broken_disassembly, NM)
            check("mutation rejected: %s" % name, False, fix["note"])
        except Exception:
            check("mutation rejected: %s" % name, True, fix["note"])

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
