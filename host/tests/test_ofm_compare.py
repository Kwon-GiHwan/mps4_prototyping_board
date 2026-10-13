import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import ofm_compare as C

# shape of MLEK DumpTensorData output: "\n\t" every 16 values, then info lines
DUMP = ("INFO - Initial input tensors values\n\n\t0x11, 0x22, \n"
        "INFO - input tensors populated\n\n\t0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, "
        "\n\t0xff, 0x80, \nINFO - Running inference\n"
        "INFO - output tensors post inference\n\n\t0x7f, 0x81, 0x00, \nINFO - done\n")


class Dump(unittest.TestCase):
    def test_sections(self):
        self.assertEqual(C.section(DUMP, C.IFM_MARK), bytes(range(16)) + b"\xff\x80")   # not the initial dump
        self.assertEqual(C.section(DUMP, C.OFM_MARK), b"\x7f\x81\x00")

    def test_board_format_without_tab(self):
        board = "INFO - output tensors post inference\n\n0x80, 0x7f, \n0x01, \nINFO - Inference completed.\n"
        self.assertEqual(C.section(board, C.OFM_MARK), b"\x80\x7f\x01")


class Compare(unittest.TestCase):
    def test_equal(self):
        r = C.compare(b"\x01\x02", b"\x01\x02")
        self.assertEqual((r["mismatch_count"], r["positions"], r["max_abs_diff"]), (0, [], 0))

    def test_int8_signed_diff(self):
        r = C.compare(bytes([0x7f, 0x05, 0x80, 0x00]), bytes([0x7b, 0x05, 0x7f, 0xff]))
        self.assertEqual(r["positions"], [0, 2, 3])
        self.assertEqual(r["a_values"], [127, -128, 0])
        self.assertEqual(r["b_values"], [123, 127, -1])
        self.assertEqual(r["signed_diff_a_minus_b"], [4, -255, 1])
        self.assertEqual(r["max_abs_diff"], 255)

    def test_length_mismatch_refused(self):
        with self.assertRaises(ValueError):
            C.compare(b"\x01", b"\x01\x02")


if __name__ == "__main__":
    unittest.main()
