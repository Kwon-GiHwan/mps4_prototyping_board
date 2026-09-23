#!/usr/bin/env python3
"""Gate over the linked Tier B ELF and its generated source. Each refusal names its rule.

Every PMU access in the base runner goes through pmu_reg_write(offset, value) /
pmu_reg_read(offset) with an IMMEDIATE offset (movw r0, #0x1184 ...). Programming
and reading event slots in a loop is the only thing that produces a call whose
offset operand is register-computed (adds r0, rN, rM). That, not an absolute
address literal (which the accessor design never emits), is the observable.

  RULE_INFERENCE_LINKED    apU85Conv_TEST MUST be linked (this image runs inference)
  RULE_PMEVTYPER_LOOP_STORE a bl <pmu_reg_write> with a register-computed offset exists
  RULE_PMEVCNTR_LOOP_LOAD   a bl <pmu_reg_read>  with a register-computed offset exists
  RULE_BUILD_ID             build id literal present
  RULE_MAIN_PRESENT         main linked
  RULE_GEN_MODE2            generated source defines INSTRUMENTATION_EVENTS and keeps END_ONLY's refusal
"""
import argparse, re, sys

RULES = ("RULE_INFERENCE_LINKED", "RULE_PMEVTYPER_LOOP_STORE", "RULE_PMEVCNTR_LOOP_LOAD",
         "RULE_BUILD_ID", "RULE_MAIN_PRESENT", "RULE_GEN_MODE2")
_REG_ADD = re.compile(r"\badds?(?:\.w)?\s+r0,\s*r\d+,\s*r\d+")


class GateFail(Exception):
    def __init__(self, rule, msg): super().__init__(f"{rule}: {msg}"); self.rule = rule


def _lits(t): return {int(m.group(1), 16) for m in re.finditer(r"\b(?:0x)?([0-9a-fA-F]{8})\b", t)}


def _register_offset_call(objdump_text, callee):
    """True if some `bl <callee>` has an `r0 = rN + rM` add between it and the
    previous bl -- i.e. the offset operand of THIS call is register-computed."""
    lines = objdump_text.split("\n")
    for i, l in enumerate(lines):
        if not re.search(r"\bbl\s+[0-9a-f]+\s+<" + callee + r">", l):
            continue
        j = i - 1
        while j >= 0 and not re.search(r"\bbl\s", lines[j]):
            if _REG_ADD.search(lines[j]):
                return True
            j -= 1
    return False


def check(objdump_text, nm_text, gen_text, build_id):
    if not re.search(r"\b[Tt] apU85Conv_TEST\b", nm_text):
        raise GateFail(RULES[0], "apU85Conv_TEST not linked: this image cannot run the workload")
    if not _register_offset_call(objdump_text, "pmu_reg_write"):
        raise GateFail(RULES[1], "no pmu_reg_write call with a register-computed offset: slots are not programmed")
    if not _register_offset_call(objdump_text, "pmu_reg_read"):
        raise GateFail(RULES[2], "no pmu_reg_read call with a register-computed offset: slots are not read back")
    if build_id not in _lits(objdump_text):
        raise GateFail(RULES[3], f"build id 0x{build_id:08x} absent")
    if not re.search(r"\b[Tt] main\b", nm_text):
        raise GateFail(RULES[4], "no main")
    if "#define INSTRUMENTATION_EVENTS    2U" not in gen_text or \
       "count != 0U && mode != INSTRUMENTATION_EVENTS" not in gen_text:
        raise GateFail(RULES[5], "generated source lacks mode 2 or dropped END_ONLY's count refusal")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("objdump", "nm", "gen"): ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--build-id", required=True, type=lambda s: int(s, 0))
    a = ap.parse_args(argv)
    try:
        check(open(a.objdump).read(), open(a.nm).read(), open(a.gen).read(), a.build_id)
    except GateFail as e:
        print(f"GATE FAIL {e}"); return 1
    print("GATE OK: inference linked, slot program+read loops present, mode 2 present, END_ONLY refusal kept"); return 0


if __name__ == "__main__":
    sys.exit(main())
