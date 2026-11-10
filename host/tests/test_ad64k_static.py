"""ad64k_static.py: register/area parsing and the refusals that tie the analysis to the measured artifacts."""
import pathlib, shutil, sys, tempfile, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import ad64k_static as A

HL = """High level NPU operations:
0 Conv2D , size=1,1 stride=1,1, OFM Block=[1, 1, 16, 288], IFM Block=[1, 1, 16, 64], OFM UBlock=[1, 4, 32] Traversal=DepthFirst
High level command stream:
0 DMA src: Dram:ReadOnly, address: 0x0, dest: Sram:Staging, address: 0xa800, sizes: (N/A), length: 4816
1 Conv2D OFM area [0, 0, 0, 0 - 1, 2, 32, 192], IFM [0, 0, 0, 0 - 1, 4, 32, 1], IFM2 [ - ], padding: [top:1], cascaded
2 Conv2D OFM area [0, 2, 0, 0 - 1, 4, 32, 192], IFM [0, 1, 0, 0 - 1, 6, 32, 1], IFM2 [ - ]
"""


class Parse(unittest.TestCase):
    def test_acc_format(self):
        self.assertEqual(A.acc(0x300), ("U2X2", 0))
        self.assertEqual(A.acc(0x200), ("U1X4", 0))
        self.assertEqual(A.acc(0x410), ("U2X4", 1))

    def test_area_and_ublocks(self):
        self.assertEqual(A.area("0, 2, 0, 0 - 1, 4, 32, 192"), (2, 0, 0, 4, 32, 192))
        self.assertEqual(A.volume((2, 0, 0, 4, 32, 192)), 2 * 32 * 192)
        self.assertEqual(A.ublocks((0, 0, 0, 1, 16, 276), (1, 4, 32)), 1 * 4 * 9)
        self.assertEqual(A.ublocks((0, 0, 0, 32, 32, 16), (2, 2, 32)), 16 * 16 * 1)
        self.assertEqual(A.ublocks((0, 0, 0, 1, 16, 276), (2, 4, 32)), 1 * 4 * 9)   # 1 row still takes a 2-row ublock

    def test_high_level(self):
        c = A.hl_commands(HL)
        self.assertEqual([x["dmas"] for x in c], [[dict(src="Dram:ReadOnly", dst="Sram:Staging", length=4816)], []])
        self.assertEqual([x["cascaded"] for x in c], [True, False])
        self.assertEqual(A.hl_ublocks(HL), [("Conv2D", (1, 4, 32))])


class Refusals(unittest.TestCase):
    """A copy of the real inputs with one thing changed must be refused."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        shutil.copytree(A.MAP, d / "map"); shutil.copytree(A.WL, d / "wl", ignore=shutil.ignore_patterns("*cache*", "kws*", "s4*"))
        for f in A.WL.glob("ad_medium_int8_cache64k.drwl*"):
            shutil.copy(f, d / "wl")
        self.old = (A.MAP, A.WL)
        A.MAP, A.WL = d / "map", d / "wl"

    def tearDown(self):
        A.MAP, A.WL = self.old
        self.tmp.cleanup()

    def test_unchanged_copy_passes(self):
        ks = A.kernels("cache64k")
        self.assertEqual(len(ks), 66)
        pool = [k for k in ks if k["kind"] == "POOL"]
        self.assertEqual([(k["weight_stream_bytes"], k["weight_region"]) for k in pool], [(0, "")])  # no weights read

    def edit(self, name, old, new):
        f = A.MAP / "cache64k" / name
        t = f.read_text(); self.assertIn(old, t); f.write_text(t.replace(old, new, 1))

    def test_cms_hash(self):
        f = A.MAP / "cache64k" / "ad_medium_int8.cms.sha256"
        f.write_text("0" * 64 + "\n")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_cms_bytes(self):
        f = A.MAP / "cache64k" / "ad_medium_int8.cms.bin"
        b = bytearray(f.read_bytes()); b[-1] ^= 1; f.write_bytes(bytes(b))
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_vela_hash(self):
        (A.MAP / "cache64k" / "ad_medium_int8.vela.sha256").write_text("0" * 64 + "\n")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_ublock_disagrees_with_register(self):
        self.edit("ad_medium_int8.hlcs.txt", "OFM UBlock=[1, 4, 32]", "OFM UBlock=[2, 2, 32]")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_offsets(self):
        self.edit("ad_medium_int8.op_map.csv", "\n1,", "\n1,9")   # second kernel's offset changed
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_command_op_name(self):
        self.edit("ad_medium_int8.hlcs.txt", "DepthwiseConv2D OFM area [0, 0, 0, 0 - 1, 1, 16, 192]",
                  "Conv2D OFM area [0, 0, 0, 0 - 1, 1, 16, 192]")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_npu_operation_name(self):
        self.edit("ad_medium_int8.hlcs.txt", "\n1 DepthwiseConv2D , subOps", "\n1 Conv2D , subOps")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")

    def test_operator_order(self):
        self.edit("ad_medium_int8.op_map.csv", ",DepthwiseConv2D,16x16x192", ",Conv2D,16x16x192")
        with self.assertRaises(SystemExit):
            A.kernels("cache64k")


if __name__ == "__main__":
    unittest.main()
