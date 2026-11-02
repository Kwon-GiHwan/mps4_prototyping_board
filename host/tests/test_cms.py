import struct, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import cms
import pmwl

STOP = 0xFFFF0000                           # NPU_OP_STOP, mask 0xFFFF (cmd0)


def w(*xs):
    return struct.pack(f"<{len(xs)}I", *xs)


# cmd1 (2 words, control 1 in bits 15:14) + CONV, cmd0 BLOCKDEP + DEPTHWISE, cmd1 + POOL, STOP
CONV, DW, POOL, KWAIT = 0x0002, 0x0003, 0x0005, 0x0012
CMD1 = 0x4000 | 0x010                       # some NPU_SET_* with a payload word
BLOCKDEP = 0x0116 | (3 << 16)               # cmd0 with parameter 3 (opcode 278)
STREAM = w(CMD1, 0xDEADBEEF, CONV, BLOCKDEP, DW, CMD1, 0x1, POOL, STOP)


class Parse(unittest.TestCase):
    def test_instruction_boundaries(self):
        ins = cms.instructions(STREAM)
        self.assertEqual([o for o, *_ in ins], [0, 8, 12, 16, 20, 28, 32])   # cmd1 takes 8 bytes
        self.assertEqual([op for *_, op in ins], [0x010, CONV, 0x116, DW, 0x010, POOL, 0])

    def test_kernel_ops(self):
        self.assertEqual(cms.kernel_offsets(STREAM), [8, 16, 28])
        self.assertEqual(cms.boundaries(STREAM), [0, 12, 20, 32])           # before op 0 setup, after each op

    def test_truncated_cmd1_refused(self):
        with self.assertRaises(ValueError): cms.instructions(w(CMD1))


class Insert(unittest.TestCase):
    def test_pmu_mask_word(self):
        self.assertEqual(cms.pmu_mask(1), 0x00010013)                       # opcode 19, cmd0, enable bit 16
        self.assertEqual(cms.pmu_mask(0), 0x00000013)

    def test_insert_before_offsets(self):
        out = cms.insert(STREAM, {0: [cms.pmu_mask(1)], 20: [cms.pmu_mask(0)]})
        self.assertEqual(out, w(0x10013, CMD1, 0xDEADBEEF, CONV, BLOCKDEP, DW, 0x13, CMD1, 0x1, POOL, STOP))
        self.assertEqual(cms.kernel_offsets(out), [12, 20, 36])

    def test_insert_off_boundary_refused(self):
        with self.assertRaises(ValueError): cms.insert(STREAM, {4: [cms.pmu_mask(1)]})   # inside a cmd1
        with self.assertRaises(ValueError): cms.insert(STREAM, {36: [cms.pmu_mask(1)]})  # after STOP
        with self.assertRaises(ValueError): cms.insert(STREAM + w(BLOCKDEP), {36: [cms.pmu_mask(1)]})  # past STOP

    def test_gate_ops(self):
        # enable before kernel op i's setup, disable after kernel op j-1: counts ops i..j-1 as parsed
        out = cms.gate(STREAM, 1, 3)
        self.assertEqual(out, w(0x13, CMD1, 0xDEADBEEF, CONV, 0x10013, BLOCKDEP, DW, CMD1, 0x1, POOL, 0x13, STOP))
        self.assertEqual(cms.gate(STREAM, 0, 1)[:4], w(0x10013))
        with self.assertRaises(ValueError): cms.gate(STREAM, 2, 2)
        with self.assertRaises(ValueError): cms.gate(STREAM, 0, 4)


INFO = dict(cms=STREAM, const=b"\x01" * 32, arena_size=64, fast_size=16, ifm_off=0, ifm_len=4, ofm_off=8, ofm_len=2)
INFO4 = dict(INFO, inputs=[(0, 4), (32, 3)], outputs=[(8, 2), (40, 5)])


class Repack(unittest.TestCase):
    def test_same_cms_is_byte_identical(self):
        b3 = pmwl.pack(INFO, b"\x02" * 4, b"\x03" * 2, pmwl.knobs(ta_profile=1))
        self.assertEqual(cms.with_cms(b3, STREAM), b3)
        b4 = pmwl.pack(INFO4, [b"\x02" * 4, b"\x04" * 3], [b"\x03" * 2, b"\x05" * 5], pmwl.knobs(ta_profile=1))
        self.assertEqual(cms.with_cms(b4, STREAM), b4)

    def test_new_cms_moves_the_data_and_keeps_the_rest(self):
        b = pmwl.pack(INFO4, [b"\x02" * 4, b"\x04" * 3], [b"\x03" * 2, b"\x05" * 5], pmwl.knobs(ta_profile=1))
        new = cms.gate(STREAM, 0, 3)
        b2, h, h2 = cms.with_cms(b, new), pmwl.parse_header(b), None
        h2 = pmwl.parse_header(b2)
        self.assertEqual(b2[h2["cms_off"]:h2["cms_off"] + h2["cms_len"]], new)
        self.assertEqual(h2["knobs"], h["knobs"])
        for k in ("arena_size", "fast_size", "const_len", "version"):
            self.assertEqual(h2[k], h[k])
        self.assertEqual(b2[h2["const_off"]:h2["const_off"] + h2["const_len"]], b"\x01" * 32)
        for io in ("inputs", "outputs"):
            for e, e2 in zip(h[io], h2[io]):
                off, off2 = (e.get("data_off", e.get("golden_off")), e2.get("data_off", e2.get("golden_off")))
                self.assertEqual(b2[off2:off2 + e2["len"]], b[off:off + e["len"]])
                self.assertEqual(e2["arena_off"], e["arena_off"])


if __name__ == "__main__":
    unittest.main()
