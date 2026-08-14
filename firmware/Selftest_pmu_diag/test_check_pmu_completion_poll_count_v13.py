import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-72s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


def fail(message: str) -> AssertionError:
    return AssertionError(message)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise fail("%s: expected 1 match, found %d" % (what, count))
    return text.replace(old, new, 1)


SCHEMA_VERSION = 13
BUILD_ID = "0x33314950"
POLL_LIMIT = 10000
INVALID_REMAINING = 0xFFFFFFFF

RUNNER_RAW_STOCK = """#if defined(PMU_QUAL_SCHEMA_V8)
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

VENDOR_RAW_STOCK = """#define BUSY_SLEEP
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

RUNNER_SHA256 = "57b3028bc820825ce7e560e0979e36a4c10acd9cfff55408d2985132ca384b4c"
VENDOR_SHA256 = "053d15bd81ce35f32b18d6d876ac501db41d97db141ab1fbe8fb7b70a564dceb"

RUNNER_V12_GENERATED = """#if defined(PMU_QUAL_SCHEMA_V12)
#define PMU_DIAG_SCHEMA_VERSION 12U
#define PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID 0x32314950U
#endif
"""

VENDOR_V12_GENERATED = """uint32_t __attribute__((noinline)) v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

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
"""

RUNNER_V13_OK = """#if defined(PMU_QUAL_SCHEMA_V13)
#define PMU_DIAG_SCHEMA_VERSION 13U
#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U
#define V13_POLL_SUCCESS 1U
#define V13_POLL_TIMEOUT 2U
#define PMU_DIAG_FIELD_COUNT 101U
#endif

static pmu_diag_snapshot_t pmu_qual_internal_post_disable;
extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;

void test_entry(v13_t* d)
{
    d->pmcr_readback_after_disable = 0U;
    d->poll_result = V13_POLL_TIMEOUT;
    d->poll_status_at_success = 0U;
    d->poll_remaining_at_success = 0xFFFFFFFFU;
}

void emit_record(v13_t* d, uint32_t *out_words)
{
    out_words[100] = d->poll_remaining_at_success;
}
"""

VENDOR_V13_OK = """uint32_t __attribute__((noinline)) v13_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);
            return status;
        }
    }

    return 0U;
}
"""


def _remaining_after(iteration_index: int) -> int:
    return POLL_LIMIT - iteration_index


SEMANTIC_BOUNDARIES = (
    {"name": "first poll", "remaining": _remaining_after(0), "iterations": 1},
    {"name": "interior poll", "remaining": _remaining_after(4321), "iterations": 4322},
    {"name": "last poll", "remaining": _remaining_after(9999), "iterations": 10000},
)


def _negative_vendor_fixtures() -> dict[str, dict[str, str]]:
    duplicate_store = """            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);
            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);
"""
    timeout_store = """    pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;
    return 0U;
"""
    second_status_read = """            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            status = *status_reg;
            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);
"""
    extra_mmio = """        (void)*(volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_CMD);
        status = *status_reg;
"""
    unrelated_counter = """    uint32_t remaining = 10000U;

    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;

    for (uint32_t i = 0U; i < 10000U; ++i) {
        remaining = 10000U;
        status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;
            pmu_completion_poll_v13_t_poll_remaining_at_success = remaining;
            return status;
        }
    }
"""
    per_iteration_store = """        pmu_completion_poll_v13_t_poll_remaining_at_success = i;
        status = *status_reg;
"""
    return {
        "remaining_before_p2": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n",
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n",
                "remaining-before-p2",
            ),
            "expected": "remaining store must follow P2 exactly",
        },
        "duplicate_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n",
                duplicate_store,
                "duplicate-store",
            ),
            "expected": "poll_remaining_at_success store count != 1",
        },
        "timeout_reachable_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    return 0U;\n",
                timeout_store,
                "timeout-store",
            ),
            "expected": "timeout path must not publish remaining",
        },
        "constant_remaining": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n",
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = 10000U;\n",
                "constant-remaining",
            ),
            "expected": "remaining must be computed as (10000U - i)",
        },
        "unrelated_reinitialized_counter": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "    pmu_completion_poll_v13_t_poll_entry = DWT->CYCCNT;\n\n"
                "    for (uint32_t i = 0U; i < 10000U; ++i) {\n"
                "        status = *status_reg;\n"
                "        if ((status & 0x02U) != 0U) {\n"
                "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n"
                "            return status;\n"
                "        }\n"
                "    }\n",
                unrelated_counter,
                "reinitialized-counter",
            ),
            "expected": "remaining must dataflow from loop index only",
        },
        "per_iteration_increment_store": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "        status = *status_reg;\n",
                per_iteration_store,
                "per-iteration-store",
            ),
            "expected": "remaining store must be success-only",
        },
        "second_status_read": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
                "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n",
                second_status_read,
                "second-status-read",
            ),
            "expected": "helper STATUS read count != 1",
        },
        "extra_mmio": {
            "vendor": replace_once(
                VENDOR_V13_OK,
                "        status = *status_reg;\n",
                extra_mmio,
                "extra-mmio",
            ),
            "expected": "helper contains forbidden operation",
        },
        "wrong_completion_mask": {
            "vendor": VENDOR_V13_OK.replace("(status & 0x02U)", "(status & 0x04U)", 1),
            "expected": "helper completion mask",
        },
        "retained_v12_hard_bypass": {
            "vendor": VENDOR_V13_OK.replace("return status;", "write_reg(NPU_REG_CMD, 0x00000002);\n            return status;", 1),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
        "retained_v12_qread_release_drift": {
            "vendor": VENDOR_V13_OK.replace(
                "            return status;\n",
                "            read_val = read_reg(NPU_REG_QREAD);\n"
                "            write_reg(NPU_REG_CMD, 0x00000000);\n"
                "            write_reg(NPU_REG_CMD, 0x0000000CU);\n"
                "            return status;\n",
                1,
            ),
            "expected": "retained V12 hard-bypass/CMD/QREAD/release drift",
        },
    }


NEGATIVE_VENDOR_FIXTURES = _negative_vendor_fixtures()


def validate_local_fixtures():
    required_suffix = (
        "            pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
        "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n"
        "            return status;\n"
    )
    if VENDOR_V13_OK.count("for (uint32_t i = 0U; i < 10000U; ++i)") != 1:
        raise fail("positive vendor fixture must have exactly one helper loop")
    if required_suffix not in VENDOR_V13_OK:
        raise fail("positive vendor fixture lost V13 success suffix")
    if sha256_text(RUNNER_RAW_STOCK) != RUNNER_SHA256:
        raise fail("pinned runner raw SHA fixture drifted")
    if sha256_text(VENDOR_RAW_STOCK) != VENDOR_SHA256:
        raise fail("pinned vendor raw SHA fixture drifted")
    if RUNNER_V13_OK.count("poll_remaining_at_success = 0xFFFFFFFFU;") != 1:
        raise fail("runner fixture must reset invalid remaining sentinel exactly once")
    if RUNNER_V13_OK.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") != 1:
        raise fail("runner fixture must declare remaining field exactly once")
    if RUNNER_V13_OK.count("out_words[100] = d->poll_remaining_at_success;") != 1:
        raise fail("runner fixture must serialize remaining wire word exactly once")
    if RUNNER_V13_OK.count("#define PMU_DIAG_FIELD_COUNT 101U") != 1:
        raise fail("runner fixture must pin field count for appended wire word exactly once")
    if RUNNER_V12_GENERATED.count("PMU_COMPLETION_POLL_DIAG_V12_BUILD_ID") != 1:
        raise fail("generated V12 raw-input rejection fixture malformed")
    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        if payload["vendor"] == VENDOR_V13_OK:
            raise fail("negative fixture is a no-op: %s" % name)


def run_future_suite(gate, patcher):
    runner_out, runner_meta = patcher.patch_runner(RUNNER_RAW_STOCK)
    vendor_out, vendor_meta = patcher.patch_vendor(VENDOR_RAW_STOCK)

    check("runner patch returns replacements", isinstance(runner_meta, dict) and bool(runner_meta))
    check("vendor patch returns replacements", isinstance(vendor_meta, dict) and bool(vendor_meta))
    check("runner patch sets schema 13", "#define PMU_DIAG_SCHEMA_VERSION 13U" in runner_out)
    check("runner patch pins build id 0x33314950", "#define PMU_COMPLETION_POLL_DIAG_V13_BUILD_ID 0x33314950U" in runner_out)
    check(
        "runner patch declares remaining record field exactly once",
        runner_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") >= 1
        and runner_out.count("extern volatile uint32_t pmu_completion_poll_v13_t_poll_remaining_at_success;") == 1,
    )
    check("runner patch resets invalid remaining sentinel", "poll_remaining_at_success = 0xFFFFFFFFU;" in runner_out)
    check(
        "runner patch appends exactly one remaining wire word",
        runner_out.count("out_words[100] = d->poll_remaining_at_success;") == 1
        and runner_out.count("#define PMU_DIAG_FIELD_COUNT 101U") == 1,
    )
    check("vendor patch emits V13 helper symbol", "v13_poll_completion" in vendor_out)
    check("vendor patch appends one remaining word", vendor_out.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check(
        "vendor patch emits exact success suffix",
        (
            "pmu_completion_poll_v13_t_status_completion_seen = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_exit = DWT->CYCCNT;\n"
            "            pmu_completion_poll_v13_t_poll_remaining_at_success = (10000U - i);\n"
            "            return status;"
        ) in vendor_out,
    )
    check(
        "vendor timeout path does not publish remaining",
        "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;\n    return 0U;" not in vendor_out,
    )

    for boundary in SEMANTIC_BOUNDARIES:
        remaining = boundary["remaining"]
        iterations = boundary["iterations"]
        check(
            "semantic boundary %s maps remaining to iterations" % boundary["name"],
            1 <= remaining <= 10000 and iterations == (10001 - remaining),
            "remaining=%d iterations=%d" % (remaining, iterations),
        )
    check("timeout semantic keeps invalid remaining sentinel", INVALID_REMAINING == 0xFFFFFFFF)

    try:
        evidence = gate.verify_generated_sources(runner_out, vendor_out)
        check(
            "future V13 gate accepts canonical generated sources",
            evidence.get("schema_version") == SCHEMA_VERSION
            and evidence.get("build_id") == BUILD_ID
            and evidence.get("poll_remaining_symbol") == "pmu_completion_poll_v13_t_poll_remaining_at_success",
        )
    except Exception as exc:
        check("future V13 gate accepts canonical generated sources", False, str(exc))
        evidence = None

    for wrong_runner, wrong_vendor, label in (
        (RUNNER_RAW_STOCK + "\n/* drift */\n", VENDOR_RAW_STOCK, "runner hash mismatch"),
        (RUNNER_RAW_STOCK, VENDOR_RAW_STOCK + "\n/* drift */\n", "vendor hash mismatch"),
        (RUNNER_V12_GENERATED, VENDOR_RAW_STOCK, "generated V12 runner as raw input"),
        (RUNNER_RAW_STOCK, VENDOR_V12_GENERATED, "generated V12 vendor as raw input"),
        (RUNNER_RAW_STOCK + RUNNER_RAW_STOCK, VENDOR_RAW_STOCK, "multiple raw runner targets"),
        ("/* missing helper */\n", VENDOR_RAW_STOCK, "zero raw runner targets"),
        (RUNNER_RAW_STOCK, VENDOR_RAW_STOCK + VENDOR_RAW_STOCK, "multiple raw vendor targets"),
        (RUNNER_RAW_STOCK, "/* missing helper */\n", "zero raw vendor targets"),
    ):
        try:
            gate.verify_generated_sources(
                wrong_runner,
                wrong_vendor,
                raw_runner_sha256=RUNNER_SHA256,
                raw_vendor_sha256=VENDOR_SHA256,
            )
            check("future V13 gate rejects %s" % label, False, "unexpected pass")
        except TypeError:
            check("future V13 gate rejects %s" % label, False, "verify_generated_sources signature still missing V13 raw-input contract")
        except Exception as exc:
            check("future V13 gate rejects %s" % label, True, str(exc))

    for name, payload in NEGATIVE_VENDOR_FIXTURES.items():
        try:
            gate.verify_generated_sources(RUNNER_V13_OK, payload["vendor"])
            check("future V13 gate rejects %s" % name, False, "unexpected pass")
        except Exception as exc:
            check("future V13 gate rejects %s" % name, payload["expected"] in str(exc), str(exc))

    return evidence


if __name__ == "__main__":
    validate_local_fixtures()

    check("fixture schema version is 13", SCHEMA_VERSION == 13)
    check("fixture build id is 0x33314950", BUILD_ID == "0x33314950")
    check("raw runner SHA fixture is frozen", RUNNER_SHA256 == sha256_text(RUNNER_RAW_STOCK))
    check("raw vendor SHA fixture is frozen", VENDOR_SHA256 == sha256_text(VENDOR_RAW_STOCK))
    check("positive vendor stores remaining exactly once", VENDOR_V13_OK.count("pmu_completion_poll_v13_t_poll_remaining_at_success") == 1)
    check("positive vendor timeout publishes no remaining", "return 0U;" in VENDOR_V13_OK and "pmu_completion_poll_v13_t_poll_remaining_at_success = 1U;" not in VENDOR_V13_OK)
    check("negative fixture count covers required drifts", len(NEGATIVE_VENDOR_FIXTURES) >= 11)
    check(
        "boundary semantics cover first interior last and timeout invalid",
        [item["remaining"] for item in SEMANTIC_BOUNDARIES] == [10000, 5679, 1] and INVALID_REMAINING == 0xFFFFFFFF,
    )

    import check_pmu_completion_poll_count_v13 as gate
    import patches.patch_pmu_completion_poll_count_v13 as patcher

    run_future_suite(gate, patcher)

    print()
    print("passed=%d failed=%d" % (passed, failed))
    raise SystemExit(1 if failed else 0)
