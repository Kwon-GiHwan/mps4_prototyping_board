import struct, sys, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import record_v2 as R
import runner_proto as rp

V4_TAIL = ["regioncfg_irq", "qconfig_irq", "placement"]   # docs/plan/stage4_memory_placement_plan.md F4


def payload(fields=None, flags=None, rc=0, total=None, magic=R.MAGIC, schema=5):
    names = R.SCHEMA_FIELDS[schema]
    if flags is None:
        flags = R.REQUIRED | (R.REGIONCFG_MATCH if schema >= 4 else 0)
    f = dict.fromkeys(names, 0); f.update(schema=schema, event_count=2, event_code0=35, event_code1=48)
    f.update(fields or {})
    total = total or R.HEADER_WORDS + len(names)
    body = struct.pack(f"<{len(names)}I", *(f[k] for k in names))
    head = bytearray(struct.pack("<8I", magic, 2, total, 8, 5, flags, rc, 0))
    p = bytes(head) + body
    crc = zlib.crc32(p[16:28] + p[32:]) & 0xFFFFFFFF                     # words 4..end without word 7
    return p[:28] + struct.pack("<I", crc) + p[32:]


class Parse(unittest.TestCase):
    def test_round_trip_and_windows(self):
        r = R.parse(payload(dict(ccnt_irq_lo=7, ccnt_irq_hi=2, dwt_arm=0xFFFFFFF0, dwt_irq=0x10, dwt_invoke=1,
                                 dwt_return=101, ev_irq0=9, ev_irq1=4)))
        self.assertEqual((r.run_sequence, r.valid_flags & R.REQUIRED, r.run_rc), (5, R.REQUIRED, 0))
        self.assertEqual(r.npu_execution_cycles(), (2 << 32) + 7)
        self.assertEqual(r.npu_execution_dwt(), 0x20)                           # DWT wraps
        self.assertEqual(r.host_end_to_end(), 100)
        self.assertEqual(r.events(), [(35, 9), (48, 4)])

    def test_refusals(self):
        p = bytearray(payload()); p[100] ^= 1
        for bad in (bytes(p), payload(magic=0x31454D52), payload()[:-4], payload(dict(schema=1)), b"\0" * 16,
                    payload(dict(schema=3)), payload(dict(schema=4), schema=3)):   # schema word vs record length
            with self.assertRaises(rp.ProtocolError):
                R.parse(bad)

    def test_schema_4_adds_three_fields_at_the_end(self):
        self.assertEqual(R.FIELDS_V4[-3:], V4_TAIL)
        self.assertEqual(R.HEADER_WORDS + len(R.FIELDS_V4), 98)                # 95 words before (image 83398c7)
        r = R.parse(payload(dict(regioncfg_irq=0x153, qconfig_irq=3, placement=1), schema=4))
        self.assertEqual((r.f["regioncfg_irq"], r.f["qconfig_irq"], r.f["placement"]), (0x153, 3, 1))
        self.assertNotIn("pmu_flags", r.f)
        self.assertEqual(R.validity(r, [35, 48]), (True, []))                  # every archived schema-4 RUN

    def test_schema_5_adds_two_fields_at_the_end(self):                        # Stage 6E-X3 amendment A
        self.assertEqual(R.SCHEMA, 5)
        self.assertEqual(R.FIELDS[-2:], ["pmu_flags", "pmcr_after_arm"])
        self.assertEqual(R.FIELDS[:-2], R.FIELDS_V4)
        self.assertEqual(R.HEADER_WORDS + len(R.FIELDS), 100)
        r = R.parse(payload(dict(pmu_flags=1, pmcr_after_arm=0x400F)))
        self.assertEqual((r.f["schema"], r.f["pmu_flags"], r.f["pmcr_after_arm"]), (5, 1, 0x400F))
        with self.assertRaises(rp.ProtocolError):
            R.parse(payload(dict(schema=4)))                                   # schema word vs record length

    def test_schema_3_records_still_parse(self):                               # every archived driver-runner RUN
        r = R.parse(payload(dict(arena_base=0x700015C0), schema=3))
        self.assertEqual((r.f["schema"], r.f["arena_base"]), (3, 0x700015C0))
        self.assertNotIn("placement", r.f)
        self.assertEqual(R.validity(r, [35, 48]), (True, []))                  # no placement term for schema 3


class Validity(unittest.TestCase):
    def test_each_term(self):
        ok = R.parse(payload())
        self.assertEqual(R.validity(ok, [35, 48]), (True, []))
        cases = {"job_result": R.parse(payload(dict(job_result=2))), "codes_echo": ok,
                 "run_rc": R.parse(payload(rc=1)),
                 "one_irq": R.parse(payload(flags=R.REQUIRED & ~R.ONE_IRQ | R.REGIONCFG_MATCH)),
                 "no_overflow": R.parse(payload(flags=R.REQUIRED & ~R.NO_OVERFLOW | R.REGIONCFG_MATCH)),
                 "regioncfg_match": R.parse(payload(flags=R.REQUIRED))}
        for term, r in cases.items():
            codes = [35, 51] if term == "codes_echo" else [35, 48]
            valid, failed = R.validity(r, codes)
            self.assertFalse(valid, term)
            self.assertIn(term, failed)
        self.assertEqual(R.REGIONCFG_MATCH, 1 << 6)
        self.assertEqual(R.validity(R.parse(payload(flags=R.REQUIRED | R.REGIONCFG_MATCH | R.OUTPUT_MATCH)),
                                    [35, 48])[0], True)
        self.assertEqual(R.validity(R.parse(payload(dict(ofm_mismatch=3))), [35, 48])[0], True)   # reported apart


if __name__ == "__main__":
    unittest.main()
