#!/usr/bin/env python3
"""S0-3 step 2a verdicts: does TA profile 2 remove the CPU-NPU gap? (evidence/s0_3_ta/contract.md)

  python3 host/analysis/s0_3_ta.py <fi101_s013 raw root> <s0_3_ta root> <out dir>

Profile 1 reference: <s013 root>/<cond>/<model>/ (boots 94-100). This experiment: <root>/ctl/mobilenet (boot 129,
drift check) and <root>/ta2/<model>/ (boots 130-136).
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402

WARMUP = 2
GAP_MODELS_MIN_FRAC = 0.05
DRIFT_MODEL = "mobilenet_v2_1.0_224_INT8"


def window(runs):
    """Per measured RUN: (frac, ratio) from the inference-window seams."""
    return [((r["infer_cpu"] - r["infer"]) / r["infer"], r["infer"] / r["infer_cpu"])
            for r in runs.values() if r["infer"] and r["infer_cpu"]]


def usable(runs):
    return bool(runs) and all(r["valid"] for r in runs.values()) and len(window(runs)) == len(runs)


def median_frac(runs):
    return S.med([f for f, _ in window(runs)])


def drift(ctl, ref):
    if not (usable(ctl) and usable(ref)):
        return "UNPROVEN"
    f, f_ref = median_frac(ctl), median_frac(ref)
    a, ra = S.med(S.values(ctl, S.ACTIVE)), S.values(ref, S.ACTIVE)
    ok = abs(f - f_ref) <= 0.10 * abs(f_ref) and min(ra) * 0.995 <= a <= max(ra) * 1.005
    return "DRIFT_OK" if ok else "DRIFT"


def model_verdict(p1, p2):
    """None for a model without a profile-1 gap (descriptive only)."""
    if not (usable(p1) and usable(p2)):
        return "UNPROVEN"
    f1 = median_frac(p1)
    if f1 < GAP_MODELS_MIN_FRAC:
        return None
    if all(0.99 <= r <= 1.01 for _, r in window(p2)):
        return "TA_REMOVES_GAP"
    if median_frac(p2) <= 0.5 * f1:
        return "TA_REDUCES_GAP"
    return "TA_NO_EFFECT"


def overall(verdicts, drift_verdict):
    v = [x for x in verdicts if x is not None]
    if drift_verdict != "DRIFT_OK" or not v or "UNPROVEN" in v:
        return "UNPROVEN"
    if all(x == "TA_REMOVES_GAP" for x in v):
        return "TA_EXPLAINS"
    if all(x == "TA_NO_EFFECT" for x in v):
        return "TA_NOT_EXPLAINS"
    return "MIXED"


def describe(runs):
    if not runs:
        return {}
    w = window(runs)
    out = dict(npu_active=S.med(S.values(runs, S.ACTIVE)), infer_npu=S.med([r["infer"] for r in runs.values()]),
               infer_cpu=S.med([r["infer_cpu"] for r in runs.values()]), frac=S.med([f for f, _ in w]),
               s0_3_ratio_in_band=all(0.99 <= r <= 1.01 for _, r in w))
    out["gap"] = out["infer_cpu"] - out["infer_npu"]
    for name, e in S.BEATS.items():
        out[f"{name}_beats"] = S.med(S.values(runs, e))
    out["gap_per_sram_wr_beat"] = out["gap"] / out["sram_wr_beats"] if out["sram_wr_beats"] else None
    return out


def find(root, model):
    hits = [d for d in pathlib.Path(root).glob(f"*/{model}") if (d / "runs.csv").exists()]
    return hits[0] if len(hits) == 1 else None


def main(s013_root, root, out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    load = lambda d: S.load_runs(d, WARMUP) if d and (d / "runs.csv").exists() else {}
    root = pathlib.Path(root)
    models = sorted(d.name for d in pathlib.Path(s013_root).glob("*/*") if (d / "runs.csv").exists())
    d_v = drift(load(root / "ctl" / DRIFT_MODEL), load(find(s013_root, DRIFT_MODEL)))
    rows, desc = [], []
    for m in models:
        p1, p2 = load(find(s013_root, m)), load(root / "ta2" / m)
        v = model_verdict(p1, p2)
        rows.append(dict(model=m, verdict=v if v else "DESCRIPTIVE_ONLY", measured_runs_p2=len(p2)))
        desc += [dict(model=m, ta_profile=p, **describe(r)) for p, r in ((1, p1), (2, p2)) if r]
    ctl = load(root / "ctl" / DRIFT_MODEL)
    if ctl:
        desc.append(dict(model=DRIFT_MODEL, ta_profile="1 (boot 129)", **describe(ctl)))
    res = dict(drift=d_v, overall=overall([None if r["verdict"] == "DESCRIPTIVE_ONLY" else r["verdict"] for r in rows],
                                         d_v), models=rows)
    for name, rs in (("verdicts", rows), ("describe", desc)):
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n"); w.writeheader(); w.writerows(rs)
    json.dump(res, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
