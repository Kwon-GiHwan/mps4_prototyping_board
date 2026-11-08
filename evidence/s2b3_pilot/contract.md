# Stage 2B-3 Phase 3a pilot — single-op PMU mask windows around a reference op (frozen 2026-11-09, before boot 244)

Plan: `docs/plan/stage2b3_plan.md` ("Phase 3a 설계"). Owner 2026-11-09: pilot only — ad, yolo, mobilenet, rnnoise
(the owner chose the subset; the other three, kws, vww4, wav2letter, follow only on a later decision, with the same
rules). **TA profile 1** (MLEK sys_dram_mid) in every boot. Ethos-U85 1024 MAC. No firmware or image change.

Question: when a PMU mask window is opened around one kernel op of the original command stream, where does the MAC
activity of a reference op A land among the windows of A−1, A, A+1 (= B) and A+2? This is a diagnostic of the
window–execution relation. **It does not establish attribution:** no outcome here says a window's counts belong to an
op; exact attribution needs a separate, independent check (Phase 3b, not designed yet).

## Selection (static, before data; `host/analysis/s2b3_select.py`, Phase 1–2 commit `d309bc2`)

A = an op with both neighbours, MACs > 0 and ≥ 4 × each neighbour's MACs, largest contrast MACs / max(neighbour MACs,
1024); ties → more MACs, then earlier. B = A + 1. MACs from the command-stream registers (= Vela's counts). Fewest MAC
cycles = MACs / TRM peak (Table 7, U85-1024, 8-bit: CONV 1024, 2048 with 2:4 sparsity; DEPTHWISE 128; other ops 0).

| model | A / B | fewest cycles A−1 | A | B | A+2 | A / max(others) | statically identifiable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ad_medium_int8 | 5 Conv2D / 6 DWConv | 4,968 | 19,044 | 4,968 | 19,044 | 1.0 | **no** (op 7 = same conv as A) |
| yolo-fastest_192_face_v4 | 99 Conv2D / 100 Resize | 0 | 648 | 0 | 0 | ∞ | yes |
| mobilenet_v2_1.0_224_INT8 | 164 Conv2D / 165 DWConv | 0 | 10,584 | 1,984 | 4,410 | 2.4 | yes |
| rnnoise_INT8 | 37 FC / 38 Add | 0 | 32 | 0 | 0 | ∞ | yes (A is small: 32 cycles) |
| (later) kws_micronet_m | 11 / 12 | 984 | 2,680 | 0 | 2 | 2.7 | yes |
| (later) vww4_128_128_INT8 | 66 / 67 | 0 | 1,224 | 324 | 72 | 3.8 | yes |
| (later) wav2letter_pruned_int8 | 8 / 9 | 63,232 | 2,312,500 | 578,125 | 8,383 | 4.0 | yes |

The selection is not changed after this table (owner). ad is measured as the owner asked; its verdict is
`NOT_IDENTIFIABLE` by rule and its windows are reported descriptively. Fewest cycles are lower bounds; the real
cycles of a depthwise or weight-bound op can be larger, so "identifiable" here is necessary, not sufficient.

## Image and blobs

- Image `d0cd4775` (as 2B-0 … 2B-2). Card read back 2026-11-09 before the campaign (`inspect.sh`, read-only):
  APP `d0cd47756c0b…c191`, VECTORS `4c11ff9874f3…2bc8a`, DDR `81d37a219a6b…de98`.
- Blobs by `make_window_blobs.py` from the 2B-0b `ctl` blobs (digests as in `evidence/s2_mask/contract.md`: ad
  `55fa924c7e60`, yolo `1f71e47582c5`, mobilenet `0d51cf9eaf86`, rnnoise `5c3990a9c991`). Checked: every masked
  stream minus its PMU_MASK words is byte-identical to `ctl`'s; constants identical; only knob word 30 (mask_en) set.
- Window W(k) = `cms.gate(stream, k, k+1)`: PMU_MASK(0) at the start, PMU_MASK(1) right after kernel op k−1's
  instruction (before op k's setup), PMU_MASK(0) right after op k's instruction.
- Arms: `ctl`, `w_prev` = W(A−1), `w_A` = W(A), `w_B` = W(A+1), `w_next` = W(A+2), `u` = A−1 … A+2 in one window,
  wait variant, `ctl2` (byte copy of ctl, after the masked boots: A/A).
- **Wait variant** (same rule everywhere): for the first of A, B whose setup holds a DMA_WAIT or KERNEL_WAIT, the same
  window with PMU_MASK(1) moved to right after the last such wait — mobilenet `w_A_wait` (setup of 164: KERNEL_WAIT n=1,
  DMA_START, DMA_WAIT k=0), rnnoise `w_B_wait` (setup of 38: DMA_START, DMA_WAIT k=0); ad, yolo: none (`NOT_APPLICABLE`).

## Boots (`plan.txt`): 244–273, sets A, C, D (`ids.txt` = 2B-2's), 10 RUNs per set, 2 warm-up

Per model: ctl, w_prev, w_A, w_B, w_next, u, [wait variant], ctl2. Models: ad, rnnoise, yolo, mobilenet. A boot that
fails before any RUN is re-run once after the campaign into the same root (amendment, rules unchanged).

## Rules (preregistered; `host/analysis/s2b3_windows.py`, tests `host/tests/test_s2b3_windows.py`, 21 mutations RED)

Validity as fi101_s013 (model mode incl. `knobs_honoured`). Medians over measured RUNs. M_k = median `mac_active`
(event 48, set A) of W(A+k), k = −1, 0, 1, 2; S = A's fewest MAC cycles; T = Σ M_k.

1. **Static:** S ≤ max(fewest cycles of A−1, A+1, A+2) → `NOT_IDENTIFIABLE` (decided above, before data).
2. **Preconditions** → else `UNPROVEN`: every RUN of every arm valid and the arms ctl, ctl2, w_prev, w_A, w_B,
   w_next, u present; **A/A**: ctl2 = ctl for every key of every set plus NPU cycles and CPU inference cycles
   (2B-0b tolerance: deterministic 0.1 %, jittery max(1 %, ctl's RUN width), noisy > 5 % not judged); **no
   disturbance**: every masked arm's median CPU inference cycles (`infer_cpu_cycles`, not gated by the mask) = ctl's
   within that tolerance (CPU cycles must be judged, i.e. not noisy); **output**: every masked arm's OFM comparison
   (mismatch count, max abs diff) equal to ctl's in every RUN, and ctl's the same in all its RUNs.
3. **Diagnosis** from the medians: T < S → `NOT_IDENTIFIABLE`; exactly one k with M_k ≥ S and T − M_k < S →
   `WINDOW_LOCALIZED(k)`; no k with M_k ≥ S → `WINDOW_SPLIT`; otherwise `WINDOW_AMBIGUOUS`.
4. **Stability:** the diagnosis is repeated per measured RUN (RUNs of the four window arms paired by rep); any rep with
   another result, or no rep present in all four → `UNSTABLE`.
5. Across models: reported side by side. A shared `WINDOW_LOCALIZED(k)` is reported as such; different offsets or
   diagnoses are reported as they are, never forced to a common rule.

## Reported, not judged (descriptive, rules fixed now)

- Per model, arm, set and event: median and RUN width (`windows.csv`); ctl `npu_active` and NPU cycles.
- Event pattern: for every event of sets A, C, D, each window's share of Σ of the four windows, and Σ / u (local
  partition at the A boundary). Read: does each event concentrate in the same window as mac_active?
- B window: mac_active of W(B) against B's fewest cycles (0 for rnnoise Add and yolo Resize). **Not evidence of
  misattribution by itself:** an op with no MACs may still do MAC block traversal (owner).
- Wait variant: its counts against the matching window (activity between the window opening and the end of the wait).
- OFM against the golden: ad, mobilenet, rnnoise golden = MLEK FI101 (0 mismatches expected as in 2B-0b); yolo's golden
  is pending (MLEK golden not yet taken), so only "same as ctl" is claimed.

## What the outcomes mean

- `WINDOW_LOCALIZED(k)`: only window A+k can hold A's minimum MAC cycles. k = 0: activity concentrates where the
  window sits; k = +1/+2: it concentrates one/two windows late. It does not say the counts in that window are A's.
- `WINDOW_SPLIT`: no single window can hold A's minimum: the work of A is spread over windows (overlap at the window
  edges). `WINDOW_AMBIGUOUS`: more than one window could hold it. `UNSTABLE`: the location changes RUN to RUN.
- `NOT_IDENTIFIABLE`: this window set cannot locate A (static, or A's minimum not inside the four windows).
- `UNPROVEN`: a precondition failed (invalid RUN, drift, disturbance or output change).

## Limits

- Fewest cycles are lower bounds from the TRM's peak table; activity of other ops in a window is not bounded from above.
- The mask's application time is not documented (TRM: "debug feature only"); this pilot observes it, it does not model it.
- Four models only (owner's pilot). kws, vww4, wav2letter: same rules, later decision.

## Results (appended after boots 244–273; rules above unchanged)

Campaign 2026-11-08 15:36–18:29 UTC (board clock), 30/30 boots `campaign exit=0`, none re-run. TA profile 1.
Analysis `host/analysis/s2b3_windows.py` as frozen; full report `results/fi101_stage2b3/pilot/README.md`.

| model | M(−1) | M(0) | M(+1) | M(+2) | S | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| ad_medium_int8 | 13,912 | 6,095 | 19,835 | 6,143 | 19,044 | NOT_IDENTIFIABLE (static; preconditions also hold) |
| mobilenet_v2_1.0_224_INT8 | 1,423 | 10,584 | 10,584 | 3,333 | 10,584 | WINDOW_AMBIGUOUS |
| rnnoise_INT8 | 0 | 8 | 0 | 144 | 32 | WINDOW_LOCALIZED(+2) |
| yolo-fastest_192_face_v4 | 1,512 | 72 | 648 | 0 | 648 | WINDOW_AMBIGUOUS |

Preconditions held for every model (all RUNs valid, A/A, no CPU disturbance, OFM = ctl in every arm and RUN; ad,
mobilenet, rnnoise (0, 0) = MLEK golden; yolo (955, 7) = ctl). Per-RUN diagnoses equal the median diagnosis (no
`UNSTABLE`). No shared offset. None of this attributes counts to an op.
