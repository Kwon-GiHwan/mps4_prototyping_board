# Stage 2A-F2 (PMCLUT) and 2B-0 (NPU_OP_PMU_MASK) — board results

Contract `evidence/s2_probe/contract.md` (frozen `62cf7f4`, amendment 1 `043e492`). Image `d0cd4775`, **TA profile 1**
in every boot. Boots 158–176 (boot 170 failed at the first PING before any RUN and was re-run as 176, amendment 1);
every measured RUN of every completed boot valid. Raw: `evidence/s2_probe/raw/{lut,mask}/`.
Verdicts: `python3 host/analysis/s2_probe.py evidence/s2_probe/raw/lut evidence/s2_probe/raw/mask results/fi101_stage2_probe`.

## 2A-F2 — PMCLUT: preregistered outcome

**`LUT_IDENTITY_EXACT`** (boot 158, kws): with the LUT selecting event 1, counter 0 equalled event 1's own counter in
every measured RUN of all six sets. PMCLUT works on this board as the TRM describes.

Overlap, fraction f = cycles with both events / cycles of event 1 (median of 8 RUNs), all seven models (`lut_overlap.csv`):

| model | MAC act ∧ IB stall | MAC act ∧ W stall | AO act ∧ BS/OB stall | WD act ∧ WD stall | NPU act ∧ blockdep | MAC act ∧ AO act |
| --- | --- | --- | --- | --- | --- | --- |
| kws | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.664 PARTLY |
| ad | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.850 PARTLY |
| rnnoise | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.013 IDLE |
| vww4 | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.394 PARTLY |
| yolo | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.513 PARTLY |
| mobilenet | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.607 PARTLY |
| wav2letter | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 0.000 IDLE | 1.000 ACTIVE | 0.903 ACTIVE |

IDLE = `STALL_WHILE_IDLE` (f ≤ 0.1), ACTIVE = `STALL_WHILE_ACTIVE` (f ≥ 0.9), PARTLY = `PARTLY_WHILE_ACTIVE`; for the last
two columns the class names are kept although the events are not stalls (contract).

Reading — `POST_HOC_DESCRIPTIVE`:
1. **A unit's stall cycles and its active cycles never coincide** (exactly 0 in all 28 cells): a stall event counts
   cycles in which the unit is *not* working and is held by that reason. So `stall / npu_active` is the share of the
   inference in which the unit waited for that reason — a breakdown of its non-active time. This corrects reading 1 of
   `results/fi101_stage2a/` (see the correction there).
2. `cc_stalled_on_blockdep` is counted only while the NPU is active (f = 1.000).
3. **MAC/AO concurrency** (share of AO-active cycles in which the MAC is also active) orders the models as their Stage 1
   active-cycle MAC efficiency does: wav2letter 0.90, ad 0.85, kws 0.66, mobilenet 0.61, yolo 0.51, vww4 0.39,
   rnnoise 0.01.

## 2B-0 — NPU_OP_PMU_MASK: preregistered outcome **`MASK_DISTURBS`**

| model | passthrough (m_all vs ctl, ≤ 1 %) | additive (m_a + m_b vs m_all, ≤ 1 %) | verdict | default state |
| --- | --- | --- | --- | --- |
| kws | **false** | false | `MASK_DISTURBS` | `MASK_DEFAULT_OFF` |
| mobilenet | true | true | `MASK_WORKS` | `MASK_DEFAULT_OFF` |

Overall `MASK_DISTURBS` (the worst model decides).

Reading — `POST_HOC_DESCRIPTIVE`:
1. **mobilenet:** m_all equals ctl within 0.05 % on every event and on NPU cycles; m_a + m_b equals m_all exactly for
   `mac_active` (133,504 + 441,291 = 574,795) and `mac_dpu_active`, within 1 % for the rest. **PMCCNTR is gated too**
   (m_none: 0 cycles), and the mask starts disabled.
2. **kws fails on its own RUN-to-RUN jitter, not on a visible disturbance.** Events fixed by the command stream are
   identical (`mac_active` 56,450, `mac_dpu_active` 49,495, `ao_active` ±2 in every arm), but the time-dependent ones
   move by more than 1 % between boots: `npu_active` ctl 90,029–91,761 vs m_all 89,448–91,778 (ranges overlap for every
   event). kws's own spread in fi101_s013 was 2.9 % (`results/fi101_stage2a/run_spread.csv`); the contract's 1 % band
   was narrower than that — a design error in the contract, recorded, not changed after the data.
3. In kws, m_a + m_b misses 29 of 56,450 MAC-active cycles (−0.05 %) and NPU cycles by −3.4 %: at a mid-stream
   boundary in a short model some cycles fall outside both parts (the command processor parses ahead of execution and
   ops overlap via BLOCKDEP). In mobilenet the split is exact for MAC cycles.
4. Already visible with the split: mobilenet's `mac_stalled_by_w` sits almost entirely in the second half of the
   stream (208,935 of 209,428 cycles).

## What this means for Stage 2B

- PMCLUT is usable: overlap measurements (e.g. "MAC active while EXT read stalled") are available per RUN.
- The mask path gates counting along the command stream and is exact for command-determined events on mobilenet. The
  preregistered verdict does not clear it: kws fails the 1 % band. Before Stage 2B relies on it, a confirmation with a
  jitter-aware criterion (e.g. against the control's own RUN range, more RUNs on short models) is needed, preregistered
  before its data.
