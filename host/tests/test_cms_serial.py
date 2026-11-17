"""Stage 6E-X3 stream edits: KERNEL_WAIT/PMU_MASK insertion (host/lib/cms.py), COP1 replacement (host/lib/tflite_cop1.py)
and the workload generator. Expected values are hand-written (encodings from Vela's own KERNEL_WAIT word 0x00010012)."""
import hashlib
import json
import pathlib
import shutil
import struct
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
sys.path.insert(0, str(REPO / "host" / "analysis"))
import cms  # noqa: E402
import drwl  # noqa: E402
import tflite_cop1 as T  # noqa: E402
import stage6ex3_workloads as W  # noqa: E402

SRC = REPO / "evidence/stage6ex3/workloads/src"


def model_of(name):
    blob = (SRC / f"{name}.drwl").read_bytes()
    h = drwl.parse(blob)
    return blob[h["model_off"]:h["model_off"] + h["model_len"]]


def stream_of(name):
    return W._cms_of(T.cop1(model_of(name)))


class Encoding(unittest.TestCase):
    def test_words(self):
        self.assertEqual((cms.kernel_wait(0), cms.kernel_wait(1)), (0x00000012, 0x00010012))
        self.assertEqual((cms.pmu_mask(0), cms.pmu_mask(1)), (0x00000013, 0x00010013))
        for bad in (-1, 0x10000):
            with self.assertRaises(ValueError):
                cms.kernel_wait(bad)


class Serial(unittest.TestCase):
    def setUp(self):
        self.s = stream_of("kws_micronet_m")
        self.n = len(cms.kernel_offsets(self.s))

    def test_reference_stream(self):
        self.assertEqual(hashlib.sha256(self.s).hexdigest()[:8], "21564a54")    # = m7 / op map stream
        self.assertEqual(self.n, 14)

    def test_windows(self):
        bits = [1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1]
        x = cms.serial_mask(self.s, bits)
        self.assertEqual(len(x), len(self.s) + 8 * (self.n + 1))
        ins = cms.instructions(x)
        kw = [i for i, (_, w, c, op) in enumerate(ins) if c == 0 and w == 0x12]
        mk = [(i, (w >> 16) & 1) for i, (_, w, c, op) in enumerate(ins) if c == 0 and op == 19]
        kern = [i for i, (_, w, c, op) in enumerate(ins) if c == 0 and op in cms.KERNEL_OPS]
        self.assertEqual((len(kw), len(mk), len(kern)), (self.n + 1, self.n + 1, self.n))
        self.assertEqual([b for _, b in mk], bits + [0])
        for j, k in enumerate(kern):                                    # window of op j: its mask, then a barrier
            prev_mask = max(i for i, _ in mk if i < k)
            self.assertEqual(dict(mk)[prev_mask], bits[j])
            self.assertIn(prev_mask - 1, kw)                            # KERNEL_WAIT(0) right before that mask
            if j > 0:
                self.assertGreater(prev_mask, kern[j - 1])              # ... and after op j-1's instruction
            nxt = min(i for i in kw if i > k)
            self.assertEqual(nxt, k + 1)                                # barrier right after op j's instruction
        self.assertLess(mk[-1][0], max(i for i, (_, w, c, op) in enumerate(ins) if c == 0 and op == 0))   # before STOP
        self.assertEqual(cms.strip_serial(x), self.s)

    def test_same_stream_but_bits(self):
        a = cms.serial_mask(self.s, [1] * self.n)
        b = cms.serial_mask(self.s, [0] * self.n)
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertEqual(len(diff), self.n)                             # one bit (byte 2 of each PMU_MASK word)
        self.assertTrue(all(i % 4 == 2 for i in diff))

    def test_refusals(self):
        for bits in ([1] * (self.n - 1), [1] * (self.n + 1), [2] + [1] * (self.n - 1)):
            with self.assertRaises(ValueError):
                cms.serial_mask(self.s, bits)


class Cop1(unittest.TestCase):
    def test_replace(self):
        m = model_of("ad_medium_int8")
        c = T.cop1(m)
        self.assertEqual(T.cop1_with_cms(c, W._cms_of(c)), c)
        s = W._cms_of(c)
        new_c = T.cop1_with_cms(c, s + b"\x12\0\0\0\x13\0\0\0")
        self.assertEqual(len(new_c), len(c) + 8)
        self.assertEqual(W._cms_of(new_c), s + b"\x12\0\0\0\x13\0\0\0")
        new_m = T.with_cop1(m, new_c)
        self.assertEqual(T.cop1(new_m), new_c)
        _, start, n = T.cop1_buffer_field(new_m)
        self.assertEqual((start % 16, n, start >= len(m)), (0, len(new_c), True))
        diff = [i for i in range(len(m)) if m[i] != new_m[i]]
        self.assertTrue(0 < len(diff) <= 4 and max(diff) - min(diff) < 4)
        field, _, _ = T.cop1_buffer_field(m)
        self.assertTrue(all(field <= i < field + 4 for i in diff))

    def test_bad_payloads(self):
        c = T.cop1(model_of("kws_micronet_m"))
        for bad in (b"XXXX" + c[4:], c[:-2]):
            with self.assertRaises(ValueError):
                T.cop1_with_cms(bad, b"\0" * 4)
        unknown = c[:4] + struct.pack("<I", 9) + c[8:]
        with self.assertRaises(ValueError):
            T.cop1_with_cms(unknown, b"\0" * 4)


class Workloads(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(W.groups("kws_micronet_m"), {"G_0": [0, 1], "G_V": [3, 5, 7], "G_R": [2, 4, 6, 8, 9, 10, 11, 12, 13]})
        self.assertEqual(W.groups("ad_medium_int8"), {"G_0": [0, 1], "G_V": [3, 5, 7, 9], "G_R": [2, 4, 6, 8, 10, 11, 12, 13]})

    def test_bits(self):
        g = W.groups("kws_micronet_m")
        self.assertEqual(W.bits_for("B1", g, 14), [1] * 14)
        self.assertEqual(W.bits_for("B3", g, 14), [1, 1] + [0] * 12)
        self.assertEqual([a + b + c for a, b, c in zip(W.bits_for("B2", g, 14), W.bits_for("B3", g, 14),
                                                        W.bits_for("B4", g, 14))], [1] * 14)

    def test_rebuild_matches_manifest(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            man = W.build(SRC, tmp)
            frozen = json.loads((REPO / "evidence/stage6ex3/workloads/x3_manifest.json").read_text())
            self.assertEqual(man, frozen)
            for k, v in man.items():
                self.assertEqual(v["stripped_cms_sha256"], v["orig_cms_sha256"])
                self.assertEqual(drwl.parse((tmp / f"{k}.drwl").read_bytes())["pmu_flags"], 0 if v["cond"] == "B0" else 1)
            self.assertEqual(man["x3_kws_B0"]["drwl_sha256"][:8], "c77bf2b7")      # m7 bytes unchanged
            self.assertEqual(man["x3_ad_B0"]["drwl_sha256"][:8], "9d8b45ad")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
