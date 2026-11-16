"""stage6be1r.py (evidence/stage6b/stage6be1r/contract.md): the cycle floor, memory, rank key, execution-config de-dup,
DPU extra slot, build conditions, selection status and the D-PW verdict, on synthetic facts. Expected values typed here."""
import pathlib, sys, unittest
from unittest import mock
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6be1r as X


def facts(cin, h, w, cout, ublock="2x2x32", ifm_block="8x8x64", ofm_block="8x8x64", kernels=None, trav="DepthFirst",
          cycles=60000, mem=("Dram", "Dram")):
    rows = [dict(npu_op="Conv2D", cpu="0", cms_offsets="100", traversal=trav, ofm_block=ofm_block, ifm_block=ifm_block,
                 ofm_ublock=ublock, kernel="1x1", ifm_memory=mem[0], ofm_memory=mem[1], vela_op_cycles=str(cycles)),
            dict(npu_op="Relu6", cpu="0", cms_offsets="", traversal="", ofm_block="xx", ifm_block="xx", ofm_ublock="xx",
                 kernel="1x1", ifm_memory=mem[1], ofm_memory=mem[1], vela_op_cycles="0")]
    ks = kernels or [[h, w, cout]]
    return dict(n_ethosu_ops=1, rows=rows, kernels=[dict(ofm=k, ifm_depth=cin, offset=100, kind="CONV") for k in ks])


NAME = lambda cin, h, w, cout: f"e1r_c{cin}_h{h}w{w}_o{cout}"


def case(cin, h, cout, **kw):
    return X.case_of(NAME(cin, h, h, cout), facts(cin, h, h, cout, **kw))


def elig(cin, h, cout, existing=frozenset(), **kw):
    return X.eligible(NAME(cin, h, h, cout), facts(cin, h, h, cout, **kw), set(existing))


class Eligibility(unittest.TestCase):
    def test_good_and_floor(self):
        self.assertTrue(elig(72, 25, 96)[0])
        self.assertTrue(elig(72, 25, 96, cycles=50000)[0])                 # the floor is inclusive
        ok, why = elig(72, 25, 96, cycles=49999)
        self.assertFalse(ok)
        self.assertEqual(why, ["Vela cycles 49999 < 50000"])

    def test_cycles_sum_rows(self):
        f = facts(72, 25, 25, 96, cycles=40000)
        f["rows"][1]["vela_op_cycles"] = "15000"
        self.assertEqual(X.vela_cycles(f), 55000)
        f["rows"][1]["vela_op_cycles"] = ""
        self.assertEqual(X.vela_cycles(f), 40000)

    def test_memory(self):
        for mem in (("Sram", "Dram"), ("Dram", "Sram")):
            with self.subTest(mem):
                ok, why = elig(72, 25, 96, mem=mem)
                self.assertFalse(ok)
                self.assertEqual(why, [f"memory {mem[0]}/{mem[1]}"])

    def test_e1_terms_kept(self):
        self.assertFalse(elig(72, 25, 96, trav="PartKernel")[0])
        self.assertFalse(elig(72, 25, 96, existing={(25, 25, 72, 96)})[0])
        self.assertFalse(elig(64, 24, 96, ifm_block="8x8x64")[0])        # 64, 24x24, one kernel 2x2x32: no split

    def test_existing_includes_e1_six(self):
        ex = X.existing_shapes()
        for s in ((13, 13, 72, 96), (13, 13, 136, 96), (7, 7, 72, 48), (13, 13, 200, 96), (13, 13, 80, 96), (7, 7, 72, 112)):
            self.assertIn(s, ex)
        self.assertIn((24, 24, 48, 96), ex)


class RankAndSig(unittest.TestCase):
    def test_min_gap_hand(self):
        # Cin 72 (64+8), 8x8, Cout 96, 2x2x32: 48 ublocks. H1-UC 48*(8+4)=576; competitors 576 (H1-G, no-spatial,
        # whole-Cout), 480 (C16, U16, no-chunks), 432 (U8, no-min32) -> five differ, smallest gap 96
        c = case(72, 8, 96)
        self.assertEqual(X.E.n_split(c), 5)
        self.assertEqual(X.min_gap(c), 96)

    def test_exec_sig(self):
        self.assertEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(80, 25, 96)))      # 8 and 16 both cost 32
        self.assertNotEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(100, 25, 96)))  # 36 -> 48
        self.assertNotEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(72, 27, 96)))   # kernel size
        self.assertNotEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(72, 25, 96, ublock="2x4x16")))
        self.assertNotEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(72, 25, 96, ofm_block="6x8x96")))
        self.assertNotEqual(X.exec_sig(case(72, 25, 96)), X.exec_sig(case(72, 25, 96, ifm_block="8x8x16")))

    def test_rank_order(self):
        rows = [dict(case="b", vela_cycles=60000, s=5, g=96), dict(case="a", vela_cycles=60000, s=5, g=96),
                dict(case="c", vela_cycles=90000, s=5, g=96), dict(case="d", vela_cycles=50000, s=5, g=200),
                dict(case="e", vela_cycles=50000, s=6, g=1)]
        with mock.patch.object(X.E, "n_split", lambda c: c["s"]), mock.patch.object(X, "min_gap", lambda c: c["g"]):
            self.assertEqual([r["case"] for r in sorted(rows, key=X.rank_key)], ["e", "d", "c", "a", "b"])


class BuildOk(unittest.TestCase):
    GOOD = dict(pack_rc=0, fits=True, deterministic=True, golden_sha256="g", ref_sha256="g", reference=dict(n=25 * 25 * 96))

    def test_good(self):
        self.assertEqual(X.build_ok(NAME(72, 25, 25, 96), self.GOOD), (True, []))

    def test_each_failure(self):
        bad = dict(pack=dict(pack_rc=1), fits=dict(fits=False), det=dict(deterministic=False),
                   golden=dict(golden_sha256="x"), nogolden=dict(golden_sha256=None, ref_sha256=None),
                   length=dict(reference=dict(n=25 * 25 * 95)))
        for k, kw in bad.items():
            with self.subTest(k):
                self.assertFalse(X.build_ok(NAME(72, 25, 25, 96), dict(self.GOOD, **kw))[0])


class Select(unittest.TestCase):
    def pool(self):
        # only u8 (64+24) splits D-PW from D-U8; 64+8 and 64+64+8 do not (8 -> 1 either way)
        return dict(
            a72=case(72, 26, 96),                                            # E1-A (64+8)
            a80=case(80, 26, 96),                                            # E1-A, same execution config as a72
            b=case(136, 25, 96),                                             # E1-B (odd edge)
            c=case(136, 26, 48, ublock="2x4x16"),                            # E1-C
            d=case(128, 26, 96, kernels=[[26, 26, 16], [26, 26, 80]]),       # E1-D only (64+64)
            u8=case(88, 26, 112),                                            # 64+24: D-PW 64/8+32/8 vs D-U8 64/8+24/8
            x=case(136, 26, 176),
            y=case(136, 26, 80),
        )

    def test_one_per_category_dedup_extras(self):
        p = self.pool()
        s = X.select(list(p.values()), {})
        self.assertEqual(s["status"], "OK")
        self.assertEqual(len(s["selected"]), 6)
        sel = [c for c in p.values() if c["case"] in s["selected"]]
        for cat in X.CATEGORIES:
            name = next(n for n, r in s["role"].items() if r == cat)
            self.assertIn(cat, X.E.categories(next(c for c in sel if c["case"] == name)))
        self.assertEqual(len({X.exec_sig(c) for c in sel}), 6)               # no repeated execution config
        self.assertFalse(p["a72"]["case"] in s["selected"] and p["a80"]["case"] in s["selected"])
        self.assertEqual(s["role"][p["u8"]["case"]], "extra-DPU")
        self.assertEqual(s["need_build"], s["selected"])

    def test_extra_skips_same_cin_cout(self):
        p = self.pool()
        dup = case(136, 27, 176)                                             # same (Cin, Cout) as x, other config
        with mock.patch.object(X, "rank_key", lambda c: (0 if c["case"] == dup["case"] else 1, c["case"])):
            s = X.select([p["a72"], p["b"], p["c"], p["d"], p["x"], dup, p["y"]], {})
        self.assertIn(dup["case"], s["selected"])
        self.assertNotIn(p["x"]["case"], s["selected"])

    def test_twin_config_never_selected(self):
        # a80 has a72's execution config and is next in rank: it must not fill the last slot (-> NEEDS_REVISION)
        p = self.pool()
        order = ["a72", "a80", "b", "c", "d", "u8"]
        names = {p[k]["case"]: i for i, k in enumerate(order)}
        with mock.patch.object(X, "rank_key", lambda c: names[c["case"]]):
            s = X.select([p[k] for k in order], {})
        self.assertEqual(s["role"][p["a72"]["case"]], "E1-A")
        self.assertNotIn(p["a80"]["case"], s["selected"])
        self.assertEqual((s["status"], len(s["selected"])), ("NEEDS_REVISION", 5))

    def test_failed_build_skipped(self):
        p = self.pool()
        s1 = X.select(list(p.values()), {})
        first = next(n for n, r in s1["role"].items() if r == "E1-A")
        s2 = X.select(list(p.values()), {first: False})
        self.assertNotIn(first, s2["selected"])
        s3 = X.select(list(p.values()), {n: True for n in s1["selected"]})
        self.assertEqual((s3["selected"], s3["need_build"]), (s1["selected"], []))

    def test_missing_category_needs_revision(self):
        p = self.pool()
        s = X.select([c for k, c in p.items() if k != "c"], {})
        self.assertEqual(s["status"], "NEEDS_REVISION")
        self.assertEqual(s["missing_categories"], ["E1-C"])

    def test_dpu_slot_falls_back(self):
        p = self.pool()
        s = X.select([c for k, c in p.items() if k != "u8"], {})
        self.assertNotIn("extra-DPU", s["role"].values())
        self.assertEqual(s["status"], "OK")


class Verdicts(unittest.TestCase):
    def shape(self, cls, pw, u16, u8, match_pw=True):
        dpu = {"D-PW": dict(pred=pw, match=match_pw), "D-U16": dict(pred=u16, match=False), "D-U8": dict(pred=u8, match=False)}
        return dict(cls=cls, dpu=dpu)

    def test_dpu(self):
        both = [self.shape("PRIMARY_VALID", 10, 12, 10), self.shape("PRIMARY_VALID", 10, 10, 9)]
        self.assertEqual(X.dpu_verdict(both), "D-PW_CONSISTENT")
        self.assertEqual(X.dpu_verdict(both[:1]), "INSUFFICIENT_EVIDENCE")              # no D-U8 split
        self.assertEqual(X.dpu_verdict(both[1:]), "INSUFFICIENT_EVIDENCE")              # no D-U16 split
        self.assertEqual(X.dpu_verdict(both + [self.shape("PRIMARY_VALID", 10, 12, 10, False)]), "D-PW_CONTRADICTED")
        self.assertEqual(X.dpu_verdict([self.shape("MAC_ONLY_DIAGNOSTIC", 10, 12, 10), both[1]]), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(X.dpu_verdict(both + [self.shape("MAC_ONLY_DIAGNOSTIC", 10, 12, 10, False)]), "D-PW_CONSISTENT")
        self.assertEqual(X.dpu_verdict(both + [self.shape("PRIMARY_VALID", 10, 10, 10, False)]), "D-PW_CONSISTENT")

    def test_npu_table(self):
        t = X.npu_table(dict(metrics=dict(npu_active=60000, npu_active_range=1200, npu_active_pass_b=60100)))
        self.assertEqual((t["a_median"], t["a_range"], t["a_range_pct"], t["b_median"]), (60000, 1200, 2.0, 60100))
        self.assertIsNone(X.npu_table(dict())["a_range_pct"])

    def test_predictions_fields(self):
        p = X.predictions(case(88, 26, 112, cycles=70000))
        self.assertEqual(p["vela_cycles"], 70000)
        self.assertTrue(p["dpu_pw_vs_u8_split"])
        self.assertFalse(X.predictions(case(72, 26, 112))["dpu_pw_vs_u8_split"])        # 64+8: 8 -> 1 either way


if __name__ == "__main__":
    unittest.main()
