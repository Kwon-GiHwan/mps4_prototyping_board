import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib")); sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage1 as S

PROF = json.loads((REPO / "config" / "mlek_baseline.json").read_text())
IDS = [35, 48, 130, 135, 140, 386, 391, 396]
KNOBS = ["0xffffffff", "0x0000000a", "0x00000002", "0x00000000", "0x00000000", "0x00000004", "0x00000004",
         "0x00020f0b", "0x00021f3f", "0x00000000", "0x31100000", "0x00000001",
         "0xffffffff", "0xffffffff", "0xffffffff", "0xffffffff"]
W = {"class": "isolated_operator", "n_mac": 1024 * 1000, "blob_sha256": "b" * 64, "cms_sha256": "c" * 64,
     "golden": {"source": "test", "input_sha256": "i" * 64, "ofm_sha256": "g" * 64}, "operator_type": "CONV_2D", "shape": "x"}
# npu_active 2000, mac_active 1000 -> peak 0.5, ratio 0.5, active-cycle eff. 1.0
VALUES = {35: 2000, 48: 1000, 130: 300, 135: 100, 140: 9000, 386: 50, 391: 10, 396: 9000}


def campaign(name="op", row=lambda rep, ev: {}, summ=None, reps=35, prof=None):
    d = pathlib.Path(tempfile.mkdtemp()); w = d / name; w.mkdir()
    s = dict(blob_sha256="b" * 64, cms_sha256="c" * 64, blob_knobs=KNOBS, ifm_sha256="i" * 64, golden_sha256="g" * 64,
             provenance=dict((prof or PROF)["image"]), requested_ids=IDS, coverage="COMPLETE_SUBSET(8)", refusal=None,
             runs=reps)
    s.update(summ or {}); (w / "summary.json").write_text(json.dumps(s))
    with open(w / "runs.csv", "w", newline="") as f:
        cw = csv.DictWriter(f, fieldnames=["rep", "ev_type", "event_value", "event_overflow", "run_rc", "run_valid",
                                           "window_cycles", "vendor_rc", "ofm_mismatch_count"])
        cw.writeheader()
        for rep in range(1, reps + 1):
            for ev in IDS:
                r = dict(rep=rep, ev_type=ev, event_value=VALUES[ev], event_overflow=False, run_rc=0, run_valid=True,
                         window_cycles=50_000, vendor_rc=0, ofm_mismatch_count=0)
                r.update(row(rep, ev)); cw.writerow(r)
    return d


class Checks(unittest.TestCase):
    def test_r6_replaced_by_mac_le_npu(self):
        run = dict(valid=True, run_rc=0, vendor_rc=0, ofm_mismatch=0, overflow=False, npu_active=10, mac_active=10,
                   window_cycles=100)
        self.assertEqual(S.stage1_checks(run), [])                     # no cycle event needed
        self.assertEqual(S.stage1_checks(dict(run, mac_active=11)), ["R6s_mac_le_npu"])
        self.assertEqual(S.stage1_checks(dict(run, run_rc=0x7D)), ["R2_rc"])


class Derive(unittest.TestCase):
    def test_metrics(self):
        run = {"npu_active": 2000, "mac_active": 1000, "sram_rd_beats": 300, "sram_wr_beats": 100,
               "ext_rd_beats": 50, "ext_wr_beats": 10, "sram_enabled": 9000, "ext_enabled": 9000}
        d = S.derive(run, 1024 * 1000)
        self.assertEqual((d["mac_throughput"], d["peak_mac_efficiency"], d["mac_active_ratio"],
                          d["mac_active_cycle_efficiency"], d["decomposition_residual"]), (512.0, 0.5, 0.5, 1.0, 0.0))
        self.assertEqual((d["sram_beats_per_mac"], d["ext_beats_per_mac"]), (400 / 1_024_000, 60 / 1_024_000))
        self.assertEqual((d["sram_beats_per_npu_cycle"], d["ext_beats_per_npu_cycle"]), (0.2, 0.03))
        self.assertEqual(d["ext_enabled_per_npu_cycle"], 4.5)

    def test_non_mac_workload(self):
        run = {"npu_active": 10, "mac_active": 0, "sram_rd_beats": 1, "sram_wr_beats": 1, "ext_rd_beats": 1,
               "ext_wr_beats": 1, "sram_enabled": 1, "ext_enabled": 1}
        d = S.derive(run, None)
        self.assertIsNone(d["peak_mac_efficiency"]); self.assertIsNone(d["sram_beats_per_mac"])

    def test_stats(self):
        s = S.stats([1.0, 2.0, 3.0, 4.0])
        self.assertEqual((s["median"], s["mean"], s["min"], s["max"], s["deterministic"]), (2.5, 2.5, 1.0, 4.0, False))
        self.assertAlmostEqual(s["std"], 1.2909944, places=6); self.assertAlmostEqual(s["cv"], 0.5163978, places=6)
        self.assertTrue(S.stats([5.0, 5.0])["deterministic"])


class Analyse(unittest.TestCase):
    def test_valid_workload_uses_measured_runs(self):
        # warm-up RUNs carry a different npu_active; the median must come from RUNs 6..35 only
        d = campaign(row=lambda rep, ev: dict(event_value=3000) if rep <= 5 and ev == 35 else {})
        per_run, summ = S.analyse(d, {"op": W}, PROF, IDS)
        self.assertEqual(len(per_run), 35)
        self.assertEqual(summ["op"]["status"], "VALID")
        m = summ["op"]["metrics"]
        self.assertEqual((m["npu_active"]["median"], m["npu_active"]["n"]), (2000, 30))
        self.assertEqual(m["peak_mac_efficiency"]["median"], 0.5)
        self.assertTrue(all(p["run_valid"] for p in per_run))
        self.assertEqual({p["warmup_or_measured"] for p in per_run if p["run_id"] <= 5}, {"warmup"})

    def test_failed_run_recorded_and_workload_unresolved(self):
        d = campaign(row=lambda rep, ev: dict(ofm_mismatch_count=2) if rep == 20 else {})
        per_run, summ = S.analyse(d, {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["status"], "UNRESOLVED"); self.assertNotIn("metrics", summ["op"])
        bad = [p for p in per_run if not p["run_valid"]]
        self.assertTrue(all(not p["run_valid"] for p in per_run))        # a failed gate invalidates the boot
        r20 = next(p for p in per_run if p["run_id"] == 20)
        self.assertEqual((r20["output_valid"], r20["failed_checks"]), (False, "R3_output"))
        self.assertEqual(len(bad), 35)

    def test_wrong_input_hash_invalid(self):
        d = campaign(summ=dict(ifm_sha256="x" * 64))
        _, summ = S.analyse(d, {"op": W}, PROF, IDS)
        self.assertEqual((summ["op"]["gate"], summ["op"]["status"]), ("INVALID", "UNRESOLVED"))

    def test_knob_failure_flag(self):
        d = campaign(row=lambda rep, ev: dict(run_rc=0x7D) if rep == 9 else {})
        per_run, _ = S.analyse(d, {"op": W}, PROF, IDS)
        self.assertFalse(next(p for p in per_run if p["run_id"] == 9)["knobs_honoured"])


R10 = json.loads((REPO / "config" / "mlek_r10.json").read_text())


class TenRunProfile(unittest.TestCase):
    """Profile mlek_r10: 10 RUNs per boot, RUNs 1-2 warm-up, 8 measured (owner decision 2026-10-27)."""

    def test_profile_differs_from_the_frozen_one_only_in_runs_image_and_name(self):
        same = {k for k in PROF if k not in ("name", "what", "image", "repeats", "warmup")}
        self.assertEqual({k: R10[k] for k in same}, {k: PROF[k] for k in same})
        self.assertEqual((R10["repeats"], R10["warmup"]), (10, 2))
        self.assertEqual(R10["image"]["app_sha256"][:8], "26f6129a")
        self.assertEqual((R10["image"]["vectors_sha256"], R10["image"]["ddr_sha256"]),
                         (PROF["image"]["vectors_sha256"], PROF["image"]["ddr_sha256"]))

    def test_ten_runs_use_runs_3_to_10(self):
        d = campaign(row=lambda rep, ev: dict(event_value=3000) if rep <= 2 and ev == 35 else {}, reps=10, prof=R10)
        per_run, summ = S.analyse(d, {"op": W}, R10, IDS)
        self.assertEqual(summ["op"]["status"], "VALID")
        self.assertEqual((summ["op"]["metrics"]["npu_active"]["median"], summ["op"]["metrics"]["npu_active"]["n"]),
                         (2000, 8))
        self.assertEqual([p["run_id"] for p in per_run if p["warmup_or_measured"] == "warmup"], [1, 2])

    def test_run_count_must_match_the_profile(self):
        _, summ = S.analyse(campaign(reps=35, prof=R10), {"op": W}, R10, IDS)     # 35 RUNs under the 10-RUN profile
        self.assertEqual((summ["op"]["gate"], summ["op"]["status"]), ("BASELINE_FAIL", "UNRESOLVED"))
        _, summ = S.analyse(campaign(reps=10, prof=R10), {"op": W}, PROF, IDS)    # 10 RUNs under the 35-RUN profile
        self.assertEqual(summ["op"]["status"], "UNRESOLVED")

    def test_image_must_match_the_profile(self):
        _, summ = S.analyse(campaign(reps=10), {"op": W}, R10, IDS)              # old image under mlek_r10
        self.assertIn("B1_image", summ["op"]["failed_boot"])


class Fingerprint(unittest.TestCase):
    def test_rows(self):
        per_run, summ = S.analyse(campaign(), {"op": W}, PROF, IDS)
        t = S.fingerprint(summ)
        self.assertIn("| op | isolated_operator | 1,024,000 | 2,000 | 512.0 | 50.0% | 50.0% | 100.0% |", t)
        bad = campaign(name="op", row=lambda rep, ev: dict(run_rc=1) if rep == 1 else {})
        _, summ = S.analyse(bad, {"op": W}, PROF, IDS)
        self.assertIn("| op | isolated_operator | BASELINE_FAIL |", S.fingerprint(summ))


class Datasets(unittest.TestCase):
    """Amendment 2: a re-measured dataset is keyed <workload>@<label> and never overwrites the s1 entry."""
    def test_added_dataset_keeps_s1(self):
        _, s1 = S.analyse(campaign(row=lambda rep, ev: dict(ofm_mismatch_count=29)), {"op": W}, PROF, IDS)
        rows, a2 = S.analyse(campaign(), {"op": dict(W, numerical_difference_diagnostic={"mismatch_count": 29})},
                             PROF, IDS, "a2")
        s1.update(a2)
        self.assertEqual((s1["op"]["status"], s1["op@a2"]["status"]), ("UNRESOLVED", "VALID"))
        self.assertEqual((s1["op"]["dataset"], s1["op@a2"]["dataset"]), ("s1", "a2"))
        self.assertEqual({r["dataset"] for r in rows}, {"a2"})
        self.assertEqual(s1["op@a2"]["numerical_difference_diagnostic"], {"mismatch_count": 29})
        t = S.fingerprint(s1)
        self.assertIn("| op | isolated_operator | BASELINE_FAIL |", t)
        self.assertIn("| op@a2 | isolated_operator | 1,024,000 | 2,000 |", t)


if __name__ == "__main__":
    unittest.main()
