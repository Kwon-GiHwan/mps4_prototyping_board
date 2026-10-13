import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import pmu_tiers_join as J

W = "FTDI-X / FI101-r1p0 (109762 v0100) / NPU APB 0x50004000 PMEVTYPER[slot]"
def ra(ev, name): return dict(ev_type=str(ev), name=name, in_trm110="True", in_driver171="True", verdict_p1_slot0="ACCEPTED",
                              readback_p1_slot0=f"{ev:08x}", slots_accepted_p1="8", boot="boot1", app_sha256="a", where=W, how="A", authorization="z")
def rb(ev, name, v="COUNTED_NONZERO"): return dict(ev_type=str(ev), name=name, verdict=v, values="[1, 2, 3]", boot="boot2", app_sha256="b", how="B")


class T(unittest.TestCase):
    def test_join_rows_and_columns(self):
        rows = J.join([ra(17, "cycle"), ra(35, "npu_active")], [rb(17, "cycle"), rb(35, "npu_active", "COUNTED_ZERO")])
        self.assertEqual([r["ev_type"] for r in rows], [17, 35])
        self.assertEqual(rows[1]["tierB_verdict"], "COUNTED_ZERO")
        self.assertEqual(rows[0]["board_serial"], "FTDI-X"); self.assertEqual(rows[0]["fpga_image"], "FI101-r1p0 (109762 v0100)")
        self.assertEqual(set(rows[0]), set(J.COLS))

    def test_refuses_mismatched_coverage(self):
        with self.assertRaises(SystemExit): J.join([ra(17, "cycle")], [rb(17, "cycle"), rb(35, "npu_active")])

    def test_refuses_name_mismatch(self):
        with self.assertRaises(SystemExit): J.join([ra(17, "cycle")], [rb(17, "npu_idle")])


if __name__ == "__main__":
    unittest.main()
