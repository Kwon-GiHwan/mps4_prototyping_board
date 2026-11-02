#!/usr/bin/env python3
"""Stage 2A-F2 (PMCLUT: is a stall counted while its unit is active?) and Stage 2B-0 (NPU_OP_PMU_MASK gating)
verdicts (evidence/s2_probe/contract.md).

  python3 host/analysis/s2_probe.py <lut root> <mask root> <out dir>

<lut root>/lut_id/kws_micronet_m (LUT 0xCCCC = event 1), <lut root>/lut/<model> (LUT 0x8888 = event 0 AND event 1),
sets from <lut root>/ids.txt (copied there by run_campaign.sh); <mask root>/<arm>/<model> for arms ctl, m_all, m_none,
m_a, m_b (set A).
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import fi101_s013 as S  # noqa: E402

WARMUP = 2
CLOSE, BAND, ACTIVE_MIN, IDLE_MAX = 0.001, 0.01, 0.9, 0.1


def valid(runs):
    return bool(runs) and all(r["valid"] for r in runs.values())


def identity(runs, sets):
    """Counter 0 under a LUT selecting event 1 must equal event 1's own counter in the same RUN."""
    if not valid(runs):
        return "UNPROVEN"
    pairs = [(r["ev"][sets[s][0]], r["ev"][sets[s][1]]) for (s, _), r in runs.items()]
    if any(raw is None or raw == 0 for _, raw in pairs):
        return "UNPROVEN"
    if all(c == raw for c, raw in pairs):
        return "LUT_IDENTITY_EXACT"
    return "LUT_IDENTITY_CLOSE" if all(abs(c - raw) <= CLOSE * raw for c, raw in pairs) else "LUT_FAILS"


def overlap(runs, sets):
    """Per set: (class, median of composite(e0 AND e1) / raw e1)."""
    out = {}
    for s, codes in sets.items():
        rs = {k: r for k, r in runs.items() if k[0] == s}
        if not valid(rs):
            out[s] = ("UNPROVEN", None)
            continue
        raw = [r["ev"][codes[1]] for r in rs.values()]
        if all(x == 0 for x in raw):
            out[s] = ("COUNTED_ZERO", None)
            continue
        if any(x == 0 for x in raw):
            out[s] = ("INCONSISTENT", None)
            continue
        f = S.med([r["ev"][codes[0]] / r["ev"][codes[1]] for r in rs.values()])
        cls = "STALL_WHILE_ACTIVE" if f >= ACTIVE_MIN else "STALL_WHILE_IDLE" if f <= IDLE_MAX else "PARTLY_WHILE_ACTIVE"
        out[s] = (cls, f)
    return out


def gated(ov, lut_verdict):
    """Overlap classes stand only if the identity boot showed the LUT counts what it is told to."""
    if lut_verdict in ("LUT_IDENTITY_EXACT", "LUT_IDENTITY_CLOSE"):
        return ov
    return {s: ("UNPROVEN", None) for s in ov}


def _meds(runs, cycles=False):
    """Event medians; with cycles, also the NPU PMCCNTR inference window ('infer')."""
    evs = sorted({e for r in runs.values() for e in r["ev"]})
    out = {e: S.med([r["ev"][e] for r in runs.values() if e in r["ev"]]) for e in evs}
    if cycles:
        out["infer"] = S.med([r["infer"] for r in runs.values()])
    return out


def passthrough(m_all, ctl):
    """Mask enabled for the whole stream changes no event median and not the NPU cycles by more than 1 % against the
    unmasked control."""
    if not (valid(m_all) and valid(ctl)):
        return None
    a, c = _meds(m_all, True), _meds(ctl, True)
    return all(abs(a[e] - c[e]) <= BAND * c[e] for e in c)


def additive(m_a, m_b, m_all):
    """First part + second part = whole stream, per event median, within 1 % of the whole."""
    if not (valid(m_a) and valid(m_b) and valid(m_all)):
        return None
    a, b, t = _meds(m_a), _meds(m_b), _meds(m_all)
    return all(abs(a[e] + b[e] - t[e]) <= BAND * t[e] for e in t)


def default_state(m_none, ctl):
    if not (valid(m_none) and valid(ctl)):
        return "UNPROVEN"
    n, c = _meds(m_none), _meds(ctl)
    if all(n[e] == 0 for e in c):
        return "MASK_DEFAULT_OFF"
    if all(abs(n[e] - c[e]) <= BAND * c[e] for e in c):
        return "MASK_DEFAULT_ON"
    return "MASK_DEFAULT_OTHER"


def mask_verdict(passes, adds):
    if passes is None or adds is None:
        return "UNPROVEN"
    if not passes:
        return "MASK_DISTURBS"
    return "MASK_WORKS" if adds else "MASK_NOT_ADDITIVE"


def mask_overall(vs):
    if not vs or "UNPROVEN" in vs:
        return "UNPROVEN"
    for v in ("MASK_DISTURBS", "MASK_NOT_ADDITIVE"):
        if v in vs:
            return v
    return "MASK_WORKS"


def load(d):
    return S.load_runs(d, WARMUP) if (d / "runs.csv").exists() else {}


def sets_of(path):
    import pmu_events_parse as E
    _, sets = E.parse_ids_text(pathlib.Path(path).read_text())
    return {i + 1: s for i, s in enumerate(sets)}


def main(lut_root, mask_root, out):
    root, mroot, out = pathlib.Path(lut_root), pathlib.Path(mask_root), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lut_sets = sets_of(root / "ids.txt")
    lut_v = identity(load(root / "lut_id" / "kws_micronet_m"), lut_sets)
    ov_rows = []
    for d in sorted((root / "lut").glob("*")):
        if d.is_dir():
            for s, (cls, f) in gated(overlap(load(d), lut_sets), lut_v).items():
                ov_rows.append(dict(model=d.name, set=s, e0=lut_sets[s][0], e1=lut_sets[s][1], verdict=cls, fraction=f))
    mask_rows = []
    for d in sorted((mroot / "ctl").glob("*")):
        m = d.name
        arm = {a: load(mroot / a / m) for a in ("ctl", "m_all", "m_none", "m_a", "m_b")}
        p, ad = passthrough(arm["m_all"], arm["ctl"]), additive(arm["m_a"], arm["m_b"], arm["m_all"])
        mask_rows.append(dict(model=m, passthrough=p, additive=ad, verdict=mask_verdict(p, ad),
                              default=default_state(arm["m_none"], arm["ctl"]),
                              **{f"{a}_{k}": v for a in arm for k, v in _meds(arm[a], True).items()}))
    res = dict(lut_identity=lut_v, mask_overall=mask_overall([r["verdict"] for r in mask_rows]),
               mask=[{k: r[k] for k in ("model", "passthrough", "additive", "verdict", "default")} for r in mask_rows])
    for name, rs in (("lut_overlap", ov_rows), ("mask", mask_rows)):
        if rs:
            keys = list(dict.fromkeys(k for r in rs for k in r))
            with open(out / f"{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(rs)
    json.dump(res, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
