#!/usr/bin/env python3
"""FINAL POLISHING PASS checks A-G.

A-F close MOD-1, MOD-2, MIN-1, MIN-2 and pin the three delta semantics so the
MOD-2 defect cannot silently return. G, added for NEW-1, requires every
main-text figure to carry at least one explicit PROSE reference: a caption or an
image insertion containing "Figure X" does not satisfy it. Runs on top of the
existing suites, which it does not duplicate.
"""
import json
import os
import re
import sys

from manuscript_text import Manuscript

REVIEW = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(REVIEW)
DEFAULT = os.path.join(PAPER, "MANUSCRIPT.md")

WHOLE_MODEL_DELTA = 19000     # 7.1, uninstrumented: 36,086 -> 55,086
PROFILED_GROUP_SUM = 19060    # frozen U85_GROUP_DIFFERENTIAL.csv, rnnoise B-frozen
RESIDUAL = PROFILED_GROUP_SUM - WHOLE_MODEL_DELTA


def main(path=DEFAULT):
    m = Manuscript.load(path)
    raw = m.raw
    fails, notes = [], {}

    def check(tag, name, ok, detail=""):
        notes["%s %s" % (tag, name)] = (("PASS" if ok else "FAIL")
                                        + (" — " + detail if detail else ""))
        if not ok:
            fails.append("%s %s: %s" % (tag, name, detail))

    # ---- A. figures first appear in order 1,2,3,4,5 ---------------------
    captions = re.findall(r"\*\*Figure (\d)\.\*\*", raw)
    check("A", "captions appear in order 1..5",
          captions == ["1", "2", "3", "4", "5"], str(captions))
    embeds = re.findall(r"figures/(fig\d)_", raw)
    check("A", "embedded files appear in numeric order",
          embeds == ["fig%d" % i for i in range(1, 6)], str(embeds))
    check("A", "each figure embedded exactly once",
          len(embeds) == len(set(embeds)) == 5, str(embeds))
    # the file each caption follows must carry that caption's number
    pairs = re.findall(r"figures/(fig(\d))_[a-z0-9_]+\.svg\)\s*\n\s*\n\*\*Figure (\d)\.",  # filenames contain digits (u85)
                       raw)
    check("A", "each caption number matches its file number",
          len(pairs) == 5 and all(p[1] == p[2] for p in pairs),
          str([(p[0], p[2]) for p in pairs]))

    # ---- G. every figure carries a prose reference (NEW-1) ---------------
    # Strip the two places "Figure X" occurs structurally rather than as prose:
    # the image insertion (alt text) and the caption block. What remains is
    # running text, so a caption alone can never satisfy this check.
    prose_only = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)
    prose_only = re.sub(r"\*\*Figure \d\.\*\*[^\n]*(\n(?!\n)[^\n]*)*", "",
                        prose_only)
    referenced = {int(x) for x in re.findall(r"Figure (\d)", prose_only)}
    for i in range(1, 6):
        check("G", "Figure %d has an explicit prose reference" % i,
              i in referenced, "only caption/insertion found")
    check("G", "all five figures referenced in prose",
          referenced >= {1, 2, 3, 4, 5}, "referenced=%s" % sorted(referenced))
    # the stripping must be real: captions alone must NOT satisfy the rule
    caption_only = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)
    check("G", "caption text is excluded from the prose set",
          "**Figure 1.**" in caption_only and "**Figure 1.**" not in prose_only,
          "caption stripping is not working")
    # a prose reference must sit outside any caption block
    for i in (2, 4, 5):
        check("G", "Figure %d prose reference is a real sentence" % i,
              bool(re.search(r"Figure %d (shows|summarizes|gives|reports)" % i,
                             prose_only)),
              "must explain the figure's role, not merely 'See Figure X'")
    check("G", "no bare 'See Figure X' reference",
          not re.search(r"(?<![a-zA-Z])See Figure \d\.?\s*$", prose_only, re.M))

    # ---- B. every Figure reference resolves ------------------------------
    refs = {int(x) for x in re.findall(r"Figure (\d)", raw)}
    check("B", "every Figure reference resolves to an existing figure",
          refs <= {1, 2, 3, 4, 5}, "referenced=%s" % sorted(refs))
    check("B", "no stale figure number beyond the set",
          not re.search(r"Figure [6-9]", raw))
    on_disk = sorted(f for f in os.listdir(os.path.join(PAPER, "figures"))
                     if f.endswith(".svg"))
    check("B", "exactly five figure files on disk", len(on_disk) == 5, str(on_disk))
    for f in on_disk:
        check("B", "%s referenced by the manuscript" % f, ("figures/" + f) in raw)
    # old filenames must be gone from disk and text
    for stale in ("fig5_platform_sensitivity", "fig4_board_relative_cost",
                  "fig2_u85_group_delta", "fig3_u85_memory_robustness"):
        check("B", "stale filename %s absent" % stale,
              stale not in raw and not os.path.exists(
                  os.path.join(PAPER, "figures", stale + ".svg")))

    # ---- C. no "whole-model +19,060" claim remains -----------------------
    # The defect is EQUATING the two, not mentioning them together: the
    # reconciliation sentence and caption legitimately name both numbers in one
    # breath in order to distinguish them. So the rule fires only on an
    # equating construction with no distinguishing connective between the two.
    EQUATES = (r"whole-model\s+(?:observed\s+)?(?:change|delta)\s+"
               r"(?:is|was|=|of|:)\s*\+?19,?060")
    DISTINGUISHES = r"beside|against|versus|vs\.|rather than|not|residual"

    def equates_the_two(text):
        flat = re.sub(r"\s+", " ", text)
        out = []
        for mm in re.finditer(EQUATES, flat, re.I):
            span = flat[max(0, mm.start() - 60):mm.end() + 60]
            if not re.search(DISTINGUISHES, span, re.I):
                out.append(span)
        return out

    # mutation test: the rule must still fire on the sentence it was written for
    _defect = ("two platforms ... ten groups regress; "
               "the whole-model change is +19,060 cycles.")
    check("C", "rule still fires on the original MOD-2 defect",
          bool(equates_the_two(_defect)),
          "a check that cannot fail is worse than no check")
    check("C", "rule does not fire on the reconciliation sentence",
          not equates_the_two(
              "places the +19,000 whole-model observed delta beside the "
              "+19,060 profiled-group sum so that the 60-cycle residual "
              "between the two measurement boundaries stays visible"))
    check("C", "no whole-model +19,060 claim in the manuscript",
          not equates_the_two(raw), str(equates_the_two(raw)[:2]))
    figsvg = open(os.path.join(PAPER, "figures", "fig4_u85_group_delta.svg")).read()
    figtext = re.sub(r"<[^>]+>", " ", figsvg)
    figtext = re.sub(r"\s+", " ", figtext)
    check("C", "no whole-model +19,060 claim in the figure",
          not re.search(r"whole-model change is \+?19,?060", figtext, re.I),
          "")
    prov = json.load(open(os.path.join(PAPER, "figures", "FIGURE_PROVENANCE.json")))
    check("C", "no whole-model +19,060 claim in provenance",
          not re.search(r"whole-model[^.]{0,30}19,?060", json.dumps(prov), re.I))

    # ---- D. the three delta semantics are distinguished ------------------
    check("D", "whole-model delta stated as +19,000",
          m.has("whole-model observed delta is +19,000")
          or m.has("whole-model observed delta of +19,000"),
          "")
    check("D", "profiled-group delta stated as +19,060",
          m.has("reconstructed profiled-group delta is +19,060")
          or m.has("profiled groups sum to +19,060"))
    check("D", "residual stated as 60 with scoped wording",
          m.has("60-cycle residual") or m.has("residual of 60 cycles"))
    check("D", "residual wording is the frozen scoped one",
          m.has("deterministic profiling-boundary") and m.has("interrupt-service"),
          "must not assert a stronger causal model")
    check("D", "arithmetic holds", PROFILED_GROUP_SUM - WHOLE_MODEL_DELTA == RESIDUAL
          == 60, str(RESIDUAL))
    check("D", "figure shows all three quantities",
          all(t in figtext for t in ("whole-model observed delta",
                                     "reconstructed profiled-group delta",
                                     "residual", "+19,000", "+19,060")),
          "")
    check("D", "figure states the boundaries are not identical",
          "not identical" in figtext)
    check("D", "section 9.5 residual explanation retained",
          m.has("Each service boundary carries a small deterministic"))

    # ---- E. 468x used everywhere in current manuscript authority ---------
    check("E", "manuscript states 468x", m.has("span **468×**") or m.has("468×"))
    check("E", "no 467x anywhere in the manuscript", "467" not in raw,
          "the planning value may remain only in frozen historical documents")
    check("E", "workload estimate table present",
          m.has("Vela `cycles_total`") and m.has("| model | domain |"))
    check("E", "span basis configuration named",
          m.has("SSE-320 / ethos-u85-256 /") and m.has("Dedicated_Sram"))

    # ---- F. MIN-1 / MIN-2 closed ------------------------------------------
    secs = m.sections()
    three = sorted(k for k in secs if k.startswith("3."))
    check("F", "MIN-1: methodology has 3.1-3.6, no 3.7",
          three == ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"], str(three))
    check("F", "MIN-1: provenance moved to Appendix B",
          m.has("## Appendix B. Provenance and procedure"))
    check("F", "MIN-1: pointer left in Methodology",
          m.has("are set out in Appendix B"))
    for guard in ("model SHA → Vela artifact SHA",
                  "SOURCE_DATE_EPOCH",
                  "exactly equal",
                  "mutation tests proving"):
        check("F", "MIN-1: guard preserved — %s" % guard[:34], m.has(guard))
    meth = raw[raw.index("## 3. Methodology"):raw.index("## 4. ")]
    body = raw[raw.index("## 1. Introduction"):]
    share = 100.0 * len(meth.split()) / len(body.split())
    # asserted as a narrow band, not an open bound: the reported figure must be
    # the measured one. A first draft of the polishing record stated an
    # unobserved 16.2%; the measured value is 18.0%.
    check("F", "MIN-1: methodology share reduced and as reported",
          17.5 <= share <= 18.5 and len(meth.split()) == 1580,
          "%d words, %.1f%% of the body" % (len(meth.split()), share))
    check("F", "MIN-2: appendix A retitled",
          m.has("## Appendix A. Exact values behind the board validation"))
    check("F", "MIN-2: old narrow title gone",
          not m.has("Exact values behind Figure"))
    check("F", "MIN-2: appendix A still reachable from section 6",
          m.has("tabulated in Appendix A") or m.has("Appendix A gives the exact"))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    print("\nRESULT:", ("ALL %d PASS" % len(notes)) if not fails
          else "FAILED (%d of %d): %s" % (len(fails), len(notes), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
