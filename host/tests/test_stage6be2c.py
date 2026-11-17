"""Stage 6B-E2C rules (evidence/stage6b/stage6be2c/contract.md) and the full register decoder. Expected values by hand."""
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms_full  # noqa: E402
import stage6be2c as E  # noqa: E402


def cmd0(op, param):
    return struct.pack("<I", (param << 16) | op)


def cmd1(op, param, payload):
    return struct.pack("<II", (param << 16) | (1 << 14) | op, payload)


class Decoder(unittest.TestCase):
    def test_kernel_state(self):
        # IFM_DEPTH_M1 (260) = 275, IFM_BASE0 (cmd1 0) = 0x100, DMA_START (16), CONV (2), then OFM_REGION (287) = 2, CONV
        s = cmd0(260, 275) + cmd1(0, 0, 0x100) + cmd1(48, 0, 64) + cmd0(16, 0) + cmd0(2, 0) + cmd0(287, 2) + cmd0(2, 0)
        k = cms_full.kernels(s)
        self.assertEqual(len(k), 2)
        self.assertEqual(k[0]["regs"]["NPU_SET_IFM_DEPTH_M1"], 275)
        self.assertEqual(k[0]["regs"]["NPU_SET_IFM_BASE0"], 0x100)
        self.assertEqual(len(k[0]["dma"]), 1)
        self.assertNotIn("NPU_SET_OFM_REGION", k[0]["regs"])
        self.assertEqual(k[1]["regs"]["NPU_SET_OFM_REGION"], 2)
        self.assertEqual(k[1]["regs"]["NPU_SET_IFM_DEPTH_M1"], 275)      # state carries over
        self.assertEqual(k[1]["dma"], [])

    def test_cmd1_high_part(self):      # the 16-bit cmd1 parameter is the high part of the 48-bit value
        k = cms_full.kernels(cmd1(0, 1, 0x100) + cmd0(2, 0))
        self.assertEqual(k[0]["regs"]["NPU_SET_IFM_BASE0"], (1 << 32) | 0x100)

    def test_categories(self):
        for n, c in (("NPU_SET_IFM_BASE0", "ADDRESS"), ("NPU_SET_OFM_REGION", "ADDRESS"), ("NPU_SET_WEIGHT_BASE", "ADDRESS"),
                     ("NPU_SET_SCALE_REGION", "ADDRESS"), ("NPU_SET_DMA0_SRC", "ADDRESS"), ("NPU_SET_DMA0_DST_REGION", "ADDRESS"),
                     ("NPU_SET_IFM_STRIDE_C", "LAYOUT"), ("NPU_SET_OFM_PRECISION", "LAYOUT"), ("NPU_SET_IFM_PRECISION", "LAYOUT"),
                     ("NPU_SET_BLOCKDEP", "DEPENDENCY"), ("NPU_SET_WEIGHT_LENGTH", "COMPUTE"), ("NPU_SET_OFM_BLK_DEPTH_M1", "COMPUTE"),
                     ("NPU_SET_ACTIVATION", "COMPUTE"), ("NPU_SET_DMA0_LEN", "COMPUTE"), ("NPU_SET_IFM_ZERO_POINT", "COMPUTE")):
            self.assertEqual(cms_full.category(n), c, n)

    def test_diff(self):
        a = dict(NPU_SET_IFM_BASE0=1, NPU_SET_BLOCKDEP=3, NPU_SET_ACTIVATION=0)
        b = dict(NPU_SET_IFM_BASE0=2, NPU_SET_BLOCKDEP=3, NPU_SET_ACTIVATION=0, NPU_SET_IFM_STRIDE_X=1)
        self.assertEqual(cms_full.diff(a, b), dict(ADDRESS=["NPU_SET_IFM_BASE0"], LAYOUT=["NPU_SET_IFM_STRIDE_X"]))


def facts(regs, mem=("Dram", "Dram"), ops=("Conv2D",), wsha="w"):
    perf = [dict(id=str(i), operator=o) for i, o in enumerate(ops)]
    cid = str(ops.index("Conv2D"))
    kern = [dict(kind="CONV", regs=regs)]
    return dict(ok=True, perf=perf, perf_debug=[dict(id=cid, ifm_memory=mem[0], ofm_memory=mem[1])],
                kernels=kern, streams=[dict(WEIGHT=dict(length=10, const_sha256=wsha))],
                main=[dict(id=cid, ofm_ublock_h="2", ofm_ublock_w="2", ofm_ublock_c="32", ifm_block_c="64")])


R = dict(NPU_SET_IFM_BASE0=0, NPU_SET_IFM_PRECISION=0, NPU_SET_ACTIVATION=0, NPU_SET_BLOCKDEP=0,
         NPU_SET_OFM_HEIGHT_M1=15, NPU_SET_OFM_WIDTH_M1=15, NPU_SET_OFM_DEPTH_M1=275, NPU_SET_IFM_DEPTH_M1=275)


class Classes(unittest.TestCase):
    def test_placement(self):
        a, b = facts(R), facts(dict(R, NPU_SET_IFM_BASE0=64), mem=("Sram", "Sram"))
        c = E.compare(a, b)
        self.assertEqual(E.placement_class(c, ("Dram", "Dram"), ("Sram", "Sram")), "PLACEMENT_ONLY")
        self.assertEqual(E.placement_class(c, ("Dram", "Dram"), ("Dram", "Sram")), "NOT_CONTROLLED")
        self.assertEqual(E.placement_class(c, None, ("Sram", "Sram")), "UNAVAILABLE")
        for bad in (dict(R, NPU_SET_IFM_PRECISION=1), dict(R, NPU_SET_ACTIVATION=1), dict(R, NPU_SET_BLOCKDEP=1)):
            self.assertEqual(E.placement_class(E.compare(a, facts(bad)), ("Dram", "Dram"), ("Sram", "Sram")), "NOT_CONTROLLED")
        self.assertEqual(E.placement_class(E.compare(a, facts(R, wsha="x")), ("Dram", "Dram"), ("Sram", "Sram")), "NOT_CONTROLLED")
        self.assertEqual(E.placement_class(E.compare(a, facts(R, ops=("Add", "Conv2D"))), ("Dram", "Dram"), ("Sram", "Sram")), "NOT_CONTROLLED")

    def test_weights_need_digest(self):
        self.assertFalse(E.compare(facts(R, wsha=None), facts(R, wsha=None))["weights_equal"])

    def test_wrapper(self):
        a = facts(R)
        w1 = facts(dict(R, NPU_SET_BLOCKDEP=2, NPU_SET_IFM_BASE0=5), ops=("Add", "Conv2D", "Add"))
        self.assertEqual(E.wrapper_class(E.compare(a, w1), ("Dram", "Dram"), ("Dram", "Dram")), "WRAPPER_ONLY")
        lay = facts(dict(R, NPU_SET_IFM_PRECISION=1), ops=("Add", "Conv2D", "Add"))
        self.assertEqual(E.wrapper_class(E.compare(a, lay), ("Dram", "Dram"), ("Dram", "Dram")), "WRAPPER_PLUS_LAYOUT")
        self.assertEqual(E.wrapper_class(E.compare(a, w1), ("Dram", "Dram"), ("Sram", "Sram")), "NOT_CONTROLLED")
        comp = facts(dict(R, NPU_SET_ACTIVATION=3), ops=("Add", "Conv2D", "Add"))
        self.assertEqual(E.wrapper_class(E.compare(a, comp), ("Dram", "Dram"), ("Dram", "Dram")), "NOT_CONTROLLED")
        self.assertEqual(E.wrapper_class(E.compare(a, facts(R, wsha="x")), ("Dram", "Dram"), ("Dram", "Dram")), "NOT_CONTROLLED")
        self.assertEqual(E.wrapper_class(E.compare(a, w1), ("Dram", "Dram"), None), "UNAVAILABLE")

    def test_conv_memory_and_h1uc(self):
        f = facts(R, mem=("Sram", "Dram"), ops=("Add", "Conv2D"))
        self.assertEqual(E.conv_memory(f), ("Sram", "Dram"))
        self.assertEqual(E.h1uc(facts(R)), 20736)          # 8 * 8 * 9 ublocks * (4 * 64/8 + max(32, 32)/8)

    def test_estimator_only(self):
        b = dict(ok=True, cms_sha256="c", const_sha256="k", arena_size=1, fast_size=2, inputs=[1], outputs=[2])
        self.assertTrue(E.estimator_only(b, dict(b)))
        for k in ("cms_sha256", "const_sha256", "arena_size", "fast_size", "inputs", "outputs"):
            self.assertFalse(E.estimator_only(b, dict(b, **{k: "z"})), k)
        self.assertFalse(E.estimator_only(b, dict(b, ok=False)))

    def test_first_dram(self):
        d = facts(R, mem=("Dram", "Dram")); s = facts(R, mem=("Sram", "Sram"))
        self.assertEqual(E.first_dram({"W1-P0-c0": dict(L500=s), "W1-P0-c16384": dict(L500=d), "W1-P0-c65536": dict(L500=d)}), "W1-P0-c16384")
        self.assertEqual(E.first_dram({"W1-P0-c0": dict(L500=dict(ok=False)), "W1-P0-c16384": dict(L500=d)}), "W1-P0-c16384")
        self.assertIsNone(E.first_dram({"W1-P0-c0": dict(L500=s)}))

    def test_verdict(self):
        ok = dict(cls="PLACEMENT_ONLY", numeric_verified=True)
        self.assertEqual(E.verdict(False, {"a": ok}), "READY_FOR_BOARD_REVIEW")
        self.assertEqual(E.verdict(False, {"a": dict(cls="WRAPPER_ONLY", numeric_verified=True)}), "READY_FOR_BOARD_REVIEW")
        self.assertEqual(E.verdict(False, {"a": dict(ok, numeric_verified=False)}), "PARTIAL_IDENTIFIABILITY")
        self.assertEqual(E.verdict(False, {"a": dict(cls="WRAPPER_PLUS_LAYOUT", numeric_verified=True)}), "PARTIAL_IDENTIFIABILITY")
        self.assertEqual(E.verdict(False, {"a": dict(cls="NOT_CONTROLLED", numeric_verified=True),
                                           "b": dict(cls="UNAVAILABLE", numeric_verified=False)}), "NOT_IDENTIFIABLE")
        self.assertEqual(E.verdict(True, {"a": ok}), "INVALID")


if __name__ == "__main__":
    unittest.main()
