"""The driver runner firmware and the host declare record v2, the capabilities, the DRWL layout and the request ids
independently. This test reads the C sources (the X-macro lists and defines) and requires them to equal the host
modules; neither side imports the other. A change on one side only must turn this RED."""
import re, sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "lib"))
import driver_link
import drwl
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
                                                               "n_in", "n_out")}
        self.assertTrue(want <= set(offs), (want, offs))


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

    def test_irq_snapshot_offsets_are_the_drivers(self):
        # literals from MLEK b2c0bb2 core driver src/ethosu85_interface.h (NPU_REG_STATUS/QREAD/QSIZE; 0x24 is PROT)
        h = SRC["hooks.c"]
        self.assertEqual((define("NPU_OFF_QREAD", h), define("NPU_OFF_QSIZE", h)), (0x18, 0x20))


if __name__ == "__main__":
    unittest.main()
