"""Amendment 2 golden validity G1-G5 (host/analysis/mlek_golden.py).

Positive fixture: the real mobilenet MLEK FI101 capture of evidence/mobilenet_ofm with its gmlek blob meta and the
amendment-1 manifest entry. Expected values come from that evidence, not from the module."""
import hashlib, json, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import mlek_golden as G

E = REPO / "evidence" / "mobilenet_ofm"
TEXT = (E / "app_uart.raw").read_bytes().decode("ascii", "replace").replace("\r", "")
META = json.loads((E / "workloads" / "mobilenet_v2_1.0_224_INT8.gmlek.pmwl.json").read_text())
FROZEN = json.loads((REPO / "config" / "mlek_baseline.manifest.a1.json").read_text())["workloads"]["mobilenet_v2_1.0_224_INT8"]
VELA = "031fade0e9b7136e2ed55a23422efbcc7aba28a32c8ebd3e043afbcc2f44bb75"   # MLEK stage-B Vela output (REPORT.md)
TFL = (E / "tflite_ofm.bin").read_bytes()


class Validity(unittest.TestCase):
    def test_real_capture_passes(self):
        self.assertEqual(G.validity(TEXT, META, FROZEN, VELA),
                         dict.fromkeys(("G1_lengths", "G2_same_vela_output", "G3_ta_configured",
                                        "G4_model_and_cms_unchanged", "G5_blob_holds_dump"), True))

    def test_entry_diagnostic_matches_report(self):
        e = G.entry(TEXT, META, FROZEN, VELA, TFL)
        d = e["numerical_difference_diagnostic"]
        self.assertEqual((d["mismatch_count"], d["positions"], d["signed_diff_mlek_minus_tflite"], d["max_abs_diff"]),
                         (7, [540, 620, 825, 880, 886, 912, 972], [2, 1, 1, -1, -16, 8, 2], 16))
        self.assertEqual(e["golden"]["input_sha256"][:8], "be4e0171")
        self.assertEqual(e["golden"]["ofm_sha256"][:8], "6f5b50a8")
        self.assertEqual(e["blob_sha256"], "0d51cf9eaf86d8e3aa9628a8da966d04f28f86610f6ceb9bd7ed94ae0996c7fd")
        self.assertEqual(e["cms_sha256"], FROZEN["cms_sha256"])

    def failed(self, text=TEXT, meta=META, frozen=FROZEN, vela=VELA):
        return [k for k, ok in G.validity(text, meta, frozen, vela).items() if not ok]

    def test_truncated_output_dump(self):
        self.assertEqual(self.failed(text=TEXT[:-4000]), ["G1_lengths", "G5_blob_holds_dump"])

    def test_other_vela_output(self):
        self.assertEqual(self.failed(vela="0" * 64), ["G2_same_vela_output"])

    def test_ta_not_configured(self):
        self.assertEqual(self.failed(text=TEXT.replace("Configured TA_EXT", "Skipped TA_EXT")), ["G3_ta_configured"])

    def test_cms_or_model_changed(self):
        self.assertEqual(self.failed(meta=dict(META, cms_sha256="0" * 64)), ["G4_model_and_cms_unchanged"])
        self.assertEqual(self.failed(meta=dict(META, model_sha256="0" * 64)), ["G4_model_and_cms_unchanged"])

    def test_blob_not_from_this_dump(self):
        self.assertEqual(self.failed(meta=dict(META, ifm_sha256="0" * 64)), ["G5_blob_holds_dump"])
        self.assertEqual(self.failed(meta=dict(META, golden_sha256=META["tflite_ofm_sha256"])), ["G5_blob_holds_dump"])

    def test_entry_refuses(self):
        with self.assertRaisesRegex(ValueError, "G2_same_vela_output"):
            G.entry(TEXT, META, FROZEN, "0" * 64, TFL)
        with self.assertRaisesRegex(ValueError, "tflite_runtime"):
            G.entry(TEXT, META, FROZEN, VELA, bytes(len(TFL)))


if __name__ == "__main__":
    unittest.main()
