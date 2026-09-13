"""S4 -- apply / revert the core-driver stall-counter patch, proven by digest.

Contract: plan 2026-09-14 section 11. Only dependencies/core-driver/src/ethosu_driver.c changes.
The patch programs event counters 4-7 BEFORE the HAL's inference_begin hook (so CCNT and the
HAL's counters 0-3 are untouched) and prints the four values AFTER the HAL's inference_end hook.

  python3 patch_driver.py apply    # stock digest required; writes patched file, saves stock copy
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

BEGIN_BLOCK = """#if defined(ETHOSU85)
    /* S4 stall-counter patch: extra event counters, programmed before the HAL hook. */
    ETHOSU_PMU_Set_EVTYPER(drv, 4, ETHOSU_PMU_MAC_ACTIVE);
    ETHOSU_PMU_Set_EVTYPER(drv, 5, ETHOSU_PMU_MAC_STALLED_BY_W);
    ETHOSU_PMU_Set_EVTYPER(drv, 6, ETHOSU_PMU_MAC_STALLED_BY_IB);
    ETHOSU_PMU_Set_EVTYPER(drv, 7, ETHOSU_PMU_AO_STALLED_BY_OB);
    ETHOSU_PMU_CNTR_Enable(drv, ETHOSU_PMU_CNT5_Msk | ETHOSU_PMU_CNT6_Msk | ETHOSU_PMU_CNT7_Msk | ETHOSU_PMU_CNT8_Msk);
#endif
"""
END_BLOCK = """#if defined(ETHOSU85)
        /* S4 stall-counter patch: read after the HAL hook has disabled its own counters. */
        printf("NPU S4 MAC_ACTIVE: %u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, 4));
        printf("NPU S4 MAC_STALLED_BY_W: %u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, 5));
        printf("NPU S4 MAC_STALLED_BY_IB: %u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, 6));
        printf("NPU S4 AO_STALLED_BY_OB: %u cycles\\n", (unsigned)ETHOSU_PMU_Get_EVCNTR(drv, 7));
#endif
"""


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def apply():
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("refuse: driver is not stock (%s)" % cur)
    src = open(DRV).read()
    for a in (BEGIN_ANCHOR, END_ANCHOR, INCLUDE_ANCHOR):
        if src.count(a) != 1:
            raise SystemExit("refuse: anchor not unique: %r" % a)
    shutil.copy(DRV, SAVE)
    src = src.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + '#include "pmu_ethosu.h"\n')
    src = src.replace(BEGIN_ANCHOR, BEGIN_BLOCK + BEGIN_ANCHOR)
    src = src.replace(END_ANCHOR, END_ANCHOR + END_BLOCK)
    open(DRV, "w").write(src)
    print("applied", sha(DRV))


def revert():
    shutil.copy(SAVE, DRV)
    cur = sha(DRV)
    if cur != STOCK_SHA:
        raise SystemExit("REVERT FAILED: digest %s" % cur)
    print("reverted", cur)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "apply":
        apply()
    elif cmd == "revert":
        revert()
    else:
        print("stock" if sha(DRV) == STOCK_SHA else "PATCHED", sha(DRV))
