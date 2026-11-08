import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import s2b3_windows as W

S_A = 1000
CYC = {-1: 100, 0: S_A, 1: 300, 2: 0}
CTL_CPU = {3: 9950, 4: 10000, 5: 10050}             # control CPU cycles: width 1 % -> tolerance 1 %


def runs(mac, cpu=10000, valid=True, reps=(3, 4, 5), npu=5000, extra=None):
    """mac: one value for every RUN or {rep: value}; sets 1 (mac_active 48) and 2 (event 131)."""
    out = {}
    for rep in reps:
        v = mac[rep] if isinstance(mac, dict) else mac
        c = cpu[rep] if isinstance(cpu, dict) else cpu
        out[(1, rep)] = dict(ev={48: v, 35: 2000, **(extra or {})}, valid=valid, infer=npu, infer_cpu=c)
        out[(2, rep)] = dict(ev={131: 7}, valid=valid, infer=npu, infer_cpu=c)
    return out


def arms(prev=50, a=1200, b=300, nxt=10, **over):
    base = dict(ctl=runs(0, cpu=CTL_CPU), ctl2=runs(0), w_prev=runs(prev), w_A=runs(a), w_B=runs(b),
                w_next=runs(nxt), u=runs(1560))
    base.update(over)
    return base


def ofm(arms_, sig=("0", "0")):
    return {k: {sig} for k in arms_}


class Diagnose(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(W.diagnose({-1: 50, 0: 1200, 1: 300, 2: 10}, S_A), ("WINDOW_LOCALIZED", 0))
        self.assertEqual(W.diagnose({-1: 50, 0: 300, 1: 1200, 2: 10}, S_A), ("WINDOW_LOCALIZED", 1))
        self.assertEqual(W.diagnose({-1: 600, 0: 600, 1: 0, 2: 0}, S_A), ("WINDOW_SPLIT", None))
        self.assertEqual(W.diagnose({-1: 0, 0: 1000, 1: 1000, 2: 0}, S_A), ("WINDOW_AMBIGUOUS", None))
        self.assertEqual(W.diagnose({-1: 0, 0: 1000, 1: 999, 2: 0}, S_A), ("WINDOW_LOCALIZED", 0))  # rest < S
        self.assertEqual(W.diagnose({-1: 500, 0: 1000, 1: 500, 2: 0}, S_A), ("WINDOW_AMBIGUOUS", None))  # rest = S
        self.assertEqual(W.diagnose({-1: 0, 0: 999, 1: 0, 2: 0}, S_A), ("NOT_IDENTIFIABLE", None))
        self.assertEqual(W.diagnose({-1: 0, 0: 999, 1: 1, 2: 0}, S_A), ("WINDOW_SPLIT", None))         # T = S

    def test_static(self):
        self.assertTrue(W.identifiable(CYC))
        self.assertFalse(W.identifiable({-1: 0, 0: 1000, 1: 1000, 2: 0}))
        self.assertFalse(W.identifiable({-1: 0, 0: 1000, 1: 0, 2: 1001}))


class Model(unittest.TestCase):
    def test_localized_and_split(self):
        a = arms()
        self.assertEqual(W.model_result(a, ofm(a), CYC)[:2], ("WINDOW_LOCALIZED", 0))
        a = arms(prev=600, a=600, b=0)
        self.assertEqual(W.model_result(a, ofm(a), CYC)[:2], ("WINDOW_SPLIT", None))

    def test_static_not_identifiable_wins(self):
        a = arms()
        self.assertEqual(W.model_result(a, ofm(a), {-1: 0, 0: 1000, 1: 1000, 2: 0})[0], "NOT_IDENTIFIABLE")

    def test_unstable(self):
        a = arms(a={3: 1200, 4: 1200, 5: 900}, prev={3: 50, 4: 50, 5: 150})   # rep 5 splits
        self.assertEqual(W.model_result(a, ofm(a), CYC)[0], "UNSTABLE")

    def test_preconditions(self):
        a = arms()
        self.assertEqual(W.model_result(dict(a, w_B={}), ofm(a), CYC)[0], "UNPROVEN")                      # missing
        a2 = dict(a, w_A=runs(1200, valid=False))
        self.assertEqual(W.model_result(a2, ofm(a2), CYC)[0], "UNPROVEN")                                   # invalid
        a3 = dict(a, w_A_wait=runs(1200, valid=False))
        self.assertEqual(W.model_result(a3, ofm(a3), CYC)[0], "UNPROVEN")                                   # optional arm
        a4 = dict(a, ctl2=runs(0, npu=5100))                                                                # A/A, 2 %
        self.assertEqual(W.model_result(a4, ofm(a4), CYC)[0], "UNPROVEN")
        a5 = dict(a, ctl2=runs(0, npu=5000, reps=(3, 4, 5), extra={48: 0}))
        self.assertEqual(W.model_result(a5, ofm(a5), CYC)[0], "WINDOW_LOCALIZED")
        a6 = dict(a, u=runs(1560, cpu=10110))                                                               # 1.1 %
        self.assertEqual(W.model_result(a6, ofm(a6), CYC)[0], "UNPROVEN")
        a7 = dict(a, u=runs(1560, cpu=10090))                                                               # 0.9 % ok
        self.assertEqual(W.model_result(a7, ofm(a7), CYC)[0], "WINDOW_LOCALIZED")
        a8 = dict(a, w_B_wait=runs(300, cpu=9880))
        self.assertEqual(W.model_result(a8, ofm(a8), CYC)[0], "UNPROVEN")                                   # wait arm too
        self.assertEqual(W.model_result(dict(a, ctl2=runs(0, cpu=10110)), ofm(a), CYC)[0], "UNPROVEN")     # ctl2 cpu
        self.assertEqual(W.model_result(dict(a, ctl=runs(0, cpu={3: 9000, 4: 10000, 5: 11000})), ofm(a), CYC)[0],
                         "UNPROVEN")                                                                          # CPU noisy

    def test_ofm(self):
        a = arms()
        o = ofm(a)
        self.assertEqual(W.model_result(a, dict(o, w_A={("1", "2")}), CYC)[0], "UNPROVEN")
        two = {k: {("0", "0"), ("1", "2")} for k in a}                                   # every arm alike, but
        self.assertEqual(W.model_result(a, two, CYC)[0], "UNPROVEN")                     # ctl itself varies
        self.assertEqual(W.model_result(a, ofm(a, ("955", "7")), CYC)[0], "WINDOW_LOCALIZED")              # same as ctl

    def test_missing_key_in_ctl2(self):
        a = arms()
        ctl2 = {k: dict(v, ev={e: x for e, x in v["ev"].items() if e != 131}) for k, v in runs(0).items()}
        self.assertEqual(W.model_result(dict(a, ctl2=ctl2), ofm(a), CYC)[0], "UNPROVEN")

    def test_no_common_reps_or_union_missing(self):
        a = arms()
        a["w_A"] = runs(1200, reps=(6, 7, 8))
        self.assertEqual(W.model_result(a, ofm(a), CYC)[0], "UNSTABLE")                  # nothing to pair
        a = arms()
        del a["u"]
        self.assertEqual(W.model_result(a, ofm(a), CYC)[0], "UNPROVEN")

    def test_per_run_pairs_reps(self):
        a = arms(a={3: 1200, 4: 1300, 5: 1250})
        self.assertEqual(sorted(W.per_run(a)), [3, 4, 5])
        self.assertEqual(W.per_run(a)[4][0], 1300)


if __name__ == "__main__":
    unittest.main()
