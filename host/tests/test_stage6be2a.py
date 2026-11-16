"""Stage 6B-E2A rules (evidence/stage6b/stage6be2a/contract.md). Expected values are typed by hand from the contract and the
Vela 5.0.0 source, never read back from the module."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import stage6be2a as E  # noqa: E402

DRAM = dict(clock_scale=0.75, ports_used=2, burst_length=128, read_latency=500, write_latency=250, max_reads=64, max_writes=32)
SRAM = dict(clock_scale=1.0, ports_used=2, burst_length=64, read_latency=32, write_latency=32, max_reads=8, max_writes=8)
CAPS = dict(ta_sram_rlatency=32, ta_sram_wlatency=32, ta_ext_rlatency=500, ta_ext_wlatency=250, ta_sram_maxr=8, ta_sram_maxw=8,
            ta_ext_maxr=0, ta_ext_maxw=32, axi_sram=134923, axi_ext=139071, ta_sram_bwcap=4000, ta_sram_pulse_on=3999,
            ta_sram_pulse_off=1, ta_ext_bwcap=3750, ta_ext_pulse_on=4000, ta_ext_pulse_off=1000, npu_config=536880410,
            fast_size=393216, ta_sram_mode=1, ta_ext_mode=1)
BURSTS = dict(sram_read=[60.0, 64.0], sram_write=[64.0], ext_read=[100.0, 128.0])


def status(rows, item):
    return next(r["status"] for r in rows if r["item"] == item)


class ChannelBW(unittest.TestCase):
    def test_dram(self):
        self.assertAlmostEqual(E.channel_bw(DRAM, "IFM"), 6.5536)        # 128 * 32 / 500 * 0.8
        self.assertAlmostEqual(E.channel_bw(DRAM, "Write"), 20.97152)    # 128 * 51.2 / 250 * 0.8
        self.assertAlmostEqual(E.channel_bw(DRAM, "Weight"), 10.6496)    # 128 * 52 / 500 * 0.8
        self.assertAlmostEqual(E.channel_bw(DRAM, "Scale"), 0.4096)      # 128 * 2 / 500 * 0.8

    def test_sram(self):
        self.assertAlmostEqual(E.channel_bw(SRAM, "IFM"), 20.48)         # 64 * 12.8 / 32 * 0.8
        self.assertAlmostEqual(E.channel_bw(SRAM, "Write"), 20.48)

    def test_bandwidth_cap(self):
        fast = dict(SRAM, read_latency=1, write_latency=1)
        self.assertAlmostEqual(E.channel_bw(fast, "IFM"), 32.0)          # 1.0 * 16 * 2


class MacCycles(unittest.TestCase):
    def test_g12(self):            # 16x16x276, blocks 8x16x64, ublock 2x2x32: 2560 * 9 + 1250
        self.assertEqual(E.mac_cycles_src([16, 16, 276], [16, 16, 276], [8, 16, 64], [8, 16, 64], [2, 2, 32]), 24290)

    def test_delay_single_ublock(self):   # 130 per block, one block, AO = bias 625
        self.assertEqual(E.mac_cycles_src([2, 2, 16], [2, 2, 32], [2, 2, 16], [2, 2, 32], [2, 2, 32]), 755)

    def test_block_clipped_to_ofm(self):   # blocks 4x4 on a 2x2 OFM are clipped: same as the single-ublock case
        self.assertEqual(E.mac_cycles_src([2, 2, 16], [2, 2, 32], [4, 4, 16], [4, 4, 32], [2, 2, 32]), 755)

    def test_integer_depth_division_and_ao_compute(self):   # 20 // 8 = 2: 256; AO = ceil(0.0625 * 16384) = 1024
        self.assertEqual(E.mac_cycles_src([16, 32, 20], [16, 32, 32], [16, 32, 24], [16, 32, 32], [2, 2, 32]), 1280)


class Forms(unittest.TestCase):
    OPS = [dict(npu=10, sram=4, dram=20), dict(npu=5, sram=6, dram=1)]

    def test_values(self):
        f = E.forms(self.OPS, 2.0, 0.5)
        self.assertEqual((f["F0"], f["F1"], f["F2"], f["F3"], f["F4"]), (26, 41, 31, 46, 22))

    def test_f4_needs_ratios(self):
        self.assertIsNone(E.forms(self.OPS, None, 0.5)["F4"])

    def test_rel_err(self):
        self.assertEqual(E.rel_err(150, 100), 0.5)
        self.assertIsNone(E.rel_err(150, None))
        self.assertIsNone(E.rel_err(150, 0))


class M2(unittest.TestCase):
    def test_holds(self):
        self.assertTrue(E.m2(dict(A=[0.1, -0.2, 0.05], B=[0.1, -0.15, 0.0, 0.12, 0.05]), "F3")["holds"])

    def test_too_few_b(self):
        self.assertFalse(E.m2(dict(A=[0.1], B=[0.1, 0.1, 0.1, 0.1]), "F3")["holds"])

    def test_one_b_outside(self):
        self.assertFalse(E.m2(dict(A=[0.1], B=[0.1, 0.1, 0.1, 0.1, -0.16]), "F3")["holds"])

    def test_a_median(self):
        self.assertFalse(E.m2(dict(A=[0.2, -0.3, 0.1], B=[0.1] * 5), "F3")["holds"])


class Audit(unittest.TestCase):
    def test_axi_fields(self):
        self.assertEqual(E.axi_fields(0x21F3F), dict(max_reads=64, max_writes=32, max_beats=2))
        self.assertEqual(E.axi_fields(0x20F0B), dict(max_reads=12, max_writes=16, max_beats=2))
        self.assertEqual(E.axi_fields(0x3F01)["max_writes"], 32)      # bits 13-15 are reserved

    def test_outstanding(self):
        self.assertEqual(E.effective_outstanding(0, 64), 64)
        self.assertEqual(E.effective_outstanding(8, 12), 8)

    def test_c4(self):
        self.assertEqual(E.c4_bandwidth(3750, 4000, 1000, 24), "UNKNOWN")       # 6, 12, 12, 24
        self.assertEqual(E.c4_bandwidth(100, 4000, 1000, 24), "MISMATCH_VERIFIED")
        self.assertEqual(E.c4_bandwidth(10000, 1, 0, 24), "MATCH")
        self.assertEqual(E.c4_bandwidth(1000, 1000, 0, 12), "UNKNOWN")         # 8 < 12 <= 16, 16, 32
        self.assertEqual(E.c4_bandwidth(1000, 1000, 0, 20), "UNKNOWN")         # 8, 16 < 20 <= 32

    def test_c5(self):
        self.assertEqual(E.c5_burst([150, 160], 128), "MISMATCH_VERIFIED")
        self.assertEqual(E.c5_burst([64, 100], 128), "MATCH")
        self.assertEqual(E.c5_burst([150, 100], 128), "UNKNOWN")
        self.assertEqual(E.c5_burst([], 128), "UNKNOWN")
        self.assertEqual(E.c5_burst([140.8], 128), "MATCH")

    def test_profile1(self):
        r = E.audit(CAPS, BURSTS)
        for item in ("C1 latency Sram", "C1 latency Dram", "C2 outstanding Sram", "C2 outstanding Dram", "C3 ports", "C7 SRAM size",
                     "C5 burst sram_read", "C5 burst ext_read"):
            self.assertEqual(status(r, item), "MATCH", item)
        self.assertEqual(status(r, "C4 bandwidth Sram"), "UNKNOWN")
        self.assertEqual(status(r, "C4 bandwidth Dram"), "UNKNOWN")
        self.assertFalse(any(x["status"] == "MISMATCH_VERIFIED" for x in r))

    def test_mismatches(self):
        self.assertEqual(status(E.audit(dict(CAPS, ta_ext_rlatency=400), BURSTS), "C1 latency Dram"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(dict(CAPS, ta_ext_maxr=16), BURSTS), "C2 outstanding Dram"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(dict(CAPS, ta_sram_maxw=4), BURSTS), "C2 outstanding Sram"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(dict(CAPS, npu_config=536880410 & ~0x400), BURSTS), "C3 ports"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(dict(CAPS, fast_size=65536), BURSTS), "C7 SRAM size"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(CAPS, dict(BURSTS, ext_read=[256.0, 250.0])), "C5 burst ext_read"), "MISMATCH_VERIFIED")
        self.assertEqual(status(E.audit(CAPS, dict(BURSTS, sram_write=[128.0])), "C5 burst sram_write"), "MISMATCH_VERIFIED")


class Hypotheses(unittest.TestCase):
    def test_spearman_ties(self):
        self.assertAlmostEqual(E.spearman([1, 2, 2, 3], [1, 2, 3, 4]), 4.5 / 22.5 ** 0.5)
        self.assertIsNone(E.spearman([1, 2], [1, 2]))

    def test_h1(self):
        self.assertEqual(E.h1([0.1, 0.12, 0.2], [0.9, 0.9, 0.9], [False]), "SUPPORTED_PATTERN")
        self.assertEqual(E.h1([0.5, 0.6], [0.55, 0.62], [True, True]), "CONTRADICTED")
        self.assertEqual(E.h1([0.5, 0.6], [0.55, 0.62], [True, False]), "NOT_DISTINGUISHABLE")
        self.assertEqual(E.h1([0.5, 0.6], [0.8, 0.9], [True, True]), "NOT_DISTINGUISHABLE")

    def test_h2(self):
        hold = lambda f: {k: dict(holds=k == f) for k in ("F1", "F2", "F3", "F4")}
        over_all = {f: dict(A=[True, True], B=[True, False]) for f in ("F1", "F2", "F3")}
        self.assertEqual(E.h2(hold("F3"), over_all), "SUPPORTED_PATTERN")
        self.assertEqual(E.h2(hold("F4"), over_all), "CONTRADICTED")
        self.assertEqual(E.h2(hold("F4"), dict(over_all, F2=dict(A=[False, False], B=[True]))), "NOT_DISTINGUISHABLE")

    def test_h3(self):
        self.assertEqual(E.h3_group([10, 20, 30, 40], [1, 2, 3, 4]), "CONTRADICTED")
        self.assertEqual(E.h3_group([100, 101, 99, 100.5], [1, 2, 3, 4]), "SUPPORTED_PATTERN")
        self.assertEqual(E.h3_group([10, 40, 20, 30], [1, 2, 3, 4]), "NOT_DISTINGUISHABLE")   # rho 0.4
        self.assertEqual(E.h3_group([10, 200, 5, 100], [1, 2, 3, 4]), "NOT_DISTINGUISHABLE")  # rho 0, CV large
        self.assertEqual(E.h3_group([100, 101, 99, 102], [1, 2, 3, 4]), "NOT_DISTINGUISHABLE")  # rho 0.4, CV small
        self.assertEqual(E.h3("CONTRADICTED", "CONTRADICTED"), "CONTRADICTED")
        self.assertEqual(E.h3("CONTRADICTED", "SUPPORTED_PATTERN"), "NOT_DISTINGUISHABLE")

    def test_h4(self):
        self.assertEqual(E.h4(0.9, 0.5), dict(status="NOT_DISTINGUISHABLE", pattern_difference=True))
        self.assertEqual(E.h4(0.9, 0.7), dict(status="NOT_DISTINGUISHABLE", pattern_difference=False))
        self.assertEqual(E.h4(0.9, 0.6), dict(status="NOT_DISTINGUISHABLE", pattern_difference=True))   # 0.30 > 0.25


class Verdict(unittest.TestCase):
    M1 = dict(M1a=True, M1b=True, M1c=True)
    HOLD = {"F3": dict(holds=True)}
    NONE = {"F3": dict(holds=False)}
    MIS = [dict(status="MISMATCH_VERIFIED")]
    OK = [dict(status="MATCH"), dict(status="UNKNOWN")]

    def test_order(self):
        self.assertEqual(E.verdict(self.M1, self.HOLD, self.MIS, True), "COST_MODEL_MECHANISM_IDENTIFIED")
        self.assertEqual(E.verdict(dict(self.M1, M1c=False), self.HOLD, self.MIS, True), "CONFIGURATION_DISCREPANCY_IDENTIFIED")
        self.assertEqual(E.verdict(dict(self.M1, M1a=False), self.HOLD, self.OK, True), "CAUSE_UNRESOLVED")
        self.assertEqual(E.verdict(dict(self.M1, M1b=False), self.HOLD, self.OK, True), "CAUSE_UNRESOLVED")
        self.assertEqual(E.verdict(self.M1, self.NONE, self.OK, True), "CAUSE_UNRESOLVED")
        self.assertEqual(E.verdict(self.M1, self.HOLD, self.OK, False), "NOT_JUDGED (integrity)")


class Sensitivity(unittest.TestCase):
    BASE = dict(ok=True, cms_sha256="a", const_sha256="b", arena_size=1, fast_size=2, inputs=[[0, 1]], outputs=[[1, 1]])

    def test_classes(self):
        self.assertEqual(E.sensitivity_class(self.BASE, dict(self.BASE)), "ESTIMATOR_ONLY_COMPARABLE")
        for k, v in (("cms_sha256", "x"), ("const_sha256", "x"), ("arena_size", 9), ("fast_size", 9), ("inputs", []), ("outputs", [])):
            self.assertEqual(E.sensitivity_class(self.BASE, dict(self.BASE, **{k: v})), "COMPILE_CHANGED", k)
        self.assertEqual(E.sensitivity_class(self.BASE, dict(self.BASE, ok=False)), "NOT_COMPARABLE")
        self.assertEqual(E.sensitivity_class(self.BASE, dict(ok=True)), "NOT_COMPARABLE")


class M1(unittest.TestCase):
    def compile(self, mac="24290", total="30", op_total="20", traversal="DepthFirst", kx="1"):
        perf = [dict(id="1", operator="Conv2D", op_cycles=op_total, npu_cycles="20", Sram_ac="5", Dram_ac="12", lutram_ac="0"),
                dict(id="2", operator="Add", op_cycles="10", npu_cycles="3", Sram_ac="10", Dram_ac="0", lutram_ac="0")]
        dbg = [dict(id="1", ifm_shape_h="16", ifm_shape_w="16", ifm_shape_c="276", ofm_shape_h="16", ofm_shape_w="16",
                    ofm_shape_c="276", kernel_size_x=kx, kernel_size_y="1")]
        main = [dict(id="1", mac_cycles=mac, traversal=traversal, ifm_block_h="8", ifm_block_w="16", ifm_block_c="64",
                     ofm_block_h="8", ofm_block_w="16", ofm_block_c="64", ofm_ublock_h="2", ofm_ublock_w="2", ofm_ublock_c="32")]
        return dict(summary=dict(cycles_total=total), db=dict(perf=perf, perf_debug=dbg, perf_debug_main=main))

    def test_pass(self):
        m = E.m1_checks(dict(s=self.compile()))
        self.assertEqual((m["M1a"], m["M1b"], m["M1c"], m["M1c_n"]), (True, True, True, 1))

    def test_op_not_max(self):
        self.assertFalse(E.m1_checks(dict(s=self.compile(op_total="19", total="29")))["M1a"])

    def test_total_not_sum(self):
        self.assertFalse(E.m1_checks(dict(s=self.compile(total="31")))["M1b"])

    def test_mac_off_by_two(self):
        self.assertFalse(E.m1_checks(dict(s=self.compile(mac="24292")))["M1c"])
        self.assertTrue(E.m1_checks(dict(s=self.compile(mac="24291")))["M1c"])

    def test_scope(self):
        self.assertEqual(E.m1_checks(dict(s=self.compile(traversal="PartKernel")))["M1c_n"], 0)
        self.assertEqual(E.m1_checks(dict(s=self.compile(kx="3")))["M1c_n"], 0)
        self.assertFalse(E.m1_checks(dict(s=self.compile(traversal="PartKernel")))["M1c"])


if __name__ == "__main__":
    unittest.main()
