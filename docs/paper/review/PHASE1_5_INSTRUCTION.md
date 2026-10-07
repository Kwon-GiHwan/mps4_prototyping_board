# PHASE-1.5 TEXT CORRECTION — MANAGER GO (recorded verbatim scope)

Authoritative manuscript : paper-manuscript-review-phase1-frozen = f09bba6
Authoritative review     : paper-manuscript-phase1-review-frozen = 85aa4d5

## Manager decisions
- D1 APPROVED — Phase-1.5 separate text pass
- D2 F12 Conclusion DEFERRED to Phase 2
- D3 F14 primary-source reinforcement APPROVED
- D4 X2 / X4 / X5 remain HOLD
- REVIEW_ACTION_PLAN 7-14 remain HOLD
- No new measurement, build, FVP run, board run, or analysis authorized.

## Authorized fix set
APPLY   : F1-F11, F13, F14, F15
DO NOT  : F12 (Conclusion) — explicit hold, no temporary conclusion
DO NOT  : REVIEW_ACTION_PLAN 7-14 beyond what is strictly necessary

## Binding constraints per item
- F4  highest priority. Remove any "purely by adapter state" / "TA caused" equivalent.
      Preserve ESTABLISHED: same Vela/NPU artifact; TA differs; subsystem differs;
      Fast Models/timing implementation differs. Therefore TA/subsystem/FM = NOT_SEPARATED.
      Frame as methodology warning against raw cross-platform cycle comparison.
      DO NOT modify frozen X0/X1/X3 evidence documents to harmonize wording.
- F1-F3 semantic target verification, not regex existence. No stale pre-Phase-1 numbers.
- F6/F7 weaken thesis wording rather than broaden Results. All clauses must become
      SUPPORTED. No architecture-only causality. Provide clause -> result -> evidence ->
      limitation trace.
- F8  tier the abstract: primary = MAC scaling, U85 mechanism, Vela prediction;
      validation = board ordering, platform sensitivity. Add no new numbers.
- F9/F10 preserve only what the source directly supports; no field-wide frequency from a
      small citation set; no capability-absence claim beyond established scope; prefer
      positive positioning. Never reintroduce first/few/uncommon/less common/no prior work.
- F13 apply exactly as specified in frozen PHASE1_ACTIONS.md; do not broaden. If it
      interacts with another corrected sentence, preserve the stricter evidence boundary.
- F14 REFERENCE_ONLY. Resolve exact Arm document identifier; verify content supports the
      cited statement; official title/number; invent no date/version metadata; omit
      unverifiable fields; never cite U85 docs as authority for U55/U65 facts; do not alter
      scientific claims to accommodate a citation. If unverifiable: leave uncited or narrow,
      and report unresolved authority. Do not fabricate.
- F15 extend checker to causal phrases beyond "X caused" (purely by, solely due to,
      attributable to, results from, driven by, because of). Must distinguish affirmative
      causal claim / negated-retired claim / quoted historical framing / NOT_SEPARATED
      qualification. No global blacklist. Add regression fixtures for the F4 sentence class.
- RQ1 smallest authorized text correction using existing Results only. No new metric,
      no X2, no new computation. Target RQ1_CLOSED or STOP.

## Required outputs
docs/paper/review/PHASE1_5_REMEDIATION.md  (per-F-item traceability, incl. F4 final causal
scope: TA / subsystem / FM = NOT_SEPARATED)

## Validation battery (13)
Phase-1 15 checks; cross-reference audit; thesis trace; abstract evidence trace; related-work
attribution; reference resolution; causal-language checker incl. F15 fixtures; platform-role
conflict scan; X0 num_macs correction preservation; compiler-path distinction preservation;
U65 bridge verdict preservation; X1/X3 CLASS A/B scope preservation.
Require: all authorized findings CLOSED, scientific contradiction count = 0.

## Freeze
paper-manuscript-phase1_5-frozen           (corrected manuscript)
paper-manuscript-phase1_5-review-frozen    (narrow verification-only gate, no edits)
Do not move previous manuscript/review tags.
