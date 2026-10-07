#!/usr/bin/env python3
"""Structural validation battery for docs/paper/MANUSCRIPT.md.

Introduced for PHASE 1.5; extended and migrated onto the shared normalization
layer in PHASE 2. Covers what the claim-discipline checks do not: cross-
reference resolution, thesis/abstract traces, related-work attribution,
reference resolution, platform-role conflicts, and preservation of frozen
results that editing must not disturb.

Section pointers are validated against section *titles*, not hardcoded numbers,
so renumbering (Phase-2 action 8 promotes the robustness study to its own
section) cannot silently invalidate a check.
"""
import json
import os
import re
import sys

from manuscript_text import Manuscript

# default resolves relative to this file, so the suite runs from anywhere
DEFAULT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "MANUSCRIPT.md")


def main(path=DEFAULT):
    m = Manuscript.load(path)
    raw, prose = m.raw, m.prose
    secs = m.sections()
    refs = raw.split("## References")[1]
    body = prose[:prose.index("## References")]
    fails, notes = [], {}

    def check(name, ok, detail=""):
        notes[name] = ("PASS" if ok else "FAIL") + (" — " + detail if detail else "")
        if not ok:
            fails.append("%s: %s" % (name, detail))

    def section_titled(*words):
        """The number of the section whose title contains all `words`."""
        for num, title in sorted(secs.items()):
            if all(w.lower() in title.lower() for w in words):
                return num
        return None

    # -- 1. cross-reference resolution ------------------------------------
    ptrs = m.section_pointers()
    missing = sorted({"%s (L%d)" % (h.text, h.line) for h in ptrs
                      if h.text not in secs})
    check("cross-reference targets exist", not missing,
          "unresolved %s" % missing)

    # -- 2. semantic targets, derived from titles -------------------------
    board = section_titled("hardware validation")
    mech = section_titled("mechanism study")
    robust = section_titled("structural metrics") or section_titled("Validity")
    for label, pattern, want in (
        ("board work cited from Related Work",
         r"rather than absolute cycle agreement \(Section (\d+(?:\.\d+)?)\)", board),
        ("operation-level decomposition cited from Related Work",
         r"to the operation level on a specific NPU \(Section (\d+(?:\.\d+)?)\)", mech),
        ("structural comparison cited from platform-role prose",
         r"where a comparison is explicitly structural \(Section (\d+(?:\.\d+)?)\)",
         robust),
    ):
        hits = m.find(pattern)
        got = re.search(pattern, hits[0].text, re.I).group(1) if hits else None
        check("semantic target — " + label, got is not None and got == want,
              "points at %r (%r); expected %r (%r)"
              % (got, secs.get(got, ""), want, secs.get(want, "")))

    # -- 3. no stale pointer from an earlier numbering ---------------------
    # Literal number checks were removed in Phase 2: action 8 renumbered the
    # sections, so a hardcoded "Section 6 is wrong" rule became wrong itself.
    # Staleness is now defined structurally — every pointer must resolve (check
    # 1) and the load-bearing ones must land on the right TITLE (check 2) — plus
    # the retired pre-Phase-1.5 phrasings below, which name no number.
    stale = [t for t in ("which is the gap Section", "Such suites",
                         "purely by adapter state")
             if m.has(t)]
    check("no retired phrasing", not stale, str(stale))

    # -- 4. thesis trace ---------------------------------------------------
    th = re.sub(r"\s+", " ",
                re.search(r"\*\*Thesis\.\*\*(.+?)We ask", raw, re.S).group(1))
    check("thesis C1 non-monotonic scoped", "can become non-monotonic" in th)
    check("thesis C2 bound to the boundary",
          "where it does become non-monotonic" in th and "that transition is shaped" in th,
          "C2 must not generalize beyond the studied transition")
    check("thesis C3 drops unpreregistered intensifier",
          "far better" not in th and "not comparable at all" in th,
          "C3 must not rank transfer against an unevaluated raw layer")
    check("thesis asserts no architecture-only causality",
          not re.search(r"because (the|of) (larger|MAC|array|architecture)", th, re.I))

    # -- 5. abstract -------------------------------------------------------
    absn = re.sub(r"\s+", " ", raw.split("## Abstract")[1].split("\n---")[0])
    check("abstract tiers primary results", "Three primary findings follow" in absn,
          "must not read as four co-primary findings")
    check("abstract marks validation tier",
          "validate these findings rather than extending them" in absn)
    check("abstract adds no new numbers",
          set(re.findall(r"\d[\d,]*\s?%?", absn))
          <= set(re.findall(r"\d[\d,]*\s?%?", re.sub(r"\s+", " ", raw))))

    # -- 6. related-work attribution ---------------------------------------
    check("no field-wide frequency claim",
          not m.find(r"\b(commonly|typically|usually|most (?:studies|work))\b"
                     r"[^.]{0,120}(characteri[sz]|report|measure)"))
    check("no reintroduced novelty vocabulary",
          not m.find(r"to our knowledge|no prior work|"
                     r"the first (study|work|paper|to\b)|few (studies|works)|"
                     r"less common|uncommon"))
    check("MicroNets not miscast as a benchmark suite", not m.has("Such suites"),
          "positive positioning required instead")

    # -- 7. references ------------------------------------------------------
    cited = {int(x)
             for g in re.findall(r"\[((?:\d{1,2})(?:\s*,\s*\d{1,2})*)\]", body)
             for x in re.split(r"\s*,\s*", g)}
    listed = {int(x) for x in re.findall(r"^\[(\d{1,2})\]", refs, re.M)}
    check("references resolve both ways", cited == listed,
          "cited-not-listed %s / listed-not-cited %s"
          % (sorted(cited - listed), sorted(listed - cited)))
    check("U55/U65 primary sources present",
          "102420" in refs and "102023" in refs and "[16]" in body and "[17]" in body)
    check("U85 docs not used as U55/U65 authority",
          not m.has("Ethos-U55 and Ethos-U65 manuals define the discrete MAC "
                    "configurations of those generations [1, 2]"))

    # -- 8. platform roles --------------------------------------------------
    check("SSE-315 never an authoritative performance platform",
          not m.find(r"SSE-315[^.]{0,120}(performance (result|figure|value)|"
                     r"authoritative|primary (measurement|performance))"))
    check("platform role table intact",
          all(m.has(r) for r in
              ("primary memory-aware simulated substrate",
               "diagnostic / platform-sensitivity control",
               "U65-specific diagnostic reference substrate",
               "primary U85 substrate and hardware-validation anchor")))

    # -- 9-12. frozen results that editing must not disturb -----------------
    check("X0 num_macs correction preserved",
          m.has("NOT_REPRODUCIBLE") and m.has("NOT_LOAD_BEARING")
          and m.has("FVP parameter acceptance is not used as the authority"))
    check("compiler-path distinction preserved",
          m.has("--debug-force-legacy-core") and m.has("post-compilation")
          and m.has("not an exact decomposition"))
    check("U65 bridge verdict preserved",
          m.has("NOT_EQUIVALENT") and m.has("AXI_BEAT_EXACT_EQUIVALENCE", where="flat"))
    check("X1/X3 CLASS A/B scope preserved",
          m.has("reported separately and are not combined")
          and m.has("NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR")
          and m.has("NOT_SEPARATED"))

    # -- 13. F4 causal scope stated ----------------------------------------
    check("F4 causal scope stated in the manuscript",
          m.has("cannot be attributed to the timing adapter alone")
          and m.has("methodology warning against raw"))

    print(json.dumps(notes, indent=1, ensure_ascii=False))
    print("\nRESULT:", ("ALL %d PASS" % len(notes)) if not fails
          else "FAILED: %s" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
