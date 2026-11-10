"""qread_pilot.py on a pilot boot produced end to end by the simulator (firmware trace code, DriverLink, the board
script's --conditions), plus the rules on synthetic numbers."""
import json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
for d in ("analysis", "lib", "tests", "board"):
    sys.path.insert(0, str(REPO / "host" / d))
import drwl
import qread_pilot as P
import qread_trace as Q
import test_driver_runner_sim as SIM
from test_cms_timeline import S          # four kernel ops, 312 bytes

CONDS = ("wfe 0 0 off 1,2,3\nbusy 1 0 off 1\n"
         f"t06 2 0 {Q.TraceConfig(1, 6).word():#x} 1\nt10 2 0 {Q.TraceConfig(1, 10).word():#x} 1\n"
         f"t14 2 0 {Q.TraceConfig(1, 14).word():#x} 1\np10 2 0 {Q.TraceConfig(2, 10).word():#x} 2\n")


def setUpModule():
    SIM.setUpModule()


def tearDownModule():
    SIM.tearDownModule()


class Pilot(unittest.TestCase):
    def boot(self, d, **env):
        import run_driver_events as R
        links, primes = [], []
        R.DriverLink = lambda port: links.append(SIM.link(SIM_CMS_LEN=str(len(S)), **env)) or links[-1]
        real_prime = R.prime
        R.prime = lambda link, blob: primes.append(1) or real_prime(link, blob)
        (d / "w.drwl").write_bytes(drwl.pack(SIM.simm([40], [30]), [SIM.IFM], [SIM.expected_output(SIM.IFM, 0, 30)]))
        (d / "ids.txt").write_text("35 17\n35 48 51 53 55 64 80 81\n35 128 130 132 135 384 386 391\n")
        (d / "cond.txt").write_text(CONDS)
        (d / "m.cms.bin").write_bytes(S)
        argv = ["x", "--out", str(d / "boot"), "--host-boot-index", "1", "--workload", str(d / "w.drwl"),
                "--ids", f"@{d / 'ids.txt'}", "--repeats", "5", "--conditions", f"@{d / 'cond.txt'}",
                "--image-sha256", "b,r,d,i"]
        old, sys.argv = sys.argv, argv
        try:
            self.assertEqual(R.main(), 0)
        finally:
            sys.argv, R.prime = old, real_prime
        for l in links:
            l._ser.close()
        self.assertEqual(len(primes), 1)                                            # one upload for six conditions
        return P.main(str(d / "boot"), str(d / "m.cms.bin"), str(d / "out"))

    def test_perturbed_trace(self):
        with tempfile.TemporaryDirectory() as d:
            res = self.boot(pathlib.Path(d), SIM_TRACE_SLOT0="1")                  # polling "moves" NPU_ACTIVE
            self.assertEqual(res["P1"], "UNRESOLVED")
            self.assertEqual((res["t06"]["perturbation"], res["t06"]["verdict"]), ("EFFECTIVE", "TRACE_PERTURBED"))

    def test_events_moved_after_irq(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            self.boot(d)
            raw = json.loads((d / "boot" / "p10" / "raw_runs.json").read_text())
            raw[-1]["record"]["ev_irq1"] -= 1                                      # the IRQ read one count lower
            (d / "boot" / "p10" / "raw_runs.json").write_text(json.dumps(raw))
            self.assertEqual(P.events_at_end(d / "boot" / "p10", 1), "EVENTS_MOVED_AFTER_IRQ")

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            res = self.boot(d)
            self.assertEqual(res["P1"], "UNRESOLVED")                               # same simulated timing
            self.assertEqual(res["t06"]["perturbation"], "UNRESOLVED")
            self.assertEqual(res["t06"]["verdict"], "TRACE_VALID")                  # every op boundary seen alone
            self.assertEqual(res["t14"]["verdict"], "TRACE_UNOBSERVABLE")           # one poll before the end
            self.assertEqual(len(res["t06"]["run_verdicts"]), 4)                    # 5 RUNs, 1 warm-up
            self.assertEqual(res["P3_events"], "EVENTS_AT_END")
            self.assertTrue((d / "out" / "t06" / "set1_rep2" / "brackets.csv").exists())
            self.assertEqual(json.loads((d / "out" / "summary.json").read_text())["P1"], "UNRESOLVED")


class Rules(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(P.compare([100, 101], [101, 102])[0], "UNRESOLVED")          # 1 apart, 1 % floor 1.015
        self.assertEqual(P.compare([100, 100], [103, 103])[0], "EFFECTIVE")
        self.assertEqual(P.compare([100, 104], [103, 103])[0], "UNRESOLVED")          # inside the 4-cycle RUN range
        self.assertEqual(P.compare([100, 110], [108, 108])[0], "UNRESOLVED")          # 3 apart: floor 1.08, range 10
        self.assertEqual(P.compare([], [1])[0], "UNPROVEN")

    def test_wait_effect_needs_both(self):
        a = {(1, 2): dict(ev={35: 100}, infer=200), (1, 3): dict(ev={35: 100}, infer=200)}
        b = {(1, 2): dict(ev={35: 100}, infer=230), (1, 3): dict(ev={35: 100}, infer=230)}
        self.assertEqual(P.wait_effect(a, b)[0], "EFFECTIVE")                         # NPU_EXECUTION moved
        self.assertEqual(P.wait_effect(a, a)[0], "UNRESOLVED")
        self.assertEqual(P.wait_effect(a, {})[0], "UNPROVEN")

    def test_worst(self):
        self.assertEqual(P.worst(["TRACE_VALID", "TRACE_COARSE"]), "TRACE_COARSE")
        self.assertEqual(P.worst(["TRACE_VALID", "TRACE_INVALID", "TRACE_PERTURBED"]), "TRACE_INVALID")
        self.assertEqual(P.worst(["TRACE_VALID", "UNPROVEN"]), "TRACE_VALID")
        self.assertEqual(P.worst([]), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
