#!/usr/bin/env python3
"""PHASE 1.5 validation battery (manager decision section 13).

Covers the items the 16 consistency checks do not: semantic cross-reference
resolution, thesis/abstract traces, related-work attribution, reference
resolution, platform-role conflicts, and preservation of four frozen results
that Phase-1.5 editing must not have disturbed.
"""
import json, re, subprocess, sys

RAW = open("docs/paper/MANUSCRIPT.md").read()
FLAT = re.sub(r"\s+", " ", RAW)
BODY, REFS = RAW.split("## References")
fails, notes = [], {}


def check(name, ok, detail=""):
    notes[name] = ("PASS" if ok else "FAIL") + (" — " + detail if detail else "")
    if not ok:
        fails.append("%s: %s" % (name, detail))


# --- section index ---------------------------------------------------------
heads = {}
for m in re.finditer(r"^#{2,3} (\d+(?:\.\d+)?)\.? (.+)$", RAW, re.M):
    heads[m.group(1)] = m.group(2).strip()
# Section 8's subsections are bold-inline ("**8.1 The timing adapter ...**"),
# not markdown headings; index them too or every 8.x pointer looks unresolved.
for m in re.finditer(r"\*\*(\d+\.\d+)\s+([^*]+)", RAW):
    heads.setdefault(m.group(1), m.group(2).strip().rstrip(".")) 

# 1. cross-reference resolution: every pointer names an existing section
ptrs = sorted({m.group(1) for m in re.finditer(r"Section (\d+(?:\.\d+)?)", RAW)})
missing = [p for p in ptrs if p not in heads]
check("cross-reference targets exist", not missing,
      "unresolved %s (have %s)" % (missing, sorted(heads)))

# 2. cross-reference semantics: the three repaired pointers land on the right topic
SEM = {
    "board work cited from Related Work": (
        r"relative-cost structure\* at the one physically available "
        r"configuration rather than absolute cycle agreement \(Section (\d+)\)",
        "5", "hardware validation"),
    "operation-level decomposition cited from Related Work": (
        r"decomposes one configuration transition to the operation level on a"
        r" specific NPU\s*\(Section (\d+)\)", "6", "mechanism study"),
    "structural comparison cited from 3.1": (
        r"the latter appear only where a comparison is explicitly structural"
        r"\s*\(Section (\d+\.\d+)\)", "4.6", "Robustness of the structural metrics"),
}
for label, (pat, want, topic) in SEM.items():
    m = re.search(re.sub(r"\\s\+", " ", pat.replace("\\s*", " ")), FLAT)
    got = m.group(1) if m else None
    ok = got == want and topic.lower() in heads.get(want, "").lower()
    check("semantic target — " + label, ok,
          "points at %s (%r); expected %s about %r" % (got, heads.get(got, ""), want, topic))

# 3. no stale pre-Phase-1 pointer survives (Section 7 for the decomposition,
#    Section 6 for the board, Section 5 for the structural comparison)
stale = []
if re.search(r"operation level on a specific\s+NPU,? which is the gap Section 7", FLAT):
    stale.append("Related Work -> Section 7 for decomposition")
if re.search(r"absolute cycle agreement \(Section 6\)", FLAT):
    stale.append("Related Work -> Section 6 for board")
if re.search(r"explicitly structural \(Section 5\)", FLAT):
    stale.append("3.1 -> Section 5 for structural comparison")
check("no stale Phase-1 pointer", not stale, str(stale))

# 4. thesis trace: three clauses, each anchored by a result the paper prints
thesis = re.search(r"\*\*Thesis\.\*\*(.+?)\n\nWe ask", RAW, re.S).group(1)
tflat = re.sub(r"\s+", " ", thesis)
check("thesis C1 non-monotonic scoped", "can become non-monotonic" in tflat)
check("thesis C2 bound to the boundary",
      "where it does become non-monotonic" in tflat and "that transition is shaped" in tflat,
      "C2 must not generalize beyond the studied transition")
check("thesis C3 drops unpreregistered intensifier",
      "far better" not in tflat and "not comparable at all" in tflat,
      "C3 must not rank transfer against an unevaluated raw layer")
check("thesis asserts no architecture-only causality",
      not re.search(r"because (the|of) (larger|MAC|array|architecture)", tflat, re.I))

# 5. abstract tiering: primary vs validation legible
absn = RAW.split("## Abstract")[1].split("\n---")[0]
aflat = re.sub(r"\s+", " ", absn)
check("abstract tiers primary results",
      "Three primary findings follow" in aflat, "must not read as four co-primary findings")
check("abstract marks validation tier",
      "validate these findings rather than extending them" in aflat)
check("abstract adds no new numbers",
      set(re.findall(r"\d[\d,]*\s?%?", aflat)) <= set(re.findall(r"\d[\d,]*\s?%?", FLAT)))

# 6. related-work attribution
check("no field-wide frequency claim",
      not re.search(r"\b(commonly|typically|usually|most (?:studies|work))\b"
                    r"[^.]{0,120}(characteri[sz]|report|measure)", aflat + FLAT, re.I))
check("no reintroduced novelty vocabulary",
      not re.search(r"to our knowledge|no prior work|the first (study|work|paper|to\b)|"
                    r"few (studies|works)|less common|uncommon", FLAT, re.I))
check("MicroNets not miscast as a benchmark suite",
      not re.search(r"Such suites", FLAT),
      "positive positioning required instead")

# 7. reference resolution
cited = {int(x) for g in re.findall(r"\[((?:\d{1,2})(?:\s*,\s*\d{1,2})*)\]", BODY)
         for x in re.split(r"\s*,\s*", g)}
listed = {int(x) for x in re.findall(r"^\[(\d{1,2})\]", REFS, re.M)}
check("references resolve both ways", cited == listed,
      "cited-not-listed %s / listed-not-cited %s" % (sorted(cited - listed), sorted(listed - cited)))
check("U55/U65 primary sources present",
      "102420" in REFS and "102023" in REFS and "[16]" in BODY and "[17]" in BODY)
check("U85 docs not used as U55/U65 authority",
      not re.search(r"Ethos-U55 and Ethos-U65 manuals[^.]{0,80}\[1, 2\]", FLAT))

# 8. platform-role conflict scan
check("SSE-315 never an authoritative performance platform",
      not re.search(r"SSE-315[^.]{0,120}(performance (result|figure|value)|"
                    r"authoritative|primary (measurement|performance))", FLAT, re.I))
check("platform role table intact",
      all(r in FLAT for r in ("primary memory-aware simulated substrate",
                              "diagnostic / platform-sensitivity control",
                              "U65-specific diagnostic reference substrate",
                              "primary U85 substrate and hardware-validation anchor")))

# 9-12. frozen results that editing must not have disturbed
check("X0 num_macs correction preserved",
      "NOT_REPRODUCIBLE" in FLAT and "NOT_LOAD_BEARING" in FLAT
      and "FVP parameter acceptance is not used as the authority" in FLAT)
check("compiler-path distinction preserved",
      "--debug-force-legacy-core" in FLAT and "post-compilation" in FLAT
      and "not an exact decomposition" in FLAT.replace("**", ""))
check("U65 bridge verdict preserved",
      "NOT_EQUIVALENT" in FLAT and "AXI_BEAT_EXACT_EQUIVALENCE" in FLAT)
check("X1/X3 CLASS A/B scope preserved",
      "reported separately and are not combined" in FLAT
      and "NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR" in FLAT
      and "NOT_SEPARATED" in FLAT)

# 13. F4 final causal scope explicitly stated
check("F4 causal scope stated in the manuscript",
      bool(re.search(r"cannot be attributed to the timing\s+adapter alone", FLAT))
      and "methodology warning against raw" in FLAT)

print(json.dumps(notes, indent=1, ensure_ascii=False))
print("\nRESULT:", "ALL %d PASS" % len(notes) if not fails else "FAILED: %s" % fails)
sys.exit(1 if fails else 0)
