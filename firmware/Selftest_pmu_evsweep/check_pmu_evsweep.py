#!/usr/bin/env python3
"""Gate over the linked sweep ELF: prove it is a sweep, not a runner.

Reads objdump -d and nm text (already produced by the Makefile) and refuses
unless every rule holds. Each refusal names its rule.

  RULE_PMEVTYPER0_TARGET  the literal PMEVTYPER0 address (0x50005380) must
                          appear in the disassembly -- the sweep stores to it
  RULE_NO_INFERENCE       apU85Conv_TEST must NOT be a linked symbol
  RULE_BUILD_ID           the build id literal must appear in the disassembly
  RULE_MAIN_PRESENT       main must be linked (an empty image proves nothing)
"""
import argparse, re, sys

PMEVTYPER0_ABS = 0x50004000 + 0x1380
RULES = ("RULE_PMEVTYPER0_TARGET", "RULE_NO_INFERENCE", "RULE_BUILD_ID", "RULE_MAIN_PRESENT")


class GateFail(Exception):
    def __init__(self, rule, msg):
        super().__init__(f"{rule}: {msg}"); self.rule = rule


def _lits(objdump_text):
    """All 32-bit literals GCC emitted as .word / movw+movt pairs are visible as
    hex words in objdump -d; collect every 0x-prefixed or bare 8-hex token."""
    found = set()
    for m in re.finditer(r"\b(?:0x)?([0-9a-fA-F]{8})\b", objdump_text):
        found.add(int(m.group(1), 16))
    return found


def check(objdump_text, nm_text, build_id):
    lits = _lits(objdump_text)
    if PMEVTYPER0_ABS not in lits:
        raise GateFail(RULES[0], f"0x{PMEVTYPER0_ABS:08x} not found as a literal")
    if re.search(r"\bapU85Conv_TEST\b", nm_text):
        raise GateFail(RULES[1], "apU85Conv_TEST is linked: this image can run inference")
    if build_id not in lits:
        raise GateFail(RULES[2], f"build id 0x{build_id:08x} not found as a literal")
    if not re.search(r"\b[Tt] main\b", nm_text):
        raise GateFail(RULES[3], "no main symbol")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", required=True); ap.add_argument("--nm", required=True)
    ap.add_argument("--build-id", required=True, type=lambda s: int(s, 0))
    a = ap.parse_args(argv)
    try:
        check(open(a.objdump).read(), open(a.nm).read(), a.build_id)
    except GateFail as e:
        print(f"GATE FAIL {e}"); return 1
    print("GATE OK: sweep image, no inference linked, build id present"); return 0


if __name__ == "__main__":
    sys.exit(main())
