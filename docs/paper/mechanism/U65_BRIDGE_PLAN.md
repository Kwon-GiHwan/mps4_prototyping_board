# U65 cross-backend instrumentation equivalence — frozen plan

Manager decision (2026-09-02): U65 bridge-equivalence **GO**; manuscript
integration, cross-generation narrative, P2/P3/P4 all HOLD.

**Goal.** Establish whether the compiler-internal IRQ instrumentation used
by the legacy U55/U65 profiling path and the binary post-compilation IRQ
strategy developed for U85 implement the **same measurement boundary**.
This validates instrumentation equivalence only. It does NOT authorize
absolute U65-vs-U85 cycle comparison, cross-generation PMU-event
equivalence, or architectural causality claims.

## Design principle (the strict form)

Both methods derive from the **same clean U65 legacy program C0** —
Method B must NOT compile through regor or any different backend:

```
              SAME U65 CLEAN LEGACY PROGRAM (C0)
                            |
             +--------------+--------------+
        Method A                       Method B
  compiler-internal IRQ         binary postprocessor IRQ
 (legacy Vela path, existing    (parse C0, insert NPU_OP_IRQ at the
  qualified insertion patch)     SAME semantic boundaries; a
                            \    U65-specific command backend —
                             \   the U85 parser is NOT assumed)
                              compare measurement
```

The only intended independent variable is the IRQ insertion backend.
Held identical: model identity, Vela 5.0.0 legacy path, accelerator
config, memory/system config, driver PMU snapshot implementation, PMU
event configuration, FVP, input tensor.

## E0 — common baseline

Cells (exact repository identities; no substitution):

```
kws_micronet_m @ U65-256   (frozen model sha c1feed3a…)
rnnoise_INT8  @ U65-256    (frozen model sha 9c582545…)
platform  SSE-300 / TARGET_SUBSYSTEM sse-300 / Y256 / TA ON
vela      --system-config Ethos_U65_High_End --memory-mode Dedicated_Sram
          --optimise Performance --config default_vela.ini  (frozen sweep contract)
FVP       FVP_Corstone_SSE-300_Ethos-U65 (pinned install)
C0 gate   regenerated clean artifacts must hash-match the frozen formal
          vela shas (8b7930df…, adbda150…); C0 stream hash frozen before
          instrumentation
```

## E1 — structural qualification (fail-closed, before any runtime)

1. U65 postprocessor parse→serialize(0 modifications) byte-identical to C0.
2. Branch/offset/length semantics audited from `ethosu65_interface.h`
   (pre-audit: the U65 CMD0/CMD1 space contains **no branch opcode**;
   framing is the shared COP1 driver-action format).
3. A and B emit the same ordered semantic IRQ boundary IDs.
4. Stripping only the IRQ contribution from A and from B must each
   reconstruct C0's stream bytes exactly.
5. Any unmatched/duplicated/merged/ambiguous boundary → STOP.
6. If instrumented binary identity A==B is achieved, record it as the
   stronger implementation result; if not, semantic boundary equivalence
   must be proven before runtime use.

## E2 — runtime equivalence

Run each cell under clean C0, Method A, Method B in fresh FVP processes.
Repetition contract (preregistered): 3 fresh runs per arm, full-vector
exact equality, per the qualified FVP convention; no tolerance may be
introduced after data. Compare A vs B on: output CRC, IRQ count, IRQ
order, op/group attribution, per-group CYCLE, admitted memory PMU
counters, whole-model reconstructed sum, completion, fatal state.

Strongest target: output bit-identical; boundaries exact; attribution
exact; PMU vector exact. Raw A/B stream byte identity reported separately
if achieved. If PMU vectors differ: no averaging/normalizing — classify
`BACKENDS_NOT_MEASUREMENT_EQUIVALENT` and STOP.

Perturbation: clean→A and clean→B reported separately, descriptively; no
pass/fail percentage. The bridge question is segmentation identity, not
zero overhead.

## Escalation

Start ONLY with the two cells above. No automatic expansion to U65-512 or
U55; if command-structure coverage is materially insufficient, report and
request approval.

## Outputs / freeze order

`U65_BRIDGE_PLAN.md` (this) → `U65_BINARY_BACKEND_AUDIT.md` →
`U65_BRIDGE_STRUCTURAL_EQUIVALENCE.csv` →
`U65_BRIDGE_RUNTIME_EQUIVALENCE.csv` → `U65_BRIDGE_RESULTS.md` +
`U65_BRIDGE_LIMITATIONS.md`. Freeze: plan → structural qualification →
runtime evidence → bridge result. Then STOP; manuscript integration does
not start on completion.

Final report fields: clean/A/B cells; no-op roundtrip; exact boundary,
attribution, PMU-vector, output matches; perturbation observations; rule
failures; verdict `MEASUREMENT_EQUIVALENT` or `NOT_EQUIVALENT`; frozen
tags/hashes.

---

## Amendment 1 (2026-09-02, pre-acquisition) — stack fact discovered at E0

Vela 5.0.0 routes **all** targets through regor by default; the legacy
Python core is deprecated and reachable only via
`--debug-force-legacy-core` (U55/U65 + TFLite only). Two consequences,
recorded before any runtime data:

1. The frozen formal U55/U65 sweep artifacts of this paper are **regor
   outputs** (verified: the plag-free C0 regeneration hash-matched the
   frozen vela sha). Any manuscript statement about the U55/U65 compile
   path must say regor, not legacy.
2. Method A (compiler-internal insertion) only exists on the legacy core.
   Per this plan's own isolation principle, **C0 is therefore defined as
   the `--debug-force-legacy-core` output** under the otherwise identical
   frozen contract, and BOTH methods derive from it. C0's identity is
   frozen anew (it is a different program from the frozen regor artifact;
   the E0 "must hash-match the frozen formal vela shas" gate is
   superseded by "C0 hash frozen at generation", since matching a regor
   artifact would reintroduce exactly the compiler-mixing this plan
   forbids). The regor↔legacy program difference is out of scope for the
   bridge and noted for the limitations file.
