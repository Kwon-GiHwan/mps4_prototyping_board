import struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import cms_timeline as T


def c0(op, val=0):
    return [op | val << 16]


def c1(op, value):
    return [0x4000 | op | (value >> 32) << 16, value & 0xFFFFFFFF]


def fm(ifm_base, ofm_base, h=4, w=2, d=8, kh=3, kw=3, ifm_d=16, region=1):
    """Registers of one op: IFM/OFM in `region`, stride_y 100 bytes per row, h rows."""
    return (c0(267, h - 1) + c0(271, region) + c1(0, ifm_base) + c1(5, 100) + c0(260, ifm_d - 1)
            + c0(274, h - 1) + c0(273, w - 1) + c0(275, d - 1) + c0(287, region) + c1(16, ofm_base) + c1(21, 100)
            + c0(289, kh - 1) + c0(288, kw - 1))


def stream(*parts):
    words = [x for p in parts for x in p] + [0xFFFF0000]
    return struct.pack(f"<{len(words)}I", *words)


S = stream(fm(0, 1000), c0(16), c0(17, 0), c0(2),                       # op 0 CONV, after DMA_START + DMA_WAIT k=0
           c0(303, 3), fm(1000, 2000, ifm_d=8), c0(3),                   # op 1 DW reads op 0's OFM, BLOCKDEP 3
           c0(18, 1), c0(303, 0), fm(2000, 3000, kh=1, kw=1), c0(5),     # op 2 POOL after KERNEL_WAIT n=1
           fm(1000, 4000, kh=1, kw=1), c0(6))                            # op 3 ELEMENTWISE reads op 0's OFM


class Timeline(unittest.TestCase):
    def setUp(self):
        self.rows = T.timeline(S)

    def test_types_and_sync(self):
        self.assertEqual([r["type"] for r in self.rows], ["CONV", "DEPTHWISE", "POOL", "ELEMENTWISE"])
        self.assertEqual([r["sync_before"] for r in self.rows], ["DMA_START DMA_WAIT k=0", "", "KERNEL_WAIT n=1", ""])
        self.assertEqual([r["blockdep"] for r in self.rows], [0, 3, 0, 0])

    def test_macs(self):
        self.assertEqual(self.rows[0]["macs"], 4 * 2 * 8 * 9 * 16)      # CONV: OFM x kernel x IFM depth
        self.assertEqual(self.rows[1]["macs"], 4 * 2 * 8 * 9)           # DEPTHWISE: no IFM depth
        self.assertEqual(self.rows[2]["macs"], 4 * 2 * 8)               # POOL 1x1
        self.assertEqual(self.rows[3]["macs"], 0)
        self.assertEqual(self.rows[0]["ofm_hwc"], "4x2x8")

    def test_dependencies(self):
        self.assertEqual([r["ifm_src"] for r in self.rows], ["", 0, 1, 0])
        self.assertEqual([r["dep_prev"] for r in self.rows], [0, 1, 1, 0])     # op 3 reads op 0, not op 2

    def test_last_writer_and_region(self):
        rows = T.timeline(stream(fm(0, 1000), c0(2), fm(0, 1000), c0(2), fm(1000, 5000), c0(2),
                                 fm(1000, 6000, region=2), c0(2)))
        self.assertEqual([r["ifm_src"] for r in rows], ["", "", 1, ""])          # last writer; other region: none

    def test_ifm2_height_and_high_address_bits(self):
        ifm2 = lambda base: c0(395, 3) + c0(399, 1) + c1(128, base) + c1(133, 100)
        rows = T.timeline(stream(fm(0, 1000), c0(2), fm(0, 3000), c0(2),
                                 fm(9000, 8000) + ifm2(1300), c0(6),        # IFM2 row 3 of op 0's 4-row OFM
                                 fm(1 << 32 | 3000, 7000), c0(2),           # same low bits, other 4 GB page
                                 c0(17, 2), fm(0, 6000), c0(2)))
        self.assertEqual(rows[2]["ifm2_src"], 0)
        self.assertEqual(rows[2]["ifm_src"], "")
        self.assertEqual(rows[3]["ifm_src"], "")
        self.assertEqual(rows[4]["sync_before"], "DMA_WAIT k=2")

    def test_sparsity(self):
        rows = T.timeline(stream(fm(0, 1000), c0(302, 0x10), c0(2), c0(302, 0x01), fm(0, 1000), c0(2),
                                 c0(302, 0x10), fm(0, 1000), c0(6)))
        self.assertEqual([r["sparse"] for r in rows], [1, 0, 0])        # bit 4 only; not for elementwise

    def test_overlap_edges(self):
        self.assertTrue(T.overlaps((1, 0, 10), (1, 9, 20)))
        self.assertFalse(T.overlaps((1, 0, 10), (1, 10, 20)))                    # end is exclusive
        self.assertFalse(T.overlaps((1, 0, 10), (2, 0, 10)))
        self.assertFalse(T.overlaps(None, (1, 0, 10)))


if __name__ == "__main__":
    unittest.main()
