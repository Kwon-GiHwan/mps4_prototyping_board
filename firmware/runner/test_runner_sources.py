"""Order and refusal properties of the runner sources that the build gate cannot see in the ELF.

Ported from the retired string-patch generator's tests (firmware/patches/test_patch_pmu_events_source.py, removed
with the generator): the same properties, read from runner/ and common/ instead of the generated file."""
import pathlib, re, unittest

FW = pathlib.Path(__file__).resolve().parents[1]
RD = lambda *p: (FW.joinpath(*p)).read_text()
MEASURE, PMWL, IO, PROTO, TA = RD("runner", "measure.c"), RD("runner", "pmwl.c"), RD("runner", "io_wrap.c"), \
    RD("runner", "proto.c"), RD("common", "ta.c")
MEASURE_H = RD("runner", "measure.h")


def between(text, start, end):
    a = text.index(start)
    return text[a:text.index(end, a)]


class EventsMode(unittest.TestCase):
    def test_mode_2_and_refusals(self):
        self.assertIn("#define INSTRUMENTATION_EVENTS    2U", MEASURE_H)
        self.assertIn("count != 0U && mode != INSTRUMENTATION_EVENTS", MEASURE)
        self.assertIn("(1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY) | (1U << INSTRUMENTATION_EVENTS)",
                      MEASURE)
        self.assertIn("/* END_ONLY, unchanged: no event slot is ever armed. */", MEASURE)

    def test_arming_is_one_write_with_the_cycle_bit(self):
        self.assertEqual(MEASURE.count("NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)"), 1)
        self.assertNotIn("pmu_reg_write(NPU_REG_PMCNTENSET, (1U << cfg.event_count) - 1U)", MEASURE)
        self.assertEqual(MEASURE.count("pmu_reg_write(NPU_REG_PMCNTENSET, NPU_PMU_PMCNTEN_CYCLE_MASK);"), 1)

    def test_held_power_programming_order(self):
        # hold(CMD=0) < guard < PMCR EN|RST < guard < arm < selects < enable verified < the run
        run = MEASURE[MEASURE.index("void handle_run(uint32_t sequence)"):]
        order = ["npu_write(NPU_OFF_CMD, 0U);", "timing_wait_cycles(PMU_EVENTS_POWER_GUARD_CYCLES);",
                 "NPU_PMCR_CNT_EN_MSK | NPU_PMCR_EVENT_CNT_RST_MSK", "timing_wait_cycles(PMU_EVENTS_RESET_GUARD_CYCLES);",
                 "NPU_PMU_PMCNTEN_CYCLE_MASK | ((1U << cfg.event_count) - 1U)", "NPU_REG_PMEVTYPER_BASE + 4U * i",
                 "r.cycle_global_enable_verified =", "run_rc = run_fixed_inference();"]
        idx = [run.index(x) for x in order]
        self.assertEqual(idx, sorted(idx))
        self.assertIn("#define PMU_EVENTS_POWER_GUARD_CYCLES 65536U", MEASURE)
        self.assertIn("#define PMU_EVENTS_RESET_GUARD_CYCLES 65536U", MEASURE)


class ReadSeam(unittest.TestCase):
    def test_cpm_seam_reads_before_counting_itself(self):
        cpm = between(IO, 'strcmp(fmt, "Testing CPM signals\\n") == 0', "seam_fired++;")
        for stmt in ("npu_pmu_read_cycles", "seam_ovf = npu_pmu_overflow_status();",
                     "pmu_reg_read(NPU_REG_PMEVCNTR_BASE + 4U * k)", "seam_status = npu_read(NPU_OFF_STATUS);",
                     "seam_power_ctrl = npu_read(NPU_OFF_POWER_CTRL);"):
            self.assertIn(stmt, cpm)
        self.assertIn("measurement_active && instr_cfg.mode == INSTRUMENTATION_EVENTS", IO)

    def test_apply_seam_writes_then_reads_back(self):
        ap = between(IO, '"Updating POWER_CTRL register with MAC_RAMP_VAR=%d \\n"', "pmwl_knob_pending = 0U;")
        self.assertLess(ap.index("npu_write(off[k], pmwl_knob[k]);"), ap.index("npu_read(off[k]) != pmwl_knob[k]"))
        self.assertIn("measurement_active && pmwl_knob_pending", IO)

    def test_seam_state_cleared_when_the_window_opens(self):
        open_ = between(MEASURE, "/* ================= WINDOW OPENS ================= */", "measurement_active = 1U;")
        for stmt in ("seam_fired = 0U;", "seam_power_ctrl = 0U;", "ofm_mm_count = 0U;", "ofm_mm_first = 0xFFFFFFFFU;",
                     "last_vendor_rc = -1;", "seam_ev[k] = 0U;"):
            self.assertIn(stmt, open_)


class Record(unittest.TestCase):
    def test_events_record_comes_from_the_seam(self):
        self.assertIn("r.npu_pmu_window_cycles_lo = seam_cycle_lo;", MEASURE)
        self.assertIn("r.event_values[i] = seam_ev[i];", MEASURE)
        self.assertIn("#define MEASUREMENT_FIELD_COUNT 109U", MEASURE_H)
        tail = ("put32(&c, r->read_seam_fired);\n    put32(&c, r->vendor_rc);\n    put32(&c, r->seam_npu_status);\n"
                "    put32(&c, r->seam_npu_qread);\n    put32(&c, r->ofm_mismatch_count);\n"
                "    put32(&c, r->ofm_max_abs_diff);\n    put32(&c, r->ofm_first_mismatch);\n}")
        self.assertIn(tail, MEASURE)
        self.assertEqual(PMWL.count("last_vendor_rc = rc;"), 1)

    def test_measured_roots_stay_symbols(self):
        # check_measure_symbols.py locates the measured path and the dispatcher by name in the ELF
        self.assertIn("__attribute__((noinline))\nstatic int32_t run_fixed_inference(void)", MEASURE)
        self.assertIn("__attribute__((noinline))\nstatic void dispatch(", PROTO)
        self.assertEqual(MEASURE.count("rc = (int32_t)apU85Conv_TEST(&m);"), 1)


class Blob(unittest.TestCase):
    def test_header_checks_and_refusals(self):
        self.assertIn("h[15] != model_total_length", PMWL)
        self.assertIn("h[1] < 1U || h[1] > 4U", PMWL)
        self.assertIn("return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;", PMWL)
        self.assertIn("if (pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS) != h[16])", PMWL)
        self.assertIn("if (pmwl_knob[i] != PMWL_OFF) { pmwl_knob_pending = 1U; }", PMWL)   # any knob arms the seam
        self.assertIn("x.out_ver_data_0 = s + h[13];", PMWL)

    def test_poison_copy_run_compare_order(self):
        order = ["memset(arena + io[e], 0xA5", "memcpy(arena + io[e], s + io[e + 2U]",
                 "rc = __real_test_u85(eTest, h[14], h[12], h[3], &x);", "ofm_mm_count++;"]
        idx = [PMWL.index(x) for x in order]
        self.assertEqual(idx, sorted(idx))

    def test_power_ctrl_knob(self):
        self.assertIn("uint32_t u85_power_ctrl_value(uint32_t v)\n{\n    return (pmwl_power_ctrl == PMWL_OFF) ? v : "
                      "pmwl_power_ctrl;\n}", PMWL)
        self.assertLess(PMWL.index("pmwl_power_ctrl = h[25];"), PMWL.index("rc = __real_test_u85("))
        chk = PMWL.index("if (seam_power_ctrl != ((pmwl_power_ctrl == PMWL_OFF) ? PMWL_VENDOR_MAC_RAMP : pmwl_power_ctrl))")
        self.assertLess(PMWL.index("rc = __real_test_u85("), chk)
        self.assertLess(chk, PMWL.index("return pmwl_knob_bad ? PMWL_KNOB_NOT_HONOURED : rc;"))
        self.assertIn("#define PMWL_VENDOR_MAC_RAMP 2U", PMWL)

    def test_onchip_fast_knob(self):
        chk = between(PMWL, "    if (h[26] != PMWL_OFF) {", "        fast = (uint8_t *)(uintptr_t)h[26];")
        for cond in ("pmwl_region_ext(2U)", "(h[26] & 0xFFU) != 0U", "h[26] < (uint32_t)(uintptr_t)__StackTop",
                     "h[26] > PMWL_SRAM_END", "h[7] > PMWL_SRAM_END - h[26]", "return PMWL_REFUSED;"):
            self.assertIn(cond, chk)
        self.assertLess(PMWL.index("if (pmwl_region_ext(2U)) { fast = dram; } else { fast = near; }"),
                        PMWL.index("fast = (uint8_t *)(uintptr_t)h[26];"))
        self.assertLess(PMWL.index("fast = (uint8_t *)(uintptr_t)h[26];"), PMWL.index("x.in_data_0      = fast;"))

    def test_ta_profile_applied_after_clear_before_run(self):
        self.assertLess(PMWL.index("    pmwl_knob_bad = 0U;\n"), PMWL.index("if (ta_apply(h[27]) != 0U) { pmwl_knob_bad = 1U; }"))
        self.assertLess(PMWL.index("if (ta_apply(h[27]) != 0U)"), PMWL.index("rc = __real_test_u85("))


class TimingAdapters(unittest.TestCase):
    def test_apply_checks_version_and_reads_back(self):
        fn = between(TA, "uint32_t ta_apply(uint32_t prof)", "return bad;")
        self.assertIn("if (ta[0x38U / 4U] != TA_VERSION) { bad = 1U; continue; }", fn)
        self.assertLess(fn.index("ta[ta_off[k] / 4U] = ta_val"), fn.index("if (ta[ta_off[k] / 4U] != ta_val"))
        self.assertIn("ta_val[prof - 1U][p][k]", fn)


class StateTable(unittest.TestCase):
    def test_set_mode_accepted_in_input_and_result_ready_only(self):
        self.assertIn("#define M_EVENTS_MODEL M(CB_SET_INSTRUMENTATION_MODE)", PROTO)
        tbl = PROTO[PROTO.index("static const uint32_t state_accepts[ST_COUNT]"):]
        tbl = tbl[:tbl.index("};") + 2]
        self.assertEqual(tbl.count("M_EVENTS_MODEL"), 2)
        self.assertLess(tbl.index("ST_INPUT_READY"), tbl.index("M_EVENTS_MODEL"))
        self.assertIsNone(re.search(r"ST_(BOOT|MODEL_LOADING|MODEL_READY|RUNNING)[^\n]*M_EVENTS_MODEL", tbl))


if __name__ == "__main__":
    unittest.main()
