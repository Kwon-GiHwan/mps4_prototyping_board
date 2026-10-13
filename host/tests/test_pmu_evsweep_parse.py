"""Every refusal rule of pmu_evsweep_parse must be reachable by a fixture."""
import sys, unittest, zlib, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))
import pmu_evsweep_parse as P


def make(accept=lambda ev: True, build_id=P.BUILD_ID_EVSW, nec=8, drop=0, dup=False,
         bad_crc=False, no_hdr=False, no_end=False, count_override=None):
    ev_lines = []
    for pas, slots in ((0, [0]), (1, range(8))):
        for s in slots:
            for ev in range(1024):
                rb = ev if accept(ev) else 0
                ev_lines.append(f"EV,{pas},{s},{ev},{rb:08x}")
    if drop: ev_lines = ev_lines[:-drop]
    if dup: ev_lines.append(ev_lines[5])
    body = "\n".join(ev_lines) + "\n"
    crc = zlib.crc32(body.encode()) & 0xFFFFFFFF
    if bad_crc: crc ^= 1
    n = count_override if count_override is not None else len(ev_lines)
    hdr = "" if no_hdr else f"EVSWEEP-HDR,{build_id:08x},00004001,0000a2a1,{nec}\n"
    end = "" if no_end else f"EVSWEEP-END,{n},{crc:08x}\n"
    return hdr + body + end


class Verdicts(unittest.TestCase):
    def test_closed_set(self):
        self.assertEqual(P.verdict(17, 0x11), "ACCEPTED")
        self.assertEqual(P.verdict(17, 0x00), "COERCED_TO_ZERO")
        self.assertEqual(P.verdict(17, 0x20), "COERCED_OTHER")
        self.assertEqual(P.verdict(17, 0x1011), "UPPER_BITS_SET")
        self.assertEqual(P.verdict(0, 0x00), "ACCEPTED")
        for v in ("ACCEPTED", "COERCED_TO_ZERO", "COERCED_OTHER", "UPPER_BITS_SET"):
            self.assertIn(v, P.VERDICTS)


class Parse(unittest.TestCase):
    def test_green(self):
        hdr, cells = P.parse(make())
        self.assertEqual(len(cells), P.EXPECTED_LINES)
        self.assertEqual(hdr.num_event_cnt, 8)

    def test_summary_shapes(self):
        acc = lambda ev: ev in (0, 17, 32, 35)
        _, cells = P.parse(make(accept=acc))
        s = P.summarize(cells)
        self.assertEqual(s["slot_agreement"], "AGREE")
        self.assertEqual(s["accepted_p1_slot0"], [0, 17, 32, 35])
        self.assertEqual(s["p0_vs_p1"], "EQUAL")

    FIXTURES = {
        "RULE_HDR_MISSING": dict(no_hdr=True),
        "RULE_END_MISSING": dict(no_end=True),
        "RULE_LINE_COUNT": dict(drop=1),
        "RULE_CRC": dict(bad_crc=True),
        "RULE_DUP_CELL": dict(dup=True),
        "RULE_BUILD_ID": dict(build_id=0x504D5543),
        "RULE_NUM_EVENT_CNT": dict(nec=4),
    }

    def test_each_fixture_trips_its_own_rule(self):
        for rule, kw in self.FIXTURES.items():
            with self.subTest(rule=rule):
                with self.assertRaises(P.Refusal) as cm:
                    P.parse(make(**kw))
                self.assertEqual(P.refusal_rule(cm.exception), rule)

    def test_verdict_is_exhaustive(self):
        # Every (ev, rb) pair lands in exactly one of the four verdicts; a
        # "none of the above" rule would be a check that cannot fail.
        for ev in (0, 1, 17, 1023):
            for rb in (0, 1, 17, 1023, 0x400, 0x411, 0xFFFFFFFF):
                self.assertIn(P.verdict(ev, rb), P.VERDICTS)

    def test_tripped_set_equals_rules(self):
        tripped = set()
        for kw in self.FIXTURES.values():
            try: P.parse(make(**kw))
            except P.Refusal as e: tripped.add(e.rule)
        self.assertEqual(tripped, set(P.RULES))


if __name__ == "__main__":
    unittest.main()
