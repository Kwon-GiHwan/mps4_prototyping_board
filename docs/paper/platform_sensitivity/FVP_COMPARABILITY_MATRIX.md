# FVP comparability matrix — X0 master document

Source-authoritative and runtime-probed map of the platform × NPU × MAC ×
Vela-option × timing-semantics × artifact-portability space, built on the
pinned stack. **No performance comparison is made or implied here.**

## 1. Supported cells

19 platform/NPU/MAC cells classify `SUPPORTED` (FVP init accepts **and** the
value is in the Vela `--accelerator-config` enumeration). Zero cells classify
`ACCEPTED_BUT_NOT_ARCHITECTURALLY_AUTHORIZED` on this stack; zero `UNRESOLVED`.
Full grid in `FVP_CAPABILITY_MATRIX.csv` (48 probe rows).

| FVP | NPU | MAC (SUPPORTED) | TA | FM version | artifact reuse with peers | comparison class |
| --- | --- | --- | --- | --- | --- | --- |
| SSE-300_Ethos-U55 | U55 | 32, 64, 128, 256 | `TA_ON` | 11.22.35 | identical NPU artifact ↔ SSE-310 | **B** (with SSE-310) |
| SSE-300_Ethos-U65 | U65 | 256, 512 | `TA_ON` | 11.22.35 | identical NPU artifact ↔ SSE-310/315 | **B** (with SSE-310/315) |
| SSE-310 | U55 | 32, 64, 128, 256 | `TA_OFF` | 11.24.13 | identical NPU artifact ↔ SSE-300 | **B** |
| SSE-310_Ethos-U65 | U65 | 256, 512 | `TA_OFF` | 11.24.13 | identical NPU artifact ↔ SSE-300/315 | **B**; **A** with SSE-315 |
| SSE-315 | U65 | 256, 512 | `TA_OFF` | 11.31.28 | identical NPU artifact ↔ SSE-300/310 | **A** with SSE-310 (both TA_OFF); **B** with SSE-300 |
| SSE-320 | U85 | 128, 256, 512, 1024, 2048 | `TA_ON` | 11.27.25 | no peer platform for U85 | **X** (no controlled peer) |

MAC values outside each row are `NOT_SUPPORTED` (rejected at FVP init, and
absent from the Vela enumeration) — the two authorities agree on every cell.

## 2. Comparison classes (frozen for X1)

```
CLASS A   same NPU, same MAC, same workload, exact same Vela artifact,
          SAME TA state, different FVP subsystem
          → SSE-310 ↔ SSE-315 for U65 {256,512}   (both TA_OFF)

CLASS B   as A but DIFFERENT TA state
          → SSE-300 ↔ SSE-310 for U55 {32,64,128,256}
          → SSE-300 ↔ SSE-310/315 for U65 {256,512}

CLASS C   same Corstone, different NPU, common MAC point, same TA state
          → SSE-300: U55@256 vs U65@256   (TA_ON both)
          → SSE-310: U55@256 vs U65@256   (TA_OFF both, diagnostic)
          NOTE: memory mode differs by NPU on this stack (see §4) — the
          contrast remains a system-level configuration contrast.

CLASS D   structural/dimensionless metrics only across platform/NPU/FM/TA
          → any comparison involving SSE-320/U85 against another platform

CLASS X   not comparable under current evidence
          → absolute cycles across any platform pair; U65 ↔ U85 with a
            controlled substrate (no such pair exists)
```

Class A is the strongest cell available on this stack and did not exist in the
paper's prior framing: SSE-310 and SSE-315 share TA state, so a U65 comparison
between them isolates the subsystem/FM axis without the TA confound.

## 3. Artifact portability (the load-bearing X1 pre-condition)

From the frozen compile matrix cross-checked against frozen per-cell build
evidence: **70/70 multi-platform pairs have byte-identical Vela artifacts**
(28 groups SSE-300↔SSE-310, 14 groups spanning SSE-300/310/315, expanded to 70
ordered pairs). Not one pair required a different NPU artifact.

```
reuse_class                 FIRMWARE_PLATFORM_SPECIFIC_BUT_NPU_ARTIFACT_IDENTICAL   70/70
vela_artifact_identity      IDENTICAL                                                70/70
host_firmware_identity      PLATFORM_SPECIFIC                                        70/70
same-artifact portability   ESTABLISHED       67    (both platform cells executed)
                            NOT_YET_QUALIFIED  3    (wav2letter/U55 @32/64/128 —
                                                     non-executable on both sides)
```

Per-cell evidence confirms the mechanism: e.g. `rnnoise_INT8__*__ethos-u55-32`
carries `vela_sha_matches_frozen: True` on both SSE-300 and SSE-310, with only
`target_subsystem` differing (`sse-300` vs `sse-310`). The complete NPU program
is therefore identical and only the host firmware is platform-specific. The
phrase "the same binary ran on both" is **not** used.

## 4. Vela option axes

Installed options (probed): Vela 5.0.0; 11 accelerator configs; system configs
`Ethos_U55_High_End_Embedded`, `Ethos_U65_High_End`, `Ethos_U85_SYS_DRAM_{Low,
Mid_512,Mid_1024,High_2048}`; memory modes `Sram_Only`, `Shared_Sram`,
`Dedicated_Sram`.

Compile probe over generation × memory mode (`VELA_MEMORY_OPTION_MATRIX.csv`):

| accelerator | Sram_Only | Shared_Sram | Dedicated_Sram |
| --- | --- | --- | --- |
| ethos-u55-256 | OK | OK | **compile FAILED → NOT_SUPPORTED** |
| ethos-u65-256 | OK | OK | OK |
| ethos-u85-256 | OK | OK | OK |

Every successful mode within a generation produces a **different artifact**
(`DIFFERENT_ARTIFACT` on all comparisons). Two cross-checks against frozen
evidence passed exactly: `ethos-u65-256/High_End/Dedicated_Sram` reproduced the
frozen U65 kws artifact `8b7930df…`, and `ethos-u85-256/DRAM_Low/Dedicated_Sram`
reproduced the frozen U85 kws artifact `7d1431a8…` — the compile stack matches
the frozen environment.

Consequence: memory mode is never a pure runtime intervention, and the U55
ladder cannot use `Dedicated_Sram` at all.

## 5. Workload universe for X1 (`COMMON_WORKLOAD_MATRIX.csv`)

Derived from the frozen 133-cell executability evidence; no workload was re-run.

```
U55  SSE-300 ∩ SSE-310    MAC 32/64/128: 6 common workloads
                          MAC 256:       7 common workloads
     excluded: wav2letter_pruned_int8 at 32/64/128 — NOT_EXECUTABLE_MEMORY on
     BOTH platforms (symmetric; classified MEMORY_LIMIT, 3 cells)

U65  SSE-300 ∩ SSE-310 ∩ SSE-315   MAC 256: 7   MAC 512: 7
```

39 cells `COMMON_EXECUTABLE`, 3 `MEMORY_LIMIT`, 0 `PLATFORM_SPECIFIC_FAILURE`,
0 `UNRESOLVED`. Executability is per-platform; artifact portability is tracked
as a separate column so the two are never conflated.

## 6. PMU / measurement semantics for X1

X1's primary metric remains whole-model `TOTAL`/`CYCLE`, which the stock runner
prints on every platform. `ACTIVE`/`IDLE` are likewise available. The
memory-interface event family remains generation-specific (U55/U65 `AXI*`
versus U85 `EXT*`/`SRAM*`; 18 of 22 shared names differ in ordinal), so no
cross-generation memory-event comparison is planned. No per-layer profiling is
planned for X1.
