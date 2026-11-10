"""Ported from feat/stage2b4-qread 65d3f8b; the legacy-runner parts (PMWL word 31, record trailing fields) replaced."""
import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib"))
import qread_trace as Q


def header(cfg_word, wps, n, dropped=0, polls=None, hook=100):
    return dict(trace_config=cfg_word, trace_words_per_sample=wps, trace_samples=n, trace_dropped=dropped,
                trace_polls=n if polls is None else polls, trace_hook_calls=hook)


def sample(t, q, ev=(), q2=None, dt=10, status=0x1):
    return [t, q, status, *ev, q if q2 is None else q2, t + dt]


class Config(unittest.TestCase):
    def test_word_layout(self):
        self.assertEqual(Q.TraceConfig(1).word(), 0x00000001)
        self.assertEqual(Q.TraceConfig(2, 10, 3).word(), 0x00030A02)
        self.assertEqual(Q.config_from_word(0x00030A02), Q.TraceConfig(2, 10, 3))
        self.assertIsNone(Q.config_from_word(0xFFFFFFFF))

    def test_refusals(self):
        for w in (0x00000000, 0x00000003, 0x00001001 | 1 << 12, 0x00100001, 0x80000001):
            with self.assertRaises(ValueError, msg=hex(w)):
                Q.config_from_word(w)
        with self.assertRaises(ValueError):
            Q.TraceConfig(1, 16)
        with self.assertRaises(ValueError):
            Q.TraceConfig(1, 0, -1)

    def test_words_per_sample(self):
        self.assertEqual(Q.TraceConfig(1).words_per_sample(6), 5)
        self.assertEqual(Q.TraceConfig(2).words_per_sample(6), 11)


class Parse(unittest.TestCase):
    def test_qread_only(self):
        w = sample(100, 0) + sample(200, 8, q2=12)
        t = Q.parse(w, header(1, 5, 2))
        self.assertEqual([(s.t_before, s.qread_before, s.qread_after, s.t_after) for s in t.samples],
                         [(100, 0, 0, 110), (200, 8, 12, 210)])
        self.assertEqual(t.samples[0].events, ())

    def test_pmu_events(self):
        w = sample(100, 0, ev=(1, 2)) + sample(200, 8, ev=(5, 9))
        t = Q.parse(w, header(2, 7, 2))
        self.assertEqual([s.events for s in t.samples], [(1, 2), (5, 9)])
        self.assertEqual(t.samples[1].t_after, 210)

    def test_layout_refusals(self):
        with self.assertRaises(ValueError):
            Q.parse(sample(1, 0), header(1, 5, 2))          # words != wps * n
        with self.assertRaises(ValueError):
            Q.parse(sample(1, 0, ev=(1,)), header(1, 6, 1))  # QREAD_ONLY with events
        with self.assertRaises(ValueError):
            Q.parse([1, 2, 3, 4], header(2, 4, 1))          # fewer than the base words
        with self.assertRaises(ValueError):
            Q.parse([], header(0xFFFFFFFF, 5, 0))           # trace off

    def test_header_from_record(self):
        f = dict(trace_config=1, trace_words_per_sample=5, samples=2, sample_dropped=0, trace_polls=9,
                 trace_hook_calls=40, qread_at_irq=7)
        self.assertEqual(Q.header_from_record(f), header(1, 5, 2, polls=9, hook=40))


class Integrity(unittest.TestCase):
    def trace(self, words, **kw):
        n = len(words) // kw.pop("wps", 5)
        return Q.parse(words, header(kw.pop("cfg", 1), len(words) // n if n else 5, n, **kw))

    def test_clean(self):
        t = self.trace(sample(100, 0) + sample(200, 8) + sample(300, 16))
        self.assertEqual(Q.integrity(t, 16), [])

    def test_each_check(self):
        cases = {
            "buffer_overflow": self.trace(sample(1, 0), dropped=3),
            "more_samples_than_polls": self.trace(sample(1, 0) + sample(50, 16), polls=1),
            "more_polls_than_hook_calls": self.trace(sample(1, 16), polls=3, hook=1),
            "final_qread_not_stream_end": self.trace(sample(1, 0) + sample(50, 12)),
            "time_not_monotonic": self.trace(sample(100, 0) + sample(50, 4)),
            "qread_decreasing": self.trace(sample(100, 8) + sample(200, 4)),
            "qread_outside_stream": self.trace(sample(100, 20)),
            "event_counter_decreasing": self.trace(sample(1, 0, ev=(5,)) + sample(50, 4, ev=(4,)), cfg=2, wps=6),
        }
        for name, t in cases.items():
            self.assertIn(name, Q.integrity(t, 16), name)
        self.assertIn("qread_outside_stream", Q.integrity(self.trace(sample(1, 6)), 16))   # not word aligned
        self.assertIn("qread_decreasing", Q.integrity(self.trace(sample(100, 8, q2=4)), 16))  # inside one read
        self.assertIn("no_samples", Q.integrity(Q.parse([], header(1, 5, 0)), 16))
        self.assertIn("more_samples_than_polls", Q.integrity(self.trace(sample(1, 16), polls=1, dropped=1), 16))
        self.assertEqual(Q.integrity(self.trace(sample(1, 16), polls=2, hook=1), 16), [])   # final sample: no hook
        self.assertEqual(Q.integrity(self.trace(sample(1, 16), polls=1, hook=0), 16), [])   # IRQ before the wait

    def test_wrap(self):
        t = self.trace(sample(0xFFFFFFF0, 0, dt=0x20) + sample(0x30, 16))   # DWT wraps between and inside reads
        self.assertEqual(Q.integrity(t, 16), [])
        self.assertEqual(Q.elapsed(0xFFFFFFF0, 0x10), 0x20)


if __name__ == "__main__":
    unittest.main()
