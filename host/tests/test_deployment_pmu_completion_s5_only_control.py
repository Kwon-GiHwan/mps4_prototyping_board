"""A run is licensed by the image its evidence was computed over, or not at all.

comparison_mode cannot come from the frame, so it comes from static image
evidence, and the question here is whether that evidence is attached to the run
or merely filed next to it.

The chain is walked in the direction it was produced -- equivalence evidence,
static evidence, build manifest -- with the V15 ELF required to be one object at
every step and each document named by its digest in the one that cites it.
Digests sitting side by side would say each document exists; what has to hold is
that each describes the next.

The first attack is not hypothetical. Amendment 1's no-count scratch build is
schema 15, variant S5, and fails equivalence. Its frames parse exactly like the
shipped build's, so before the deployment gate the only thing keeping it out of
an equivalence-mode analysis was that nobody had flashed it.

Tampered manifests are re-sealed before use, or the self-hash rule fires first
and the rule under test is never reached.
"""

import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import comparison_mode_pmu_completion_s5_only_control as chain  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402
import deployment_pmu_completion_s5_only_control as deploy  # noqa: E402


SHIPPED_ELF = "e1" * 32
SCRATCH_ELF = "e2" * 32
OTHER_ELF = "e3" * 32

SHIPPED = {"app": "a1" * 32, "vectors": "b1" * 32, "ddr": "c1" * 32}
SCRATCH = {"app": "a2" * 32, "vectors": "b1" * 32, "ddr": "c1" * 32}

Q_APP = deploy.V14_Q_DEPLOYED_APP_SHA256
Q_ELF = deploy.V14_Q_RECONSTRUCTED_ELF_SHA256


def equivalence(elf=SHIPPED_ELF, mode=contract.Q_S5_EQUIVALENT,
                status=chain.EQUIVALENCE_PASS, reference=chain.Q_REFERENCE_ANCHOR,
                q_app=Q_APP, q_elf=None, **overrides):
    document = {
        "v15_elf_sha256": elf,
        "v14_q_app_sha256": q_app,
        "v14_q_elf_sha256": Q_ELF if q_elf is None else q_elf,
        "v14_q_reference_identity": reference,
        "comparison_mode": mode,
        "status": status,
        "detector_identity": "check_single_register_equivalence",
    }
    document.update(overrides)
    return document


def static(equiv, elf=None, mode=None, **overrides):
    document = {
        "v15_elf_sha256": equiv["v15_elf_sha256"] if elf is None else elf,
        "equivalence_evidence_sha256": deploy.document_digest(equiv),
        "comparison_mode": equiv["comparison_mode"] if mode is None else mode,
        "boundary_image_verdict": "PASS",
        "equivalence_verdict": "PASS",
        "post_freeze_verdict": "PASS",
        "poll_count_transport": contract.POLL_COUNT_PRESENT,
        "poll_count_admission": contract.POLL_COUNT_NOT_ADMITTED,
    }
    document.update(overrides)
    return document


def manifest(equiv, stat, artifacts=None, elf=None, mode=None, **overrides):
    artifacts = artifacts or SHIPPED
    document = {
        "canonical_json": deploy.CANONICAL_JSON,
        "schema_version": contract.SCHEMA_VERSION,
        "build_id": "%08x" % contract.BUILD_ID,
        "variant": "S5",
        "comparison_mode": equiv["comparison_mode"] if mode is None else mode,
        "elf_sha256": equiv["v15_elf_sha256"] if elf is None else elf,
        "app_sha256": artifacts["app"],
        "vectors_sha256": artifacts["vectors"],
        "ddr_sha256": artifacts["ddr"],
        "generated_source_sha256": {"runner": "0" * 64},
        "static_evidence_sha256": deploy.document_digest(stat),
        "equivalence_evidence_sha256": deploy.document_digest(equiv),
        "equivalence_status": equiv["status"],
        "equivalence_elf_sha256": equiv["v15_elf_sha256"],
        "v14_q_reference_identity": equiv["v14_q_reference_identity"],
    }
    document.update(overrides)
    return deploy.seal_manifest(document)


def chain_of(**kwargs):
    """The three documents, consistent unless a test makes them otherwise."""

    equiv = equivalence(**kwargs.pop("equivalence", {}))
    stat = static(equiv, **kwargs.pop("static", {}))
    man = manifest(equiv, stat, **kwargs.pop("manifest", {}))
    return equiv, stat, man


def open_cell(equiv, stat, man, source=None, readback=None, boot_id="b1"):
    source = SHIPPED if source is None else source
    readback = source if readback is None else readback
    return deploy.open_verified_cell(man, equiv, stat, source, readback, boot_id=boot_id)


class TheHappyPathIssuesAContext(unittest.TestCase):
    def test_a_qualified_image_opens_a_cell(self):
        context = open_cell(*chain_of())
        self.assertEqual(context.comparison_mode, contract.Q_S5_EQUIVALENT)
        self.assertEqual(context.app_sha256, SHIPPED["app"])
        self.assertEqual(context.elf_sha256, SHIPPED_ELF)
        self.assertEqual(context.boot_id, "b1")
        self.assertEqual(len(context.manifest_sha256), 64)
        self.assertEqual(len(context.candidate_identity), 64)

    def test_the_manifest_digest_is_taken_from_outside_the_manifest(self):
        equiv, stat, man = chain_of()
        context = open_cell(equiv, stat, man)
        self.assertEqual(context.manifest_sha256, deploy.document_digest(man))
        self.assertNotEqual(context.manifest_sha256, man[deploy.MANIFEST_SELF_HASH_KEY])

    def test_candidate_identity_is_computed_not_chosen(self):
        equiv, stat, man = chain_of()
        other_equiv, other_stat, other_man = chain_of(
            equivalence={"elf": OTHER_ELF}, manifest={"artifacts": SCRATCH}
        )
        self.assertNotEqual(
            deploy.candidate_identity(man), deploy.candidate_identity(other_man)
        )

    def test_the_fallback_opens_a_cell_in_the_fallback_mode(self):
        equiv, stat, man = chain_of(
            equivalence={"mode": contract.S5_WITHIN_VARIANT_ONLY,
                         "status": chain.EQUIVALENCE_FALLBACK}
        )
        self.assertEqual(
            open_cell(equiv, stat, man).comparison_mode, contract.S5_WITHIN_VARIANT_ONLY
        )


class NegativeATheScratchBuildCannotBorrowTheShippedEvidence(unittest.TestCase):
    def test_deploying_the_scratch_app_under_the_shipped_manifest_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(*chain_of(), source=SCRATCH)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_ARTIFACT_NOT_DECLARED
        )

    def test_the_scratch_app_landing_on_the_board_is_refused_at_readback(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(*chain_of(), source=SHIPPED, readback=SCRATCH)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH
        )

    def test_a_vectors_or_ddr_swap_is_refused_too(self):
        for name in ("vectors", "ddr"):
            swapped = dict(SHIPPED)
            swapped[name] = "f" * 64
            with self.assertRaises(deploy.DeploymentError) as caught:
                open_cell(*chain_of(), source=SHIPPED, readback=swapped)
            self.assertEqual(
                deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH, name
            )


class NegativeBAForgedModeDoesNotSurviveItsOwnEvidence(unittest.TestCase):
    def test_claiming_equivalence_over_fallback_evidence_is_refused(self):
        # The whole chain agrees on the mode; the equivalence result does not
        # license it. The mode is evidence-constrained, not declared.
        equiv, stat, man = chain_of(
            equivalence={"mode": contract.Q_S5_EQUIVALENT,
                         "status": chain.EQUIVALENCE_FALLBACK}
        )
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_the_forgery_is_sealed_so_the_self_hash_is_not_what_caught_it(self):
        _, _, man = chain_of(
            equivalence={"mode": contract.Q_S5_EQUIVALENT,
                         "status": chain.EQUIVALENCE_FALLBACK}
        )
        self.assertEqual(
            deploy.manifest_self_hash(man), man[deploy.MANIFEST_SELF_HASH_KEY]
        )

    def test_an_equivalence_status_that_licenses_nothing_is_refused(self):
        equiv, stat, man = chain_of(equivalence={"status": "PROBABLY_FINE"})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EQUIVALENCE_EVIDENCE_UNUSABLE
        )

    def test_an_unknown_comparison_mode_is_refused(self):
        equiv, stat, man = chain_of(equivalence={"mode": "MOSTLY_EQUIVALENT"})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MODE_CONTRADICTS_EVIDENCE
        )


class NegativeCTheEvidenceMustDescribeTheImageThatRuns(unittest.TestCase):
    def test_equivalence_evidence_computed_over_another_elf_is_refused(self):
        # Everything present, everything well formed, and the comparison was
        # made over a different binary.
        equiv = equivalence(elf=OTHER_ELF)
        stat = static(equiv, elf=SHIPPED_ELF)
        man = manifest(equiv, stat, elf=SHIPPED_ELF)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_ELF_UNBOUND
        )

    def test_a_structurally_similar_q_is_not_the_qualified_q(self):
        equiv, stat, man = chain_of(equivalence={"reference": "deadbee"})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_REFERENCE_IDENTITY
        )

    def test_comparing_against_a_v14_q_that_is_not_the_one_that_ran_is_refused(self):
        equiv, stat, man = chain_of(equivalence={"q_app": "9" * 64})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_REFERENCE_IDENTITY
        )

    def test_reading_a_v14_q_elf_that_is_not_the_pinned_reference_is_refused(self):
        # Pinned by the 2026-08-21 reconstruction: this is the ELF whose objcopy
        # output is the deployed artifact set. Any other is a different image.
        equiv, stat, man = chain_of(equivalence={"q_elf": "7" * 64})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_V14_REFERENCE_MISMATCH
        )

    def test_the_analysis_reference_produces_the_deployed_app(self):
        # The relation the reconstruction established, kept as a contract: the
        # pinned ELF is the one whose build output is what the board ran.
        self.assertEqual(
            deploy.V14_Q_ANALYSIS_REFERENCE["produced_app_sha256"],
            deploy.V14_Q_DEPLOYED_REFERENCE["app_sha256"],
        )
        self.assertEqual(
            deploy.V14_Q_RECONSTRUCTION_ATTEMPT_RESULT,
            deploy.RECONSTRUCTION_APP_SET_MATCHED,
        )

    def test_the_reconstruction_does_not_claim_to_have_recovered_the_historical_elf(self):
        # No historical ELF digest was ever recorded, so there is nothing to have
        # matched. The pin is a reconstructed analysis reference and says so.
        self.assertIn("reconstructed_elf_sha256", deploy.V14_Q_ANALYSIS_REFERENCE)
        self.assertNotIn("historical_elf_sha256", deploy.V14_Q_ANALYSIS_REFERENCE)


class N7TheModeIsOneValueAcrossTheChain(unittest.TestCase):
    def test_static_evidence_disagreeing_with_the_manifest_is_refused(self):
        equiv = equivalence()
        stat = static(equiv, mode=contract.S5_WITHIN_VARIANT_ONLY)
        man = manifest(equiv, stat)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception),
            deploy.RULE_MODE_DISAGREES_ACROSS_EVIDENCE,
        )

    def test_the_manifest_disagreeing_with_both_documents_is_refused(self):
        equiv = equivalence()
        stat = static(equiv)
        man = manifest(equiv, stat, mode=contract.S5_WITHIN_VARIANT_ONLY)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception),
            deploy.RULE_MODE_DISAGREES_ACROSS_EVIDENCE,
        )

    def test_two_against_one_does_not_carry_the_vote(self):
        # Whichever way the majority falls, the answer is the same refusal.
        equiv = equivalence(mode=contract.S5_WITHIN_VARIANT_ONLY,
                            status=chain.EQUIVALENCE_FALLBACK)
        stat = static(equiv, mode=contract.Q_S5_EQUIVALENT)
        man = manifest(equiv, stat, mode=contract.Q_S5_EQUIVALENT)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception),
            deploy.RULE_MODE_DISAGREES_ACROSS_EVIDENCE,
        )


class TheDocumentsMustCiteEachOther(unittest.TestCase):
    def test_a_manifest_citing_a_different_equivalence_document_is_refused(self):
        equiv = equivalence()
        stat = static(equiv)
        man = manifest(equiv, stat, equivalence_evidence_sha256="4" * 64)
        man = deploy.seal_manifest(man)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_DIGEST_MISMATCH
        )

    def test_static_evidence_citing_a_different_equivalence_document_is_refused(self):
        equiv = equivalence()
        stat = static(equiv, equivalence_evidence_sha256="4" * 64)
        man = manifest(equiv, stat)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_DIGEST_MISMATCH
        )

    def test_a_manifest_citing_a_different_static_document_is_refused(self):
        # Without this the manifest-to-static citation is a branch no fixture
        # reaches: deleting it changed nothing until this test existed.
        equiv = equivalence()
        stat = static(equiv)
        man = deploy.seal_manifest(
            manifest(equiv, stat, static_evidence_sha256="3" * 64)
        )
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_DIGEST_MISMATCH
        )

    def test_an_edited_static_document_no_longer_matches_its_digest(self):
        equiv = equivalence()
        stat = static(equiv)
        man = manifest(equiv, stat)
        stat["boundary_image_verdict"] = "FAIL"
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_DIGEST_MISMATCH
        )

    def test_an_edited_evidence_document_no_longer_matches_its_digest(self):
        equiv = equivalence()
        stat = static(equiv)
        man = manifest(equiv, stat)
        equiv["detector_identity"] = "something_else"
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_DIGEST_MISMATCH
        )

    def test_an_incomplete_evidence_document_is_refused(self):
        equiv = equivalence()
        del equiv["detector_identity"]
        stat = static(equiv)
        man = manifest(equiv, stat)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_INCOMPLETE
        )

    def test_incomplete_static_evidence_is_refused(self):
        equiv = equivalence()
        stat = static(equiv)
        del stat["poll_count_admission"]
        man = manifest(equiv, stat)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_INCOMPLETE
        )


class TheManifestMustBeWhatItSaysItIs(unittest.TestCase):
    def test_a_missing_key_is_refused(self):
        equiv, stat, man = chain_of()
        man = dict(man)
        del man["static_evidence_sha256"]
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_INCOMPLETE
        )

    def test_an_edited_manifest_that_was_not_resealed_is_refused(self):
        equiv, stat, man = chain_of()
        man = dict(man)
        man["app_sha256"] = SCRATCH["app"]
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man, source=SCRATCH)
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_SELF_HASH)

    def test_a_foreign_schema_is_refused(self):
        equiv, stat, man = chain_of(manifest={"schema_version": 14})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_IDENTITY)

    def test_a_foreign_build_id_is_refused(self):
        equiv, stat, man = chain_of(manifest={"build_id": "34314950"})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_IDENTITY)

    def test_a_variant_that_is_not_s5_is_refused(self):
        equiv, stat, man = chain_of(manifest={"variant": "Q"})
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(equiv, stat, man)
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_IDENTITY)


class TheContextCannotBeAsserted(unittest.TestCase):
    def test_building_a_cell_context_by_hand_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            deploy.VerifiedCellContext(
                issued_by=object(),
                app_sha256=SHIPPED["app"],
                comparison_mode=contract.Q_S5_EQUIVALENT,
            )
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_CELL_CONTEXT_FORGED
        )

    def test_a_cell_without_a_boot_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(*chain_of(), boot_id="")
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_CELL_CONTEXT_FORGED
        )

    def test_a_missing_source_digest_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(*chain_of(), source={"app": SHIPPED["app"]})
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_ARTIFACT_NOT_DECLARED
        )

    def test_a_missing_readback_digest_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(*chain_of(), source=SHIPPED, readback={"app": SHIPPED["app"]})
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH
        )


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_module_declares(self):
        def missing_manifest_key():
            equiv, stat, man = chain_of()
            man = {k: v for k, v in man.items() if k != "elf_sha256"}
            return open_cell(equiv, stat, man)

        def unsealed():
            equiv, stat, man = chain_of()
            man = dict(man, app_sha256=SCRATCH["app"])
            return open_cell(equiv, stat, man)

        def wrong_elf():
            equiv = equivalence(elf=OTHER_ELF)
            stat = static(equiv, elf=SHIPPED_ELF)
            return open_cell(equiv, stat, manifest(equiv, stat, elf=SHIPPED_ELF))

        def mode_disagreement():
            equiv = equivalence()
            stat = static(equiv, mode=contract.S5_WITHIN_VARIANT_ONLY)
            return open_cell(equiv, stat, manifest(equiv, stat))

        def digest_mismatch():
            equiv = equivalence()
            stat = static(equiv, equivalence_evidence_sha256="4" * 64)
            return open_cell(equiv, stat, manifest(equiv, stat))

        def incomplete_evidence():
            equiv = equivalence()
            del equiv["detector_identity"]
            stat = static(equiv)
            return open_cell(equiv, stat, manifest(equiv, stat))

        attempts = (
            missing_manifest_key,
            unsealed,
            lambda: open_cell(*chain_of(manifest={"schema_version": 14})),
            lambda: open_cell(*chain_of(equivalence={"status": "PROBABLY_FINE"})),
            lambda: open_cell(*chain_of(equivalence={"mode": "MOSTLY_EQUIVALENT"})),
            lambda: open_cell(*chain_of(equivalence={"reference": "deadbee"})),
            wrong_elf,
            lambda: open_cell(*chain_of(), source=SCRATCH),
            lambda: open_cell(*chain_of(), source=SHIPPED, readback=SCRATCH),
            lambda: deploy.VerifiedCellContext(issued_by=object()),
            incomplete_evidence,
            digest_mismatch,
            mode_disagreement,
            lambda: open_cell(*chain_of(equivalence={"q_elf": "7" * 64})),
        )
        tripped = set()
        for attempt in attempts:
            try:
                attempt()
            except deploy.DeploymentError as exc:
                tripped.add(deploy.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(deploy, name) for name in deploy.RULES})


if __name__ == "__main__":
    unittest.main()
