"""Stage 6B-E2D rules (evidence/stage6b/stage6be2d/contract.md). Expected values typed by hand."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6be2d as E  # noqa: E402


def res(npu, rng, mac=20736, status="VALID"):
    return dict(status=status, reasons=[], metrics=dict(npu_active=npu, npu_active_range=rng, mac_active=mac))


class Rules(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(E.PE_VELA, {500: 100310 - 53052, 1000: 200622 - 83142})
        self.assertEqual(E.INTERACTION_VELA, (200622 - 100310) - (83142 - 53052))
        self.assertEqual(E.H1UC, 20736)
        self.assertEqual([b for _, _, b in E.ORDER], list(range(440, 449)))
        self.assertEqual([(c, L) for c, L, _ in E.ORDER][1:5], [("W0-P0", 500), ("W0-P1", 500), ("W1-P0", 500), ("W1-P1", 500)])
        self.assertEqual([(c, L) for c, L, _ in E.ORDER][5:], [("W1-P1", 1000), ("W1-P0", 1000), ("W0-P1", 1000), ("W0-P0", 1000)])

    def test_tol(self):
        self.assertEqual(E.tol(100000, [300, 400]), 1000)
        self.assertEqual(E.tol(100000, [700, 600]), 1300)

    def test_placement_effect(self):
        t = {500: 1000, 1000: 1000}
        self.assertEqual(E.placement_effect({500: 5000, 1000: 9000}, t, True), "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.placement_effect({500: -5000, 1000: -9000}, t, True), "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.placement_effect({500: 5000, 1000: -9000}, t, True), "PLACEMENT_EFFECT_NOT_RESOLVED")
        self.assertEqual(E.placement_effect({500: 1000, 1000: 9000}, t, True), "PLACEMENT_EFFECT_NOT_RESOLVED")   # = tol
        self.assertEqual(E.placement_effect({500: 5000, 1000: 9000}, t, False), "NOT_IDENTIFIABLE")

    def test_within(self):
        self.assertTrue(E.within(53000, 47258, 1000))      # 5742 <= 7088.7 + 1000
        self.assertFalse(E.within(56400, 47258, 1000))     # 9142 > 8088.7
        self.assertTrue(E.within(55300, 47258, 1000))      # 8042 <= 8088.7

    def test_fidelity(self):
        t = {500: 1000, 1000: 1000}
        ok = {500: 47258, 1000: 117480}
        self.assertEqual(E.fidelity(ok, t, {500: True, 1000: True}), "PLACEMENT_RESPONSE_CONSISTENT")
        self.assertEqual(E.fidelity({500: 47258, 1000: 50000}, t, {500: True, 1000: True}), "PLACEMENT_RESPONSE_DISCREPANCY")
        self.assertEqual(E.fidelity(ok, t, {500: True, 1000: False}), "FIDELITY_PARTIAL")
        self.assertEqual(E.fidelity({500: 0, 1000: 117480}, t, {500: True, 1000: False}), "PLACEMENT_RESPONSE_DISCREPANCY")
        self.assertEqual(E.fidelity(ok, t, {}), "NOT_COMPARABLE")

    def test_validity(self):
        p = dict(verdict="PASS")
        good = {k: dict(status="VALID") for k in ("REF", "a", "b")}
        self.assertEqual(E.validity(p, good, {"a": True, "b": True}), "VALID")
        self.assertEqual(E.validity(p, good, {"a": True, "b": False}), "PARTIAL_VALID")
        for s in ("UNSTABLE", "INVALID_OUTPUT", "INVALID_PMU"):
            self.assertEqual(E.validity(p, dict(good, a=dict(status=s)), {"b": True}), "PARTIAL_VALID", s)
        for s in ("CONFIG_MISMATCH", "UNMEASURED"):
            self.assertEqual(E.validity(p, dict(good, a=dict(status=s)), {"b": True}), "MEASUREMENT_INVALID", s)
        self.assertEqual(E.validity(dict(verdict="FAIL"), good, {"a": True}), "MEASUREMENT_INVALID")

    def test_mechanism(self):
        self.assertEqual(E.mechanism(), "MECHANISM_UNRESOLVED")

    def test_effects(self):
        r = {"W1-P0-L500": res(150000, 500), "W1-P1-L500": res(100000, 400), "W1-P0-L1000": res(260000, 600), "W1-P1-L1000": res(160000, 300)}
        e = E.effects(r, "W1", True)
        self.assertEqual(e["pe"], {500: 50000, 1000: 100000})
        self.assertEqual(e["tol_pe"], {500: 1000, 1000: 1600})          # max(1000, 900), max(1600, 900)
        self.assertEqual(e["le"], {"W1-P0": 110000, "W1-P1": 60000})
        self.assertEqual(e["tol_le"], {"W1-P0": 1500, "W1-P1": 1000})    # max(1500, 1100), max(1000, 700)
        self.assertEqual((e["interaction"], e["tol_interaction"]), (50000, 1800))   # max(1000, 1800)
        self.assertAlmostEqual(e["ratio"]["W1-P0"], 260000 / 150000)
        self.assertEqual(e["cls"], "PLACEMENT_EFFECT_OBSERVED")
        self.assertEqual(E.effects(r, "W1", False), dict(usable=False))

    def test_key(self):
        self.assertEqual(E.key("REF", 500), "REF")
        self.assertEqual(E.key("W1-P0", 1000), "W1-P0-L1000")


if __name__ == "__main__":
    unittest.main()
