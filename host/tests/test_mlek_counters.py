import sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis")); sys.path.insert(0, str(REPO / "host" / "container"))
import mlek_counters as C
import mlek_profiler_events as P

E = REPO / "evidence" / "mobilenet_ofm" / "app_uart.raw"
TEXT = E.read_bytes().decode("ascii", "replace").replace("\r", "")


class Counters(unittest.TestCase):
    def test_real_capture(self):
        # values as printed in evidence/mobilenet_ofm/app_uart.raw
        self.assertEqual(C.counters(TEXT), {"ACTIVE": 1447736, "SRAM_RD_DATA_BEAT_RECEIVED": 672948,
                                            "SRAM_WR_DATA_BEAT_WRITTEN": 401443, "EXT_RD_DATA_BEAT_RECEIVED": 301217,
                                            "EXT_WR_DATA_BEAT_WRITTEN": 47887, "IDLE": 5936, "TOTAL": 1453672})

    def test_instrumented_names_and_refusals(self):
        t = ("INFO - Profile for Inference:\nINFO - NPU ACTIVE: 10 cycles\nINFO - NPU ETHOSU_PMU_MAC_ACTIVE: 4 cycles\n"
             "INFO - NPU ETHOSU_PMU_AO_ACTIVE: 3 cycles\nINFO - output tensors post inference\nINFO - NPU ACTIVE: 99 cycles\n")
        self.assertEqual(C.counters(t), {"ACTIVE": 10, "MAC_ACTIVE": 4, "AO_ACTIVE": 3})
        self.assertEqual(set(C.EVENT_ID) >= {"MAC_ACTIVE", "AO_ACTIVE", "ACTIVE"}, True)
        with self.assertRaises(ValueError):
            C.counters("no profile here")
        with self.assertRaises(ValueError):
            C.counters(t + t)                                            # two profiles
        with self.assertRaises(ValueError):
            C.counters("INFO - Profile for Inference:\nINFO - NPU ACTIVE: 1 cycles\nINFO - NPU ACTIVE: 2 cycles\n")
        with self.assertRaises(ValueError):
            C.counters("INFO - Profile for Inference:\nINFO - NPU IDLE: 1 cycles\n")


C_FIXTURE = ("    counters->npu_evt_counters[4].event_type = ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN;\n"
             "    counters->npu_evt_counters[4].unit       = unit_beats;\n"
             "#endif /* defined(ETHOSU55) || defined(ETHOSU65) */\n")
H_FIXTURE = ("#elif defined(ETHOSU85)\n" + P.H_OLD + "#endif\n")


class ProfilerPatch(unittest.TestCase):
    def test_adds_three_counters_after_the_five(self):
        c = P.generate(C_FIXTURE, P.C_OLD, P.c_new(), "c")
        for i, ev in ((5, "ETHOSU_PMU_MAC_ACTIVE;"), (6, "ETHOSU_PMU_MAC_DPU_ACTIVE;"), (7, "ETHOSU_PMU_AO_ACTIVE;")):
            self.assertIn(f"counters->npu_evt_counters[{i}].event_type = {ev}", c)
        self.assertIn("ETHOSU_PMU_CNT6_Msk", c); self.assertIn("ETHOSU_PMU_CNT8_Msk", c)
        self.assertLess(c.index("npu_evt_counters[4].unit"), c.index("npu_evt_counters[5]"))
        self.assertTrue(c.rstrip().endswith("#endif /* defined(ETHOSU55) || defined(ETHOSU65) */"))
        h = P.generate(H_FIXTURE, P.H_OLD, P.H_NEW, "h")
        self.assertIn("ETHOSU_USED_PMU_NCOUNTERS   (8U)", h)

    def test_refuses_missing_or_double_anchor(self):
        with self.assertRaises(SystemExit):
            P.generate(C_FIXTURE.replace("unit_beats", "unit_cycles"), P.C_OLD, P.c_new(), "c")
        with self.assertRaises(SystemExit):
            P.generate(H_FIXTURE * 2, P.H_OLD, P.H_NEW, "h")

    def test_apply_refuses_a_tree_that_is_not_the_original(self):
        with tempfile.TemporaryDirectory() as d:
            for f in P.ORIGINAL:
                (pathlib.Path(d) / f).parent.mkdir(parents=True, exist_ok=True)
                (pathlib.Path(d) / f).write_text("not the original")
            with self.assertRaises(SystemExit):
                P.apply(pathlib.Path(d))


if __name__ == "__main__":
    unittest.main()
