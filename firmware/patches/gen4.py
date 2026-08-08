P = "Selftest_pmu/gen_npu_pmu_regs.py"
s = open(P).read()

# --- extraction: PMCCNTR_CFG fields and the pmu_event values ---------------
old = '''    cc = _bitfields(text, "pmccntr_r", span=64)'''
new = '''    # PMCCNTR_CFG: the cycle counter is gated by a start/stop EVENT pair. A
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
    em = re.search(r"enum class pmu_event\\s*:\\s*\\w+\\s*\\{(.+?)\\n\\};", text, re.S)
    if not em:
        raise SystemExit("enum class pmu_event not found")
    events = {}
    for name, val in re.findall(r"(\\w+)\\s*=\\s*(\\d+)\\s*,", em.group(1)):
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

    cc = _bitfields(text, "pmccntr_r", span=64)'''
assert s.count(old) == 1
s = s.replace(old, new)

s = s.replace("    return found, bits, widths[\"CYCLE_CNT_LO\"] + widths[\"CYCLE_CNT_HI\"], cyc",
              "    cyc.update(cfg)\n"
              "    return found, bits, widths[\"CYCLE_CNT_LO\"] + widths[\"CYCLE_CNT_HI\"], cyc")

# --- rendering -------------------------------------------------------------
old_tail = '''          "",
          "_Static_assert(NPU_PMU_CYCLE_COUNTER_WIDTH == 48,'''
new_tail = '''          "",
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
          "#define NPU_PMU_CYCLE_CFG_VALUE \\\\",
          "    (((NPU_PMU_EVENT_CYCLE    << NPU_PMU_PMCCNTR_CFG_START_SHIFT) & NPU_PMU_PMCCNTR_CFG_START_MASK) | \\\\",
          "     ((NPU_PMU_EVENT_NO_EVENT << NPU_PMU_PMCCNTR_CFG_STOP_SHIFT)  & NPU_PMU_PMCCNTR_CFG_STOP_MASK))",
          "",
          "_Static_assert(NPU_PMU_EVENT_CYCLE == 17u, \\"unexpected CYCLE event\\");",
          "_Static_assert(NPU_PMU_EVENT_NO_EVENT == 0u, \\"unexpected NO_EVENT\\");",
          "_Static_assert(NPU_PMU_CYCLE_CFG_VALUE == 0x11u,",
          "               \\"cycle counter configuration disagrees with the known encoding\\");",
          "_Static_assert(NPU_PMU_CYCLE_COUNTER_WIDTH == 48,'''
assert s.count(old_tail) == 1
s = s.replace(old_tail, new_tail)

s = s.replace('    print("  PMOVS  cycle overflow bit:     %d" % cyc["PMOVSSET_CYCLE_OVF"])',
              '    print("  PMOVS  cycle overflow bit:     %d" % cyc["PMOVSSET_CYCLE_OVF"])\n'
              '    print("  CFG start/stop shift:          %d / %d" % (cyc["START"][0], cyc["STOP"][0]))\n'
              '    print("  pmu_event CYCLE / NO_EVENT:    %d / %d"\n'
              '          % (cyc["EVENT_CYCLE"], cyc["EVENT_NO_EVENT"]))')
open(P, "w").write(s)
print("generator extended")
