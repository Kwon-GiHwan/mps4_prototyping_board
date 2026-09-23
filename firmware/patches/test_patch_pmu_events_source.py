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
        self.assertEqual(g.count("cfg.mode == INSTRUMENTATION_EVENTS"), 5)   # widen x3 (edits 5,6,7) + inner if x2 (5b, 8)
        self.assertIn("NPU_REG_PMEVTYPER_BASE + 4U * i", g)
        # the event-slot arming must never be a bare write that can drop the cycle bit
        self.assertIn("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)", g)
        self.assertNotIn("pmu_reg_write(NPU_REG_PMCNTENSET, (1U << cfg.event_count) - 1U)", g)
        # TRM guarantee clause: programming happens under cnt_en=1, i.e. enable precedes
        # the PMEVTYPER writes inside the EVENTS block, and a reset pulse follows arming.
        blk = g[g.index("/* Tier B. TRM:"):g.index("cnten = pmu_reg_read(NPU_REG_PMCNTENSET);")]
        self.assertLess(blk.index("npu_pmu_enable();"), blk.index("NPU_REG_PMEVTYPER_BASE + 4U * i"))
        self.assertLess(blk.index("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)"),
                        blk.index("NPU_PMCR_CYCLE_CNT_RST_MSK | NPU_PMCR_EVENT_CNT_RST_MSK"))
        self.assertIn("NPU_REG_PMEVCNTR_BASE + 4U * i", g)
        self.assertIn("(1U << INSTRUMENTATION_EVENTS)", g)
        # END_ONLY still refuses count != 0 and still arms no slots
        self.assertIn("count != 0U && mode != INSTRUMENTATION_EVENTS", g)
        self.assertIn("/* END_ONLY, unchanged: no event slot is ever armed. */", g)

    def test_refuses_mutated_base(self):
        with self.assertRaises(SystemExit):
            P.generate(BASE.replace("uint32_t cnten;", "uint32_t cnten2;"))


if __name__ == "__main__":
    unittest.main()
