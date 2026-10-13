#!/usr/bin/env python3
"""X1 structural platform-sensitivity analyzer.

Frozen before formal acquisition (contract: X1_ANALYSIS_CONTRACT.md).
Reuses the paper's existing metric definitions verbatim; introduces no
aggregate robustness score and no new threshold. CLASS A and CLASS B are
computed and reported separately and can never be pooled.

Input: a JSON list of formal cells, each
  {workload, npu, mac, platform, ta_state, vela_artifact_sha256,
   axf_sha256, cycles, runs_exact_equal}
"""
import json
import math
import sys
from collections import defaultdict

STRONG, PARTIAL = 0.75, 0.50            # frozen class thresholds
SATURATION = 0.50                        # frozen saturation rule

CLASS_A = [("ethos-u65", "SSE-310", "SSE-315")]
CLASS_B = [("ethos-u55", "SSE-300", "SSE-310"),
           ("ethos-u65", "SSE-300", "SSE-310"),
           ("ethos-u65", "SSE-300", "SSE-315")]
TA = {"SSE-300": "TA_ON", "SSE-310": "TA_OFF", "SSE-315": "TA_OFF",
      "SSE-320": "TA_ON"}
EXPECTED_MACS = {"ethos-u55": [32, 64, 128, 256], "ethos-u65": [256, 512]}
# X0-frozen: wav2letter has no executable U55 cell below MAC 256
U55_UNAVAILABLE = {("wav2letter_pruned_int8", m) for m in (32, 64, 128)}


class Reject(Exception):
    pass


def validate(cells):
    """Fail-closed gates. Every rejection rule of the contract lives here."""
    for c in cells:
        if c["platform"] not in TA:
            raise Reject("unknown platform label: %s" % c["platform"])
        if c.get("ta_state") != TA[c["platform"]]:
            raise Reject("TA classification mismatch for %s: %s != %s"
                         % (c["platform"], c.get("ta_state"), TA[c["platform"]]))
        if not c.get("runs_exact_equal"):
            raise Reject("cell without exact-equal repetitions: %s" % c)
        if c["npu"] == "ethos-u55" and (c["workload"], c["mac"]) in U55_UNAVAILABLE:
            raise Reject("workload unavailable at this U55 MAC point: %s@%s"
                         % (c["workload"], c["mac"]))
    # artifact identity across each comparison set
    art = defaultdict(dict)
    for c in cells:
        art[(c["workload"], c["npu"], c["mac"])][c["platform"]] = \
            c["vela_artifact_sha256"]
    for key, pm in art.items():
        if len(set(pm.values())) > 1:
            raise Reject("artifact hash mismatch for %s: %s" % (key, pm))
    # MAC completeness per (platform, npu, workload)
    have = defaultdict(set)
    for c in cells:
        have[(c["platform"], c["npu"], c["workload"])].add(c["mac"])
    for (plat, npu, w), macs in have.items():
        want = {m for m in EXPECTED_MACS[npu]
                if not (npu == "ethos-u55" and (w, m) in U55_UNAVAILABLE)}
        if macs != want:
            raise Reject("missing MAC point for %s/%s/%s: have %s want %s"
                         % (plat, npu, w, sorted(macs), sorted(want)))
    return True


def spearman(a, b):
    n = len(a)
    if n < 2 or len(b) != n:
        raise Reject("spearman needs equal-length series of >= 2")
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return num / (da * db) if da and db else float("nan")


def cls(eff):
    if eff is None:
        return "NOT_AVAILABLE"
    return ("STRONG" if eff >= STRONG else
            "PARTIAL" if eff >= PARTIAL else "WEAK_OR_SATURATED")


def per_platform(cells):
    """Within-platform metrics only. Nothing here crosses a platform."""
    by = defaultdict(dict)
    for c in cells:
        by[(c["platform"], c["npu"])][(c["workload"], c["mac"])] = c["cycles"]
    out = {}
    for (plat, npu), d in by.items():
        macs = EXPECTED_MACS[npu]
        workloads = sorted({w for (w, _) in d})
        res = {"ranking": {}, "adjacent": {}, "cumulative": {},
               "classes": {}, "saturation": {}, "normalized": {}}
        for mac in macs:
            present = [(w, d[(w, mac)]) for w in workloads if (w, mac) in d]
            if len(present) >= 2:
                present.sort(key=lambda t: t[1])
                res["ranking"][mac] = [w for w, _ in present]
                vals = [v for _, v in present]
                g = math.exp(sum(math.log(v) for v in vals) / len(vals))
                res["normalized"][mac] = {w: round(v / g, 6) for w, v in present}
        for w in workloads:
            series = [(m, d[(w, m)]) for m in macs if (w, m) in d]
            if len(series) < 2:
                res["saturation"][w] = "NOT_AVAILABLE"
                continue
            m0, c0 = series[0]
            adj, cum, kl, sat = {}, {}, {}, "NONE_OBSERVED"
            for i in range(1, len(series)):
                mp, cp = series[i - 1]
                mi, ci = series[i]
                a = (cp / ci) / (mi / mp)
                adj[mi] = round(a, 6)
                cum[mi] = round((c0 / ci) / (mi / m0), 6)
                kl[mi] = cls(a)
                if a < SATURATION and sat == "NONE_OBSERVED":
                    sat = mi
            res["adjacent"][w] = adj
            res["cumulative"][w] = cum
            res["classes"][w] = kl
            res["saturation"][w] = sat
        out[(plat, npu)] = res
    return out


def compare(pp, npu, A, B, klass):
    """Structural agreement between two platforms of the same NPU."""
    a, b = pp.get((A, npu)), pp.get((B, npu))
    if a is None or b is None:
        raise Reject("missing platform data for %s/%s vs %s" % (npu, A, B))
    r = {"class": klass, "npu": npu, "platform_A": A, "platform_B": B,
         "ta_A": TA[A], "ta_B": TA[B], "ranking": {}, "step_direction": {},
         "scaling_class": {}, "saturation": {}, "normalized_order": {},
         "disagreements": []}
    for mac in sorted(set(a["ranking"]) & set(b["ranking"])):
        ra, rb = a["ranking"][mac], b["ranking"][mac]
        if set(ra) != set(rb):
            raise Reject("workload-pair mismatch at MAC %s" % mac)
        idx = {w: i for i, w in enumerate(rb)}
        rho = spearman(list(range(len(ra))), [idx[w] for w in ra])
        r["ranking"][mac] = {"identical_order": ra == rb, "spearman": round(rho, 6)}
        if ra != rb:
            r["disagreements"].append({"kind": "ranking", "mac": mac,
                                       "A": ra, "B": rb})
        na, nb = a["normalized"].get(mac, {}), b["normalized"].get(mac, {})
        oa = sorted(na, key=lambda w: na[w])
        ob = sorted(nb, key=lambda w: nb[w])
        r["normalized_order"][mac] = {"identical": oa == ob}
    for w in sorted(set(a["classes"]) & set(b["classes"])):
        ca, cb = a["classes"][w], b["classes"][w]
        aa, ab = a["adjacent"][w], b["adjacent"][w]
        steps = sorted(set(ca) & set(cb))
        same_dir, same_cls = [], []
        for m in steps:
            da = "IMPROVE" if aa[m] > 0 else "OTHER"
            db = "IMPROVE" if ab[m] > 0 else "OTHER"
            same_dir.append(da == db)
            same_cls.append(ca[m] == cb[m])
            if ca[m] != cb[m]:
                r["disagreements"].append({"kind": "scaling_class", "workload": w,
                                           "mac_step": m, "A": ca[m], "B": cb[m],
                                           "adjacent_A": aa[m], "adjacent_B": ab[m]})
        r["step_direction"][w] = {"steps": len(steps), "agree": sum(same_dir)}
        r["scaling_class"][w] = {"steps": len(steps), "agree": sum(same_cls)}
        sa, sb = a["saturation"][w], b["saturation"][w]
        r["saturation"][w] = {"A": sa, "B": sb, "agree": sa == sb}
        if sa != sb:
            r["disagreements"].append({"kind": "saturation", "workload": w,
                                       "A": sa, "B": sb})
    return r


def main(path, out):
    cells = json.load(open(path))
    validate(cells)
    pp = per_platform(cells)
    comps = [compare(pp, npu, A, B, "A") for npu, A, B in CLASS_A] + \
            [compare(pp, npu, A, B, "B") for npu, A, B in CLASS_B]
    # Q6: descriptive location of disagreements, never pooled into one rate
    q6 = {"CLASS_A_disagreements": sum(len(c["disagreements"])
                                       for c in comps if c["class"] == "A"),
          "CLASS_B_disagreements": sum(len(c["disagreements"])
                                       for c in comps if c["class"] == "B"),
          "note": "counts are reported per class; they are never combined into a "
                  "single platform-robustness rate, and carry no causal claim"}
    res = {"per_platform": {"%s|%s" % k: v for k, v in pp.items()},
           "comparisons": comps, "q6_location_of_disagreements": q6}
    json.dump(res, open(out, "w"), indent=1)
    print("comparisons:", len(comps),
          "| CLASS A disagreements:", q6["CLASS_A_disagreements"],
          "| CLASS B disagreements:", q6["CLASS_B_disagreements"])


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2])
    except Reject as e:
        print("REJECT:", e)
        sys.exit(2)
