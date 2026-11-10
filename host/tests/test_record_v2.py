import struct, sys, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import record_v2 as R
import runner_proto as rp


def payload(fields=None, flags=R.REQUIRED, rc=0, total=None, magic=R.MAGIC):
    f = dict.fromkeys(R.FIELDS, 0); f.update(schema=3, event_count=2, event_code0=35, event_code1=48)
    f.update(fields or {})
    total = total or R.HEADER_WORDS + len(R.FIELDS)
    body = struct.pack(f"<{len(R.FIELDS)}I", *(f[k] for k in R.FIELDS))
    head = bytearray(struct.pack("<8I", magic, 2, total, 8, 5, flags, rc, 0))
    p = bytes(head) + body
    crc = zlib.crc32(p[16:28] + p[32:]) & 0xFFFFFFFF                     # words 4..end without word 7
    return p[:28] + struct.pack("<I", crc) + p[32:]


class Parse(unittest.TestCase):
    def test_round_trip_and_windows(self):
        r = R.parse(payload(dict(ccnt_irq_lo=7, ccnt_irq_hi=2, dwt_arm=0xFFFFFFF0, dwt_irq=0x10, dwt_invoke=1,
                                 dwt_return=101, ev_irq0=9, ev_irq1=4)))
        self.assertEqual((r.run_sequence, r.valid_flags, r.run_rc), (5, R.REQUIRED, 0))
        self.assertEqual(r.npu_execution_cycles(), (2 << 32) + 7)
        self.assertEqual(r.npu_execution_dwt(), 0x20)                           # DWT wraps
        self.assertEqual(r.host_end_to_end(), 100)
        self.assertEqual(r.events(), [(35, 9), (48, 4)])

    def test_refusals(self):
        p = bytearray(payload()); p[100] ^= 1
        for bad in (bytes(p), payload(magic=0x31454D52), payload()[:-4], payload(dict(schema=1)), b"\0" * 16):
            with self.assertRaises(rp.ProtocolError):
                R.parse(bad)


class Validity(unittest.TestCase):
    def test_each_term(self):
        ok = R.parse(payload())
        self.assertEqual(R.validity(ok, [35, 48]), (True, []))
        cases = {"job_result": R.parse(payload(dict(job_result=2))), "codes_echo": ok,
                 "run_rc": R.parse(payload(rc=1)),
                 "one_irq": R.parse(payload(flags=R.REQUIRED & ~R.ONE_IRQ)),
                 "no_overflow": R.parse(payload(flags=R.REQUIRED & ~R.NO_OVERFLOW))}
        for term, r in cases.items():
            codes = [35, 51] if term == "codes_echo" else [35, 48]
            valid, failed = R.validity(r, codes)
            self.assertFalse(valid, term)
            self.assertIn(term, failed)
        self.assertEqual(R.validity(R.parse(payload(flags=R.REQUIRED | R.OUTPUT_MATCH)), [35, 48])[0], True)
        self.assertEqual(R.validity(R.parse(payload(dict(ofm_mismatch=3))), [35, 48])[0], True)   # reported apart


if __name__ == "__main__":
    unittest.main()
