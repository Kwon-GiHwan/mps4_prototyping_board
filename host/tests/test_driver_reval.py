import csv, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import driver_reval as R

M = "kws_micronet_m"          # in SAME_INPUT_DRIVER (driver_p3 has the stage's input)
X = "yolo-fastest_192_face_v4"  # cross-input: stage seed-1, driver and bridge MLEK input


def write_runs(d, sets, jit=None):
    """sets: {set_id: {ev: value}}; event e moves by jit[e] per RUN (reps 3..5 measured)."""
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for s, evs in sets.items():
        for rep in (1, 2, 3, 4, 5):
            for e, v in evs.items():
                v = v + (rep - 4) * (jit or {}).get(e, 0)
                rows.append(dict(set_id=s, rep=rep, ev_type=e, event_value=v, run_valid="True", window_cycles=1000,
                                 infer_npu_cycles=900, infer_cpu_cycles=900, infer_sys_ticks="", host_run_s="",
                                 event_overflow="False"))
    with (d / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def write_table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k != "model", k))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


A_SET = {35: 100000, 48: 60000, 51: 50000, 64: 20000, 80: 10000, 81: 70000}
B_SET = {35: 100000, 128: 100, 130: 1000, 135: 500, 384: 50, 386: 400, 391: 10}
C_SET = {35: 100000, 131: 2000}


class Rules(unittest.TestCase):
    def test_agree(self):
        self.assertTrue(R.agree("DET", 5.0, 5.0, [], []))
        self.assertFalse(R.agree("DET", 5.0, 5.000001, [], []))
        self.assertTrue(R.agree("JITTER", 100.9, 100.0, [], []))               # 1 % floor
        self.assertFalse(R.agree("JITTER", 101.1, 100.0, [], []))
        self.assertTrue(R.agree("JITTER", 103.0, 100.0, [99, 102], [97, 100]))  # larger range 3
        self.assertTrue(R.agree("JITTER", "COUNTED_ZERO", "COUNTED_ZERO", [], []))
        self.assertFalse(R.agree("JITTER", 0.1, "COUNTED_ZERO", [], []))
        self.assertIsNone(R.agree("JITTER", None, 1.0, [], []))

    def test_verdict(self):
        V = R.verdict
        self.assertEqual(V("STATIC", True, None, None, None)[0], R.RETAINED)
        self.assertEqual(V("POLLUTED", False, True, None, None)[0], R.INVALID)
        self.assertEqual(V("WINDOW", False, True, None, None)[0], R.COND)
        self.assertEqual(V("JITTER", False, True, None, None)[0], R.REVALIDATED)
        self.assertEqual(V("JITTER", False, False, None, None)[0], R.COND)
        self.assertEqual(V("JITTER", False, None, None, None)[0], R.UP)
        self.assertEqual(V("DET", True, True, True, None)[0], R.REVALIDATED)
        self.assertEqual(V("DET", True, True, False, None), (R.COND, "path agrees, input changes it"))
        self.assertEqual(V("DET", True, False, True, None)[0], R.COND)
        self.assertEqual(V("DET", True, True, None, None)[0], R.UP)
        self.assertEqual(V("JITTER", True, None, None, True)[0], R.RETAINED)
        self.assertEqual(V("JITTER", True, None, None, False)[0], R.REMEASURE)
        self.assertEqual(V("JITTER", True, None, None, None)[0], R.UP)


class Rows(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = pathlib.Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def build(self, stage_sets, driver_sets, same_sets=None, bridge_sets=None, published=None, stage_jit=None):
        for m in (M, X):
            write_runs(self.d / "stage" / "ctl" / m, stage_sets, stage_jit)
            write_runs(self.d / "driver" / m, driver_sets)
            write_runs(self.d / "bridge" / m, bridge_sets or {1: A_SET, 2: B_SET})
        write_runs(self.d / "same" / M, same_sets or {1: {35: 100000}, 2: A_SET, 3: B_SET})
        pub = dict(n_mac=1e7, vela_cycles_npu=95000.0, active=100000.0, mac_active_ratio=0.6, dpu_over_mac=50000 / 60000,
                   runner_window=5e6, infer_cycles=102000.0, **(published or {}))
        res = self.d / "results"
        write_table(res / "fi101_stage1/stage1.csv", [dict(model=m, **pub) for m in (M, X)])
        write_table(res / "fi101_stage3/stage3.csv", [dict(model=m, sram_bytes=24000.0, ext_bytes=6560.0, ext_rd_burst=8.0,
                                                           sram_rd_req_stall=0.01, vela_sram_bytes=1.0,
                                                           vela_dram_bytes=1.0) for m in (M, X)])
        write_table(res / "fi101_stage3/unit_stalls.csv", [dict(model=m, mac_stalled_by_ib=0.1) for m in (M, X)])
        write_table(res / "fi101_stage2a/stage2a_models.csv", [dict(model=m, mac_active=0.6) for m in (M, X)])
        R.main(*(str(self.d / k) for k in ("stage", "bridge", "driver", "same", "results", "out")))
        with (self.d / "out" / "reval.csv").open() as f:
            return {(r["model"], r["stage"], r["metric"]): r for r in csv.DictReader(f)}

    def test_same_input_bridged_and_cross(self):
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, {1: A_SET, 2: B_SET, 3: {35: 100000, 131: 2000}})
        v = lambda m, s, k: rows[(m, s, k)]["verdict"]
        self.assertEqual(v(M, "stage1", "mac_active_ratio"), R.REVALIDATED)
        self.assertEqual(rows[(M, "stage1", "mac_active_ratio")]["input_basis"], "SAME_INPUT")
        self.assertEqual(v(X, "stage1", "mac_active_ratio"), R.REVALIDATED)
        self.assertEqual(rows[(X, "stage1", "mac_active_ratio")]["input_basis"], "BRIDGED")
        self.assertEqual(v(X, "stage3", "sram_rd_req_stall"), R.RETAINED)          # set C: no bridge, agrees
        self.assertEqual(v(M, "stage1", "runner_window"), R.INVALID)
        self.assertEqual(v(M, "stage1", "infer_cycles"), R.COND)
        self.assertEqual(v(M, "stage1", "n_mac"), R.RETAINED)
        self.assertEqual(v(M, "stage2a", "mac_active"), R.REVALIDATED)          # follows stage1 mac_active_ratio
        self.assertEqual(v(M, "stage3_channels", "channel_shares"), R.RETAINED)

    def test_differences(self):
        drv_a = {**A_SET, 48: 66000}                                         # MAC 10 % higher on the driver
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, {1: drv_a, 2: B_SET, 3: {35: 100000, 131: 4000}},
                          same_sets={1: {35: 100000}, 2: drv_a, 3: B_SET})
        v = lambda m, s, k: rows[(m, s, k)]["verdict"]
        self.assertEqual(v(M, "stage1", "mac_active_ratio"), R.COND)              # same input, path changes it
        self.assertEqual(v(X, "stage1", "mac_active_ratio"), R.COND)              # bridged, path changes it
        self.assertEqual(v(X, "stage3", "sram_rd_req_stall"), R.REMEASURE)         # unbridged, differs
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, {1: A_SET, 2: {**B_SET, 130: 1001}, 3: C_SET},
                          same_sets={1: {35: 100000}, 2: A_SET, 3: {**B_SET, 130: 1001}})
        self.assertEqual(rows[(M, "stage3_channels", "channel_shares")]["verdict"], R.REMEASURE)

    def test_input_dependence_through_the_bridge(self):
        br = {**A_SET, 48: 54000}                                            # legacy on MLEK input: other MAC
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, {1: br, 2: B_SET, 3: C_SET},
                          bridge_sets={1: br, 2: B_SET})
        r = rows[(X, "stage1", "mac_active_ratio")]
        self.assertEqual((r["verdict"], r["reason"]), (R.COND, "path agrees, input changes it"))

    def test_det_that_moves_is_judged_as_jitter(self):
        drv = {1: A_SET, 2: {**B_SET, 384: 51}, 3: C_SET}                          # burst 7.84 vs 8.0: 2 % lower
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, drv, same_sets={1: {35: 100000}, 2: A_SET, 3: drv[2]})
        r = rows[(M, "stage3", "ext_rd_burst")]
        self.assertEqual((r["cls"], r["verdict"]), ("DET", R.COND))                # fixed in the stage: exact rule
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, drv, same_sets={1: {35: 100000}, 2: A_SET, 3: drv[2]},
                          stage_jit={384: 2})                                       # stage 48..52 RUN to RUN
        r = rows[(M, "stage3", "ext_rd_burst")]
        self.assertEqual((r["cls"], r["verdict"]), ("JITTER", R.REVALIDATED))     # within the stage's own range

    def test_missing_driver_is_unproven(self):
        rows = self.build({1: A_SET, 2: B_SET, 3: C_SET}, {1: {35: 100000}})
        self.assertEqual(rows[(X, "stage3", "sram_rd_req_stall")]["verdict"], R.UP)


if __name__ == "__main__":
    unittest.main()
