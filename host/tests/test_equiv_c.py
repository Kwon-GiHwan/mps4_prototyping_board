import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import equiv_c as C

BEAT = dict(SRAM_RD_DATA_BEAT_RECEIVED=100, SRAM_WR_DATA_BEAT_WRITTEN=50, EXT_RD_DATA_BEAT_RECEIVED=30,
            EXT_WR_DATA_BEAT_WRITTEN=1)
STOCK = [dict(BEAT, ACTIVE=a) for a in (1000, 1010, 1004)]
EVENTS = [dict(BEAT, ACTIVE=a, MAC_ACTIVE=m, MAC_DPU_ACTIVE=m, AO_ACTIVE=200) for a, m in ((1002, 500), (1006, 502),
                                                                                            (1001, 501))]
ID = {v: k for k, v in __import__("mlek_counters").EVENT_ID.items()}


def rows(active=(1003, 1005, 1007), mac=(500, 501, 502), beats=None, ofm="0", valid="True"):
    b = dict(BEAT, **(beats or {}))
    out = []
    for rep, (a, m) in enumerate(zip(active, mac), start=3):
        vals = {35: a, 48: m, 51: m, 64: 200, 130: b["SRAM_RD_DATA_BEAT_RECEIVED"], 135: b["SRAM_WR_DATA_BEAT_WRITTEN"],
                386: b["EXT_RD_DATA_BEAT_RECEIVED"], 391: b["EXT_WR_DATA_BEAT_WRITTEN"]}
        out += [dict(rep=str(rep), ev_type=str(e), event_value=str(v), run_valid=valid, ofm_mismatch_count=ofm)
                for e, v in vals.items()]
    return out


class StockSource(unittest.TestCase):
    def test_reference_boots_when_no_capture(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            b = C.stock_boots(pathlib.Path(d), "kws_micronet_m")
            self.assertEqual([x["ACTIVE"] for x in b], [91431, 90915, 91501])   # mlek_board_reference.json B1-B3
            self.assertEqual(C.stock_boots(pathlib.Path(d), "rnnoise_INT8"), [])
            (pathlib.Path(d) / "stock" / "B1").mkdir(parents=True)
            (pathlib.Path(d) / "stock" / "B1" / "app_uart.raw").write_bytes(
                b"INFO - Profile for Inference:\r\nINFO - NPU ACTIVE: 7 cycles\r\n")
            self.assertEqual(C.stock_boots(pathlib.Path(d), "kws_micronet_m"), [{"ACTIVE": 7}])   # captures win


class Rules(unittest.TestCase):
    def test_all_equivalent(self):
        r = C.model(STOCK, EVENTS, rows())
        self.assertTrue(all(v == C.EQ for k, v in r.items() if k != "instrumented_build_inert"), r)
        self.assertTrue(r["instrumented_build_inert"])

    def test_each_metric_can_fail(self):
        self.assertEqual(C.model(STOCK, EVENTS, rows(ofm="2"))["M1_output"], C.NE)
        self.assertEqual(C.model(STOCK, EVENTS, rows(beats=dict(EXT_RD_DATA_BEAT_RECEIVED=31)))
                         ["M2_EXT_RD_DATA_BEAT_RECEIVED"], C.NE)
        self.assertEqual(C.model(STOCK, EVENTS, rows(active=(1040, 1041, 1042)))["M3_ACTIVE"], C.NE)
        self.assertEqual(C.model(STOCK, EVENTS, rows(mac=(600, 601, 602)))["M4_MAC_ACTIVE"], C.NE)

    def test_tolerance_is_the_larger_range(self):
        self.assertEqual(C.jitter([1000, 1010], [1015, 1016]), C.NE)    # diff 10.5 > max(10, 1)
        self.assertEqual(C.jitter([1000, 1010], [1014, 1016]), C.EQ)    # diff 10 <= 10
        self.assertEqual(C.jitter([1000, 1001], [990, 1030]), C.EQ)     # runner range 40 covers it
        self.assertEqual(C.exact([5, 5], [5]), C.EQ)
        self.assertEqual(C.exact([5, 6], [5]), C.NE)                     # MLEK itself not exact
        self.assertEqual(C.exact([5], [5, 6]), C.NE)
        self.assertEqual(C.exact([5, 6], [5, 6]), C.NE)                  # not one value on either side

    def test_missing_is_unproven(self):
        r = C.model([], [], rows())
        self.assertTrue(all(r[k] == C.UP for k in r if k.startswith(("M2", "M3", "M4"))))
        self.assertEqual(C.model(STOCK, EVENTS, [])["M1_output"], C.UP)
        self.assertEqual(C.model(STOCK, EVENTS, rows(valid="False"))["M1_output"], C.UP)
        self.assertEqual(C.model(STOCK, [], rows())["M4_MAC_ACTIVE"], C.UP)

    def test_instrumented_build_must_not_disturb(self):
        moved = [dict(e, EXT_RD_DATA_BEAT_RECEIVED=29) for e in EVENTS]
        r = C.model(STOCK, moved, rows())
        self.assertFalse(r["instrumented_build_inert"])
        self.assertEqual(r["M4_MAC_ACTIVE"], C.UP)
        slow = [dict(e, ACTIVE=e["ACTIVE"] + 100) for e in EVENTS]
        self.assertEqual(C.model(STOCK, slow, rows())["M4_AO_ACTIVE"], C.UP)

    def test_warmup_and_invalid_runs_are_not_counted(self):
        rs = rows() + [dict(rep="1", ev_type="35", event_value="9999", run_valid="True", ofm_mismatch_count="0")]
        self.assertEqual(C.runner_values([r for r in rs if int(r["rep"]) > C.WARMUP], "ACTIVE"), [1003, 1005, 1007])
        rs = rows() + [dict(rep="4", ev_type="35", event_value="9999", run_valid="False", ofm_mismatch_count="0")]
        self.assertEqual(sorted(C.runner_values(rs, "ACTIVE")), [1003, 1005, 1007])


if __name__ == "__main__":
    unittest.main()
