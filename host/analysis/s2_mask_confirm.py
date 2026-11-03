#!/usr/bin/env python3
"""Stage 2B-0b: NPU_OP_PMU_MASK confirmation with a jitter-aware criterion (evidence/s2_mask/contract.md).

  python3 host/analysis/s2_mask_confirm.py <root> <out dir>

<root>/<arm>/<model> for arms ctl, ctl2 (the same blob, a second boot after the masked ones: A/A), m_all, m_a, m_b
(set A). The tolerance of each event is the RUN-to-RUN range of the first control boot alone; ctl2 must meet it
against ctl, or the boot-to-boot drift is larger than the criterion can see and the model is UNPROVEN.
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402

WARMUP = 2
DET_MAX, FLOOR, NOISY_MIN = 0.001, 0.01, 0.05
ARMS = ("ctl", "ctl2", "m_all", "m_a", "m_b")
NPU = "infer"                     # NPU PMCCNTR inference window, judged with the events in passthrough only


def series(runs, key):
    """Values of one event (or NPU cycles) over a list of RUNs."""
    if key == NPU:
        return [r["infer"] for r in runs if r["infer"] is not None]
    return [r["ev"][key] for r in runs if r["ev"].get(key) is not None]


def width(xs):
    """(max - min) / median of the control's RUNs; 0 for an all-zero event, inf if the median is 0 otherwise."""
    m = S.med(xs)
    if not xs or m is None:
        return None
    if m == 0:
        return 0.0 if max(xs) == 0 else float("inf")
    return (max(xs) - min(xs)) / m


def klass(w):
    if w is None:
        return "MISSING"
    return "DETERMINISTIC" if w <= DET_MAX else "NOISY" if w > NOISY_MIN else "JITTERY"


def close(x, ref, tol):
    return x == 0 if ref == 0 else abs(x - ref) <= tol * ref


def tol_pass(w):
    """Passthrough tolerance: an event fixed by the command stream must stay fixed; a jittery one may move as far as
    the control moves by itself, at least 1 %."""
    return DET_MAX if w <= DET_MAX else max(FLOOR, w)


def event_table(ctl):
    keys = sorted({e for r in ctl for e in r["ev"]}) + [NPU]
    return {k: width(series(ctl, k)) for k in keys}


def aa(ctl, ctl2, ws):
    """The control against itself (two boots): every judged key must pass the passthrough rule."""
    return all(close(S.med(series(ctl2, k)), S.med(series(ctl, k)), tol_pass(w))
               for k, w in ws.items() if klass(w) in ("DETERMINISTIC", "JITTERY"))


def passthrough(m_all, ctl, ws):
    return all(close(S.med(series(m_all, k)), S.med(series(ctl, k)), tol_pass(w))
               for k, w in ws.items() if klass(w) in ("DETERMINISTIC", "JITTERY"))


def additive(m_a, m_b, m_all, ws):
    """Per event (not NPU cycles): median(m_a) + median(m_b) = median(m_all) within max(1 %, the control's width)."""
    out = True
    for k, w in ws.items():
        if k == NPU or klass(w) not in ("DETERMINISTIC", "JITTERY"):
            continue
        a, b = S.med(series(m_a, k)), S.med(series(m_b, k))
        out = out and close(a + b, S.med(series(m_all, k)), max(FLOOR, w))
    return out


def valid(runs):
    return bool(runs) and all(r["valid"] for r in runs)


def model_verdict(arm):
    """arm: {name: [RUN, ...]} -> (verdict, details)."""
    if not all(valid(arm.get(a, [])) for a in ARMS):
        return "UNPROVEN", dict(reason="missing or invalid boot")
    ws = event_table(arm["ctl"])
    if klass(ws[NPU]) not in ("DETERMINISTIC", "JITTERY"):
        return "UNPROVEN", dict(reason="NPU cycles missing or too noisy", widths=ws)
    if not all(series(arm[a], k) for a in ARMS for k in ws):
        return "UNPROVEN", dict(reason="an event of the control missing in another arm", widths=ws)
    d = dict(widths=ws, aa=aa(arm["ctl"], arm["ctl2"], ws),
             noisy=[k for k, w in ws.items() if klass(w) == "NOISY"])
    if not d["aa"]:
        return "UNPROVEN", dict(d, reason="control fails against itself")
    d.update(passthrough=passthrough(arm["m_all"], arm["ctl"], ws),
             additive=additive(arm["m_a"], arm["m_b"], arm["m_all"], ws))
    if not d["passthrough"]:
        return "MASK_DISTURBS", d
    return ("MASK_WORKS" if d["additive"] else "MASK_NOT_ADDITIVE"), d


def overall(vs):
    if not vs or "UNPROVEN" in vs:
        return "UNPROVEN"
    for v in ("MASK_DISTURBS", "MASK_NOT_ADDITIVE"):
        if v in vs:
            return v
    return "MASK_WORKS"


def load(d):
    return list(S.load_runs(d, WARMUP).values()) if (d / "runs.csv").exists() else []


def main(root, out):
    root, out = pathlib.Path(root), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows, verdicts = [], {}
    for d in sorted((root / "ctl").glob("*")):
        m = d.name
        arm = {a: load(root / a / m) for a in ARMS}
        v, det = model_verdict(arm)
        verdicts[m] = dict(verdict=v, **{k: det[k] for k in ("aa", "passthrough", "additive", "noisy", "reason")
                                         if k in det})
        for k, w in det.get("widths", {}).items():
            row = dict(model=m, key=k, ctl_width=w, cls=klass(w))
            for a in ARMS:
                row[a] = S.med(series(arm[a], k))
            if None not in (row["m_a"], row["m_b"]):
                row["m_a_plus_m_b"] = row["m_a"] + row["m_b"]
            rows.append(row)
    res = dict(overall=overall([x["verdict"] for x in verdicts.values()]), models=verdicts)
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(out / "mask_confirm.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    json.dump(res, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
