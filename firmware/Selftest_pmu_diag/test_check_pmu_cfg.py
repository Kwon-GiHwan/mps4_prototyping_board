"""Synthetic unit tests for the CFG A/B/C characterization gate.

Every test builds its inputs in memory: no ELF, no toolchain, no build tree.
The point is that each fail-closed rule is exercised in BOTH directions --
a passing case and at least one negative case that must raise.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_pmu_cfg as cfg  # noqa: E402

GateError = cfg.GateError

# A synthetic stand-in for the GENERATED register header. Only the fields the
# gate reads are present; the values mirror the real generated encoding.
REGS = """
#define NPU_REG_PMCCNTR_CFG 0x0034U
#define NPU_REG_PMCR 0x0028U
#define NPU_REG_PMCNTENSET 0x002CU
#define NPU_REG_PMOVSSET 0x0030U
#define NPU_PMU_PMCCNTR_CFG_START_SHIFT 0U
#define NPU_PMU_PMCCNTR_CFG_START_MASK  0x000003FFU
#define NPU_PMU_PMCCNTR_CFG_STOP_SHIFT  16U
#define NPU_PMU_PMCCNTR_CFG_STOP_MASK   0x03FF0000U
#define NPU_PMU_EVENT_CYCLE             17U
#define NPU_PMU_EVENT_NO_EVENT          0U
"""


def _tu(*writes):
    """A fake preprocessed translation unit with the given CFG write args."""
    body = "int main(void) { pmu_reg_write(0x0028U, 1U);\n"
    for w in writes:
        body += "  pmu_reg_write(0x0034U, %s);\n" % w
    return body + "return 0; }\n"


# --- generated value composition -------------------------------------------

def test_generated_values_compose_from_header_not_literals():
    b, c = cfg.generated_cfg_values(REGS)
    assert b == 0x11, "START=CYCLE(17) | STOP=NO_EVENT(0) must compose to 0x11"
    assert c == 0, "case C must compose to an explicit zero"


def test_generated_values_reject_non_zero_no_event():
    bad = REGS.replace("#define NPU_PMU_EVENT_NO_EVENT          0U",
                       "#define NPU_PMU_EVENT_NO_EVENT          3U")
    with pytest.raises(GateError, match="explicit ZERO"):
        cfg.generated_cfg_values(bad)


def test_generated_values_reject_zero_cycle_encoding():
    bad = REGS.replace("#define NPU_PMU_EVENT_CYCLE             17U",
                       "#define NPU_PMU_EVENT_CYCLE             0U")
    with pytest.raises(GateError, match="non-zero"):
        cfg.generated_cfg_values(bad)


def test_plain_define_requires_exactly_one_definition():
    with pytest.raises(GateError, match="found 0"):
        cfg._plain_define(REGS, "NPU_PMU_EVENT_MISSING")
    dup = REGS + "#define NPU_PMU_EVENT_CYCLE 17U\n"
    with pytest.raises(GateError, match="found 2"):
        cfg._plain_define(dup, "NPU_PMU_EVENT_CYCLE")


def test_case_contract_values():
    assert cfg.case_contract("A", REGS) == (0, None)
    assert cfg.case_contract("B", REGS) == (1, 0x11)
    assert cfg.case_contract("C", REGS) == (1, 0)
    with pytest.raises(GateError, match="unknown CFG case"):
        cfg.case_contract("D", REGS)


# --- the substituted per-case contract --------------------------------------

def test_case_a_accepts_zero_writes():
    assert cfg.check_cfg_case_contract("A", _tu(), REGS) == (0, None)


def test_case_a_rejects_any_write():
    with pytest.raises(GateError, match="PMCCNTR_CFG write"):
        cfg.check_cfg_case_contract("A", _tu("0x11U"), REGS)


def test_case_b_accepts_the_generated_cycle_value():
    assert cfg.check_cfg_case_contract("B", _tu("0x11U"), REGS) == (1, 0x11)


def test_case_b_accepts_the_composed_expression_form():
    # The preprocessed TU may carry the expanded arithmetic rather than a
    # folded literal; both must resolve identically.
    expr = "(((17U << 0U) & 0x000003FFU) | ((0U << 16U) & 0x03FF0000U))"
    assert cfg.check_cfg_case_contract("B", _tu(expr), REGS) == (1, 0x11)


def test_case_b_rejects_a_wrong_value():
    with pytest.raises(GateError, match="requires 0x11"):
        cfg.check_cfg_case_contract("B", _tu("0x12U"), REGS)


def test_case_b_rejects_a_missing_write():
    with pytest.raises(GateError, match="exactly 1"):
        cfg.check_cfg_case_contract("B", _tu(), REGS)


def test_case_b_rejects_a_duplicated_write():
    with pytest.raises(GateError, match="exactly 1"):
        cfg.check_cfg_case_contract("B", _tu("0x11U", "0x11U"), REGS)


def test_case_c_accepts_explicit_zero():
    assert cfg.check_cfg_case_contract("C", _tu("0x0U"), REGS) == (1, 0)


def test_case_c_rejects_a_non_zero_write():
    with pytest.raises(GateError, match="requires 0x0"):
        cfg.check_cfg_case_contract("C", _tu("0x11U"), REGS)


def test_a_and_c_differ_only_in_write_count_not_final_value():
    """The load-bearing pair, asserted directly."""
    a_count, a_value = cfg.check_cfg_case_contract("A", _tu(), REGS)
    c_count, c_value = cfg.check_cfg_case_contract("C", _tu("0x0U"), REGS)
    assert a_count == 0 and c_count == 1, "write counts must differ 0 vs 1"
    assert a_value is None and c_value == 0, "both end at CFG value zero"


def test_literal_value_refuses_non_arithmetic():
    with pytest.raises(GateError, match="pure integer arithmetic"):
        cfg.check_cfg_case_contract("B", _tu("some_runtime_variable"), REGS)


# --- matrix gate -------------------------------------------------------------

# A realistic flag line: only the build id and the case macro may vary.
FLAG_TEMPLATE = (
    "-mcpu=cortex-m85+nomve+nofp -mthumb -std=gnu11 -O1 -g3 "
    "-ffunction-sections -fdata-sections -fno-builtin-printf "
    "-DMEASUREMENT_BUILD -DPMU_DIAG_BUILD -DPMU_QUAL_SCHEMA_V8 "
    "-DPMU_QUAL_MODE_Q1 -DPMU_QUAL_CFG_EXPERIMENT {case} "
    "-DPMU_DIAG_SEAM_S1 -DRUNNER_FIRMWARE_BUILD_ID={bid} -ISelftest_pmu -MMD -MP"
)

BUILD_IDS = {"A": "0x31414350", "B": "0x31424350", "C": "0x31434350"}


def _flags(case, case_macro=None, bid=None):
    return FLAG_TEMPLATE.format(
        case=case_macro or ("-DPMU_DIAG_CASE_%s" % case),
        bid=bid or BUILD_IDS[case])


def _doc(case, build_id, **over):
    d = {
        "cfg_case": case,
        "cfg_case_id": cfg.CASE_ID[case],
        "build_id": build_id,
        "cfg_expected_write_count": 0 if case == "A" else 1,
        "cfg_expected_value": None if case == "A" else (
            "0x00000011" if case == "B" else "0x00000000"),
        "compiler_flags": _flags(case),
        "artifact_sha256": {"APP.BIN": "aa" + case},
        # common terms -- identical across cases by contract
        "schema_version": 8,
        "vendor_object_sha256": "vobj",
        "vendor_source_sha256": "vsrc",
        "callsite_disassembly_sha256": "digest",
        "hook_order_sha256": "hookorder",
        "stop_store_address": 1,
        "target_call_address": 2,
        "expected_return_address": 3,
        "release_store_address": 4,
        "release_immediate_value": 12,
        "test_cpm": 1,
        # Declared layout shift: A (no write) must be lowest.
        "hook_wrapper_call_address": {"A": 1000, "B": 1020, "C": 1024}[case],
    }
    d.update(over)
    return d


def _write_matrix(tmp_path, docs):
    paths = {}
    for case, doc in docs.items():
        p = tmp_path / ("m%s.json" % case)
        p.write_text(json.dumps(doc))
        paths[case] = str(p)
    return paths


def _default_docs():
    return {"A": _doc("A", "0x31414350"),
            "B": _doc("B", "0x31424350"),
            "C": _doc("C", "0x31434350")}


def test_matrix_accepts_identity_only_differences(tmp_path):
    docs = cfg.matrix_check(_write_matrix(tmp_path, _default_docs()))
    assert set(docs) == {"A", "B", "C"}


def test_matrix_rejects_a_differing_common_term(tmp_path):
    d = _default_docs()
    d["B"]["callsite_disassembly_sha256"] = "DIFFERENT"
    with pytest.raises(GateError, match="unexpected non-identity differences"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_a_differing_vendor_object(tmp_path):
    d = _default_docs()
    d["C"]["vendor_object_sha256"] = "OTHER"
    with pytest.raises(GateError, match="vendor_object_sha256"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_a_differing_hook_order(tmp_path):
    d = _default_docs()
    d["A"]["hook_order_sha256"] = "OTHER"
    with pytest.raises(GateError, match="hook_order_sha256"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_duplicate_build_ids(tmp_path):
    d = _default_docs()
    d["C"]["build_id"] = d["B"]["build_id"]
    with pytest.raises(GateError, match="build ids are not unique"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_mislabelled_case(tmp_path):
    d = _default_docs()
    d["B"]["cfg_case"] = "C"
    with pytest.raises(GateError, match="self-reports cfg_case"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_case_a_with_a_write(tmp_path):
    d = _default_docs()
    d["A"]["cfg_expected_write_count"] = 1
    with pytest.raises(GateError, match="case A must have 0 CFG writes"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_case_c_without_a_write(tmp_path):
    d = _default_docs()
    d["C"]["cfg_expected_write_count"] = 0
    with pytest.raises(GateError, match="case C must have exactly 1"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_case_c_non_zero_value(tmp_path):
    d = _default_docs()
    d["C"]["cfg_expected_value"] = "0x00000011"
    with pytest.raises(GateError, match="case C must write an explicit ZERO"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_case_b_zero_value(tmp_path):
    d = _default_docs()
    d["B"]["cfg_expected_value"] = "0x00000000"
    with pytest.raises(GateError, match="case B must write exactly one"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_a_new_unlisted_manifest_key(tmp_path):
    """A key nobody declared as identity-only must fail closed, not pass."""
    d = _default_docs()
    d["A"]["some_future_field"] = 1
    d["B"]["some_future_field"] = 2
    d["C"]["some_future_field"] = 3
    with pytest.raises(GateError, match="some_future_field"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_accepts_the_declared_layout_shift(tmp_path):
    """A/B/C hook call sites may differ, but only in the declared direction."""
    docs = cfg.matrix_check(_write_matrix(tmp_path, _default_docs()))
    shifts = cfg.check_layout_shift(docs)["hook_wrapper_call_address"]
    assert shifts["A"] < shifts["B"] and shifts["A"] < shifts["C"]


def test_matrix_rejects_a_layout_shift_in_the_wrong_direction(tmp_path):
    """If A is not lowest, the shift did not come from the added write."""
    d = _default_docs()
    d["A"]["hook_wrapper_call_address"] = 9999
    with pytest.raises(GateError, match="lowest address"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_matrix_rejects_a_missing_layout_key(tmp_path):
    d = _default_docs()
    del d["B"]["hook_wrapper_call_address"]
    with pytest.raises(GateError, match="missing from a manifest"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_hook_body_addresses_are_still_common_terms(tmp_path):
    """Only the CALL SITE is exempt; the hook's own addresses are not."""
    assert "hook_pmu_disable_address" not in cfg.LAYOUT_SHIFT_KEYS
    d = _default_docs()
    for case, addr in (("A", 1), ("B", 2), ("C", 3)):
        d[case]["hook_pmu_disable_address"] = addr
    with pytest.raises(GateError, match="hook_pmu_disable_address"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_identity_only_keys_are_the_documented_set():
    assert set(cfg.IDENTITY_ONLY_KEYS) == {
        "build_id", "cfg_case", "cfg_case_id", "cfg_expected_write_count",
        "cfg_expected_value", "artifact_sha256"}
    assert "compiler_flags" not in cfg.IDENTITY_ONLY_KEYS


def test_structural_mode_is_q1():
    """The CFG images must be held to the Q1 hook rules, not Q0's."""
    assert cfg.CFG_STRUCTURAL_MODE == "Q1"


# --- compiler flag normalization (fail-closed) ------------------------------

def test_flags_normalize_only_the_two_declared_variables():
    a = cfg.normalize_compiler_flags(_flags("A"))
    b = cfg.normalize_compiler_flags(_flags("B"))
    c = cfg.normalize_compiler_flags(_flags("C"))
    assert a == b == c, "only build id and case macro may differ"
    assert "<BUILD_ID>" in a and "<CASE>" in a
    assert "-O1" in a and "-fno-builtin-printf" in a


def test_flags_identity_accepts_the_real_shape(tmp_path):
    cfg.matrix_check(_write_matrix(tmp_path, _default_docs()))


def test_flags_reject_optimization_drift(tmp_path):
    d = _default_docs()
    d["B"]["compiler_flags"] = _flags("B").replace("-O1", "-O2")
    with pytest.raises(GateError, match="compiler flags differ"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_an_unrelated_define_drift(tmp_path):
    d = _default_docs()
    d["C"]["compiler_flags"] = _flags("C") + " -DSOMETHING_ELSE=1"
    with pytest.raises(GateError, match="compiler flags differ"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_dropping_fno_builtin_printf(tmp_path):
    d = _default_docs()
    d["A"]["compiler_flags"] = _flags("A").replace(" -fno-builtin-printf", "")
    with pytest.raises(GateError, match="compiler flags differ"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_reordering(tmp_path):
    d = _default_docs()
    toks = _flags("B").split()
    toks[0], toks[1] = toks[1], toks[0]
    d["B"]["compiler_flags"] = " ".join(toks)
    with pytest.raises(GateError, match="compiler flags differ"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_include_path_drift(tmp_path):
    d = _default_docs()
    d["C"]["compiler_flags"] = _flags("C").replace("-ISelftest_pmu", "-IOther")
    with pytest.raises(GateError, match="compiler flags differ"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_a_missing_required_flag(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = _flags(case).replace(
            " -DPMU_QUAL_CFG_EXPERIMENT", "")
    with pytest.raises(GateError, match="missing the required flag"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_wrong_case_macro(tmp_path):
    d = _default_docs()
    d["B"]["compiler_flags"] = _flags("B", case_macro="-DPMU_DIAG_CASE_A")
    with pytest.raises(GateError,
                       match=r"carries -DPMU_DIAG_CASE_A, expected -DPMU_DIAG_CASE_B"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_flags_reject_lto(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = _flags(case) + " -flto"
    with pytest.raises(GateError, match="enables LTO"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_compiler_flags_is_not_wholesale_exempt():
    assert "compiler_flags" not in cfg.IDENTITY_ONLY_KEYS
    assert "compiler_flags" in cfg.NORMALIZED_KEYS


# --- exactly-one case macro / build id, and build-id agreement --------------
#
# Each negative below perturbs ALL THREE cases identically, so the normalized
# cross-case comparison still passes and the per-case rule under test is what
# actually fires. Perturbing one case only would trip the earlier "flags
# differ" check and prove nothing about these rules.

def test_build_id_agreement_positive(tmp_path):
    """The happy path: every compiler build id equals its manifest build id."""
    docs = cfg.matrix_check(_write_matrix(tmp_path, _default_docs()))
    for case in ("A", "B", "C"):
        flag = [t for t in docs[case]["compiler_flags"].split()
                if t.startswith("-DRUNNER_FIRMWARE_BUILD_ID=")][0]
        assert int(flag.split("=", 1)[1], 0) == int(docs[case]["build_id"], 16)


def test_reject_duplicate_same_case_macro(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = (_flags(case)
                                     + " -DPMU_DIAG_CASE_%s" % case)
    with pytest.raises(GateError, match="exactly ONE PMU_DIAG_CASE macro"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_reject_two_different_case_macros(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = _flags(case) + " -DPMU_DIAG_CASE_C"
    with pytest.raises(GateError, match="exactly ONE PMU_DIAG_CASE macro"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_reject_duplicate_build_id_define(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = (_flags(case)
                                     + " -DRUNNER_FIRMWARE_BUILD_ID=0x31414350")
    with pytest.raises(GateError,
                       match="exactly ONE RUNNER_FIRMWARE_BUILD_ID define"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_reject_unparsable_build_id(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = _flags(case, bid="notanumber")
    with pytest.raises(GateError, match="unparsable RUNNER_FIRMWARE_BUILD_ID"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_reject_build_id_disagreeing_with_manifest(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["compiler_flags"] = _flags(case, bid="0xDEADBEEF")
    with pytest.raises(GateError, match="does not match the manifest build id"):
        cfg.matrix_check(_write_matrix(tmp_path, d))


def test_reject_unparsable_manifest_build_id(tmp_path):
    d = _default_docs()
    for case in ("A", "B", "C"):
        d[case]["build_id"] = "not-hex-%s" % case
    with pytest.raises(GateError, match="no parsable manifest build_id"):
        cfg.matrix_check(_write_matrix(tmp_path, d))
