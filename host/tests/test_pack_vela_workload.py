import struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import pack_vela_workload as K

INFO = dict(cms=b"\x00" * 12 + struct.pack("<I", 0xFFFF0000), const=b"\x01" * 32, arena_size=64,
            fast_size=16, ifm_off=0, ifm_len=4, ofm_off=8, ofm_len=2)


class T(unittest.TestCase):
    def test_default_is_v1_all_off(self):
        self.assertEqual(K.knobs(), [K.OFF] * 8)
        b = K.pack(INFO, b"\x02" * 4, b"\x03" * 2, K.knobs())
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (1, 64))

    def test_v2_split_ports(self):
        k = K.knobs("ext:rd_weights", {"cmd": "ext", "const": "ext", "arena": "sram", "fast": "sram"})
        self.assertEqual(k[0], 0x102)                       # AXI_SEL ext | CH_SEL rd_weights
        self.assertEqual(k[1], 2 | 0 << 2 | 0 << 4 | 0 << 6)  # REGIONCFG: const->ATTR2(EXT), arena/fast->ATTR0
        self.assertEqual(k[2], 2)                           # QCONFIG: cmd -> ATTR2
        self.assertEqual(k[3:7], [0x0, 0x0, 0x4, 0x4])      # MEM_ATTR0..3
        b = K.pack(INFO, b"\x02" * 4, b"\x03" * 2, k)
        h = struct.unpack("<16I", b[:64]); self.assertEqual((h[1], h[2]), (2, 96))
        self.assertEqual(list(struct.unpack("<8I", b[64:96])), k)

    def test_cop1_extraction(self):
        raw = b"\x11\x22\x33\x44" * 2
        cop = b"COP1" + struct.pack("<I", 1) + b"\x00" * 8 + struct.pack("<I", 2 | (2 << 16)) + raw
        self.assertEqual(K.extract_cms(cop), raw)


if __name__ == "__main__":
    unittest.main()
