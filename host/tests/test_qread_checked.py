"""qread_checked: parsing and trace class on hand-encoded checked samples (the layout written out here from trace.h's
comment, not from the module under test)."""
import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import qread_checked as C
import qread_trace as Q

ID = 0x20007001
CMS = 400


def slot(off, *values, accepted=True, ids=None):
    ids = ids or [ID] * len(values)
    return [(1 if accepted else 0) << 20 | len(values) << 16 | off] + [w for p in zip(ids, values) for w in p]


def sample(t, slots, job=1, final=0, start=0, bad_check=False):
    body = [w for s in slots for w in s]
    n_att = sum(s[0] >> 16 & 0xF for s in slots)
    words = [0x5A << 24 | job << 23 | final << 22 | start << 21 | len(slots) << 8 | n_att, t] + body + [t + 50]
    x = 0xA5A5A5A5
    for w in words:
        x ^= w
    return words + [x ^ (1 if bad_check else 0)]


def job(qb, qa, status=None, extra=()):
    """The slots of one job sample; status = a STATUS slot (default: accepted at once, running)."""
    return [slot(0x18, qb), status or slot(0x04, 0xFFFF0001), *extra, slot(0x18, qa)]


def run_of(samples, qsize=CMS, reserve_extra=()):
    """reserve sample (its counters too in mode 4), start (QSIZE), one job sample per slot list; the last is final."""
    w = sample(10, [slot(0x18, CMS), slot(0x04, 0xFFFF0020), *reserve_extra, slot(0x18, CMS)], job=0, final=1)
    w += sample(100, [slot(0x20, qsize)], start=1)
    for i, sl in enumerate(samples):
        w += sample(200 + 100 * i, sl, final=int(i == len(samples) - 1))
    return w


def run(*job_q, extra=(), qsize=CMS):
    return run_of([job(qb, qa, extra=extra) for qb, qa in job_q], qsize)


def header(words, mode=3, **kw):
    h = dict(trace_config=Q.TraceConfig(mode, 6, 12).word(), trace_words_per_sample=13, trace_samples=None,
             trace_dropped=0, trace_polls=100, trace_hook_calls=1000, trace_words=len(words), trace_rejected=0,
             trace_unaccepted=0, trace_id=ID)
    h.update(kw)
    return h


def parsed(words, n_events=0, mode=3, **kw):
    if "trace_samples" not in kw:                               # count samples by walking the encoded lengths
        n = i = 0
        while i < len(words):
            j = i + 2
            for _ in range(words[i] >> 8 & 0xFF):
                j += 1 + 2 * (words[j] >> 16 & 0xF)
            i, n = j + 2, n + 1
        kw["trace_samples"] = n
    return C.parse(words, header(words, mode, **kw), n_events)


class Parse(unittest.TestCase):
    def test_valid(self):
        t = parsed(run((0, 100), (100, 300), (300, CMS)))
        self.assertEqual(C.trace_class(t, CMS, ID), (C.VALID, []))
        self.assertEqual([(s.job, s.start, s.final) for s in t.samples][:2], [(False, False, True), (True, True, False)])
        self.assertEqual(len(t.job()), 3)
        self.assertEqual(t.qsize(), CMS)
        self.assertEqual(t.job()[1].qread_after.value, 300)

    def test_recovered_keeps_the_rejected_read(self):
        w = run_of([job(0, 100), job(100, 300, status=slot(0x04, ID, 0xFFFF0001)), job(300, CMS)])
        t = parsed(w, trace_rejected=1)
        self.assertEqual(C.trace_class(t, CMS, ID), (C.RECOVERED, []))
        st = t.job()[1].status
        self.assertEqual((st.attempts, st.first_ok, st.value), (((ID, ID), (ID, 0xFFFF0001)), False, 0xFFFF0001))
        r = C.rejected_attempts(t)
        self.assertEqual([(x["offset"], x["value_is_id"], x["id_read_ok"], x["accepted_later"]) for x in r],
                         [(0x04, True, True, True)])
        # a stale ID read: the ID read returned the previous slot's value
        w = run_of([job(0, 100), job(100, 300, status=slot(0x04, 0xFFFF0001, 0xFFFF0001, ids=[100, ID])),
                    job(300, CMS)])
        r = C.rejected_attempts(parsed(w, trace_rejected=1))
        self.assertEqual([(x["id_read_ok"], x["id_read_is_prev_value"]) for x in r], [(False, True)])

    def test_each_invalid_term(self):
        ok = run((0, 100), (100, CMS))
        cases = {
            "checksum": (ok[:-1] + [ok[-1] ^ 1], {}),
            "buffer_overflow": (ok, dict(trace_dropped=1)),
            "sample_count": (ok, dict(trace_samples=9)),
            "rejected_count": (ok, dict(trace_rejected=1)),
            "unaccepted_read": (ok, dict(trace_unaccepted=1)),
            "id_not_npu_id": (ok, dict(trace_id=ID + 1)),
            "qsize_not_stream_length": (run((0, 100), (100, CMS), qsize=CMS - 4), {}),
            "final_qread_not_stream_end": (run((0, 100), (100, 200)), {}),
            "qread_decreasing": (run((0, 100), (96, CMS)), {}),
            "qread_outside_stream": (run((0, 102), (102, CMS)), {}),
            "more_samples_than_polls": (ok, dict(trace_polls=2)),
        }
        for name, (w, kw) in cases.items():
            cls, why = C.trace_class(parsed(w, **kw), CMS, ID)
            self.assertEqual(cls, C.INVALID, name)
            self.assertIn(name, why, name)

    def test_unaccepted_slot_in_data(self):
        w = run((0, 100))
        w += sample(400, [slot(0x18, 100), slot(0x04, ID, ID, ID, accepted=False), slot(0x18, CMS)], final=1)
        self.assertIn("unaccepted_read", C.problems(parsed(w), CMS, ID))

    def test_counters(self):
        ev = lambda a, b: [slot(0x1300, a), slot(0x1304, b)]
        t = parsed(run_of([job(0, 100, extra=ev(5, 9)), job(100, CMS, extra=ev(6, 9))], reserve_extra=ev(90, 90)),
                   n_events=2, mode=4)
        self.assertEqual(C.trace_class(t, CMS, ID), (C.VALID, []))               # the reserve sample's are outside
        t = parsed(run_of([job(0, 100, extra=ev(8, 9)), job(100, CMS, extra=ev(7, 10))], reserve_extra=ev(0, 0)),
                   n_events=2, mode=4)
        self.assertIn("event_counter_decreasing", C.problems(t, CMS, ID))
        t = parsed(run_of([job(0, 100, extra=ev(8, 9)), job(100, CMS, extra=ev(8, 9))], reserve_extra=ev(0, 0)),
                   n_events=1, mode=4)
        self.assertTrue(any(e.startswith("slot_layout") for e in t.layout_errors))   # two counters, one armed

    def test_layout_errors(self):
        ok = run((0, CMS))
        self.assertIn("bad_header_at_0", parsed([0x12345678] + ok, trace_samples=3).layout_errors)
        t = C.parse(ok[:-3], header(ok[:-3], trace_samples=3), 0)
        self.assertTrue(any(e.startswith("truncated_sample") for e in t.layout_errors))
        bad = sample(10, [slot(0x04, 1), slot(0x18, 0), slot(0x18, 0)], job=0, final=1)   # STATUS first
        self.assertTrue(any(e.startswith("slot_layout") for e in parsed(bad).layout_errors))
        wrong_n = sample(10, [slot(0x18, 0), slot(0x04, 1), slot(0x18, 0)], job=0)
        wrong_n[0] += 1                                             # header says one more attempt
        x = 0xA5A5A5A5
        for v in wrong_n[:-1]:
            x ^= v
        wrong_n[-1] = x
        self.assertTrue(any(e.startswith("attempt_count") for e in parsed(wrong_n).layout_errors))
        self.assertIn("no_job_samples", C.problems(parsed(sample(10, [slot(0x20, CMS)], start=1)), CMS, ID))

    def test_n_words(self):
        self.assertEqual(Q.n_words(dict(trace_config=Q.TraceConfig(3).word(), trace_words=77, trace_samples=1,
                                        trace_words_per_sample=5)), 77)
        self.assertEqual(Q.n_words(dict(trace_config=Q.TraceConfig(1).word(), trace_words=0, trace_samples=3,
                                        trace_words_per_sample=5)), 15)


if __name__ == "__main__":
    unittest.main()
