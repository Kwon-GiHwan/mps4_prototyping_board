"""Schema-14 frame contract, frozen here independently of the parser.

The order below is written out rather than imported. A test that asks the
parser for the field order and then checks the parser against it agrees with
itself no matter what the firmware sends, which is the one thing this file
exists to prevent.
"""

import struct
import unittest

from host import runner_proto as v8
from host import runner_proto_pmu_completion_visibility_v14 as v14


# The wire order of the 34-word appendix, frozen. Position is the contract.
APPENDIX_ORDER = (
    "variant_id",
    "qsize_expected",
    "pre_program_status",
    "pre_submit_status",
    "t_submit_after_cmd",
    "t_primary_entry",
    "t_first_observation",
    "primary_result",
    "primary_iterations",
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
    "convergence_result",
    "convergence_iterations",
    "convergence_final_qread",
    "convergence_final_status",
    "convergence_timeout",
    "failure_phase",
    "failure_reason",
    "failure_qread",
    "failure_status",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
    "mailbox_valid",
)

HEADER_WORDS = 8
BASE_WORDS = 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS          # 119
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS           # 127
PAYLOAD_BYTES = TOTAL_WORDS * 4                   # 508
SCHEMA_VERSION = 14
BUILD_ID = 0x34314950
MAILBOX_VALID = 0x5631344D
VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}


def canonical_appendix(variant):
    """A well-formed appendix: distinct values, so a swap cannot go unnoticed."""

    values = {name: 0x1000 + index for index, name in enumerate(APPENDIX_ORDER)}
    values["variant_id"] = VARIANTS[variant]
    values["qsize_expected"] = 0x110
    values["primary_result"] = 1                  # completed
    values["convergence_result"] = 1
    values["convergence_timeout"] = 0
    values["failure_phase"] = 0
    values["failure_reason"] = 0
    values["first_q_done"] = 1
    values["first_cmd_end_reached"] = 1
    values["first_irq_raised"] = 1
    values["first_state"] = 0
    values["mailbox_valid"] = MAILBOX_VALID
    return values


def build_frame(variant="Q", appendix=None, seq=7, rc=0, total_words=TOTAL_WORDS,
                schema=SCHEMA_VERSION, header_words=HEADER_WORDS, magic=None,
                body_words=None, fix_crc=True, fix_length=True):
    """A schema-14 frame, built the way the firmware builds one."""

    appendix = dict(canonical_appendix(variant) if appendix is None else appendix)
    if body_words is None:
        body_words = [0x2000 + index for index in range(BASE_WORDS)]
        body_words += [appendix[name] for name in APPENDIX_ORDER]
    header = [
        v8.PMU_DIAG_MAGIC if magic is None else magic,
        schema,
        total_words,
        header_words,
        seq,
        0,
        rc,
        0,
    ]
    payload = bytearray(struct.pack("<%dI" % (len(header) + len(body_words)),
                                    *header, *body_words))
    if fix_length:
        struct.pack_into("<I", payload, 8, len(payload) // 4)
    if fix_crc:
        crc = v8.measurement_payload_crc(bytes(payload), len(payload) // 4)
        struct.pack_into("<I", payload, 28, crc)
    return bytes(payload)


class ParserRedTests(unittest.TestCase):
    """Everything the wire contract fixes, asserted against the parser."""

    def test_frame_geometry_is_the_contract(self):
        self.assertEqual(v14.HEADER_WORDS, HEADER_WORDS)
        self.assertEqual(v14.BASE_WORDS, BASE_WORDS)
        self.assertEqual(v14.APPENDIX_WORDS, APPENDIX_WORDS)
        self.assertEqual(v14.BODY_WORDS, BODY_WORDS)
        self.assertEqual(v14.TOTAL_WORDS, TOTAL_WORDS)
        self.assertEqual(v14.PAYLOAD_BYTES, PAYLOAD_BYTES)
        self.assertEqual(v14.SCHEMA_VERSION, SCHEMA_VERSION)
        self.assertEqual(v14.BUILD_ID, BUILD_ID)
        self.assertEqual(v14.MAILBOX_VALID, MAILBOX_VALID)

    def test_appendix_order_is_the_frozen_one(self):
        self.assertEqual(tuple(v14.APPENDIX_FIELDS), APPENDIX_ORDER)

    def test_the_magic_sits_at_the_last_body_word(self):
        # Body word 118, absolute frame word 126: the position the firmware
        # publishes last and the host checks first.
        self.assertEqual(APPENDIX_ORDER.index("mailbox_valid"), APPENDIX_WORDS - 1)
        self.assertEqual(BASE_WORDS + APPENDIX_WORDS - 1, 118)
        self.assertEqual(HEADER_WORDS + BASE_WORDS + APPENDIX_WORDS - 1, 126)

    def test_canonical_frames_parse_for_every_variant(self):
        for variant, identifier in VARIANTS.items():
            result = v14.parse_payload(build_frame(variant))
            self.assertEqual(result.variant_id, identifier)
            self.assertEqual(result.qsize_expected, 0x110)
            self.assertEqual(result.mailbox_valid, MAILBOX_VALID)
            self.assertEqual(result.schema_version, SCHEMA_VERSION)

    def test_every_appendix_field_lands_where_the_contract_puts_it(self):
        appendix = canonical_appendix("Q")
        result = v14.parse_payload(build_frame("Q", appendix))
        for name in APPENDIX_ORDER:
            self.assertEqual(getattr(result, name), appendix[name], name)

    def test_a_swap_of_any_two_appendix_words_is_visible(self):
        # Distinct canonical values are what make this a test rather than a
        # coincidence: swapping two equal words would prove nothing.
        for left in range(APPENDIX_WORDS - 1):
            appendix = canonical_appendix("Q")
            a, b = APPENDIX_ORDER[left], APPENDIX_ORDER[left + 1]
            if appendix[a] == appendix[b]:
                continue
            appendix[a], appendix[b] = appendix[b], appendix[a]
            try:
                result = v14.parse_payload(build_frame("Q", appendix))
            except v8.ProtocolError:
                # Refusing the swapped frame is the strongest way of noticing
                # it, and the contract fields do exactly that.
                continue
            self.assertNotEqual(
                (getattr(result, a), getattr(result, b)),
                (canonical_appendix("Q")[a], canonical_appendix("Q")[b]),
                "%s/%s swap was invisible" % (a, b),
            )

    def test_a_truncated_frame_is_refused(self):
        frame = build_frame()
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(frame[:-4])

    def test_an_extended_frame_is_refused(self):
        frame = build_frame()
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(frame + b"\x00\x00\x00\x00")

    def test_a_declared_length_that_disagrees_with_the_frame_is_refused(self):
        frame = bytearray(build_frame())
        struct.pack_into("<I", frame, 8, TOTAL_WORDS + 1)
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(bytes(frame))

    def test_a_short_body_is_refused(self):
        frame = build_frame(body_words=[0] * (BODY_WORDS - 1))
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(frame)

    def test_a_wrong_crc_is_refused(self):
        frame = bytearray(build_frame())
        struct.pack_into("<I", frame, 28, 0xDEADBEEF)
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(bytes(frame))

    def test_a_wrong_magic_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(build_frame(magic=0xDEADBEEF))

    def test_an_older_schema_is_refused_rather_than_coerced(self):
        for schema in (7, 8, 12, 13):
            with self.assertRaises(v8.ProtocolError):
                v14.parse_payload(build_frame(schema=schema))

    def test_a_wrong_header_word_count_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(build_frame(header_words=9))

    def test_a_missing_mailbox_magic_is_refused(self):
        appendix = canonical_appendix("Q")
        appendix["mailbox_valid"] = 0
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(build_frame("Q", appendix))

    def test_a_variant_id_outside_the_contract_is_refused(self):
        appendix = canonical_appendix("Q")
        appendix["variant_id"] = 4
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(build_frame("Q", appendix))

    def test_a_qsize_that_is_not_the_frozen_workload_is_refused(self):
        appendix = canonical_appendix("Q")
        appendix["qsize_expected"] = 0x111
        with self.assertRaises(v8.ProtocolError):
            v14.parse_payload(build_frame("Q", appendix))

    def test_the_parser_does_not_import_the_test_order(self):
        # The parser owning its own table is what makes the comparison above a
        # comparison. This catches the accident of importing it back.
        import inspect

        source = inspect.getsource(v14)
        self.assertNotIn("test_pmu_completion_visibility_v14", source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


def failure_appendix(variant, phase, reason, *, primary=0, convergence=0,
                     keep_first=False, keep_convergence=False, qread=None, status=0x2000):
    """An appendix for one failure mode, published the way the firmware does."""

    appendix = canonical_appendix(variant)
    appendix["primary_result"] = primary
    appendix["convergence_result"] = convergence
    appendix["convergence_timeout"] = 1 if convergence == 2 else 0
    appendix["primary_iterations"] = 41 if primary == 1 else 0
    appendix["convergence_iterations"] = 7 if convergence == 1 else 0
    appendix["failure_phase"] = phase
    appendix["failure_reason"] = reason
    appendix["failure_qread"] = v14.U32_INVALID if qread is None else qread
    appendix["failure_status"] = status
    if not keep_first:
        for name in ("first_qread", "first_status", "first_q_done",
                     "first_cmd_end_reached", "first_irq_raised", "first_state"):
            appendix[name] = v14.U32_INVALID
    if not keep_convergence:
        for name in ("convergence_final_qread", "convergence_final_status"):
            appendix[name] = v14.U32_INVALID
    return appendix


class ClassifierRedTests(unittest.TestCase):
    """The publication matrix, one fixture per way a run can end."""

    def classify(self, variant="Q", appendix=None):
        return v14.classify_payload(v14.parse_payload(build_frame(variant, appendix)))

    # --- success -----------------------------------------------------------
    def test_success_publishes_every_phase_and_no_failure_tuple(self):
        for variant in VARIANTS:
            doc = self.classify(variant)
            self.assertTrue(doc["sample_valid"], variant)
            for phase in ("t_submit_after_cmd", "t_primary_entry", "t_first_observation",
                          "first_tuple", "convergence"):
                self.assertTrue(doc["phases"][phase], "%s/%s" % (variant, phase))
            self.assertFalse(doc["phases"]["failure_tuple"], variant)

    def test_q_never_carries_a_category_and_dual_variants_do(self):
        self.assertIsNone(self.classify("Q")["category"])
        for variant in ("QS", "SQ"):
            self.assertIn(self.classify(variant)["category"],
                          (v14.CATEGORY_Q_FIRST, v14.CATEGORY_S5_FIRST,
                           v14.CATEGORY_SAME_ITERATION))

    def test_the_category_follows_the_first_tuple(self):
        cases = ((1, 0, v14.CATEGORY_Q_FIRST), (0, 1, v14.CATEGORY_S5_FIRST),
                 (1, 1, v14.CATEGORY_SAME_ITERATION))
        for q_done, cmd_end, expected in cases:
            appendix = canonical_appendix("QS")
            appendix["first_q_done"] = q_done
            appendix["first_cmd_end_reached"] = cmd_end
            self.assertEqual(self.classify("QS", appendix)["category"], expected)

    def test_q_only_first_tuple_has_no_status_derived_fields(self):
        fields = self.classify("Q")["first_tuple_fields"]
        self.assertTrue(fields["first_qread"])
        for name in ("first_status", "first_cmd_end_reached", "first_irq_raised", "first_state"):
            self.assertFalse(fields[name], name)
        self.assertTrue(self.classify("QS")["first_tuple_fields"]["first_status"])

    # --- pre-run failures ---------------------------------------------------
    def test_pre_run_failure_invalidates_timing_and_both_tuples(self):
        for phase, reason in ((1, 1), (1, 2), (1, 3), (2, 4), (2, 5), (2, 6)):
            doc = self.classify("Q", failure_appendix("Q", phase, reason))
            self.assertFalse(doc["sample_valid"], (phase, reason))
            for name in ("t_submit_after_cmd", "t_primary_entry", "t_first_observation",
                         "first_tuple", "convergence"):
                self.assertFalse(doc["phases"][name], (phase, reason, name))
            self.assertTrue(doc["phases"]["failure_tuple"], (phase, reason))

    # --- primary failures ---------------------------------------------------
    def test_primary_failure_keeps_submit_timing_and_drops_the_rest(self):
        for primary, reason in ((2, 7), (3, 2), (4, 3)):
            doc = self.classify("Q", failure_appendix("Q", 3, reason, primary=primary))
            self.assertFalse(doc["sample_valid"], primary)
            self.assertTrue(doc["phases"]["t_submit_after_cmd"], primary)
            self.assertTrue(doc["phases"]["t_primary_entry"], primary)
            self.assertFalse(doc["phases"]["t_first_observation"], primary)
            self.assertFalse(doc["phases"]["first_tuple"], primary)
            self.assertFalse(doc["phases"]["convergence"], primary)

    # --- convergence failures ----------------------------------------------
    def test_convergence_failure_keeps_the_first_tuple(self):
        for convergence, reason in ((2, 8), (3, 2), (4, 3)):
            appendix = failure_appendix("QS", 4, reason, primary=1,
                                        convergence=convergence, keep_first=True)
            doc = self.classify("QS", appendix)
            self.assertFalse(doc["sample_valid"], convergence)
            self.assertTrue(doc["phases"]["first_tuple"], convergence)
            self.assertTrue(doc["phases"]["t_first_observation"], convergence)
            self.assertFalse(doc["phases"]["convergence"], convergence)
            self.assertTrue(doc["phases"]["failure_tuple"], convergence)
            self.assertIsNone(doc["category"], convergence)

    def test_convergence_failure_retains_the_successful_primary_count(self):
        appendix = failure_appendix("QS", 4, 8, primary=1, convergence=2, keep_first=True)
        doc = self.classify("QS", appendix)
        self.assertEqual(doc["problems"], [])
        self.assertEqual(doc["primary_result"], v14.PRIMARY_OBSERVED)

    # --- cleanup ------------------------------------------------------------
    def test_cleanup_invariant_keeps_both_tuples_and_still_invalidates_the_sample(self):
        appendix = failure_appendix("QS", 5, 9, primary=1, convergence=1,
                                    keep_first=True, keep_convergence=True)
        doc = self.classify("QS", appendix)
        self.assertFalse(doc["sample_valid"])
        self.assertTrue(doc["phases"]["first_tuple"])
        self.assertTrue(doc["phases"]["convergence"])
        self.assertTrue(doc["phases"]["cleanup_readbacks"])
        self.assertIsNone(doc["category"])

    # --- iteration counts ---------------------------------------------------
    def test_iteration_counts_are_bound_to_their_own_stage(self):
        appendix = canonical_appendix("Q")
        appendix["primary_iterations"] = 0
        self.assertTrue(self.classify("Q", appendix)["problems"])
        appendix = canonical_appendix("Q")
        appendix["primary_iterations"] = 10001
        self.assertTrue(self.classify("Q", appendix)["problems"])
        appendix = failure_appendix("Q", 3, 7, primary=2)
        appendix["primary_iterations"] = 5
        self.assertTrue(self.classify("Q", appendix)["problems"])

    def test_convergence_timeout_flag_tracks_the_convergence_result(self):
        appendix = failure_appendix("QS", 4, 8, primary=1, convergence=2, keep_first=True)
        appendix["convergence_timeout"] = 0
        self.assertTrue(self.classify("QS", appendix)["problems"])
        appendix = canonical_appendix("QS")
        appendix["convergence_timeout"] = 1
        self.assertTrue(self.classify("QS", appendix)["problems"])

    # --- disagreements ------------------------------------------------------
    def test_a_stage_result_that_disagrees_with_the_failure_phase_is_a_problem(self):
        appendix = failure_appendix("Q", 0, 0, primary=2)
        self.assertTrue(self.classify("Q", appendix)["problems"])
        appendix = canonical_appendix("Q")
        appendix["failure_reason"] = 7
        self.assertTrue(self.classify("Q", appendix)["problems"])

    # --- what a valid diagnostic must always say ---------------------------
    def test_every_document_carries_the_three_truths(self):
        for appendix in (None, failure_appendix("Q", 3, 7, primary=2)):
            doc = self.classify("Q", appendix)
            self.assertTrue(doc["perturbed_by_convergence_tail"])
            self.assertTrue(doc["not_comparable_to_v13"])
            self.assertTrue(doc["not_performance_metric"])
            self.assertFalse(doc["may_publish_pmu_metric"])

    def test_an_invalid_sample_publishes_no_distribution(self):
        doc = self.classify("QS", failure_appendix("QS", 3, 7, primary=2))
        self.assertFalse(doc["may_publish_distribution"])
        self.assertIsNone(doc["category"])
        self.assertTrue(self.classify("QS")["may_publish_distribution"])


import hashlib
import json
import os
import tempfile


def build_manifest(root, variant="Q", artifacts=None):
    """A manifest over real files, self-hashed the way the build self-hashes."""

    artifacts = {"APP.BIN": b"application", "DDR.BIN": b"ddr"} if artifacts is None else artifacts
    table = {}
    for name, payload in artifacts.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(payload)
        table[name] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    document = {
        "variant": variant,
        "schema_version": 14,
        "build_id": "0x34314950",
        "canonical_json": "v14-canonical-json-v1",
        "frozen_input_sha256": {"runner": "0" * 64},
        "declared_artifacts": table,
    }
    document["manifest_self_hash"] = v14.manifest_self_hash(document)
    return document


class ManifestRedTests(unittest.TestCase):
    """The manifest is recomputed, never read."""

    def test_a_real_manifest_verifies(self):
        with tempfile.TemporaryDirectory() as root:
            report = v14.verify_manifest(build_manifest(root), root)
            self.assertEqual(report["artifacts_verified"], 2)
            self.assertEqual(report["undeclared_files_present"], [])

    def test_the_self_hash_covers_every_other_key(self):
        with tempfile.TemporaryDirectory() as root:
            for key, value in (("variant", "QS"), ("schema_version", 14), ("build_id", "0x34314950")):
                document = build_manifest(root)
                document[key] = value if key != "schema_version" else 14
            document = build_manifest(root)
            document["variant"] = "QS"          # self-hash now stale
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_a_substituted_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            with open(os.path.join(root, "APP.BIN"), "wb") as handle:
                handle.write(b"a different application")
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_a_missing_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            os.unlink(os.path.join(root, "DDR.BIN"))
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_a_declared_size_that_disagrees_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            document["declared_artifacts"]["APP.BIN"]["bytes"] = 1
            document["manifest_self_hash"] = v14.manifest_self_hash(document)
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_an_undeclared_file_is_reported_when_containment_is_waived(self):
        # This test used to assert that reporting was enough. It is not: the
        # contract rejects an extra artifact, and only a caller that says so
        # explicitly gets the weaker answer.
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            with open(os.path.join(root, "SECOND.BIN"), "wb") as handle:
                handle.write(b"another image")
            report = v14.verify_manifest(document, root, allow_undeclared=True)
            self.assertEqual(report["undeclared_files_present"], ["SECOND.BIN"])
            self.assertIn("not required", report["containment"])

    def test_an_artifact_name_that_escapes_the_build_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            document["declared_artifacts"]["../escape"] = {"sha256": "0" * 64, "bytes": 0}
            document["manifest_self_hash"] = v14.manifest_self_hash(document)
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_wrong_variant_schema_build_or_canonical_form_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            for key, value in (
                ("variant", "ZZ"),
                ("schema_version", 13),
                ("build_id", "0x33314950"),
                ("canonical_json", "v13-canonical-json-v1"),
            ):
                document = build_manifest(root)
                document[key] = value
                document["manifest_self_hash"] = v14.manifest_self_hash(document)
                with self.assertRaises(v8.ProtocolError):
                    v14.verify_manifest(document, root)

    def test_a_manifest_with_no_self_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            del document["manifest_self_hash"]
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_canonical_bytes_are_stable_and_end_in_one_newline(self):
        payload = v14.canonical_json_bytes({"b": 1, "a": [2, 3]})
        self.assertEqual(payload, b'{"a":[2,3],"b":1}\n')
        self.assertEqual(payload, v14.canonical_json_bytes({"a": [2, 3], "b": 1}))


class ManifestContainmentTests(unittest.TestCase):
    """What MANIFEST PASS has to mean about the tree it was run against."""

    def test_a_symlinked_artifact_pointing_outside_the_build_is_refused(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            payload = b"outside-the-build"
            external = os.path.join(elsewhere, "real.bin")
            with open(external, "wb") as handle:
                handle.write(payload)
            document = {
                "variant": "Q",
                "schema_version": 14,
                "build_id": "0x34314950",
                "canonical_json": "v14-canonical-json-v1",
                "frozen_input_sha256": {"runner": "0" * 64},
                "declared_artifacts": {
                    "APP.BIN": {
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                    }
                },
            }
            document["manifest_self_hash"] = v14.manifest_self_hash(document)
            os.symlink(external, os.path.join(root, "APP.BIN"))
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_an_undeclared_file_beside_the_declared_ones_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            with open(os.path.join(root, "SECOND.BIN"), "wb") as handle:
                handle.write(b"another image")
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_a_stored_bundle_hash_that_disagrees_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            document["artifact_bundle_sha256"] = "f" * 64
            document["manifest_self_hash"] = v14.manifest_self_hash(document)
            with self.assertRaises(v8.ProtocolError):
                v14.verify_manifest(document, root)

    def test_a_stored_bundle_hash_that_agrees_is_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root)
            report = v14.verify_manifest(document, root)
            document["artifact_bundle_sha256"] = report["artifact_bundle_sha256"]
            document["manifest_self_hash"] = v14.manifest_self_hash(document)
            again = v14.verify_manifest(document, root)
            self.assertEqual(again["artifact_bundle_sha256"], report["artifact_bundle_sha256"])

    def test_a_declared_artifact_may_still_live_in_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as root:
            document = build_manifest(root, artifacts={"generated/u85.c": b"source"})
            self.assertEqual(v14.verify_manifest(document, root)["artifacts_verified"], 1)
