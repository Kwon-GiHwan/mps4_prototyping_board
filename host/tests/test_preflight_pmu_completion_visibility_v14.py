"""The board preflight contract, attacked at its boundaries and its ordering.

A gate with one positive and one negative fixture is a gate that has been shown
to work on the two cases its author thought of. What matters here is the case
nobody thought of: the PING that answered three times but once from the wrong
state, the UART port with no visible holder whose root ownership could not be
established, the deployment authorised because someone called the authorising
method without running the gates.

So each gate is pushed at its threshold, and the state machine is pushed at its
order. Nothing in this file touches a board: every reading is synthetic, and
that is the point -- the contract is qualified as a contract before it is ever
pointed at hardware.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import preflight_pmu_completion_visibility_v14 as preflight  # noqa: E402


PASS = preflight.PASS
FAIL = preflight.FAIL
UNPROVEN = preflight.UNPROVEN


def good_storage(**overrides):
    readings = {
        "mount_count": 0,
        "block_device_write_holders": 0,
        "uart_holders": {
            port: {"holders": 0, "root_inclusive": True} for port in preflight.FTDI_PORTS
        },
        "usb_off_confirmed": True,
        "block_device_present": False,
    }
    readings.update(overrides)
    return readings


def good_baseline(**overrides):
    readings = {
        "ddr_selftest_passed": True,
        "cpuwait_cleared": True,
        "pings": [{"answered": True, "state": 1} for _ in range(3)],
        "protocol_errors": {name: 0 for name in preflight.PROTOCOL_ERROR_COUNTERS},
    }
    readings.update(overrides)
    return readings


QUALIFIED = {
    "APP.BIN": "a" * 64,
    "VECTORS.BIN": "b" * 64,
    "DDR.BIN": "c" * 64,
}


def good_candidate(**overrides):
    readings = {
        "candidate_digests": dict(QUALIFIED),
        "qualified_digests": dict(QUALIFIED),
        "candidate_variant": "Q",
        "manifest_variant": "Q",
        "manifest_verified": True,
        "real_elf_pass": True,
        "read_order_equivalent": True,
        "common_tail_shared": True,
    }
    readings.update(overrides)
    return readings


class InheritedThresholds(unittest.TestCase):
    """The thresholds V11-A, V12 and V13 ran against a board. V14 may not move them."""

    def verdict(self, gate_id, readings):
        gate = next(g for g in preflight.GATES if g["id"] == gate_id)
        return gate["evaluate"](readings)[0]

    # -- PING ----------------------------------------------------------------

    def test_three_pings_from_idle_pass(self):
        self.assertEqual(self.verdict("PING_LIVENESS", good_baseline()), PASS)

    def test_two_of_three_pings_fail(self):
        readings = good_baseline(pings=[{"answered": True, "state": 1} for _ in range(2)])
        self.assertEqual(self.verdict("PING_LIVENESS", readings), FAIL)

    def test_three_pings_with_one_unanswered_fail(self):
        pings = [{"answered": True, "state": 1} for _ in range(3)]
        pings[1] = {"answered": False, "state": 1}
        self.assertEqual(self.verdict("PING_LIVENESS", good_baseline(pings=pings)), FAIL)

    def test_three_pings_with_one_outside_idle_fail(self):
        # The case a count alone would miss: three answers, one from the wrong state.
        pings = [{"answered": True, "state": 1} for _ in range(3)]
        pings[2] = {"answered": True, "state": 2}
        self.assertEqual(self.verdict("PING_LIVENESS", good_baseline(pings=pings)), FAIL)

    def test_a_ping_without_a_state_is_unproven(self):
        pings = [{"answered": True, "state": 1} for _ in range(3)]
        pings[0] = {"answered": True}
        self.assertEqual(self.verdict("PING_LIVENESS", good_baseline(pings=pings)), UNPROVEN)

    # -- protocol counters ---------------------------------------------------

    def test_seven_zero_counters_pass(self):
        self.assertEqual(self.verdict("PROTOCOL_ERRORS", good_baseline()), PASS)

    def test_any_incremented_counter_fails(self):
        for name in preflight.PROTOCOL_ERROR_COUNTERS:
            counters = {each: 0 for each in preflight.PROTOCOL_ERROR_COUNTERS}
            counters[name] = 1
            self.assertEqual(
                self.verdict("PROTOCOL_ERRORS", good_baseline(protocol_errors=counters)),
                FAIL,
                name,
            )

    def test_a_missing_counter_is_unproven_not_pass(self):
        # Six zeroes say nothing about the seventh.
        counters = {each: 0 for each in preflight.PROTOCOL_ERROR_COUNTERS}
        del counters["parser_resync"]
        self.assertEqual(
            self.verdict("PROTOCOL_ERRORS", good_baseline(protocol_errors=counters)), UNPROVEN
        )

    # -- DDR and CPUWAIT -----------------------------------------------------

    def test_ddr_and_cpuwait_pass_together(self):
        self.assertEqual(self.verdict("DDR_SELFTEST", good_baseline()), PASS)
        self.assertEqual(self.verdict("CPUWAIT", good_baseline()), PASS)

    def test_failed_ddr_selftest_fails(self):
        self.assertEqual(
            self.verdict("DDR_SELFTEST", good_baseline(ddr_selftest_passed=False)), FAIL
        )

    def test_uncleared_cpuwait_fails_even_with_ddr_pass(self):
        readings = good_baseline(cpuwait_cleared=False)
        self.assertEqual(self.verdict("DDR_SELFTEST", readings), PASS)
        self.assertEqual(self.verdict("CPUWAIT", readings), FAIL)

    def test_absent_ddr_reading_is_unproven(self):
        self.assertEqual(
            self.verdict("DDR_SELFTEST", good_baseline(ddr_selftest_passed=None)), UNPROVEN
        )

    # -- UART ----------------------------------------------------------------

    def test_four_free_ports_pass(self):
        self.assertEqual(self.verdict("UART_OWNERSHIP", good_storage()), PASS)

    def test_a_user_holder_fails(self):
        holders = {
            port: {"holders": 0, "root_inclusive": True} for port in preflight.FTDI_PORTS
        }
        holders["ttyUSB1"] = {"holders": 1, "root_inclusive": True}
        self.assertEqual(self.verdict("UART_OWNERSHIP", good_storage(uart_holders=holders)), FAIL)

    def test_a_root_owned_holder_fails(self):
        holders = {
            port: {"holders": 0, "root_inclusive": True} for port in preflight.FTDI_PORTS
        }
        holders["ttyUSB3"] = {"holders": 1, "root_inclusive": True, "owner": "root"}
        self.assertEqual(self.verdict("UART_OWNERSHIP", good_storage(uart_holders=holders)), FAIL)

    def test_unprovable_root_ownership_is_unproven_not_pass(self):
        # This is the state this project actually stopped at: nothing visible,
        # and no way to establish whether a root-owned process held the port.
        # A boolean would have had to call it true.
        holders = {
            port: {"holders": 0, "root_inclusive": True} for port in preflight.FTDI_PORTS
        }
        holders["ttyUSB0"] = {"holders": 0, "root_inclusive": False}
        self.assertEqual(
            self.verdict("UART_OWNERSHIP", good_storage(uart_holders=holders)), UNPROVEN
        )

    def test_a_port_with_no_reading_at_all_is_unproven(self):
        holders = {
            port: {"holders": 0, "root_inclusive": True}
            for port in preflight.FTDI_PORTS[:3]
        }
        self.assertEqual(
            self.verdict("UART_OWNERSHIP", good_storage(uart_holders=holders)), UNPROVEN
        )

    # -- storage -------------------------------------------------------------

    def test_absent_card_and_zero_mounts_pass(self):
        self.assertEqual(self.verdict("USB_OFF", good_storage()), PASS)
        self.assertEqual(self.verdict("MOUNT_COUNT", good_storage()), PASS)

    def test_card_still_present_after_usb_off_fails(self):
        self.assertEqual(
            self.verdict("USB_OFF", good_storage(block_device_present=True)), FAIL
        )

    def test_a_mount_fails(self):
        self.assertEqual(self.verdict("MOUNT_COUNT", good_storage(mount_count=1)), FAIL)

    def test_a_write_holder_fails(self):
        self.assertEqual(
            self.verdict("BLOCK_WRITE_HOLDERS", good_storage(block_device_write_holders=1)),
            FAIL,
        )

    def test_unknown_holder_status_is_unproven(self):
        self.assertEqual(
            self.verdict("BLOCK_WRITE_HOLDERS", good_storage(block_device_write_holders=None)),
            UNPROVEN,
        )


class V14CandidateGates(unittest.TestCase):
    """The layer V14 does define: which bytes, which variant, which evidence."""

    def verdict(self, gate_id, readings):
        gate = next(g for g in preflight.GATES if g["id"] == gate_id)
        return gate["evaluate"](readings)[0]

    def test_matching_digests_pass(self):
        self.assertEqual(self.verdict("CANDIDATE_IDENTITY", good_candidate()), PASS)

    def test_a_drifted_digest_fails(self):
        digests = dict(QUALIFIED)
        digests["APP.BIN"] = "d" * 64
        self.assertEqual(
            self.verdict("CANDIDATE_IDENTITY", good_candidate(candidate_digests=digests)), FAIL
        )

    def test_a_missing_artifact_fails(self):
        digests = dict(QUALIFIED)
        del digests["DDR.BIN"]
        self.assertEqual(
            self.verdict("CANDIDATE_IDENTITY", good_candidate(candidate_digests=digests)), FAIL
        )

    def test_an_extra_artifact_fails(self):
        digests = dict(QUALIFIED)
        digests["EXTRA.BIN"] = "e" * 64
        self.assertEqual(
            self.verdict("CANDIDATE_IDENTITY", good_candidate(candidate_digests=digests)), FAIL
        )

    def test_an_empty_qualified_table_is_unproven(self):
        # Agreeing with nothing is not agreement.
        self.assertEqual(
            self.verdict("CANDIDATE_IDENTITY", good_candidate(qualified_digests={})), UNPROVEN
        )

    def test_variant_disagreement_fails(self):
        self.assertEqual(
            self.verdict("VARIANT_IDENTITY", good_candidate(manifest_variant="SQ")), FAIL
        )

    def test_a_variant_outside_the_contract_fails(self):
        self.assertEqual(
            self.verdict(
                "VARIANT_IDENTITY", good_candidate(candidate_variant="ZZ", manifest_variant="ZZ")
            ),
            FAIL,
        )

    def test_an_unreplayed_manifest_is_unproven(self):
        self.assertEqual(
            self.verdict("MANIFEST_REPLAY", good_candidate(manifest_verified=None)), UNPROVEN
        )

    def test_each_static_evidence_field_is_required(self):
        for field in ("real_elf_pass", "read_order_equivalent", "common_tail_shared"):
            self.assertEqual(
                self.verdict("STATIC_GATE_EVIDENCE", good_candidate(**{field: None})),
                UNPROVEN,
                field,
            )
            self.assertEqual(
                self.verdict("STATIC_GATE_EVIDENCE", good_candidate(**{field: False})),
                FAIL,
                field,
            )


class Sequencing(unittest.TestCase):
    """The order is the safety property, so the order is what gets attacked."""

    def test_the_whole_contract_authorizes_when_everything_passes(self):
        run = preflight.run_preflight(good_storage(), good_baseline(), good_candidate())
        self.assertEqual(run.state, preflight.DEPLOYMENT_AUTHORIZED)
        self.assertTrue(run.authorized())
        self.assertTrue(run.require_authorization())
        self.assertEqual(run.report()["mandatory_unproven"], [])

    def test_a_storage_failure_stops_before_the_baseline_is_read(self):
        run = preflight.run_preflight(
            good_storage(mount_count=1), good_baseline(), good_candidate()
        )
        self.assertEqual(run.state, preflight.STOPPED)
        report = run.report()
        self.assertEqual(report["stages"][preflight.BASELINE], [])
        self.assertEqual(report["stages"][preflight.CANDIDATE], [])

    def test_a_dead_baseline_stops_before_the_candidate_is_considered(self):
        # The attribution argument: deploying onto a board that is already dead
        # makes the next failure impossible to attribute.
        run = preflight.run_preflight(
            good_storage(), good_baseline(ddr_selftest_passed=False), good_candidate()
        )
        self.assertEqual(run.state, preflight.STOPPED)
        self.assertEqual(run.report()["stages"][preflight.CANDIDATE], [])

    def test_an_unproven_gate_stops_the_run_like_a_failure(self):
        holders = {
            port: {"holders": 0, "root_inclusive": True} for port in preflight.FTDI_PORTS
        }
        holders["ttyUSB0"] = {"holders": 0, "root_inclusive": False}
        run = preflight.run_preflight(
            good_storage(uart_holders=holders), good_baseline(), good_candidate()
        )
        self.assertEqual(run.state, preflight.STOPPED)
        self.assertFalse(run.authorized())
        self.assertEqual(run.report()["mandatory_unproven"], ["UART_OWNERSHIP"])

    def test_stages_cannot_be_run_out_of_order(self):
        run = preflight.Preflight()
        with self.assertRaises(preflight.PreflightError):
            run.run_stage(preflight.BASELINE, good_baseline())

    def test_the_candidate_stage_cannot_be_reached_by_skipping_the_baseline(self):
        run = preflight.Preflight()
        run.run_stage(preflight.STORAGE, good_storage())
        with self.assertRaises(preflight.PreflightError):
            run.run_stage(preflight.CANDIDATE, good_candidate())

    def test_a_stopped_run_does_not_continue(self):
        run = preflight.Preflight()
        run.run_stage(preflight.STORAGE, good_storage(mount_count=1))
        self.assertEqual(run.state, preflight.STOPPED)
        with self.assertRaises(preflight.PreflightError):
            run.run_stage(preflight.BASELINE, good_baseline())

    def test_a_stage_cannot_be_run_twice(self):
        run = preflight.Preflight()
        run.run_stage(preflight.STORAGE, good_storage())
        with self.assertRaises(preflight.PreflightError):
            run.run_stage(preflight.STORAGE, good_storage())

    def test_a_refused_stage_evaluates_nothing(self):
        # Two guards stand between a caller and an out-of-order stage: the order
        # check, and the transition table. Either alone makes the call raise, so
        # a test that only asserts "it raises" cannot tell which one is doing
        # the work -- and neuter either and the suite stays green. This pins the
        # order check specifically: a stage refused for being out of order must
        # not have read its gates on the way to refusing.
        run = preflight.Preflight()
        with self.assertRaises(preflight.PreflightError):
            run.run_stage(preflight.BASELINE, good_baseline())
        self.assertEqual(run.results, {})
        self.assertEqual(run.state, preflight.INITIAL)

    def test_no_state_is_a_legal_transition_to_itself(self):
        # And this pins the table: re-entering a state is never legal, whether
        # or not the order check would have caught the caller first.
        for state, targets in preflight.LEGAL_TRANSITIONS.items():
            self.assertNotIn(state, targets, state)

    def test_the_transition_table_leads_only_forward_or_to_stopped(self):
        order = (
            preflight.INITIAL,
            preflight.STORAGE_SAFE,
            preflight.BASELINE_LIVE,
            preflight.DEPLOYMENT_AUTHORIZED,
        )
        for index, state in enumerate(order):
            for target in preflight.LEGAL_TRANSITIONS[state]:
                if target == preflight.STOPPED:
                    continue
                self.assertEqual(
                    order.index(target), index + 1, "%s -> %s" % (state, target)
                )

    def test_authorization_raises_rather_than_returning_false(self):
        # A caller who forgets to look at the answer still cannot deploy.
        run = preflight.Preflight()
        with self.assertRaises(preflight.PreflightError):
            run.require_authorization()

    def test_the_transition_history_records_where_it_stopped(self):
        run = preflight.run_preflight(
            good_storage(), good_baseline(cpuwait_cleared=False), good_candidate()
        )
        transitions = run.report()["transitions"]
        self.assertEqual(transitions[0]["to"], preflight.STORAGE_SAFE)
        self.assertEqual(transitions[-1]["to"], preflight.STOPPED)
        self.assertIn("BASELINE", transitions[-1]["reason"])


class NormativeSources(unittest.TestCase):
    """Every inherited threshold cites a document, and every citation is pinned."""

    def test_every_inherited_gate_cites_a_pinned_source(self):
        for gate in preflight.GATES:
            if gate["layer"] != preflight.INHERITED:
                continue
            source = gate["source"]
            self.assertIsNotNone(source, gate["id"])
            for field in ("document", "section", "commit", "blob"):
                self.assertTrue(source.get(field), "%s: %s" % (gate["id"], field))

    def test_the_cited_documents_are_the_documents_in_this_tree(self):
        # A citation to "the current version of a file" drifts. The blob hash is
        # what makes the citation checkable, so it is checked.
        seen = set()
        for gate in preflight.GATES:
            source = gate["source"]
            if source is None or source["document"] in seen:
                continue
            seen.add(source["document"])
            path = REPO / source["document"]
            self.assertTrue(path.is_file(), source["document"])
            blob = subprocess.run(
                ["git", "hash-object", str(path)],
                capture_output=True,
                text=True,
                cwd=str(REPO),
            ).stdout.strip()
            self.assertTrue(
                blob.startswith(source["blob"]),
                "%s: cited %s, tree has %s" % (source["document"], source["blob"], blob[:12]),
            )

    def test_v14_gates_do_not_claim_inherited_authority(self):
        for gate in preflight.GATES:
            if gate["layer"] == preflight.V14_SPECIFIC:
                self.assertIsNone(gate["source"], gate["id"])

    def test_both_layers_are_present_and_separate(self):
        layers = {gate["layer"] for gate in preflight.GATES}
        self.assertEqual(layers, {preflight.INHERITED, preflight.V14_SPECIFIC})


class CommandLine(unittest.TestCase):
    def run_cli(self, document):
        with tempfile.TemporaryDirectory() as scratch:
            path = pathlib.Path(scratch) / "readings.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(REPO / "host" / "preflight_pmu_completion_visibility_v14.py"), str(path)],
                capture_output=True,
                text=True,
            )

    def test_a_clean_reading_prints_go(self):
        result = self.run_cli(
            {
                "storage": good_storage(),
                "baseline": good_baseline(),
                "candidate": good_candidate(),
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PREBOARD_GATE GO", result.stdout)

    def test_a_stopped_reading_exits_nonzero(self):
        result = self.run_cli(
            {
                "storage": good_storage(),
                "baseline": good_baseline(),
                "candidate": good_candidate(manifest_verified=False),
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PREBOARD_GATE STOP", result.stderr)

    def test_a_missing_section_is_a_caller_error(self):
        result = self.run_cli({"storage": good_storage(), "baseline": good_baseline()})
        self.assertEqual(result.returncode, 2)
        self.assertIn("candidate", result.stderr)


if __name__ == "__main__":
    unittest.main()
