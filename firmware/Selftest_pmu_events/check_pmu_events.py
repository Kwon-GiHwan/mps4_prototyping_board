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
         "RULE_BUILD_ID", "RULE_MAIN_PRESENT", "RULE_GEN_MODE2", "RULE_SEAM_HOOK", "RULE_EXT_ATTR", "RULE_EXT_DRAM", "RULE_MODEL")
PMWL_MAGIC = 0x4C574D50
RAISED_TIMEOUT = "#define BUSY_SLEEP_TIMEOUT 200000000"
DRAM_SIZES = {"test3_weights": "TEST3_WEIGHTS_SIZE", "test3_in_data_0": "TEST3_IN_SIZE",
              "test3_scratch_buffer": "TEST3_SCRATCH_SIZE"}
EXT_LITERAL = b"Enabling AXI EXT port testing"
SEAM_FMT = '"Testing CPM signals\\n"'   # as it appears in C source
_R0_IMM = re.compile(r"\b(?:movs?|movw|mov\.w)\s+r0,\s*#|\bldr\s+r0,\s*\[pc")   # constant offset
_R0_WRITE = re.compile(r"\b(?:movs?|movw|mov\.w|adds?|add\.w|subs?|sub\.w|ldr(?:\.w)?|orr|and|lsl)s?\s+r0,")


class GateFail(Exception):
    def __init__(self, rule, msg): super().__init__(f"{rule}: {msg}"); self.rule = rule


def _lits(t): return {int(m.group(1), 16) for m in re.finditer(r"\b(?:0x)?([0-9a-fA-F]{8})\b", t)}


def _register_offset_call(objdump_text, callee):
    """True if some `bl <callee>` takes an offset that is NOT a constant: the last
    instruction writing r0 between the previous bl and this bl is a register move /
    add (loop-carried), not an immediate or a pc-relative literal load. Every
    base-runner call site passes an immediate (movw r0, #0x1184 ...)."""
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


def _nm_size(nm_text, sym):
    m = re.search(r"^[0-9a-f]+ ([0-9a-f]+) [a-zA-Z] " + sym + r"$", nm_text, re.M)
    return int(m.group(1), 16) if m else None


def check(objdump_text, nm_text, gen_text, build_id, elf_bytes=None, expect_ext=False, expect_dram=False,
          expect_model=False, gen_vendor_text=None):
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
    wrap = gen_text[gen_text.find("int __wrap_printf(const char *fmt, ...)"):]
    if SEAM_FMT not in wrap or not re.search(r"\b[Tt] __wrap_printf\b", nm_text):
        raise GateFail(RULES[6], "read seam absent: __wrap_printf lacks the CPM format or is not linked")
    if elf_bytes is not None and (EXT_LITERAL in elf_bytes) != expect_ext:
        raise GateFail(RULES[7], f"USE_AXI_EXT path {'absent' if expect_ext else 'present'} in ELF, expected the opposite")
    wrapped = bool(re.search(r"\b[Tt] __wrap_test_u85$", nm_text, re.M))
    if wrapped != expect_dram:
        raise GateFail(RULES[8], f"__wrap_test_u85 {'linked' if wrapped else 'absent'}, expected the opposite")
    if expect_dram:
        for sym, macro in DRAM_SIZES.items():
            m = re.search(r"#define " + macro + r" +(0x[0-9A-Fa-f]+)U", gen_text)
            if not m or _nm_size(nm_text, sym) != int(m.group(1), 16):
                raise GateFail(RULES[8], f"{macro} != linked size of {sym} ({_nm_size(nm_text, sym)})")
    has_magic = PMWL_MAGIC in _lits(objdump_text)
    if has_magic != expect_model:
        raise GateFail(RULES[9], f"PMWL blob path {'linked' if has_magic else 'absent'}, expected the opposite")
    if expect_model and (gen_vendor_text is None or RAISED_TIMEOUT not in gen_vendor_text):
        raise GateFail(RULES[9], "generated vendor u85.c lacks the raised BUSY_SLEEP_TIMEOUT")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("objdump", "nm", "gen"): ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--build-id", required=True, type=lambda s: int(s, 0))
    ap.add_argument("--elf"); ap.add_argument("--expect-ext", action="store_true")
    ap.add_argument("--expect-dram", action="store_true")
    ap.add_argument("--expect-model", action="store_true"); ap.add_argument("--gen-vendor")
    a = ap.parse_args(argv)
    try:
        check(open(a.objdump).read(), open(a.nm).read(), open(a.gen).read(), a.build_id,
              open(a.elf, "rb").read() if a.elf else None, a.expect_ext, a.expect_dram,
              a.expect_model, open(a.gen_vendor).read() if a.gen_vendor else None)
    except GateFail as e:
        print(f"GATE FAIL {e}"); return 1
    print("GATE OK: inference linked, slot program+read loops present, mode 2 present, END_ONLY refusal kept, CPM read seam present, EXT attr " + ("ON" if a.expect_ext else "OFF") + " as expected, DRAM wrap " + ("ON" if a.expect_dram else "OFF") + ", model " + ("ON" if a.expect_model else "OFF")); return 0


if __name__ == "__main__":
    sys.exit(main())
