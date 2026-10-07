"""Isolate whether RESET_ON/RESET_OFF breaks the WRITE_AXI/READ_AXI round trip."""

import os

from mcc_harness import STAGING, Harness

PW = os.environ["MPS4_SUDO_PW"]
PATTERN = b"DIAG0123456789AB"  # 16 bytes


def show(label, sent, got):
    print("  %-22s sent=%r" % (label, sent), flush=True)
    print("  %-22s got =%r" % ("", got), flush=True)
    print("  %-22s %s" % ("", "IDENTICAL" if sent == got else "DIFFERENT"), flush=True)


h = Harness(PW)

print("=== A: no reset (mirrors the successful manual probe) ===", flush=True)
h.write_memory(STAGING, PATTERN, name="DIAG_A.BIN")
got_a = h.read_memory(STAGING, len(PATTERN), name="DIAG_AR.BIN")
show("A", PATTERN, got_a)

print("\n=== B: RESET_ON before write, RESET_OFF after read ===", flush=True)
print("  RESET_ON  -> %s" % h.reset_on().replace("\r", " ").strip()[:70], flush=True)
h.write_memory(STAGING, PATTERN, name="DIAG_B.BIN")
got_b = h.read_memory(STAGING, len(PATTERN), name="DIAG_BR.BIN")
show("B", PATTERN, got_b)
print("  RESET_OFF -> %s" % h.reset_off().replace("\r", " ").strip()[:70], flush=True)

print("\n=== C: write with no reset, read after RESET_ON ===", flush=True)
h.write_memory(STAGING, PATTERN, name="DIAG_C.BIN")
print("  RESET_ON  -> %s" % h.reset_on().replace("\r", " ").strip()[:70], flush=True)
got_c = h.read_memory(STAGING, len(PATTERN), name="DIAG_CR.BIN")
show("C", PATTERN, got_c)
print("  RESET_OFF -> %s" % h.reset_off().replace("\r", " ").strip()[:70], flush=True)

h.close()
