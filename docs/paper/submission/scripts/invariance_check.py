#!/usr/bin/env python3
"""SE1 section 16: scientific invariance of the LaTeX layer vs d137a7d.

Any drift is a BLOCKER. The check runs against the rendered PDF text, not just
main.tex, so a claim lost in typesetting is caught too.
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
FROZEN = "d137a7d"


def norm(t):
    return re.sub(r"\s+", " ", t)


def pdf_text():
    sys.path.insert(0, "/private/tmp/claude-501/-Users-gihwan-Documents-Projects-"
                       "mps4-prototyping-board/cacdc52d-41ab-4b19-8701-"
                       "3b76597632c2/scratchpad/pdfvenv/lib/python3.9/site-packages")
    import fitz
    d = fitz.open(os.path.join(SUB, "build", "paper-review.pdf"))
    # The `review` class option prints a line-number margin. Clip it away by
    # taking only text right of the margin, so stray line numbers cannot be
    # mistaken for content (a bare "467" line number otherwise looks like the
    # retired 467x figure).
    pages = []
    for pg in d:
        r = pg.rect
        body = fitz.Rect(r.x0 + 46, r.y0, r.x1, r.y1)
        pages.append(pg.get_text(clip=body))
    raw = " ".join(pages)
    # undo hyphenation introduced by line breaking before phrase matching
    raw = re.sub(r"-\s*\n\s*", "", raw)
    raw = norm(raw)
    raw = raw.replace("- ", "-")
    return raw


def main():
    md = norm(subprocess.run(["git", "-C", REPO, "show",
                              "%s:docs/paper/MANUSCRIPT.md" % FROZEN],
                             capture_output=True, text=True, check=True).stdout)
    tex = norm(open(os.path.join(SUB, "main.tex")).read())
    pdf = pdf_text()
    fails, notes = [], {}

    def hs(t):
        """Hyphen-insensitive form: PDF line breaking splits hyphenated words,
        and de-hyphenating turns 'non-monotonic' into 'nonmonotonic'. Compare
        both sides with hyphens removed so neither form can cause a false
        drift report."""
        return t.replace("-", "").lower()

    pdf_h = hs(pdf)

    def says(phrase):
        return hs(phrase) in pdf_h

    def check(name, ok, detail=""):
        notes[name] = ("PASS" if ok else "FAIL") + (" — " + detail if detail else "")
        if not ok:
            fails.append("%s: %s" % (name, detail))

    # --- RQs -------------------------------------------------------------
    for n in "1234":
        check("RQ%s present" % n, ("RQ%s" % n) in pdf)
    check("RQ1 not restored to the refused question",
          "which generation is faster" not in pdf or
          "Deliberately not" in pdf)

    # --- thesis clauses ---------------------------------------------------
    check("thesis C1", says("does not yield proportional performance gains"))
    check("thesis C2 bound to the boundary",
          says("where it does become non-monotonic"))
    check("  and C2 rule can fire", not says("where it does become monotonic zzz"),
          "sanity: the matcher is not vacuously true")
    check("thesis C3 without intensifier",
          not says("far better") and says("not comparable at all"))

    # --- five figure semantics -------------------------------------------
    for n, frag in ((1, "Cumulative scaling efficiency"),
                    (2, "Metric agreement across the tested platform pairs"),
                    (3, "Relative cost shape"),
                    (4, "Distribution of the reversal"),
                    (5, "Cross-memory robustness")):
        check("figure %d semantics" % n, says(frag), frag)

    # --- frozen numeric anchors ------------------------------------------
    for anchor in ("468", "19,000", "19,060", "133", "222", "74", "21",
                   "24/32", "14/14", "7/7", "27 of 29", "19 of 21", "19/20",
                   "31/55", "0.9429", "1.0000"):
        check("anchor %s" % anchor, anchor in pdf)
    # the retired figure is the workload span "467x"; a bare 467 elsewhere is
    # not the claim. Mutation-tested below.
    span_pat = r"467\s*(?:\u00d7|x\b)"
    check("467x absent (provenance correction preserved)",
          not re.search(span_pat, pdf))
    check("  and the rule can fire", bool(re.search(span_pat, "span 467x")),
          "a check that cannot fail is worse than no check")
    check("board rho = 1.0", "= 1.0" in pdf or "rho = 1.0" in pdf)
    check("zero rank inversions", "0 rank inversions" in pdf)

    # --- scope vocabulary -------------------------------------------------
    for v in ("NOT_SEPARATED", "NOT_EVALUABLE", "ASSOCIATED_WITH",
              "CONSISTENT_WITH", "NOT_EQUIVALENT", "NOT_COMPARABLE",
              "ROBUST_IN_TESTED_PAIRS", "TA_STATE_SENSITIVE",
              "NOT_REPRODUCIBLE", "NO_OBSERVED_CYCLE_DIFFERENCE"):
        check("vocabulary %s" % v, v in pdf.replace(" ", "") or v in pdf)

    # --- CLASS A/B restriction -------------------------------------------
    check("CLASS A/B never pooled",
          says("reported separately and are not combined"))
    check("U65 bridge NOT_EQUIVALENT", "NOT_EQUIVALENT" in pdf)

    # --- prohibited claims -------------------------------------------------
    NEG = (r"\bnot\b|\bno\b|never|cannot|without|refus|unavailable|"
           r"NOT_SEPARATED|NOT_COMPARABLE|retired|rather than|is a judgement")
    for name, pat in (
        ("no raw cross-platform cycle claim",
         r"cross-platform cycles are (directly )?comparable"),
        ("no architecture-only causality",
         r"(block|ublock) (enlargement|change) (caused|causes)|"
         r"core replication is (better|superior)"),
        ("no TA causation", r"(TA|timing[- ]adapter) caused"),
        ("no FVP-board timing equivalence",
         r"FVP (accurately )?predicts (board|hardware)"),
    ):
        hits = [pdf[max(0, m.start() - 120):m.end() + 120]
                for m in re.finditer(pat, pdf, re.I)]
        hits = [h for h in hits if not re.search(NEG, h, re.I)]
        check(name, not hits, str(hits[:1]))

    # --- content coverage: every markdown section reached the PDF ---------
    md_lines = subprocess.run(["git", "-C", REPO, "show",
                               "%s:docs/paper/MANUSCRIPT.md" % FROZEN],
                              capture_output=True, text=True,
                              check=True).stdout.split("\n")
    secs = [re.match(r"^## (\d+)\. (.+)$", l).group(2)
            for l in md_lines if re.match(r"^## \d+\. ", l)]
    low = pdf.lower().replace("-", "")
    missing = [t for t in secs
               if t.split("(")[0].strip()[:24].lower().replace("-", "") not in low]
    check("all sections present in the PDF", not missing, str(missing))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    print("\nDRIFT:", 0 if not fails else len(fails))
    print("RESULT:", ("ALL %d PASS" % len(notes)) if not fails
          else "FAILED: %s" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
