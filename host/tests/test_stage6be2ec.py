"""Stage 6B-E2E-C rules (evidence/stage6b/stage6be2ec/contract.md). Expected values typed by hand."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis"), str(REPO / "host/lib")]
import stage6be2ec as E  # noqa: E402


def summary():
    """A minimal E2E-B summary with the required values (fixture)."""
    def res(npu, mac, ao, wd, tr):
        return dict(status="VALID", metrics=dict(npu_active=npu, mac_active=mac, ao_active=ao, wd_active=wd), traffic=tr)
    t0 = dict(sram_rd_beats=25088.0, sram_rd_trans=1568.0, sram_wr_beats=9216.0, ext_rd_beats=27066.0,
              ext_rd_trans=10417.0, ext_wr_beats=7872.0)
    t3 = dict(sram_rd_beats=40832.0, sram_rd_trans=11192.0, sram_wr_beats=17088.0, ext_rd_beats=11322.0,
              ext_rd_trans=793.0, ext_wr_beats=0.0)
    return dict(verdicts={"x": 1}, results={
        "B0-L500": res(99044.0, 20736.0, 14974.5, 5900.0, dict(t0)), "B0-L1000": res(159122.5, 20736.0, 14921.0, 3571.0, dict(t0)),
        "B3-L500": res(60320.0, 20736.0, 14921.0, 5882.5, dict(t3)), "B3-L1000": res(72526.5, 20736.0, 14922.0, 3581.0, dict(t3))})


class Phase0(unittest.TestCase):
    def ok(self, s, same=True, diff=((28, 0, 1),)):
        return E.phase0_checks(s, same, {"verdicts": {"x": 1}}, list(diff))

    def test_pass(self):
        r = self.ok(summary())
        self.assertTrue(r["ok"], r["checks"])

    def mutate(self, path, value):
        s = summary()
        d = s
        for p in path[:-1]:
            d = d[p]
        d[path[-1]] = value
        return self.ok(s)["checks"]

    def test_each_check(self):
        self.assertFalse(self.ok(summary(), same=False)["checks"]["summary_bytes"])
        self.assertFalse(E.phase0_checks(summary(), True, {"verdicts": {"x": 2}}, [(28, 0, 1)])["checks"]["verdicts"])
        self.assertFalse(self.mutate(["results", "B3-L500", "metrics", "npu_active"], 60321.0)["B3_npu"])
        self.assertFalse(self.mutate(["results", "B0-L1000", "metrics", "npu_active"], 159122.0)["B0_le"])
        self.assertFalse(self.mutate(["results", "B3-L1000", "metrics", "mac_active"], 20737.0)["B3_mac"])
        self.assertFalse(self.mutate(["results", "B3-L1000", "traffic", "ext_rd_trans"], 794.0)["B3_ext"])
        c = self.mutate(["results", "B0-L500", "traffic", "ext_rd_beats"], 27067.0)
        self.assertFalse(c["removed"])
        self.assertFalse(c["conservation"])
        self.assertFalse(self.mutate(["results", "B3-L500", "traffic", "sram_wr_beats"], 17089.0)["conservation"])
        self.assertFalse(self.mutate(["results", "B3-L500", "traffic", "sram_rd_trans"], 11193.0)["conservation"])
        self.assertFalse(self.mutate(["results", "B3-L500", "metrics", "ao_active"], 14974.5 * 1.0101)["ao_wd_invariant"])
        self.assertTrue(self.mutate(["results", "B3-L500", "metrics", "ao_active"], 14974.5 * 1.0099)["ao_wd_invariant"])
        self.assertFalse(self.mutate(["results", "B3-L1000", "metrics", "wd_active"], 3571.0 * 0.98)["ao_wd_invariant"])
        self.assertFalse(self.mutate(["results", "B0-L1000", "status"], "UNSTABLE")["outputs_valid"])
        self.assertFalse(self.ok(summary(), diff=[(28, 0, 1), (40, 1, 2)])["checks"]["command_stream_identical"])
        self.assertFalse(self.ok(summary(), diff=[None])["checks"]["command_stream_identical"])

    def test_removed_transactions_and_ok(self):
        c = self.mutate(["results", "B0-L500", "traffic", "ext_rd_trans"], 10418.0)
        self.assertFalse(c["removed"])
        s = summary()
        s["results"]["B3-L500"]["metrics"]["mac_active"] = 1.0
        self.assertFalse(self.ok(s)["ok"])

    def test_real_rerun_cleans_up(self):
        t = pathlib.Path(tempfile.gettempdir())
        before = len(list(t.glob("tmp*")))
        p = E.phase0()
        self.assertEqual(len(list(t.glob("tmp*"))), before)
        self.assertTrue(p["ok"], p["checks"])
        self.assertEqual(p["label"], "POSTHOC_DIAGNOSTIC")


class Phase1(unittest.TestCase):
    def test_event_status(self):
        trm = {384, 387, 160}
        self.assertEqual(E.event_status(53, trm, {}), "RESERVED")
        self.assertEqual(E.event_status(387, trm, {387: ["COUNTED_NONZERO", "COUNTED_NONZERO"]}), "VERIFIED_ON_FI101")
        self.assertEqual(E.event_status(387, trm, {387: ["COUNTED_NONZERO", "INCONSISTENT"]}), "INCONSISTENT_ON_FI101")
        self.assertEqual(E.event_status(160, trm, {}), "TRM_ONLY_UNVERIFIED")
        self.assertEqual(E.event_status(384, trm, {384: ["COUNTED_ZERO"]}), "TRM_ONLY_UNVERIFIED")

    def test_channel_status(self):
        w = {"rd_weights", "rd_ifm"}
        self.assertEqual(E.channel_status("rd_weights", w), "READ_FILTER_VERIFIED")
        self.assertEqual(E.channel_status("rd_cmd", w), "UNVERIFIED")
        self.assertEqual(E.channel_status("wr_ofm", w | {"wr_ofm"}), "WRITE_NOT_INTERPRETABLE")

    def test_real_files(self):
        p = E.pmu_capability()
        self.assertEqual(p["events"][387]["status"], "VERIFIED_ON_FI101")
        self.assertEqual(p["events"][398]["status"], "INCONSISTENT_ON_FI101")
        self.assertEqual(p["events"][160]["status"], "TRM_ONLY_UNVERIFIED")
        self.assertEqual(p["events"][53]["status"], "RESERVED")
        self.assertEqual(p["channels"]["rd_weights"], "READ_FILTER_VERIFIED")
        self.assertEqual(p["channels"]["rd_mem2mem"], "READ_FILTER_VERIFIED")
        self.assertEqual(p["channels"]["rd_cmd"], "UNVERIFIED")
        self.assertEqual(p["channels"]["rd_scale_bias"], "UNVERIFIED")
        self.assertFalse(p["driver_runner_pmcaxi"])
        self.assertTrue(p["legacy_readback"])
        self.assertEqual(p["items"]["9 driver runner set/readback"]["status"], "NOT_IMPLEMENTED")


class Phase2(unittest.TestCase):
    def test_cell_row(self):
        r = E.cell_row("X", 500, 50000, 20736, {386: 1000, 384: 100, 130: 64, 128: 8, 391: 0})
        self.assertEqual((r["ext_beats_per_trans"], r["ext_trans_per_knpu"], r["sram_beats_per_trans"]), (10.0, 2.0, 8.0))
        r = E.cell_row("X", 500, 50000, 20736, {"386": 1000, "384": 0, "130": 0, "128": 0, "391": 0})
        self.assertIsNone(r["ext_beats_per_trans"])

    def test_pair(self):
        row = lambda npu, rd, tr: dict(npu_active=npu, ext_rd_beats=rd, ext_rd_trans=tr)
        a = {500: row(100, 1000, 500), 1000: row(160, 1000, 500)}
        b = {500: row(60, 400, 100), 1000: row(70, 400, 100)}
        p = E.pair(a, b)
        self.assertEqual((p["removed_beats"], p["removed_trans"], p["removed_beats_per_trans"]), (600, 400, 1.5))
        self.assertEqual((p["le_from"], p["le_to"], p["delta_le"], p["delta_le_per_removed_trans"]), (60, 10, 50, 0.125))
        self.assertEqual(p["residual_le_per_trans"], 0.1)
        self.assertTrue(p["same_traffic_both_latencies"])
        b[1000] = row(70, 401, 100)
        self.assertFalse(E.pair(a, b)["same_traffic_both_latencies"])

    def test_real_transactions(self):
        tx = E.transactions(summary())
        self.assertEqual(tx["rows"]["W0-P1"][500]["ext_rd_trans"], 788.0)
        self.assertEqual(tx["pairs"]["B0->B3"]["removed_trans"], 9624.0)
        self.assertEqual(tx["weight_path_only"]["B3"]["le"], 12206.5)

    def test_vela_ops(self):
        v = E.vela_ops()
        self.assertEqual([o["op"] for o in v["L500"]], [21562, 24290, 7200])
        self.assertEqual([o["op"] for o in v["L1000"]], [43124, 32818, 7200])


class Phase3(unittest.TestCase):
    def test_residual(self):
        r = E.residual_channels(11322.0)
        self.assertEqual(r["channel_bytes"], dict(rd_weights=174752, rd_scale_bias=5760, rd_cmd=628, rd_ifm=0, rd_mem2mem=0))
        self.assertEqual(r["expected_beats"], 11321.25)
        self.assertEqual(r["difference_bytes"], 12.0)
        self.assertEqual(r["region0_tensors"], ["SCALE", "WEIGHT"])
        self.assertEqual(r["ext_regions_b3"], [0])


class Phase4(unittest.TestCase):
    REC = dict(arena_base=0x31076770, base0=0x70000420, base_size0=0x16090)

    def test_sram_copy(self):
        f = E.sram_copy_fits(0x31076770, 0x70000420, 0x16090)
        self.assertEqual((f["copy_base"], f["copy_end"], f["fits"]), (0x31280420, 0x312964B0, True))
        self.assertFalse(E.sram_copy_fits(0x31076770, 0x70000420, 0x180000)["fits"])
        self.assertTrue(E.sram_copy_fits(0x31076770, 0x70000420, 0x17FBE0)["fits"])     # ends exactly at the limit

    def test_status_and_discriminating(self):
        self.assertEqual(E.method_status({"a": "VERIFIED_SOURCE", "b": "BOARD_CHECK_REQUIRED"}), "AVAILABLE")
        self.assertEqual(E.method_status({"a": "VERIFIED_SOURCE", "b": "FAILS"}), "UNAVAILABLE")
        self.assertTrue(E.discriminating({"H-R1": "x", "H-R2": "y"}))
        self.assertFalse(E.discriminating({"H-R1": "x", "H-R2": "x"}))
        self.assertFalse(E.discriminating({"H-R2": "y"}))

    def base(self, **kw):
        m = dict(controlled_variable="v", prereqs={"i": "VERIFIED_BOARD", "x": "BOARD_CHECK_REQUIRED"}, instrumentation=["i"],
                 predictions={"H-R1": "a", "H-R2": "b"}, needs_new_data=True, budget=(5, 50))
        m.update(kw)
        return m

    def test_gate(self):
        self.assertTrue(E.gate(self.base())["passed"])
        self.assertFalse(E.gate(self.base(controlled_variable=None))["passed"])
        self.assertFalse(E.gate(self.base(predictions={"H-R1": "a", "H-R2": "a"}))["passed"])
        self.assertFalse(E.gate(self.base(prereqs={"i": "BOARD_CHECK_REQUIRED"}))["passed"])
        self.assertTrue(E.gate(self.base(prereqs={"i": "VERIFIED_SOURCE"}))["passed"])
        self.assertFalse(E.gate(self.base(needs_new_data=False))["passed"])
        self.assertFalse(E.gate(self.base(budget=(6, 50)))["passed"])
        self.assertFalse(E.gate(self.base(budget=(5, 51)))["passed"])
        self.assertFalse(E.gate(self.base(prereqs={"i": "VERIFIED_BOARD", "x": "FAILS"}))["passed"])

    def ms(self, a_pass, b_pass, a_disc=True, b_disc=True, a_checks=1, b_checks=2):
        g = lambda p: dict(passed=p)
        return dict(A=dict(gate=g(a_pass), discriminating=a_disc, board_checks=a_checks),
                    B=dict(gate=g(b_pass), discriminating=b_disc, board_checks=b_checks))

    def test_verdict(self):
        self.assertEqual(E.verdict(False, self.ms(True, True)), dict(verdict="INVALID", selected=None))
        self.assertEqual(E.verdict(True, self.ms(True, True)), dict(verdict="READY_FOR_TARGETED_BOARD_REVIEW", selected="A"))
        self.assertEqual(E.verdict(True, self.ms(True, True, a_checks=2))["selected"], "B")
        self.assertEqual(E.verdict(True, self.ms(False, True))["selected"], "B")
        self.assertEqual(E.verdict(True, self.ms(False, False, False, False))["verdict"], "MECHANISM_NOT_IDENTIFIABLE")
        self.assertEqual(E.verdict(True, self.ms(False, False, False, True))["verdict"], "STATIC_CHARACTERIZATION_COMPLETE")

    def test_methods_real(self):
        ms = E.methods(E.pmu_capability(), self.REC)
        self.assertFalse(ms["A"]["discriminating"])
        self.assertTrue(ms["B"]["discriminating"])
        self.assertEqual(ms["B"]["status"], "AVAILABLE")
        self.assertEqual(ms["A"]["prereqs"]["rd_cmd / rd_scale_bias filter"], "BOARD_CHECK_REQUIRED")
        self.assertEqual(ms["A"]["prereqs"]["driver runner set/readback"], "BOARD_CHECK_REQUIRED")
        big = dict(self.REC, base_size0=0x180000)
        self.assertEqual(E.methods(E.pmu_capability(), big)["B"]["status"], "UNAVAILABLE")

    def test_constants(self):
        self.assertEqual((E.LOW, E.HIGH, E.BUDGET, E.INVARIANT_REL), (0.25, 0.75, (5, 50), 0.01))
        self.assertEqual(E.REMOVED, (15744.0, 9624.0))
        self.assertEqual(E.REQUIRED["B3"]["le"], 12206.5)


class Run(unittest.TestCase):
    def test_run_writes_and_cleans(self):
        with tempfile.TemporaryDirectory() as d:
            t = pathlib.Path(tempfile.gettempdir())
            before = len(list(t.glob("tmp*")))
            s = E.run(d)
            self.assertEqual(len(list(t.glob("tmp*"))), before)
            self.assertTrue((pathlib.Path(d) / "stage6be2ec_summary.json").exists())
            self.assertIn(s["final"]["verdict"], ("READY_FOR_TARGETED_BOARD_REVIEW", "STATIC_CHARACTERIZATION_COMPLETE",
                                                   "MECHANISM_NOT_IDENTIFIABLE", "INVALID"))


if __name__ == "__main__":
    unittest.main()
