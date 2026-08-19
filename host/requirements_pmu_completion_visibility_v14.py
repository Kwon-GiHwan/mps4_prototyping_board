#!/usr/bin/env python3
"""Which layer decides each V14 claim, and where that decision is proved.

The contract is now large enough that "it is tested" has stopped being a useful
sentence. A claim can be checked in four places and decided in none of them, or
decided in two places that mean different things by it -- which is the failure
this table exists to make impossible.

Every requirement names exactly one **authority**: the layer whose answer is the
answer. The other layers may corroborate, and they are listed, but they do not
decide. "QSIZE is never read while the NPU runs" is decided by the linked image,
not by the source that produced it and not by the host that reads its records.
"This sample is valid" is decided by the parser and classifier, not by the
collector that stores it. "This campaign supports that conclusion" is decided by
the analyzer. "The board may be touched" is decided by the preflight machine.

The table is data, and the suite next to it checks the data rather than trusting
it: every firmware rule named here must exist and must carry its own targeted
negative in the checker's claim matrix, every host function named here must
exist, every test named here must exist, and every requirement must name exactly
one authority. A requirement that drifts out of its implementation fails.
"""

from __future__ import annotations


# The layers, in the order evidence flows through them.
SOURCE = "source/generator"
ELF = "linked ELF"
PROVENANCE = "manifest/provenance"
PARSER = "host parser/classifier"
COLLECTOR = "collector"
ANALYZER = "analyzer"
PREFLIGHT = "board preflight"

LAYERS = (SOURCE, ELF, PROVENANCE, PARSER, COLLECTOR, ANALYZER, PREFLIGHT)

QUALIFIED = "QUALIFIED"


def _req(
    identifier,
    claim,
    authority,
    *,
    rules=(),
    corroborated_by=(),
    functions=(),
    tests=(),
    real_artifact,
    note=None,
):
    """One row. ``rules`` are firmware claim-matrix rules; ``tests`` are host tests.

    ``real_artifact`` says whether this requirement's authority has been applied
    to the artifact that would ship -- the three real images, the real generated
    sources, the real build trees -- as opposed to only to fixtures.
    """

    return {
        "id": identifier,
        "claim": claim,
        "authority": authority,
        "corroborated_by": tuple(corroborated_by),
        "rules": tuple(rules),
        "functions": tuple(functions),
        "tests": tuple(tests),
        "real_artifact": real_artifact,
        "note": note,
        "status": QUALIFIED,
    }


REQUIREMENTS = (
    # ---------------------------------------------------------------- ELF ---
    _req(
        "R01_QSIZE_STOPPED_ONLY",
        "QSIZE is read only while the NPU is stopped, never from the measured loop",
        ELF,
        rules=("RULE_PRIMARY_NO_QSIZE",),
        corroborated_by=(SOURCE,),
        real_artifact=True,
        note="the source can be written correctly and compiled into a loop that reads it; "
        "the image is what runs",
    ),
    _req(
        "R02_PRE_RUN_GATE_DOMINATES",
        "the stopped-state gate runs before the queue is programmed, on every path",
        ELF,
        rules=("RULE_PRE_PROGRAM_DOMINANCE",),
        corroborated_by=(SOURCE,),
        real_artifact=True,
    ),
    _req(
        "R03_NO_TRANSITION_BEFORE_PROGRAMMING",
        "nothing starts the NPU between that gate and the programming it guards",
        ELF,
        rules=("RULE_NO_TRANSITION_BEFORE_PROGRAMMING",),
        real_artifact=True,
    ),
    _req(
        "R04_GATE_SHAPE",
        "the gate reads STATUS exactly once, in one function",
        SOURCE,
        rules=("RULE_PRE_PROGRAM_GATE_SHAPE",),
        corroborated_by=(ELF,),
        real_artifact=True,
        note="decided on the generated text: it is a statement about how the gate is "
        "written, and the compiler is free to schedule the read it produces",
    ),
    _req(
        "R05_PRIMARY_READ_ORDER",
        "the measured loop reads what the variant is named for, in that order",
        ELF,
        rules=("RULE_PRIMARY_READ_ORDER",),
        corroborated_by=(SOURCE,),
        real_artifact=True,
    ),
    _req(
        "R06_PRIMARY_UNPERTURBED",
        "the measured loop carries no per-iteration store, call or timestamp",
        ELF,
        rules=("RULE_PRIMARY_NO_PER_ITERATION_EFFECT",),
        real_artifact=True,
    ),
    _req(
        "R07_FAULT_PRIORITY",
        "reset and fault are decided before completion is",
        ELF,
        rules=("RULE_PRIMARY_FAULT_PRIORITY",),
        real_artifact=True,
    ),
    _req(
        "R08_IRQ_NOT_AN_EXIT",
        "irq_raised is observed and never becomes an exit condition",
        ELF,
        rules=("RULE_PRIMARY_IRQ_NOT_AN_EXIT",),
        corroborated_by=(SOURCE,),
        real_artifact=True,
    ),
    _req(
        "R09_COMMON_TAIL",
        "every variant joins one convergence tail, identical up to relocation",
        ELF,
        rules=("RULE_TAIL_SHARED",),
        real_artifact=True,
    ),
    _req(
        "R10_TAIL_CONTRACT",
        "the tail reads QREAD then STATUS per iteration, decides all four conditions "
        "from one tuple, carries the contract's bound, and perturbs nothing per iteration",
        ELF,
        rules=(
            "RULE_TAIL_READ_ORDER",
            "RULE_TAIL_FOUR_CONDITIONS",
            "RULE_TAIL_BOUND",
            "RULE_TAIL_NO_PER_ITERATION_EFFECT",
        ),
        real_artifact=True,
    ),
    _req(
        "R11_READ_ORDER_EQUIVALENCE",
        "QS and SQ differ in read order and in nothing else",
        ELF,
        rules=("RULE_READ_ORDER_EQUIVALENCE",),
        real_artifact=True,
        note="the whole experiment rests on this: a difference anywhere else would be "
        "an alternative explanation for whatever the campaign observes",
    ),
    _req(
        "R12_MAILBOX_PUBLICATION",
        "the validity word is written once, by the publisher, to that word alone, fenced "
        "on both sides",
        ELF,
        rules=(
            "RULE_MAILBOX_PUBLISHED_ONCE",
            "RULE_MAILBOX_PUBLISHER_IDENTITY",
            "RULE_MAILBOX_PUBLISH_ADDRESS",
            "RULE_MAILBOX_PUBLISH_FENCED",
        ),
        real_artifact=True,
    ),
    _req(
        "R13_RUNNER_GATED_COPY",
        "the runner reads the whole tuple, only where the magic said there is one, "
        "checks that magic once, and writes no mailbox word",
        ELF,
        rules=(
            "RULE_RUNNER_MAILBOX_GATED",
            "RULE_RUNNER_MAILBOX_READONLY",
            "RULE_RUNNER_MAILBOX_ONE_CHECK",
            "RULE_RUNNER_TUPLE_COMPLETE",
        ),
        real_artifact=True,
    ),
    _req(
        "R14_FRAME_LENGTH",
        "the serializer writes the contract's frame length, countably, through named callees",
        ELF,
        rules=(
            "RULE_SERIALIZATION_LENGTH",
            "RULE_SERIALIZATION_COUNTABLE",
            "RULE_SERIALIZATION_NAMED_CALLEES",
        ),
        corroborated_by=(PARSER,),
        real_artifact=True,
    ),
    _req(
        "R15_RECORD_LAYOUT",
        "the laid-out record is the contract's body, with the appendix contiguous, in wire "
        "order, ending the record, and described by DWARF from the same build",
        ELF,
        rules=(
            "RULE_RECORD_SIZE",
            "RULE_RECORD_APPENDIX_ORDER",
            "RULE_RECORD_APPENDIX_CONTIGUOUS",
            "RULE_RECORD_APPENDIX_ENDS_RECORD",
            "RULE_DWARF_RECORD_PRESENT",
            "RULE_DWARF_MEMBER_READABLE",
            "RULE_DWARF_SIZE_PRESENT",
            "RULE_DWARF_NM_AGREE",
        ),
        corroborated_by=(PARSER,),
        real_artifact=True,
    ),
    _req(
        "R16_NPU_IRQ_NEVER_ENABLED",
        "the NPU interrupt is never enabled, and a write to its enable word this gate "
        "cannot read is refused",
        ELF,
        rules=("RULE_NPU_IRQ_NEVER_ENABLED", "RULE_NPU_IRQ_UNRESOLVED_WRITE"),
        real_artifact=True,
        note="inherited from V12 and, for the first time in V14, actually executed",
    ),
    _req(
        "R17_UNREADABLE_STORE_REFUSED",
        "a store whose addressing form the gate cannot read is refused where it matters",
        ELF,
        rules=("RULE_STORE_FORM_UNREADABLE",),
        real_artifact=True,
    ),
    # --------------------------------------------------------- provenance ---
    _req(
        "R18_BUILD_DETERMINISM_IDENTITY",
        "two builds of a variant declare and produce byte-identical artifacts, and the two "
        "sides are independent artifacts rather than one tree under two names",
        PROVENANCE,
        functions=(
            "compare_declared_builds:compare_variant",
            "compare_declared_builds:build_root_fault",
            "compare_declared_builds:_same_file",
        ),
        tests=(
            "test_compare_declared_builds:test_identical_builds_compare_clean",
            "test_compare_declared_builds:test_the_same_root_on_both_sides_is_refused",
            "test_compare_declared_builds:test_hardlinked_artifacts_are_not_two_builds",
        ),
        real_artifact=True,
        note="artifact identity is decided here; that A and B were two clean runs at two "
        "times is temporal provenance and belongs to the build orchestration, not to this "
        "tool. Adversarially qualified at step 5.",
    ),
    _req(
        "R19_MANIFEST_BINDING",
        "the manifest binds every declared artifact by digest and size, carries its own "
        "self-hash over canonical JSON, and replays against the bundle it describes",
        PROVENANCE,
        functions=("runner_proto_pmu_completion_visibility_v14:verify_manifest",),
        tests=("test_pmu_completion_visibility_v14:test_the_self_hash_covers_every_other_key",),
        real_artifact=True,
    ),
    # -------------------------------------------------------------- parser --
    _req(
        "R20_WIRE_ABI",
        "a frame is a V14 frame only at schema 14, the frozen build id, and the contract's "
        "127 words of 508 bytes",
        PARSER,
        functions=("runner_proto_pmu_completion_visibility_v14:parse_payload",),
        tests=("test_pmu_completion_visibility_v14:test_a_truncated_frame_is_refused",),
        corroborated_by=(ELF,),
        real_artifact=False,
        note="applied to real bytes only when a board runs; until then its authority is "
        "exercised against synthesised frames built from the same constants the image uses",
    ),
    _req(
        "R21_SAMPLE_VALIDITY",
        "a run is a sample only when every phase succeeded and the record is internally "
        "consistent",
        PARSER,
        functions=("runner_proto_pmu_completion_visibility_v14:classify_payload",),
        tests=(
            "test_pmu_completion_visibility_v14:test_the_canonical_frame_is_valid_and_carries_no_problems",
            "test_pmu_completion_visibility_v14:test_a_first_tuple_that_observed_nothing_is_refused",
        ),
        corroborated_by=(COLLECTOR,),
        real_artifact=False,
    ),
    _req(
        "R22_FIRST_TUPLE_CONSISTENCY",
        "the first-tuple flags agree with the cursor and STATUS word they were derived from",
        PARSER,
        functions=("runner_proto_pmu_completion_visibility_v14:classify_payload",),
        tests=("test_pmu_completion_visibility_v14:test_a_first_tuple_that_disagrees_with_its_own_status_is_refused",),
        real_artifact=False,
        note="the flag is the firmware's; the raw words are the firmware's too, and a "
        "record whose flag disagrees with its own words is not a sample",
    ),
    # ----------------------------------------------------------- collector --
    _req(
        "R23_CELL_ACCEPTANCE",
        "a cell is ten runs from one boot, numbered by the firmware's own counter, and a "
        "cell is never completed by topping up a failed attempt",
        COLLECTOR,
        functions=(
            "collect_pmu_completion_visibility_v14:Cell.record_frame",
            "collect_pmu_completion_visibility_v14:Cell._end",
        ),
        tests=(
            "test_collect_pmu_completion_visibility_v14:test_an_invalid_run_ends_the_attempt_rather_than_being_re_offered",
            "test_collect_pmu_completion_visibility_v14:test_a_retry_restarts_at_run_one",
            "test_collect_pmu_completion_visibility_v14:test_the_run_sequence_comes_from_the_frame",
        ),
        real_artifact=False,
    ),
    _req(
        "R24_CAMPAIGN_STOP",
        "an invalid sample quarantines its attempt and stops the campaign before anything "
        "else is accepted",
        COLLECTOR,
        functions=("collect_pmu_completion_visibility_v14:Cell._end",),
        tests=("test_collect_pmu_completion_visibility_v14:test_a_failure_stops_the_campaign_until_disposed",),
        real_artifact=False,
    ),
    # ------------------------------------------------------------ analyzer --
    _req(
        "R25_BALANCED_MATRIX",
        "nine cells, nine distinct boots, every variant in every position exactly once",
        ANALYZER,
        functions=("analyze_pmu_completion_visibility_v14:_validate",),
        tests=("test_analyze_pmu_completion_visibility_v14:test_three_q_cells_on_one_boot_are_not_three_boots",),
        real_artifact=False,
    ),
    _req(
        "R26_CATEGORY_REDERIVED",
        "the read-order category the verdict rests on is re-derived from the record's own "
        "raw fields rather than read from a field someone else computed",
        ANALYZER,
        functions=("analyze_pmu_completion_visibility_v14:_derive_category",),
        tests=(
            "test_analyze_pmu_completion_visibility_v14:test_the_analyzer_rederives_the_category_from_raw_fields",
            "test_analyze_pmu_completion_visibility_v14:test_a_relabelled_sample_is_refused",
        ),
        real_artifact=False,
        note="a verdict that trusts a derived field is a verdict about that field",
    ),
    _req(
        "R27_VERDICT",
        "the campaign yields one of four conclusions, and names none of the claims the "
        "design forbids: no latency, no cross-variant cycle comparison, no simultaneity",
        ANALYZER,
        functions=("analyze_pmu_completion_visibility_v14:analyze",),
        tests=(
            "test_analyze_pmu_completion_visibility_v14:test_order_reversal_concludes_read_order_bias",
            "test_analyze_pmu_completion_visibility_v14:test_q_first_in_both_dual_variants_requires_the_control",
        ),
        real_artifact=False,
        note="the four are READ_ORDER_BIAS_DOMINATES, CONTROL_REQUIRED_NO_FINAL_ORDERING, "
        "NO_GAP_RESOLVED and UNRESOLVED. Naming which register is earlier is not among "
        "them: that claim waits for a fresh bit5-only S5 control.",
    ),
    # ----------------------------------------------------------- preflight --
    _req(
        "R28_BOARD_AUTHORIZATION",
        "the board may be touched only when every mandatory gate is PASS, in order, with "
        "UNPROVEN stopping the run like a failure",
        PREFLIGHT,
        functions=(
            "preflight_pmu_completion_visibility_v14:run_preflight",
            "preflight_pmu_completion_visibility_v14:Preflight",
        ),
        tests=(
            "test_preflight_pmu_completion_visibility_v14:test_the_whole_contract_authorizes_when_everything_passes",
            "test_preflight_pmu_completion_visibility_v14:test_an_unproven_gate_stops_the_run_like_a_failure",
        ),
        real_artifact=False,
        note="UNIT-QUALIFIED; the actual board preflight has not been run",
    ),
    _req(
        "R29_CANDIDATE_IDENTITY",
        "the bytes deployed to the board are the bytes that were qualified, for the variant "
        "the manifest declares",
        PREFLIGHT,
        functions=(
            "preflight_pmu_completion_visibility_v14:gate_candidate_identity",
            "preflight_pmu_completion_visibility_v14:gate_variant_identity",
        ),
        tests=(
            "test_preflight_pmu_completion_visibility_v14:test_a_drifted_digest_fails",
            "test_preflight_pmu_completion_visibility_v14:test_variant_disagreement_fails",
        ),
        corroborated_by=(PROVENANCE,),
        real_artifact=False,
    ),
)


def by_authority():
    counts = {layer: 0 for layer in LAYERS}
    for requirement in REQUIREMENTS:
        counts[requirement["authority"]] += 1
    return counts


def summary():
    """The numbers the step-7 exit criteria ask for."""

    untested = [
        requirement["id"]
        for requirement in REQUIREMENTS
        if not requirement["rules"] and not requirement["tests"]
    ]
    ambiguous = [
        requirement["id"]
        for requirement in REQUIREMENTS
        if requirement["authority"] not in LAYERS
        or requirement["authority"] in requirement["corroborated_by"]
    ]
    return {
        "load_bearing": len(REQUIREMENTS),
        "qualified": sum(1 for r in REQUIREMENTS if r["status"] == QUALIFIED),
        "untested": untested,
        "ambiguous_authority": ambiguous,
        "by_authority": by_authority(),
        "real_artifact_applied": sum(1 for r in REQUIREMENTS if r["real_artifact"]),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(summary(), indent=2, sort_keys=True))
