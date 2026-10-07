"""Every P0-E2 gate, tripped by a fixture built to reach it.

The point of this file is not that the ten gates pass on good input. It is that
each one *fails* on bad input, at its own rule id, and that no gate is reachable
only through a neighbour's refusal. Eleven gates in this repository have turned
out to examine nothing; the coverage test at the bottom is what makes that
detectable here, and every check in gates.py is mutation-tested against it.

Run with:
    python3 -m unittest host.tests.p0e2.test_gates
"""

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from host.experiments.p0e2 import gates  # noqa: E402


GOOD_MODELS = dict(gates.FROZEN_MODEL_SHA)
GOOD_TOOLCHAIN = dict(gates.SEPTEMBER_TOOLCHAIN)
GOOD_PATCHES = dict(gates.SEPTEMBER_PATCH_SHA)


def run_vector(**over):
    """One process's metric vector, in the shape stage 2 records it."""
    base = {"total": 1040, "active": 1000, "idle": 40,
            "crc": "0:96:0xA553FCA6", "plprof": "PLPROF,0,1,2", "pl_count": 1}
    base.update(over)
    return base


def op(index, op_type="Conv2D", ifm="1x224x224x3", ofm="1x112x112x32",
       workload="mobilenet_v2_1.0_224_INT8"):
    return {"workload": workload, "op_index": index, "op_type": op_type,
            "ifm_shape": ifm, "ofm_shape": ofm}


class ModelShaGate(unittest.TestCase):
    def test_frozen_models_pass(self):
        self.assertTrue(gates.check_model_sha(GOOD_MODELS))

    def test_altered_sha_is_refused(self):
        bad = dict(GOOD_MODELS, wav2letter_pruned_int8="00" * 32)
        with self.assertRaises(gates.GateError) as caught:
            gates.check_model_sha(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_MODEL_SHA)

    def test_absent_model_is_refused(self):
        bad = {k: v for k, v in GOOD_MODELS.items()
               if k != "mobilenet_v2_1.0_224_INT8"}
        with self.assertRaises(gates.GateError) as caught:
            gates.check_model_sha(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_MODEL_SHA)

    def test_model_outside_the_closed_set_is_refused(self):
        """Section 1 is a closed set; a seventh workload has no frozen value."""
        bad = dict(GOOD_MODELS, dnn_s_quantized="ab" * 32)
        with self.assertRaises(gates.GateError) as caught:
            gates.check_model_sha(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_MODEL_SHA)


class ToolchainGate(unittest.TestCase):
    def test_september_toolchain_passes(self):
        self.assertTrue(gates.check_toolchain(GOOD_TOOLCHAIN))

    def test_vela_drift_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_toolchain(dict(GOOD_TOOLCHAIN, vela="5.1.0"))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_TOOLCHAIN)

    def test_absent_component_is_refused(self):
        bad = {k: v for k, v in GOOD_TOOLCHAIN.items() if k != "fvp"}
        with self.assertRaises(gates.GateError) as caught:
            gates.check_toolchain(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_TOOLCHAIN)


class PatchIdentityGate(unittest.TestCase):
    def test_september_patches_pass(self):
        self.assertTrue(gates.check_patch_identity(GOOD_PATCHES))

    def test_edited_patch_is_refused(self):
        bad = dict(GOOD_PATCHES, **{"patch_driver_u85_v3.py": "cc" * 32})
        with self.assertRaises(gates.GateError) as caught:
            gates.check_patch_identity(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_PATCH_IDENTITY)

    def test_substituted_exploration_tool_is_refused(self):
        """/workspace/per-layer-profiling/patch-driver.py is a different tool;
        reaching for it instead of the campaign patch must not pass."""
        bad = {k: v for k, v in GOOD_PATCHES.items()
               if k != "patch_driver_u85_v3.py"}
        bad["patch-driver.py"] = "dd" * 32
        with self.assertRaises(gates.GateError) as caught:
            gates.check_patch_identity(bad)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_PATCH_IDENTITY)


class IrqValidGate(unittest.TestCase):
    def cell(self, **over):
        base = {"cell": "mobilenet_v2_1.0_224_INT8__256_Low",
                "irq_count": 221, "stream_irq_count": 221,
                "serviced_launches": 221}
        base.update(over)
        return base

    def test_matching_counts_pass(self):
        self.assertTrue(gates.check_irq_valid(self.cell()))

    def test_stream_dropped_an_irq(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_irq_valid(self.cell(stream_irq_count=220))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IRQ_VALID)

    def test_target_serviced_fewer_than_inserted(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_irq_valid(self.cell(serviced_launches=198))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IRQ_VALID)

    def test_no_irq_at_all_is_not_a_vacuous_pass(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_irq_valid(
                self.cell(irq_count=0, stream_irq_count=0, serviced_launches=0))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IRQ_VALID)

    def test_missing_evidence_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_irq_valid(self.cell(serviced_launches=None))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IRQ_VALID)


class LayerCapGate(unittest.TestCase):
    def test_measured_counts_pass(self):
        for n in (39, 216, 220, 221, 226, 228):
            self.assertTrue(gates.check_layer_cap({"cell": "c", "irq_count": n}))

    def test_over_the_cap_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_layer_cap({"cell": "c", "irq_count": 257})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_LAYER_CAP)

    def test_batch_split_is_refused_even_under_the_cap(self):
        """Contract section 5: the cap is a STOP, never a reason to split."""
        with self.assertRaises(gates.GateError) as caught:
            gates.check_layer_cap({"cell": "c", "irq_count": 120, "batches": 3})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_LAYER_CAP)

    def test_missing_count_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_layer_cap({"cell": "c", "irq_count": None})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_LAYER_CAP)


class RepsExactGate(unittest.TestCase):
    def test_three_identical_processes_pass(self):
        self.assertTrue(gates.check_reps_exact([run_vector()] * 3))

    def test_one_cycle_of_disagreement_is_a_stop(self):
        runs = [run_vector(), run_vector(), run_vector(total=1041)]
        with self.assertRaises(gates.GateError) as caught:
            gates.check_reps_exact(runs)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_REPS_EXACT)

    def test_per_layer_records_must_agree_too(self):
        runs = [run_vector(), run_vector(plprof="PLPROF,0,9,9"), run_vector()]
        with self.assertRaises(gates.GateError) as caught:
            gates.check_reps_exact(runs)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_REPS_EXACT)

    def test_two_runs_are_not_three(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_reps_exact([run_vector()] * 2)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_REPS_EXACT)

    def test_dropping_a_field_is_not_agreement(self):
        thin = run_vector()
        del thin["idle"]
        with self.assertRaises(gates.GateError) as caught:
            gates.check_reps_exact([thin, run_vector(), run_vector()])
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_REPS_EXACT)

    def test_the_replicate_vector_is_the_registered_one(self):
        """Widening this tuple weakens every reps check, so it is asserted."""
        self.assertEqual(
            gates.REPLICATE_FIELDS,
            ("total", "active", "idle", "crc", "plprof", "pl_count"))


class SumCoherentGate(unittest.TestCase):
    def test_september_envelope_cells_pass(self):
        """The fifteen frozen cells the envelope was derived from: the two
        extremes of each bound, which must remain inside it."""
        for unit_sum, clean_total in ((285195, 287068),   # vww4 256, -1873
                                      (256195, 259068),   # vww4 512, -2873
                                      (118340, 116068),   # kws  512, +2272
                                      (35313, 36086)):    # rnnoise 256, -2.14%
            self.assertTrue(gates.check_sum_coherent(
                {"cell": "c", "unit_ccnt_sum": unit_sum,
                 "clean_total": clean_total}))

    def test_absolute_residual_beyond_the_envelope_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_sum_coherent({"cell": "c", "unit_ccnt_sum": 1_000_000,
                                      "clean_total": 1_004_000})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_SUM_COHERENT)

    def test_ratio_beyond_the_envelope_is_refused(self):
        """Small model, small absolute residual, ratio out of band: the
        absolute bound alone would let this through."""
        with self.assertRaises(gates.GateError) as caught:
            gates.check_sum_coherent({"cell": "c", "unit_ccnt_sum": 9_000,
                                      "clean_total": 10_000})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_SUM_COHERENT)

    def test_missing_sum_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_sum_coherent({"cell": "c", "unit_ccnt_sum": None,
                                      "clean_total": 10_000})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_SUM_COHERENT)

    def test_zero_clean_total_is_refused_not_divided_by(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_sum_coherent({"cell": "c", "unit_ccnt_sum": 0,
                                      "clean_total": 0})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_SUM_COHERENT)


class OutputCrcGate(unittest.TestCase):
    def test_identical_crc_passes(self):
        self.assertTrue(gates.check_output_crc(
            {"cell": "c", "clean_crc": "0:96:0xA553FCA6",
             "prof_crc": "0:96:0xA553FCA6"}))

    def test_differing_crc_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_output_crc({"cell": "c", "clean_crc": "0:96:0xA553FCA6",
                                    "prof_crc": "0:96:0xDEADBEEF"})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_OUTPUT_CRC)

    def test_two_absent_outputs_are_not_a_match(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_output_crc({"cell": "c", "clean_crc": "",
                                    "prof_crc": ""})
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_OUTPUT_CRC)


class IdentityJoinGate(unittest.TestCase):
    def join(self, **over):
        base = {"key": gates.IDENTITY_JOIN_KEY,
                "left": [op(0), op(1, "DepthwiseConv2D")],
                "right": [op(1, "DepthwiseConv2D"), op(0)]}
        base.update(over)
        return base

    def test_identity_join_passes_regardless_of_row_order(self):
        self.assertTrue(gates.check_identity_join(self.join()))

    def test_positional_key_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(key=("workload", "row_index")))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)

    def test_same_length_but_different_identities_is_refused(self):
        """What a positional join would silently accept."""
        right = [op(0), op(1, "Conv2D", ofm="1x56x56x64")]
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(right=right))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)

    def test_row_lacking_a_key_field_is_refused(self):
        thin = dict(op(0))
        del thin["ofm_shape"]
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(left=[thin, op(1)]))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)

    def test_duplicate_identity_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(left=[op(0), op(0)],
                                                right=[op(0), op(0)]))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)

    def test_duplicate_on_the_256_side_only_is_refused(self):
        """Duplicated on one side only, so the set comparison still agrees and
        only the 256-side uniqueness check can catch it. Without this fixture
        that check has no reaching input and could be deleted unnoticed."""
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(left=[op(0), op(0)],
                                                right=[op(0)]))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)

    def test_duplicate_on_the_512_side_only_is_refused(self):
        with self.assertRaises(gates.GateError) as caught:
            gates.check_identity_join(self.join(left=[op(0)],
                                                right=[op(0), op(0)]))
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_IDENTITY_JOIN)


class RestoreGate(unittest.TestCase):
    PRE = {"ethosu_driver.c": "56b2fecb", "ethosu_device_u85.c": "4cc662ad",
           "UseCaseHandler.cc": "5fb1a446",
           "register_command_stream_generator.py": "efcd87e8"}

    def test_restored_tree_passes(self):
        self.assertTrue(gates.check_restore(self.PRE, dict(self.PRE)))

    def test_still_patched_file_is_refused(self):
        post = dict(self.PRE, **{"ethosu_driver.c": "0badf00d"})
        with self.assertRaises(gates.GateError) as caught:
            gates.check_restore(self.PRE, post)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_RESTORE)

    def test_vanished_file_is_refused(self):
        post = {k: v for k, v in self.PRE.items() if k != "UseCaseHandler.cc"}
        with self.assertRaises(gates.GateError) as caught:
            gates.check_restore(self.PRE, post)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_RESTORE)

    def test_leftover_patched_copy_is_refused(self):
        post = dict(self.PRE, **{"ethosu_driver.c.patched": "0badf00d"})
        with self.assertRaises(gates.GateError) as caught:
            gates.check_restore(self.PRE, post)
        self.assertEqual(gates.refusal_rule(caught.exception),
                         gates.RULE_P0E2_RESTORE)


class RuleCoverage(unittest.TestCase):
    """Every rule in RULES is reachable by a fixture, and no fixture trips a
    rule that is not in RULES. A rule that no fixture reaches is a rule with no
    evidence that it can fail."""

    def test_every_rule_is_tripped_by_some_fixture(self):
        attempts = (
            lambda: gates.check_model_sha(
                dict(GOOD_MODELS, wav2letter_pruned_int8="00" * 32)),
            lambda: gates.check_toolchain(dict(GOOD_TOOLCHAIN, vela="5.1.0")),
            lambda: gates.check_patch_identity(
                dict(GOOD_PATCHES, **{"patch_app.py": "cc" * 32})),
            lambda: gates.check_irq_valid(
                {"cell": "c", "irq_count": 221, "stream_irq_count": 220,
                 "serviced_launches": 221}),
            lambda: gates.check_layer_cap({"cell": "c", "irq_count": 257}),
            lambda: gates.check_reps_exact(
                [run_vector(), run_vector(), run_vector(total=1041)]),
            lambda: gates.check_sum_coherent(
                {"cell": "c", "unit_ccnt_sum": 1_000_000,
                 "clean_total": 1_004_000}),
            lambda: gates.check_output_crc(
                {"cell": "c", "clean_crc": "a", "prof_crc": "b"}),
            lambda: gates.check_identity_join(
                {"key": ("workload", "row_index"), "left": [], "right": []}),
            lambda: gates.check_restore(
                {"f": "1"}, {"f": "2"}),
        )
        tripped = set()
        for attempt in attempts:
            try:
                attempt()
            except gates.GateError as exc:
                tripped.add(gates.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(gates, n) for n in gates.RULES})

    def test_rules_tuple_matches_the_module_constants(self):
        declared = {n for n in dir(gates) if n.startswith("RULE_P0E2_")}
        self.assertEqual(declared, set(gates.RULES))


if __name__ == "__main__":
    unittest.main()
