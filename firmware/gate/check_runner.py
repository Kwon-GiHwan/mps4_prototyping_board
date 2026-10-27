#!/usr/bin/env python3
"""Gate over the linked runner ELF and its sources (runner/, common/). Each refusal names its rule.

Every PMU access goes through pmu_reg_write(offset, value) / pmu_reg_read(offset) with an IMMEDIATE offset
(movw r0, #0x1184 ...). Programming and reading event slots in a loop is the only thing that produces a call whose
offset operand is register-computed (adds r0, rN, rM). That, not an absolute address literal (which the accessor
design never emits), is the observable.

  RULE_INFERENCE_LINKED     apU85Conv_TEST MUST be linked (this image runs inference)
  RULE_PMEVTYPER_LOOP_STORE a bl <pmu_reg_write> with a register-computed offset exists
  RULE_PMEVCNTR_LOOP_LOAD   a bl <pmu_reg_read>  with a register-computed offset exists
  RULE_BUILD_ID             build id literal present
  RULE_MAIN_PRESENT         main linked
  RULE_MODE2                sources define INSTRUMENTATION_EVENTS and keep END_ONLY's count refusal
  RULE_SEAM_HOOK            __wrap_printf carries the CPM read seam and is linked
  RULE_EXT_ATTR             the vendor's USE_AXI_EXT path is compiled in
  RULE_TEST_U85_WRAP        __wrap_test_u85 is linked (the PMWL blob replaces test3)
  RULE_MODEL                PMWL path linked, knob apply seam present, vendor copy has the raised timeout and
                            routes POWER_CTRL through the runner's strong u85_power_ctrl_value
"""
import argparse, re, sys

RULES = ("RULE_INFERENCE_LINKED", "RULE_PMEVTYPER_LOOP_STORE", "RULE_PMEVCNTR_LOOP_LOAD", "RULE_BUILD_ID",
         "RULE_MAIN_PRESENT", "RULE_MODE2", "RULE_SEAM_HOOK", "RULE_EXT_ATTR", "RULE_TEST_U85_WRAP", "RULE_MODEL")
PMWL_MAGIC = 0x4C574D50
RAISED_TIMEOUT = "#define BUSY_SLEEP_TIMEOUT 200000000"
POWER_CTRL_HOOK = "write_reg(NPU_REG_POWER_CTRL, u85_power_ctrl_value(MAC_RAMP_VAR));"
EXT_LITERAL = b"Enabling AXI EXT port testing"
SEAM_FMT = '"Testing CPM signals\\n"'   # as it appears in C source
APPLY_FMT = "Updating POWER_CTRL register with MAC_RAMP_VAR=%d"
_R0_IMM = re.compile(r"\b(?:movs?|movw|mov\.w)\s+r0,\s*#|\bldr\s+r0,\s*\[pc")   # constant offset
_R0_WRITE = re.compile(r"\b(?:movs?|movw|mov\.w|adds?|add\.w|subs?|sub\.w|ldr(?:\.w)?|orr|and|lsl)s?\s+r0,")


class GateFail(Exception):
    def __init__(self, rule, msg): super().__init__(f"{rule}: {msg}"); self.rule = rule


def _lits(t): return {int(m.group(1), 16) for m in re.finditer(r"\b(?:0x)?([0-9a-fA-F]{8})\b", t)}


def _register_offset_call(objdump_text, callee):
    """True if some `bl <callee>` takes an offset that is NOT a constant: the last instruction writing r0 between
    the previous bl and this bl is a register move / add (loop-carried), not an immediate or a pc-relative literal
    load. Every fixed-register call site passes an immediate (movw r0, #0x1184 ...)."""
    lines = objdump_text.split("\n")
    for i, l in enumerate(lines):
        if not re.search(r"\bbl\s+[0-9a-f]+\s+<" + callee + r">", l):
            continue
        j = i - 1
        while j >= 0 and not re.search(r"\bbl\s", lines[j]):
            if _R0_WRITE.search(lines[j]):
                if not _R0_IMM.search(lines[j]):
                    return True
                break
            j -= 1
    return False


def check(objdump_text, nm_text, src_text, build_id, elf_bytes, vendor_text):
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
    if "#define INSTRUMENTATION_EVENTS    2U" not in src_text or \
       "count != 0U && mode != INSTRUMENTATION_EVENTS" not in src_text:
        raise GateFail(RULES[5], "sources lack mode 2 or dropped END_ONLY's count refusal")
    wrap = src_text[src_text.find("int __wrap_printf(const char *fmt, ...)"):]
    if SEAM_FMT not in wrap or not re.search(r"\b[Tt] __wrap_printf\b", nm_text):
        raise GateFail(RULES[6], "read seam absent: __wrap_printf lacks the CPM format or is not linked")
    if EXT_LITERAL not in elf_bytes:
        raise GateFail(RULES[7], "USE_AXI_EXT path absent in the ELF")
    if not re.search(r"\b[Tt] __wrap_test_u85$", nm_text, re.M):
        raise GateFail(RULES[8], "__wrap_test_u85 not linked: the blob would never replace test3")
    if PMWL_MAGIC not in _lits(objdump_text):
        raise GateFail(RULES[9], "PMWL blob path not linked")
    if APPLY_FMT not in wrap:
        raise GateFail(RULES[9], "__wrap_printf lacks the knob apply seam")
    if RAISED_TIMEOUT not in vendor_text:
        raise GateFail(RULES[9], "generated vendor u85.c lacks the raised BUSY_SLEEP_TIMEOUT")
    if POWER_CTRL_HOOK not in vendor_text:
        raise GateFail(RULES[9], "generated vendor u85.c does not route POWER_CTRL through the runner hook")
    if not re.search(r"^[0-9a-f]+(?: [0-9a-f]+)? T u85_power_ctrl_value$", nm_text, re.M):
        raise GateFail(RULES[9], "u85_power_ctrl_value is not the runner's strong definition: the POWER_CTRL knob would be ignored")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("objdump", "nm", "src", "elf", "vendor"): ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--build-id", required=True, type=lambda s: int(s, 0))
    a = ap.parse_args(argv)
    try:
        check(open(a.objdump).read(), open(a.nm).read(), open(a.src).read(), a.build_id,
              open(a.elf, "rb").read(), open(a.vendor).read())
    except GateFail as e:
        print(f"GATE FAIL {e}"); return 1
    print("GATE OK: inference linked, slot program+read loops present, mode 2 present, END_ONLY refusal kept, "
          "CPM read seam present, EXT path ON, test_u85 wrap ON, PMWL model path ON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
