"""Ported from feat/stage2b4-qread 65d3f8b; Cli uses the driver runner's boot dir (record v2 fields, cms sidecar)."""
import json, struct, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis")); sys.path.insert(0, str(REPO / "host" / "lib"))
sys.path.insert(0, str(REPO / "host" / "tests"))
import qread_timeline as T
import qread_trace as Q
from test_cms_timeline import S   # four kernel ops: CONV, DEPTHWISE, POOL, ELEMENTWISE

KOFF = [o for o in (i * 4 for i in range(len(S) // 4))
        if struct.unpack_from("<I", S, o)[0] & 0x3FF in (2, 3, 5, 6) and not struct.unpack_from("<I", S, o)[0] >> 14 & 3]


def trace(points, events=None, dropped=0, hook=50):
    """points: (t, qread); every read takes 10 cycles, QREAD unchanged inside a read."""
    ev = events or [()] * len(points)
    s = tuple(Q.Sample(t, q, 1, e, q, t + 10) for (t, q), e in zip(points, ev))
    return Q.Trace(Q.TraceConfig(2 if events else 1), s, dropped, len(s), hook)


class Map(unittest.TestCase):
    def test_offsets_from_the_stream(self):
        cm = T.CommandMap.from_stream(S)
        self.assertEqual([k.offset for k in cm.kernels], KOFF)
        self.assertEqual([k.type for k in cm.kernels], ["CONV", "DEPTHWISE", "POOL", "ELEMENTWISE"])
        self.assertEqual(cm.cms_len, len(S))

    def test_completed(self):
        cm = T.CommandMap.from_stream(S)
        self.assertEqual(cm.completed(0), 0)
        self.assertEqual(cm.completed(KOFF[0]), 0)        # QREAD at the instruction: not yet complete
        self.assertEqual(cm.completed(KOFF[0] + 4), 1)
        self.assertEqual(cm.completed(KOFF[3]), 3)
        self.assertEqual(cm.completed(len(S)), 4)


class Timeline(unittest.TestCase):
    def setUp(self):
        self.cm = T.CommandMap.from_stream(S)

    def test_brackets_each_op_alone(self):
        pts = [(100, 0), (200, KOFF[0]), (300, KOFF[0] + 4), (400, KOFF[2]), (500, KOFF[2] + 4), (600, KOFF[3] + 4)]
        bs = T.brackets(trace(pts), self.cm)
        self.assertEqual([(b.lo, b.hi, b.first_past) for b in bs],
                         [(200, 310, 2), (300, 410, 3), (400, 510, 4), (500, 610, 5)])
        self.assertEqual(T.resolved_ratio(bs), 1.0)

    def test_skip_and_unbounded(self):
        pts = [(100, KOFF[0]), (200, KOFF[2] + 4), (300, len(S))]      # ops 0-2 first seen together
        bs = T.brackets(trace(pts), self.cm)
        self.assertEqual([b.first_past for b in bs], [1, 1, 1, 2])
        self.assertEqual(T.resolved_ratio(bs), 0.25)                     # only op 3 alone
        bs = T.brackets(trace([(100, KOFF[1] + 4), (200, KOFF[2] + 4), (300, len(S))]), self.cm)
        self.assertEqual((bs[0].lo, bs[0].first_past), (None, 0))        # complete before the first sample
        self.assertEqual(T.resolved_ratio(bs), 0.5)                      # ops 2 and 3 only
        pts = [(100, KOFF[0] + 4), (200, KOFF[1] + 4), (300, KOFF[2] + 4), (400, len(S))]
        bs = T.brackets(trace(pts), self.cm)
        self.assertEqual([b.first_past for b in bs], [0, 1, 2, 3])       # every op seen alone, but op 0
        self.assertEqual(T.resolved_ratio(bs), 0.75)                     # was complete before any sample
        bs = T.brackets(trace([(100, 0), (200, KOFF[2])]), self.cm)
        self.assertEqual((bs[3].hi, bs[3].first_past), (None, None))     # never seen complete
        self.assertEqual(T.resolved_ratio([]), 0.0)

    def test_progress_and_deltas(self):
        pts = [(100, 0), (200, KOFF[0] + 4), (300, KOFF[0] + 4), (400, len(S))]
        tr = trace(pts, events=[(0, 0), (5, 1), (9, 1), (20, 4)])
        p = T.progress(tr, self.cm)
        self.assertEqual([(r["t_before"], r["kernels_complete"], r["newly_complete"]) for r in p],
                         [(0, 0, 0), (100, 1, 1), (200, 1, 0), (300, 4, 3)])
        self.assertEqual(list(T.deltas(tr, self.cm, [None, 81])[0])[-2:], ["d_slot0", "d_ev81"])   # no shift
        d = T.deltas(tr, self.cm, [48, 81])
        self.assertEqual([(r["dt"], r["dqread"], r["qread_stalled"], r["d_ev48"], r["d_ev81"]) for r in d],
                         [(100, KOFF[0] + 4, 0, 5, 1), (100, 0, 1, 4, 0), (100, len(S) - KOFF[0] - 4, 0, 11, 3)])


class Verdict(unittest.TestCase):
    def test_priority_and_bounds(self):
        self.assertEqual(T.verdict(["x"], False, 1.0), "TRACE_INVALID")
        self.assertEqual(T.verdict(["x"], None, 1.0), "TRACE_INVALID")
        self.assertEqual(T.verdict([], None, 1.0), "UNPROVEN")
        self.assertEqual(T.verdict([], True, 1.0), "TRACE_PERTURBED")
        self.assertEqual(T.verdict([], False, 0.09), "TRACE_UNOBSERVABLE")
        self.assertEqual(T.verdict([], False, 0.10), "TRACE_COARSE")
        self.assertEqual(T.verdict([], False, 0.89), "TRACE_COARSE")
        self.assertEqual(T.verdict([], False, 0.90), "TRACE_VALID")
        self.assertEqual(T.verdict([], False, 0.5, low=0.6), "TRACE_UNOBSERVABLE")


class Cli(unittest.TestCase):
    def test_boot_dir(self):
        pts = [(100, 0), (200, KOFF[0] + 4), (300, KOFF[1] + 4), (400, KOFF[2] + 4), (500, len(S))]
        words = [w for t, q in pts for w in (t, q, 1, q, t + 10)]
        def rec(cfg, ovf=0):
            f = dict(trace_config=cfg, trace_words_per_sample=5, samples=len(pts), sample_dropped=0,
                     trace_polls=len(pts), trace_hook_calls=9, ovf_irq=ovf)
            f.update({f"event_code{i}": 0 for i in range(8)})
            return f
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "boot" / "traces").mkdir(parents=True)
            (d / "m.drwl.cms.bin").write_bytes(S)
            (d / "boot" / "traces" / "set1_rep3.bin").write_bytes(struct.pack(f"<{len(words)}I", *words))
            (d / "boot" / "traces" / "set1_rep5.bin").write_bytes(struct.pack(f"<{len(words)}I", *words))
            raw = [{"ping": {}}, dict(set_id=1, rep=3, record=rec(1)),
                   dict(set_id=1, rep=4, record=rec(1)),                       # no trace file
                   dict(set_id=1, rep=5, record=rec(0xFFFFFFFF))]              # trace file but the record says OFF
            (d / "boot" / "raw_runs.json").write_text(json.dumps(raw))
            T.main(str(d / "m.drwl.cms.bin"), str(d / "boot"), str(d / "out"))
            s = json.loads((d / "out" / "summary.json").read_text())
            self.assertEqual(s["set1_rep3"]["resolved_ratio"], 1.0)
            self.assertEqual(s["set1_rep3"]["verdict_before_baseline"], "UNPROVEN")
            self.assertEqual(s["set1_rep4"]["verdict"], "TRACE_INVALID")
            self.assertEqual(s["set1_rep5"]["verdict"], "TRACE_INVALID")
            self.assertTrue((d / "out" / "set1_rep3" / "brackets.csv").exists())

    def test_slot_codes(self):
        r = {f"event_code{i}": 30 + i for i in range(8)}
        self.assertEqual(T.slot_codes(dict(r, ovf_irq=0b10), 3), [30, None, 32])


if __name__ == "__main__":
    unittest.main()
