"""S4 -- apply / revert the core-driver stall-counter patch, proven by digest.

Contract: plan 2026-09-14 section 11 (corrected after the manager review: the stock U85 profiler
already uses FIVE event slots, counters 0-4 = NPU_ACTIVE, SRAM_RD, SRAM_WR, EXT_RD, EXT_WR; only
counters 5-7 are free). The patch programs counters 5-7 BEFORE the HAL's inference_begin hook
(CCNT and counters 0-4 untouched) and prints them AFTER the HAL's inference_end hook.
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
END_ANCHOR = "        ethosu_inference_end(drv, drv->job.user_arg);\n"
INCLUDE_ANCHOR = '#include "ethosu_log.h"\n'

PASSES = {"A": ("MAC_ACTIVE", "MAC_STALLED_BY_W", "MAC_STALLED_BY_IB"),
          "B": ("MAC_ACTIVE", "AO_STALLED_BY_OB", "NPU_IDLE")}


def blocks(pass_id):
    ev = PASSES[pass_id]
    begin = "#if defined(ETHOSU85)\n    /* S4 pass %s: counters 5-7, programmed before the HAL hook (0-4 stay stock). */\n" % pass_id
    for i, e in enumerate(ev):
        begin += "    ETHOSU_PMU_Set_EVTYPER(drv, %d, ETHOSU_PMU_%s);\n" % (5 + i, e)
    begin += "    ETHOSU_PMU_CNTR_Enable(drv, ETHOSU_PMU_CNT6_Msk | ETHOSU_PMU_CNT7_Msk | ETHOSU_PMU_CNT8_Msk);\n#endif\n"
    end = "#if defined(ETHOSU85)\n        /* S4 pass %s: read after the HAL hook has disabled its own counters. */\n" % pass_id
    for i, e in enumerate(ev):
        end += '        printf("NPU S4 %s: %%u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, %d));\n' % (e, 5 + i)
    end += "#endif\n"
    return begin, end


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def apply(pass_id):
    begin_block, end_block = blocks(pass_id)
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("refuse: driver is not stock (%s)" % cur)
    src = open(DRV).read()
    for a in (BEGIN_ANCHOR, END_ANCHOR, INCLUDE_ANCHOR):
        if src.count(a) != 1:
            raise SystemExit("refuse: anchor not unique: %r" % a)
    shutil.copy(DRV, SAVE)
    src = src.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + '#include "pmu_ethosu.h"\n')
    src = src.replace(BEGIN_ANCHOR, begin_block + BEGIN_ANCHOR)
    src = src.replace(END_ANCHOR, END_ANCHOR + end_block)
    open(DRV, "w").write(src)
    print("applied pass", pass_id, sha(DRV))


def revert():
    shutil.copy(SAVE, DRV)
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("REVERT FAILED: digest %s" % cur)
    print("reverted", cur)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "apply":
        apply(sys.argv[2])
    elif cmd == "revert":
        revert()
    else:
        print("stock" if sha(DRV) == STOCK_SHA else "PATCHED", sha(DRV))
