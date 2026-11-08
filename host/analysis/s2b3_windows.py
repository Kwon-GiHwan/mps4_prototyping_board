#!/usr/bin/env python3
"""Stage 2B-3 Phase 3a pilot: where the MAC activity of a reference op A falls among single-op PMU mask windows
(evidence/s2b3_pilot/contract.md). TA profile 1.

  python3 host/analysis/s2b3_windows.py <root> <timeline dir> <out dir>

<root>/<arm>/<model>, arms: ctl, ctl2 (no mask, A/A), w_prev, w_A, w_B, w_next (W(k) = cms.gate(stream, k, k+1) for
k = A-1, A, A+1 = B, A+2), u (A-1 .. A+2 in one window), optional w_A_wait / w_B_wait (opening moved past the last
DMA_WAIT/KERNEL_WAIT in that op's setup). Sets from the RUNs; mac_active (48) of set A drives the diagnosis.

Diagnosis (median of measured RUNs, M_k = mac_active of W(A+k), S = A's fewest MAC cycles at the TRM peak):
  T = Σ M_k < S                              -> NOT_IDENTIFIABLE (A's minimum is not inside the four windows)
  exactly one k with M_k >= S and T - M_k < S -> WINDOW_LOCALIZED(k)   (only that window can hold A's minimum)
  no k with M_k >= S                         -> WINDOW_SPLIT
  otherwise                                  -> WINDOW_AMBIGUOUS
A diagnosis says where activity concentrates, not that it is A's: it never establishes attribution.
Statically NOT_IDENTIFIABLE (before data) if S <= the largest fewest-cycles of the other three ops.
Repeated per measured RUN (RUNs paired by rep); any RUN with another diagnosis -> UNSTABLE.
Preconditions, else UNPROVEN: every RUN valid; A/A (ctl2 = ctl within the 2B-0b tolerance, every key of every set
plus NPU and CPU cycles); no disturbance (each masked arm's CPU inference cycles = ctl within tolerance); every
masked arm's OFM comparison (mismatch count, max abs diff) equal to ctl's in every RUN.
"""
import csv, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fi101_s013 as S  # noqa: E402
import s2_mask_confirm as M  # noqa: E402
import s2b3_existing as X  # noqa: E402
import s2b3_select as SEL  # noqa: E402

WARMUP, SET_A, MAC_ACTIVE = 2, 1, 48
WINDOWS = {-1: "w_prev", 0: "w_A", 1: "w_B", 2: "w_next"}
MASKED = tuple(WINDOWS.values()) + ("u", "w_A_wait", "w_B_wait")
NPU, CPU = "npu", "cpu"


def series(runs, key):
    """key = (set, event) or (set, NPU) / (set, CPU)."""
    s, e = key
    pick = {NPU: lambda r: r["infer"], CPU: lambda r: r["infer_cpu"]}.get(e, lambda r: r["ev"].get(e))
    return [v for (ss, _), r in sorted(runs.items()) if ss == s for v in [pick(r)] if v is not None]


def keys(runs):
    out = {(s, e) for (s, _), r in runs.items() for e in r["ev"]}
    return sorted(out | {(s, k) for s, _ in out for k in (NPU, CPU)}, key=str)


def diagnose(m, s):
    """m: {offset: mac_active} for the four windows; s: A's fewest MAC cycles."""
    t = sum(m.values())
    if t < s:
        return "NOT_IDENTIFIABLE", None
    cand = [k for k, v in m.items() if v >= s]
    if len(cand) == 1 and t - m[cand[0]] < s:
        return "WINDOW_LOCALIZED", cand[0]
    if not cand:
        return "WINDOW_SPLIT", None
    return "WINDOW_AMBIGUOUS", None


def identifiable(cycles):
    """cycles: {offset: fewest MAC cycles of op A+offset}."""
    return cycles[0] > max(v for k, v in cycles.items() if k != 0)


def per_run(arms):
    """{rep: {offset: mac_active}} for reps measured in every window arm."""
    vals = {k: {rep: r["ev"].get(MAC_ACTIVE) for (s, rep), r in arms[a].items() if s == SET_A}
            for k, a in WINDOWS.items()}
    reps = set.intersection(*(set(v) for v in vals.values()))
    return {rep: {k: vals[k][rep] for k in WINDOWS} for rep in sorted(reps)
            if all(vals[k][rep] is not None for k in WINDOWS)}


def preconditions(arms, ofm):
    """-> reason or None. arms: {arm: runs}; ofm: {arm: set of (count, max diff)}."""
    need = ("ctl", "ctl2") + tuple(WINDOWS.values()) + ("u",)
    if not all(arms.get(a) and all(r["valid"] for r in arms[a].values()) for a in need):
        return "missing or invalid boot"
    if any(not all(r["valid"] for r in arms[a].values()) for a in arms):
        return "invalid RUN"
    ctl = arms["ctl"]
    ws = {k: M.width(series(ctl, k)) for k in keys(ctl)}
    judged = {k: w for k, w in ws.items() if M.klass(w) in ("DETERMINISTIC", "JITTERY")}
    if any(not series(arms["ctl2"], k) for k in judged):
        return "a key of the control missing in ctl2"
    if not all(M.close(S.med(series(arms["ctl2"], k)), S.med(series(ctl, k)), M.tol_pass(w)) for k, w in judged.items()):
        return "A/A: ctl2 differs from ctl"
    cpu = (SET_A, CPU)
    if cpu not in judged:
        return "CPU cycles missing or too noisy"
    for a in arms:
        if a in MASKED and not M.close(S.med(series(arms[a], cpu)), S.med(series(ctl, cpu)), M.tol_pass(judged[cpu])):
            return f"disturbance: {a} CPU inference cycles differ from ctl"
    if len(ofm.get("ctl", ())) != 1 or any(ofm.get(a) != ofm["ctl"] for a in arms):
        return "OFM comparison differs from ctl"
    return None


def model_result(arms, ofm, cycles):
    """cycles: {offset: fewest MAC cycles} for ops A-1 .. A+2 -> (verdict, offset or None, details)."""
    if not identifiable(cycles):
        return "NOT_IDENTIFIABLE", None, dict(reason="static: A's fewest cycles not above its neighbours'")
    why = preconditions(arms, ofm)
    if why:
        return "UNPROVEN", None, dict(reason=why)
    med = {k: S.med(series(arms[a], (SET_A, MAC_ACTIVE))) for k, a in WINDOWS.items()}
    d = diagnose(med, cycles[0])
    runs = [diagnose(m, cycles[0]) for m in per_run(arms).values()]
    if not runs or any(r != d for r in runs):
        return "UNSTABLE", None, dict(median=d, per_run=runs)
    return d[0], d[1], dict(mac_active=med)


def ofm_signatures(folder):
    """{(set, rep): (mismatch count, max abs diff)} of measured RUNs -> set of distinct signatures."""
    out = {}
    for r in csv.DictReader(open(folder / "runs.csv")):
        if int(r["rep"]) > WARMUP:
            out[(r["set_id"], r["rep"])] = (r["ofm_mismatch_count"], r["ofm_max_abs_diff"])
    return set(out.values())


def main(root, timeline_dir, out):
    root, out = pathlib.Path(root), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res, rows = {}, []
    for d in sorted((root / "ctl").glob("*")):
        m = d.name
        ops = list(csv.DictReader(open(pathlib.Path(timeline_dir) / f"{m}.csv")))
        a, _, _ = SEL.select([int(r["macs"]) for r in ops])
        cycles = {k: X.min_cycles(ops[a + k]) for k in WINDOWS}
        present = [p for p in sorted(root.iterdir()) if (p / m / "runs.csv").exists()]
        arms = {p.name: S.load_runs(p / m, WARMUP) for p in present}
        ofm = {p.name: ofm_signatures(p / m) for p in present}
        v, k, det = model_result(arms, ofm, cycles)
        res[m] = dict(verdict=v, offset=k, A=a, B=a + 1, fewest_cycles=cycles, **det)
        for arm, runs in arms.items():
            for key in keys(runs):
                rows.append(dict(model=m, arm=arm, set=key[0], key=key[1], median=S.med(series(runs, key)),
                                 width=M.width(series(runs, key))))
    with open(out / "windows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    json.dump(res, open(out / "summary.json", "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:4])
