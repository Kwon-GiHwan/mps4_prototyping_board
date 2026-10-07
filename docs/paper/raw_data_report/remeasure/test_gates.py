"""Mutation test for the R1 gates.

Each gate is neutered at the data, not at the code: one cell in a copy of
R1_RAW.json is corrupted in exactly the way the gate exists to catch, and the
gate must go FAIL. A mutation that survives means the gate has no reaching
fixture and examines nothing.

    python3 -m unittest docs.paper.raw_data_report.remeasure.test_gates
    (or)  python3 docs/paper/raw_data_report/remeasure/test_gates.py
"""
import copy, json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates


def _counters(rep):
    return rep["pmu"]["counters"]


class GateMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(gates.RAW):
            raise unittest.SkipTest("R1_RAW.json not present; run remeasure_u85.py first")
        cls.raw = json.load(open(gates.RAW))
        cls.frozen = gates.frozen_rows()

    def verdicts(self, results):
        g, _ = gates.evaluate(results, self.frozen)
        return {k: v["verdict"] for k, v in g.items()}

    def test_00_unmutated_all_pass(self):
        """The baseline must be green, or every mutation below is vacuous."""
        self.assertEqual(set(self.verdicts(self.raw).values()), {"PASS"})

    def _mutate(self, fn):
        m = copy.deepcopy(self.raw)
        fn(m[0])
        return self.verdicts(m)

    def test_g1_detects_artifact_mismatch(self):
        v = self._mutate(lambda c: c["reproduction_gate"].__setitem__(
            "axf_sha_matches_anchor", False))
        self.assertEqual(v["G1_artifact_reproduction"], "FAIL")

    def test_g2_detects_total_cycle_drift(self):
        v = self._mutate(lambda c: _counters(c["reps"][0]).__setitem__(
            "TOTAL", _counters(c["reps"][0])["TOTAL"] + 1))
        self.assertEqual(v["G2_total_cycles_match_frozen"], "FAIL")

    def test_g3_detects_active_cycle_drift(self):
        v = self._mutate(lambda c: _counters(c["reps"][0]).__setitem__(
            "ACTIVE", _counters(c["reps"][0])["ACTIVE"] + 1))
        self.assertEqual(v["G3_active_cycles_match_frozen"], "FAIL")

    def test_g4_detects_repetition_disagreement(self):
        v = self._mutate(lambda c: _counters(c["reps"][1]).__setitem__(
            "SRAM_RD_DATA_BEAT_RECEIVED",
            _counters(c["reps"][1])["SRAM_RD_DATA_BEAT_RECEIVED"] + 1))
        self.assertEqual(v["G4_repetition_identical"], "FAIL")

    def test_g4_detects_missing_repetition(self):
        v = self._mutate(lambda c: c.__setitem__("reps", c["reps"][:1]))
        self.assertEqual(v["G4_repetition_identical"], "FAIL")

    def test_g5_detects_absent_memory_counter(self):
        v = self._mutate(lambda c: _counters(c["reps"][0]).pop(
            "EXT_WR_DATA_BEAT_WRITTEN"))
        self.assertEqual(v["G5_memory_counters_present"], "FAIL")

    def test_g5_is_the_original_failure_mode(self):
        """The exact loss being repaired: the U85 memory counters absent."""
        def kill(c):
            for r in c["reps"]:
                for k in gates.MEM:
                    _counters(r).pop(k, None)
        v = self._mutate(kill)
        self.assertEqual(v["G5_memory_counters_present"], "FAIL")

    def test_short_cell_count_fails_every_gate(self):
        """A gate is PASS only at 35/35; a truncated run must not read as PASS."""
        g, _ = gates.evaluate(self.raw[:-1], self.frozen)
        self.assertTrue(all(v["verdict"] == "FAIL" for v in g.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
