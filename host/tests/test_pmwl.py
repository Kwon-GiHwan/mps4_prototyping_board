import struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import pmwl

INFO = dict(cms=b"\x00" * 12 + struct.pack("<I", 0xFFFF0000), const=b"\x01" * 32, arena_size=64,
            fast_size=16, ifm_off=0, ifm_len=4, ofm_off=8, ofm_len=2)


class Knobs(unittest.TestCase):
    def test_default_is_v1_all_off(self):
        self.assertEqual(pmwl.knobs(), [pmwl.OFF] * 16)
        b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, pmwl.knobs())
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (1, 64))

    def test_v2_split_ports(self):
        k = pmwl.knobs("ext:rd_weights", {"cmd": "ext", "const": "ext", "arena": "sram", "fast": "sram"})
        self.assertEqual(k[0], 0x102)                       # AXI_SEL ext | CH_SEL rd_weights
        self.assertEqual(k[1], 2 | 0 << 2 | 0 << 4 | 0 << 6)  # REGIONCFG: const->ATTR2(EXT), arena/fast->ATTR0
        self.assertEqual(k[2], 2)                           # QCONFIG: cmd -> ATTR2
        self.assertEqual(k[3:7], [0x0, 0x0, 0x4, 0x4])      # MEM_ATTR0..3
        b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (2, 96))
        self.assertEqual(list(struct.unpack("<8I", b[64:96])), k[:8])

    def test_v3_axi_limit(self):
        k = pmwl.knobs("ext:rd_weights", {"cmd": "ext", "const": "ext", "arena": "sram", "fast": "sram"},
                    {"sram": 0x20000, "ext": 0x20000})
        self.assertEqual(k[7:9], [0x20000, 0x20000])
        b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (3, 128))
        self.assertEqual(list(struct.unpack("<16I", b[64:128])), k)
        with self.assertRaises(SystemExit): pmwl.knobs(axi_limit={"sram": 0x40000})   # reserved bit 18

    def test_power_ctrl_is_word_25_and_v3(self):
        self.assertEqual(pmwl.knobs()[9], pmwl.OFF)                       # default: vendor value
        k = pmwl.knobs(power_ctrl=0)
        self.assertEqual(k[9], 0)
        self.assertEqual([i for i, w in enumerate(k) if w != pmwl.OFF], [9])
        b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (3, 128))   # word 25 needs v3
        self.assertEqual(struct.unpack("<I", b[64 + 9 * 4:64 + 10 * 4])[0], 0)          # header word 16 + 9
        self.assertEqual(pmwl.knobs(power_ctrl=63)[9], 63)
        for bad in (64, -1):
            with self.assertRaises(SystemExit): pmwl.knobs(power_ctrl=bad)

    def test_fast_base_is_word_26(self):
        sram = {"cmd": "ext", "const": "ext", "arena": "ext", "fast": "sram"}
        self.assertEqual(pmwl.knobs(ports=sram)[10], pmwl.OFF)
        k = pmwl.knobs(ports=sram, fast_base=0x31100000)
        self.assertEqual(k[10], 0x31100000)
        b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
        self.assertEqual(struct.unpack("<I", b[64 + 10 * 4:64 + 11 * 4])[0], 0x31100000)   # header word 26
        for bad in (0x31100010, 0x30FFFF00, 0x31400000):
            with self.assertRaises(SystemExit): pmwl.knobs(ports=sram, fast_base=bad)
        with self.assertRaises(SystemExit): pmwl.knobs(ports=dict(sram, fast="ext"), fast_base=0x31100000)
        with self.assertRaises(SystemExit): pmwl.knobs(fast_base=0x31100000)

    def test_ta_profile_is_word_27(self):
        self.assertEqual(pmwl.knobs()[11], pmwl.OFF)
        for prof in (1, 2):
            k = pmwl.knobs(ta_profile=prof)
            self.assertEqual([i for i, w in enumerate(k) if w != pmwl.OFF], [11])
            b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
            self.assertEqual(struct.unpack("<I", b[64 + 11 * 4:64 + 12 * 4])[0], prof)   # header word 27
        for bad in (0, 3):
            with self.assertRaises(SystemExit): pmwl.knobs(ta_profile=bad)



class Header(unittest.TestCase):
    def test_word_indices(self):
        self.assertEqual(pmwl.word("cms_len"), 3)
        self.assertEqual(pmwl.word("total_len"), 15)
        self.assertEqual([pmwl.word(n) for n in ("axi_chan", "power_ctrl", "fast_base", "ta_profile")], [16, 25, 26, 27])

    def test_parse_roundtrip_each_version(self):
        for kw, version in ((pmwl.knobs(), 1),
                            (pmwl.knobs(ports={"cmd": "ext", "const": "ext", "arena": "ext", "fast": "sram"}), 2),
                            (pmwl.knobs(ta_profile=1), 3)):
            b = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, kw)
            h = pmwl.parse_header(b)
            self.assertEqual(h["version"], version)
            self.assertEqual((h["cms_len"], h["ofm_len"], h["total_len"]), (16, 2, len(b)))
            self.assertEqual(b[h["golden_off"]:h["golden_off"] + 2], b"\x03" * 2)
            self.assertEqual(b[h["cms_off"]:h["cms_off"] + h["cms_len"]], INFO["cms"])
            self.assertEqual(h["knobs"], kw)

    def test_v2_word_23_is_reserved(self):
        kw = pmwl.knobs(ports={"cmd": "ext", "const": "ext", "arena": "ext", "fast": "sram"})
        b = bytearray(pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, kw))
        struct.pack_into("<I", b, 4 * 23, 0x1234)          # garbage in the reserved v2 slot
        self.assertEqual(pmwl.parse_header(bytes(b))["knobs"][7], pmwl.OFF)

    def test_refuses_bad_blob(self):
        good = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, pmwl.knobs())
        with self.assertRaises(ValueError): pmwl.parse_header(b"PMWL")
        with self.assertRaises(ValueError): pmwl.parse_header(b"XXXX" + good[4:])
        with self.assertRaises(ValueError): pmwl.parse_header(good[:4] + struct.pack("<I", 9) + good[8:])


if __name__ == "__main__":
    unittest.main()
