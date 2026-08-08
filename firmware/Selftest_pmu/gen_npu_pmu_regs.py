"""Generate and verify Selftest_pmu/npu_pmu_regs.h from the Ethos-U85 interface header.

The offsets are NOT retyped by hand. They are extracted from the SDK's
ethosu85_interface.h, so a mismatch between this build and the vendor register
map is a build failure rather than a silent wrong address.

  --generate   write the header
  --check      re-extract and compare; non-zero exit on any drift

The core driver itself is deliberately NOT linked: doing so would change the
link closure of the measurement image and contaminate configuration B, which is
supposed to differ from C only by a runtime branch.
"""

import argparse
import re
import sys

SDK_HEADER = ("/opt/arm/ml-embedded-evaluation-kit/dependencies/core-driver/"
              "src/ethosu85_interface.h")
OUT = "Selftest_pmu/npu_pmu_regs.h"

# name -> the #define we extract it from
WANTED = [
    "NPU_REG_PMCR",
    "NPU_REG_PMCNTENSET",
    "NPU_REG_PMCNTENCLR",
    "NPU_REG_PMOVSSET",
    "NPU_REG_PMOVSCLR",
    "NPU_REG_PMINTSET",
    "NPU_REG_PMINTCLR",
    "NPU_REG_PMCCNTR",
    "NPU_REG_PMCCNTR_HI",
    "NPU_REG_PMCCNTR_CFG",
    "NPU_REG_PMEVCNTR_BASE",
    "NPU_REG_PMEVCNTR_ARRLEN",
    "NPU_REG_PMEVTYPER_BASE",
    "NPU_REG_PMEVTYPER_ARRLEN",
]


def _bitfields(text, struct_name, span=32):
    """Ordered (name, shift, width) for one register's C bitfield struct.

    `span` is the register's width in bits. It is 32 for the single-word
    control registers, but PMCCNTR is a TWO-word register (CYCLE_CNT_LO 32 +
    CYCLE_CNT_HI 16), so capping at 32 there silently drops the HI field.
    """
    m = re.search(r"struct %s\s*\{(.+?)\n\};" % struct_name, text, re.S)
    if not m:
        raise SystemExit("struct %s not found" % struct_name)
    out, shift = [], 0
    for name, width in re.findall(r"uint32_t\s+(\w+)\s*:\s*(\d+)\s*;", m.group(1)):
        width = int(width)
        if shift >= span:
            break
        out.append((name, shift, width))
        shift += width
    return out


def _one(fields, pattern, where):
    """Exactly one field matching `pattern`, exactly 1 bit wide, shift 0..31.

    Deliberately strict. The defect this replaces came from DERIVING the cycle
    bit from the event-counter count (8) instead of reading it: the real
    position is 31, because 8 event bits are followed by 23 reserved bits.
    Nothing here may be inferred from another register.
    """
    hits = [f for f in fields if re.fullmatch(pattern, f[0])]
    if len(hits) != 1:
        raise SystemExit("%s: expected exactly 1 field matching %s, found %d"
                         % (where, pattern, len(hits)))
    name, shift, width = hits[0]
    if width != 1:
        raise SystemExit("%s.%s: expected a 1-bit field, found %d" % (where, name, width))
    if not 0 <= shift <= 31:
        raise SystemExit("%s.%s: shift %d out of range" % (where, name, shift))
    return shift


def extract(path):
    text = open(path).read()
    found = {}
    for name in WANTED:
        hits = re.findall(r"^#define\s+%s\s+(0x[0-9A-Fa-f]+|\d+)\s*$" % name, text, re.M)
        if len(hits) != 1:
            raise SystemExit("%s: expected 1 definition, found %d" % (name, len(hits)))
        found[name] = int(hits[0], 0)

    pmcr = _bitfields(text, "pmcr_r")
    bits = {}
    for need in ("cnt_en", "event_cnt_rst", "cycle_cnt_rst", "mask_en", "num_event_cnt"):
        hit = [f for f in pmcr if f[0] == need]
        if len(hit) != 1:
            raise SystemExit("pmcr_r.%s: found %d" % (need, len(hit)))
        bits[need] = (hit[0][1], hit[0][2])

    # Cycle bits, each from its OWN register definition.
    cyc = {
        "PMCNTENSET_CYCLE": _one(_bitfields(text, "pmcntenset_r"), r"CYCLE_CNT", "pmcntenset_r"),
        "PMCNTENCLR_CYCLE": _one(_bitfields(text, "pmcntenclr_r"), r"CYCLE_CNT", "pmcntenclr_r"),
        "PMOVSSET_CYCLE_OVF": _one(_bitfields(text, "pmovsset_r"), r"CYCLE_CNT_OVF", "pmovsset_r"),
        "PMOVSCLR_CYCLE_OVF": _one(_bitfields(text, "pmovsclr_r"), r"CYCLE_CNT_OVF", "pmovsclr_r"),
    }
    if cyc["PMCNTENSET_CYCLE"] != cyc["PMCNTENCLR_CYCLE"]:
        raise SystemExit("PMCNTENSET/PMCNTENCLR cycle bit disagree: %d vs %d"
                         % (cyc["PMCNTENSET_CYCLE"], cyc["PMCNTENCLR_CYCLE"]))
    if cyc["PMOVSSET_CYCLE_OVF"] != cyc["PMOVSCLR_CYCLE_OVF"]:
        raise SystemExit("PMOVSSET/PMOVSCLR overflow bit disagree: %d vs %d"
                         % (cyc["PMOVSSET_CYCLE_OVF"], cyc["PMOVSCLR_CYCLE_OVF"]))

    # PMCCNTR_CFG: the cycle counter is gated by a start/stop EVENT pair. A
    # zeroed register means START = NO_EVENT, i.e. configured never to start --
    # which is exactly what an unprogrammed counter reads back as.
    cfg_fields = _bitfields(text, "pmccntr_cfg_r")
    cfg = {}
    for key, want in (("START", "CYCLE_CNT_CFG_START"), ("STOP", "CYCLE_CNT_CFG_STOP")):
        hit = [f for f in cfg_fields if f[0] == want]
        if len(hit) != 1:
            raise SystemExit("pmccntr_cfg_r.%s: found %d" % (want, len(hit)))
        _, shift, width = hit[0]
        if width != 10 or not 0 <= shift <= 31 or shift + width > 32:
            raise SystemExit("pmccntr_cfg_r.%s: shift %d width %d out of contract"
                             % (want, shift, width))
        cfg[key] = (shift, width)
    if cfg["START"][0] == cfg["STOP"][0]:
        raise SystemExit("PMCCNTR_CFG START and STOP overlap")

    # pmu_event values. NO fallback: if the enum or a member is missing the
    # build fails rather than inventing 0x11 from an external implementation.
    em = re.search(r"enum class pmu_event\s*:\s*\w+\s*\{(.+?)\n\};", text, re.S)
    if not em:
        raise SystemExit("enum class pmu_event not found")
    events = {}
    for name, val in re.findall(r"(\w+)\s*=\s*(\d+)\s*,", em.group(1)):
        if name in events and events[name] != int(val):
            raise SystemExit("pmu_event.%s defined twice with different values" % name)
        events[name] = int(val)
    for need in ("CYCLE", "NO_EVENT"):
        if need not in events:
            raise SystemExit("pmu_event.%s not found -- refusing to guess" % need)
        if not 0 <= events[need] < (1 << cfg["START"][1]):
            raise SystemExit("pmu_event.%s = %d does not fit the CFG field"
                             % (need, events[need]))
    cfg["EVENT_CYCLE"] = events["CYCLE"]
    cfg["EVENT_NO_EVENT"] = events["NO_EVENT"]

    cc = _bitfields(text, "pmccntr_r", span=64)
    widths = dict((n, w) for n, sh, w in cc if n.startswith("CYCLE_CNT_"))
    if widths.get("CYCLE_CNT_LO") != 32:
        raise SystemExit("CYCLE_CNT_LO width %r, expected 32" % widths.get("CYCLE_CNT_LO"))
    if widths.get("CYCLE_CNT_HI") != 16:
        raise SystemExit("CYCLE_CNT_HI width %r, expected 16" % widths.get("CYCLE_CNT_HI"))
    cyc.update(cfg)
    return found, bits, widths["CYCLE_CNT_LO"] + widths["CYCLE_CNT_HI"], cyc


def render(found, bits, cycle_width, cyc):
    L = ["/* GENERATED by Selftest_pmu/gen_npu_pmu_regs.py -- do not edit.",
         " *",
         " * Extracted from the Ethos-U core driver's register map:",
         " *   %s" % SDK_HEADER,
         " *",
         " * The driver is NOT linked; only the register geometry is borrowed,",
         " * and check mode re-verifies it against the vendor header.",
         " *",
         " * EVERY cycle-counter bit below comes from ITS OWN register struct.",
         " * Deriving one from another is what produced the milestone-1 defect:",
         " * the cycle bit was computed as 1<<8 from the event-counter count,",
         " * but 8 event bits are followed by 23 reserved bits, so the real",
         " * position is 31. Bit 8 is reserved and reads as zero, which made a",
         " * wrapped counter look overflow-free.",
         " */",
         "#ifndef NPU_PMU_REGS_H", "#define NPU_PMU_REGS_H", "",
         "/* Register offsets, relative to the NPU base (U85_BASE_ADDRESS). */"]
    for name in WANTED:
        if name.endswith("ARRLEN"):
            continue
        L.append("#define %-28s 0x%04XU" % (name, found[name]))
    L += ["",
          "#define NPU_PMU_EVENT_COUNTERS_MAX   %uU" % found["NPU_REG_PMEVCNTR_ARRLEN"],
          "#define NPU_PMU_EVENT_COUNTER_WIDTH  32U",
          "",
          "/* Cycle counter is %u bits (LO 32 + HI 16), NOT 64. */" % cycle_width,
          "#define NPU_PMU_CYCLE_COUNTER_WIDTH  %uU" % cycle_width,
          "#define NPU_PMU_CYCLE_HI_VALID_BITS  16U",
          ""]
    for fname in ("cnt_en", "event_cnt_rst", "cycle_cnt_rst", "mask_en", "num_event_cnt"):
        pos, width = bits[fname]
        L.append("#define NPU_PMCR_%s_POS %uU" % (fname.upper(), pos))
        L.append("#define NPU_PMCR_%s_MSK 0x%08XU" % (fname.upper(), ((1 << width) - 1) << pos))
    L += ["",
          "/* Per-register cycle bits. Never derived from the counter count. */",
          "#define NPU_PMU_PMCNTEN_CYCLE_SHIFT   %uU" % cyc["PMCNTENSET_CYCLE"],
          "#define NPU_PMU_PMCNTEN_CYCLE_MASK    (1U << NPU_PMU_PMCNTEN_CYCLE_SHIFT)",
          "#define NPU_PMU_PMOVS_CYCLE_OVF_SHIFT %uU" % cyc["PMOVSSET_CYCLE_OVF"],
          "#define NPU_PMU_PMOVS_CYCLE_OVF_MASK  (1U << NPU_PMU_PMOVS_CYCLE_OVF_SHIFT)",
          "",
          "/* Cycle-counter gating. The value is COMPOSED from the extracted",
          " * field positions and event numbers -- 0x11 is never written into",
          " * the source. It only appears in the static assertion below, as a",
          " * cross-check against the independently published encoding. */",
          "#define NPU_PMU_PMCCNTR_CFG_START_SHIFT %uU" % cyc["START"][0],
          "#define NPU_PMU_PMCCNTR_CFG_START_MASK  0x%08XU" % (((1 << cyc["START"][1]) - 1) << cyc["START"][0]),
          "#define NPU_PMU_PMCCNTR_CFG_STOP_SHIFT  %uU" % cyc["STOP"][0],
          "#define NPU_PMU_PMCCNTR_CFG_STOP_MASK   0x%08XU" % (((1 << cyc["STOP"][1]) - 1) << cyc["STOP"][0]),
          "#define NPU_PMU_EVENT_CYCLE             %uU" % cyc["EVENT_CYCLE"],
          "#define NPU_PMU_EVENT_NO_EVENT          %uU" % cyc["EVENT_NO_EVENT"],
          "#define NPU_PMU_CYCLE_CFG_VALUE \\",
          "    (((NPU_PMU_EVENT_CYCLE    << NPU_PMU_PMCCNTR_CFG_START_SHIFT) & NPU_PMU_PMCCNTR_CFG_START_MASK) | \\",
          "     ((NPU_PMU_EVENT_NO_EVENT << NPU_PMU_PMCCNTR_CFG_STOP_SHIFT)  & NPU_PMU_PMCCNTR_CFG_STOP_MASK))",
          "",
          "_Static_assert(NPU_PMU_EVENT_CYCLE == 17u, \"unexpected CYCLE event\");",
          "_Static_assert(NPU_PMU_EVENT_NO_EVENT == 0u, \"unexpected NO_EVENT\");",
          "_Static_assert(NPU_PMU_CYCLE_CFG_VALUE == 0x11u,",
          "               \"cycle counter configuration disagrees with the known encoding\");",
          "_Static_assert(NPU_PMU_CYCLE_COUNTER_WIDTH == 48, \"unexpected PMU cycle width\");",
          "_Static_assert(NPU_PMU_EVENT_COUNTERS_MAX == 8, \"ABI event slot count changed\");",
          "_Static_assert(NPU_PMU_PMCNTEN_CYCLE_SHIFT >= NPU_PMU_EVENT_COUNTERS_MAX,",
          "               \"PMCNTEN cycle bit overlaps the event-counter range\");",
          "_Static_assert(NPU_PMU_PMOVS_CYCLE_OVF_SHIFT >= NPU_PMU_EVENT_COUNTERS_MAX,",
          "               \"PMOVS overflow bit overlaps the event-counter range\");",
          "_Static_assert(NPU_PMU_PMCNTEN_CYCLE_SHIFT == NPU_PMU_PMOVS_CYCLE_OVF_SHIFT,",
          "               \"cycle enable and overflow bits must share a position\");",
          "/* Cross-check against the independently known encoding, exactly as",
          " * NPU_PMU_CYCLE_CFG_VALUE == 0x11 above. The positional rules cannot",
          " * catch every cycle bit being moved to the same wrong place at once:",
          " * bit 8 sits above the event range and the registers still agree with",
          " * each other. Only pinning the known value closes that. This is a",
          " * cross-check, NOT the source -- the value is still extracted. */",
          "_Static_assert(NPU_PMU_PMCNTEN_CYCLE_SHIFT == 31u,",
          "               \"cycle enable bit is not at the known position 31\");",
          "", "#endif /* NPU_PMU_REGS_H */", ""]
    return "\n".join(L)


ap = argparse.ArgumentParser()
ap.add_argument("--generate", action="store_true")
ap.add_argument("--check", action="store_true")
ap.add_argument("--header", default=SDK_HEADER)
ap.add_argument("--out", default=OUT)
a = ap.parse_args()

found, bits, cycle_width, cyc = extract(a.header)
text = render(found, bits, cycle_width, cyc)

if a.generate:
    open(a.out, "w").write(text)
    print("wrote %s" % a.out)
    print("  event counters (array length): %d" % found["NPU_REG_PMEVCNTR_ARRLEN"])
    print("  cycle counter width:           %d bits" % cycle_width)
    print("  PMCNTEN cycle bit:             %d" % cyc["PMCNTENSET_CYCLE"])
    print("  PMOVS  cycle overflow bit:     %d" % cyc["PMOVSSET_CYCLE_OVF"])
    print("  CFG start/stop shift:          %d / %d" % (cyc["START"][0], cyc["STOP"][0]))
    print("  pmu_event CYCLE / NO_EVENT:    %d / %d"
          % (cyc["EVENT_CYCLE"], cyc["EVENT_NO_EVENT"]))
    sys.exit(0)

if a.check:
    try:
        have = open(a.out).read()
    except OSError as exc:
        print("FAIL cannot read %s: %s" % (a.out, exc))
        sys.exit(1)
    if have != text:
        print("FAIL %s no longer matches the vendor register map." % a.out)
        print("     Regenerate it and re-verify the firmware.")
        sys.exit(1)
    print("PASS npu_pmu_regs.h matches %s" % a.header)
    sys.exit(0)

ap.error("choose --generate or --check")
