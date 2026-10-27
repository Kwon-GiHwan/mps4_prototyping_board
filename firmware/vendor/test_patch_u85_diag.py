import difflib, pathlib, sys, unittest
HERE = pathlib.Path(__file__).parent; sys.path.insert(0, str(HERE))
import patch_u85_diag as D
import patch_u85_vendor_timeout as V
BASE = (HERE.parent / "Drivers" / "u85_driver" / "u85.c").read_bytes().decode()


def changed(a, b):
    return [l for l in difflib.unified_diff(a.split("\r\n"), b.split("\r\n"), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]


class T(unittest.TestCase):
    def test_only_the_two_diag_changes_on_top_of_the_measurement_copy(self):
        d = changed(V.generate(BASE), D.generate(BASE))
        self.assertEqual(d, [
            "-  static volatile int i,j=0;",
            "-  for (i=0 ; i < BUSY_SLEEP_TIMEOUT; i++) {",
            "-    if (irq_triggered) {",
            "-      return;",
            "-    }",
            "-    j=j*i;",
            "+  const uint32_t t0 = *(volatile uint32_t *)0xE0001004U; /* diag D1: DWT CYCCNT */",
            "+  while (!irq_triggered) {",
            "+    if (*(volatile uint32_t *)0xE0001004U - t0 > 2000000000U) { return; }",
            "+    if ((status_register & 0x02) == 0) { /* diag D2: an IRQ the vendor never clears */",
            "+        static uint32_t diag_unacked;",
            "+        if (++diag_unacked >= 16U) { NVIC_DisableIRQ(NPU0_IRQn); }",
            "+    }"])

    def test_no_bare_lf(self):
        g = D.generate(BASE)
        self.assertEqual(g.count("\n"), g.count("\r\n"))

    def test_the_bounded_wait_is_inside_sleep_and_the_guard_inside_the_handler(self):
        g = D.generate(BASE)
        s = g[g.index("static inline void sleep()"):g.index("static inline uint32_t read_reg(")]
        self.assertIn("0xE0001004U - t0 > 2000000000U", s)
        h = g[g.index("void u85_irq_handler()"):g.index("static inline void wait_for_irq(void)")]
        self.assertLess(h.index("irq_history_mask = status_register >> 16;"), h.index("NVIC_DisableIRQ(NPU0_IRQn)"))
        self.assertLess(h.index("NVIC_DisableIRQ(NPU0_IRQn)"), h.index("if ((status_register & 0x02)){"))

    def test_refuses_missing_anchor(self):
        with self.assertRaises(SystemExit): D.generate(BASE.replace("    j=j*i;", "    j=j+i;", 1))
        with self.assertRaises(SystemExit): D.generate(BASE.replace("irq_history_mask = status_register >> 16;",
                                                                    "irq_history_mask = status_register >> 15;", 1))


if __name__ == "__main__":
    unittest.main()
