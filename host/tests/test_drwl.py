import hashlib, struct, sys, unittest, pathlib
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import drwl as D


class Pack(unittest.TestCase):
    def test_layout(self):
        b = D.pack(b"M" * 20, [b"i" * 3, b"j" * 5], [b"g" * 7])
        h = D.parse(b)
        self.assertEqual((h["magic"], h["version"], h["n_in"], h["n_out"], h["total_len"]), (D.MAGIC, 1, 2, 1, len(b)))
        self.assertEqual(struct.unpack_from("<I", b, 0)[0], 0x4C575244)          # 'DRWL' little-endian
        self.assertEqual(b[h["model_off"]:h["model_off"] + h["model_len"]], b"M" * 20)
        self.assertEqual([b[o:o + n] for o, n in h["inputs"]], [b"i" * 3, b"j" * 5])
        self.assertEqual([b[o:o + n] for o, n in h["outputs"]], [b"g" * 7])
        self.assertTrue(all(o % 16 == 0 for o, _ in [(h["model_off"], 0)] + h["inputs"] + h["outputs"]))
        self.assertEqual(h["model_off"], 96)          # 16 header words + 6 table words = 88 B, aligned up
        self.assertEqual(len(b) % 16, 0)

    def test_pack_refusals(self):
        for args in ((b"", [b"i"], [b"g"]), (b"m", [], [b"g"]), (b"m", [b"i"], []),
                     (b"m", [b"i"] * 9, [b"g"]), (b"m", [b"i"], [b"g"] * 9)):
            with self.assertRaises(ValueError):
                D.pack(*args)
        D.pack(b"m", [b"i"] * 4, [b"g"] * 5)       # rnnoise: 4 inputs, 5 outputs
        D.pack(b"m", [b"i"] * 8, [b"g"] * 8)       # 8 per side is allowed


class Parse(unittest.TestCase):
    def setUp(self):
        self.b = bytearray(D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7]))

    def test_refusals(self):
        bad = []
        x = bytearray(self.b); x[0] ^= 1; bad.append(x)                                   # magic
        x = bytearray(self.b); struct.pack_into("<I", x, 4, 2); bad.append(x)             # version
        x = bytearray(self.b); struct.pack_into("<I", x, 8, len(x) + 16); bad.append(x)   # total_len
        x = bytearray(self.b); struct.pack_into("<I", x, 20, 0); bad.append(x)            # no inputs
        x = bytearray(self.b); struct.pack_into("<I", x, 24, 9); bad.append(x)            # 9 outputs > 8
        x = bytearray(self.b); struct.pack_into("<I", x, 20, 9); bad.append(x)            # 9 inputs > 8
        x = bytearray(self.b); struct.pack_into("<I", x, 64, 8); bad.append(x)            # IFM inside the table
        x = bytearray(self.b); struct.pack_into("<I", x, 64, 104); bad.append(x)          # misaligned
        x = bytearray(self.b); struct.pack_into("<I", x, 68, 10_000); bad.append(x)       # past the end
        x = bytearray(self.b); struct.pack_into("<I", x, 16, 0); bad.append(x)            # empty model
        bad.append(self.b[:40])                                                            # short
        for i, x in enumerate(bad):
            with self.assertRaises(ValueError, msg=i):
                D.parse(bytes(x))


    def test_nine_on_one_side_refused_even_when_well_formed(self):
        for ins, outs in ((1, 9), (9, 1)):
            with mock.patch.object(D, "IO_MAX", 9):                               # build a well-formed 9-entry side
                b = D.pack(b"M" * 20, [b"i"] * ins, [b"g"] * outs)
            with self.assertRaises(ValueError, msg=(ins, outs)):
                D.parse(b)

class Placement(unittest.TestCase):
    """Header word 7 (docs/plan/stage4_memory_placement_plan.md F1): 0 = DDR arena, 1 = SRAM arena."""
    S4 = REPO / "evidence" / "stage4" / "workloads" / "s4_conv_base.drwl"
    S4_SHA256 = "2681c566729ce568f4041df6a69d1b5c5c558d2172bb76b6d75ad64ca2b4f267"   # Stage 4 conv_base (boot 330)

    def test_word_7(self):
        self.assertEqual(D.HEADER_FIELDS[7], "placement")
        b = D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7])
        self.assertEqual(struct.unpack_from("<I", b, 28)[0], 0)                   # default DDR
        self.assertEqual(D.parse(b)["placement"], 0)
        s = D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7], placement=1)
        self.assertEqual(D.parse(s)["placement"], 1)
        self.assertEqual([i for i in range(len(b)) if b[i] != s[i]], [28])
        w = D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7], placement=2)                # PLACEMENT_SRAM_W (E2E-D)
        self.assertEqual(D.parse(w)["placement"], 2)
        self.assertEqual([i for i in range(len(b)) if b[i] != w[i]], [28])
        with self.assertRaises(ValueError):
            D.pack(b"M", [b"i"], [b"g"], placement=3)

    def test_unknown_placement_refused(self):
        b = bytearray(D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7]))
        for v in (3, 0xFFFFFFFF):
            struct.pack_into("<I", b, 28, v)
            with self.assertRaises(ValueError, msg=v):
                D.parse(bytes(b))
            with self.assertRaises(ValueError, msg=v):
                D.with_placement(bytes(b), 0)                                      # refuses what parse refuses
        with self.assertRaises(ValueError):
            D.with_placement(D.pack(b"M", [b"i"], [b"g"]), 3)

    def test_stage4_blob_a_unchanged_b_one_word(self):
        a = self.S4.read_bytes()
        self.assertEqual(hashlib.sha256(a).hexdigest(), self.S4_SHA256)
        self.assertEqual(D.parse(a)["placement"], 0)                               # every earlier blob: word 7 = 0
        self.assertEqual(D.with_placement(a, 0), a)
        b = D.with_placement(a, 1)
        self.assertEqual(len(b), len(a))
        self.assertEqual([i for i in range(len(a)) if a[i] != b[i]], [28])        # one byte of word 7 (LE 1)
        self.assertEqual(b[28:32], bytes([1, 0, 0, 0]))
        self.assertEqual(D.with_placement(b, 0), a)


if __name__ == "__main__":
    unittest.main()
