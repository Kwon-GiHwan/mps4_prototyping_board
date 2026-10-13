import struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host"))
import pack_vela_workload as K


class T(unittest.TestCase):
    def test_cop1_extraction(self):
        raw = b"\x11\x22\x33\x44" * 2
        cop = b"COP1" + struct.pack("<I", 1) + b"\x00" * 8 + struct.pack("<I", 2 | (2 << 16)) + raw
        self.assertEqual(K.extract_cms(cop), raw)


if __name__ == "__main__":
    unittest.main()
