import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import equiv_a as A

RESET, VENDOR = 0x00021F3F, 0x00021F3F


def w(i, entry=(0x1111, 0x2222), written=(0x1111, 0x2222), seam=None, after64=0, restored=0):
    s = seam or written
    return dict(run_index=i, cap_sram_entry=entry[0], cap_ext_entry=entry[1], cap_sram_written=written[0],
                cap_ext_written=written[1], cap_sram_seam=s[0], cap_ext_seam=s[1], ta_ext_maxr_after_64=after64,
                ta_ext_maxr_restored=restored)


def raw(words):
    return [{"ping": {}}] + [dict(set_id=1, rep=i + 1, trailing=[0] * 20 + list(x.values())) for i, x in enumerate(words)]


JIT = {3: -25, 4: 0, 5: 25}     # npu_active and NPU cycles move 1 % RUN to RUN: jittery, tolerance 1 %


def runs(npu=5000, mac=100, valid=True, reps=(3, 4, 5)):
    return {(1, r): dict(ev={48: mac, 35: npu + JIT[r]}, valid=valid, infer=npu + JIT[r], infer_cpu=6000)
            for r in reps}


class E1(unittest.TestCase):
    def test_inert_differs_unstable(self):
        later = (0x1111, 0x2222)
        self.assertEqual(A.e1([w(1), w(2, entry=later)])[0], "E1_INERT")
        self.assertEqual(A.e1([w(1, written=(0x21F3F, 0x2222)), w(2, entry=(0x21F3F, 0x2222),
                                                                  written=(0x21F3F, 0x2222))])[0], "E1_DIFFERS")
        self.assertEqual(A.e1([w(1), w(2, written=(0x1111, 0x2223))])[0], "E1_UNSTABLE")
        self.assertEqual(A.e1([w(1), w(2, written=(0x1111, 0x2223), seam=(0x1111, 0x2222))])[0], "E1_UNSTABLE")
        self.assertEqual(A.e1([w(1), w(2, seam=(0x1111, 0x0))])[0], "E1_UNSTABLE")

    def test_reset_value_is_run_one_only(self):
        # a later RUN's entry value is the previous RUN's write, not the reset value
        self.assertEqual(A.e1([w(1, entry=(0x5, 0x2222)), w(2)])[0], "E1_DIFFERS")
        self.assertEqual(A.e1([w(2), w(3)])[0], "UNPROVEN")
        self.assertEqual(A.e1([w(1), None])[0], "UNPROVEN")
        self.assertEqual(A.e1([])[0], "UNPROVEN")


class E2(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(A.e2([w(1), w(2)])[0], "E2_SAME")
        self.assertEqual(A.e2([w(1, after64=64), w(2, after64=64)])[0], "E2_DIFFERS")
        self.assertEqual(A.e2([w(1, after64=32)])[0], "E2_OTHER")
        self.assertEqual(A.e2([w(1), w(2, after64=64)])[0], "E2_UNSTABLE")
        self.assertEqual(A.e2([w(1, restored=64)])[0], "UNPROVEN")
        self.assertEqual(A.e2([w(1), None])[0], "UNPROVEN")


class Words(unittest.TestCase):
    def test_trailing_slice_and_missing(self):
        ws = A.diag_words(raw([w(1, after64=7)]))
        self.assertEqual((ws[0]["run_index"], ws[0]["ta_ext_maxr_after_64"]), (1, 7))
        self.assertEqual(A.diag_words([dict(set_id=1, rep=1, trailing=[0] * 22)]), [None])


class Image(unittest.TestCase):
    def test_reproduces_and_differs(self):
        self.assertEqual(A.image(runs(), runs())[0], "DIAG_IMAGE_REPRODUCES")
        self.assertEqual(A.image(runs(mac=101), runs())[0], "DIAG_IMAGE_DIFFERS")           # deterministic key moved
        self.assertEqual(A.image(runs(npu=5020), runs())[0], "DIAG_IMAGE_REPRODUCES")      # jitter inside 1 %
        self.assertEqual(A.image(runs(npu=5100), runs())[0], "DIAG_IMAGE_DIFFERS")         # 2 % outside
        self.assertEqual(A.image(runs(valid=False), runs())[0], "UNPROVEN")
        self.assertEqual(A.image({}, runs())[0], "UNPROVEN")
        d = {k: dict(v, ev={35: v["ev"][35]}) for k, v in runs().items()}
        self.assertEqual(A.image(d, runs())[0], "UNPROVEN")                                # key missing


if __name__ == "__main__":
    unittest.main()
