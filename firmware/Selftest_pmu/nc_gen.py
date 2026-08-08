"""Negative gates for the register generator.

Each case tampers with a COPY of the vendor header. A case is DETECTED if the
generator refuses OR the header it produces fails to compile. Both are valid
defences; what is not acceptable is a mutated header that generates cleanly AND
compiles cleanly, because that is a wrong constant nothing rejects.

Why the compile step exists
---------------------------
The mismatch checks compare PMCNTENSET against PMCNTENCLR and PMOVSSET against
PMOVSCLR. Moving ONE of a pair is caught. Moving BOTH together leaves them
agreeing with each other, so the comparison passes and only the C
_Static_assert in the generated header stands between that and a wrong build.
Until this file actually compiled the header, that backstop had never once been
exercised in a negative test -- it was an untested assertion about an untested
assertion. The simultaneous-drift cases below are the exact shape of the
milestone-1 defect (cycle bit assumed at 8, actually 31).

Positive control and negative gates are counted SEPARATELY. Reporting "8/8"
when 7 are negative and 1 is a positive control overstates the coverage.
"""

import re
import subprocess
import sys

H = ("/opt/arm/ml-embedded-evaluation-kit/dependencies/core-driver/src/"
     "ethosu85_interface.h")
G = "Selftest_pmu/gen_npu_pmu_regs.py"
CC = "arm-none-eabi-gcc"
CFLAGS = ["-mcpu=cortex-m85+nomve+nofp", "-mthumb", "-mfloat-abi=soft",
          "-std=gnu11", "-fsyntax-only", "-x", "c"]
BASE = open(H).read()

PROBE = "/tmp/probe.c"
open(PROBE, "w").write('#include "/tmp/o.h"\nint probe_ok;\n')


def struct_edit(text, name, old, new, count=1):
    m = re.search(r"struct %s\s*\{.+?\n\};" % name, text, re.S)
    if not m:
        raise SystemExit("struct %s not found" % name)
    return text.replace(m.group(0), m.group(0).replace(old, new, count), 1)


def move_cycle_bit(text, struct):
    """Move a register's cycle bit from 31 to 8 by collapsing the reserved gap."""
    return struct_edit(text, struct, "uint32_t reserved0 : 23;",
                       "uint32_t reserved0 : 0;")


CASES = [
    ("CYCLE event removed", lambda t: t.replace("    CYCLE = 17,\n", "", 1)),
    ("NO_EVENT removed", lambda t: t.replace("    NO_EVENT = 0,\n", "", 1)),
    ("CFG START field removed",
     lambda t: struct_edit(t, "pmccntr_cfg_r",
                           "uint32_t CYCLE_CNT_CFG_START : 10;", "")),
    ("CFG START width 10 -> 8",
     lambda t: struct_edit(t, "pmccntr_cfg_r",
                           "uint32_t CYCLE_CNT_CFG_START : 10;",
                           "uint32_t CYCLE_CNT_CFG_START : 8;")),
    ("PMCNTENSET cycle bit 31 -> 8 (SET only)",
     lambda t: move_cycle_bit(t, "pmcntenset_r")),
    ("PMCNTENCLR cycle bit 31 -> 8 (CLR only)",
     lambda t: move_cycle_bit(t, "pmcntenclr_r")),
    ("PMOVSSET overflow bit 31 -> 8 (SET only)",
     lambda t: move_cycle_bit(t, "pmovsset_r")),
    ("PMOVSCLR overflow bit 31 -> 8 (CLR only)",
     lambda t: move_cycle_bit(t, "pmovsclr_r")),
    # The two that the mismatch check alone cannot catch -- this is the
    # milestone-1 defect reproduced exactly.
    ("PMCNTEN SET+CLR moved TOGETHER 31 -> 8",
     lambda t: move_cycle_bit(move_cycle_bit(t, "pmcntenset_r"), "pmcntenclr_r")),
    ("PMOVS SET+CLR moved TOGETHER 31 -> 8",
     lambda t: move_cycle_bit(move_cycle_bit(t, "pmovsset_r"), "pmovsclr_r")),
    # Stronger still: move ALL FOUR together. They then agree with each other
    # AND sit at bit 8, which is positionally legal (event bits are 0..7), so
    # neither the mismatch check nor the positional assert can see it. Only a
    # cross-check against the known encoding can.
    ("ALL FOUR cycle bits moved TOGETHER 31 -> 8",
     lambda t: move_cycle_bit(move_cycle_bit(move_cycle_bit(move_cycle_bit(
         t, "pmcntenset_r"), "pmcntenclr_r"), "pmovsset_r"), "pmovsclr_r")),
    ("CYCLE_CNT_HI width 16 -> 32",
     lambda t: struct_edit(t, "pmccntr_r", "uint32_t CYCLE_CNT_HI : 16;",
                           "uint32_t CYCLE_CNT_HI : 32;")),
    ("event counter array length 8 -> 4",
     lambda t: t.replace("#define NPU_REG_PMEVCNTR_ARRLEN 0x0008",
                         "#define NPU_REG_PMEVCNTR_ARRLEN 0x0004", 1)),
]


def generate(header_path):
    return subprocess.run([sys.executable, G, "--generate",
                           "--header", header_path, "--out", "/tmp/o.h"],
                          capture_output=True, text=True)


def compiles():
    r = subprocess.run([CC] + CFLAGS + [PROBE], capture_output=True, text=True)
    return r.returncode == 0, r.stderr


print("=== negative gates ===")
escaped = []
for name, edit in CASES:
    open("/tmp/h.h", "w").write(edit(BASE))
    g = generate("/tmp/h.h")
    if g.returncode != 0:
        why = (g.stderr.strip().splitlines() or [""])[-1][:52]
        print("  DETECTED  %-42s generator: %s" % (name, why))
        continue
    ok, err = compiles()
    if not ok:
        line = next((l for l in err.splitlines() if "static assertion" in l.lower()
                     or "_Static_assert" in l), err.strip().splitlines()[-1] if err else "")
        print("  DETECTED  %-42s _Static_assert: %s" % (name, line.strip()[-48:]))
    else:
        print("  ESCAPED   %-42s generated AND compiled cleanly" % name)
        escaped.append(name)

print("\n=== positive control ===")
open("/tmp/h.h", "w").write(BASE)
g = generate("/tmp/h.h")
pos_ok = g.returncode == 0
comp_ok, err = (compiles() if pos_ok else (False, ""))
print("  %-9s unmodified vendor header generates and compiles"
      % ("PASS" if (pos_ok and comp_ok) else "FAIL"))
if pos_ok and not comp_ok:
    print("           compile error: %s" % err.strip().splitlines()[-1][:60])

print("\n=== summary ===")
print("  negative gates:   %d/%d detected" % (len(CASES) - len(escaped), len(CASES)))
print("  positive control: %d/1 passed" % (1 if (pos_ok and comp_ok) else 0))
if escaped:
    print("\n  ESCAPED cases (a wrong constant would ship):")
    for e in escaped:
        print("    - %s" % e)
sys.exit(1 if (escaped or not (pos_ok and comp_ok)) else 0)
