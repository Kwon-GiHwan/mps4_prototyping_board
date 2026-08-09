"""Case-identity gate for the PMU_DIAG images.

Counts pmu_reg_write() calls per PMU register in the PREPROCESSED diag
translation unit -- i.e. after #if resolution, so what is counted is what the
compiler actually sees for THIS case. The load-bearing claim is case A:
"no PMCCNTR_CFG write of any kind" must hold as a source-level fact, not as a
belief about which branch runs.

Register offsets are read from the GENERATED Selftest_pmu/npu_pmu_regs.h, not
retyped here -- the same no-second-source rule as the generator itself.

Expected counts are per TRANSLATION UNIT. The production handle_run() is
still present (dead but compiled) and contributes exactly one PMCNTENSET
write; it never writes PMCCNTR_CFG or PMOVSSET. The table below states the
expected totals explicitly so any base-file drift fails loudly instead of
being absorbed.
"""

import argparse
import difflib
import re
import subprocess
import sys

# NPU_OFF_CMD, pinned the same way the golden-window bounds are. Hardcoding is
# safe here precisely because it is fail-closed: if the source offset ever
# moved, the write counts below would read 0 and the gate fails rather than
# silently passing.
NPU_CMD_OFFSET = 0x08

REGS = ("NPU_REG_PMCCNTR_CFG", "NPU_REG_PMCNTENSET", "NPU_REG_PMOVSSET")

# Golden-window contract pins, the same cross-check status as the 0x11
# assertion: the C code carries NO literal (it reads the overlay symbols);
# this gate re-checks the linked values against the known contract.
GOLDEN_WINDOW_BASE = 0x90020CC0
GOLDEN_WINDOW_LEN = 0x100

# (case, nc) -> expected counts per register, in REGS order.
# handle_run (dead) always contributes 1 PMCNTENSET write; the diag handler
# contributes the rest.
EXPECTED = {
    ("A", "none"):     (0, 2, 0),
    ("B", "none"):     (1, 2, 0),
    ("B", "skipcfg"):  (0, 2, 0),
    ("B", "noevent"):  (1, 2, 0),
    ("B", "skiparm"):  (1, 1, 0),
    ("B", "forceovf"): (1, 2, 1),
    ("C", "none"):     (1, 2, 0),
}


def read_offsets(header_path):
    text = open(header_path).read()
    offsets = {}
    for name in REGS:
        hits = re.findall(r"^#define\s+%s\s+(0x[0-9A-Fa-f]+)U\s*$" % name, text, re.M)
        if len(hits) != 1:
            raise SystemExit("FAIL %s: expected 1 definition in %s, found %d"
                             % (name, header_path, len(hits)))
        offsets[name] = int(hits[0], 16)
    return offsets


def check_map(map_path):
    """Fail-closed check that the overlay symbols linked at the contract
    values. GNU ld map lines: '0x0000000090020cc0  __pmu_diag_..._base__ = ...'"""
    text = open(map_path).read()
    ok = True
    for name, want in (("__pmu_diag_golden_window_base__", GOLDEN_WINDOW_BASE),
                       ("__pmu_diag_golden_window_len__", GOLDEN_WINDOW_LEN)):
        hits = re.findall(r"0x([0-9a-fA-F]+)\s+%s\b" % name, text)
        vals = sorted({int(h, 16) for h in hits})
        if vals != [want]:
            print("  FAIL %-34s map values %s, expected 0x%X"
                  % (name, [hex(v) for v in vals] or "none", want))
            ok = False
        else:
            print("  PASS %-34s 0x%X" % (name, want))
    if not ok:
        print("FAIL golden window symbols do not match the contract")
        sys.exit(1)
    print("PASS golden window map contract")


# v7 power-seam contract. NPU_OFF_CMD writes are counted per VALUE, because
# the whole experiment is which images issue a hold and which issue a
# release. Values as the preprocessor renders them.
#   S1  pre-hold only; the driver's own release stands, runner only reads it
#   S2  pre-hold + post-return re-hold, so the runner must restore the release
#   S3  pre-hold only, but its private driver skipped the release
# All three end with the board in the same terminal state.
SEAM_CMD_WRITES = {
    "S1": {"0U": 1, "0x0000000CU": 0},
    "S2": {"0U": 2, "0x0000000CU": 1},
    "S3": {"0U": 1, "0x0000000CU": 1},
}
# Anything here appearing between the inference return and the S2 re-hold
# would sample the board before the seam and change the race being measured.
SEAM_FORBIDDEN_BEFORE_REHOLD = (
    "npu_read(", "npu_write(", "pmu_reg_read(", "pmu_reg_write(",
    "read_timestamp(",
)


def check_seam_sequence(text, seam, cmd_offset):
    """Prove the seam's power-write shape and, for S2, that NOTHING is
    sampled between the inference return and the re-hold.

    This source-level scan is the AUTHORITATIVE ordering proof: every NPU and
    PMU access in this translation unit goes through the four accessors named
    above, so their absence from the region is absence of access. The
    disassembly check that follows is corroboration only -- at -O1 the
    accessors are inlined and carry no symbol to grep for."""
    ok = True
    for value, want in sorted(SEAM_CMD_WRITES[seam].items()):
        # The offset is spelled exactly as the diag source spells it; a
        # changed spelling reads as 0 occurrences and fails the count.
        pat = r"npu_write\s*\(\s*0x%02XU\s*,\s*%s\s*\)" % (cmd_offset,
                                                           re.escape(value))
        got = len(re.findall(pat, text))
        status = "PASS" if got == want else "FAIL"
        if got != want:
            ok = False
        print("  %s seam %s: npu_write(CMD, %-12s) = %d (expected %d)"
              % (status, seam, value, got, want))

    calls = [m.end() for m in re.finditer(r"=\s*run_fixed_inference\s*\(\s*\)", text)]
    if not calls:
        print("  FAIL no run_fixed_inference() call site found")
        sys.exit(1)
    # handle_run_pmu_diag is the last handler in the file, so its call site is
    # the last one; handle_run's (dead) call comes earlier.
    after_return = text[calls[-1]:]

    if seam == "S2":
        m = re.search(r"pmu_diag_rehold_power\s*\(\s*\)", after_return)
        if not m:
            print("  FAIL S2 has no pmu_diag_rehold_power() after the return")
            sys.exit(1)
        region = after_return[:m.start()]
        hits = [tok for tok in SEAM_FORBIDDEN_BEFORE_REHOLD if tok in region]
        if hits:
            print("  FAIL S2 samples %s before the re-hold" % ", ".join(hits))
            ok = False
        else:
            print("  PASS S2 re-hold is the first access after the return "
                  "(no NPU/PMU/timestamp access in between)")
    else:
        if "pmu_diag_rehold_power" in text:
            print("  FAIL %s must not contain a re-hold" % seam)
            ok = False
        else:
            print("  PASS %s carries no re-hold" % seam)

    if not ok:
        print("FAIL seam %s source contract violated" % seam)
        sys.exit(1)
    print("PASS seam source contract: %s" % seam)


def check_seam_artifacts(map_path, elf_path, objdump, seam):
    """Which u85 driver actually linked, and -- for S2 -- that the re-hold is
    the first call after the inference returns."""
    mapping = {"S1": False, "S2": False, "S3": True}
    want_private = mapping[seam]
    text = open(map_path).read()
    have_private = "u85_diag.o" in text
    have_reference = re.search(r"u85_driver/u85\.o", text) is not None
    ok = True
    if have_private != want_private or have_reference == want_private:
        print("  FAIL %s linked private=%s reference=%s (expected private=%s)"
              % (seam, have_private, have_reference, want_private))
        ok = False
    else:
        print("  PASS %s links the %s u85 driver"
              % (seam, "diag-private" if want_private else "reference vendor"))

    out = subprocess.run([objdump, "-d", elf_path], capture_output=True,
                         text=True, check=True).stdout
    if seam == "S2":
        # handle_run_pmu_diag is static and -O1 folds it into dispatch(), so
        # the check locates whichever function actually contains the call
        # rather than assuming a symbol survived.
        sites = 0
        for body in re.finditer(
                r"^[0-9a-f]+ <([^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)",
                out, re.S | re.M):
            bls = re.findall(r"\sbl\s+[0-9a-f]+ <([^>]+)>", body.group(2))
            if "run_fixed_inference" not in bls:
                continue
            sites += 1
            idx = bls.index("run_fixed_inference")
            nxt = bls[idx + 1] if idx + 1 < len(bls) else "<none>"
            if nxt != "pmu_diag_rehold_power":
                print("  FAIL in <%s> the first call after "
                      "run_fixed_inference is %r, expected "
                      "pmu_diag_rehold_power" % (body.group(1), nxt))
                ok = False
            else:
                print("  PASS S2 disassembly <%s>: run_fixed_inference -> "
                      "pmu_diag_rehold_power with no call in between "
                      "(corroboration; the source scan is authoritative)"
                      % body.group(1))
        if sites == 0:
            print("  FAIL no bl to run_fixed_inference anywhere in the ELF")
            sys.exit(1)
    else:
        if re.search(r"<pmu_diag_rehold_power>:", out):
            print("  FAIL %s ELF contains pmu_diag_rehold_power" % seam)
            ok = False
        else:
            print("  PASS %s ELF carries no re-hold symbol" % seam)

    if not ok:
        print("FAIL seam %s artifact contract violated" % seam)
        sys.exit(1)
    print("PASS seam artifact contract: %s" % seam)


def check_driver_seam(driver_path, reference_path):
    """The diag driver may differ from the frozen selftest driver only by
    TEST_CPM=0, which defers CMD=0xC until after the runner's post snapshot."""
    source = open(driver_path, newline=None).read()
    reference = open(reference_path, newline=None).read()
    marker = "#define TEST_CPM 1"
    if reference.count(marker) != 1:
        raise SystemExit("FAIL reference driver does not carry exactly one %r"
                         % marker)
    expected = reference.replace(marker, "#define TEST_CPM 0")
    if source != expected:
        delta = list(difflib.unified_diff(
            expected.splitlines(), source.splitlines(),
            fromfile="expected-single-line-seam", tofile=driver_path, n=2))
        print("\n".join(delta[:40]))
        raise SystemExit("FAIL diag u85 driver differs beyond TEST_CPM=1 -> 0")
    print("PASS diag u85 driver seam: sole difference is TEST_CPM=1 -> 0")


def check_reference_sequence(text, header_path, nc, seam):
    """Gate the v6 power-guard-reset-guard-program ordering.

    v5 boot6 proved PMU state cannot persist while the selftest driver has
    requested clock/power shutdown. v6 must first hold power with CMD=0, wait,
    perform reset+guard+final programming, and defer CMD=0xC until after it.
    """
    htext = open(header_path).read()
    masks = {}
    for name in ("NPU_PMCR_CNT_EN_MSK", "NPU_PMCR_EVENT_CNT_RST_MSK",
                 "NPU_PMCR_CYCLE_CNT_RST_MSK", "NPU_REG_PMCR",
                 "NPU_REG_PMCNTENSET"):
        hits = re.findall(r"^#define\s+%s\s+(0x[0-9A-Fa-f]+)U\s*$" % name,
                          htext, re.M)
        if len(hits) != 1:
            raise SystemExit("FAIL %s: expected 1 definition, found %d"
                             % (name, len(hits)))
        masks[name] = int(hits[0], 16)

    pmcr = masks["NPU_REG_PMCR"]
    cnten = masks["NPU_REG_PMCNTENSET"]
    en = masks["NPU_PMCR_CNT_EN_MSK"]
    final = en | masks["NPU_PMCR_EVENT_CNT_RST_MSK"] \
               | masks["NPU_PMCR_CYCLE_CNT_RST_MSK"]
    program_pat = r"pmu_reg_write\s*\(\s*0x%04XU\s*,\s*0x%08XU\s*\)" % (pmcr, en)
    pmcr_write_pat = r"pmu_reg_write\s*\(\s*0x%04XU\s*,[^;]*?\)" % pmcr
    program_pos = [m.start() for m in re.finditer(program_pat, text)]
    reset_pos = []
    for m in re.finditer(pmcr_write_pat, text, re.S):
        nums = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]+)U", m.group(0))[1:]]
        value = 0
        for num in nums:
            value |= num
        if nums and value == final:
            reset_pos.append(m.start())
    guard_pos = [m.start() for m in re.finditer(
        r"reset_guard_cycles\s*=\s*65536U", text)]
    power_guard_pos = [m.start() for m in re.finditer(
        r"power_guard_cycles\s*=\s*65536U", text)]
    power_pos = [m.start() for m in re.finditer(
        r"npu_write\s*\(\s*0x08U\s*,\s*0U\s*\)", text)]
    release_pos = [m.start() for m in re.finditer(
        r"npu_write\s*\(\s*0x08U\s*,\s*0x0000000CU\s*\)", text)]
    arm_pos = [m.start() for m in re.finditer(
        r"pmu_reg_write\s*\(\s*0x%04XU" % cnten, text)]

    # Seam-dependent shape. S2 carries a second CMD=0 (the post-return
    # re-hold, which lives in pmu_diag_rehold_power earlier in the file), and
    # only S3 owns a runner-issued terminal release -- S1/S2 link the
    # reference driver, which issues its own inside test_u85().
    want_power = 2 if seam == "S2" else 1
    want_release = 0 if seam == "S1" else 1

    ordering_ok = False
    if (len(power_pos) == want_power and len(power_guard_pos) == 1
            and len(reset_pos) == 1 and len(guard_pos) == 1
            and len(program_pos) == 1 and len(release_pos) == want_release):
        # The pre-hold is the CMD=0 write immediately preceding the power
        # guard; for S2 the other one is the re-hold helper's body, which
        # sits earlier in the translation unit but runs after the inference.
        before_guard = [p for p in power_pos if p < power_guard_pos[0]]
        pre_hold = max(before_guard) if before_guard else None
        arm_after = [p for p in arm_pos if p > program_pos[0]]
        reset_after = [p for p in reset_pos if p > program_pos[0]]
        ordering_ok = (pre_hold is not None
                       and pre_hold < power_guard_pos[0] < reset_pos[0]
                       < guard_pos[0] < program_pos[0]
                       and (not release_pos or program_pos[0] < release_pos[0])
                       and not reset_after
                       and ((not arm_after)
                       if nc == "skiparm"
                       else (len(arm_after) == 1)))
    if not ordering_ok:
        print("  FAIL %s sequence: power=%s (want %d) power_guard=%s reset=%s "
              "reset_guard=%s program=%s arm=%s release=%s (want %d)"
              % (seam, power_pos, want_power, power_guard_pos, reset_pos,
                 guard_pos, program_pos, arm_pos[-1:] or "none", release_pos,
                 want_release))
        print("FAIL sequence is not power-hold -> guard -> reset -> guard -> "
              "program -> arm [-> post-snapshot power-release]")
        sys.exit(1)
    tail = "skip-arm control" if nc == "skiparm" else "arm"
    print("  PASS %s sequence power-hold -> guard -> reset -> guard -> "
          "CNT_EN-only program -> %s%s"
          % (seam, tail,
             " -> deferred power-release" if want_release
             else " (driver owns the terminal release)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preprocessed")
    ap.add_argument("--regs-header")
    ap.add_argument("--case", choices=("A", "B", "C"))
    ap.add_argument("--nc", default="none",
                    choices=("none", "skipcfg", "noevent", "skiparm", "forceovf"))
    ap.add_argument("--map")
    ap.add_argument("--map-only", action="store_true")
    ap.add_argument("--driver-source")
    ap.add_argument("--reference-driver")
    ap.add_argument("--driver-only", action="store_true")
    ap.add_argument("--seam", choices=("S1", "S2", "S3"))
    ap.add_argument("--seam-artifacts", action="store_true")
    ap.add_argument("--elf")
    ap.add_argument("--objdump")
    a = ap.parse_args()

    if a.map_only:
        if not a.map:
            raise SystemExit("--map-only requires --map")
        check_map(a.map)
        return
    if a.seam_artifacts:
        if not (a.map and a.elf and a.objdump and a.seam):
            raise SystemExit("--seam-artifacts requires --map, --elf, "
                             "--objdump and --seam")
        check_seam_artifacts(a.map, a.elf, a.objdump, a.seam)
        return
    if a.driver_only:
        if not (a.driver_source and a.reference_driver):
            raise SystemExit("--driver-only requires --driver-source and "
                             "--reference-driver")
        check_driver_seam(a.driver_source, a.reference_driver)
        return
    if not (a.preprocessed and a.regs_header and a.case):
        raise SystemExit("preprocess mode requires --preprocessed, "
                         "--regs-header and --case")

    key = (a.case, a.nc)
    if key not in EXPECTED:
        raise SystemExit("FAIL no expectation for case=%s nc=%s" % key)

    offsets = read_offsets(a.regs_header)
    text = open(a.preprocessed).read()

    ok = True
    for name, want in zip(REGS, EXPECTED[key]):
        # After preprocessing the macro argument is the bare offset literal,
        # rendered exactly as the generated header spells it (0x%04XU).
        pat = r"pmu_reg_write\s*\(\s*0x%04XU" % offsets[name]
        got = len(re.findall(pat, text))
        status = "PASS" if got == want else "FAIL"
        if got != want:
            ok = False
        print("  %s %-22s writes: %d (expected %d)" % (status, name, got, want))

    if not ok:
        print("FAIL case=%s nc=%s: write pattern does not match the requested "
              "identity" % key)
        sys.exit(1)

    seam = a.seam or "S3"
    check_reference_sequence(text, a.regs_header, a.nc, seam)
    check_seam_sequence(text, seam, NPU_CMD_OFFSET)
    print("PASS diag case identity: case=%s nc=%s" % key)


main()
