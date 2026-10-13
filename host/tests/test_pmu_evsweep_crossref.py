import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import pmu_evsweep_crossref as X


def cells(accept):
    out = []
    for p, slots in (("0", [0]), ("1", range(8))):
        for s in slots:
            for ev in range(1024):
                rb = ev if accept(ev) else 0
                out.append({"pass": p, "slot": str(s), "ev": str(ev), "readback_hex": f"{rb:08x}",
                            "verdict": "ACCEPTED" if rb == ev else "COERCED_TO_ZERO"})
    return out


class T(unittest.TestCase):
    def test_accept_exactly_trm110(self):
        trm, drv = X.load_tables()
        x = X.crossref(cells(lambda ev: ev in trm))
        self.assertEqual(x["accepted_count"], 110)
        self.assertEqual(x["trm110_not_accepted"], [])
        self.assertEqual(x["accepted_in_driver_reserved61"], [])
        self.assertEqual(len(x["driver_reserved61_not_accepted"]), 61)
        self.assertEqual(x["accepted_outside_driver171"], [])
        self.assertEqual(x["slot_agreement"], "AGREE")
        self.assertEqual(x["p0_vs_p1"], "EQUAL")

    def test_accept_all_1024(self):
        x = X.crossref(cells(lambda ev: True))
        self.assertEqual(x["accepted_count"], 1024)
        self.assertEqual(len(x["accepted_in_driver_reserved61"]), 61)
        self.assertEqual(len(x["accepted_outside_driver171"]), 1024 - 171)

    def test_per_event_rows_cover_171(self):
        prov = dict(board_serial="B", fpga_image="F", uart_log_sha256="u", app_sha256="a",
                    captured_at_utc="t", authorization="z")
        rows = X.per_event_table(cells(lambda ev: True), prov)
        self.assertEqual(len(rows), 171)
        self.assertTrue(all(r["slots_accepted_p1"] == 8 for r in rows))


if __name__ == "__main__":
    unittest.main()
