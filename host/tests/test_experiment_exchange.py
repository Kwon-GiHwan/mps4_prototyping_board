"""Offline protocol ordering and failure-state coverage for V9–V13 runners."""

from __future__ import annotations

import importlib
import struct
import unittest
from unittest.mock import patch

from host.experiments import exchange
import runner_proto as proto


RUNNERS = (
    ("interval.v9", "collect_pmu_interval_v9", "parse_pmu_interval_diag_v9_payload"),
    ("interval.v10", "collect_pmu_interval_v10", "parse_pmu_interval_diag_v10_payload"),
    ("interval.v11a", "collect_pmu_interval_v11a", "parse_pmu_interval_diag_v11a_payload"),
    ("completion_poll.v12", "collect_pmu_completion_poll_v12", "parse_pmu_completion_poll_v12_payload"),
    ("completion_poll.v13", "collect_pmu_completion_poll_count_v13", "parse_pmu_completion_poll_count_v13_payload"),
)


def frame(command, sequence=1, payload=b"", flags=0):
    return proto.Frame(1, command, flags, sequence, payload)


def ack():
    return frame(proto.CMD_RUN_PMU_DIAG | 0x80)


def complete():
    return frame(proto.CMD_PMU_DIAG_COMPLETE, payload=b"sample")


def reread(payload=b"sample", sequence=2):
    return frame(proto.CMD_GET_PMU_DIAG_RESULT | 0x80, sequence, payload)


class FakeLink:
    def __init__(self, run_frames=(), get_frames=()):
        self.run_frames = list(run_frames)
        self.get_frames = list(get_frames)
        self.queue = []
        self.sequence = 0
        self.late_frames = 0
        self.sent = []
        self.timeouts = []
        self.last_pmu_diag_raw = b"previous"
        self.last_pmu_diag_reread_raw = b"previous"

    def next_sequence(self):
        self.sequence += 1
        return self.sequence

    def send_raw(self, blob):
        command, sequence = struct.unpack_from(proto.HEADER, blob)[2:5:2]
        self.sent.append((command, sequence))
        self.queue.extend(self.run_frames if command == proto.CMD_RUN_PMU_DIAG else self.get_frames)

    def read_frame(self, timeout):
        self.timeouts.append(timeout)
        if not self.queue:
            raise proto.ProtocolError("scripted timeout")
        return self.queue.pop(0)


class ExperimentExchangeTests(unittest.TestCase):
    def test_success_preserves_wire_commands_and_drain(self):
        link = FakeLink([ack(), complete()], [reread()])
        with patch.object(exchange.time, "time", return_value=100):
            self.assertEqual(exchange.run_diag_raw(link, 60), b"sample")
            self.assertEqual(exchange.read_diag_result(link, 10), b"sample")
        self.assertEqual(link.sent, [(proto.CMD_RUN_PMU_DIAG, 1), (proto.CMD_GET_PMU_DIAG_RESULT, 2)])
        self.assertEqual(link.timeouts, [5.0, 5.0, exchange.rq.DRAIN_SECONDS, 5.0])

    def test_ack_and_completion_ordering(self):
        cases = (
            ([], "no ACK for CMD_RUN_PMU_DIAG within 60.0s"),
            ([ack()], "no PMU_DIAG_COMPLETE carrying sequence 1 within 60.0s"),
            ([complete()], "PMU_DIAG_COMPLETE arrived before the ACK"),
            ([ack(), ack()], "duplicate ACK for CMD_RUN_PMU_DIAG seq=1"),
            ([ack(), complete(), ack()], "duplicate ACK for CMD_RUN_PMU_DIAG seq=1"),
            ([ack(), complete(), complete()], "duplicate PMU_DIAG_COMPLETE for seq=1"),
            ([frame(0x55)], "frame 0x55 arrived before the ACK"),
        )
        for frames, message in cases:
            with self.subTest(message=message), self.assertRaises(proto.RunSequenceError) as caught:
                exchange.run_diag_raw(FakeLink(frames), 60)
            self.assertEqual(str(caught.exception), message)

    def test_stale_and_unrelated_frames_counted_in_run_drain_and_reread(self):
        link = FakeLink(
            [frame(0x55, 90), ack(), frame(0x55), complete(), frame(0x55, 90), frame(0x55)],
            [reread(sequence=90), reread()],
        )
        self.assertEqual(exchange.run_diag_raw(link, 60), b"sample")
        self.assertEqual(exchange.read_diag_result(link, 10), b"sample")
        self.assertEqual(link.late_frames, 5)

    def test_nack_preserves_original_exception(self):
        for stage in ("run", "get"):
            with self.subTest(stage=stage):
                nack = frame(proto.NACK, payload=b"\x01\x02", flags=3)
                link = FakeLink([nack], [nack])
                action = exchange.run_diag_raw if stage == "run" else exchange.read_diag_result
                with self.assertRaises(proto.Nack) as caught:
                    action(link, 10)
                self.assertEqual(str(caught.exception), str(proto.Nack(3, 1, 2)))

    def test_get_timeout_and_wrong_response(self):
        for frames, kind, message in (
            ([], proto.RunSequenceError, "no GET_PMU_DIAG_RESULT response carrying sequence 1 within 10.0s"),
            ([frame(0x55)], proto.ProtocolError, "unexpected response 0x55 to GET_PMU_DIAG_RESULT"),
        ):
            with self.subTest(message=message), self.assertRaises(kind) as caught:
                exchange.read_diag_result(FakeLink(get_frames=frames), 10)
            self.assertEqual(str(caught.exception), message)

    def test_timeout_floor_and_expired_deadline(self):
        link = FakeLink([ack(), complete()])
        with patch.object(exchange.time, "time", return_value=100):
            exchange.run_diag_raw(link, 0.01)
        self.assertEqual(link.timeouts[:2], [0.5, 0.5])
        for action in (exchange.run_diag_raw, exchange.read_diag_result):
            link = FakeLink([ack(), complete()], [reread()])
            with patch.object(exchange.time, "time", side_effect=[100, 102]):
                with self.assertRaises(proto.RunSequenceError):
                    action(link, 1)
            self.assertEqual(link.timeouts, [])

    def test_versioned_runner_raw_state_at_each_failure_boundary(self):
        cases = (
            ("success", [ack(), complete()], [reread()], None, b"sample", b"sample"),
            ("no ack", [], [], None, None, None),
            ("bad first payload", [ack(), complete()], [], [proto.ProtocolError("parse")], None, None),
            ("get timeout", [ack(), complete()], [], None, b"sample", None),
            ("empty reread", [ack(), complete()], [reread(b"")], None, b"sample", None),
            ("different reread", [ack(), complete()], [reread(b"other")], None, b"sample", None),
            ("bad reread payload", [ack(), complete()], [reread()], ["parsed", proto.ProtocolError("parse")], b"sample", None),
        )
        for module, collector, parser in RUNNERS:
            runner = importlib.import_module("host.experiments." + module + ".runner")
            for label, run, get, parsing, expected_raw, expected_reread in cases:
                with self.subTest(version=module, case=label):
                    link = FakeLink(run, get)
                    with patch.object(runner, parser, return_value="parsed", side_effect=parsing):
                        if label == "success":
                            self.assertEqual(getattr(runner, collector)(link), ("parsed", b"sample", b"sample"))
                        else:
                            with self.assertRaises(proto.ProtocolError):
                                getattr(runner, collector)(link)
                    self.assertEqual(link.last_pmu_diag_raw, expected_raw)
                    self.assertEqual(link.last_pmu_diag_reread_raw, expected_reread)
                    self.assertEqual(len(link.sent), 1 if expected_raw is None else 2)


if __name__ == "__main__":
    unittest.main()
