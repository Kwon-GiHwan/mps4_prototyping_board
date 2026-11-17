"""Stage 6C rules (evidence/stage6c/contract.md). Expected values typed by hand.

Board fixture: E2E-D boot 463 (REF s4c2_conv_cin48 on the same runner image 14077be, TA profile 1) with a third pass
added (set 3 = pass C, copied from set 1's RUNs: NPU_ACTIVE kept, the other seven counters set to fixed values). It tests
the three-pass judge path only; it is not data.
"""
import csv
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis"), str(REPO / "host/lib")]
import stage6c as E  # noqa: E402

WL = REPO / "evidence/stage6c/workloads"
REF463 = REPO / "evidence/stage6b/stage6be2ed/raw/evsweep_s6be2ed_run_l500"
REF375 = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"


class Constants(unittest.TestCase):
    def test_frozen(self):
        self.assertEqual(E.PASS_C, [35, 131, 142, 387, 640, 642, 656, 658])
        self.assertEqual((E.N_RUNS, E.TOL, E.VELA_BAND, E.F4_RATE), (15, 0.01, 0.10, (384, 1024)))
        self.assertEqual([b for _, b in E.ORDER], list(range(468, 477)))
        self.assertEqual([k for k, _ in E.ORDER], ["REF", "s6c_f1_rep", "s6c_f1_cin16", "s6c_f2_rep", "s6c_f2_c16", "s6c_f3_rep",
                                                    "s6c_f3_cin16", "s6c_f4_rep", "s6c_f5_rep"])
        self.assertEqual(E.N_MAC["s6c_f5_rep"], 2744000)
        self.assertEqual(E.N_MAC["s6c_f3_cin16"], 36864)

    def test_manifest(self):
        m = json.loads((WL / E.MANIFEST).read_text())
        self.assertEqual(m["s6c_f2_rep"]["vela"]["op_cycles"], 140000)
        self.assertEqual(m["s6c_f2_c16"]["vela"]["op_cycles"], 35000)
        self.assertEqual(m["s6c_f1_rep"]["drwl_sha256"][:8], "a1b054c4")
        self.assertEqual({v["placement"] for v in m.values()}, {0})
        self.assertEqual({v["image"]["bram_sha256"][:8] for v in m.values()}, {"ec0e8c3b"})


class Rules(unittest.TestCase):
    def test_measurement(self):
        self.assertEqual(E.measurement("VALID"), "VALID")
        for s in ("UNSTABLE", "INVALID_PMU"):
            self.assertEqual(E.measurement(s), "PARTIAL_VALID")
        for s in ("CONFIG_MISMATCH", "UNMEASURED", "INVALID_OUTPUT"):
            self.assertEqual(E.measurement(s), "MEASUREMENT_INVALID")

    def test_compute_pair(self):
        self.assertEqual(E.compute_pair(1000, 1010, True), "PREDICTION_SUPPORTED")
        self.assertEqual(E.compute_pair(1000, 990, True), "PREDICTION_SUPPORTED")
        self.assertEqual(E.compute_pair(1000, 1011, True), "PREDICTION_REFUTED")
        self.assertEqual(E.compute_pair(1000, 989, True), "PREDICTION_REFUTED")
        self.assertEqual(E.compute_pair(1000, 1000, False), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.compute_pair(None, 1000, True), "INSUFFICIENT_EVIDENCE")

    def test_compute_f4(self):
        self.assertEqual(E.compute_f4(384000, 1000, True), "PREDICTION_SUPPORTED")
        self.assertEqual(E.compute_f4(1024000, 1000, True), "PREDICTION_SUPPORTED")
        self.assertEqual(E.compute_f4(383000, 1000, True), "PREDICTION_REFUTED")
        self.assertEqual(E.compute_f4(1025000, 1000, True), "PREDICTION_REFUTED")
        self.assertEqual(E.compute_f4(500000, 1000, False), "INSUFFICIENT_EVIDENCE")

    def test_pipeline(self):
        p = E.pipeline_pair(10000, 50, 10101, 50, True)          # tol max(100, 100)
        self.assertEqual((p["verdict"], p["d_npu"], p["tol"]), ("CONTROLLED_EFFECT_OBSERVED", 101, 100))
        self.assertEqual(E.pipeline_pair(10000, 50, 10100, 50, True)["verdict"], "ASSOCIATION_ONLY")
        self.assertEqual(E.pipeline_pair(10000, 150, 10200, 100, True)["verdict"], "ASSOCIATION_ONLY")   # ranges 250
        self.assertEqual(E.pipeline_pair(10000, 0, 9800, 0, True)["verdict"], "CONTROLLED_EFFECT_OBSERVED")
        self.assertEqual(E.pipeline_pair(10000, 0, 20000, 0, False)["verdict"], "MECHANISM_UNRESOLVED")
        self.assertEqual(E.pipeline_single(True), "ASSOCIATION_ONLY")
        self.assertEqual(E.pipeline_single(False), "MECHANISM_UNRESOLVED")

    def test_vela_class(self):
        self.assertEqual(E.vela_class(89, 100, True), "OVERESTIMATION")
        self.assertEqual(E.vela_class(90, 100, True), "ESTIMATE_AGREEMENT")
        self.assertEqual(E.vela_class(110, 100, True), "ESTIMATE_AGREEMENT")
        self.assertEqual(E.vela_class(111, 100, True), "UNDERESTIMATION")
        self.assertEqual(E.vela_class(50, 100, False), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.vela_class(50, 0, True), "INSUFFICIENT_EVIDENCE")

    def test_h_vela(self):
        O, U, A, I = "OVERESTIMATION", "UNDERESTIMATION", "ESTIMATE_AGREEMENT", "INSUFFICIENT_EVIDENCE"
        self.assertEqual(E.h_vela_f12([O, O, O, O]), "PREDICTION_SUPPORTED")
        self.assertEqual(E.h_vela_f12([O, O, I, O]), "PREDICTION_SUPPORTED")
        self.assertEqual(E.h_vela_f12([O, U, O, O]), "PREDICTION_REFUTED")
        self.assertEqual(E.h_vela_f12([O, A, O, O]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.h_vela_f12([I, I]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.h_vela_f3([1.05, 1.2]), "PREDICTION_SUPPORTED")
        self.assertEqual(E.h_vela_f3([1.05, 0.95]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.h_vela_f3([1.05, 0.89]), "PREDICTION_REFUTED")
        self.assertEqual(E.h_vela_f3([1.0]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.h_vela_f3([]), "INSUFFICIENT_EVIDENCE")

    def test_h_pipeline(self):
        k = lambda a, b, c, d: {"s6c_f1_rep": a, "s6c_f2_rep": b, "s6c_f3_rep": c, "s6c_f4_rep": d}
        self.assertEqual(E.h_pipeline(k(5, 6, 4, 2)), "PREDICTION_SUPPORTED")
        self.assertEqual(E.h_pipeline(k(1, 2, 3, 4)), "PREDICTION_REFUTED")
        self.assertEqual(E.h_pipeline(k(5, 3, 4, 2)), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(E.h_pipeline(k(1, 5, 3, 4)), "INSUFFICIENT_EVIDENCE")       # overlap: neither direction
        self.assertEqual(E.h_pipeline({"s6c_f1_rep": 5}), "INSUFFICIENT_EVIDENCE")

    def test_validity(self):
        g = dict(verdict="PASS")
        r = {"REF": dict(status="VALID"), "a": dict(status="VALID")}
        self.assertEqual(E.validity(g, r), "VALID")
        self.assertEqual(E.validity(g, dict(r, a=dict(status="UNSTABLE"))), "PARTIAL_VALID")
        self.assertEqual(E.validity(g, dict(r, a=dict(status="UNMEASURED"))), "MEASUREMENT_INVALID")
        self.assertEqual(E.validity(dict(verdict="FAIL"), r), "MEASUREMENT_INVALID")


def rows_of(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def write_rows(p, rows):
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def add_pass_c(folder: pathlib.Path, npu_scale: float = 1.0, drop=None):
    raw = json.loads((folder / "raw_runs.json").read_text())
    raw += [dict(x, set_id=3) for x in raw[1:] if x["set_id"] == 1]
    (folder / "raw_runs.json").write_text(json.dumps(raw))
    rows = rows_of(folder / "runs.csv")
    extra = []
    for r in rows:
        if r["set_id"] != "1":
            continue
        code = E.PASS_C[int(r["slot"])]
        if drop is not None and code == drop:
            continue
        v = int(int(r["event_value"]) * npu_scale) if code == 35 else 100 + int(r["slot"])
        extra.append(dict(r, set_id="3", ev_type=str(code), name=f"ev{code}", event_value=str(v), ev_post_value=str(v)))
    write_rows(folder / "runs.csv", rows + extra)


class Board(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        shutil.copytree(WL, self.d / "wl")
        m = json.loads((WL / E.MANIFEST).read_text())
        m["REF"]["boot"] = 463
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(m))
        self.root = self.d / "run"
        (self.root / "conds").mkdir(parents=True)
        shutil.copytree(REF463 / "conds/s4c2_conv_cin48", self.root / "conds/s4c2_conv_cin48")
        self.f = self.root / "conds/s4c2_conv_cin48/wfe"

    def test_two_passes_is_invalid_pmu(self):
        r = E.config_result(self.root, self.d / "wl", "REF")
        self.assertEqual(r["status"], "INVALID_PMU")
        self.assertIn("RUN layout (3 passes x (1 warm-up + 4))", r["reasons"])

    def test_three_passes_valid(self):
        add_pass_c(self.f)
        r = E.config_result(self.root, self.d / "wl", "REF")
        self.assertEqual(r["status"], "VALID", r.get("reasons"))
        self.assertEqual(r["pass_c"]["C_131"], 101.0)
        self.assertEqual(r["traffic"]["ext1_rd_beats"], 107.0)
        self.assertEqual(E.repro_gate(str(self.root), str(self.d / "wl"), str(REF375))["verdict"], "PASS")

    def test_pass_c_missing_counter(self):
        add_pass_c(self.f, drop=642)
        r = E.config_result(self.root, self.d / "wl", "REF")
        self.assertEqual(r["status"], "INVALID_PMU")
        self.assertIn("set 3 counters missing or wrong pass", r["reasons"])

    def test_pass_c_npu_inconsistent(self):
        add_pass_c(self.f, npu_scale=1.2)
        r = E.config_result(self.root, self.d / "wl", "REF")
        self.assertEqual(r["status"], "UNSTABLE")
        self.assertIn("NPU_ACTIVE pass A vs pass C", r["reasons"])

    def test_wrong_boot_and_unmeasured(self):
        add_pass_c(self.f)
        m = json.loads((self.d / "wl" / E.MANIFEST).read_text())
        m["REF"]["boot"] = 468
        (self.d / "wl" / E.MANIFEST).write_text(json.dumps(m))
        r = E.config_result(self.root, self.d / "wl", "REF")
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        self.assertTrue(E.boot_check(str(self.root), str(self.d / "wl"), "s6c_f1_rep")["stop"])

    def test_judge_without_shapes(self):
        add_pass_c(self.f)
        s = E.judge(str(self.root), str(self.d / "wl"), str(REF375), str(self.d / "out"))
        self.assertEqual(s["reference_gate"]["verdict"], "PASS")
        self.assertEqual(s["verdicts"]["measurement_validity"], "MEASUREMENT_INVALID")     # shapes unmeasured
        self.assertEqual(s["shapes"]["s6c_f1_rep"]["measurement"], "MEASUREMENT_INVALID")
        self.assertEqual(s["shapes"]["s6c_f1_rep"]["compute"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(s["shapes"]["s6c_f4_rep"]["pipeline"], "MECHANISM_UNRESOLVED")
        self.assertEqual(s["hypotheses"]["h_vela_f1_f2"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(s["shapes"]["s6c_f2_rep"]["control_pair"]["vela_ratio"], 35000 / 140000)
        self.assertEqual(s["shapes"]["s6c_f5_rep"]["compute"], "INSUFFICIENT_EVIDENCE")    # no prediction for F5

    def test_repro_gate_not_reproduced(self):
        add_pass_c(self.f)
        ref = self.d / "ref375"
        shutil.copytree(REF375, ref)
        rows = rows_of(ref / "runs.csv")
        for r in rows:
            if r["ev_type"] == "35":
                r["event_value"] = r["ev_post_value"] = str(int(int(r["event_value"]) * 1.2))
        write_rows(ref / "runs.csv", rows)
        g = E.repro_gate(str(self.root), str(self.d / "wl"), str(ref))
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", True))


if __name__ == "__main__":
    unittest.main()
