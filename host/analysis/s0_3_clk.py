#!/usr/bin/env python3
"""S0-3 steps 2c/2d verdicts: is the CPU-NPU gap the TA stopping the NPU clock? (evidence/s0_3_clk/contract.md)

  python3 host/analysis/s0_3_clk.py <fi101_s013 raw root> <s0_3_clk root> <out dir>

Profile 1 reference: <s013 root>/<cond>/<model>/ (boots 94-100). This experiment, per model: <root>/c1/<model>
(profile 1, both TAs count MCLK_OFF), <root>/c2/<model> (profile 1, TA_SRAM counts root-clock CYCLES, TA_EXT MCLK_ON),
<root>/d/<model> (profile 3 = profile 1 with TA MODE bit 0 off, both count MCLK_OFF).
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402
import s0_3_ta as T  # noqa: E402

WARMUP = 2
SELECT = {"c1": 0x1313, "c2": 0x1201, "d": 0x1313}   # PMWL word 28 per arm (read back at the CPM seam)
SMALL_GAP_DRIFT = 0.005                               # absolute frac tolerance for models without a gap


def load(folder):
    runs = S.load_runs(folder, WARMUP) if folder and (folder / "runs.csv").exists() else {}
    raw = folder / "raw_runs.json" if folder else None
    if runs and raw.exists():
        for x in json.load(open(raw)):
            k = (x.get("set_id"), x.get("rep"))
            if k in runs:
                runs[k].update(ta_sel=x.get("ta_perfctrl_seam"), ta_sram=x.get("ta_sram_count"),
                               ta_ext=x.get("ta_ext_count"))
    return runs


def usable(runs, arm):
    return T.usable(runs) and all(r.get("ta_sel") == SELECT[arm] and r.get("ta_sram") is not None
                                  and r.get("ta_ext") is not None for r in runs.values())


def drift(runs, ref, arm):
    """Does selecting a TA counter change the timing? Arm vs the s013 profile-1 boot of the same model."""
    if not (usable(runs, arm) and T.usable(ref)):
        return "UNPROVEN"
    f, f_ref = T.median_frac(runs), T.median_frac(ref)
    tol = 0.10 * abs(f_ref) if f_ref >= T.GAP_MODELS_MIN_FRAC else SMALL_GAP_DRIFT
    a, ra = S.med(S.values(runs, S.ACTIVE)), S.values(ref, S.ACTIVE)
    ok = abs(f - f_ref) <= tol and min(ra) * 0.995 <= a <= max(ra) * 1.005
    return "DRIFT_OK" if ok else "DRIFT"


def clock_scale(c2):
    """TA root-clock cycles per CPU (DWT) cycle over the inference window, from arm c2."""
    return S.med([r["ta_sram"] / r["infer_cpu"] for r in c2.values()]) if usable(c2, "c2") else None


def explained(c1, k):
    """Per C1 RUN: clock-off cycles of the adapter that counted more, in CPU cycles, over the gap; median."""
    return S.med([max(r["ta_sram"], r["ta_ext"]) / k / (r["infer_cpu"] - r["infer"]) for r in c1.values()])


def counted(c1, c2):
    k = clock_scale(c2)
    if not usable(c1, "c1") or k is None:
        return "UNPROVEN"
    e = explained(c1, k)
    if e > 1.10:
        return "CLOCK_STOP_EXCEEDS"
    if e >= 0.90:
        return "CLOCK_STOP_MATCHES"
    return "CLOCK_STOP_PARTIAL" if e >= 0.10 else "CLOCK_STOP_ABSENT"


def mode0(ref, d):
    if not usable(d, "d"):
        return "UNPROVEN"
    v = T.model_verdict(ref, d)
    return {"TA_REMOVES_GAP": "MODE0_REMOVES_GAP", "TA_REDUCES_GAP": "MODE0_REDUCES_GAP",
            "TA_NO_EFFECT": "MODE0_NO_EFFECT"}.get(v, v)


def model_verdicts(ref, c1, c2, d):
    """(2c, 2d, drift); (None, None, drift) for a model without a profile-1 gap. A drifted c1 or c2 -> UNPROVEN."""
    dr = "DRIFT_OK" if drift(c1, ref, "c1") == drift(c2, ref, "c2") == "DRIFT_OK" else "DRIFT"
    if T.usable(ref) and T.median_frac(ref) < T.GAP_MODELS_MIN_FRAC:
        return None, None, dr
    if dr != "DRIFT_OK":
        return "UNPROVEN", "UNPROVEN", dr
    return counted(c1, c2), mode0(ref, d), dr


def overall(pairs):
    flat = [v for p in pairs for v in p]
    if not pairs or "UNPROVEN" in flat:
        return "UNPROVEN"
    if all(p == ("CLOCK_STOP_MATCHES", "MODE0_REMOVES_GAP") for p in pairs):
        return "CAUSE_CONFIRMED"
    if all(p == ("CLOCK_STOP_ABSENT", "MODE0_NO_EFFECT") for p in pairs):
        return "CAUSE_REJECTED"
    return "MIXED"


def describe(runs):
    if not runs:
        return {}
    out = T.describe(runs)
    out.update(ta_sram=S.med([r.get("ta_sram") for r in runs.values()]),
               ta_ext=S.med([r.get("ta_ext") for r in runs.values()]))
    return out


def main(s013_root, root, out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(root)
    models = sorted(d.name for d in pathlib.Path(s013_root).glob("*/*") if (d / "runs.csv").exists())
    rows, desc = [], []
    for m in models:
        ref = S.load_runs(T.find(s013_root, m), WARMUP)
        arms = {a: load(root / a / m) for a in ("c1", "c2", "d")}
        v2c, v2d, dr = model_verdicts(ref, arms["c1"], arms["c2"], arms["d"])
        k = clock_scale(arms["c2"])
        gap_model = v2c not in (None, "UNPROVEN")   # e divides by the gap: models without one are descriptive
        e = explained(arms["c1"], k) if gap_model and k and usable(arms["c1"], "c1") else None
        rows.append(dict(model=m, drift=dr, clock_stop=v2c or "DESCRIPTIVE_ONLY", mode0=v2d or "DESCRIPTIVE_ONLY",
                         root_per_cpu_cycle=k, clock_off_over_gap=e))
        desc.append(dict(model=m, arm="s013 (profile 1)", **describe(ref)))
        desc += [dict(model=m, arm=a, **describe(r)) for a, r in arms.items() if r]
    pairs = [(r["clock_stop"], r["mode0"]) for r in rows if r["clock_stop"] != "DESCRIPTIVE_ONLY"]
    res = dict(overall=overall(pairs), models=rows)
    for name, rs in (("verdicts", rows), ("describe", desc)):
        keys = list(dict.fromkeys(k for r in rs for k in r))
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rs)
    json.dump(res, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
