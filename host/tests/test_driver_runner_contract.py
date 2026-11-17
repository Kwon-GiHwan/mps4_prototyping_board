"""The driver runner firmware and the host declare record v2, the capabilities, the DRWL layout and the request ids
independently. This test reads the C sources (the X-macro lists and defines) and requires them to equal the host
modules; neither side imports the other. A change on one side only must turn this RED."""
import re, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import driver_link
import drwl
import qread_trace
import record_v2
import runner_proto

UC = REPO / "firmware" / "driver_runner" / "use_case" / "pmu_runner"
INC = {p.name: p.read_text() for p in (UC / "include").glob("*.h")}
SRC = {p.name: p.read_text() for p in (UC / "src").glob("*.c*")}


def define(name, text):
    m = re.search(rf"#define {name}\s+(0x[0-9A-Fa-f]+|\d+)U", text)
    if not m:
        raise AssertionError(f"{name} not defined")
    return int(m.group(1), 0)


def xmacro(text, name, helpers):
    """Expands a field-list macro the way the C preprocessor does for X(name): helper macros expand to their 8 or
    11 generated names."""
    body = re.search(rf"#define {name}\(X\)((?:.*\\\n)*.*)", text).group(1).replace("\\\n", " ")
    out = []
    for tok in re.findall(r"(\w+)\(X(?:, (\w+))?\)|X\((\w+)\)", body):
        helper, prefix, plain = tok
        out += helpers[helper](prefix) if helper else [plain]
    return out


EIGHT = lambda p: [f"{p}{i}" for i in range(8)]
TA = lambda p: [f"{p}{n}" for n in record_v2.TA11]


class Record(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(xmacro(INC["record.h"], "DRV_RECORD_FIELDS", {"DRV_EV8": EIGHT}), record_v2.FIELDS)

    def test_header_and_flags(self):
        h = INC["record.h"]
        self.assertEqual(define("RECORD_MAGIC", h), record_v2.MAGIC)
        self.assertEqual(define("RECORD_ABI_VERSION", h), record_v2.ABI_VERSION)
        self.assertEqual(define("RECORD_HEADER_WORDS", h), record_v2.HEADER_WORDS)
        self.assertEqual(define("RECORD_SCHEMA", h), record_v2.SCHEMA)
        flags = dict(re.findall(r"(REC_\w+)\s*=\s*1u << (\d)", h))
        self.assertEqual([int(flags[k]) for k in ("REC_COMPLETED", "REC_INVOKE_OK", "REC_ONE_ARM", "REC_ONE_IRQ",
                                                  "REC_NO_OVERFLOW", "REC_OUTPUT_MATCH")], list(range(6)))
        self.assertEqual((record_v2.COMPLETED, record_v2.OUTPUT_MATCH), (1, 32))
        self.assertLessEqual(4 * (record_v2.HEADER_WORDS + len(record_v2.FIELDS)), runner_proto.MAX_PAYLOAD)

    def test_crc_rule_is_the_v1_rule(self):
        c = SRC["record.c"]
        self.assertIn("crc32_update(0xFFFFFFFFU, out + 16, 12U)", c)   # words 4..6
        self.assertIn("crc32_update(crc, out + 32,", c)                 # words 8..end, word 7 skipped


class Caps(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(xmacro(INC["caps.h"], "DRV_CAPS_FIELDS", {"DRV_TA11": TA}), record_v2.CAPS_FIELDS)
        self.assertEqual(define("CAPS_MAGIC", INC["caps.h"]), record_v2.CAPS_MAGIC)

    def test_ta_offsets_equal_the_legacy_table(self):
        legacy = (REPO / "firmware" / "common" / "ta.c").read_text()
        want = re.search(r"ta_off\[11\] = \{([^}]*)\}", legacy).group(1)
        got = re.search(r"kTaOff\[11\] = \{([^}]*)\}", SRC["platform.cc"]).group(1)
        self.assertEqual(want.replace(" ", ""), got.replace(" ", ""))
        self.assertIn("0x51102000U, 0x51102400U", SRC["platform.cc"])


class Workload(unittest.TestCase):
    def test_layout(self):
        h = INC["workload.h"]
        self.assertEqual(define("DRWL_MAGIC", h), drwl.MAGIC)
        self.assertEqual(define("DRWL_VERSION", h), drwl.VERSION)
        self.assertEqual(define("DRWL_HEADER_WORDS", h), drwl.HEADER_WORDS)
        self.assertEqual(define("DRWL_IO_WORD", h), drwl.IO_WORD)
        self.assertEqual(define("DRWL_IO_MAX", h), drwl.IO_MAX)
        self.assertEqual(define("DRWL_ALIGN", h), drwl.ALIGN)
        offs = re.findall(r"rd32\(blob \+ (\d+)\)", SRC["workload.c"])
        want = {str(4 * drwl.HEADER_FIELDS.index(f)) for f in ("version", "total_len", "model_off", "model_len",
                                                               "n_in", "n_out", "placement")}
        self.assertTrue(want <= set(offs), (want, offs))


class Placement(unittest.TestCase):
    """docs/plan/stage4_memory_placement_plan.md F1-F4: the firmware's placement values against the host and against the
    literals of MLEK b2c0bb2 (source/hal/source/components/npu/CMakeLists.txt Dedicated_Sram: NPU_QCONFIG=3,
    NPU_REGIONCFG_0=3, NPU_REGIONCFG_1=3, regions 2-7 = 1; Shared_Sram region 1 = 0) and of the core driver
    (ethosu85_interface.h NPU_REG_QCONFIG 0x1C, NPU_REG_REGIONCFG 0x3C)."""
    P = INC["placement.h"]

    def test_values(self):
        self.assertEqual((define("PLACEMENT_DDR", self.P), define("PLACEMENT_SRAM", self.P), define("PLACEMENT_MODES", self.P)),
                         (drwl.PLACEMENT_DDR, drwl.PLACEMENT_SRAM, len(drwl.PLACEMENTS)))
        self.assertEqual((define("PLACEMENT_QCONFIG", self.P), define("PLACEMENT_REGION0", self.P),
                          define("PLACEMENT_REGION1_DDR", self.P), define("PLACEMENT_REGION2_7", self.P),
                          define("PLACEMENT_REGION1_SRAM", self.P)), (3, 3, 3, 1, 0))
        self.assertEqual(define("PLACEMENT_SRAM_ALIGN", self.P), 0x10000)
        self.assertEqual((define("PLACEMENT_SRAM_W", self.P), define("PLACEMENT_REGION0_SRAM", self.P)),
                         (drwl.PLACEMENT_SRAM_W, 0))
        self.assertEqual((define("NPU_OFF_QCONFIG", INC["probe.h"]), define("NPU_OFF_REGIONCFG", INC["probe.h"])),
                         (0x1C, 0x3C))
        self.assertEqual(define("DRWL_PLACEMENT_WORD", INC["workload.h"]), drwl.PLACEMENT_WORD)
        self.assertIn("REC_REGIONCFG_MATCH = 1u << 6", INC["record.h"])
        self.assertEqual(record_v2.REGIONCFG_MATCH, 1 << 6)

    def test_hooks(self):
        h = SRC["hooks.c"]
        self.assertIn("unsigned int ethosu_config_select(uint64_t address, int index)", h)   # the driver's prototype
        self.assertIn("return placement_config_select(index, placement_effective());", h)
        # E2E-D: QBASE (index -1) is never remapped; only index 0, only with a valid copy; the copy is made on the QBASE
        # call before the PMU is armed (outside the measured window)
        remap = h[h.index("uint64_t ethosu_address_remap("):h.index("unsigned int ethosu_config_select(")]
        self.assertEqual(remap.count("return placement_weights();"), 1)
        self.assertIn("if (index == 0 && placement_weights() != 0U) {\n        return placement_weights();", remap)
        self.assertLess(remap.index("placement_weights_prepare("), remap.index("pmu_session_arm(&cnten)"))
        self.assertLess(remap.index("if (index == -1)"), remap.index("placement_weights_prepare("))
        self.assertIn("SCB_CleanInvalidateDCache();", h)
        self.assertIn("if (placement_get() == PLACEMENT_SRAM_W && j->num_base_addr > 0) {\n"
                      "            (void)placement_weights_prepare((uintptr_t)j->base_addr[0], (uint32_t)j->base_addr_size[0], weights_sync);", remap)
        # every load drops the previous copy, after the arena is placed and checked, before the model is placed
        r = SRC["runner.c"]
        load = r[r.index("static uint32_t place_and_load(void)"):r.index("static void load_end(void)")]
        self.assertIn("placement_weights_reset(arena_base, P->arena_len, limit);", load)
        self.assertLess(load.index("placement_mem_check("), load.index("placement_weights_reset("))
        self.assertLess(load.index("placement_weights_reset("), load.index("P->place_model("))
        irq = h[h.index("void ethosu_irq_handler("):]
        # the PMU snapshot stays the first read at the IRQ; the region read-back comes after it
        self.assertLess(irq.index("pmu_session_snapshot(&s)"), irq.index("npu_word(NPU_OFF_REGIONCFG)"))
        self.assertLess(irq.index("npu_word(NPU_OFF_QCONFIG)"), irq.index("probe.irq_count++"))

    def test_run_path_unchanged(self):
        # the measured RUN gets nothing new: no placement call, no memory check, no poison, no cache maintenance
        c = SRC["runner.c"]
        run = c[c.index("static void run(void)"):c.index("static void reset_runner(void)")]
        for s in ("placement_", "dcache_sync", "memset", "prepare_io", "mem_check"):
            self.assertNotIn(s, run, s)
        self.assertIn("prepare_io()", c[c.index("static uint32_t place_and_load(void)"):])


class Commands(unittest.TestCase):
    def test_ids(self):
        h = INC["runner.h"]
        for name, host in (("CMD_PING", runner_proto.CMD_PING), ("CMD_GET_STATE", runner_proto.CMD_GET_STATE),
                           ("CMD_SET_INSTRUMENTATION_MODE", runner_proto.CMD_SET_INSTRUMENTATION_MODE),
                           ("CMD_LOAD_MODEL_BEGIN", runner_proto.CMD_LOAD_MODEL_BEGIN),
                           ("CMD_LOAD_MODEL_CHUNK", runner_proto.CMD_LOAD_MODEL_CHUNK),
                           ("CMD_LOAD_MODEL_END", runner_proto.CMD_LOAD_MODEL_END),
                           ("CMD_LOAD_INPUT", runner_proto.CMD_LOAD_INPUT), ("CMD_RUN", runner_proto.CMD_RUN),
                           ("CMD_RUN_COMPLETE", runner_proto.CMD_RUN_COMPLETE),
                           ("CMD_RESET_RUNNER", runner_proto.CMD_RESET_RUNNER),
                           ("CMD_GET_CAPABILITIES", driver_link.CMD_GET_CAPABILITIES),
                           ("CMD_SET_RUN_OPTIONS", driver_link.CMD_SET_RUN_OPTIONS)):
            self.assertEqual(define(name, h), host, name)
        f = INC["frame.h"]
        self.assertEqual(define("FRAME_MAGIC", f), runner_proto.MAGIC)
        self.assertEqual(define("FRAME_MAX_PAYLOAD", f), runner_proto.MAX_PAYLOAD)
        self.assertEqual(define("FRAME_NACK_CMD", f), runner_proto.NACK)

    def test_wait_modes(self):
        p = INC["probe.h"]
        self.assertEqual((define("WAIT_WFE", p), define("WAIT_BUSY", p)), (driver_link.WAIT_WFE, driver_link.WAIT_BUSY))

    def test_trace_layout(self):
        t = INC["trace.h"]
        Q = qread_trace
        self.assertEqual(define("TRACE_OFF", t), Q.OFF)
        self.assertEqual((define("TRACE_MODE_QREAD_ONLY", t), define("TRACE_MODE_QREAD_PMU", t)),
                         (Q.MODE_QREAD_ONLY, Q.MODE_QREAD_PMU))
        self.assertEqual((define("TRACE_MODE_MASK", t), define("TRACE_INTERVAL_SHIFT", t), define("TRACE_STORE_SHIFT", t),
                          define("TRACE_FIELD_MASK", t)), (Q.MODE_MASK, Q.INTERVAL_SHIFT, Q.STORE_SHIFT, Q.FIELD_MASK))
        self.assertEqual(define("TRACE_BASE_SAMPLE_WORDS", t), Q.BASE_SAMPLE_WORDS)
        self.assertEqual(define("TRACE_BUFFER_WORDS", t), Q.BUFFER_WORDS)
        self.assertEqual(define("TRACE_GET_MAX_WORDS", t), Q.GET_TRACE_MAX_WORDS)
        self.assertEqual(define("TRACE_GET_MAX_WORDS", t), driver_link.TRACE_GET_MAX_WORDS)
        self.assertEqual(define("CMD_GET_TRACE", t), Q.CMD_GET_TRACE)
        self.assertEqual(define("CMD_GET_TRACE", t), driver_link.CMD_GET_TRACE)
        self.assertEqual(define("WAIT_TRACE", INC["probe.h"]), driver_link.WAIT_TRACE)
        self.assertEqual(Q.OFF, driver_link.TRACE_OFF)
        # the sample order: the firmware writes t, QREAD, STATUS, events, QREAD, t (trace.c sample())
        body = SRC["trace.c"][SRC["trace.c"].index("static void sample("):]
        order = [m for m in ("clock_now()", "NPU_OFF_QREAD", "NPU_OFF_STATUS", "ev[i]", "NPU_OFF_QREAD", "clock_now()")]
        pos, at = [], 0
        for m in order:
            at = body.index(m, at) + 1; pos.append(at)
        self.assertEqual(pos, sorted(pos))
        self.assertTrue(set(Q.RECORD_FIELDS) <= set(record_v2.FIELDS))

    def test_get_output(self):
        r = INC["runner.h"]
        self.assertEqual((define("CMD_GET_OUTPUT", r), define("OUTPUT_GET_MAX_BYTES", r)),
                         (driver_link.CMD_GET_OUTPUT, driver_link.OUTPUT_GET_MAX_BYTES))
        self.assertLessEqual(driver_link.OUTPUT_GET_MAX_BYTES, runner_proto.MAX_PAYLOAD)

    def test_checked_trace_layout(self):
        t, c = INC["trace.h"], SRC["trace.c"]
        Q = qread_trace
        self.assertEqual((define("TRACE_MODE_QREAD_CHECKED", t), define("TRACE_MODE_QREAD_PMU_CHECKED", t)),
                         (Q.MODE_QREAD_CHECKED, Q.MODE_QREAD_PMU_CHECKED))
        self.assertEqual((define("TRACE_CHECKED_MAGIC", t), define("TRACE_CHECK_SEED", t), define("TRACE_MAX_ATTEMPTS", t)),
                         (Q.CHECKED_MAGIC, Q.CHECK_SEED, Q.MAX_ATTEMPTS))
        regs = (REPO / "firmware" / "common" / "npu_pmu_regs.h").read_text()
        self.assertEqual(define("NPU_REG_PMEVCNTR_BASE", regs), Q.NPU_REG_PMEVCNTR_BASE)
        self.assertTrue(set(Q.CHECKED_RECORD_FIELDS) <= set(record_v2.FIELDS))
        # header and descriptor bit positions as qread_checked.parse reads them
        self.assertIn("(TRACE_CHECKED_MAGIC << 24) | (job << 23) | (final << 22) | (start << 21) | (s->slots << 8) "
                      "| s->attempts", c)
        self.assertIn("s->w[d] = (ok << 20) | (a << 16) | off;", c)
        # an attempt: ID first, then the register (read_slot)
        body = c[c.index("static uint32_t read_slot("):]
        self.assertLess(body.index("npu_word(NPU_OFF_ID)"), body.index("v = npu_word(off)"))
        # the job sample's slot order: QREAD, STATUS, counters, QREAD (sample_checked)
        body = c[c.index("static void sample_checked("):]
        order = ("NPU_OFF_QREAD", "NPU_OFF_STATUS", "NPU_REG_PMEVCNTR_BASE", "NPU_OFF_QREAD", "seal(")
        pos, at = [], 0
        for m in order:
            at = body.index(m, at) + 1; pos.append(at)
        self.assertEqual(pos, sorted(pos))
        # the inference semaphore is the only job wait (hooks.c)
        self.assertIn("trace_wait(&s->count, sem == ethosu_drv.semaphore ? 1U : 0U)", SRC["hooks.c"])

    def test_irq_snapshot_offsets_are_the_drivers(self):
        # literals from MLEK b2c0bb2 core driver src/ethosu85_interface.h (NPU_REG_ID/STATUS/QREAD/QSIZE; 0x24 is PROT)
        self.assertEqual((define("NPU_OFF_ID", INC["trace.h"]), define("NPU_OFF_STATUS", INC["trace.h"]),
                          define("NPU_OFF_QREAD", INC["trace.h"]), define("NPU_OFF_QSIZE", INC["trace.h"])),
                         (0x00, 0x04, 0x18, 0x20))


if __name__ == "__main__":
    unittest.main()
