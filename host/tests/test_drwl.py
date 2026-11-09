import struct, sys, unittest, pathlib
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
                     (b"m", [b"i"] * 5, [b"g"] * 4)):
            with self.assertRaises(ValueError):
                D.pack(*args)
        D.pack(b"m", [b"i"] * 4, [b"g"] * 4)       # 8 is allowed


class Parse(unittest.TestCase):
    def setUp(self):
        self.b = bytearray(D.pack(b"M" * 20, [b"i" * 3], [b"g" * 7]))

    def test_refusals(self):
        bad = []
        x = bytearray(self.b); x[0] ^= 1; bad.append(x)                                   # magic
        x = bytearray(self.b); struct.pack_into("<I", x, 4, 2); bad.append(x)             # version
        x = bytearray(self.b); struct.pack_into("<I", x, 8, len(x) + 16); bad.append(x)   # total_len
        x = bytearray(self.b); struct.pack_into("<I", x, 20, 0); bad.append(x)            # no inputs
        x = bytearray(self.b); struct.pack_into("<I", x, 24, 8); bad.append(x)            # 1 + 8 > 8
        x = bytearray(self.b); struct.pack_into("<I", x, 64, 8); bad.append(x)            # IFM inside the table
        x = bytearray(self.b); struct.pack_into("<I", x, 64, 104); bad.append(x)          # misaligned
        x = bytearray(self.b); struct.pack_into("<I", x, 68, 10_000); bad.append(x)       # past the end
        x = bytearray(self.b); struct.pack_into("<I", x, 16, 0); bad.append(x)            # empty model
        bad.append(self.b[:40])                                                            # short
        for i, x in enumerate(bad):
            with self.assertRaises(ValueError, msg=i):
                D.parse(bytes(x))


if __name__ == "__main__":
    unittest.main()
