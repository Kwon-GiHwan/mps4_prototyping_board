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
        self.assertEqual(g.count("#define MEASUREMENT_FIELD_COUNT 103U"), 1)
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
        self.assertIn("(h[1] != 1U && h[1] != 2U)", blk)
        self.assertIn("return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;", blk)
        self.assertIn("if (pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS) != h[16])", blk)
        self.assertIn("#define NPU_OFF_QCONFIG   0x1CU", blk)          # interface.h value, not a guess
        self.assertIn("if (pmwl_knob[i] != PMWL_OFF) { pmwl_knob_pending = 1U; }", blk)  # any knob arms the seam
        self.assertIn("return PMWL_REFUSED;", blk)
        self.assertLess(blk.index("memset(arena + h[11], 0xA5"), blk.index("memcpy(arena + h[8]"))
        self.assertLess(blk.index("memcpy(arena + h[8]"), blk.index("rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);"))
        # apply seam: lives in __wrap_printf, guarded, reads every override back
        wp = g[g.index("int __wrap_printf(const char *fmt, ...)\n{\n    /* Tier B read seam"):]
        ap = wp[wp.index("Tier C step 2 apply seam"):wp.index("#endif", wp.index("Tier C step 2 apply seam"))]
        self.assertIn('"Updating POWER_CTRL register with MAC_RAMP_VAR=%d \\n"', ap)
        self.assertLess(ap.index("npu_write(off[k], pmwl_knob[k]);"), ap.index("npu_read(off[k]) != pmwl_knob[k]"))
        self.assertIn("x.out_ver_data_0 = s + h[13];", blk)
        # the step-0b test3 wrap still exists in the #else branch
        self.assertIn("#else\nint __wrap_test_u85(", g)

    def test_refuses_mutated_base(self):
        with self.assertRaises(SystemExit):
            P.generate(BASE.replace("uint32_t cnten;", "uint32_t cnten2;"))


if __name__ == "__main__":
    unittest.main()
