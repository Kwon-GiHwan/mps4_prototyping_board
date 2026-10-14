# Stage 2A — isolated-operator component attribution (frozen 2026-10-14, before any Stage 2A golden, blob or boot)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Data from the TA reset state or any
other profile is never mixed into this dataset.

Purpose: component-level evidence for the Stage 1 differences between conv3x3, dw3x3 and pw1x1. Each hypothesis gets
a status from a closed set, and each operator is routed to Stage 3 or Stage 4. **No memory bottleneck is decided
here, and correlation alone decides no cause.**

Questions:
1. In DWConv and PWConv, which component or dependency state goes with the cycles where the MAC is not active?
2. Does DWConv's low active-cycle efficiency go with low DPU activity?
3. PWConv is efficient while the MAC is active. Why is its MAC-active interval short?
4. Which counter differs most from conv3x3?

## 1. Configuration (unchanged from Stage 1)

- Profile `config/mlek_baseline.json`: Vela 5.0.0 with MLEK options, ethos-u85-1024, Dedicated_Sram,
  Ethos_U85_SYS_DRAM_Mid_1024, TA profile 1, AXI SRAM 0x20F0B / EXT 0x21F3F, fast scratch on-chip 0x31100000,
  POWER_CTRL 0.
- Image APP `2c2fa435…` (the Stage 1 image). The event set is passed at run time (`run_campaign.sh <ids>`), so no
  compile or runtime change is made.
- 35 RUNs per boot: RUNs 1–5 warm-up, RUNs 6–35 measured. One boot per operator: conv3x3 boot 75, dw3x3 boot 76,
  pw1x1 boot 77.
- Nothing else is run until Stage 2A is reported: no mobilenet, kws, ad_medium or fc1024, no Stage 2B, no AXI-latency
  pass, no shape sweep.

## 2. PMU event set (`config/stage2a_ids.txt`) — owner decision of 2026-10-14

| # | id | name | semantics source |
| --- | --- | --- | --- |
| 1 | 35 | npu_active | TRM |
| 2 | 48 | mac_active | TRM |
| 3 | 51 | mac_dpu_active | TRM |
| 4 | 52 | mac_stalled_by_w_or_acc | **driver-derived** (MAC_STATUS bit 4, "MAC stalled by WB or AB (not IB)") |
| 5 | 55 | mac_stalled_by_ib | **driver-derived** (MAC_STATUS bit 7, "MAC stalled by IB") |
| 6 | 64 | ao_active | TRM |
| 7 | 80 | wd_active | TRM |
| 8 | 81 | wd_stalled | TRM |

**Change from the Stage 2A guide, recorded before any data.** The guide's event 33 `cc_stalled_on_blockdep` failed the
source-level semantics check (`event_semantics_audit.md`). By owner decision it is left out of Stage 2A, and event 52
`mac_stalled_by_w_or_acc` takes its slot. Event 33 is kept for a later, separate dependency analysis once its meaning
is confirmed. Consequence: guide Pattern 3 (command/pipeline dependency) is **not measured** in Stage 2A.

**Driver-derived events (52, 55).**
- Their conditions come from the MAC_STATUS bit comments in the driver header. That the PMU event counts the status
  bit once per cycle is a structural inference that no source states.
- They are auxiliary evidence. Neither event alone can make a hypothesis `SUPPORTED`; the most it can give is
  `PARTIAL_SUPPORT` (owner decision for 55; applied to 52 on the same grounds).
- In Stage 2A attribution through them cannot be strengthened. That would need a TRM-documented component or memory
  event pointing the same way, and this set has none that measures input or accumulator supply.

PMCCNTR is stored per RUN as `pmccntr`. NPU execution cost is `npu_active`. The name ↔ id mapping is written into
`summary.json`.

## 3. Workloads and correctness (amendment 2, `docs/specs/mlek-baseline.md`)

Every RUN: custom FI101 OFM == MLEK FI101 OFM on MLEK's input, byte-exact. Manifest `evidence/stage2a/manifest.json`
fixes the blob, cms, input and golden sha256 and the knob words. It is committed before boot 75.

| operator | blob | input / golden |
| --- | --- | --- |
| conv3x3 | the Stage 1 amendment-2 blob of boot 72 (`5fcc9599…`), byte-identical | MLEK input `e5164a0f…`, golden `603ffd70…` (`evidence/stage1/a2/mlek_golden/conv3x3`) |
| pw1x1 | the Stage 1 amendment-2 blob of boot 73 (`781b6fe3…`), byte-identical | MLEK input `e5164a0f…`, golden `942e6cd7…` |
| dw3x3 | **new** amendment-2 blob, built from the Stage 1 model and cms (`ef0e4326…`) | **new MLEK FI101 golden**: boot 69 passed under the TFLite-exact R3, and amendment 2 says a new boot of such a workload needs an MLEK golden first |

The dw3x3 golden follows the fixed amendment-2 procedure: MLEK b2c0bb2 inference_runner, stage-B options plus
`-DVERIFY_TEST_OUTPUT=1`, the authorised 6-line verification-only fix (sources restored by sha256), and the
`std::rand()` input dumped on FI101. It must pass G1–G5 (`host/analysis/mlek_golden.py`) against the Stage 1 frozen
dw3x3 entry, model `5b6b86cc…` and cms `ef0e4326…`. If any check fails, dw3x3 is not measured and Stage 2A stops. The
TFLite difference is recorded as a diagnostic only. No MLEK performance number from that build is used.

**Input change for dw3x3:** Stage 1 boot 69 used the seed-1 input, and Stage 2A uses MLEK's input. Only dw3x3 changes
input between the two stages; conv3x3 and pw1x1 have the same blob as in Stage 1.

## 4. Per-RUN gate (`host/analysis/stage2a.py`, on `host/analysis/stage1.py`)

- Boot checks:
  - B1: image.
  - B2: blob, cms and knobs.
  - B3: requested ids == `config/stage2a_ids.txt`, complete coverage, no refusal, 35 RUNs.
  - B4: IFM and golden sha256 == the manifest's, otherwise `INVALID`.
- Per-RUN checks: R1–R5, plus R6s (`mac_active ≤ npu_active`), exactly as in Stage 1.

Any failed check makes the operator `UNRESOLVED`, and Stage 2A stops (§10). Every RUN is written to `per_run.csv`
either way.

**Diagnostic sanity checks: recorded per RUN, never used for validity.** The mutual exclusivity they assume is stated
only in driver comments, and the event ↔ status-bit mapping is unconfirmed (owner decision).
- S1: `mac_active + mac_stalled_by_ib ≤ npu_active`.
- S2: `mac_active + mac_stalled_by_ib + mac_stalled_by_w_or_acc ≤ npu_active`.
- S3: `mac_dpu_active ≤ npu_active`.

Each operator reports the number of measured RUNs that violate each check.

## 5. Stage 1 reproduction (guide §10) — preregistered rule

References are the Stage 1 fingerprints: conv3x3 boot 72 and pw1x1 boot 73 (same blob, input and image), and dw3x3
boot 69 (seed-1 input; see §3).
- `MAC_ACTIVE`: the reference is deterministic (min == max), so every measured Stage 2A RUN must equal it.
- `NPU_ACTIVE`: the Stage 2A median must lie within the reference's measured [min, max].

Result: `REPRODUCED` when both hold, otherwise `NOT_REPRODUCED`. A `NOT_REPRODUCED` operator is not interpreted, and
Stage 2A stops (§10). For dw3x3, a `NOT_REPRODUCED` cannot separate the input change from the PMU-set change, and it
is reported as such.

## 6. Metrics (per measured RUN, then median / mean / sample sd / CV / min / max over RUNs 6–35)

| | metric | definition |
| --- | --- | --- |
| A | mac_active_ratio | mac_active / npu_active |
| B | dpu_active_ratio | mac_dpu_active / npu_active |
| C | dpu_given_mac_active | mac_dpu_active / mac_active. Not a sub-ratio: 51 is not stated to be contained in 48, so C may exceed 1 |
| D | ao_active_ratio | ao_active / npu_active |
| E | wd_active_ratio | wd_active / npu_active |
| F | wd_stalled_ratio | wd_stalled / npu_active |
| G | mac_ib_stall_ratio | mac_stalled_by_ib / npu_active (driver-derived) |
| H | mac_w_or_acc_stall_ratio | mac_stalled_by_w_or_acc / npu_active (driver-derived; replaces the guide's blockdep ratio) |
| I | mac_active_cycle_efficiency | N_MAC / (1024 · mac_active), from Stage 2A's own mac_active |

Shown beside them, labelled as **Stage 1, separate dataset** (boot 72 / 69 / 73): peak MAC efficiency, MAC
active-cycle efficiency, SRAM beat/MAC and EXT beat/MAC.

**Interpretation limits.**
- Counters can coincide in a cycle, so ratios are never summed into a 100 % time decomposition.
- `npu_active` minus the counters is never called "unknown time".

## 7. Comparison (guide §9)

The pairs are dw3x3 vs conv3x3, pw1x1 vs conv3x3, and dw3x3 vs pw1x1. Each metric is reported with the median ratio to
its reference. There are no absolute thresholds. Separation is defined by the run-to-run spread:
- `HIGHER`: the operator's min > the reference's max.
- `LOWER`: the operator's max < the reference's min.
- `OVERLAP`: otherwise.

Hypothesis status is judged against conv3x3 only, the high-efficiency reference. dw3x3 vs pw1x1 is descriptive.

## 8. Hypotheses and status rules (operators dw3x3 and pw1x1; closed set)

`ΔI` is the excess MAC-inactive share: conv3x3's median mac_active_ratio minus the operator's.

**MAC-inactivity hypotheses (guide patterns 1–4).**
- Precondition: the operator's mac_active_ratio is `LOWER` than conv3x3's. If it is not, these hypotheses are
  `UNRESOLVED`.

| id | hypothesis (guide pattern) | counter | type |
| --- | --- | --- | --- |
| H1 | weight decoder / weight supply (P1) | F wd_stalled_ratio | TRM |
| H2 | input buffer / data supply (P2) | G mac_ib_stall_ratio | driver-derived |
| H3 | command / pipeline dependency (P3) | event 33, not measured | — |
| H3b | weight- or accumulator-buffer back-pressure on the MAC (new, replaces P3 in this set) | H mac_w_or_acc_stall_ratio | driver-derived |
| H4 | output / activation-side work during MAC inactivity (P4) | D ao_active_ratio | TRM |

Status, given the precondition:
- Counter `HIGHER` and median excess (operator − conv3x3) ≥ ΔI, so the counter could cover the whole excess
  inactivity:
  - TRM counter: `SUPPORTED`.
  - Driver-derived counter: `PARTIAL_SUPPORT`.
- Counter `HIGHER`, but the median excess < ΔI:
  - TRM counter: `PARTIAL_SUPPORT`.
  - Driver-derived counter: `CORRELATED_ONLY`.
- Counter `OVERLAP` with operator median > conv3x3 median: `UNRESOLVED`.
- Counter `LOWER`, or `OVERLAP` with operator median ≤ conv3x3 median: `REFUTED`.
- H3 is always `UNRESOLVED` (not measured).

Each comparison takes one counter at a time against ΔI. Counters are never added together.

**Active-cycle-efficiency hypotheses (guide pattern 5 and question 2).**
- Precondition: I (mac_active_cycle_efficiency) is `LOWER` than conv3x3's. If it is not, these hypotheses are
  `REFUTED` (the operator has no low active-cycle efficiency).

| id | hypothesis | status |
| --- | --- | --- |
| H5 | spatial packing / operator parallelism / shape mapping (P5) | `SUPPORTED` if C is not `LOWER` and none of F, G, H is `HIGHER`. `UNRESOLVED` if C is not `LOWER` but any of F, G, H is `HIGHER` (temporal stalls present too). `REFUTED` if C is `LOWER` |
| H6 | low active-cycle efficiency goes with DPU inactivity inside MAC-active cycles (question 2) | `SUPPORTED` if C is `LOWER`. `REFUTED` if C is `HIGHER`. `UNRESOLVED` on `OVERLAP` |

**Pattern 6.** An operator with none of H1, H2, H3b, H4 at `SUPPORTED` or `PARTIAL_SUPPORT` gets "component-level
evidence 없음" for its low MAC activity.

## 9. Routing (preregistered)

| outcome | route |
| --- | --- |
| H1 at SUPPORTED / PARTIAL_SUPPORT | Stage 3: weight-stream supply (WD stall split 83–85, weight-read request stall / latency on the port carrying weights) |
| H2 at PARTIAL_SUPPORT / CORRELATED_ONLY | Stage 3: IFM supply (SRAM/EXT read request stall, outstanding, AXI latency on the IFM channel), with a TRM-documented event to confirm the driver-derived signal |
| H3b at PARTIAL_SUPPORT / CORRELATED_ONLY | Stage 3: split 52 into 53 / 54 alongside weight-supply counters |
| H4 at SUPPORTED / PARTIAL_SUPPORT | Stage 3: output/write side (AO stall split 67–72, write request stall) |
| H5 SUPPORTED | Stage 4 shape sweep |
| H6 SUPPORTED | Stage 4 shape sweep (DPU occupancy vs channel count) |
| Pattern 6 | Stage 3: SRAM/EXT request stall, outstanding and AXI latency |

An operator can route to more than one stage. `routing.md` names each target and its reason.

## 10. Stop conditions (guide §13)

Stage 2A stops and reports, with no further experiment, if any of these occurs:
- the dw3x3 golden fails G1–G5;
- any gate check fails: output correctness, TA/profile read-back (knobs) or PMU overflow;
- an operator is `NOT_REPRODUCED`;
- a new compile or runtime change is needed.

## 11. Outputs (`evidence/stage2a/`)

- `contract.md`, `event_semantics_audit.md`, `manifest.json`, `mlek_golden/dw3x3/`, `raw/`
- `per_run.csv`, `summary.csv`, `summary.json`
- `component_fingerprint.md`, `hypothesis_status.md`, `routing.md`

Analysis command: `python3 host/analysis/stage2a.py evidence/stage2a/raw evidence/stage2a`.
