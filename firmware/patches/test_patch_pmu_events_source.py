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
        self.assertEqual(g.count("cfg.mode == INSTRUMENTATION_EVENTS"), 6)   # widen x3 (edits 5,6,7) + inner if x3 (5b, 6b, 8)
        self.assertIn("NPU_REG_PMEVTYPER_BASE + 4U * i", g)
        self.assertIn("NPU_REG_PMEVCNTR_BASE + 4U * i", g)
        self.assertIn("(1U << INSTRUMENTATION_EVENTS)", g)
        self.assertIn("count != 0U && mode != INSTRUMENTATION_EVENTS", g)
        self.assertIn("/* END_ONLY, unchanged: no event slot is ever armed. */", g)
        # arming is ONE write carrying the cycle bit; no bare event-bits write; no PMCR write of ours
        self.assertIn("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)", g)
        self.assertNotIn("pmu_reg_write(NPU_REG_PMCNTENSET, (1U << cfg.event_count) - 1U)", g)
        self.assertEqual(g.count("NPU_PMCR_CYCLE_CNT_RST_MSK"), BASE.count("NPU_PMCR_CYCLE_CNT_RST_MSK"))
        # ordering: arming (programming block) < cnt_en verified < event selects < run_fixed_inference
        i_arm = g.index("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)")
        i_ver = g.index("r.cycle_global_enable_verified =")
        i_sel = g.index("NPU_REG_PMEVTYPER_BASE + 4U * i")
        i_run = g.index("run_rc = run_fixed_inference();")
        self.assertTrue(i_arm < i_ver < i_sel < i_run)

    def test_refuses_mutated_base(self):
        with self.assertRaises(SystemExit):
            P.generate(BASE.replace("uint32_t cnten;", "uint32_t cnten2;"))


if __name__ == "__main__":
    unittest.main()
