# Project record — Ethos-U generational characterization

Consolidated record of the measurement campaign: what was established, what was
corrected, and what remains explicitly unestablished. Written so the chain can be
reconstructed without the working session.

Companion documents: `EVIDENCE_INDEX.md` (every frozen digest and tag),
`PAPER_OUTLINE.md`, `MAIN_EXPERIMENT_MATRIX.md`.

---

## 1. Final state

```
capability / executability universe    133 cells   19 configs × 7 workloads
primary benchmark universe (TA ON)      77 cells   11 configs × 7 workloads
TA-OFF diagnostic universe              56 cells    8 configs × 7 workloads

E_primary (TA-ON ∩ EXECUTABLE)          74
FVP formal samples                     222         3 × 74, M1 == M2 == M3 on 74/74
board formal samples                    21         7 × 3 independent fresh boots

RQ1 / RQ2   answered within FVP scope
RQ3         ranking preservation computed: Spearman rho = 1.0, 0 inversions
narrative   FVP frozen; RQ3 narrative NOT STARTED
```

---

## 2. Matrix split — capability is not benchmark

The single most consequential structural finding. MLEK forces
`ETHOS_U_NPU_TIMING_ADAPTER_ENABLED` **off** for `sse-310` and `sse-315`, and it
is visible at the level of which files compile:

```
sse-300  401 sources, 2 timing-adapter sources
sse-320  402 sources, 2 timing-adapter sources
sse-310  399 sources, 0
sse-315  400 sources, 0
```

With the adapter off the memory system is not modelled. The observed ~4×
difference between `SSE-300/U55@32` (112,059 cycles) and `SSE-310/U55@32`
(27,059) is `CAUSE_RESOLVED` — adapter ON vs OFF — and is **a methodology
warning, not a performance comparison**. The Vela artifacts for those two cells
are byte-identical, so the NPU command stream is the same program.

**Claim retracted during this work:** "same NPU across different Corstone
generations" was offered as a clean platform-effect isolation. It is not — the
two sides differ in adapter state, comparing a memory-constrained model against
an unconstrained one.

---

## 3. Executability is a first-class result

All 133 cells compile under Vela; **6 cannot run**. Every failure reached a
linker SRAM overflow after the single deterministic arena retry, so the smallest
arena that could clear the first allocation failure already did not fit.

```
NOT_EXECUTABLE_MEMORY   6/6 are wav2letter × ethos-u55 × Shared_Sram, MAC 32/64/128
EXECUTABILITY_UNRESOLVED 0
```

Classified **SYSTEM-LEVEL MEMORY / DEPLOYABILITY LIMITATION**, not a U55
microarchitecture limit — MAC count, NPU, memory mode and platform memory map are
confounded in those six cells.

Consequence for the sweep: the formal sample count could not be fixed until the
filter ran. The pre-registered 399 assumed every cell runnable; the true figure
is 222. **A missing cell is a result, not a gap in collection.**

The same workload runs on U85/`Dedicated_Sram` hardware, consistent with the
constraint being the platform memory map rather than the workload.

---

## 4. Corrections that changed the contract

Each was found before it could contaminate results, and each is recorded as an
amendment rather than a silent edit.

| # | finding | correction |
| --- | --- | --- |
| 1 | `Requested: N` in the TFLM failure is **one allocation**, not the arena total (`available + missing == Requested`); N can be *smaller* than the failing arena | retry = `align_up(failing_arena + missing, 16)`; alignment proven from `ETHOS_U_MEM_BYTE_ALIGNMENT`, not fitted |
| 2 | firmware embeds `__DATE__`/`__TIME__` (`Main.cc:38`) — every AXF unique to the second it linked, so qualification hashes were **unreproducible by construction** | `SOURCE_DATE_EPOCH` pinned to the MLEK commit timestamp (1776763519); qualification digests kept as historical evidence, formal reference is a separate identity |
| 3 | MLEK's generator stamps wall-clock into the model `.cc` header — but that comment never reaches the binary (differing `.cc`, identical AXF) | raw `.cc` hash demoted to informational; **body** hash load-bearing; canonicalizer strips only the proven `Date:` field and fails closed |
| 4 | the stock runner performs **exactly one inference per boot** | the registered `3 boots × 10 runs = 210` board protocol was unexecutable without patching the artifact under test → `3 boots × 1 inference = 21` |
| 5 | board repeatability metric was never actually frozen — only `median(B1,B2,B3)` was | reporting limited to raw triplets + median; no spread/CV/deviation, since choosing one after seeing B1/B2 would be post-hoc |
| 6 | my PMU parser hardcoded AXI names and silently recorded `None` for all 35 U85 cells | parser now **discovers** the emitted event set; requalified 127/127 against captured UART |

Every one of these was found at **zero formal samples** for the affected stage,
so no threshold moved after seeing a result.

---

## 5. Determinism, and its limits

```
FVP     M1 == M2 == M3   74/74 across 19 equality-bearing fields
board   B1/B2/B3         independent physical observations — equality NOT required
```

The FVP check is an integrity gate on a deterministic simulator. The board is
not, which is why the frozen protocol takes `median(B1,B2,B3)` and why no rule
was created that would hard-stop a stage because `B2 != B1`.

**Caveat recorded honestly:** on the 35 U85 cells the three AXI fields compared
`None == None == None` — true, but carrying no information. The claim is "19
equality-bearing fields", not "19 informative fields per cell".

---

## 6. Results, as computed

**Scaling (FVP, TA-ON).** 21 ladders, 53 incremental points:
`STRONG` 28, `PARTIAL` 23, `WEAK_OR_SATURATED` 2, `NOT_AVAILABLE` 3.
Saturation `NONE_OBSERVED` in 19/21; observed once (`SSE-320/U85/rnnoise` at 512);
`NOT_AVAILABLE` once (`wav2letter/SSE-300/U55`, non-executable baseline, never
rebased).

**Vela vs FVP.** Over 20 ladders: saturation classification agrees 19/20,
normalized speedup rank agrees 19/20, per-step class agreement uneven (`4/4` down
to `0/1`). Coarse structure predicted well; individual step magnitude not.

**Workload ranking (FVP).** 55 configuration pairs, `rho` median 1.0000, min
0.9429, 31/55 exactly 1.0.

**RQ3 (FVP ↔ board, U85@1024).** `Spearman rho = 1.0`, **0 rank inversions**
across all seven workloads. Normalized cost vectors reported side by side, each
domain normalized by its own geometric mean.

---

## 7. What is deliberately NOT established

```
absolute cross-generation cycle comparison        prohibited (version + TA skew)
absolute FVP-vs-board comparison                  rejected in code, both figures present
aggregate shape-distance metric                   never preregistered → not computed
board repeatability variability statistic         never preregistered → not computed
quantitative PMU cross-target comparison          board ACTIVE/IDLE canonicalization unregistered
SRAM/EXT cross-target consistency                 NOT_EVALUABLE — absent from frozen FVP records
CC_STALLED_ON_BLOCKDEP                            NOT_EVALUABLE — never configured by stock profiler
"NONE_OBSERVED means it does not saturate"        false; means not seen in the tested range
"STRONG means linear"                             false; ≥ 0.75 is a threshold, not ideal scaling
```

`rho = 1.0` is reported as a number. Whether it constitutes strong validation is
a narrative judgement not yet made, and no pass/fail threshold was invented to
declare it one.

---

## 8. Method that produced this

The recurring defect throughout was **a declaration treated as authority for a
different artifact** — host constants standing in for firmware, FVP behaviour for
FPGA behaviour, compile success for runtime executability. The countermeasures:

- check against the **emitted artifact** (generated C, real UART, linked ELF), never a parallel declaration
- **freeze the contract before the data exists**, and record supersessions rather than editing
- make every gate **provably able to fail** — mutation tests, per-branch fixtures
- enforce ordering **in code** where sequence matters, not by call-site discipline

Mutation-test coverage: 26 (FVP analysis), 28 (RQ3 analysis), 15 (PMU parser),
13 (board harness ordering), plus per-rule negatives throughout.

Two harness defects were caught this way and are now code contracts:
capture listener must be alive **before** `REBOOT`; postflight `USB_OFF` must
follow the reboot, because the reboot re-presents the debug USB card.

---

## 9. Reproduction

```
identity chain   model SHA → Vela SHA → generated .cc BODY SHA → raw AXF SHA (exact) → execution
build identity   pinned source closure + toolchain + SOURCE_DATE_EPOCH
                 + deterministic build path + build arguments
source closure   MLEK b2c0bb2, 0 tracked modifications, 9 pinned dependencies,
                 4 target-subsystem closures (sse-300/310/315/320)
```

Board restore is not "write the backups back": the card had no
`boot.bin`/`bram.bin`, so restore includes **deleting created files** and
restoring overwritten ones. Backup scope is discovered from the card, and the
probe aborts before writing if `images.txt` is not found exactly once.

See `EVIDENCE_INDEX.md` for every digest and tag.
