"""A run is licensed by the image its evidence was computed over, or not at all.

comparison_mode cannot come from the frame, so it comes from static image
evidence, and the question this file settles is whether that evidence is
actually attached to the run or merely filed next to it.

The three attacks are the ones the review named, and the first is not
hypothetical: Amendment 1's no-count scratch build is schema 15, variant S5, and
fails equivalence. Its frames parse exactly like the shipped build's. Before the
deployment gate the only thing keeping it out of an equivalence-mode analysis
was that nobody had flashed it.

Tampered manifests are re-sealed before use. An unsealed forgery trips the
self-hash rule and never reaches the rule under test, which would leave the
interesting branch unreached and deletable.
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


def manifest(elf=SHIPPED_ELF, artifacts=None, mode=contract.Q_S5_EQUIVALENT,
             status=chain.EQUIVALENCE_PASS, evidence_elf=None,
             reference=chain.Q_REFERENCE_ANCHOR, **overrides):
    artifacts = artifacts or SHIPPED
    document = {
        "canonical_json": deploy.CANONICAL_JSON,
        "schema_version": contract.SCHEMA_VERSION,
        "build_id": "%08x" % contract.BUILD_ID,
        "variant": "S5",
        "comparison_mode": mode,
        "elf_sha256": elf,
        "app_sha256": artifacts["app"],
        "vectors_sha256": artifacts["vectors"],
        "ddr_sha256": artifacts["ddr"],
        "generated_source_sha256": {"runner": "0" * 64},
        "static_evidence_sha256": "5" * 64,
        "equivalence_evidence_sha256": "6" * 64,
        "equivalence_status": status,
        "equivalence_elf_sha256": elf if evidence_elf is None else evidence_elf,
        "v14_q_reference_identity": reference,
    }
    document.update(overrides)
    return deploy.seal_manifest(document)


def open_cell(document, source=None, readback=None, boot_id="b1"):
    source = SHIPPED if source is None else source
    readback = source if readback is None else readback
    return deploy.open_verified_cell(document, source, readback, boot_id=boot_id)


class TheHappyPathIssuesAContext(unittest.TestCase):
    def test_a_qualified_image_opens_a_cell(self):
        context = open_cell(manifest())
        self.assertEqual(context.comparison_mode, contract.Q_S5_EQUIVALENT)
        self.assertEqual(context.app_sha256, SHIPPED["app"])
        self.assertEqual(context.elf_sha256, SHIPPED_ELF)
        self.assertEqual(context.boot_id, "b1")
        self.assertEqual(len(context.manifest_sha256), 64)

    def test_the_fallback_opens_a_cell_in_the_fallback_mode(self):
        document = manifest(
            mode=contract.S5_WITHIN_VARIANT_ONLY, status=chain.EQUIVALENCE_FALLBACK
        )
        self.assertEqual(open_cell(document).comparison_mode, contract.S5_WITHIN_VARIANT_ONLY)


class NegativeATheScratchBuildCannotBorrowTheShippedEvidence(unittest.TestCase):
    def test_deploying_the_no_count_scratch_app_under_the_shipped_manifest_is_refused(self):
        # Schema 15, variant S5, equivalence FAIL. Indistinguishable at the frame
        # level from the shipped build; caught here or nowhere.
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(), source=SCRATCH)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_ARTIFACT_NOT_DECLARED
        )

    def test_the_scratch_app_landing_on_the_board_is_refused_at_readback(self):
        # The manifest and the source agree; what actually reached the device
        # does not.
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(), source=SHIPPED, readback=SCRATCH)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH
        )

    def test_a_vectors_or_ddr_swap_is_refused_too(self):
        # The board loads three artifacts. Binding only the APP would leave the
        # other two free to differ from the qualified set.
        for name in ("vectors", "ddr"):
            swapped = dict(SHIPPED)
            swapped[name] = "f" * 64
            with self.assertRaises(deploy.DeploymentError) as caught:
                open_cell(manifest(), source=SHIPPED, readback=swapped)
            self.assertEqual(
                deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH, name
            )


class NegativeBAForgedModeDoesNotSurviveItsOwnEvidence(unittest.TestCase):
    def test_claiming_equivalence_over_fallback_evidence_is_refused(self):
        # The scratch build's own manifest, re-sealed, with only the mode moved
        # to the one it did not earn.
        document = manifest(
            elf=SCRATCH_ELF,
            artifacts=SCRATCH,
            mode=contract.Q_S5_EQUIVALENT,
            status=chain.EQUIVALENCE_FALLBACK,
        )
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document, source=SCRATCH)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_the_forgery_is_properly_sealed_so_the_self_hash_is_not_what_caught_it(self):
        document = manifest(
            elf=SCRATCH_ELF, artifacts=SCRATCH,
            mode=contract.Q_S5_EQUIVALENT, status=chain.EQUIVALENCE_FALLBACK,
        )
        self.assertEqual(
            deploy.manifest_self_hash(document), document[deploy.MANIFEST_SELF_HASH_KEY]
        )

    def test_an_equivalence_status_that_licenses_nothing_is_refused(self):
        document = manifest(status="PROBABLY_FINE")
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EQUIVALENCE_EVIDENCE_UNUSABLE
        )

    def test_a_pass_with_no_evidence_digest_is_refused(self):
        document = manifest(equivalence_evidence_sha256="")
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EQUIVALENCE_EVIDENCE_UNUSABLE
        )

    def test_an_unknown_comparison_mode_is_refused(self):
        document = manifest(mode="MOSTLY_EQUIVALENT")
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MODE_CONTRADICTS_EVIDENCE
        )


class NegativeCTheEvidenceMustDescribeTheImageThatRuns(unittest.TestCase):
    def test_equivalence_evidence_from_another_elf_is_refused(self):
        # The dangerous shape: everything present, everything well formed, and
        # the comparison was made over a different binary.
        document = manifest(elf=SHIPPED_ELF, evidence_elf=OTHER_ELF)
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_EVIDENCE_ELF_UNBOUND
        )

    def test_a_structurally_similar_q_is_not_the_qualified_q(self):
        document = manifest(reference="deadbee")
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_REFERENCE_IDENTITY
        )


class TheManifestMustBeWhatItSaysItIs(unittest.TestCase):
    def test_a_missing_key_is_refused(self):
        document = dict(manifest())
        del document["static_evidence_sha256"]
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document)
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_INCOMPLETE
        )

    def test_an_edited_manifest_that_was_not_resealed_is_refused(self):
        document = dict(manifest())
        document["app_sha256"] = SCRATCH["app"]
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(document, source=SCRATCH)
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_SELF_HASH)

    def test_a_foreign_schema_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(schema_version=14))
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_IDENTITY)

    def test_a_foreign_build_id_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(build_id="34314950"))
        self.assertEqual(deploy.refusal_rule(caught.exception), deploy.RULE_MANIFEST_IDENTITY)

    def test_a_variant_that_is_not_s5_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(variant="Q"))
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
            open_cell(manifest(), boot_id="")
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_CELL_CONTEXT_FORGED
        )

    def test_a_missing_source_digest_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(), source={"app": SHIPPED["app"]})
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_ARTIFACT_NOT_DECLARED
        )

    def test_a_missing_readback_digest_is_refused(self):
        with self.assertRaises(deploy.DeploymentError) as caught:
            open_cell(manifest(), source=SHIPPED, readback={"app": SHIPPED["app"]})
        self.assertEqual(
            deploy.refusal_rule(caught.exception), deploy.RULE_READBACK_MISMATCH
        )


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_module_declares(self):
        attempts = (
            lambda: open_cell({k: v for k, v in manifest().items() if k != "elf_sha256"}),
            lambda: open_cell(dict(manifest(), app_sha256=SCRATCH["app"])),
            lambda: open_cell(manifest(schema_version=14)),
            lambda: open_cell(manifest(status="PROBABLY_FINE")),
            lambda: open_cell(manifest(mode="MOSTLY_EQUIVALENT")),
            lambda: open_cell(manifest(reference="deadbee")),
            lambda: open_cell(manifest(evidence_elf=OTHER_ELF)),
            lambda: open_cell(manifest(), source=SCRATCH),
            lambda: open_cell(manifest(), source=SHIPPED, readback=SCRATCH),
            lambda: deploy.VerifiedCellContext(issued_by=object()),
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
