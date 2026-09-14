"""Fixtures for every gate rule and every preregistered outcome of h13_analyze. Run from the repo root:
    python3 -m unittest docs.paper.raw_data_report.amendments.h13.test_h13_analyze
Mutation check (manual, per CLAUDE.md): neuter a comparison in h13_analyze.py, this file must go RED."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h13_analyze as A  # noqa: E402

RN = "rnnoise_INT8__SSE-320__ethos-u85-%d"
BASE_M = {"npu_total_cycles": 36086, "npu_active_cycles": 35206, "sram_rd_beats": 143, "sram_wr_beats": 135,
          "ext_rd_beats": 7650, "ext_wr_beats": 36}
FROZEN = {RN % 256: dict(BASE_M)}
LOW = {"EXT_RLATENCY": 250, "EXT_WLATENCY": 125, "EXT_MAXR": 24, "EXT_PULSE_ON": 4000, "EXT_PULSE_OFF": 1000, "EXT_BWCAP": 2344}


def meas(total, **kw):
    m = dict(BASE_M); m["npu_total_cycles"] = total; m["npu_active_cycles"] = total - 880; m.update(kw); return m


def recs(cell, arm, total, exp="H1A", is_base=False, reps=3, status="SUCCESS", header=True, frozen_art=True,
         verify_sha="abc", verify_status="SUCCESS", vela_sha="v1", defines=None, verify_m=None, **kw):
    art = {"vela_sha256": vela_sha, "frozen_vela_sha256": "v1" if frozen_art else None, "cc_body_sha256": "c1",
           "frozen_cc_body_sha256": "c1" if frozen_art else None}
    out = []
    for rep in range(1, reps + 1):
        r = {"experiment": exp, "cell_id": cell, "arm": arm, "defines": defines or dict(LOW), "is_base": is_base, "rep": rep,
             "status": status, "measurement": meas(total, **kw), "artifact": art, "header_matches_request": header}
        if rep == 1:
            r["verify"] = {"build_ok": True, "status": verify_status, "dump_sha256": verify_sha, "measurement": verify_m or meas(total, **kw)}
        out.append(r)
    return out


def h1a_cell(mac, k_r=100, k_w=0, c0=21086, both0=None, base=36086):
    cell = RN % mac; rs = []; seen = set()
    def add(arm, total, **kw):
        if arm not in seen:
            seen.add(arm); rs.extend(recs(cell, arm, total, **kw))
    if mac == 256:
        add("r250_w125", base, is_base=True)
    for r in (0, 125, 250, 500, 1000):
        add("r%d_w250" % r, c0 + 250 * k_w + k_r * r, is_base=(mac != 256 and r == 500))
    for w in (0, 125, 250, 500):
        add("r500_w%d" % w, c0 + 500 * k_r + k_w * w)
    rs += recs(cell, "r0_w0", both0 if both0 is not None else c0)
    return rs


class Gates(unittest.TestCase):
    def rule(self, records, frozen=FROZEN):
        return A.analyze(records, [], frozen)["gates"][RN % 256].get("refused")

    def test_run_status(self):
        self.assertEqual(self.rule(recs(RN % 256, "r0_w250", 22086, status="FAILURE_TIMEOUT") + recs(RN % 256, "r250_w125", 36086, is_base=True)), None)
        g = A.analyze(recs(RN % 256, "r0_w250", 22086, status="FAILURE_TIMEOUT") + recs(RN % 256, "r250_w125", 36086, is_base=True), [], FROZEN)["gates"][RN % 256]
        self.assertEqual(g["notes"][0]["rule"], A.RULE_RUN)

    def test_reps_differ(self):
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True); rs[2]["measurement"]["npu_total_cycles"] = 36087
        self.assertEqual(self.rule(rs), A.RULE_BASE_MISMATCH)  # base arm refused at G3 -> no passing base -> G2 rule
        g = A.analyze(rs, [], FROZEN)["gates"][RN % 256]
        self.assertEqual(g["msg"].split(":")[0], RN % 256)
        rs2 = recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086)
        rs2[-1]["measurement"]["npu_total_cycles"] = 1
        self.assertEqual(A.analyze(rs2, [], FROZEN)["gates"][RN % 256]["notes"][0]["rule"], A.RULE_REPS_DIFFER)

    def test_header(self):
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, header=False)
        self.assertEqual(A.analyze(rs, [], FROZEN)["gates"][RN % 256]["notes"][0]["rule"], A.RULE_TA_HEADER)

    def test_artifact(self):
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, vela_sha="other")
        self.assertEqual(A.analyze(rs, [], FROZEN)["gates"][RN % 256]["notes"][0]["rule"], A.RULE_ARTIFACT)

    def test_base_mismatch(self):
        self.assertEqual(self.rule(recs(RN % 256, "r250_w125", 36087, is_base=True)), A.RULE_BASE_MISMATCH)
        self.assertEqual(self.rule(recs(RN % 256, "r250_w125", 36086, is_base=True)), None)

    def test_output_mismatch(self):
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, verify_sha="zzz")
        self.assertEqual(self.rule(rs), A.RULE_OUTPUT_MISMATCH)

    def test_synthetic_artifact_identity(self):
        cell = "h3_conv1x1_6x6_c128__SSE-320__ethos-u85-256"
        rs = recs(cell, "base", 1000, frozen_art=False, vela_sha="s1") + recs(cell, "relaxed", 900, frozen_art=False, vela_sha="s2")
        self.assertEqual(A.analyze(rs, [], {})["gates"][cell]["refused"], A.RULE_ARTIFACT)

    def test_instrumentation_note(self):
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True, verify_m=meas(36090))
        notes = A.analyze(rs, [], FROZEN)["gates"][RN % 256]["notes"]
        self.assertEqual(notes[0]["note"], "INSTRUMENTATION_DEVIATION")

    def test_rules_tuple_complete(self):
        tripped = set()
        for rs in (recs(RN % 256, "r250_w125", 36087, is_base=True),
                   recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, verify_sha="z")):
            tripped.add(A.analyze(rs, [], FROZEN)["gates"][RN % 256].get("refused"))
        for rs in (recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, header=False),
                   recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, vela_sha="x"),
                   recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086, status="FAILURE_TIMEOUT")):
            tripped.add(A.analyze(rs, [], FROZEN)["gates"][RN % 256]["notes"][0]["rule"])
        rs = recs(RN % 256, "r250_w125", 36086, is_base=True) + recs(RN % 256, "r0_w250", 22086); rs[-1]["measurement"]["npu_total_cycles"] = 5
        tripped.add(A.analyze(rs, [], FROZEN)["gates"][RN % 256]["notes"][0]["rule"])
        self.assertEqual(tripped, set(A.RULES))


class H1A(unittest.TestCase):
    def run_(self, rs, frozen=None):
        return A.analyze(rs, [], frozen if frozen is not None else {})["H1A"]

    def test_read_dominant_additive(self):
        o = self.run_(h1a_cell(256, k_r=100, k_w=10))
        self.assertEqual(o[256]["outcome"], "READ_DOMINANT"); self.assertEqual(o[256]["additivity"], "ADDITIVE")
        self.assertAlmostEqual(o[256]["k_r"], 100.0); self.assertAlmostEqual(o[256]["k_w"], 10.0)

    def test_write_dominant_and_mixed(self):
        self.assertEqual(self.run_(h1a_cell(256, k_r=5, k_w=100))[256]["outcome"], "WRITE_DOMINANT")
        self.assertEqual(self.run_(h1a_cell(256, k_r=50, k_w=50))[256]["outcome"], "MIXED")

    def test_non_additive(self):
        self.assertEqual(self.run_(h1a_cell(256, k_r=100, k_w=10, both0=30000))[256]["additivity"], "NON_ADDITIVE")

    def test_cross_mac(self):
        self.assertEqual(self.run_(h1a_cell(256, k_r=100) + h1a_cell(512, k_r=110))["cross_mac"], "SENSITIVITY_SIMILAR_ACROSS_MAC")
        self.assertEqual(self.run_(h1a_cell(256, k_r=100) + h1a_cell(512, k_r=120))["cross_mac"], "SENSITIVITY_DIFFERS_ACROSS_MAC")


def h1b_cell(mac, s, base_total=36086):
    cell = RN % mac; wb = 125 if mac == 256 else 250; rs = []
    for m, slope in s.items():
        rs += recs(cell, "maxr%d_r250_w%d" % (m, wb), 30000, exp="H1B")
        rs += recs(cell, "maxr%d_r1000_w%d" % (m, wb), 30000 + int(750 * slope), exp="H1B")
    return rs


class H1B(unittest.TestCase):
    def run_(self, rs):
        return A.analyze(rs, [], {})["H1B"]

    def test_reduces(self):
        o = self.run_(h1b_cell(256, {1: 100, 4: 90, 16: 80, 63: 70, 64: 70, 0: 70}))[256]
        self.assertEqual(o["outcome"], "CONCURRENCY_REDUCES_SENSITIVITY"); self.assertEqual(o["maxr64"], "MAXR64_IS_UNLIMITED")

    def test_no_effect_and_partial(self):
        self.assertEqual(self.run_(h1b_cell(256, {1: 100, 4: 101, 16: 99, 63: 100, 64: 100, 0: 100}))[256]["outcome"], "CONCURRENCY_NO_EFFECT_IN_RANGE")
        o = self.run_(h1b_cell(256, {1: 100, 4: 60, 16: 90, 63: 100, 64: 80, 0: 100}))[256]
        self.assertEqual(o["outcome"], "PARTIAL_OR_NON_MONOTONE"); self.assertEqual(o["maxr64"], "MAXR64_DISTINCT")

    def test_limit_note(self):
        self.assertEqual(self.run_(h1b_cell(256, {1: 100, 4: 70, 16: 70, 63: 70, 64: 70, 0: 70}))[256]["note"], "NPU_OUTSTANDING_LIMIT_LE_4_SUSPECTED")


class H1C(unittest.TestCase):
    def test_predictions(self):
        cell = RN % 256
        for obs, want in (((52757, 89229), "LINEAR_ADEQUATE"), ((49086, 89086), "PIECEWISE_ADEQUATE"), ((30000, 60000), "NEITHER_MODEL_PREDICTS")):
            rs = recs(cell, "r375_w187", obs[0], exp="H1Ca") + recs(cell, "r750_w375", obs[1], exp="H1Ca")
            self.assertEqual(A.analyze(rs, [], {})["H1Ca"][256]["outcome"], want)

    def test_generalisation(self):
        def cell(name, c0, c1000):
            return recs(name, "r0_w250", c0, exp="H1Cb") + recs(name, "r1000_w250", c1000, exp="H1Cb")
        k, a = "kws_micronet_m__SSE-320__ethos-u85-256", "ad_medium_int8__SSE-320__ethos-u85-256"
        self.assertEqual(A.analyze(cell(k, 1000, 1200) + cell(a, 1000, 1500), [], {})["H1Cb"]["generalisation"], "GENERALISES_TO_KWS_AD")
        self.assertEqual(A.analyze(cell(k, 1000, 1050) + cell(a, 1000, 1090), [], {})["H1Cb"]["generalisation"], "RNNOISE_SPECIFIC")
        self.assertEqual(A.analyze(cell(k, 1000, 1200) + cell(a, 1000, 1050), [], {})["H1Cb"]["generalisation"], "PARTIAL")


W2L = "wav2letter_pruned_int8__SSE-320__ethos-u85-512"


def h2a_cell(cycles, beats=None, zero=None):
    rs = []
    d = {"EXT_PULSE_ON": 4000, "EXT_PULSE_OFF": 1000}
    for cap, cyc in cycles.items():
        b = (beats or {}).get(cap, 1000)
        rs += recs(W2L, "bw%d_r500_w250" % cap, cyc, exp="H2A", defines=dict(d, EXT_BWCAP=cap), ext_rd_beats=b, ext_wr_beats=0)
    for cap, cyc in (zero or {}).items():
        rs += recs(W2L, "bw%d_r0_w0" % cap, cyc, exp="H2A", defines=dict(d, EXT_BWCAP=cap), ext_rd_beats=1000, ext_wr_beats=0)
    return rs


class H2A(unittest.TestCase):
    def run_(self, rs):
        return A.analyze(rs, [], {})["H2A"][512]

    def test_constrained(self):
        self.assertEqual(self.run_(h2a_cell({1875: 1500, 3750: 1000, 7500: 850, 0: 850}))["outcome"], "EXT_CAP_CONSTRAINED")

    def test_not_binding(self):
        # nominal cap at 3750 = 12 B/cyc; 1000 beats*16/1000 cycles = 16 B/cyc?? -> use small beats so achieved < 0.9 cap
        self.assertEqual(self.run_(h2a_cell({1875: 1020, 3750: 1000, 7500: 990, 0: 990}, beats={3750: 100}))["outcome"], "EXT_CAP_NOT_BINDING_IN_RANGE")

    def test_raise_ineffective(self):
        self.assertEqual(self.run_(h2a_cell({1875: 1020, 3750: 1000, 7500: 990, 0: 990}, beats={3750: 700}))["outcome"], "CAP_RAISE_INEFFECTIVE_NOT_EVIDENCE")

    def test_lowering_only(self):
        self.assertEqual(self.run_(h2a_cell({1875: 1200, 3750: 1000, 7500: 960, 0: 960}))["outcome"], "CAP_LOWERING_SLOWS_ONLY")

    def test_interaction(self):
        o = self.run_(h2a_cell({1875: 1500, 3750: 1000, 7500: 850, 0: 850}, zero={3750: 900, 7500: 600})); self.assertEqual(o["interaction"], "LATENCY_CAP_INTERACTION")
        o = self.run_(h2a_cell({1875: 1500, 3750: 1000, 7500: 850, 0: 850}, zero={3750: 900, 7500: 765})); self.assertEqual(o["interaction"], "NO_INTERACTION_DETECTED")


class SramCap(unittest.TestCase):
    def run_(self, cyc):
        cell = "kws_micronet_m__SSE-300__ethos-u55-256"; rs = []
        for cap, c in cyc.items():
            rs += recs(cell, "sbw%d" % cap, c, exp="SRAMCAP", axi0_rd_beats=10, axi0_wr_beats=10, sram_rd_beats=None, sram_wr_beats=None)
        return A.analyze(rs, [], {})["SRAMCAP"][cell]["outcome"]

    def test_outcomes(self):
        self.assertEqual(self.run_({2000: 1200, 4000: 1000, 8000: 850, 0: 850}), "SRAM_CAP_CONSTRAINED_AT_DEFAULT")
        self.assertEqual(self.run_({2000: 1200, 4000: 1000, 8000: 990, 0: 990}), "SRAM_CAP_LOWERING_SLOWS")
        self.assertEqual(self.run_({2000: 1050, 4000: 1000, 8000: 990, 0: 990}), "SRAM_CAP_NOT_BINDING_IN_RANGE")


def h3_records(ratios, relaxed=None):
    """ratios: {(op, H, W): r} -> cells at 256 (1000 cycles) and 512 (1000*r)."""
    rs, man = [], []
    for (op, h, w), r in ratios.items():
        name = "h3_%s_%dx%d_c128" % (op, h, w); area = h * w
        man.append({"model": name, "op": op, "H": h, "W": w, "area": area})
        for mac, cyc in ((256, 1000), (512, int(1000 * r))):
            cell = "%s__SSE-320__ethos-u85-%d" % (name, mac)
            rs += recs(cell, "base", cyc, exp="H3", frozen_art=False)
            if relaxed and (op, h, w) in relaxed:
                rr = relaxed[(op, h, w)]
                rs += recs(cell, "relaxed", cyc if mac == 256 else int(1000 * rr), exp="H3", frozen_art=False)
    return rs, man


class H3(unittest.TestCase):
    def test_shape_effect_and_interaction(self):
        rat = {("conv1x1", 1, 36): 0.9, ("conv1x1", 6, 6): 0.6, ("conv1x1", 2, 18): 0.8}
        rs, man = h3_records(rat, relaxed={k: 0.7 for k in rat})
        o = A.analyze(rs, man, {})["H3"]["outcomes"]
        self.assertIn("SHAPE_EFFECT:conv1x1:36", o); self.assertIn("MEMORY_SHAPE_INTERACTION:conv1x1", o)

    def test_no_shape_effect(self):
        rs, man = h3_records({("conv1x1", 1, 36): 0.70, ("conv1x1", 6, 6): 0.65, ("conv1x1", 2, 18): 0.72})
        self.assertNotIn("SHAPE_EFFECT:conv1x1:36", A.analyze(rs, man, {})["H3"]["outcomes"])

    def test_no_interaction_and_not_type_dependent(self):
        rat = {("conv1x1", 1, 36): 0.9, ("conv1x1", 6, 6): 0.6, ("conv3x3", 1, 36): 0.85, ("conv3x3", 6, 6): 0.7, ("dw3x3", 1, 36): 0.8, ("dw3x3", 6, 6): 0.72}
        rel = {("conv1x1", 1, 36): 0.9, ("conv1x1", 6, 6): 0.7}   # spread 0.2 vs base 0.3 -> not < 50 %
        o = A.analyze(*h3_records(rat, relaxed=rel), {})["H3"]["outcomes"]
        self.assertNotIn("MEMORY_SHAPE_INTERACTION:conv1x1", o); self.assertNotIn("TYPE_DEPENDENT", o)

    def test_area_and_type(self):
        rat = {}
        for a, (h, w), r in ((36, (6, 6), 0.9), (36, (1, 36), 0.9), (64, (8, 8), 0.8), (64, (1, 64), 0.8), (256, (16, 16), 0.6), (256, (1, 256), 0.6)):
            rat[("conv1x1", h, w)] = r
        rat[("conv3x3", 6, 6)] = 0.6; rat[("conv3x3", 1, 36)] = 0.6; rat[("dw3x3", 6, 6)] = 0.7; rat[("dw3x3", 1, 36)] = 0.7
        o = A.analyze(*h3_records(rat), {})["H3"]["outcomes"]
        self.assertIn("AREA_EFFECT:conv1x1", o); self.assertIn("TYPE_DEPENDENT", o)


if __name__ == "__main__":
    unittest.main()
