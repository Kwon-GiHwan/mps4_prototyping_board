import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "lib")); sys.path.insert(0, str(REPO / "host" / "analysis"))
import baseline_gate as G
import results

PROF = json.loads((REPO / "config" / "mlek_baseline.json").read_text())
IDS = [17, 32, 35, 48, 130, 135, 386, 391]
MAN = {"blob_sha256": "b" * 64, "cms_sha256": "c" * 64}
KNOBS = ["0xffffffff", "0x0000000a", "0x00000002", "0x00000000", "0x00000000", "0x00000004", "0x00000004",
         "0x00020f0b", "0x00021f3f", "0x00000000", "0x31100000", "0x00000001",
         "0xffffffff", "0xffffffff", "0xffffffff", "0xffffffff"]
MLEK = {"ACTIVE_median": 91_431, "SRAM_RD_DATA_BEAT_RECEIVED": 22_664, "SRAM_WR_DATA_BEAT_WRITTEN": 17_760,
        "EXT_RD_DATA_BEAT_RECEIVED": 15_815, "EXT_WR_DATA_BEAT_WRITTEN": 1}
VALUES = {17: 100_000, 32: 8_000, 35: 91_500, 48: 56_450, 130: 22_664, 135: 17_760, 386: 15_815, 391: 1}


def summary(**over):
    s = dict(blob_sha256=MAN["blob_sha256"], cms_sha256=MAN["cms_sha256"], blob_knobs=list(KNOBS),
             provenance=dict(PROF["image"]), requested_ids=list(IDS), coverage="COMPLETE_SUBSET(8)",
             refusal=None, runs=35)
    s.update(over); return s


def campaign(summ=None, reps=35, row=lambda rep, ev: {}, values=VALUES):
    d = pathlib.Path(tempfile.mkdtemp()) / "kws_micronet_m"; d.mkdir()
    (d / "summary.json").write_text(json.dumps(summ or summary()))
    with open(d / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rep", "ev_type", "event_value", "event_overflow", "run_rc", "run_valid",
                                          "window_cycles", "vendor_rc", "ofm_mismatch_count"])
        w.writeheader()
        for rep in range(1, reps + 1):
            for ev in IDS:
                r = dict(rep=rep, ev_type=ev, event_value=values[ev], event_overflow=False, run_rc=0, run_valid=True,
                         window_cycles=100_500, vendor_rc=0, ofm_mismatch_count=0)
                r.update(row(rep, ev)); w.writerow(r)
    return d


def run_gate(d):
    return G.gate(d, PROF, MAN, IDS)


class Gate(unittest.TestCase):
    def test_green(self):
        g = run_gate(campaign())
        self.assertEqual((g["gate"], g["failed_boot"], g["failed_runs"]), ("BASELINE_PASS", [], {}))

    def test_each_run_check_reachable(self):
        cases = {"R1_valid": dict(run_valid=False), "R2_rc": dict(run_rc=0x7D), "R3_output": dict(vendor_rc=2),
                 "R4_overflow": dict(event_overflow=True)}
        for check, over in cases.items():
            g = run_gate(campaign(row=lambda rep, ev, o=over: o if rep == 7 else {}))
            self.assertEqual(g["gate"], "BASELINE_FAIL", check)
            self.assertIn(check, g["failed_runs"][7], check)
            self.assertEqual(list(g["failed_runs"]), [7], check)
        g = run_gate(campaign(row=lambda rep, ev: dict(ofm_mismatch_count=3) if rep == 2 else {}))
        self.assertEqual(g["failed_runs"], {2: ["R3_output"]})
        g = run_gate(campaign(row=lambda rep, ev: dict(window_cycles=91_000) if rep == 3 else {}))
        self.assertIn("R5_active", g["failed_runs"][3])          # npu_active 91,500 > window
        g = run_gate(campaign(values={**VALUES, 17: 103_000}))
        self.assertEqual(g["failed_runs"][1], ["R6_cycle"])        # cycle 2.5 % off the window
        g = run_gate(campaign(values={**VALUES, 35: 0}))
        self.assertIn("R5_active", g["failed_runs"][1])

    def test_each_boot_check_reachable(self):
        cases = {"B1_image": summary(provenance=dict(PROF["image"], app_sha256="0" * 64)),
                 "B2_blob": summary(blob_sha256="x"),
                 "B3_set": summary(requested_ids=[35, 48])}
        more = [("B2_blob", summary(cms_sha256="x")), ("B2_blob", summary(blob_knobs=KNOBS[:9] + ["0x00000002"] + KNOBS[10:])),
                ("B2_blob", summary(blob_knobs=KNOBS[:11] + ["0x00000002"] + KNOBS[12:])),
                ("B3_set", summary(refusal={"rule": "RULE_PING"})), ("B3_set", summary(runs=34)),
                ("B3_set", summary(coverage="RULE_SET_COVERAGE: missing"))]
        for check, s in list(cases.items()) + more:
            g = run_gate(campaign(summ=s))
            self.assertEqual((g["gate"], g["failed_boot"]), ("BASELINE_FAIL", [check]), check)

    def test_short_campaign_fails(self):
        self.assertEqual(run_gate(campaign(reps=34))["gate"], "BASELINE_FAIL")

    def test_missing_files_unproven(self):
        d = campaign(); (d / "runs.csv").unlink()
        self.assertEqual(run_gate(d)["gate"], "UNPROVEN")
        self.assertEqual(run_gate(pathlib.Path(tempfile.mkdtemp()) / "absent")["gate"], "UNPROVEN")


GOLD = {"input_sha256": "i" * 64, "ofm_sha256": "g" * 64}


class Amendment1(unittest.TestCase):
    MAN = dict(MAN, golden=GOLD, numerical_difference_diagnostic={"mismatch_count": 7})

    def gate(self, **over):
        hashes = dict(ifm_sha256=GOLD["input_sha256"], golden_sha256=GOLD["ofm_sha256"]); hashes.update(over)
        return G.gate(campaign(summ=summary(**hashes)), PROF, self.MAN, IDS)

    def test_pass_with_frozen_input_and_golden(self):
        self.assertEqual(self.gate()["gate"], "BASELINE_PASS")       # the TFLite diagnostic does not fail it

    def test_other_input_or_golden_invalid(self):
        self.assertEqual(self.gate(ifm_sha256="x" * 64)["gate"], "INVALID")
        self.assertEqual(self.gate(golden_sha256="x" * 64)["gate"], "INVALID")
        g = G.gate(campaign(), PROF, self.MAN, IDS)                   # driver did not record them
        self.assertEqual(g["gate"], "INVALID")
        self.assertEqual(G.outcome(g, [], {})["outcome"], "UNRESOLVED")

    def test_original_manifest_ignores_input_hash(self):
        self.assertEqual(run_gate(campaign(summ=summary(ifm_sha256="x" * 64)))["gate"], "BASELINE_PASS")

    def test_golden_mismatch_still_fails_r3(self):
        g = G.gate(campaign(summ=summary(ifm_sha256=GOLD["input_sha256"], golden_sha256=GOLD["ofm_sha256"]),
                            row=lambda rep, ev: dict(ofm_mismatch_count=1) if rep == 30 else {}), PROF, self.MAN, IDS)
        self.assertEqual(g["failed_runs"], {30: ["R3_output"]})


class Outcome(unittest.TestCase):
    def outcome(self, **campaign_kw):
        d = campaign(**campaign_kw)
        return G.outcome(run_gate(d), results.load_runs(d / "runs.csv"), MLEK)

    def test_equivalent(self):
        o = self.outcome()
        self.assertEqual((o["outcome"], o["measured"], o["beats_equal"]), ("MLEK_EQUIVALENT", 30, True))

    def test_active_tolerance_both_sides(self):
        self.assertEqual(self.outcome(values={**VALUES, 35: 92_345})["outcome"], "MLEK_EQUIVALENT")   # +0.9997 %
        self.assertEqual(self.outcome(values={**VALUES, 35: 92_346})["outcome"], "MLEK_DIFFERENT")    # +1.0008 %
        self.assertEqual(self.outcome(values={**VALUES, 35: 90_517})["outcome"], "MLEK_EQUIVALENT")   # -0.9997 %
        self.assertEqual(self.outcome(values={**VALUES, 35: 90_516})["outcome"], "MLEK_DIFFERENT")

    def test_each_beat_must_equal(self):
        for ev in (130, 135, 386, 391):
            self.assertEqual(self.outcome(values={**VALUES, ev: VALUES[ev] + 1})["outcome"], "MLEK_DIFFERENT", ev)

    def test_median_uses_measured_runs_only(self):
        # warm-up RUNs 1-5 far off; the 30 measured ones on MLEK
        o = self.outcome(row=lambda rep, ev: dict(event_value=50_000) if rep <= 5 and ev == 35 else {})
        self.assertEqual(o["outcome"], "MLEK_EQUIVALENT")

    def test_gate_failure_unresolved(self):
        self.assertEqual(self.outcome(summ=summary(runs=34))["outcome"], "UNRESOLVED")

    def test_overall(self):
        self.assertEqual(G.overall([]), "UNRESOLVED")
        self.assertEqual(G.overall(["MLEK_EQUIVALENT"] * 3), "MLEK_EQUIVALENT")
        self.assertEqual(G.overall(["MLEK_EQUIVALENT", "MLEK_DIFFERENT"]), "MLEK_DIFFERENT")
        self.assertEqual(G.overall(["MLEK_DIFFERENT", "UNRESOLVED"]), "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
