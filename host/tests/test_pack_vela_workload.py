import json, struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib")); sys.path.insert(0, str(REPO / "host" / "container"))
import pack_vela_workload as K
import mlek_profile
import pmwl

PROFILE = json.loads((REPO / "config" / "mlek_baseline.json").read_text())


class T(unittest.TestCase):
    def test_cop1_extraction(self):
        raw = b"\x11\x22\x33\x44" * 2
        cop = b"COP1" + struct.pack("<I", 1) + b"\x00" * 8 + struct.pack("<I", 2 | (2 << 16)) + raw
        self.assertEqual(K.extract_cms(cop), raw)


class GraphOrder(unittest.TestCase):
    def test_op_order_to_graph_order(self):
        e = [dict(name="b", len=2), dict(name="a", len=3)]
        self.assertEqual(K.graph_order([b"BB", b"AAA"], e, ["a", "b"]), [b"AAA", b"BB"])
        self.assertEqual(K.graph_order([b"BB", b"AAA"], e, ["b", "a"]), [b"BB", b"AAA"])
        with self.assertRaises(SystemExit):
            K.graph_order([b"BB", b"AAA"], e, ["a", "c"])


class SplitDump(unittest.TestCase):
    E = [dict(name="b", len=2), dict(name="a", len=3)]          # Vela op order

    def test_graph_order_to_op_order(self):
        self.assertEqual(pmwl.split_dump(b"AAABB", ["a", "b"], self.E), [b"BB", b"AAA"])
        self.assertEqual(pmwl.split_dump(b"BBAAA", ["b", "a"], self.E), [b"BB", b"AAA"])
        self.assertEqual(pmwl.split_dump(b"xyz", ["t"], [dict(name="t", len=3)]), [b"xyz"])   # one tensor as before

    def test_refusals(self):
        with self.assertRaises(SystemExit):
            pmwl.split_dump(b"AAAB", ["a", "b"], self.E)                 # length
        with self.assertRaises(SystemExit):
            pmwl.split_dump(b"AAABBC", ["a", "b"], self.E)
        with self.assertRaises(SystemExit):
            pmwl.split_dump(b"AAABB", ["a", "c"], self.E)                # names


class Profile(unittest.TestCase):
    def test_baseline_profile_words(self):
        # words 16..27: axi_chan OFF, regioncfg (const/arena EXT, fast SRAM), qconfig (cmd EXT), MEM_ATTR 0/0/4/4,
        # AXI_SRAM, AXI_EXT, POWER_CTRL 0, fast base, TA profile 1
        want = [pmwl.OFF, 0x0A, 0x2, 0x0, 0x0, 0x4, 0x4, 0x20F0B, 0x21F3F, 0, 0x31100000, 1] + [pmwl.OFF] * 4
        self.assertEqual(pmwl.knobs(**mlek_profile.knob_args(PROFILE)), want)
        self.assertEqual(PROFILE["seed"], 1)

    def test_packer_accepts_its_own_vela_and_refuses_others(self):
        K.check_vela(PROFILE, "5.0.0")
        with self.assertRaises(SystemExit):
            K.check_vela(PROFILE, "4.4.0")
        changed = dict(PROFILE, vela=dict(PROFILE["vela"], options=PROFILE["vela"]["options"][:-1] + ["x"]))
        with self.assertRaises(SystemExit):
            K.check_vela(changed, "5.0.0")


if __name__ == "__main__":
    unittest.main()
