"""stage6bb.py (evidence/stage6b/stage6bb/contract.md): the board judge on copies of real archived RUNs — Stage 4K boot
375 (the reference binary, n_base 5) and Stage 4AO-E boot 395 (an ADD workload with n_base 6 standing in for an A2
config) — with faults injected into the copies. Expected values typed here."""
import copy, csv, json, pathlib, shutil, sys, tempfile, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import stage6bb as B

K375 = REPO / "evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48"
A395 = REPO / "evidence/stage4aoe/raw_a1/evsweep_s4aoe2_run/conds/s4aoe_add_h24"
WL6 = REPO / "evidence/stage6b/stage6bb/workloads"
AOE_WL = REPO / "evidence/stage4aoe/workloads"
CFG = "s6bb_g12"


class Base(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp())
        self.wl, self.root = self.t / "wl", self.t / "run"
        self.wl.mkdir()
        for e in ("drwl", "drwl.tflite_ofm.bin", "compile.json"):
            shutil.copy(WL6 / f"{B.REF}.{e}", self.wl / f"{B.REF}.{e}")
        for e in ("drwl", "drwl.tflite_ofm.bin", "ref_ofm.bin"):
            shutil.copy(AOE_WL / f"s4aoe_add_h24.{e}", self.wl / f"{CFG}.{e}")
        man = json.loads((WL6 / B.MANIFEST).read_text())
        ident = json.loads((WL6 / "expected_identity.json").read_text())
        man[B.REF]["boot"] = 375
        add = json.loads((AOE_WL / "expected_identity.json").read_text())["s4aoe_add_h24"]
        man[CFG].update(boot=395, n_mac=768000, drwl_sha256=add["drwl_sha256"])
        ident[CFG] = add
        (self.wl / B.MANIFEST).write_text(json.dumps(man))
        (self.wl / "expected_identity.json").write_text(json.dumps(ident))
        shutil.copytree(K375, self.root / "conds" / B.REF)
        shutil.copytree(A395, self.root / "conds" / CFG)
        self.caps = str(self.t / "caps_ref.json")
        shutil.copy(K375 / "capabilities.json", self.caps)
        # the ADD stand-in counts no MAC; give it a Conv-like MAC_ACTIVE / MAC_DPU_ACTIVE (n_mac = 768 x 1000)
        self.edit_rows(lambda r: dict(r, event_value="1000") if r["ev_type"] in ("48", "51") else r)

    def tearDown(self):
        shutil.rmtree(self.t)

    def folder(self, cfg=CFG):
        return self.root / "conds" / cfg / "wfe"

    def edit_rows(self, fn, cfg=CFG):
        p = self.folder(cfg) / "runs.csv"
        with open(p) as f:
            rows = list(csv.DictReader(f))
        keys = list(rows[0])
        rows = [fn(dict(r)) for r in rows]
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, keys); w.writeheader(); w.writerows([r for r in rows if r is not None])

    def edit_json(self, path, fn):
        d = json.loads(path.read_text()); fn(d); path.write_text(json.dumps(d))

    def status(self, cfg=CFG):
        return B.config_result(self.root, self.wl, cfg, self.caps)


class Valid(Base):
    def test_real_runs_are_valid(self):
        for cfg in (B.REF, CFG):
            with self.subTest(cfg):
                r = self.status(cfg)
                self.assertEqual((r["status"], r["reasons"]), ("VALID", []))
        self.assertEqual(self.status()["internal_conv"], "INTERNAL_CONV_NOT_OBSERVED")

    def test_reference_metrics_are_stage4k(self):
        m = self.status(B.REF)["metrics"]
        self.assertEqual((m["mac_active"], m["n_mac"]), (3456.0, 2654208))
        self.assertAlmostEqual(m["macs_per_mac_active"], 768.0)
        self.assertAlmostEqual(m["eff_1024"], 0.75)
        self.assertEqual(m["stage4k_nearest"], 768)
        self.assertEqual((m["c16_rate_768"], B.c16_rate(40), B.c16_rate(276)), (768.0, 640.0, 768 * 276 / 288))

    def test_repro_gate_same_data_passes(self):
        self.assertEqual(B.repro_gate(str(self.root), str(self.wl), str(K375 / "wfe"), self.caps)["verdict"], "PASS")

    def test_unmeasured(self):
        shutil.rmtree(self.root / "conds" / CFG)
        r = B.boot_check(str(self.root), str(self.wl), CFG, self.caps)
        self.assertEqual((r["status"], r["stop"]), ("UNMEASURED", True))


class ConfigMismatch(Base):
    def check(self, why):
        r = B.boot_check(str(self.root), str(self.wl), CFG, self.caps)
        self.assertEqual((r["status"], r["stop"]), ("CONFIG_MISMATCH", True), r)
        self.assertTrue(any(why in x for x in r["reasons"]), r["reasons"])

    def test_workload_digest(self):
        self.edit_rows(lambda r: dict(r, workload_sha256="0" * 64)); self.check("workload sha256")

    def test_manifest_digest(self):
        self.edit_json(self.wl / B.MANIFEST, lambda d: d[CFG].update(drwl_sha256="1" * 64)); self.check("workload sha256")

    def test_image(self):
        self.edit_rows(lambda r: dict(r, boot_sha256="2" * 64)); self.check("image boot_sha256")

    def test_fpga(self):
        self.edit_rows(lambda r: dict(r, fpga_image="AN555")); self.check("fpga image")

    def test_boot_index(self):
        self.edit_json(self.wl / B.MANIFEST, lambda d: d[CFG].update(boot=411)); self.check("boot index")

    def test_condition(self):
        self.edit_rows(lambda r: dict(r, condition="busy")); self.check("condition")

    def test_ta_register(self):
        self.edit_json(self.folder().parent / "capabilities.json", lambda d: d.update(ta_ext_rlatency=0)); self.check("capabilities")

    def test_npu_mac_count(self):
        for p in (self.folder().parent / "capabilities.json", pathlib.Path(self.caps)):
            self.edit_json(p, lambda d: d.update(npu_config=d["npu_config"] - 1))
        self.check("NPU MAC count")

    def test_n_base(self):
        self.edit_json(self.wl / "expected_identity.json", lambda d: d[CFG].update(n_base=5)); self.check("identity")

    def test_regioncfg_at_irq(self):
        p = self.folder() / "raw_runs.json"
        self.edit_json(p, lambda d: d[3]["record"].update(regioncfg_irq=0x15F)); self.check("identity regioncfg")


class Output(Base):
    def test_output_bytes(self):
        p = self.folder() / "output.bin"
        b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
        r = B.boot_check(str(self.root), str(self.wl), CFG, self.caps)
        self.assertEqual((r["status"], r["stop"]), ("INVALID_OUTPUT", False))

    def test_run_reports_mismatch(self):
        self.edit_rows(lambda r: dict(r, output_match="0") if r["rep"] == "3" else r)
        self.assertEqual(self.status()["status"], "INVALID_OUTPUT")

    def test_reference_output(self):
        p = self.folder(B.REF) / "output.bin"
        b = bytearray(p.read_bytes()); b[5] ^= 1; p.write_bytes(bytes(b))
        self.assertEqual(self.status(B.REF)["status"], "INVALID_OUTPUT")

    def test_outputs_differ_between_runs(self):
        p = self.folder() / "raw_runs.json"
        self.edit_json(p, lambda d: d[4].update(output_crc32=12345))
        self.assertEqual(self.status()["status"], "INVALID_OUTPUT")


class Pmu(Base):
    def check(self, why, cfg=CFG):
        r = self.status(cfg)
        self.assertEqual(r["status"], "INVALID_PMU", r)
        self.assertTrue(any(why in x for x in r["reasons"]), r["reasons"])
        self.assertFalse(B.boot_check(str(self.root), str(self.wl), cfg, self.caps)["stop"])

    def test_overflow(self):
        self.edit_rows(lambda r: dict(r, event_overflow="True") if r["rep"] == "2" else r); self.check("overflow")

    def test_invalid_run(self):
        self.edit_rows(lambda r: dict(r, run_valid="False") if r["rep"] == "4" and r["set_id"] == "1" else r)
        self.check("RUN invalid")

    def test_measurement_window(self):
        self.edit_rows(lambda r: dict(r, cycle_valid="0") if r["rep"] == "5" else r); self.check("measurement window")

    def test_missing_counter(self):
        self.edit_rows(lambda r: None if r["rep"] == "3" and r["set_id"] == "2" and r["ev_type"] == "386" else r)
        self.check("counters missing")

    def test_wrong_pass(self):
        self.edit_rows(lambda r: dict(r, ev_type="48") if r["set_id"] == "2" and r["ev_type"] == "128" else r)
        self.check("wrong pass")

    def test_counter_of_the_other_pass(self):
        rows = []
        def f(r):
            if r["set_id"] == "2" and r["rep"] == "3" and r["ev_type"] == "128":
                rows.append(dict(r, ev_type="48", slot="8"))
            return r
        self.edit_rows(f)
        self.edit_rows(lambda r: r)
        p = self.folder() / "runs.csv"
        with open(p, "a", newline="") as fh:
            csv.DictWriter(fh, list(rows[0])).writerow(rows[0])
        self.check("wrong pass")

    def test_missing_measured_run(self):
        self.edit_rows(lambda r: None if r["rep"] == "5" and r["set_id"] == "1" else r)
        self.edit_json(self.folder() / "raw_runs.json", lambda d: d.pop(5))
        self.check("RUN")

    def test_no_warmup(self):
        self.edit_json(self.folder() / "raw_runs.json", lambda d: [x.update(rep=x["rep"] + 1) for x in d[1:]])
        self.edit_rows(lambda r: dict(r, rep=str(int(r["rep"]) + 1)))
        self.check("RUN layout")

    def test_implausible_mac(self):
        self.edit_json(self.wl / B.MANIFEST, lambda d: d[B.REF].update(n_mac=3456 * 1024 + 1))
        self.check("implausible", B.REF)


class Unstable(Base):
    def check(self, why, cfg=CFG):
        r = self.status(cfg)
        self.assertEqual(r["status"], "UNSTABLE", r)
        self.assertTrue(any(why in x for x in r["reasons"]), r["reasons"])

    def test_mac_varies(self):
        self.edit_rows(lambda r: dict(r, event_value="3457") if r["rep"] == "4" and r["ev_type"] == "48" else r, B.REF)
        self.check("MAC_ACTIVE differs", B.REF)

    def test_dpu_varies(self):
        self.edit_rows(lambda r: dict(r, event_value="3455") if r["rep"] == "2" and r["ev_type"] == "51" else r, B.REF)
        self.check("MAC_DPU_ACTIVE differs", B.REF)

    def test_npu_pass_b_shift(self):
        f = lambda r: dict(r, event_value=str(int(int(r["event_value"]) * 1.2))) if r["set_id"] == "2" and r["ev_type"] == "35" else r
        self.edit_rows(f); self.check("pass A vs pass B")

    def test_npu_range(self):
        f = lambda r: dict(r, event_value=str(int(int(r["event_value"]) * 1.08))) if r["set_id"] in ("1", "2") and r["rep"] == "2" and r["ev_type"] == "35" else r
        self.edit_rows(f); self.check("pass A range")


class ReproGate(Base):
    def test_mac_changed_fails(self):
        self.edit_rows(lambda r: dict(r, event_value="3500") if r["ev_type"] == "48" and r["set_id"] == "1" else r, B.REF)
        self.assertEqual(B.repro_gate(str(self.root), str(self.wl), str(K375 / "wfe"), self.caps)["verdict"], "FAIL")

    def test_other_binary_fails(self):
        ref = self.t / "ref"; shutil.copytree(K375 / "wfe", ref)
        p = ref / "runs.csv"
        with open(p) as f:
            rows = list(csv.DictReader(f))
        keys = list(rows[0])
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, keys); w.writeheader(); w.writerows([dict(r, workload_sha256="9" * 64) for r in rows])
        g = B.repro_gate(str(self.root), str(self.wl), str(ref), self.caps)
        self.assertEqual((g["verdict"], g["same_binary"]), ("FAIL", False))

    def test_invalid_reference_config_fails(self):
        self.edit_rows(lambda r: dict(r, event_overflow="True"), B.REF)
        self.assertEqual(B.repro_gate(str(self.root), str(self.wl), str(K375 / "wfe"), self.caps)["verdict"], "FAIL")

    def test_npu_active_outside_tolerance_fails(self):
        f = lambda r: dict(r, event_value=str(int(int(r["event_value"]) * 1.03))) if r["ev_type"] == "35" else r
        self.edit_rows(f, B.REF)
        self.assertEqual(B.repro_gate(str(self.root), str(self.wl), str(K375 / "wfe"), self.caps)["verdict"], "FAIL")


MAN_A2 = dict(kind="A2", vela_sha256="v", vela=dict(cycles_total=100, vela_sha256="v", scope="A2 graph (x)"))
OK_R = dict(status="VALID", metrics=dict(npu_active=110))


class Fidelity(unittest.TestCase):
    def test_comparable_and_sign(self):
        f = B.fidelity(MAN_A2, OK_R)
        self.assertEqual(f["status"], "COMPARABLE")
        self.assertAlmostEqual(f["error_pct"], 10.0)
        self.assertAlmostEqual(B.fidelity(MAN_A2, dict(OK_R, metrics=dict(npu_active=90)))["abs_error_pct"], 10.0)

    def test_not_comparable(self):
        cases = dict(missing=dict(MAN_A2, vela=dict(MAN_A2["vela"], cycles_total=None)),
                     other_compile=dict(MAN_A2, vela_sha256="w"),
                     scope=dict(MAN_A2, vela=dict(MAN_A2["vela"], scope="Conv")),
                     reference=dict(MAN_A2, kind="reference"))
        for k, m in cases.items():
            with self.subTest(k):
                self.assertEqual(B.fidelity(m, OK_R)["status"], "NOT_COMPARABLE")
        self.assertEqual(B.fidelity(MAN_A2, dict(status="UNSTABLE"))["status"], "NOT_COMPARABLE")

    def test_static_check_catches_missing_vela(self):
        t = pathlib.Path(tempfile.mkdtemp())
        try:
            shutil.copytree(WL6, t / "wl")
            self.assertTrue(B.static_checks(t / "wl")["ok"])
            p = t / "wl" / B.MANIFEST
            d = json.loads(p.read_text()); d[CFG]["vela"]["cycles_total"] = None; p.write_text(json.dumps(d))
            self.assertIn(f"{CFG}: Vela cycles missing", B.static_checks(t / "wl")["problems"])
            d[CFG]["vela"]["cycles_total"] = 5; d[CFG]["drwl_sha256"] = "x"; p.write_text(json.dumps(d))
            self.assertIn(f"{CFG}: drwl digest", B.static_checks(t / "wl")["problems"])
            d[CFG]["drwl_sha256"] = B.sha(t / "wl" / f"{CFG}.drwl"); d[CFG]["n_mac"] += 1; p.write_text(json.dumps(d))
            self.assertIn(f"{CFG}: N_MAC != H*W*Cin*Cout", B.static_checks(t / "wl")["problems"])
        finally:
            shutil.rmtree(t)


def res(**st):
    return {c: dict(status=st.get(c, "VALID")) for c in B.ORDER}


class Verdicts(unittest.TestCase):
    def test_characterization(self):
        ok = dict(verdict="PASS")
        self.assertEqual(B.characterization(ok, res()), "CHARACTERIZATION_VALID")
        self.assertEqual(B.characterization(ok, res(s6bb_g25="INVALID_OUTPUT")), "PARTIAL_CHARACTERIZATION")
        self.assertEqual(B.characterization(ok, res(s6bb_g28="UNMEASURED")), "PARTIAL_CHARACTERIZATION")
        self.assertEqual(B.characterization(dict(verdict="FAIL"), res()), "MEASUREMENT_INVALID")
        self.assertEqual(B.characterization(ok, res(s6bb_g09="CONFIG_MISMATCH")), "MEASUREMENT_INVALID")
        self.assertEqual(B.characterization(ok, res(**{c: "UNSTABLE" for c in B.ORDER[1:]})), "MEASUREMENT_INVALID")

    def test_fidelity_verdict(self):
        f = {c: dict(status="COMPARABLE") for c in B.ORDER}
        f[B.REF] = dict(status="NOT_COMPARABLE")
        self.assertEqual(B.fidelity_verdict(f), "FIDELITY_COMPARABLE")
        f["s6bb_g12"] = dict(status="NOT_COMPARABLE")
        self.assertEqual(B.fidelity_verdict(f), "FIDELITY_PARTIAL")
        self.assertEqual(B.fidelity_verdict({c: dict(status="NOT_COMPARABLE") for c in B.ORDER}), "FIDELITY_NOT_COMPARABLE")

    def test_order_and_boots_fixed(self):
        self.assertEqual(B.ORDER, ["s4c2_conv_cin48", "s6bb_g12", "s6bb_g25", "s6bb_g40", "s6bb_g53", "s6bb_g11", "s6bb_g56",
                                   "s6bb_g52", "s6bb_g57", "s6bb_g09", "s6bb_g28"])
        man = json.loads((WL6 / B.MANIFEST).read_text())
        self.assertEqual([man[c]["boot"] for c in B.ORDER], list(range(410, 421)))


if __name__ == "__main__":
    unittest.main()
