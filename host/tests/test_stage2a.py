import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib")); sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage2a as S

PROF = json.loads((REPO / "config" / "mlek_baseline.json").read_text())
IDS = [35, 48, 51, 52, 55, 64, 80, 81]
KNOBS = ["0xffffffff", "0x0000000a", "0x00000002", "0x00000000", "0x00000000", "0x00000004", "0x00000004",
         "0x00020f0b", "0x00021f3f", "0x00000000", "0x31100000", "0x00000001",
         "0xffffffff", "0xffffffff", "0xffffffff", "0xffffffff"]
W = {"class": "isolated_operator", "n_mac": 1024 * 500, "blob_sha256": "b" * 64, "cms_sha256": "c" * 64,
     "golden": {"source": "test", "input_sha256": "i" * 64, "ofm_sha256": "g" * 64}}
# npu 2000, mac 1000, dpu 900, w/acc 100, ib 300, ao 400, wd 200, wd_stalled 50
VALUES = {35: 2000, 48: 1000, 51: 900, 52: 100, 55: 300, 64: 400, 80: 200, 81: 50}


def campaign(row=lambda rep, ev: {}, summ=None):
    d = pathlib.Path(tempfile.mkdtemp()); w = d / "op"; w.mkdir()
    s = dict(blob_sha256="b" * 64, cms_sha256="c" * 64, blob_knobs=KNOBS, ifm_sha256="i" * 64, golden_sha256="g" * 64,
             provenance=dict(PROF["image"]), requested_ids=IDS, coverage="COMPLETE_SUBSET(8)", refusal=None, runs=35)
    s.update(summ or {}); (w / "summary.json").write_text(json.dumps(s))
    with open(w / "runs.csv", "w", newline="") as f:
        cw = csv.DictWriter(f, fieldnames=["rep", "ev_type", "event_value", "event_overflow", "run_rc", "run_valid",
                                           "window_cycles", "vendor_rc", "ofm_mismatch_count"])
        cw.writeheader()
        for rep in range(1, 36):
            for ev in IDS:
                r = dict(rep=rep, ev_type=ev, event_value=VALUES[ev], event_overflow=False, run_rc=0, run_valid=True,
                         window_cycles=50_000, vendor_rc=0, ofm_mismatch_count=0)
                r.update(row(rep, ev)); cw.writerow(r)
    return d


def st(median, lo=None, hi=None, det=None):
    lo = median if lo is None else lo; hi = median if hi is None else hi
    return {"median": median, "min": lo, "max": hi, "deterministic": lo == hi if det is None else det}


class Analyse(unittest.TestCase):
    def test_metrics_from_named_events(self):
        _, summ = S.analyse(campaign(), {"op": W}, PROF, IDS)
        m = summ["op"]["metrics"]
        self.assertEqual(summ["op"]["status"], "VALID")
        got = {k: m[k]["median"] for k in ("mac_active_ratio", "dpu_active_ratio", "dpu_given_mac_active",
                                            "ao_active_ratio", "wd_active_ratio", "wd_stalled_ratio",
                                            "mac_ib_stall_ratio", "mac_w_or_acc_stall_ratio",
                                            "mac_active_cycle_efficiency")}
        self.assertEqual(got, {"mac_active_ratio": 0.5, "dpu_active_ratio": 0.45, "dpu_given_mac_active": 0.9,
                               "ao_active_ratio": 0.2, "wd_active_ratio": 0.1, "wd_stalled_ratio": 0.025,
                               "mac_ib_stall_ratio": 0.15, "mac_w_or_acc_stall_ratio": 0.05,
                               "mac_active_cycle_efficiency": 0.5})

    def test_diagnostics_never_invalidate(self):
        # mac 1000 + ib 1500 > npu 2000 in RUN 10: S1 and S2 violated, RUN and workload stay valid
        per_run, summ = S.analyse(campaign(row=lambda rep, ev: dict(event_value=1500) if rep == 10 and ev == 55
                                           else {}), {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["status"], "VALID")
        self.assertEqual(summ["op"]["diagnostic_violations"],
                         {"S1_mac_plus_ib_le_npu": 1, "S2_mac_plus_ib_plus_wacc_le_npu": 1, "S3_dpu_le_npu": 0})
        r10 = next(p for p in per_run if p["run_id"] == 10)
        self.assertTrue(r10["run_valid"]); self.assertFalse(r10["S1_mac_plus_ib_le_npu"])

    def test_diagnostic_boundary_is_allowed(self):
        # mac 1000 + ib 1000 == npu 2000: not a violation of S1 (S2 adds w/acc 100 and is violated)
        _, summ = S.analyse(campaign(row=lambda rep, ev: dict(event_value=1000) if ev == 55 else {}),
                            {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["diagnostic_violations"],
                         {"S1_mac_plus_ib_le_npu": 0, "S2_mac_plus_ib_plus_wacc_le_npu": 30, "S3_dpu_le_npu": 0})
        # mac 1000 + ib 900 + w/acc 100 == npu 2000: S2 holds; dpu 2001 > npu in RUN 12 violates S3 only
        _, summ = S.analyse(campaign(row=lambda rep, ev: dict(event_value=900) if ev == 55
                                     else dict(event_value=2001) if rep == 12 and ev == 51 else {}),
                            {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["status"], "VALID")
        self.assertEqual(summ["op"]["diagnostic_violations"],
                         {"S1_mac_plus_ib_le_npu": 0, "S2_mac_plus_ib_plus_wacc_le_npu": 0, "S3_dpu_le_npu": 1})

    def test_gate_is_stage1s(self):
        _, summ = S.analyse(campaign(summ=dict(requested_ids=[33, 35, 48, 51, 55, 64, 80, 81])), {"op": W}, PROF, IDS)
        self.assertEqual((summ["op"]["gate"], summ["op"]["failed_boot"]), ("BASELINE_FAIL", ["B3_set"]))
        _, summ = S.analyse(campaign(row=lambda rep, ev: dict(event_value=2500) if rep == 7 and ev == 48 else {}),
                            {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["failed_runs"], {7: ["R6s_mac_le_npu"]})
        _, summ = S.analyse(campaign(row=lambda rep, ev: dict(ofm_mismatch_count=1) if rep == 3 else {}),
                            {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["status"], "UNRESOLVED")
        _, summ = S.analyse(campaign(summ=dict(golden_sha256="x" * 64)), {"op": W}, PROF, IDS)
        self.assertEqual(summ["op"]["gate"], "INVALID")


class Reproduction(unittest.TestCase):
    REF = {"mac_active": st(1000), "npu_active": st(2000, 1990, 2010)}

    def test_reproduced(self):
        r = S.reproduction({"mac_active": st(1000), "npu_active": st(2005, 1980, 2030)}, self.REF)
        self.assertEqual(r["result"], "REPRODUCED")

    def test_mac_differs_in_one_run(self):
        r = S.reproduction({"mac_active": st(1000, 1000, 1001), "npu_active": st(2000)}, self.REF)
        self.assertEqual((r["result"], r["mac_active_equal"]), ("NOT_REPRODUCED", False))

    def test_npu_median_outside_range(self):
        for med in (1989, 2011):
            r = S.reproduction({"mac_active": st(1000), "npu_active": st(med)}, self.REF)
            self.assertEqual((r["result"], r["npu_active_median_in_range"]), ("NOT_REPRODUCED", False))
        r = S.reproduction({"mac_active": st(1000), "npu_active": st(2010)}, self.REF)   # boundary is inside
        self.assertEqual(r["result"], "REPRODUCED")

    def test_reference_not_deterministic(self):
        ref = dict(self.REF, mac_active=st(1000, 999, 1001))
        r = S.reproduction({"mac_active": st(1000), "npu_active": st(2000)}, ref)
        self.assertEqual(r["result"], "NOT_REPRODUCED")


class Separation(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(S.separation(st(5, 4.1, 6), st(3, 2, 4)), "HIGHER")
        self.assertEqual(S.separation(st(5, 4, 6), st(3, 2, 4)), "OVERLAP")     # touching ranges overlap
        self.assertEqual(S.separation(st(1, 0, 1.9), st(3, 2, 4)), "LOWER")
        self.assertEqual(S.separation(st(1, 0, 2), st(3, 2, 4)), "OVERLAP")


def ops(**kw):
    """Reference (conv-like) and operator metric dicts; MAC active 0.8 vs 0.2 -> excess inactive share 0.6."""
    base = {k: st(0.1) for k in ("wd_stalled_ratio", "mac_ib_stall_ratio", "mac_w_or_acc_stall_ratio",
                                 "ao_active_ratio")}
    ref = dict(base, mac_active_ratio=st(0.8, 0.79, 0.81), mac_active_cycle_efficiency=st(0.6),
               dpu_given_mac_active=st(0.9))
    op = dict(base, mac_active_ratio=st(0.2, 0.19, 0.21), mac_active_cycle_efficiency=st(0.1),
              dpu_given_mac_active=st(0.9))
    op.update(kw)
    return op, ref


class Inactivity(unittest.TestCase):
    def status(self, metric, source, **kw):
        op, ref = ops(**kw)
        return S.inactivity_status(op, ref, metric, source)["status"]

    def test_trm_covering_excess_is_supported(self):
        self.assertEqual(self.status("wd_stalled_ratio", "TRM", wd_stalled_ratio=st(0.75, 0.74, 0.76)), "SUPPORTED")

    def test_trm_not_covering_is_partial(self):
        self.assertEqual(self.status("wd_stalled_ratio", "TRM", wd_stalled_ratio=st(0.3, 0.29, 0.31)),
                         "PARTIAL_SUPPORT")

    def test_driver_derived_capped(self):
        self.assertEqual(self.status("mac_ib_stall_ratio", "driver", mac_ib_stall_ratio=st(0.75, 0.74, 0.76)),
                         "PARTIAL_SUPPORT")
        self.assertEqual(self.status("mac_ib_stall_ratio", "driver", mac_ib_stall_ratio=st(0.3, 0.29, 0.31)),
                         "CORRELATED_ONLY")

    def test_overlap_and_lower(self):
        self.assertEqual(self.status("ao_active_ratio", "TRM", ao_active_ratio=st(0.12, 0.05, 0.2)), "UNRESOLVED")
        self.assertEqual(self.status("ao_active_ratio", "TRM", ao_active_ratio=st(0.09, 0.05, 0.2)), "REFUTED")
        self.assertEqual(self.status("ao_active_ratio", "TRM", ao_active_ratio=st(0.01)), "REFUTED")

    def test_precondition_mac_ratio_not_lower(self):
        self.assertEqual(self.status("wd_stalled_ratio", "TRM", wd_stalled_ratio=st(0.9),
                                     mac_active_ratio=st(0.8, 0.7, 0.9)), "UNRESOLVED")


class Efficiency(unittest.TestCase):
    def test_not_low_refutes_both(self):
        op, ref = ops(mac_active_cycle_efficiency=st(0.8))
        h = S.efficiency_status(op, ref)
        self.assertEqual((h["H5"]["status"], h["H6"]["status"]), ("REFUTED", "REFUTED"))

    def test_spatial_packing(self):
        op, ref = ops()
        h = S.efficiency_status(op, ref)
        self.assertEqual((h["H5"]["status"], h["H6"]["status"]), ("SUPPORTED", "UNRESOLVED"))

    def test_dpu_inactivity(self):
        op, ref = ops(dpu_given_mac_active=st(0.3))
        h = S.efficiency_status(op, ref)
        self.assertEqual((h["H5"]["status"], h["H6"]["status"]), ("REFUTED", "SUPPORTED"))

    def test_stall_present_leaves_h5_open(self):
        op, ref = ops(mac_ib_stall_ratio=st(0.5))
        self.assertEqual(S.efficiency_status(op, ref)["H5"]["status"], "UNRESOLVED")


class Hypotheses(unittest.TestCase):
    def summary(self, **kw):
        op, ref = ops(**kw)
        return {"conv3x3": {"metrics": ref}, "dw3x3": {"metrics": op}, "pw1x1": {"metrics": op}}

    def test_pattern6_when_no_component(self):
        h = S.hypotheses(self.summary())["dw3x3"]
        self.assertFalse(h["component_evidence_for_low_mac_activity"])
        self.assertEqual(h["hypotheses"]["H3"]["status"], "UNRESOLVED")
        self.assertTrue(any("pattern 6" in r for r in h["routes"]))

    def test_driver_only_partial_does_not_route_like_supported_trm(self):
        h = S.hypotheses(self.summary(mac_ib_stall_ratio=st(0.75)))["dw3x3"]
        self.assertEqual(h["hypotheses"]["H2"]["status"], "PARTIAL_SUPPORT")
        self.assertTrue(h["component_evidence_for_low_mac_activity"])
        self.assertTrue(any(r.startswith("Stage 3: IFM supply") for r in h["routes"]))


if __name__ == "__main__":
    unittest.main()
