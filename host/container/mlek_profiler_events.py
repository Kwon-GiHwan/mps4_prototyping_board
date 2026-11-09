#!/usr/bin/env python3
"""MLEK instrumented build (docs/plan/equivalence_plan.md §9, C-c; owner 2026-11-09): the Ethos-U85 profiler of MLEK
b2c0bb2 counts ACTIVE and four beat counters (`ethosu_profiler.c`, hard-wired). This adds MAC_ACTIVE, MAC_DPU_ACTIVE
and AO_ACTIVE in counters 6-8 (U85 has 8), so MLEK reports the internal-unit events the runner measures. Nothing else
changes: the first five counters, their order and masks stay as they are, so the stock counters can be compared with
the stock build on the same input (the disturbance check).

The MLEK tree is patched in place for one build and restored by digest afterwards, as the amendment-2 VERIFY fix was
(`/work/a2/build.sh`): run `apply`, build, then `restore` (git checkout of the two files, then the digests are checked).

  python3 mlek_profiler_events.py apply <MLEK root>
  python3 mlek_profiler_events.py restore <MLEK root>
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

C_FILE = "source/hal/source/components/npu/ethosu_profiler.c"
H_FILE = "source/hal/source/components/npu/include/ethosu_profiler.h"
ORIGINAL = {C_FILE: "a52bcefc754785364d265d74a12879831a1236a580244cf984a8852bf8ab9aec",
            H_FILE: "be83fefe6ab358f97328c812f08ae9ae5dd8b55e117308c6ef438098981f16fe"}
EXTRA = (("ETHOSU_PMU_MAC_ACTIVE", "CNT6", "NPU ETHOSU_PMU_MAC_ACTIVE", "unit_cycles"),
         ("ETHOSU_PMU_MAC_DPU_ACTIVE", "CNT7", "NPU ETHOSU_PMU_MAC_DPU_ACTIVE", "unit_cycles"),
         ("ETHOSU_PMU_AO_ACTIVE", "CNT8", "NPU ETHOSU_PMU_AO_ACTIVE", "unit_cycles"))

H_OLD = "    #define ETHOSU_USED_PMU_NCOUNTERS   (5U)    /**< Number of actual PMU counters we want to display */\n"
H_NEW = ("    #define ETHOSU_USED_PMU_NCOUNTERS   (8U)    /**< equivalence C-c: + MAC_ACTIVE, MAC_DPU_ACTIVE, "
         "AO_ACTIVE */\n")
C_OLD = ("    counters->npu_evt_counters[4].unit       = unit_beats;\n"
         "#endif /* defined(ETHOSU55) || defined(ETHOSU65) */\n")


def c_new() -> str:
    blocks = "".join(
        f"\n    counters->npu_evt_counters[{5 + i}].event_type = {ev};\n"
        f"    counters->npu_evt_counters[{5 + i}].event_mask = ETHOSU_PMU_{cnt}_Msk;\n"
        f"    counters->npu_evt_counters[{5 + i}].name       = \"{name}\";\n"
        f"    counters->npu_evt_counters[{5 + i}].unit       = {unit};\n"
        for i, (ev, cnt, name, unit) in enumerate(EXTRA))
    return ("    counters->npu_evt_counters[4].unit       = unit_beats;\n"
            "    /* equivalence C-c (instrumented build): counters 6-8 */" + blocks
            + "#endif /* defined(ETHOSU55) || defined(ETHOSU65) */\n")


def generate(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{what}: anchor found {text.count(old)} times, need 1")
    return text.replace(old, new)


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def apply(root: pathlib.Path) -> None:
    for f, want in ORIGINAL.items():
        if sha(root / f) != want:
            raise SystemExit(f"{f}: not the pinned original (restore it first)")
    (root / H_FILE).write_text(generate((root / H_FILE).read_text(), H_OLD, H_NEW, H_FILE))
    (root / C_FILE).write_text(generate((root / C_FILE).read_text(), C_OLD, c_new(), C_FILE))
    print("applied:", {f: sha(root / f)[:12] for f in ORIGINAL})


def restore(root: pathlib.Path) -> None:
    subprocess.run(["git", "-C", str(root), "checkout", "--", *ORIGINAL], check=True)
    bad = [f for f, want in ORIGINAL.items() if sha(root / f) != want]
    if bad:
        raise SystemExit(f"restore failed, digest differs: {bad}")
    print("RESTORED by digest:", {f: v[:12] for f, v in ORIGINAL.items()})


if __name__ == "__main__":
    {"apply": apply, "restore": restore}[sys.argv[1]](pathlib.Path(sys.argv[2]))
