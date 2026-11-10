"""The driver runner's platform-independent core (frame, workload, record, pmu_session, runner) compiled for the host
with fake ports (firmware/driver_runner/tests/host_sim.c) and driven by the host's own DriverLink over a pipe: the same
bytes as on the board. Expected values come from the simulator's documented fake model and from drwl.py, not from the
module under test."""
import csv, json, os, shutil, struct, subprocess, sys, tempfile, threading, time, unittest, pathlib, zlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import drwl
import driver_link
import qread_checked as C
import qread_trace as Q
import record_v2
import runner_proto as rp

FW = REPO / "firmware"
UC = FW / "driver_runner" / "use_case" / "pmu_runner"
SRCS = [UC / "src" / f for f in ("frame.c", "workload.c", "record.c", "pmu_session.c", "runner.c", "probe.c", "trace.c")]
SIM = None
CC = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")


def setUpModule():
    global SIM, _tmp
    if CC is None:
        raise unittest.SkipTest("no C compiler")
    _tmp = tempfile.TemporaryDirectory()
    SIM = pathlib.Path(_tmp.name) / "host_sim"
    subprocess.run([CC, "-std=c11", "-Wall", "-Wextra", "-Werror", "-DTRACE_SIM_READ=sim_npu_read", "-I", str(UC / "include"), "-I", str(FW / "common"),
                    "-o", str(SIM), str(FW / "driver_runner" / "tests" / "host_sim.c"), *map(str, SRCS)], check=True)


def tearDownModule():
    _tmp.cleanup()


class PipeSerial:
    """The subset of pyserial RunnerLink uses, over the simulator's stdin/stdout."""

    def __init__(self, env):
        self.p = subprocess.Popen([str(SIM)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(os.environ, **env))
        self.buf, self.lock = bytearray(), threading.Lock()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            b = self.p.stdout.read1(65536)
            if not b:
                return
            with self.lock:
                self.buf += b

    def read(self, n=1):
        t = time.time() + 0.2
        while time.time() < t:
            with self.lock:
                if self.buf:
                    out = bytes(self.buf[:n]); del self.buf[:n]; return out
            time.sleep(0.002)
        return b""

    def write(self, data):
        self.p.stdin.write(data); self.p.stdin.flush(); return len(data)

    def flush(self):
        pass

    def close(self):
        if self.p.stdin.closed:
            return
        self.p.stdin.close()
        self.stderr = self.p.stderr.read().decode()
        self.p.wait(5)
        self.p.stderr.close()
        self.p.stdout.close()


def link(**env):
    l = driver_link.DriverLink.__new__(driver_link.DriverLink)
    l.protocol, l.late_frames, l.last_measurement = rp.PROTO_MEASURE_V2, 0, None
    l._ser, l._buf, l._seq, l.text_log, l.resyncs = PipeSerial(env), bytearray(), 0, [], 0
    return l


def simm(ins, outs):
    """The simulator's model container: 'SIMM', n_in, n_out, lengths."""
    return struct.pack(f"<3I{len(ins) + len(outs)}I", 0x4D4D4953, len(ins), len(outs), *ins, *outs)


def expected_output(ifm0, k, n):
    return bytes((ifm0[j % len(ifm0)] + k + 1) & 0xFF for j in range(n))


def load(l, blob):
    l.load_model_begin(len(blob), zlib.crc32(blob))
    for off in range(0, len(blob), 4092):
        l.load_model_chunk(off, blob[off:off + 4092])
    return l.load_model_end()


IFM = bytes(range(7, 47))   # 40 bytes


class Session(unittest.TestCase):
    def tearDown(self):
        self.l._ser.close()

    def test_full_run(self):
        self.l = l = link()
        self.assertEqual(l.ping().state, 1)                                    # IDLE
        caps = l.capabilities()
        self.assertEqual((caps["magic"], caps["schema"], caps["record_fields"]),
                         (record_v2.CAPS_MAGIC, 3, len(record_v2.FIELDS)))
        self.assertEqual(l.set_instrumentation_mode(2, [35, 48, 51], 7), (2, 2, 3, 1))
        self.assertEqual(l.set_run_options(driver_link.WAIT_BUSY, 0x00200023), (1, 0x00200023, driver_link.TRACE_OFF))
        golds = [expected_output(IFM, 0, 30), expected_output(IFM, 1, 9)]
        blob = drwl.pack(simm([40], [30, 9]), [IFM], golds)
        computed, expected, total = load(l, blob)
        self.assertEqual((computed, expected, total), (zlib.crc32(blob), zlib.crc32(blob), len(blob)))
        l.load_input(b"")
        self.assertEqual(l.run(), 0)
        r = l.last_measurement
        self.assertEqual(r.valid_flags & record_v2.REQUIRED, record_v2.REQUIRED)
        self.assertTrue(r.valid_flags & record_v2.OUTPUT_MATCH)
        self.assertEqual(record_v2.validity(r, [35, 48, 51]), (True, []))
        self.assertEqual(r.events(), [(35, 350), (48, 481), (51, 512)])          # fake: EVTYPER * 10 + slot
        self.assertEqual(r.npu_execution_cycles(), (1 << 32) + 5000)
        self.assertEqual(r.npu_execution_dwt(), 777)
        f = r.f
        self.assertEqual((f["event_set_id"], f["wait_mode"], f["pmccntr_cfg"], f["arm_count"], f["irq_count"]),
                         (7, 1, 0x00200023, 1, 1))
        self.assertEqual((f["ofm_mismatch"], f["ofm_first"]), (0, 0xFFFFFFFF))
        self.assertEqual(f["arena_base"] - f["model_base"], (f["model_len"] + 15) // 16 * 16)   # MLEK's ld rule
        self.assertEqual(f["model_len"], len(simm([40], [30, 9])))
        self.assertEqual((f["n_base"], f["base0"], f["base_size2"]), (3, 0x70000010, 300))
        self.assertEqual(f["cnten_at_arm"], 0x80000007)                          # cycle counter + 3 slots
        self.assertEqual([f[f"ev_irq{i}"] for i in range(3, 8)], [0] * 5)          # unarmed slots are not read
        self.assertEqual(f["pmcr_at_arm"], 0x2001)
        self.assertGreater(r.host_end_to_end(), r.npu_execution_dwt())
        self.assertEqual(l.run(), 0)                                            # a second RUN, same model
        self.assertEqual(l.last_measurement.run_sequence, r.run_sequence + 1)
        l._ser.close()
        self.assertIn("evtyper=35,48 pmccntr_cfg=0x200023 cntenset=0x80000007", l._ser.stderr)
        self.assertIn("pmcr=0x2007", l._ser.stderr)                              # cnt_en kept, both resets set

    def test_four_inputs_five_outputs(self):                                     # rnnoise's IO shape
        self.l = l = link()
        l.set_instrumentation_mode(2, [35], 1)
        ins = [IFM, b"a" * 24, b"b" * 48, b"c" * 96]
        outs = [expected_output(IFM, k, n) for k, n in enumerate((4, 1, 24, 48, 96))]
        load(l, drwl.pack(simm([len(b) for b in ins], [len(b) for b in outs]), ins, outs))
        l.load_input(b"")
        self.assertEqual(l.run(), 0)
        self.assertEqual(l.last_measurement.f["ofm_mismatch"], 0)

    def test_get_output(self):                                                # Stage 4 output check
        self.l = l = link()
        l.set_instrumentation_mode(2, [35], 1)
        ins = [IFM, b"a" * 24]
        outs = [expected_output(IFM, k, n) for k, n in enumerate((4000, 30, 1500))]
        load(l, drwl.pack(simm([len(b) for b in ins], [len(b) for b in outs]), ins, outs))
        l.load_input(b"")
        with self.assertRaises(rp.Nack) as c:
            l.output_crc()                                                     # no RUN yet
        self.assertEqual(c.exception.code, 5)
        self.assertEqual(l.run(), 0)
        whole = b"".join(outs)
        self.assertEqual(l.output_crc(), (zlib.crc32(whole), len(whole)))
        self.assertEqual(l.get_output(len(whole)), whole)                      # two replies across tensor borders
        self.assertEqual(l.request(driver_link.CMD_GET_OUTPUT, struct.pack("<II", 3990, 25)).payload, whole[3990:4015])
        self.assertEqual(l.request(driver_link.CMD_GET_OUTPUT, struct.pack("<II", len(whole) - 3, 10)).payload,
                         whole[-3:])                                           # clipped to the end
        self.assertEqual(len(l.request(driver_link.CMD_GET_OUTPUT, struct.pack("<II", 0, 9999)).payload),
                         driver_link.OUTPUT_GET_MAX_BYTES)

    def trace_run(self, cfg, codes):
        self.l = l = link()
        l.set_instrumentation_mode(2, codes, 1)
        self.assertEqual(l.set_run_options(driver_link.WAIT_TRACE, 0, cfg.word()), (2, 0, cfg.word()))
        load(l, drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
        l.load_input(b"")
        self.assertEqual(l.run(), 0)
        r = l.last_measurement
        h = Q.header_from_record(r.f)
        t = Q.parse(l.get_trace(h["trace_words_per_sample"] * h["trace_samples"]), h)
        return r, t

    def test_trace_qread_only(self):                                           # sim stream: 4096 B, 16 B / 64 cycles
        r, t = self.trace_run(Q.TraceConfig(Q.MODE_QREAD_ONLY, 6), [35])
        self.assertEqual(Q.integrity(t, 4096), [])
        self.assertEqual(r.f["wait_mode"], driver_link.WAIT_TRACE)
        self.assertEqual(t.samples[-1].qread_after, 4096)                      # the final sample, after the IRQ
        self.assertGreater(len({s.qread_after for s in t.samples}), 50)        # progress observed, not just the end
        self.assertTrue(all(s.events == () for s in t.samples))
        self.assertLess(r.f["trace_polls"], r.f["trace_hook_calls"] // 2)        # 2^6-cycle interval, not every pass
        total = r.f["samples"] * r.f["trace_words_per_sample"]
        tail = self.l.request(Q.CMD_GET_TRACE, struct.pack("<II", total - 2, 10)).payload
        self.assertEqual(len(tail), 8)                                         # clipped to what is stored
        self.assertEqual(self.l.request(Q.CMD_GET_TRACE, struct.pack("<II", total, 10)).payload, b"")
        self.assertEqual(self.l.get_trace(7), self.l.get_trace(total)[:7])          # exactly what was asked
        self.assertEqual(r.f["irq_count"], 1)
        self.assertEqual(record_v2.validity(r, [35]), (True, []))

    def test_trace_pmu_and_store_policy(self):
        r, t = self.trace_run(Q.TraceConfig(Q.MODE_QREAD_PMU, 4, 12), [35, 48])
        self.assertEqual(Q.integrity(t, 4096), [])
        self.assertEqual(r.f["trace_words_per_sample"], 7)                      # 5 + 2 events
        self.assertTrue(all(len(s.events) == 2 for s in t.samples))
        self.assertLess(r.f["samples"], r.f["trace_polls"])                     # store only on QREAD change
        qs = [s.qread_after for s in t.samples]
        self.assertEqual(len(qs), len(set(qs)))                                 # every stored sample moved QREAD

    def checked_run(self, cfg, codes, **env):
        self.l = l = link(SIM_RESERVE="1", **env)
        l.set_instrumentation_mode(2, codes, 1)
        l.set_run_options(driver_link.WAIT_TRACE, 0, cfg.word())
        load(l, drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
        l.load_input(b"")
        self.assertEqual(l.run(), 0)
        r = l.last_measurement
        h = Q.header_from_record(r.f)
        return r, C.parse(l.get_trace(Q.n_words(h)), h, len(codes))

    def test_checked_qread_only(self):                                         # Stage 2B operator-aware pilot, P1
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_CHECKED, 4, 12), [35])   # polls faster than QREAD moves
        self.assertEqual(C.trace_class(t, 4096, 0x20007001), (C.VALID, []))
        self.assertEqual((r.f["trace_id"], r.f["trace_rejected"], r.f["trace_unaccepted"]), (0x20007001, 0, 0))
        self.assertEqual(r.f["trace_words"], sum(4 + 3 * len(x.slots) for x in t.samples))   # all first-read
        # the reserve take's sample is kept, flagged, and outside the window; then the start sample (QSIZE)
        self.assertEqual([(x.job, x.start) for x in t.samples[:2]], [(False, False), (True, True)])
        self.assertTrue(t.samples[0].final)
        self.assertEqual(t.qsize(), 4096)
        job = t.job()
        self.assertEqual(job[-1].qread_after.value, 4096)
        self.assertTrue(job[-1].final)
        self.assertTrue(all(sl.first_ok for x in t.samples for sl in x.slots))
        self.assertEqual([sl.offset for sl in job[0].slots], [0x18, 0x04, 0x18])
        # store policy: the sample right before every QREAD change is kept, so consecutive values are one poll apart
        q = [x.qread_after.value for x in job]
        changes = [i for i in range(1, len(job)) if q[i] != q[i - 1]]
        self.assertGreater(len(changes), 50)
        gaps = [Q.elapsed(job[i - 1].t_before, job[i].t_before) for i in changes]
        self.assertLess(max(gaps), 40)                                         # one poll (~28 cycles here)
        self.assertLess(r.f["samples"], r.f["trace_polls"])                     # unchanged polls are not kept

    def test_checked_recovered_and_kept(self):
        # trace.c read 20 = STATUS of the second job sample (2 ID reads at begin, 6 in the reserve sample, 2 for QSIZE,
        # 6 in the first job sample): it returns the ID read's data, is rejected and re-read once
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_CHECKED, 6, 12), [35], SIM_STALE_AT="20")
        self.assertEqual(C.trace_class(t, 4096, 0x20007001), (C.RECOVERED, []))
        self.assertEqual((r.f["trace_rejected"], r.f["trace_unaccepted"]), (1, 0))
        rej = C.rejected_attempts(t)
        self.assertEqual(len(rej), 1)
        self.assertEqual((rej[0]["offset"], rej[0]["value"], rej[0]["value_is_id"], rej[0]["accepted_later"]),
                         (0x04, 0x20007001, True, True))
        st = t.job()[1].status
        self.assertEqual((len(st.attempts), st.accepted, st.first_ok), (2, True, False))
        self.assertEqual(st.attempts[0], (0x20007001, 0x20007001))             # the first read is in the raw data

    def test_checked_stale_id_read(self):
        # read 19 = the ID read before the second job sample's STATUS: it returns the QREAD just read; rejected, re-read
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_CHECKED, 6, 12), [35], SIM_STALE_AT="19")
        self.assertEqual(C.trace_class(t, 4096, 0x20007001), (C.RECOVERED, []))
        rej = C.rejected_attempts(t)
        self.assertEqual([(x["offset"], x["id_read_ok"], x["id_read_is_prev_value"]) for x in rej], [(0x04, False, True)])

    def test_checked_qread_below_the_same_samples_first(self):
        # QREAD read 6 = the second job sample's second QREAD, 16 B behind its first: rejected and re-read
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_CHECKED, 6, 12), [35], SIM_QREAD_DIP="6")
        self.assertEqual(C.trace_class(t, 4096, 0x20007001), (C.RECOVERED, []))
        rej = C.rejected_attempts(t)
        self.assertEqual([(x["offset"], x["value_is_id"], x["id_read_ok"]) for x in rej], [(0x18, False, True)])

    def test_checked_unrecovered_is_invalid(self):
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_CHECKED, 6, 12), [35], SIM_STALE_AT="17,6")
        cls, why = C.trace_class(t, 4096, 0x20007001)
        self.assertEqual(cls, C.INVALID)
        self.assertIn("unaccepted_read", why)
        self.assertEqual(r.f["trace_unaccepted"], 1)
        self.assertEqual(len(t.job()[1].qread_before.attempts), 3)              # the first read and two re-reads

    def test_checked_pmu(self):
        r, t = self.checked_run(Q.TraceConfig(Q.MODE_QREAD_PMU_CHECKED, 6, 12), [35, 48], SIM_TRACE_SLOT0="1")
        self.assertEqual(C.trace_class(t, 4096, 0x20007001), (C.VALID, []))
        self.assertEqual([sl.offset for sl in t.job()[0].slots], [0x18, 0x04, 0x1300, 0x1304, 0x18])
        ev = [[sl.value for sl in x.events] for x in t.job()]
        self.assertTrue(all(b >= a for x, y in zip(ev, ev[1:]) for a, b in zip(x, y)))
        self.assertGreater(ev[-1][1], ev[0][1])

    def test_legacy_trace_shows_the_reserve_sample(self):
        # the pilot of boots 325-326: in the legacy modes the reserve take's sample opens the trace (board: 40/40 RUNs)
        self.l = l = link(SIM_RESERVE="1")
        l.set_instrumentation_mode(2, [35], 1)
        l.set_run_options(driver_link.WAIT_TRACE, 0, Q.TraceConfig(Q.MODE_QREAD_ONLY, 6).word())
        load(l, drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
        l.load_input(b"")
        for _ in range(2):
            self.assertEqual(l.run(), 0)
        h = Q.header_from_record(l.last_measurement.f)
        t = Q.parse(l.get_trace(Q.n_words(h)), h)
        self.assertEqual(t.samples[0].qread_after, 4096)                       # the previous RUN's stream end
        self.assertIn("qread_decreasing", Q.integrity(t, 4096))

    def test_trace_option_refusals_and_state(self):
        self.l = l = link()
        def nack(fn, detail):
            with self.assertRaises(rp.Nack) as c:
                fn()
            self.assertEqual(c.exception.code, 6, detail)                      # RANGE (detail 3/4 not on the host side)
        nack(lambda: l.set_run_options(driver_link.WAIT_WFE, 0, Q.TraceConfig(1).word()), 4)   # trace without WAIT_TRACE
        nack(lambda: l.set_run_options(driver_link.WAIT_TRACE, 0, driver_link.TRACE_OFF), 4)   # WAIT_TRACE, no trace
        nack(lambda: l.set_run_options(driver_link.WAIT_TRACE, 0, 0x80000001), 3)               # reserved bits
        nack(lambda: l.set_run_options(driver_link.WAIT_TRACE, 0, 5), 3)                        # unknown mode
        with self.assertRaises(rp.Nack) as c:
            l.request(Q.CMD_GET_TRACE, struct.pack("<II", 0, 10))                                # no RUN yet
        self.assertEqual(c.exception.code, 5)
        load(l, drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
        l.load_input(b"")
        with self.assertRaises(rp.Nack) as c:
            l.request(Q.CMD_GET_TRACE, struct.pack("<II", 0, 10))                                # input ready, no RUN
        self.assertEqual(c.exception.code, 5)

    def test_output_mismatch_is_reported_not_invalid(self):
        self.l = l = link()
        l.set_instrumentation_mode(2, [35], 1)
        good = expected_output(IFM, 0, 30)
        bad = bytearray(good); bad[4] ^= 0x7F; bad[9] = (bad[9] - 3) & 0xFF
        s8 = lambda b: b - 256 if b > 127 else b
        want_max = max(abs(s8(a) - s8(b)) for a, b in zip(good, bad))
        load(l, drwl.pack(simm([40], [30]), [IFM], [bytes(bad)]))
        l.load_input(b"")
        l.run()
        r = l.last_measurement
        self.assertEqual((r.f["ofm_mismatch"], r.f["ofm_first"], r.f["ofm_max_diff"]), (2, 4, want_max))
        self.assertEqual(want_max, 103)                                          # 12 vs 12 ^ 0x7F = 115
        self.assertFalse(r.valid_flags & record_v2.OUTPUT_MATCH)
        self.assertEqual(record_v2.validity(r, [35]), (True, []))

    def test_signed_difference(self):
        self.l = l = link()
        l.set_instrumentation_mode(2, [35], 1)
        ifm = bytes([126]) + IFM[1:]                                             # output byte 0 = 127
        gold = bytearray(expected_output(ifm, 0, 30)); gold[0] = 0x80            # -128: |127 - (-128)| = 255
        load(l, drwl.pack(simm([40], [30]), [ifm], [bytes(gold)]))
        l.load_input(b"")
        l.run()
        self.assertEqual((l.last_measurement.f["ofm_mismatch"], l.last_measurement.f["ofm_max_diff"]), (1, 255))


class Failures(unittest.TestCase):
    def run_with(self, env, codes=(35,)):
        l = link(**env)
        try:
            l.set_instrumentation_mode(2, list(codes), 1)
            load(l, drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
            l.load_input(b"")
            l.run()
            return l.last_measurement
        finally:
            l._ser.close()

    def test_flags_follow_the_hooks(self):
        cases = {"SIM_INVOKE_FAIL": {"invoke_ok", "one_arm", "one_irq", "run_rc"},
                 "SIM_NO_IRQ": {"one_irq"}, "SIM_TWO_IRQ": {"one_irq"}, "SIM_OVF": {"no_overflow"}}
        for env, want in cases.items():
            r = self.run_with({env: "1"})
            ok, failed = record_v2.validity(r, [35])
            self.assertFalse(ok, env)
            self.assertTrue(want <= set(failed), (env, failed))

    def test_refusals(self):
        l = link()
        try:
            def nack(fn, code):
                with self.assertRaises(rp.Nack) as c:
                    fn()
                self.assertEqual(c.exception.code, code)
            nack(lambda: l.run(), 5)                                             # STATE: nothing loaded
            nack(lambda: l.request(0x7E), 2)                                     # BAD_COMMAND
            nack(lambda: l.request(0x05, b"\0" * 12), 3)                         # LENGTH
            nack(lambda: l.set_instrumentation_mode(1, [35]), 6)                 # END_ONLY is not offered
            nack(lambda: l.set_run_options(5), 6)                                # no such wait mode
            nack(lambda: l.set_instrumentation_mode(0, [35]), 6)                 # OFF with events
            nack(lambda: l.request(0x05, struct.pack("<11I", 2, 1, 9, *([35] * 8))), 6)   # 9 slots
            nack(lambda: l.request(0x05, struct.pack("<11I", 2, 1, 1, 0x400, *([0] * 7))), 6)  # id > 10 bits
            nack(lambda: l.load_model_begin(1 << 30, 0), 6)                      # bigger than staging
            blob = drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)])
            l.load_model_begin(len(blob), zlib.crc32(blob) ^ 1)
            l.load_model_chunk(0, blob)
            nack(lambda: l.load_model_end(), 8)                                  # MODEL_CRC
            for bad, status in ((drwl.pack(simm([40], [30]), [IFM], [b"x" * 31]), 0x500 + 1),   # OFM size
                                (drwl.pack(simm([40], [30, 2]), [IFM], [b"x" * 30]), 0x400),    # output count
                                (drwl.pack(b"NOPE" * 4, [IFM], [b"x"]), 0x300 + 1)):            # model init
                l.load_model_begin(len(bad), zlib.crc32(bad))
                l.load_model_chunk(0, bad)
                with self.assertRaises(rp.Nack) as c:
                    l.load_model_end()
                self.assertEqual(c.exception.code, 9)
                self.assertEqual(l.capabilities()["load_status"], status)
            mis = bytearray(blob); struct.pack_into("<I", mis, 64, struct.unpack_from("<I", mis, 64)[0] + 4)
            l.load_model_begin(len(mis), zlib.crc32(mis))                        # IFM offset off its 16-B grid
            l.load_model_chunk(0, bytes(mis))
            with self.assertRaises(rp.Nack):
                l.load_model_end()
            self.assertEqual(l.capabilities()["load_status"], 0x100 + 6)
            l._ser.write(rp.build_frame(0x01, 99)[:-1] + b"\0")                  # a frame with a broken CRC
            self.assertEqual(l.ping().bad_crc, 1)
            l.load_model_begin(len(blob), zlib.crc32(blob))
            nack(lambda: l.load_model_chunk(8, blob[8:16]), 7)                   # a gap
            nack(lambda: l.load_model_begin(len(blob), 0), 5)                    # not while loading
        finally:
            l._ser.close()


if __name__ == "__main__":
    unittest.main()


class BoardScript(unittest.TestCase):
    """host/board/run_driver_events.py end to end against the simulator; the analyses' loader reads its output."""

    def test_campaign_traces(self):
        sys.path.insert(0, str(REPO / "host" / "board"))
        import run_driver_events as R
        links = []
        R.DriverLink = lambda port: links.append(link()) or links[-1]
        word = Q.TraceConfig(Q.MODE_QREAD_PMU, 6).word()
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "w.drwl").write_bytes(drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
            (d / "ids.txt").write_text("35 48\n")
            argv = ["x", "--out", str(d / "out"), "--host-boot-index", "7", "--workload", str(d / "w.drwl"),
                    "--ids", f"@{d / 'ids.txt'}", "--repeats", "2", "--wait-mode", "2", "--trace-word", hex(word),
                    "--image-sha256", "b,r,d,i"]
            old, sys.argv = sys.argv, argv
            try:
                self.assertEqual(R.main(), 0)
            finally:
                sys.argv = old
            raw = json.loads((d / "out" / "raw_runs.json").read_text())
            for x in raw[1:]:
                b = (d / "out" / "traces" / f"set{x['set_id']}_rep{x['rep']}.bin").read_bytes()
                t = Q.parse(list(struct.unpack(f"<{len(b) // 4}I", b)), Q.header_from_record(x["record"]))
                self.assertEqual(Q.integrity(t, 4096), [])
            self.assertEqual(json.loads((d / "out" / "summary.json").read_text())["trace_word"], word)
            argv[argv.index("2", argv.index("--wait-mode"))] = "0"                 # trace word without WAIT_TRACE
            sys.argv = argv
            try:
                with self.assertRaises(SystemExit):
                    R.main()
            finally:
                sys.argv = old
        for l in links:
            l._ser.close()

    def test_campaign_outputs(self):
        sys.path.insert(0, str(REPO / "host" / "board"))
        import run_driver_events as R
        links = []
        R.DriverLink = lambda port: links.append(link()) or links[-1]
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            want = expected_output(IFM, 0, 30)
            (d / "w.drwl").write_bytes(drwl.pack(simm([40], [30]), [IFM], [want]))
            (d / "cond.txt").write_text("wfe 0 0 off all\n")
            argv = ["x", "--out", str(d / "out"), "--host-boot-index", "7", "--workload", str(d / "w.drwl"),
                    "--ids", "35,48", "--repeats", "2", "--conditions", f"@{d / 'cond.txt'}", "--outputs",
                    "--image-sha256", "b,r,d,i"]
            old, sys.argv = sys.argv, argv
            try:
                self.assertEqual(R.main(), 0)
            finally:
                sys.argv = old
            raw = json.loads((d / "out" / "wfe" / "raw_runs.json").read_text())[1:]
            self.assertEqual({(x["output_crc32"], x["output_len"]) for x in raw}, {(zlib.crc32(want), 30)})
            self.assertEqual((d / "out" / "wfe" / "output.bin").read_bytes(), want)
        for l in links:
            l._ser.close()

    def test_campaign_conditions(self):
        sys.path.insert(0, str(REPO / "host" / "board"))
        import run_driver_events as R
        links = []
        R.DriverLink = lambda port: links.append(link()) or links[-1]
        word = Q.TraceConfig(Q.MODE_QREAD_ONLY, 6).word()
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "w.drwl").write_bytes(drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
            (d / "ids.txt").write_text("35 17\n35 48\n")
            (d / "cond.txt").write_text(f"# c\nwfe 0 0 off all\nbusy 1 0 off 1\ntrace 2 0 {word:#x} 2\n")
            argv = ["x", "--out", str(d / "out"), "--host-boot-index", "7", "--workload", str(d / "w.drwl"),
                    "--ids", f"@{d / 'ids.txt'}", "--repeats", "2", "--conditions", f"@{d / 'cond.txt'}",
                    "--image-sha256", "b,r,d,i"]
            old, sys.argv = sys.argv, argv
            try:
                self.assertEqual(R.main(), 0)
            finally:
                sys.argv = old
            o = d / "out"
            sets = {c: sorted({(x["set_id"], x["record"]["wait_mode"]) for x in json.loads((o / c / "raw_runs.json")
                                                                                         .read_text())[1:]})
                    for c in ("wfe", "busy", "trace")}
            self.assertEqual(sets, {"wfe": [(1, 0), (2, 0)], "busy": [(1, 1)], "trace": [(2, 2)]})
            self.assertEqual(sorted(p.name for p in (o / "trace" / "traces").iterdir()), ["set2_rep1.bin", "set2_rep2.bin"])
            self.assertFalse((o / "wfe" / "traces").exists())
            self.assertEqual(links[0].last_measurement.run_sequence, 2 * 2 + 2 + 2)  # one load, 8 RUNs, one boot
            self.assertFalse((o / "wfe" / "output.bin").exists())                # outputs only with --outputs
            row = next(csv.DictReader(open(o / "busy" / "runs.csv")))
            self.assertEqual(row["condition"], "busy")
        for l in links:
            l._ser.close()
        for bad in ("a 0 0 off\n", "a 2 0 off all\n", "a 0 0 0x1 all\n", "a 0 0 off all\na 1 0 off all\n",
                    "a/b 0 0 off all\n", "a 3 0 off all\n"):
            with self.assertRaises(ValueError, msg=bad):
                R.parse_conditions(bad)

    def test_campaign_files(self):
        sys.path.insert(0, str(REPO / "host" / "board")); sys.path.insert(0, str(REPO / "host" / "analysis"))
        import run_driver_events as R
        import fi101_s013 as S
        links = []
        R.DriverLink = lambda port: links.append(link()) or links[-1]
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "w.drwl").write_bytes(drwl.pack(simm([40], [30]), [IFM], [expected_output(IFM, 0, 30)]))
            (d / "ids.txt").write_text("35 48\n35 51 53\n")
            argv = ["x", "--out", str(d / "out"), "--host-boot-index", "7", "--workload", str(d / "w.drwl"),
                    "--ids", f"@{d / 'ids.txt'}", "--repeats", "3", "--wait-mode", "1",
                    "--image-sha256", "b,r,d,i"]
            old, sys.argv = sys.argv, argv
            try:
                self.assertEqual(R.main(), 0)
            finally:
                sys.argv = old
            caps = json.loads((d / "out" / "capabilities.json").read_text())
            self.assertEqual(caps["magic"], record_v2.CAPS_MAGIC)
            runs = S.load_runs(d / "out", 1)                                     # reps 2, 3 of both sets
            self.assertEqual(sorted(runs), [(1, 2), (1, 3), (2, 2), (2, 3)])
            self.assertEqual(runs[(1, 2)]["ev"], {35: 350, 48: 481})
            self.assertEqual(runs[(2, 3)]["ev"], {35: 350, 51: 511, 53: 532})
            self.assertTrue(all(v["valid"] for v in runs.values()))
            self.assertEqual({v["infer"] for v in runs.values()}, {(1 << 32) + 5000})
            self.assertEqual({v["infer_cpu"] for v in runs.values()}, {777})
            row = next(csv.DictReader(open(d / "out" / "runs.csv")))
            self.assertEqual((row["wait_mode"], row["output_match"], row["boot_sha256"], row["runner"]),
                             ("1", "1", "b", "driver_runner"))
            raw = json.loads((d / "out" / "raw_runs.json").read_text())
            self.assertEqual(len(raw), 1 + 2 * 3)
        for l in links:
            l._ser.close()
