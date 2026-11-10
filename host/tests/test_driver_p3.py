import csv, json, sys, tempfile, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import driver_p3 as D

SETS = {1: [35, 17], 2: [35, 48, 51, 53, 55, 64, 80, 81], 3: [35, 128, 130, 132, 135, 384, 386, 391]}
JIT = {3: -400, 4: 0, 5: 400}                       # NPU_ACTIVE moves 0.8 % RUN to RUN


def caps(**over):
    c = {f"ta_sram_{k}": v for k, v in D.TA_EXPECTED["ta_sram_"].items()}
    c.update({f"ta_ext_{k}": v for k, v in D.TA_EXPECTED["ta_ext_"].items()})
    c.update(D.NPU_EXPECTED, ta_ext_maxr=0, ta_sram_perfctrl=0, ta_ext_perfctrl=0, cfg_sram_cap=0x21F3F,
             cfg_ext_cap=0x21F3F, power_requests=1)
    c.update(over)
    return c


def write_boot(d, active=100000, mac=60000, beats=(10, 20, 30, 1), ofm="0", valid="True", npu_exec=100500,
               host=150000, set_shift=None, arm=1, irq=1, legacy=False, host_shift=None, ofm_by_set=None,
               drop_set=None):
    d.mkdir(parents=True, exist_ok=True)
    rows, raw = [], [{"ping": {}}]
    vals = {48: mac, 130: beats[0], 135: beats[1], 386: beats[2], 391: beats[3]}
    for s, codes in SETS.items():
        if s == drop_set:
            continue
        for rep in (1, 2, 3, 4, 5):
            a = active + JIT.get(rep, 0) + (set_shift or {}).get(s, 0)
            rec = {"event_count": len(codes), "arm_count": arm, "irq_count": irq,
                   "ccnt_irq_lo": npu_exec, "ccnt_irq_hi": 0}
            for i, e in enumerate(codes):
                v = a if e == 35 else vals.get(e, 7)
                rec[f"event_code{i}"], rec[f"ev_irq{i}"] = e, v
                rows.append(dict(set_id=s, rep=rep, slot=i, ev_type=e, event_value=v, run_valid=valid,
                                 event_overflow="False", window_cycles=npu_exec, infer_npu_cycles=npu_exec,
                                 infer_cpu_cycles=npu_exec, infer_sys_ticks="", host_run_s="",
                                 host_end_to_end_cycles=host + (host_shift or {}).get(s, 0),
                                 ofm_mismatch_count=(ofm_by_set or {}).get(s, ofm)))
            raw.append(dict(set_id=s, rep=rep, record=rec))
    with (d / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    if not legacy:
        (d / "raw_runs.json").write_text(json.dumps(raw))
        (d / "capabilities.json").write_text(json.dumps(caps()))
    return d


class Checks(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = pathlib.Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def run_main(self, **kw):
        write_boot(self.d / "drv" / "wfe" / "kws", **kw)
        write_boot(self.d / "leg" / "kws", legacy=True)
        return D.main(str(self.d / "drv"), str(self.d / "leg"), str(self.d / "out"))["kws"]

    def test_all_pass(self):
        r = self.run_main()
        self.assertEqual([r[k] for k in ("D1", "D2", "D3", "D4", "D5", "D6")],
                         ["PLATFORM_AS_MLEK", "EXEC_OK", "WINDOW_OK", "STABLE", "REPRODUCES_LEGACY", "PMU_INERT"])
        self.assertEqual(r["D1_detail"]["e2"], "E2_SAME")

    def test_each_check_fails(self):
        self.assertEqual(self.run_main(ofm="2")["D2"], "EXEC_INVALID")
        self.assertEqual(self.run_main(valid="False")["D2"], "EXEC_INVALID")
        self.assertEqual(self.run_main(irq=2)["D3"], "WINDOW_INVALID")
        self.assertEqual(self.run_main(arm=0)["D3"], "WINDOW_INVALID")
        self.assertEqual(self.run_main(npu_exec=99000)["D3"], "WINDOW_INVALID")          # execution < active
        self.assertEqual(self.run_main(mac=60001)["D5"], "DIFFERS_FROM_LEGACY")
        self.assertEqual(self.run_main(beats=(10, 20, 30, 2))["D5"], "DIFFERS_FROM_LEGACY")
        self.assertEqual(self.run_main(active=103000)["D5"], "DIFFERS_FROM_LEGACY")      # 3 % > legacy width
        self.assertEqual(self.run_main(active=100300)["D5"], "REPRODUCES_LEGACY")        # 0.3 % inside
        self.assertEqual(self.run_main(set_shift={2: 3000})["D6"], "PMU_EFFECTIVE")      # set A 3 % slower
        self.assertEqual(self.run_main(set_shift={3: 500})["D6"], "PMU_INERT")           # 0.5 % inside 1 %
        self.assertEqual(self.run_main(host_shift={2: 3000})["D6"], "PMU_EFFECTIVE")     # host span 2 % longer
        self.assertEqual(self.run_main(ofm_by_set={3: "1"})["D6"], "PMU_EFFECTIVE")      # output changes with set B
        self.assertEqual(self.run_main(drop_set=3)["D6"], "UNPROVEN")

    def test_warmup_parameter(self):
        write_boot(self.d / "drv" / "wfe" / "kws", active=100000)
        write_boot(self.d / "leg" / "kws", legacy=True)
        # rep 2 is far off: excluded with the default 2 warm-up RUNs, included (and then not STABLE in MAC) with 1
        import csv as _c
        f = self.d / "drv" / "wfe" / "kws" / "runs.csv"
        rows = list(_c.DictReader(f.open()))
        for r in rows:
            if r["rep"] == "2" and r["ev_type"] == "48":
                r["event_value"] = "1"
            if r["rep"] == "2" and r["set_id"] == "2":
                r["run_valid"] = "False"
        with f.open("w", newline="") as fh:
            w = _c.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        self.assertEqual(D.main(str(self.d / "drv"), str(self.d / "leg"), str(self.d / "o2"))["kws"]["D4"], "STABLE")
        r1 = D.main(str(self.d / "drv"), str(self.d / "leg"), str(self.d / "o1"), 1)["kws"]
        self.assertEqual((r1["D4"], r1["D2"]), ("UNSTABLE", "EXEC_INVALID"))
        self.assertEqual(D.main(str(self.d / "drv"), str(self.d / "leg"), str(self.d / "o3"))["kws"]["D2"], "EXEC_OK")

    def test_platform(self):
        self.assertEqual(D.platform(caps())[0], "PLATFORM_AS_MLEK")
        self.assertEqual(D.platform(caps(ta_ext_maxr=64)), ("PLATFORM_AS_MLEK", D.platform(caps(ta_ext_maxr=64))[1]))
        self.assertEqual(D.platform(caps(ta_ext_maxr=64))[1]["e2"], "E2_DIFFERS")
        self.assertEqual(D.platform(caps(ta_ext_maxr=5))[1]["e2"], "E2_OTHER")
        for k in ("ta_sram_maxr", "ta_ext_rlatency", "axi_sram", "mem_attr2", "power_ctrl"):
            self.assertEqual(D.platform(caps(**{k: 99}))[0], "PLATFORM_DIFFERS", k)
        self.assertEqual(D.platform(None)[0], "UNPROVEN")

    def test_repeat_and_missing(self):
        runs = {(2, 3): dict(ev={48: 5, 130: 1, 135: 1, 386: 1, 391: 1}),
                (2, 4): dict(ev={48: 6, 130: 1, 135: 1, 386: 1, 391: 1})}
        self.assertEqual(D.repeat(runs), "UNSTABLE")
        self.assertEqual(D.repeat({(2, 3): dict(ev={48: 5})}), "UNPROVEN")
        self.assertEqual(D.legacy({}, {(1, 3): {}})[0], "UNPROVEN")
        self.assertEqual(D.window([{"ping": {}}]), "UNPROVEN")
        self.assertEqual(D.execution([]), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
