"""qread_op_pilot.py on boots produced end to end by the simulator (checked trace firmware, DriverLink, the board
script's --conditions) over yolo's real command stream, plus the rules on synthetic numbers."""
import json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
for d in ("analysis", "lib", "tests", "board"):
    sys.path.insert(0, str(REPO / "host" / d))
import drwl
import qread_checked as C
import qread_op_pilot as P
import qread_trace as Q
import test_driver_runner_sim as SIM

CMS = REPO / "evidence/qread_pilot/workloads/yolo-fastest_192_face_v4.drwl.cms.bin"   # 21,056 B, ops 99/100 inside
NPU_ID = 0x20007001
IDS = "35 17\n35 48 51 53 55 64 80 81\n35 128 130 132 135 384 386 391\n35 48 81 387\n"
P12 = f"base 0 0 off 1,2,3\nq06 2 0 {Q.TraceConfig(3, 6, 12).word():#x} 1,2,3\n"
P3 = f"pbase 0 0 off 4\np06 2 0 {Q.TraceConfig(4, 6, 12).word():#x} 4\n"


def setUpModule():
    SIM.setUpModule()


def tearDownModule():
    SIM.tearDownModule()


def boot(d: pathlib.Path, conds: str, **env) -> pathlib.Path:
    import run_driver_events as R
    links = []
    R.DriverLink = lambda port: links.append(SIM.link(SIM_CMS_LEN=str(CMS.stat().st_size), SIM_RESERVE="1",
                                                      **env)) or links[-1]
    (d / "w.drwl").write_bytes(drwl.pack(SIM.simm([40], [30]), [SIM.IFM], [SIM.expected_output(SIM.IFM, 0, 30)]))
    (d / "ids.txt").write_text(IDS)
    (d / "cond.txt").write_text(conds)
    argv = ["x", "--out", str(d / "boot"), "--host-boot-index", "1", "--workload", str(d / "w.drwl"),
            "--ids", f"@{d / 'ids.txt'}", "--repeats", "5", "--conditions", f"@{d / 'cond.txt'}",
            "--image-sha256", "b,r,d,i"]
    old, sys.argv = sys.argv, argv
    try:
        assert R.main() == 0
    finally:
        sys.argv = old
    for l in links:
        l._ser.close()
    return d / "boot"


class EndToEnd(unittest.TestCase):
    def test_valid_observed_associated(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").mkdir()
            res = P.p12(str(boot(d / "a", P12)), str(CMS), NPU_ID, str(d / "out12"))
            self.assertEqual(res["P1"], C.VALID)
            self.assertEqual(len(res["P1_runs"]), 12)                                  # 3 sets x 4 measured
            self.assertEqual(res["kernel_offsets"], {99: 18980, 100: 19136})
            self.assertEqual(res["P2"], P.OBSERVED)
            r = res["P2_runs"]["set1_rep2"]
            self.assertTrue(r["separated"])
            self.assertLess(r["brackets"][99]["hi"], r["brackets"][100]["hi"])
            ds = res["P1_descriptive"]
            self.assertEqual(ds["rejected_attempts"], [])
            self.assertEqual(ds["samples_with_qread_0"], ds["of_them_status_running"])   # QREAD 0 while running
            self.assertTrue(all(abs(v["diff_pct"]) < 1e-9 for v in res["P1_perturbation"].values()))
            (d / "c").mkdir()
            res3 = P.p3(str(boot(d / "c", P3)), str(CMS), NPU_ID, str(d / "out3"), str(d / "out12" / "summary.json"))
            self.assertEqual(res3["P3"], P.ASSOCIATED, res3.get("terms"))
            iv = res3["intervals"]["set4_rep2"]
            self.assertTrue(iv and all(x["first_read"] for x in iv))
            self.assertEqual(len(iv[0]["d_events"]), 4)
            # the same p06 data against a q06 whose brackets were 3x narrower: the resolution is not kept
            s12 = json.loads((d / "out12" / "summary.json").read_text())
            for r in s12["P2_runs"].values():
                for op in ("99", "100"):
                    r["brackets"][op]["width"] = r["brackets"][op]["width"] / 3
            (d / "narrow.json").write_text(json.dumps(s12))
            res3 = P.p3(str(d / "c" / "boot"), str(CMS), NPU_ID, str(d / "out3n"), str(d / "narrow.json"))
            self.assertEqual((res3["P3"], res3["terms"]["resolution_kept"]), ("NOT_ASSOCIATED", False))
            self.assertNotIn("intervals", res3)

    def test_recovered_reads(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").mkdir()
            res = P.p12(str(boot(d / "a", P12, SIM_STALE_EVERY="997")), str(CMS), NPU_ID, str(d / "o"))
            self.assertEqual(res["P1"], C.RECOVERED)
            self.assertTrue(all(c == C.RECOVERED for c, _ in res["P1_runs"].values()))
            rej = res["P1_descriptive"]["rejected_attempts"]
            self.assertTrue(rej and all(x["accepted_later"] for x in rej))
            self.assertTrue(all(x["value_is_id"] or not x["id_read_ok"] for x in rej))   # either kind of stale read
            self.assertIn(res["P2"], (P.OBSERVED, P.COARSE))

    def test_unrecovered_is_invalid_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").mkdir()
            res = P.p12(str(boot(d / "a", P12, SIM_STALE_EVERY="4001,6")), str(CMS), NPU_ID, str(d / "o"))
            self.assertEqual(res["P1"], C.INVALID)
            self.assertIn("unaccepted_read", res["P1_runs"]["set1_rep2"][1])
            self.assertEqual(res["P2"], P.NOT_RUN)
            (d / "s.json").write_text(json.dumps(res, default=str))
            self.assertEqual(P.p3(str(d / "a" / "boot"), str(CMS), NPU_ID, str(d / "o3"), str(d / "s.json"))["P3"],
                             P.NOT_RUN)

    def test_perturbed(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").mkdir()
            res = P.p12(str(boot(d / "a", P12, SIM_TRACE_SLOT0="1")), str(CMS), NPU_ID, str(d / "o"))
            self.assertEqual(res["P1"], P.PERTURBED)                              # polling "moves" NPU_ACTIVE
            self.assertEqual(res["P2"], P.NOT_RUN)

    def test_wrong_npu_id_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "a").mkdir()
            res = P.p12(str(boot(d / "a", P12)), str(CMS), NPU_ID + 1, str(d / "o"))
            self.assertEqual(res["P1"], C.INVALID)
            self.assertIn("id_not_npu_id", res["P1_runs"]["set1_rep2"][1])


def run(v35, valid=True, output=True):
    return dict(ev={35: v35}, valid=valid, output=output)


class Rules(unittest.TestCase):
    def test_perturbation_floor(self):
        base = {(1, 2): run(1000), (1, 3): run(1000)}
        self.assertEqual(P.perturbation({(1, 2): run(1010), (1, 3): run(1010)}, base)[0], "UNPERTURBED")   # = 1 %
        self.assertEqual(P.perturbation({(1, 2): run(1011), (1, 3): run(1011)}, base)[0], P.PERTURBED)
        self.assertEqual(P.perturbation({(1, 2): run(989), (1, 3): run(989)}, base)[0], P.PERTURBED)
        two = {**base, (2, 2): run(500)}
        self.assertEqual(P.perturbation({(1, 2): run(1000), (2, 2): run(506)}, two)[0], P.PERTURBED)  # any set
        self.assertEqual(P.perturbation({(1, 2): run(1000)}, {})[0], P.UP)

    def test_condition_order(self):
        self.assertEqual(P.condition_verdict([C.VALID, C.INVALID], P.PERTURBED), C.INVALID)
        self.assertEqual(P.condition_verdict([C.VALID, C.RECOVERED], P.PERTURBED), P.PERTURBED)
        self.assertEqual(P.condition_verdict([C.VALID, C.RECOVERED], "UNPERTURBED"), C.RECOVERED)
        self.assertEqual(P.condition_verdict([C.VALID, C.VALID], "UNPERTURBED"), C.VALID)
        self.assertEqual(P.condition_verdict([], "UNPERTURBED"), P.UP)
        self.assertEqual(P.condition_verdict([C.VALID], P.UP), P.UP)

    def test_run_class_terms(self):
        h = dict(trace_dropped=0, trace_samples=0, trace_rejected=0, trace_unaccepted=0, trace_id=1, trace_polls=0)
        t = C.Trace(Q.TraceConfig(3), (), h, ())
        self.assertEqual(P.run_class(None, run(1), 4, 1), (C.INVALID, ["no_trace"]))
        cls, why = P.run_class(t, run(1, output=False), 4, 1)
        self.assertEqual(cls, C.INVALID)
        self.assertIn("output_mismatch", why)
        self.assertIn("no_job_samples", why)
        self.assertIn("run_not_valid", P.run_class(t, run(1, valid=False), 4, 1)[1])

    def sample(self, qb, qa, t0, ok_b=True, ok_a=True):
        def sl(v, ok):
            return C.Slot(0x18, ((NPU_ID, v),) if ok else ((NPU_ID, NPU_ID), (NPU_ID, v)), True)
        return C.Sample(True, False, False, t0, t0 + 10, (sl(qb, ok_b), C.Slot(4, ((NPU_ID, 1),), True), sl(qa, ok_a)),
                        True)

    def test_bracket_and_separation(self):
        job = (self.sample(0, 100, 0), self.sample(100, 200, 100), self.sample(200, 300, 200))
        b = P.bracket(job, 150)
        self.assertEqual((b["observed"], b["lo"], b["hi"], b["width"]), (True, 100, 110, 10))
        self.assertEqual(P.bracket(job, 300)["why"], "not_bracketed")              # never passed
        rec = (job[0], self.sample(100, 200, 100, ok_a=False), job[2])
        self.assertEqual(P.bracket(rec, 150)["why"], "recovered_endpoint")         # a re-read never decides it
        self.assertTrue(P.separated(job, 150, 250))                                # 200 lies in (150, 250]
        self.assertFalse(P.separated(job, 110, 190))
        self.assertTrue(P.separated(rec, 150, 250))                                # sample 3 read 200 at once
        only_rec = (self.sample(0, 100, 0), self.sample(100, 200, 100, ok_b=True, ok_a=False),
                    self.sample(300, 300, 200))
        self.assertFalse(P.separated(only_rec, 150, 250))                          # 200 was a re-read

    def test_boundaries_need_separation(self):
        tr = lambda job: C.Trace(Q.TraceConfig(3), job, {}, ())
        apart = (self.sample(0, 100, 0), self.sample(100, 200, 100), self.sample(200, 300, 200))
        together = (self.sample(0, 100, 0), self.sample(100, 300, 100), self.sample(300, 300, 200))
        offs = {99: 150, 100: 250}
        self.assertTrue(P.boundaries({(1, 2): tr(apart)}, offs)[0])
        ok, per = P.boundaries({(1, 2): tr(apart), (1, 3): tr(together)}, offs)   # every RUN must separate them
        self.assertFalse(ok)
        self.assertEqual((per["set1_rep3"]["brackets"][99]["observed"], per["set1_rep3"]["separated"]), (True, False))


if __name__ == "__main__":
    unittest.main()
