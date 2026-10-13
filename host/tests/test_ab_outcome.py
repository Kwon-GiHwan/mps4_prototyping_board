import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ab_outcome as A  # noqa: E402

C = {"35": 1000, "48": 100, "386": 500, "391": 10}


def t(npu, **kw):
    d = dict(C, **{"35": npu}); d.update(kw); return d


class Outcome(unittest.TestCase):
    def test_bands(self):   # MLEK 200: gap 800
        self.assertEqual(A.outcome(True, True, C, t(360), 200), "SUPPORTED")          # closure 0.8
        self.assertEqual(A.outcome(True, True, C, t(361), 200), "PARTIAL_CONTRIBUTOR")
        self.assertEqual(A.outcome(True, True, C, t(840), 200), "PARTIAL_CONTRIBUTOR")  # closure 0.2
        self.assertEqual(A.outcome(True, True, C, t(841), 200), "REFUTED")
        self.assertEqual(A.outcome(True, True, C, t(1200), 200), "REFUTED")            # worse

    def test_not_screened_is_unresolved(self):
        self.assertEqual(A.outcome(False, True, C, t(200), 200), "UNRESOLVED")
        self.assertEqual(A.outcome(True, False, C, t(200), 200), "UNRESOLVED")

    def test_invariant_moves_make_it_unresolved(self):
        for ev in ("48", "386", "391"):
            moved = t(200, **{ev: C[ev] * 1.01})
            self.assertEqual(A.outcome(True, True, C, moved, 200), "UNRESOLVED", ev)
        within = t(200, **{"386": 500.4})   # 0.08 % < 0.1 %
        self.assertEqual(A.outcome(True, True, C, within, 200), "SUPPORTED")

    def test_no_gap_is_unresolved(self):
        self.assertEqual(A.outcome(True, True, t(200), t(150), 200), "UNRESOLVED")

    def test_overall_needs_kws_and_ad_agree(self):
        self.assertEqual(A.overall({"kws_micronet_m": "SUPPORTED", "ad_medium_int8": "SUPPORTED"}), "SUPPORTED")
        self.assertEqual(A.overall({"kws_micronet_m": "SUPPORTED", "ad_medium_int8": "PARTIAL_CONTRIBUTOR"}), "UNRESOLVED")
        self.assertEqual(A.overall({"kws_micronet_m": "REFUTED", "ad_medium_int8": "REFUTED",
                                    "mobilenet_v2_1.0_224_INT8": "SUPPORTED"}), "REFUTED")
        self.assertEqual(A.overall({"kws_micronet_m": "UNRESOLVED", "ad_medium_int8": "UNRESOLVED"}), "UNRESOLVED")

    def test_closed_set(self):
        got = {A.outcome(s, True, C, t(n), 200) for s in (True, False) for n in (200, 500, 1000)}
        self.assertEqual(got, set(A.OUTCOMES))


class Reference(unittest.TestCase):
    def test_mlek_reference_is_the_b1_b3_median(self):
        ref = A.mlek_active()
        self.assertEqual(ref, {"kws_micronet_m": 91_431, "ad_medium_int8": 145_976,
                               "mobilenet_v2_1.0_224_INT8": 1_448_049})


if __name__ == "__main__":
    unittest.main()
