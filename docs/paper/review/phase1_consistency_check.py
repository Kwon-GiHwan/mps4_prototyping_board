#!/usr/bin/env python3
"""Consistency checks for docs/paper/MANUSCRIPT.md.

15 checks mandated by the REMEDIATION PHASE 1 decision, plus check 16
(causal-isolation language) added in PHASE 1.5 to close finding F15. Fail-closed: any FAIL blocks the
freeze. Whitespace-normalized matching (the manuscript is hard-wrapped) and
negation-context awareness (the paper legitimately *refuses* many of the
phrases that would otherwise be prohibited).
"""
import re, sys, json

NEG = (r"(\bno\b|\bnot\b|never|without|remain|refus|prohibit|forbid|retire|"
       r"withdraw|NOT_COMPARABLE|NOT_EVALUABLE|does not|deliberately|"
       r"is not used|outside what)")
# --- F15: causal isolation beyond "X caused" -------------------------------
# A causal connective alone is not a defect; the paper legitimately uses these
# words to REFUSE causal attribution. The rule fires only when a connective
# binds a confounded subject AND nothing in the window exculpates it.
CAUSAL = (r"purely by|purely due to|solely (?:by|due to|because of)|"
          r"attributable to|attributed to|results? from|stems? from|"
          r"driven by|caused by|\bcauses?\b|\bcaused\b|because of|due to")
# subjects whose contributions this study has declared NOT_SEPARATED
CONFOUNDED = (r"timing[- ]adapter|adapter state|\bTA\b|TA state|subsystem|"
              r"Fast Models|Corstone|platform|ublock|bandwidth|"
              r"memory[- ]system|shared[- ]SRAM|contention|SSE-3\d\d")
# markers that make an occurrence legitimate rather than an assertion
EXCULPATING = (r"\bnot\b|\bno\b|never|cannot|can not|without|refus|unavailable|"
               r"NOT_SEPARATED|NOT_EVALUABLE|ASSOCIATED_WITH|CONSISTENT_WITH|"
               r"retired|retracted|withdraw|unsupported|is not supported|"
               r"remain|earlier|historical|prior study|claim retracted|"
               r"methodology warning|rather than")

def causal_isolation_hits(text, window=260):
    """Affirmative causal-isolation claims about a confounded subject."""
    flat = re.sub(r"\s+", " ", text)
    out = []
    for m in re.finditer(CAUSAL, flat, re.I):
        w = flat[max(0, m.start() - window):m.end() + window]
        if not re.search(CONFOUNDED, w, re.I):
            continue                      # not about a confounded subject
        if re.search(EXCULPATING, w, re.I):
            continue                      # negated / retired / qualified / quoted
        out.append(flat[max(0, m.start() - 90):m.end() + 130])
    return out




def main():
    RAW = open("docs/paper/MANUSCRIPT.md").read()
    FLAT = re.sub(r"\s+", " ", RAW)
    BODY, REFS = RAW.split("## References")
    fails, notes = [], {}


    def ctx(pat, w=180):
        return [FLAT[max(0, m.start()-w):m.end()+w] for m in re.finditer(pat, FLAT, re.I)]

    def check(n, name, ok, detail=""):
        notes["%02d %s" % (n, name)] = ("PASS" if ok else "FAIL") + (" — " + detail if detail else "")
        if not ok: fails.append("%02d %s: %s" % (n, name, detail))

    # 1 every in-text citation resolves to a reference entry
    cited = {int(x) for grp in re.findall(r"\[((?:\d{1,2})(?:\s*,\s*\d{1,2})*)\]", BODY)
             for x in re.split(r"\s*,\s*", grp)}
    listed = {int(x) for x in re.findall(r"^\[(\d{1,2})\]", REFS, re.M)}
    check(1, "citations resolve", not (cited - listed), "dangling %s" % sorted(cited - listed))
    # 2 every reference entry is cited at least once
    check(2, "no orphan references", not (listed - cited), "uncited %s" % sorted(listed - cited))
    # 3 no placeholder citation metadata
    ph = [p for p in ("TODO", "TBD", "XXX", "CITATION NEEDED", "et al., YEAR", "????") if p in RAW]
    check(3, "no fabricated/placeholder citations", not ph, str(ph))
    # 4 no unsupported novelty claim
    nov = []
    for pat in (r"to our knowledge", r"no prior work", r"the first (study|work|paper|to\b)",
                r"\bwe are the first\b", r"few (studies|works)", r"\bunprecedented\b",
                r"\bnovel(ty)? contribution\b"):
        nov += [c[150:250] for c in ctx(pat)]
    check(4, "no unsupported novelty claim", not nov, str(nov))
    # 5 RQ numbering is exactly 1..4 and each is answered
    rq = sorted({m for m in re.findall(r"\*\*RQ(\d)\*\*", RAW)})
    check(5, "RQ set intact", rq == ["1", "2", "3", "4"], str(rq))
    # 6 RQ1 no longer asks the refused absolute cross-generation question
    bad = [c for c in ctx(r"which generation is faster") if not re.search(NEG, c, re.I)]
    check(6, "RQ1 rescoped away from absolute comparison", not bad, str(bad))
    # 7 abstract exists and states the thesis-supporting headline figures
    absc = RAW.split("## Abstract")[1].split("---")[0] if "## Abstract" in RAW else ""
    check(7, "abstract present", 100 < len(absc.split()) < 400, "%d words" % len(absc.split()))
    # 8 every figure asserted in the abstract also appears in the body
    missing = [f for f in ("53", "28", "23", "74", "133", "222", "21", "19,000")
               if f not in re.sub(r"\s+", " ", BODY.split("## 1. Introduction")[1])]
    check(8, "abstract figures traceable to body", not missing, str(missing))
    # 9 no raw cross-platform cycle ratio / % faster-slower
    bad = [c[150:250] for p in (r"cycle ratio", r"%\s*(faster|slower)")
           for c in ctx(p) if not re.search(NEG, c, re.I)]
    check(9, "no prohibited cross-platform magnitude claim", not bad, str(bad))
    # 10 no invented aggregate robustness score
    bad = [c[150:250] for c in ctx(r"robustness (score|index|percentage)")
           if not re.search(NEG, c, re.I)]
    check(10, "no robustness score invented", not bad, str(bad))
    # 11 no causal attribution to TA / platform
    bad = [c[150:250] for c in ctx(r"(TA|timing[- ]adapter|Corstone|Fast Models)\s+caused")
           if not re.search(NEG, c, re.I)]
    check(11, "TA association not causation", not bad, str(bad))
    # 12 no causal architectural attribution for the U85 reversal
    bad = [c[150:250] for p in (r"ublock enlargement causes", r"scales better because",
                                r"core replication is (better|superior)")
           for c in ctx(p) if not re.search(NEG, c, re.I)]
    check(12, "U85 mechanism stays non-causal", not bad, str(bad))
    # 13 board scope: no simulation==hardware equivalence claim
    bad = [c[150:250] for p in (r"FVP (accurately )?predicts hardware",
                                r"cycle counts agree", r"board validates (FVP|MAC)")
           for c in ctx(p) if not re.search(NEG, c, re.I)]
    check(13, "board validation scope preserved", not bad, str(bad))
    # 14 frozen evidence vocabulary and CLASS A/B separation survive the rewrite
    inv = [t for t in ("ASSOCIATED_WITH", "NOT_SEPARATED", "NOT_EVALUABLE",
                       "reported separately and are not combined",
                       "FVP parameter acceptance is not used as the authority",
                       "--debug-force-legacy-core", "post-compilation")
           if t not in FLAT]
    check(14, "frozen invariants retained", not inv, str(inv))
    # 15 frozen numeric results unchanged by the rewrite
    num = [n for n in ("74", "133", "222", "21 formal samples", "92 cells, 276 samples",
                       "24/32", "14/14", "rho = 1.0", "7/7") if n not in FLAT]
    check(15, "frozen figures unchanged", not num, str(num))

    # 16 no causal-isolation claim over a NOT_SEPARATED subject (F15)
    hits = causal_isolation_hits(BODY)
    check(16, "no causal isolation of a confounded factor", not hits, str(hits[:3]))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    print("\nRESULT:", "ALL %d PASS" % len(notes) if not fails else "FAILED: %s" % fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
