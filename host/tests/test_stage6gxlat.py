"""Stage 6G-X_LAT judge (contract evidence/stage6gxlat/contract.md). Expected values are hand-written."""
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6gxlat as G  # noqa: E402
import stage6ex3 as X  # noqa: E402

EV = REPO / "evidence/stage6ex3"
ROOTS = {"x3b": str(EV / "raw_b/evsweep_x3b_run"), "x3c": str(EV / "raw_c/evsweep_x3c_run"),
         "l250": "/nonexistent250", "l1000": "/nonexistent1000"}
WL = EV / "workloads"


def caps500():
    p = REPO / "evidence/stage6gxlat/caps_14077be.json"
    return json.loads(p.read_text())


class Rules(unittest.TestCase):
    def test_tol(self):
        self.assertEqual(G.tol_of(2423, 500, 600, 30000, 40000), 2423)
        self.assertEqual(G.tol_of(2423, 1500, 1000, 30000, 40000), 2500)
        self.assertEqual(G.tol_of(100, 10, 10, 30000, 40000), 400)          # 1 % of the larger median

    def test_response(self):
        self.assertEqual(G.response(2501, 2500), "SENSITIVE")
        self.assertEqual(G.response(-2501, 2500), "SENSITIVE")
        self.assertEqual(G.response(2500, 2500), "NOT_DETECTABLY_SENSITIVE")

    def test_fidelity(self):
        self.assertEqual(G.fidelity(10000, 10000, 5001), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(G.fidelity(10000, 10000, 5000), "DIRECTION_AND_MAGNITUDE_CONSISTENT")
        self.assertEqual(G.fidelity(20000, 40000, 3000), "DIRECTION_ONLY_CONSISTENT")    # |e| 20000 > 6000+3000
        self.assertEqual(G.fidelity(40000 - 9000, 40000, 3000), "DIRECTION_AND_MAGNITUDE_CONSISTENT")   # boundary
        self.assertEqual(G.fidelity(40000 - 9001, 40000, 3000), "DIRECTION_ONLY_CONSISTENT")
        self.assertEqual(G.fidelity(-20000, 20000, 3000), "INCONSISTENT")
        self.assertEqual(G.fidelity(30000, 2000, 3000), "INCONSISTENT")        # Vela flat, board responds
        self.assertEqual(G.fidelity(2000, 30000, 3000), "INCONSISTENT")        # board flat, Vela responds

    def test_overall(self):
        D, O, I, N = ("DIRECTION_AND_MAGNITUDE_CONSISTENT", "DIRECTION_ONLY_CONSISTENT", "INCONSISTENT",
                      "INSUFFICIENT_EVIDENCE")
        self.assertEqual(G.overall_fidelity([N, N]), N)
        self.assertEqual(G.overall_fidelity([D, D, N]), D)
        self.assertEqual(G.overall_fidelity([D, O, N]), O)
        self.assertEqual(G.overall_fidelity([D, O, I]), I)

    def test_invariant(self):
        self.assertTrue(G.invariant({250: 1010, 500: 1000, 1000: 990}, 1000))
        self.assertFalse(G.invariant({250: 1011, 500: 1000}, 1000))
        self.assertFalse(G.invariant({250: None, 500: 1000}, 1000))

    def test_mechanism(self):
        self.assertEqual(G.mechanism([]), "MECHANISM_UNRESOLVED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: 500, 55: 0, 387: 0})]), "PARTIALLY_SUPPORTED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: 499, 55: 499, 387: 499})]), "MECHANISM_UNRESOLVED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: -900, 55: 0, 387: 0})]), "MECHANISM_UNRESOLVED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: 0, 55: 0, 387: 600})]), "PARTIALLY_SUPPORTED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: 0, 55: 600, 387: 0})]), "PARTIALLY_SUPPORTED")
        self.assertEqual(G.mechanism([dict(db=1000, ev={81: 600, 55: 0, 387: 0}),
                                      dict(db=1000, ev={81: 0, 55: 0, 387: 0})]), "MECHANISM_UNRESOLVED")

    def test_h_l2(self):
        self.assertEqual(G.h_l2([dict(dram_share=0.5, rel=0.3), dict(dram_share=0.49, rel=0.2)]), "SUPPORTED")
        self.assertEqual(G.h_l2([dict(dram_share=0.9, rel=0.3), dict(dram_share=0.1, rel=0.3)]), "REFUTED")
        self.assertEqual(G.h_l2([dict(dram_share=0.9, rel=0.3), dict(dram_share=0.9, rel=0.1),
                                 dict(dram_share=0.1, rel=0.2)]), "REFUTED")                 # every, not some
        self.assertEqual(G.h_l2([dict(dram_share=0.9, rel=0.3)]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(G.h_l2([dict(dram_share=0.1, rel=0.3)]), "INSUFFICIENT_EVIDENCE")

    def test_measurement(self):
        self.assertEqual(G.measurement(["VALID", "VALID"]), "VALID")
        self.assertEqual(G.measurement(["VALID", "UNSTABLE"]), "PARTIAL_VALID")
        self.assertEqual(G.measurement(["VALID", "CONFIG_MISMATCH"]), "MEASUREMENT_INVALID")
        self.assertEqual(G.measurement(["UNSTABLE", "INVALID_PMU"]), "MEASUREMENT_INVALID")


class Fixed(unittest.TestCase):
    def test_boots(self):
        self.assertEqual(sorted(G.BOOTS.values()), list(range(505, 517)))
        self.assertEqual(G.BOOTS[("x3_kws_B2", 250)], 505)
        self.assertEqual(G.BOOTS[("x3_ad_B4", 250)], 516)
        self.assertEqual(G.BOOTS[("x3_kws_B3", 1000)], 507)
        self.assertEqual(sum(1 for (_, l) in G.BOOTS if l == 250), 6)

    def test_images(self):
        self.assertEqual(G.IMAGES[250]["bram_sha256"][:8], "4f5f54aa")
        self.assertEqual(G.IMAGES[1000]["bram_sha256"][:8], "7004c530")
        for lat in (250, 1000):
            for f in ("boot_sha256", "ddr_sha256", "images_txt_sha256"):
                self.assertEqual(G.IMAGES[lat][f], X.IMAGE[f])
        for lat in (250, 500, 1000):
            got = dict(x.split()[::-1] for x in
                       (REPO / f"evidence/stage6gxlat/image_L{lat}/image/image.sha256").read_text().splitlines())
            want = X.IMAGE["bram_sha256"] if lat == 500 else G.IMAGES[lat]["bram_sha256"]
            self.assertEqual(got["bram.bin"], want)

    def test_vela_comparable(self):
        vj = json.loads((REPO / "evidence/stage6gxlat/vela/xlat_vela.json").read_text())
        self.assertTrue(G.vela_comparable(vj, "ad_medium_int8", 1000))
        self.assertTrue(G.vela_comparable(vj, "kws_micronet_m", 250))
        self.assertFalse(G.vela_comparable(vj, "kws_micronet_m", 1000))
        bad = json.loads(json.dumps(vj))
        bad["models"]["ad_medium_int8"]["L500"]["cms_sha256"] = "x"
        self.assertFalse(G.vela_comparable(bad, "ad_medium_int8", 250))

    def test_vela_group(self):
        rows = [{"Op Cycles": "100", "NPU": "100", "SRAM AC": "10", "DRAM AC": "50"},
                {"Op Cycles": "300", "NPU": "20", "SRAM AC": "10", "DRAM AC": "300"},
                {"Op Cycles": "400", "NPU": "20", "SRAM AC": "400", "DRAM AC": "10"}]
        self.assertAlmostEqual(G.vela_group(rows, [1, 2])["dram_bound_share"], 3 / 7)     # SRAM-bound not DRAM
        g = G.vela_group(rows, [0, 1])
        self.assertEqual((g["op_cycles"], g["npu"], g["dram"], g["bound"]), (400.0, 120.0, 350.0, ["NPU", "DRAM AC"]))
        self.assertAlmostEqual(g["dram_bound_share"], 0.75)

    def test_predictions_frozen(self):
        p = json.loads((REPO / "evidence/stage6gxlat/predictions.json").read_text())
        self.assertEqual(p["ad_medium_int8:G_0"]["delta_V"]["250_1000"], 24144.0)
        self.assertEqual(p["kws_micronet_m:G_V"]["delta_V"]["250_500"], 6585.0)
        self.assertEqual(p["kws_micronet_m:G_R"]["L500"]["op_cycles"], 55551.0)     # = X3 group value


class OnX3Data(unittest.TestCase):
    """Dry run on the X3 raw data: the L500 boots are VALID under X3 identity; under X_LAT identity they mismatch."""

    def test_l500_valid(self):
        r = G.check_l500(ROOTS, WL, caps500(), "x3_kws_B2")
        self.assertEqual(r["status"], "VALID")
        self.assertEqual(X.val(r, 1, 48)[0], 11700.0)

    def test_new_identity_rejects_x3_boot(self):
        roots = dict(ROOTS, l250=ROOTS["x3c"])
        r = G.check(roots, WL, caps500(), "x3_kws_B2", 250)
        self.assertEqual(r["status"], "CONFIG_MISMATCH")
        for why in ("image bram_sha256", "boot index", "TA registers", "TA EXT RLATENCY"):
            self.assertIn(why, r["reasons"])

    def test_identity_restored(self):
        before = (X.IMAGE, X.BOOT, X.EXT_RLATENCY, X.KEY_ROOT)
        with G.x3_identity("x3_ad_B4", 1000):
            self.assertEqual((X.EXT_RLATENCY, X.BOOT), (1000, {"x3_ad_B4": 515}))
            self.assertEqual(X.KEY_ROOT["x3_ad_B4"], "l1000")
            self.assertEqual((X.KEY_ROOT["x3_kws_B0"], X.KEY_ROOT["x3_ad_B0"]), ("x3b", "x3c"))
        self.assertEqual((X.IMAGE, X.BOOT, X.EXT_RLATENCY, X.KEY_ROOT), before)

    def test_unmeasured(self):
        self.assertEqual(G.check(ROOTS, WL, caps500(), "x3_kws_B2", 250)["status"], "UNMEASURED")

    def test_caps(self):
        c = G.caps_for(caps500(), 250)
        self.assertEqual(c["ta_ext_rlatency"], 250)
        self.assertEqual(caps500()["ta_ext_rlatency"], 500)
        self.assertEqual({k: v for k, v in c.items() if k != "ta_ext_rlatency"},
                         {k: v for k, v in caps500().items() if k != "ta_ext_rlatency"})


PRED = json.loads((REPO / "evidence/stage6gxlat/predictions.json").read_text())


def fake(npu, mac=1000.0, rng=100.0, status="VALID", wd_st=0.0, dpu=None):
    st = {s: {str(c): (0.0, 0.0) for c in cs} for s, cs in X.SETS.items()}
    st[1]["35"], st[1]["48"], st[1]["51"], st[1]["81"] = (npu, rng), (mac, 0.0), (dpu or mac, 0.0), (wd_st, 0.0)
    for c in (130, 135, 386, 391):
        st[2][str(c)] = (500.0, 0.0)
    return dict(status=status, stats=st, reasons=[])


class Judge(unittest.TestCase):
    """judge() end to end on synthetic boot results; Vela values from the frozen predictions."""

    def run_judge(self, board):
        sc, s5 = G.check, G.check_l500
        try:
            G.check = lambda roots, wl, caps, k, lat: board(k, lat)
            G.check_l500 = lambda roots, wl, caps, k: board(k, 500)
            return G.judge(ROOTS, WL, {}, REPO / "evidence/stage6gxlat/vela")
        finally:
            G.check, G.check_l500 = sc, s5

    @staticmethod
    def name(k):
        m = "kws_micronet_m" if "_kws_" in k else "ad_medium_int8"
        return m, {"B2": "G_V", "B3": "G_0", "B4": "G_R"}[k[-2:]]

    def test_board_equals_vela(self):
        def board(k, lat):
            m, g = self.name(k)
            v = PRED[f"{m}:{g}"][f"L{lat}"]["op_cycles"]
            return fake(v, wd_st=v)                      # WD_STALLED moves with NPU_ACTIVE
        s = self.run_judge(board)
        v, gr = s["verdicts"], s["groups"]
        self.assertEqual(v["measurement"], "VALID")
        self.assertEqual(v["compute_invariance"], "SUPPORTED")
        self.assertEqual(v["vela_term_fidelity"], "DIRECTION_AND_MAGNITUDE_CONSISTENT")
        self.assertEqual(gr["kws_micronet_m:G_V"]["segment"], [250, 500])
        self.assertEqual(gr["ad_medium_int8:G_V"]["segment"], [250, 1000])
        self.assertEqual(gr["kws_micronet_m:G_0"]["fidelity"], "INSUFFICIENT_EVIDENCE")   # dV 1,205 vs tol 2,423
        self.assertEqual(gr["ad_medium_int8:G_0"]["fidelity"], "DIRECTION_AND_MAGNITUDE_CONSISTENT")
        self.assertEqual(gr["ad_medium_int8:G_0"]["delta_B"], 24144.0)
        self.assertEqual(gr["ad_medium_int8:G_0"]["prediction_error_delta"], 0.0)
        self.assertEqual(gr["kws_micronet_m:G_V"]["delta_B_segment"], 6585.0)
        self.assertEqual(gr["kws_micronet_m:G_V"]["tol_250_1000"], 2423.0)
        self.assertEqual(gr["ad_medium_int8:G_R"]["slope_250_500"], 9154.0 / 250)
        self.assertEqual(v["latency_response"]["kws_micronet_m:G_0"], "SENSITIVE")      # 25,753 - 22,056 > 2,423
        self.assertEqual(v["latency_response_overall"], "SENSITIVE")
        self.assertEqual(v["pipeline_mechanism"], "PARTIALLY_SUPPORTED")
        self.assertIn(v["h_l2_term_dominance"], ("SUPPORTED", "REFUTED"))
        self.assertTrue(all(g["traffic_comparable"] for g in gr.values()))

    def test_flat_board(self):
        s = self.run_judge(lambda k, lat: fake(50000.0))
        v = s["verdicts"]
        self.assertEqual(set(v["latency_response"].values()), {"NOT_DETECTABLY_SENSITIVE"})
        self.assertEqual(v["latency_response_overall"], "NOT_DETECTABLY_SENSITIVE")
        self.assertEqual(v["vela_term_fidelity"], "INCONSISTENT")
        self.assertEqual(s["groups"]["ad_medium_int8:G_V"]["fidelity"], "INCONSISTENT")
        self.assertEqual(s["groups"]["ad_medium_int8:G_V"]["prediction_error_delta"], -40989.0)
        self.assertEqual(v["pipeline_mechanism"], "MECHANISM_UNRESOLVED")

    def test_confounded_and_invalid(self):
        def board(k, lat):
            if k == "x3_ad_B3" and lat == 1000:
                return fake(40000.0, mac=1011.0)
            if k == "x3_kws_B4" and lat == 250:
                return fake(40000.0, status="UNSTABLE")
            if k == "x3_ad_B2" and lat == 1000:
                return fake(40000.0, dpu=1011.0)
            if k == "x3_kws_B3" and lat == 500:
                return fake(40000.0, status="UNSTABLE")
            if k == "x3_ad_B4":
                return fake(40000.0 + lat, rng={250: 1500.0, 500: 100.0, 1000: 2000.0}[lat])
            return fake(40000.0 + lat)
        s = self.run_judge(board)
        v, gr = s["verdicts"], s["groups"]
        self.assertEqual(v["measurement"], "PARTIAL_VALID")
        self.assertEqual(v["compute_invariance"], "REFUTED")
        self.assertEqual(gr["ad_medium_int8:G_0"]["response"], "CONFOUNDED")
        self.assertNotIn("fidelity", gr["ad_medium_int8:G_0"])
        self.assertEqual(gr["kws_micronet_m:G_R"]["response"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(gr["kws_micronet_m:G_R"]["fidelity"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(gr["kws_micronet_m:G_R"]["status"]["L250"], "UNSTABLE")
        self.assertEqual(gr["ad_medium_int8:G_V"]["response"], "CONFOUNDED")               # DPU alone
        self.assertEqual(gr["kws_micronet_m:G_0"]["response"], "INSUFFICIENT_EVIDENCE")    # L500 not VALID
        self.assertEqual(gr["ad_medium_int8:G_R"]["tol_250_1000"], 3500.0)                # r250 + r1000

    def test_traffic_flag(self):
        def board(k, lat):
            r = fake(40000.0 + lat)
            if k == "x3_ad_B2" and lat == 250:
                r["stats"][2]["386"] = (506.0, 0.0)
            if k == "x3_ad_B3" and lat == 1000:
                r["stats"][2]["391"] = (494.0, 0.0)
            return r
        gr = self.run_judge(board)["groups"]
        self.assertFalse(gr["ad_medium_int8:G_V"]["traffic_comparable"])
        self.assertFalse(gr["ad_medium_int8:G_0"]["traffic_comparable"])                   # EXT write beats
        self.assertTrue(gr["ad_medium_int8:G_R"]["traffic_comparable"])


if __name__ == "__main__":
    unittest.main()
