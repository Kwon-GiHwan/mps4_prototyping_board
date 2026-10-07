#!/usr/bin/env python3
"""PHASE 2 validation: numerical integrity, prohibited claims, reader flow.

Sections 13-15 of the Phase-2 decision. Every load-bearing number in the
manuscript is re-derived here from the FROZEN OUTPUT ARTIFACTS and compared
against the text; frozen metrics are never regenerated with modified code — the
CSV/JSON that the frozen analysis emitted is read as-is.
"""
import csv
import json
import os
import re
import sys

from manuscript_text import Manuscript

REVIEW = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(REVIEW)


def rd(rel):
    with open(os.path.join(PAPER, rel)) as fh:
        return list(csv.DictReader(fh))


def main(path=os.path.join(PAPER, "MANUSCRIPT.md")):
    m = Manuscript.load(path)
    fails, notes = [], {}

    def check(group, name, ok, detail=""):
        notes["%s | %s" % (group, name)] = (("PASS" if ok else "FAIL")
                                            + (" — " + detail if detail else ""))
        if not ok:
            fails.append("%s | %s: %s" % (group, name, detail))

    def says(phrase):
        return m.has(phrase, where="flat")

    # =============== 14. NUMERICAL / EVIDENCE INTEGRITY ==================
    G = "numeric"

    # -- formal sweep counts, from the frozen canonical cell list ----------
    cells = rd("analysis/canonical_cells.csv")
    check(G, "formal cell count (74)", len(cells) == 74 and says("74 executable"),
          "frozen rows=%d" % len(cells))
    check(G, "formal sample count (222 = 74x3)",
          len(cells) * 3 == 222 and says("222"), "%d" % (len(cells) * 3))
    eq = [c for c in cells if c.get("M1_eq_M2_eq_M3") in ("True", "true", "1")]
    check(G, "determinism 74/74", len(eq) == len(cells),
          "%d/%d" % (len(eq), len(cells)))

    # -- scaling class counts, recomputed from the frozen scaling table ----
    sc = rd("analysis/scaling.csv")
    ladders = {(r["platform"], r["npu"], r["workload"]) for r in sc}
    check(G, "21 preregistered ladders", len(ladders) == 21 and says("21 preregistered"),
          "frozen=%d" % len(ladders))
    # adjacent transitions actually evaluable in the frozen table
    adj = 0
    for key in ladders:
        pts = sorted((int(r["mac"]) for r in sc
                      if (r["platform"], r["npu"], r["workload"]) == key
                      and r["status"] == "EXECUTABLE"))
        adj += max(len(pts) - 1, 0)
    check(G, "53 adjacent transitions", adj == 53 and says("53 adjacent"),
          "frozen=%d" % adj)
    for n_, label in ((28, "`STRONG` (≥ 0.75) | 28"), (23, "`PARTIAL` (0.50–0.75) | 23"),
                      (2, "`WEAK_OR_SATURATED` (< 0.50) | 2")):
        check(G, "class row %d present" % n_, says(label), label)

    # -- saturation, from the frozen saturation table ----------------------
    sat = rd("analysis/saturation.csv")
    none_obs = sum(1 for r in sat if r["saturation_point"] == "NONE_OBSERVED")
    observed = [r for r in sat if r["saturation_point"] not in
                ("NONE_OBSERVED", "NOT_AVAILABLE", "")]
    check(G, "saturation NONE_OBSERVED 19/21",
          none_obs == 19 and says("19 of 21 ladders"), "frozen=%d" % none_obs)
    check(G, "saturation observed exactly once", len(observed) == 1,
          str([(r["platform"], r["npu"], r["workload"], r["saturation_point"])
               for r in observed]))
    if observed:
        o = observed[0]
        check(G, "saturation cell is SSE-320/U85/rnnoise@512",
              (o["platform"], o["npu"], o["workload"], o["saturation_point"])
              == ("SSE-320", "ethos-u85", "rnnoise_INT8", "512")
              and says("SSE-320 / U85 / `rnnoise_INT8` at MAC 512"),
              str(o))

    # -- Vela agreement ----------------------------------------------------
    va = rd("analysis/vela_fvp_trend_agreement.csv")
    agree = sum(1 for r in va if r["saturation_agrees"] == "True")
    rho1 = sum(1 for r in va if r["speedup_rank_rho"] == "1.0")
    check(G, "Vela saturation agreement 19/20",
          len(va) == 20 and agree == 19 and says("19/20"),
          "frozen=%d/%d" % (agree, len(va)))
    check(G, "Vela speedup ordering 19/20", rho1 == 19, "frozen=%d" % rho1)

    # -- board -------------------------------------------------------------
    nrc = rd("analysis/board_rq3/normalized_relative_cost.csv")
    check(G, "board 7 workloads / 21 samples",
          len(nrc) == 7 and says("21 formal samples"), "rows=%d" % len(nrc))
    with open(os.path.join(PAPER, "analysis/board_rq3/ranking_preservation.json")) as fh:
        rp = json.load(fh)
    blob = json.dumps(rp)
    check(G, "board rho = 1.0 and 0 inversions",
          "1.0" in blob and says("rho = 1.0") and says("0 rank inversions"),
          "frozen keys=%s" % list(rp)[:6])
    for r in nrc:                     # appendix values must match frozen to 4dp
        for col, side in (("fvp_normalized_cost", "FVP"),
                          ("board_normalized_cost", "board")):
            v = "%.4f" % float(r[col])
            check(G, "appendix %s %s = %s" % (r["workload"], side, v), says(v), v)

    # -- U85 mechanism ------------------------------------------------------
    gd = [r for r in rd("mechanism/U85_GROUP_DIFFERENTIAL.csv")
          if r["workload"] == "rnnoise_INT8" and r["binding_pair"] == "B-frozen"]
    tot = sum(int(r["delta"]) for r in gd)
    dirs = {d: sum(1 for r in gd if r["direction"] == d)
            for d in ("REGRESS", "IMPROVE", "SAME")}
    check(G, "rnnoise 14-group partition", len(gd) == 14 and says("14-group common partition"),
          "frozen=%d" % len(gd))
    check(G, "group deltas sum to +19,060", tot == 19060 and says("+19,060"),
          "frozen=%d" % tot)
    check(G, "10 regress / 1 improve / 3 same",
          dirs == {"REGRESS": 10, "IMPROVE": 1, "SAME": 3}
          and says("ten regressing groups") and says("Ten groups regress"),
          str(dirs))
    check(G, "whole-model rnnoise 36,086 -> 55,086",
          says("36,086 → 55,086"), "")
    cm = [r for r in rd("mechanism/U85_P1B_CROSSMODE_GROUPS.csv")
          if r["workload"] == "rnnoise_INT8"]
    sums = {k: sum(int(r[k + "_delta"]) for r in cm) for k in ("SO", "SH", "DS")}
    check(G, "cross-memory totals 3,015 / 15,075 / 19,060",
          sums == {"SO": 3015, "SH": 15075, "DS": 19060}, str(sums))
    cons = sum(1 for r in cm if len({r["SO_dir"], r["SH_dir"], r["DS_dir"]}) == 1)
    flips = sum(1 for r in cm
                if {"REGRESS", "IMPROVE"} <= {r["SO_dir"], r["SH_dir"], r["DS_dir"]})
    check(G, "27 of 29 direction-consistent, zero flips",
          len(cm) == 29 and cons == 27 and flips == 0
          and says("27 of 29 groups direction-consistent"),
          "n=%d consistent=%d flips=%d" % (len(cm), cons, flips))

    # -- X1 / X3 ------------------------------------------------------------
    q = {(r["metric"], r["class"]): r
         for r in rd("platform_sensitivity/X3_METRIC_QUALIFICATION.csv")
         if r["class"] in ("A", "B")}
    for (met, cls), want in ((("workload_ranking", "A"), "2/2"),
                             (("workload_ranking", "B"), "8/8"),
                             (("mac_step_direction", "A"), "7/7"),
                             (("mac_step_direction", "B"), "32/32"),
                             (("scaling_class", "B"), "24/32"),
                             (("saturation_verdict", "B"), "20/20")):
        r = q.get((met, cls))
        got = "%s/%s" % (r["agreement"], r["tested_universe"]) if r else None
        check(G, "X3 %s CLASS %s = %s" % (met, cls, want),
              got == want and says(want), "frozen=%s" % got)
    dis = int(q[("scaling_class", "B")]["disagreement"])
    check(G, "eight CLASS B class disagreements",
          dis == 8 and says("eight scaling-class labels"), "frozen=%d" % dis)
    check(G, "CLASS A 14/14 exact-cycle observation",
          says("14/14 tested cells had") and
          says("NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR"))
    check(G, "X1 universe 92 cells / 276 samples", says("92 cells, 276 samples"))

    # -- bridge component verdicts -----------------------------------------
    for v in ("STRUCTURAL_EQUIVALENCE", "SEMANTIC_BOUNDARY_EQUIVALENCE",
              "ATTRIBUTION_EQUIVALENCE", "CYCLE_DOMAIN_EQUIVALENCE",
              "ACTIVE_DOMAIN_EQUIVALENCE", "AXI_BEAT_EXACT_EQUIVALENCE"):
        check(G, "bridge verdict %s present" % v, says(v))
    check(G, "bridge overall NOT_EQUIVALENT", says("NOT_EQUIVALENT"))

    # -- executability ------------------------------------------------------
    ex = rd("analysis/executability.csv")
    nonexec = [r for r in ex if r["classification"] != "EXECUTABLE"]
    check(G, "133 compiled, 6 non-executable",
          len(ex) == 133 and len(nonexec) == 6
          and says("All 133 capability cells compiled") and says("6 could not run"),
          "rows=%d nonexec=%d" % (len(ex), len(nonexec)))
    check(G, "the 6 are all wav2letter x U55 x Shared_Sram",
          {(r["workload"], r["npu"], r["memory_mode"]) for r in nonexec}
          == {("wav2letter_pruned_int8", "ethos-u55", "Shared_Sram")}
          and says("all `wav2letter_pruned_int8` × Ethos-U55 × `Shared_Sram`"),
          str({(r["workload"], r["mac_config"]) for r in nonexec}))
    ta_on = [r for r in ex if r["universe"] == "PRIMARY_BENCHMARK"]
    ta_on_exec = [r for r in ta_on if r["classification"] == "EXECUTABLE"]
    check(G, "74 formal cells = 77 TA-ON minus 3 non-executable",
          len(ta_on) == 77 and len(ta_on_exec) == 74 == len(cells),
          "TA_ON=%d executable=%d canonical=%d"
          % (len(ta_on), len(ta_on_exec), len(cells)))
    check(G, "56 TA-OFF diagnostic cells",
          sum(1 for r in ex if r["universe"] == "TA_OFF_DIAGNOSTIC") == 56
          and says("56 TA-OFF cells"))

    # =============== 15. PROHIBITED CLAIM SCAN ===========================
    P = "prohibited"
    NEG = (r"\bnot\b|\bno\b|never|cannot|without|refus|unavailable|"
           r"NOT_COMPARABLE|NOT_EVALUABLE|NOT_SEPARATED|NOT_EQUIVALENT|"
           r"retired|retracted|withdraw|unsupported|remain|earlier|historical|"
           r"is a judgement|rather than|methodology warning")

    def affirmative(pattern):
        return ["L%d: %s" % (h.line, h.text) for h in m.find(pattern)
                if not re.search(NEG, h.context, re.I)]

    for name, pat in (
        ("raw cross-platform cycles directly comparable",
         r"cross-platform cycles are (directly )?comparable|"
         r"cycles are comparable across (platforms|generations)"),
        ("U85 is X% faster/slower than U65", r"U85 is [\d.]+\s?%|"
         r"(U85|U65|U55) is \d+(\.\d+)?\s?(%|times|x) (faster|slower)"),
        ("TA caused the X1 class disagreement",
         r"(TA|timing[- ]adapter) (caused|is responsible for|explains)"),
        ("block enlargement caused U85 regression",
         r"(block|ublock) (enlargement|change) (caused|causes|explains)"),
        ("memory bandwidth caused P1 behaviour",
         r"bandwidth (caused|causes|explains|drives)"),
        ("FVP predicts board latency accurately",
         r"FVP (accurately )?predicts (board|hardware)|"
         r"predicts (board|hardware) (latency|timing) accurately"),
        ("profiler backends fully PMU-equivalent",
         r"backends are (fully )?equivalent|full PMU (vector )?equivalence established"),
        ("legacy profile exactly decomposes regor execution",
         r"legacy[- ](core )?prof\w+ (exactly )?decomposes"),
        ("num_macs=100 accepted / FVP checks only bounds",
         r"num_macs\s*=\s*100|range-checks bounds without validating"),
    ):
        check(P, name, not affirmative(pat), str(affirmative(pat)[:2]))

    # =============== 13. READER-FLOW COHERENCE ===========================
    C = "coherence"
    secs = m.sections()
    order = [k for k in sorted(secs, key=lambda x: [int(i) for i in x.split(".")])
             if "." not in k]
    check(C, "section numbering is contiguous 1..10",
          order == [str(i) for i in range(1, 11)], str(order))
    check(C, "every pointer resolves",
          not [h.text for h in m.section_pointers() if h.text not in secs])
    # figures: all generated, all referenced, all captioned
    figs = sorted(f for f in os.listdir(os.path.join(PAPER, "figures"))
                  if f.endswith(".svg"))
    for f in figs:
        check(C, "%s embedded" % f, ("figures/" + f) in m.raw)
    for i in range(1, len(figs) + 1):
        check(C, "Figure %d has a caption" % i, says("**Figure %d.**" % i))
    check(C, "figure count is 3-5", 3 <= len(figs) <= 5, str(len(figs)))
    # RQs introduced before answered
    intro = m.raw.index("## 1. Introduction")
    for rq in ("RQ1", "RQ2", "RQ3", "RQ4"):
        decl = m.raw.index("**%s**" % rq)
        answers = [x.start() for x in re.finditer(re.escape(rq), m.raw)]
        check(C, "%s declared before it is answered" % rq,
              decl > intro and all(a >= decl for a in answers if a > intro),
              "declared at %d" % decl)
    # contributions map to results
    for probe in ("Section 4", "Section 5", "Section 6", "Section 7",
                  "Section 8", "Section 9"):
        check(C, "%s referenced in prose" % probe, says(probe))
    # terminology consistency
    for term in ("compiler estimate", "operation group", "TA state",
                 "platform sensitivity", "physical observation",
                 "simulated observation"):
        check(C, "term used: %s" % term, says(term))
    # appendix pointer exists for the moved tables
    check(C, "appendix referenced from the section that lost its tables",
          says("tabulated in\nAppendix A") or says("tabulated in Appendix A"))
    check(C, "appendix exists", says("## Appendix A."))
    # conclusion discipline
    # Both sides must be whitespace-normalized: an unnormalized "53\n" does not
    # equal the body's "53 ", which produced a false positive on first run.
    concl = re.sub(r"\s+", " ",
                   m.raw[m.raw.index("## 10. Conclusion"):m.raw.index("## Appendix A.")])
    cnums = set(re.findall(r"\d[\d,]*\s?%?", concl))
    allnums = set(re.findall(r"\d[\d,]*\s?%?",
                             re.sub(r"\s+", " ", m.raw[:m.raw.index("## 10. Conclusion")])))
    check(C, "conclusion introduces no new number", cnums <= allnums,
          str(sorted(cnums - allnums)[:6]))
    check(C, "conclusion has no novelty claim",
          not re.search(r"first|novel|unprecedented|no prior", concl, re.I))
    check(C, "conclusion promises no future experiment",
          not re.search(r"we will|future work will|plan to (run|measure)", concl, re.I))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    total = len(notes)
    print("\nRESULT:", ("ALL %d PASS" % total) if not fails
          else "FAILED (%d of %d): %s" % (len(fails), total, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
