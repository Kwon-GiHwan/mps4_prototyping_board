#!/usr/bin/env python3
"""Equivalence experiment A (evidence/equiv_a/contract.md): what the vendor path leaves in CFG_SRAM_CAP / CFG_EXT_CAP
(E1) and in TA_EXT MAXR when MLEK's 64 is written (E2), read back by the diagnostic image (-DRUNNER_DIAG_EQUIV).
TA profile 1.

  python3 host/analysis/equiv_a.py <diag root> <reference root> <out dir>

<diag root>/<model>/ and <reference root>/<model>/ hold run_pmu_events.py output (raw_runs.json, runs.csv) of the same
blob and ids: the diagnostic image and the measurement image d0cd4775.

Diagnostic record words (Measurement.trailing[20:29]): RUN index since boot, CAP SRAM/EXT at __wrap_test_u85 entry,
CAP SRAM/EXT after the vendor's writes (POWER_CTRL printf), CAP SRAM/EXT at the CPM seam, TA_EXT MAXR after writing
64, TA_EXT MAXR after restoring the profile value.

  E1  UNPROVEN if a word is missing or the RUN 1 entry value is absent; E1_UNSTABLE if the post-write or seam values
      vary between RUNs; E1_INERT if every post-write value equals RUN 1's entry value (= the reset value MLEK keeps);
      otherwise E1_DIFFERS (the runner runs with a CAP state MLEK does not have).
  E2  UNPROVEN if a word is missing or any restore read differs from profile 1's 0; E2_UNSTABLE if the read after
      writing 64 varies; E2_SAME if it reads 0 (MLEK's 64 leaves the runner's state); E2_DIFFERS if it reads 64;
      otherwise E2_OTHER.
  Image  every RUN valid in both roots; each key judged in the reference (2B-0b rule: deterministic 0.1 %, jittery
      max(1 %, reference RUN width), noisy not judged) within tolerance -> DIAG_IMAGE_REPRODUCES, else
      DIAG_IMAGE_DIFFERS; a judged key missing -> UNPROVEN.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402
import s2_mask_confirm as M  # noqa: E402
import s2b3_windows as W  # noqa: E402

WARMUP = 2
FIRST = 20                       # trailing index of the first diagnostic word (record field 123)
WORDS = ("run_index", "cap_sram_entry", "cap_ext_entry", "cap_sram_written", "cap_ext_written", "cap_sram_seam",
         "cap_ext_seam", "ta_ext_maxr_after_64", "ta_ext_maxr_restored")
PROFILE1_EXT_MAXR, MLEK_EXT_MAXR = 0, 64


def diag_words(raw: list[dict]) -> list[dict]:
    """One dict per RUN entry of raw_runs.json; None for a RUN without the diagnostic words."""
    out = []
    for r in raw:
        if "set_id" not in r:
            continue
        w = r["trailing"][FIRST:FIRST + len(WORDS)]
        out.append(dict(zip(WORDS, w)) if len(w) == len(WORDS) else None)
    return out


def e1(ws: list[dict | None]) -> tuple[str, dict]:
    if not ws or any(w is None for w in ws):
        return "UNPROVEN", dict(reason="diagnostic words missing")
    first = [w for w in ws if w["run_index"] == 1]
    if not first:
        return "UNPROVEN", dict(reason="no RUN 1 after boot")
    reset = (first[0]["cap_sram_entry"], first[0]["cap_ext_entry"])
    written = {(w["cap_sram_written"], w["cap_ext_written"]) for w in ws}
    seam = {(w["cap_sram_seam"], w["cap_ext_seam"]) for w in ws}
    det = dict(reset=[f"0x{x:08x}" for x in reset], written=sorted([f"0x{a:08x}", f"0x{b:08x}"] for a, b in written),
               seam=sorted([f"0x{a:08x}", f"0x{b:08x}"] for a, b in seam))
    if len(written) != 1 or len(seam) != 1:
        return "E1_UNSTABLE", det
    return ("E1_INERT" if written == {reset} else "E1_DIFFERS"), det


def e2(ws: list[dict | None]) -> tuple[str, dict]:
    if not ws or any(w is None for w in ws):
        return "UNPROVEN", dict(reason="diagnostic words missing")
    if any(w["ta_ext_maxr_restored"] != PROFILE1_EXT_MAXR for w in ws):
        return "UNPROVEN", dict(reason="TA_EXT MAXR not restored to profile 1")
    after = {w["ta_ext_maxr_after_64"] for w in ws}
    det = dict(after_writing_64=sorted(after))
    if len(after) != 1:
        return "E2_UNSTABLE", det
    v = after.pop()
    return {PROFILE1_EXT_MAXR: "E2_SAME", MLEK_EXT_MAXR: "E2_DIFFERS"}.get(v, "E2_OTHER"), det


def image(diag: dict, ref: dict) -> tuple[str, dict]:
    """diag, ref: S.load_runs results of the same blob and ids on the two images."""
    if not diag or not ref or not all(r["valid"] for r in list(diag.values()) + list(ref.values())):
        return "UNPROVEN", dict(reason="missing or invalid RUN")
    off = []
    for k in W.keys(ref):
        w = M.width(W.series(ref, k))
        if M.klass(w) not in ("DETERMINISTIC", "JITTERY"):
            continue
        d = W.series(diag, k)
        if not d:
            return "UNPROVEN", dict(reason=f"key {k} missing in the diagnostic image")
        if not M.close(S.med(d), S.med(W.series(ref, k)), M.tol_pass(w)):
            off.append(str(k))
    return ("DIAG_IMAGE_REPRODUCES" if not off else "DIAG_IMAGE_DIFFERS"), dict(outside=off)


def main(diag_root: str, ref_root: str, out: str) -> dict:
    res = {}
    for d in sorted(pathlib.Path(diag_root).iterdir()):
        if not (d / "raw_runs.json").exists():
            continue
        ws = diag_words(json.loads((d / "raw_runs.json").read_text()))
        ref = pathlib.Path(ref_root) / d.name
        im = image(S.load_runs(d, WARMUP), S.load_runs(ref, WARMUP) if (ref / "runs.csv").exists() else {})
        res[d.name] = dict(zip(("E1", "E1_detail"), e1(ws))) | dict(zip(("E2", "E2_detail"), e2(ws))) \
            | dict(zip(("image", "image_detail"), im))
    o = pathlib.Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), indent=1, default=str))
