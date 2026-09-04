#!/usr/bin/env python3
"""Claim-discipline checks for docs/paper/MANUSCRIPT.md.

15 checks mandated by the REMEDIATION PHASE 1 decision, plus check 16
(causal-isolation language) added in PHASE 1.5 to close finding F15.

Phase 2: all text matching now goes through the shared normalization layer
(`manuscript_text.Manuscript`) instead of this file's own whitespace handling,
so a hard-wrapped phrase can never again look absent. Findings report the
manuscript line they occur on.
"""
import json
import re
import sys

from manuscript_text import Manuscript

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

NEG = (r"(\bno\b|\bnot\b|never|without|remain|refus|prohibit|forbid|retire|"
       r"withdraw|NOT_COMPARABLE|NOT_EVALUABLE|does not|deliberately|"
       r"is not used|outside what)")


def causal_isolation_hits(text, window=260):
    """Affirmative causal-isolation claims about a confounded subject."""
    flat = re.sub(r"\s+", " ", text)
    out = []
    for m in re.finditer(CAUSAL, flat, re.I):
        w = flat[max(0, m.start() - window):m.end() + window]
        if not re.search(CONFOUNDED, w, re.I):
            continue                      # not about a confounded subject
        if re.search(EXCULPATING, w, re.I):
            continue                      # negated / retired / qualified
        out.append(flat[max(0, m.start() - 90):m.end() + 130])
    return out


def main(path="docs/paper/MANUSCRIPT.md"):
    m = Manuscript.load(path)
    raw, prose = m.raw, m.prose
    body_end = prose.index("## References")
    body = prose[:body_end]
    refs = raw.split("## References")[1]
    fails, notes = [], {}

    def check(n, name, ok, detail=""):
        notes["%02d %s" % (n, name)] = (("PASS" if ok else "FAIL")
                                        + (" — " + detail if detail else ""))
        if not ok:
            fails.append("%02d %s: %s" % (n, name, detail))

    def unnegated(pattern):
        """Hits whose surrounding window carries no refusal marker."""
        return [("L%d: %s" % (h.line, h.text))
                for h in m.find(pattern)
                if not re.search(NEG, h.context, re.I)]

    # 1 every in-text citation resolves to a reference entry
    cited = {int(x)
             for g in re.findall(r"\[((?:\d{1,2})(?:\s*,\s*\d{1,2})*)\]", body)
             for x in re.split(r"\s*,\s*", g)}
    listed = {int(x) for x in re.findall(r"^\[(\d{1,2})\]", refs, re.M)}
    check(1, "citations resolve", not (cited - listed),
          "dangling %s" % sorted(cited - listed))
    # 2 every reference entry is cited at least once
    check(2, "no orphan references", not (listed - cited),
          "uncited %s" % sorted(listed - cited))
    # 3 no placeholder citation metadata
    ph = [p for p in ("TODO", "TBD", "XXX", "CITATION NEEDED", "et al., YEAR")
          if p in raw]
    check(3, "no fabricated/placeholder citations", not ph, str(ph))
    # 4 no unsupported novelty claim
    nov = []
    for pat in (r"to our knowledge", r"no prior work",
                r"the first (study|work|paper|to\b)", r"\bwe are the first\b",
                r"few (studies|works)", r"\bunprecedented\b",
                r"\bless common\b", r"\buncommon\b"):
        nov += ["L%d: %s" % (h.line, h.text) for h in m.find(pat)]
    check(4, "no unsupported novelty claim", not nov, str(nov))
    # 5 RQ numbering is exactly 1..4
    rq = sorted({x for x in re.findall(r"\*\*RQ(\d)\*\*", raw)})
    check(5, "RQ set intact", rq == ["1", "2", "3", "4"], str(rq))
    # 6 RQ1 no longer asks the refused absolute question
    check(6, "RQ1 rescoped away from absolute comparison",
          not unnegated(r"which generation is faster"))
    # 7 abstract present
    absn = raw.split("## Abstract")[1].split("\n---")[0]
    check(7, "abstract present", 100 < len(absn.split()) < 400,
          "%d words" % len(absn.split()))
    # 8 abstract figures traceable to the body
    after_intro = prose[prose.index("## 1. Introduction"):]
    missing = [f for f in ("53", "28", "23", "74", "133", "222", "21", "19,000")
               if f not in after_intro]
    check(8, "abstract figures traceable to body", not missing, str(missing))
    # 9 no raw cross-platform magnitude claim
    check(9, "no prohibited cross-platform magnitude claim",
          not (unnegated(r"cycle ratio")
               + unnegated(r"%\s*(faster|slower)")))
    # 10 no invented aggregate robustness score
    check(10, "no robustness score invented",
          not unnegated(r"robustness (score|index|percentage)"))
    # 11 TA association not causation
    check(11, "TA association not causation",
          not unnegated(r"(TA|timing[- ]adapter|Corstone|Fast Models)\s+caused"))
    # 12 U85 mechanism stays non-causal
    check(12, "U85 mechanism stays non-causal",
          not (unnegated(r"ublock enlargement causes")
               + unnegated(r"scales better because")
               + unnegated(r"core replication is (better|superior)")))
    # 13 board validation scope preserved
    check(13, "board validation scope preserved",
          not (unnegated(r"FVP (accurately )?predicts hardware")
               + unnegated(r"cycle counts agree")
               + unnegated(r"board validates (FVP|MAC)")))
    # 14 frozen invariants retained
    inv = [t for t in ("ASSOCIATED_WITH", "NOT_SEPARATED", "NOT_EVALUABLE",
                       "reported separately and are not combined",
                       "FVP parameter acceptance is not used as the authority",
                       "--debug-force-legacy-core", "post-compilation")
           if not m.has(t, where="flat")]
    check(14, "frozen invariants retained", not inv, str(inv))
    # 15 frozen numeric results unchanged
    num = [n for n in ("74", "133", "222", "21 formal samples",
                       "92 cells, 276 samples", "24/32", "14/14", "rho = 1.0",
                       "7/7")
           if not m.has(n, where="flat")]
    check(15, "frozen figures unchanged", not num, str(num))
    # 16 no causal isolation of a confounded factor (F15)
    hits = causal_isolation_hits(body)
    check(16, "no causal isolation of a confounded factor", not hits,
          str(hits[:3]))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    print("\nRESULT:", ("ALL %d PASS" % len(notes)) if not fails
          else "FAILED: %s" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
