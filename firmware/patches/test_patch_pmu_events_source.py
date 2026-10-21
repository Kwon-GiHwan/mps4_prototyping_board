"""The generator must land every edit on the real base, and refuse a wrong base."""
import hashlib, pathlib, sys, unittest
HERE = pathlib.Path(__file__).parent; sys.path.insert(0, str(HERE))
import patch_pmu_events_source as P
BASE = (HERE.parent / "Selftest_pmu" / "runner_pmu_main.c").read_text()


class T(unittest.TestCase):
    def test_base_is_pinned(self):
        self.assertEqual(hashlib.sha256(BASE.encode()).hexdigest(), P.BASE_SHA256)

    def test_every_anchor_unique_in_base(self):
        for anchor, _ in P.EDITS:
            self.assertEqual(BASE.count(anchor), 1, anchor[:60])

    def test_generated_carries_mode_2(self):
        g = P.generate(BASE)
        self.assertIn("#define INSTRUMENTATION_EVENTS    2U", g)
        self.assertEqual(g.count("cfg.mode == INSTRUMENTATION_EVENTS"), 6)   # widen x3 (5,6,7) + inner if x2 (5b,8) + seam (11)
        self.assertIn("NPU_REG_PMEVTYPER_BASE + 4U * i", g)
        self.assertIn("NPU_REG_PMEVCNTR_BASE + 4U * k", g)   # read in the seam (amendment 7)
        self.assertIn("(1U << INSTRUMENTATION_EVENTS)", g)
        self.assertIn("count != 0U && mode != INSTRUMENTATION_EVENTS", g)
        self.assertIn("/* END_ONLY, unchanged: no event slot is ever armed. */", g)
        # arming is ONE write carrying the cycle bit; no bare event-bits write; no PMCR write of ours
        self.assertIn("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)", g)
        self.assertNotIn("pmu_reg_write(NPU_REG_PMCNTENSET, (1U << cfg.event_count) - 1U)", g)
        # amendment 8: exactly one extra reset-bit write, the held-power PMCR = EN|RST of the diag sequence
        self.assertEqual(g.count("NPU_PMCR_CYCLE_CNT_RST_MSK"), BASE.count("NPU_PMCR_CYCLE_CNT_RST_MSK") + 1)
        # ordering: arming (programming block) < cnt_en verified < event selects < run_fixed_inference
        # amendment 8: EVENTS programming = hold(CMD=0) < guard < PMCR EN|RST < guard < arm < selects
        #               < base enable/verify < run; END_ONLY's own three lines survive in the else branch
        blk = g[g.index("/* Tier B (amendment 8)."):g.index("run_rc = run_fixed_inference();")]
        order = ["npu_write(NPU_OFF_CMD, 0U);", "pmu_events_wait_cycles(PMU_EVENTS_POWER_GUARD_CYCLES);",
                 "NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK", "pmu_events_wait_cycles(PMU_EVENTS_RESET_GUARD_CYCLES);",
                 "NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)", "NPU_REG_PMEVTYPER_BASE + 4U * i",
                 "r.cycle_global_enable_verified ="]
        idx = [blk.index(x) for x in order]
        self.assertEqual(idx, sorted(idx))
        self.assertEqual(g.count("pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);"), 1)
        self.assertEqual(g.count("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)"), 1)  # armed once
        self.assertIn("#define NPU_OFF_CMD 0x08U", g)
        self.assertEqual(g.count("#define PMU_EVENTS_POWER_GUARD_CYCLES 65536U"), 1)
        # amendment 7: seam storage, seam hook in __wrap_printf, snapshot copied into the record,
        # one appended record word and the field count bumped exactly once
        self.assertIn('strcmp(fmt, "Testing CPM signals\\n") == 0', g)
        self.assertIn("r.npu_pmu_window_cycles_lo = seam_cycle_lo;", g)
        self.assertIn("put32(&c, r->read_seam_fired);", g)
        self.assertIn("#if defined(PMU_EVENTS_EXT_DRAM)\n#define MEASUREMENT_FIELD_COUNT 109U\n#else\n#define MEASUREMENT_FIELD_COUNT 103U\n#endif", g)
        self.assertIn("put32(&c, r->read_seam_fired);\n#if defined(PMU_EVENTS_EXT_DRAM)\n    put32(&c, r->vendor_rc);\n"
                      "    put32(&c, r->seam_npu_status);\n    put32(&c, r->seam_npu_qread);\n"
                      "    put32(&c, r->ofm_mismatch_count);\n    put32(&c, r->ofm_max_abs_diff);\n    put32(&c, r->ofm_first_mismatch);\n#endif", g)
        self.assertEqual(g.count("last_vendor_rc = rc;"), 2)
        cpm = g[g.index("Tier B read seam (amendment 7)"):g.index("seam_fired++;")]
        self.assertIn("seam_status = npu_read(NPU_OFF_STATUS);", cpm)   # before the vendor's CMD=0xC   # both wraps (model, test3) record it
        self.assertNotIn("#define MEASUREMENT_FIELD_COUNT 102U", g)
        wrap = g[g.index("int __wrap_printf(const char *fmt, ...)\n{\n    /* Tier B read seam"):]
        self.assertLess(wrap.index("npu_pmu_read_cycles"), wrap.index("seam_fired++"))

    def test_step0b_wrap_is_guarded(self):
        g = P.generate(BASE)
        blk = g[g.index("#else\nint __wrap_test_u85("):g.index("#endif /* PMU_EVENTS_MODEL */")]   # the test3 (step 0b) body
        self.assertIn("int __wrap_test_u85(", blk)
        self.assertIn("rc = __real_test_u85(", blk)
        # poison precedes the call; copy-back follows it
        self.assertLess(blk.index("memset(d + EXT_DRAM_OUT_OFF, 0xA5"), blk.index("rc = __real_test_u85("))
        self.assertLess(blk.index("rc = __real_test_u85("), blk.index("memcpy(w->out_data_0"))
        self.assertIn("__attribute__((noinline))", g[g.index("#endif /* PMU_EVENTS_MODEL */"):g.index("static int32_t run_fixed_inference(void)")])
        self.assertEqual(g.count("rc = (int32_t)apU85Conv_TEST(&m);"), 1)   # runner entry unchanged

    def test_step1_model_branch(self):
        g = P.generate(BASE)
        blk = g[g.index("#if defined(PMU_EVENTS_MODEL)"):g.index("#endif /* PMU_EVENTS_MODEL */")]
        self.assertIn("h[15] != model_total_length", blk)
        self.assertIn("h[1] < 1U || h[1] > 4U", blk)
        self.assertIn("NPU_OFF_AXI_SRAM, NPU_OFF_AXI_EXT};", g)
        self.assertIn("return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;", blk)
        self.assertIn("if (pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS) != h[16])", blk)
        self.assertIn("#define NPU_OFF_QCONFIG   0x1CU", blk)          # interface.h value, not a guess
        self.assertIn("if (pmwl_knob[i] != PMWL_OFF) { pmwl_knob_pending = 1U; }", blk)  # any knob arms the seam
        self.assertIn("return PMWL_REFUSED;", blk)
        # every OFM poisoned, then every IFM copied (version 4 IO table; one entry each before it), then the run
        self.assertLess(blk.index("memset(arena + io[e], 0xA5"), blk.index("memcpy(arena + io[e], s + io[e + 2U]"))
        self.assertLess(blk.index("memcpy(arena + io[e], s + io[e + 2U]"), blk.index("rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);"))
        # apply seam: lives in __wrap_printf, guarded, reads every override back
        wp = g[g.index("int __wrap_printf(const char *fmt, ...)\n{\n    /* Tier B read seam"):]
        ap = wp[wp.index("Tier C step 2 apply seam"):wp.index("#endif", wp.index("Tier C step 2 apply seam"))]
        self.assertIn('"Updating POWER_CTRL register with MAC_RAMP_VAR=%d \\n"', ap)
        self.assertLess(ap.index("npu_write(off[k], pmwl_knob[k]);"), ap.index("npu_read(off[k]) != pmwl_knob[k]"))
        self.assertIn("x.out_ver_data_0 = s + h[13];", blk)
        self.assertLess(blk.index("rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);"), blk.index("ofm_mm_count++;"))
        # the step-0b test3 wrap still exists in the #else branch
        self.assertIn("#else\nint __wrap_test_u85(", g)

    def test_power_ctrl_knob(self):
        g = P.generate(BASE)
        blk = g[g.index("#if defined(PMU_EVENTS_MODEL)"):g.index("#endif /* PMU_EVENTS_MODEL */")]
        # strong hook in the model branch; OFF passes the vendor value through
        self.assertIn("uint32_t u85_power_ctrl_value(uint32_t v)\n{\n    return (pmwl_power_ctrl == PMWL_OFF) ? v : pmwl_power_ctrl;\n}", blk)
        self.assertIn("pmwl_power_ctrl = h[25];", blk)
        self.assertLess(blk.index("pmwl_power_ctrl = h[25];"), blk.index("rc = __real_test_u85("))
        # the seam reads POWER_CTRL while the NPU is still powered, and the wrap refuses a mismatch
        seam = g[g.index('strcmp(fmt, "Testing CPM signals\\n") == 0'):]
        self.assertLess(seam.index("seam_power_ctrl = npu_read(NPU_OFF_POWER_CTRL);"), seam.index("seam_fired++;"))
        self.assertIn("#define NPU_OFF_POWER_CTRL 0x38U", g)     # ethosu85_interface.h NPU_REG_POWER_CTRL
        chk = blk.index("if (seam_power_ctrl != ((pmwl_power_ctrl == PMWL_OFF) ? PMWL_VENDOR_MAC_RAMP : pmwl_power_ctrl))")
        self.assertLess(blk.index("rc = __real_test_u85("), chk)
        self.assertLess(chk, blk.index("return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;"))
        self.assertIn("#define PMWL_VENDOR_MAC_RAMP 2U", blk)
        self.assertIn("seam_power_ctrl = 0U;", g)                 # cleared when the window opens

    def test_onchip_fast_knob(self):
        g = P.generate(BASE)
        blk = g[g.index("#if defined(PMU_EVENTS_MODEL)"):g.index("#endif /* PMU_EVENTS_MODEL */")]
        chk = blk[blk.index("    if (h[26] != PMWL_OFF) {"):]
        chk = chk[:chk.index("        fast = (uint8_t *)(uintptr_t)h[26];")]
        # every refusal condition present, and the refusal precedes the assignment
        for cond in ("pmwl_region_ext(2U)", "(h[26] & 0xFFU) != 0U", "h[26] < (uint32_t)(uintptr_t)__StackTop",
                     "h[26] > PMWL_SRAM_END", "h[7] > PMWL_SRAM_END - h[26]", "return PMWL_REFUSED;"):
            self.assertIn(cond, chk)
        self.assertIn("#define PMWL_SRAM_END 0x31400000U", blk)   # lnk.ld SRAM 0x31000000 + 0x00400000
        # applied after the default placement, before the vendor run
        self.assertLess(blk.index("if (pmwl_region_ext(2U)) { fast = dram; } else { fast = near; }"),
                        blk.index("fast = (uint8_t *)(uintptr_t)h[26];"))
        self.assertLess(blk.index("fast = (uint8_t *)(uintptr_t)h[26];"), blk.index("x.in_data_0      = fast;"))

    def test_ta_profile_knob(self):
        g = P.generate(BASE)
        blk = g[g.index("#if defined(PMU_EVENTS_MODEL)"):g.index("#endif /* PMU_EVENTS_MODEL */")]
        self.assertIn("static const uint32_t pmwl_ta_base[2] = {0x51102000U, 0x51102400U};", blk)   # MLEK mps4 TA bases
        self.assertIn("#define PMWL_TA_VERSION 0x1117U", blk)
        self.assertIn("{0x00U, 0x04U, 0x08U, 0x0CU, 0x10U, 0x14U, 0x18U, 0x1CU, 0x20U, 0x28U, 0x30U}", blk)  # timing_adapter.c map
        # MLEK sys_dram_mid, Dedicated_Sram branch, pre-masked
        self.assertIn("{{8U, 8U, 0U, 32U, 32U, 3999U, 1U, 4000U, 0U, 1U, 0U},", blk)
        self.assertIn("{0U, 32U, 0U, 500U, 250U, 4000U, 1000U, 3750U, 0U, 1U, 0U}},", blk)
        self.assertEqual(blk.count("{0U, 0U, 0U, 0U, 0U, 0xFFFFU, 0U, 0U, 0U, 1U, 0U}"), 2)
        fn = blk[blk.index("static uint32_t pmwl_ta_apply(uint32_t prof)"):]
        fn = fn[:fn.index("return bad;")]
        self.assertIn("if (ta[0x38U / 4U] != PMWL_TA_VERSION) { bad = 1U; continue; }", fn)
        self.assertLess(fn.index("ta[pmwl_ta_off[k] / 4U] = pmwl_ta_val"), fn.index("if (ta[pmwl_ta_off[k] / 4U] != pmwl_ta_val"))
        self.assertIn("pmwl_ta_val[prof - 1U][p][k]", fn)
        # applied in the wrap after knob_bad is cleared and before the vendor run; bad values refused
        self.assertIn("if (h[27] < 1U || h[27] > 2U) { return PMWL_REFUSED; }", blk)
        self.assertLess(blk.index("    pmwl_knob_bad = 0U;\n"), blk.index("if (pmwl_ta_apply(h[27]) != 0U) { pmwl_knob_bad = 1U; }"))
        self.assertLess(blk.index("if (pmwl_ta_apply(h[27]) != 0U)"), blk.index("rc = __real_test_u85("))

    def test_step3_state_table(self):
        g = P.generate(BASE)
        self.assertIn("#if defined(PMU_EVENTS_MODEL)\n#define M_EVENTS_MODEL M(CB_SET_INSTRUMENTATION_MODE)\n#else\n#define M_EVENTS_MODEL 0U\n#endif", g)
        tbl = g[g.index("static const uint32_t state_accepts[ST_COUNT]"):]
        tbl = tbl[:tbl.index("};") + 2]
        self.assertEqual(tbl.count("M_EVENTS_MODEL"), 2)
        self.assertLess(tbl.index("ST_INPUT_READY"), tbl.index("M_EVENTS_MODEL"))   # not in IDLE/BOOT rows

    def test_refuses_mutated_base(self):
        with self.assertRaises(SystemExit):
            P.generate(BASE.replace("uint32_t cnten;", "uint32_t cnten2;"))


if __name__ == "__main__":
    unittest.main()
