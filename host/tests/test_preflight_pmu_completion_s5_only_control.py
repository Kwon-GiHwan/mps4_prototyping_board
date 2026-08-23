"""The pre-board gate, and what it refuses to call cleared.

Its hardest job is being honest about its own edge. Six checks need a device,
and each is reported as PENDING_DEPLOYMENT rather than omitted -- because a
reader who counts eight PASSes and sees nothing else will conclude the candidate
is cleared, which is exactly the reading this gate exists to prevent.

So the first test here is that an overall PASS is unreachable while anything is
outstanding, and that it is unreachable by construction rather than by the
present data happening to leave something pending.

The rest are the questions a reader should ask of the evidence: was this
measured on the artifact being shipped, against the reference actually pinned,
and is any of it stale.
"""

import copy
import json
import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import canonical_elf_pmu_completion_s5_only_control as canonical  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deploy  # noqa: E402
import preflight_pmu_completion_s5_only_control as pre  # noqa: E402


EVIDENCE = REPO / "docs/superpowers/evidence/v15-preboard-qualification-20260821"

ARTIFACTS = {
    "app_sha256": "4967fa39205eefb11601be165b0e553239d2b201e4b5019d4efb7bf1ba6dc693",
    "vectors_sha256": "6864a22bf98b0172ee7ace58aead9c6d85ebd3afec64ddae0771bbe2474d0d91",
    "ddr_sha256": "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
    "raw_elf_sha256": "c2373581fe344e3ab35199693fe157ca710b2bb9441442df8986f31a78fe882b",
    "analysis_elf_sha256": "49d225401b7bf15978d9bf04815e603d0df3db25d752cd0f4778d199378c99d6",
}


def documents():
    """The real evidence, reloaded per test so edits cannot leak between them."""

    return (
        json.loads((EVIDENCE / "build_manifest.json").read_text()),
        json.loads((EVIDENCE / "equivalence_evidence.json").read_text()),
        json.loads((EVIDENCE / "static_evidence.json").read_text()),
        copy.deepcopy(ARTIFACTS),
    )


def run(manifest=None, equivalence=None, static=None, artifacts=None):
    m, e, s, a = documents()
    return pre.preflight(
        manifest if manifest is not None else m,
        equivalence if equivalence is not None else e,
        static if static is not None else s,
        artifacts if artifacts is not None else a,
    )


def resealed(manifest, **changes):
    document = dict(manifest)
    document.update(changes)
    return deploy.seal_manifest(document)


class TheRealCandidateClearsWhatCanBeCleared(unittest.TestCase):
    def test_the_eight_board_independent_checks_pass(self):
        result = run()
        independent = {
            k: v for k, v in result["checks"].items()
            if k not in pre.BOARD_DEPENDENT_CHECKS
        }
        self.assertEqual(len(independent), 8)
        self.assertEqual(set(independent.values()), {pre.STATUS_PASS})

    def test_the_mode_and_identities_come_out_of_the_real_evidence(self):
        result = run()
        self.assertEqual(result["comparison_mode"], contract.Q_S5_EQUIVALENT)
        self.assertEqual(len(result["candidate_identity"]), 64)
        self.assertEqual(
            result["v14_q_analysis_elf_sha256"], canonical.V14_Q_ANALYSIS_ELF_SHA256
        )


class AnOverallPassIsUnreachableBeforeDeployment(unittest.TestCase):
    def test_the_overall_verdict_is_pending_not_pass(self):
        self.assertEqual(run()["overall"], pre.STATUS_PENDING)

    def test_every_board_dependent_check_is_reported_rather_than_omitted(self):
        checks = run()["checks"]
        for name in pre.BOARD_DEPENDENT_CHECKS:
            self.assertEqual(checks[name], pre.STATUS_PENDING, name)

    def test_the_pending_list_names_them(self):
        self.assertEqual(set(run()["pending"]), set(pre.BOARD_DEPENDENT_CHECKS))

    def test_pass_would_require_the_pending_set_to_be_empty(self):
        # Unreachable by construction, not because today's data happens to leave
        # something outstanding.
        self.assertTrue(pre.BOARD_DEPENDENT_CHECKS)
        result = run()
        self.assertTrue(result["pending"])
        self.assertNotEqual(result["overall"], pre.STATUS_PASS)

    def test_deployment_verified_is_never_read_as_a_pass(self):
        self.assertEqual(run()["checks"]["destination_readback_equality"],
                         pre.STATUS_PENDING)

    def test_evidence_claiming_a_verified_deployment_is_refused(self):
        m, e, s, a = documents()
        real = deploy.verify_evidence_chain

        def lying(manifest, equivalence, static):
            document = real(manifest, equivalence, static)
            document["deployment_verified"] = True
            return document

        deploy.verify_evidence_chain = lying
        try:
            with self.assertRaises(pre.PreflightError) as caught:
                pre.preflight(m, e, s, a)
        finally:
            deploy.verify_evidence_chain = real
        self.assertEqual(
            pre.refusal_rule(caught.exception),
            pre.RULE_DEPLOYMENT_TREATED_AS_VERIFIED,
        )

    def test_board_authorization_is_recorded_as_not_requested(self):
        self.assertEqual(run()["board_authorization"], "NOT_REQUESTED")

    def test_task_14b_is_recorded_as_blocked(self):
        self.assertIn("BLOCKED", run()["task_14b_final_positive_path"])


class TheGatesMustHaveRunOnTheShippedArtifact(unittest.TestCase):
    def test_evidence_without_the_pinned_transform_is_refused(self):
        m, e, s, a = documents()
        del e["analysis_elf_transform"]
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF
        )

    def test_a_different_transform_is_refused(self):
        m, e, s, a = documents()
        e["analysis_elf_transform"] = dict(
            canonical.ANALYSIS_ELF_TRANSFORM, operation="--strip-all"
        )
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF
        )

    def test_gates_run_on_a_different_elf_than_the_one_shipped_is_refused(self):
        m, e, s, a = documents()
        e["v15_analysis_elf_sha256"] = "aa" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_GATE_NOT_RUN_ON_ANALYSIS_ELF
        )


class EveryGateVerdictMustBePass(unittest.TestCase):
    def test_a_failed_gate_is_refused(self):
        for name in pre.GATE_VERDICTS_REQUIRED:
            m, e, s, a = documents()
            s[name] = "FAIL"
            with self.assertRaises(pre.PreflightError) as caught:
                pre.preflight(m, e, s, a)
            self.assertEqual(
                pre.refusal_rule(caught.exception), pre.RULE_GATE_VERDICT_NOT_PASS, name
            )

    def test_a_missing_verdict_is_not_a_pass(self):
        m, e, s, a = documents()
        del s["equivalence_verdict"]
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_GATE_VERDICT_NOT_PASS
        )

    def test_an_unproven_verdict_is_not_a_pass(self):
        m, e, s, a = documents()
        s["equivalence_verdict"] = "UNPROVEN"
        with self.assertRaises(pre.PreflightError):
            pre.preflight(m, e, s, a)


class TheReferenceMustBeThePinnedOne(unittest.TestCase):
    def test_another_v14_q_analysis_elf_is_refused(self):
        m, e, s, a = documents()
        e["v14_q_analysis_elf_sha256"] = "bb" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception),
            pre.RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF,
        )

    def test_the_raw_reference_digest_is_refused_in_that_position(self):
        m, e, s, a = documents()
        e["v14_q_analysis_elf_sha256"] = canonical.V14_Q_RAW_ELF_SAME_PATH_OBSERVATION
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_RAW_ELF_IN_IDENTITY_POSITION
        )

    def test_a_reference_app_that_is_not_the_one_that_ran_is_refused(self):
        m, e, s, a = documents()
        e["v14_q_app_sha256"] = "cc" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception),
            pre.RULE_REFERENCE_NOT_PINNED_ANALYSIS_ELF,
        )


class StaleEvidenceCannotSlipThrough(unittest.TestCase):
    def test_a_manifest_describing_a_different_build_is_refused(self):
        m, e, s, a = documents()
        a["app_sha256"] = "dd" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(pre.refusal_rule(caught.exception), pre.RULE_STALE_EVIDENCE)

    def test_an_unmeasured_artifact_is_not_assumed_to_match(self):
        m, e, s, a = documents()
        del a["vectors_sha256"]
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(pre.refusal_rule(caught.exception), pre.RULE_STALE_EVIDENCE)

    def test_a_stale_analysis_elf_is_refused(self):
        m, e, s, a = documents()
        a["analysis_elf_sha256"] = "ee" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(pre.refusal_rule(caught.exception), pre.RULE_STALE_EVIDENCE)

    def test_raw_and_analysis_being_the_same_digest_is_refused(self):
        # One of them cannot have come through the transform.
        m, e, s, a = documents()
        m = resealed(m, raw_elf_sha256=m["analysis_elf_sha256"])
        a["raw_elf_sha256"] = m["analysis_elf_sha256"]
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(pre.refusal_rule(caught.exception), pre.RULE_STALE_EVIDENCE)


class ThePollCountContractHolds(unittest.TestCase):
    def test_the_recorded_transport_and_admission_are_the_frozen_ones(self):
        m, e, s, a = documents()
        self.assertEqual(s["poll_count_transport"], contract.POLL_COUNT_PRESENT)
        self.assertEqual(s["poll_count_admission"], contract.POLL_COUNT_NOT_ADMITTED)

    def test_admitting_the_poll_count_is_refused(self):
        m, e, s, a = documents()
        s["poll_count_admission"] = contract.POLL_COUNT_ADMITTED
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_POLL_COUNT_CONTRACT_BROKEN
        )

    def test_claiming_the_count_was_omitted_is_refused(self):
        m, e, s, a = documents()
        s["poll_count_transport"] = contract.POLL_COUNT_ABSENT
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_POLL_COUNT_CONTRACT_BROKEN
        )


class TheBindingIsDelegatedAndItsFailureSurfaces(unittest.TestCase):
    def test_a_broken_document_citation_is_refused(self):
        m, e, s, a = documents()
        s["equivalence_evidence_sha256"] = "ff" * 32
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_EVIDENCE_BINDING_BROKEN
        )

    def test_a_mode_disagreement_surfaces_as_a_binding_failure(self):
        m, e, s, a = documents()
        s["comparison_mode"] = contract.S5_WITHIN_VARIANT_ONLY
        with self.assertRaises(pre.PreflightError) as caught:
            pre.preflight(m, e, s, a)
        self.assertEqual(
            pre.refusal_rule(caught.exception), pre.RULE_EVIDENCE_BINDING_BROKEN
        )


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_gate_declares(self):
        def stale():
            m, e, s, a = documents()
            a["app_sha256"] = "dd" * 32
            return pre.preflight(m, e, s, a)

        def not_pass():
            m, e, s, a = documents()
            s["equivalence_verdict"] = "FAIL"
            return pre.preflight(m, e, s, a)

        def wrong_elf():
            m, e, s, a = documents()
            e["v15_analysis_elf_sha256"] = "aa" * 32
            return pre.preflight(m, e, s, a)

        def wrong_ref():
            m, e, s, a = documents()
            e["v14_q_analysis_elf_sha256"] = "bb" * 32
            return pre.preflight(m, e, s, a)

        def raw_ref():
            m, e, s, a = documents()
            e["v14_q_analysis_elf_sha256"] = canonical.V14_Q_RAW_ELF_SAME_PATH_OBSERVATION
            return pre.preflight(m, e, s, a)

        def binding():
            m, e, s, a = documents()
            s["equivalence_evidence_sha256"] = "ff" * 32
            return pre.preflight(m, e, s, a)

        def poll():
            m, e, s, a = documents()
            s["poll_count_admission"] = contract.POLL_COUNT_ADMITTED
            return pre.preflight(m, e, s, a)

        def deployment_lie():
            m, e, s, a = documents()
            real = deploy.verify_evidence_chain
            deploy.verify_evidence_chain = lambda *args: dict(
                real(*args), deployment_verified=True
            )
            try:
                return pre.preflight(m, e, s, a)
            finally:
                deploy.verify_evidence_chain = real

        def mode_gone():
            m, e, s, a = documents()
            real = deploy.verify_evidence_chain
            deploy.verify_evidence_chain = lambda *args: dict(
                real(*args), comparison_mode="SOMETHING_ELSE"
            )
            try:
                return pre.preflight(m, e, s, a)
            finally:
                deploy.verify_evidence_chain = real

        def identity_moved():
            m, e, s, a = documents()
            real = deploy.verify_evidence_chain
            deploy.verify_evidence_chain = lambda *args: dict(
                real(*args), candidate_identity="00" * 32
            )
            try:
                return pre.preflight(m, e, s, a)
            finally:
                deploy.verify_evidence_chain = real

        tripped = set()
        for attempt in (stale, not_pass, wrong_elf, wrong_ref, raw_ref, binding,
                        poll, deployment_lie, mode_gone, identity_moved):
            try:
                attempt()
            except pre.PreflightError as exc:
                tripped.add(pre.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(pre, name) for name in pre.RULES})


if __name__ == "__main__":
    unittest.main()
