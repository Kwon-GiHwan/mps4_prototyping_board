"""S4 -- apply / revert the core-driver stall-counter patch, proven by digest.

Contract: plan 2026-09-14 section 11 (corrected after the manager review: the stock U85 profiler
already uses FIVE event slots, counters 0-4 = NPU_ACTIVE, SRAM_RD, SRAM_WR, EXT_RD, EXT_WR; only
counters 5-7 are free). The patch programs counters 5-7 BEFORE the HAL's inference_begin hook
(CCNT and counters 0-4 untouched) and prints them AFTER the HAL's inference_end hook.
Measurement window (manager review 2): the extra counters are enabled BEFORE the HAL's begin hook
and explicitly DISABLED after the HAL's end hook, immediately before they are read; the S4 window
is therefore slightly wider than the stock TOTAL window and is recorded as an S4-specific window,
never equated with TOTAL. The HAL resets all event counters once at init (EVCNTR_ALL_Reset), and
the counters start at zero; overflow status is read from PMU_Get_CNTR_OVS and printed.
Two passes because four events do not fit in three slots:
  pass A: MAC_ACTIVE, MAC_STALLED_BY_W, MAC_STALLED_BY_IB
  pass B: MAC_ACTIVE, AO_STALLED_BY_OB, NPU_IDLE   (MAC_ACTIVE repeated as a cross-pass check)

  python3 patch_driver.py apply A|B   # stock digest required; writes patched file, saves stock copy
  python3 patch_driver.py revert   # restores the stock copy; verifies stock digest
  python3 patch_driver.py status
"""
import hashlib, shutil, sys

DRV = "/opt/arm/ml-embedded-evaluation-kit/dependencies/core-driver/src/ethosu_driver.c"
STOCK_SHA = "56b2fecb3c5f4327a9c0b2ecfa070416efa84f54496cbaf0e5750649c089963f"
SAVE = "/tmp/s4/ethosu_driver.c.stock"

BEGIN_ANCHOR = "    ethosu_inference_begin(drv, drv->job.user_arg);\n"
INIT_ANCHOR = "    ethosu_register_driver(drv);\n"   # end of ethosu_init(): v2 programs the counters here
END_ANCHOR = "        ethosu_inference_end(drv, drv->job.user_arg);\n"
INCLUDE_ANCHOR = '#include "ethosu_log.h"\n'

PASSES = {"A": ("MAC_ACTIVE", "MAC_STALLED_BY_W", "MAC_STALLED_BY_IB"),
          "B": ("MAC_ACTIVE", "AO_STALLED_BY_OB", "NPU_IDLE")}


def blocks(pass_id, variant="v1"):
    ev = PASSES[pass_id]
    where = "at driver init (v2)" if variant == "v2" else "before the HAL hook (v1)"
    begin = "#if defined(ETHOSU85)\n    /* S4 pass %s: counters 5-7, programmed %s (0-4 stay stock). */\n" % (pass_id, where)
    for i, e in enumerate(ev):
        begin += "    ETHOSU_PMU_Set_EVTYPER(drv, %d, ETHOSU_PMU_%s);\n" % (5 + i, e)
    begin += "    ETHOSU_PMU_CNTR_Enable(drv, ETHOSU_PMU_CNT6_Msk | ETHOSU_PMU_CNT7_Msk | ETHOSU_PMU_CNT8_Msk);\n#endif\n"
    end = ("#if defined(ETHOSU85)\n        /* S4 pass %s: disable the extra counters first (S4 window = before HAL begin .. here), then read. */\n"
           "        ETHOSU_PMU_CNTR_Disable(drv, ETHOSU_PMU_CNT6_Msk | ETHOSU_PMU_CNT7_Msk | ETHOSU_PMU_CNT8_Msk);\n") % pass_id
    for i, e in enumerate(ev):
        end += '        printf("NPU S4 %s: %%u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, %d));\n' % (e, 5 + i)
    end += '        printf("NPU S4 OVS: 0x%08x\\n", (unsigned)ETHOSU_PMU_Get_CNTR_OVS(drv));\n'
    end += "#endif\n"
    return begin, end


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def apply(pass_id, variant="v1"):
    """v1: program the extra counters immediately before the HAL begin hook (qualification 1: FAILED G2,
    NPU_ACTIVE shifted by -12 cycles). v2: program them once at the end of ethosu_init(), long before any
    inference, so no PMU register traffic occurs near the measurement window."""
    begin_block, end_block = blocks(pass_id, variant)
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("refuse: driver is not stock (%s)" % cur)
    src = open(DRV).read()
    anchor = INIT_ANCHOR if variant == "v2" else BEGIN_ANCHOR
    for a in (anchor, END_ANCHOR, INCLUDE_ANCHOR):
        if src.count(a) != 1:
            raise SystemExit("refuse: anchor not unique: %r" % a)
    shutil.copy(DRV, SAVE)
    src = src.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + '#include "pmu_ethosu.h"\n')
    src = src.replace(anchor, anchor + begin_block) if variant == "v2" else src.replace(anchor, begin_block + anchor)
    src = src.replace(END_ANCHOR, END_ANCHOR + end_block)
    open(DRV, "w").write(src)
    print("applied pass", pass_id, variant, sha(DRV))


def revert():
    shutil.copy(SAVE, DRV)
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("REVERT FAILED: digest %s" % cur)
    print("reverted", cur)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "apply":
        apply(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "v1")
    elif cmd == "revert":
        revert()
    else:
        print("stock" if sha(DRV) == STOCK_SHA else "PATCHED", sha(DRV))
