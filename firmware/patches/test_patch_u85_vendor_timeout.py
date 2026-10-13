import difflib, hashlib, pathlib, sys, unittest
HERE = pathlib.Path(__file__).parent; sys.path.insert(0, str(HERE))
import patch_u85_vendor_timeout as V
RAW = (HERE.parent / "Drivers" / "u85_driver" / "u85.c").read_bytes()
BASE = RAW.decode()   # bytes -> str without newline translation: the file is CRLF


class T(unittest.TestCase):
    def test_pinned(self): self.assertEqual(hashlib.sha256(RAW).hexdigest(), V.VENDOR_SHA256)

    def test_crlf_preserved(self):
        g = V.generate(BASE)
        self.assertIn("\r\n", BASE)
        self.assertEqual(g.count("\r\n"), BASE.count("\r\n") + 1)   # change 3 adds one line
        self.assertEqual(g.count("\n"), g.count("\r\n"))             # no bare LF introduced

    def test_exactly_one_line_changes(self):
        g = V.generate(BASE)
        d = [l for l in difflib.unified_diff(BASE.split("\r\n"), g.split("\r\n"), lineterm="", n=0)
             if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        self.assertEqual(d, ["-#define BUSY_SLEEP_TIMEOUT 10000",
                             "+#define BUSY_SLEEP_TIMEOUT 200000000 /* Tier C step 1: was 10000 */",
                             "+__attribute__((weak)) uint32_t u85_power_ctrl_value(uint32_t v) { return v; } /* runner gap: weak default */",
                             "-\t  write_reg(NPU_REG_POWER_CTRL, MAC_RAMP_VAR);",
                             "+\t  write_reg(NPU_REG_POWER_CTRL, u85_power_ctrl_value(MAC_RAMP_VAR)); /* runner gap: hook */",
                             "-    int ret_code = 0;",
                             "+    int ret_code = 0; irq_never_triggered = false; /* Tier C step 2: per-run, not per-boot */"])
        # the weak default is defined before its only caller
        self.assertLess(g.index("uint32_t u85_power_ctrl_value(uint32_t v)"), g.index("u85_power_ctrl_value(MAC_RAMP_VAR)"))
        # the reset lands in test_u85 (the only `int ret_code = 0;`), before test_commands is called
        self.assertLess(g.index("irq_never_triggered = false; /* Tier C"), g.index("ret_code = test_commands("))

    def test_refuses_missing_anchor(self):
        with self.assertRaises(SystemExit): V.generate(BASE.replace("BUSY_SLEEP_TIMEOUT 10000", "BUSY_SLEEP_TIMEOUT 10001", 1))
        with self.assertRaises(SystemExit): V.generate(BASE.replace("NPU_REG_POWER_CTRL, MAC_RAMP_VAR)", "NPU_REG_POWER_CTRL, 2)", 1))
        with self.assertRaises(SystemExit): V.generate(BASE.replace("static int test_commands(", "static int test_cmds(", 1))


if __name__ == "__main__":
    unittest.main()
