"""The wire is 34 words, and the record is 24 names, and they are not the same.

One list held both and said "in wire order" about it. Nothing had consumed it
yet -- the Task 10 parser would have been the first -- and zipping 24 names onto
34 words truncates without raising, so the parser would have named the first 24
slots wrongly and returned plausible integers.

So the negatives here are aimed at that specific defect rather than at parsing
in general: the short-list path, both off-by-one word counts, a reordered host
tuple, and a provenance declaration that claims the wire carries something it
does not.
"""

import struct
import unittest
from unittest import mock

# Imported the way the V14 wire-parser test imports: the module under test
# resolves its own dependencies through the package, and reaching the same file
# by a second path would give these tests a different ProtocolError class than
# the one the parser raises.
from host import contract_pmu_completion_s5_only_control as contract
from host import runner_proto as v8
from host import runner_proto_pmu_completion_s5_only_control as v15


def appendix_words(**overrides):
    """The 34 appendix words of a healthy S5 run."""

    values = dict.fromkeys(v15.APPENDIX_FIELDS, 0)
    values["variant_id"] = 1
    values["qsize_expected"] = v15.QSIZE_EXPECTED
    values["t_submit_after_cmd"] = 1000
    values["t_primary_entry"] = 1100
    values["t_first_observation"] = 1832
    values["primary_iterations"] = 7
    values["first_status"] = v15.STATUS_CMD_END
    values["first_cmd_end_reached"] = 1
    values["mailbox_valid"] = v15.MAILBOX_VALID
    values.update(overrides)
    return [values[name] for name in v15.APPENDIX_FIELDS]


def frame(appendix=None, schema=v15.SCHEMA_VERSION, seq=1, rc=0, magic=None,
          base=None, total_words=None, header_words=v15.HEADER_WORDS):
    """A schema-15 frame, built the way the firmware builds one."""

    body = list(base if base is not None else [0x2000 + n for n in range(v15.BASE_WORDS)])
    body += list(appendix_words() if appendix is None else appendix)
    header = [
        v8.PMU_DIAG_MAGIC if magic is None else magic,
        schema,
        total_words if total_words is not None else 0,
        header_words,
        seq,
        0,
        rc,
        0,
    ]
    payload = bytearray(
        struct.pack("<%dI" % (len(header) + len(body)), *header, *body)
    )
    if total_words is None:
        struct.pack_into("<I", payload, 8, len(payload) // 4)
    crc = v8.measurement_payload_crc(bytes(payload), len(payload) // 4)
    struct.pack_into("<I", payload, 28, crc)
    return bytes(payload)


class TheWireContractIsTheFirmwares(unittest.TestCase):
    def test_the_parser_tuple_equals_the_firmware_tuple(self):
        document = v15.verify_wire_contract()
        self.assertTrue(document["tuples_equal"])
        self.assertEqual(document["appendix_words"], 34)
        self.assertEqual(document["firmware_appendix_words"], 34)

    def test_geometry_is_eight_plus_eightyfive_plus_thirtyfour(self):
        self.assertEqual(v15.HEADER_WORDS, 8)
        self.assertEqual(v15.BASE_WORDS, 85)
        self.assertEqual(v15.APPENDIX_WORDS, 34)
        self.assertEqual(v15.TOTAL_WORDS, 127)
        self.assertEqual(v15.PAYLOAD_BYTES, 508)

    def test_a_healthy_frame_parses(self):
        parsed = v15.parse_frame(frame())
        self.assertEqual(parsed.schema_version, 15)
        self.assertEqual(parsed.variant, "S5")
        self.assertEqual(parsed.primary_iterations, 7)
        self.assertEqual(parsed.mailbox_valid, v15.MAILBOX_VALID)


class TheParserKnowsOnlyTheWire(unittest.TestCase):
    def test_a_parsed_frame_carries_no_comparison_mode(self):
        # The target cannot determine whether its loop matches the frozen V14 Q
        # reference, so no honest wire word carries it. Amendment 2.
        self.assertNotIn("comparison_mode", v15.ParsedFrame.__dataclass_fields__)

    def test_a_parsed_frame_carries_no_build_id(self):
        self.assertNotIn("build_id", v15.ParsedFrame.__dataclass_fields__)

    def test_parsing_takes_bytes_and_nothing_else(self):
        # The API boundary Amendment 2 asks for: parse_frame(raw) -> ParsedFrame.
        # A parser that also accepted a manifest or a cell context would be the
        # place where wire-derived and externally-bound facts remix.
        import inspect

        parameters = list(inspect.signature(v15.parse_frame).parameters)
        self.assertEqual(parameters, ["payload"])


class N1TheShortListCannotNameTheWire(unittest.TestCase):
    def test_the_record_list_is_not_the_wire_list(self):
        self.assertNotEqual(len(contract.RECORD_FIELDS), v15.APPENDIX_WORDS)
        self.assertEqual(len(contract.RECORD_FIELDS), 24)

    def test_naming_thirtyfour_words_with_twentyfour_names_is_refused(self):
        # The exact defect: dict(zip(...)) would have returned 24 happy entries.
        words = tuple(range(v15.APPENDIX_WORDS))
        with self.assertRaises(v8.ProtocolError) as caught:
            with mock.patch.object(v15, "APPENDIX_FIELDS", tuple(contract.RECORD_FIELDS)):
                v15._appendix_from_words(words)
        self.assertIn("24", "%s" % caught.exception)

    def test_the_silent_truncation_it_replaces_is_demonstrated(self):
        # Shown rather than asserted about: this is why the length gate exists.
        quiet = dict(zip(contract.RECORD_FIELDS, range(v15.APPENDIX_WORDS)))
        self.assertEqual(len(quiet), 24)


class N2AndN3TheWordCountIsExact(unittest.TestCase):
    def test_thirtythree_appendix_words_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15._appendix_from_words(tuple(range(33)))

    def test_thirtyfive_appendix_words_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15._appendix_from_words(tuple(range(35)))

    def test_a_short_frame_is_refused_by_the_parser(self):
        with self.assertRaises(v8.ProtocolError):
            v15.parse_frame(frame()[:-4])


class N4TheHostMayNotReorderTheWire(unittest.TestCase):
    def test_swapping_two_names_fails_the_firmware_identity_gate(self):
        swapped = list(v15.APPENDIX_FIELDS)
        swapped[7], swapped[8] = swapped[8], swapped[7]
        with mock.patch.object(v15, "APPENDIX_FIELDS", tuple(swapped)):
            with self.assertRaises(v8.ProtocolError) as caught:
                v15.verify_wire_contract()
        self.assertIn("order", "%s" % caught.exception)

    def test_dropping_a_name_fails_the_firmware_identity_gate(self):
        with mock.patch.object(v15, "APPENDIX_FIELDS", v15.APPENDIX_FIELDS[:-1]):
            with mock.patch.object(v15, "APPENDIX_WORDS", 33):
                with self.assertRaises(v8.ProtocolError):
                    v15.verify_wire_contract()


class N5AndN6ProvenanceIsCheckedNotDeclared(unittest.TestCase):
    def test_the_declared_origins_hold_today(self):
        document = v15.verify_record_field_origins()
        self.assertEqual(document["record_fields"], 24)

    def test_comparison_mode_is_static_image_evidence(self):
        self.assertEqual(
            contract.RECORD_FIELD_ORIGINS["comparison_mode"],
            contract.STATIC_IMAGE_EVIDENCE,
        )

    def test_calling_a_derived_field_a_wire_field_is_refused(self):
        # N5: submit_to_s5_observed_cycles is computed here, not emitted there.
        origins = dict(contract.RECORD_FIELD_ORIGINS)
        origins["submit_to_s5_observed_cycles"] = contract.WIRE_APPENDIX
        with mock.patch.object(contract, "RECORD_FIELD_ORIGINS", origins):
            with self.assertRaises(v8.ProtocolError) as caught:
                v15.verify_record_field_origins()
        self.assertIn("submit_to_s5_observed_cycles", "%s" % caught.exception)

    def test_calling_qualification_metadata_a_wire_field_is_refused(self):
        origins = dict(contract.RECORD_FIELD_ORIGINS)
        origins["poll_count_admission"] = contract.WIRE_APPENDIX
        with mock.patch.object(contract, "RECORD_FIELD_ORIGINS", origins):
            with self.assertRaises(v8.ProtocolError):
                v15.verify_record_field_origins()

    def test_claiming_comparison_mode_comes_from_the_wire_is_refused(self):
        # N6: the declaration that would put the old, impossible contract back.
        origins = dict(contract.RECORD_FIELD_ORIGINS)
        origins["comparison_mode"] = contract.WIRE_APPENDIX
        with mock.patch.object(contract, "RECORD_FIELD_ORIGINS", origins):
            with self.assertRaises(v8.ProtocolError) as caught:
                v15.verify_record_field_origins()
        self.assertIn("comparison_mode", "%s" % caught.exception)

    def test_an_unmapped_record_field_is_refused(self):
        origins = dict(contract.RECORD_FIELD_ORIGINS)
        del origins["variant_id"]
        with mock.patch.object(contract, "RECORD_FIELD_ORIGINS", origins):
            with self.assertRaises(v8.ProtocolError):
                v15.verify_record_field_origins()

    def test_an_origin_outside_the_enum_is_refused(self):
        origins = dict(contract.RECORD_FIELD_ORIGINS)
        origins["variant_id"] = "PROBABLY_THE_WIRE"
        with mock.patch.object(contract, "RECORD_FIELD_ORIGINS", origins):
            with self.assertRaises(v8.ProtocolError):
                v15.verify_record_field_origins()


class TheFrameIsRefusedWhenItIsNotOurs(unittest.TestCase):
    def test_a_schema_fourteen_frame_is_refused(self):
        with self.assertRaises(v8.ProtocolError) as caught:
            v15.parse_frame(frame(schema=14))
        self.assertIn("schema", "%s" % caught.exception)

    def test_a_frame_without_the_mailbox_magic_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15.parse_frame(frame(appendix=appendix_words(mailbox_valid=0)))

    def test_a_variant_that_is_not_s5_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15.parse_frame(frame(appendix=appendix_words(variant_id=2)))

    def test_a_foreign_workload_size_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15.parse_frame(frame(appendix=appendix_words(qsize_expected=0x220)))

    def test_a_bad_magic_is_refused(self):
        with self.assertRaises(v8.ProtocolError):
            v15.parse_frame(frame(magic=0xDEADBEEF))


if __name__ == "__main__":
    unittest.main()
