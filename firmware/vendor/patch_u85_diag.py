#!/usr/bin/env python3
"""Diagnostic-only vendor copy (evidence/w2l_stall step 2): the measurement copy plus two changes that make a
stalled RUN return, so STATUS and QREAD reach the host through the existing CPM-seam fields.

D1  sleep(): the wait for the NPU IRQ ends after DIAG_WAIT_CYCLES of DWT CYCCNT instead of 200,000,000 loop
    iterations of unmeasured length.
D2  u85_irq_handler(): an NPU IRQ without STATUS bit 1 is never cleared by the vendor and re-enters forever;
    after 16 such entries the handler disables NPU0_IRQn so the wait can time out.

Never used for a measurement image. Built only by overriding the measurement Makefile's variables:
  make -f Makefile.npu_runner BUILD=build_npu_runner_diag VENDOR_PATCH=vendor/patch_u85_diag.py all
"""
import argparse, hashlib, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import patch_u85_vendor_timeout as M  # noqa: E402

DIAG_WAIT_CYCLES = 2000000000

OLD_SLEEP = re.compile(r"(static inline void sleep\(\)\r?\n\{\r?\n#if defined\(BUSY_SLEEP\)\r?\n)"
                       r"  static volatile int i,j=0;\r?\n  for \(i=0 ; i < BUSY_SLEEP_TIMEOUT; i\+\+\) \{\r?\n"
                       r"    if \(irq_triggered\) \{\r?\n      return;\r?\n    \}\r?\n    j=j\*i;\r?\n  \}\r?\n")
NEW_SLEEP = (r"\1  const uint32_t t0 = *(volatile uint32_t *)0xE0001004U; /* diag D1: DWT CYCCNT */\r\n"
             r"  while (!irq_triggered) {\r\n"
             rf"    if (*(volatile uint32_t *)0xE0001004U - t0 > {DIAG_WAIT_CYCLES}U) {{ return; }}\r\n"
             r"  }\r\n")
OLD_IRQ = re.compile(r"(    irq_history_mask = status_register >> 16;\r?\n)")
NEW_IRQ = (r"\1    if ((status_register & 0x02) == 0) { /* diag D2: an IRQ the vendor never clears */\r\n"
           r"        static uint32_t diag_unacked;\r\n"
           r"        if (++diag_unacked >= 16U) { NVIC_DisableIRQ(NPU0_IRQn); }\r\n"
           r"    }\r\n")


def generate(text):
    out = M.generate(text)
    for old, new, what in ((OLD_SLEEP, NEW_SLEEP, "sleep()"), (OLD_IRQ, NEW_IRQ, "irq handler")):
        out, n = old.subn(new, out)
        if n != 1:
            raise SystemExit(f"diag {what} anchor matched {n} times, need 1")
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = pathlib.Path(a.base).read_bytes()
    if hashlib.sha256(data).hexdigest() != M.VENDOR_SHA256:
        raise SystemExit("vendor u85.c sha256 differs from the pinned original")
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(generate(data.decode()).encode())
    print(f"generated {out} (DIAGNOSTIC, not for measurement)")


if __name__ == "__main__":
    main()
