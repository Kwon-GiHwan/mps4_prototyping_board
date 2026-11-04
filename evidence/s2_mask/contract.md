# Stage 2B-0b — NPU_OP_PMU_MASK confirmation with a jitter-aware criterion (frozen 2026-11-03, before boot 177)

Plan: `docs/plan/stage2_plan.md`. Owner 2026-11-03: "큰 작업 말고는 끝날 때까지 … 알아서 작업하자" (after the 2B-0
report that recommended this confirmation). **TA profile 1** (MLEK sys_dram_mid) in every boot. Cost clock = NPU
cycles (S0-3).

Why: 2B-0 (`evidence/s2_probe/`, verdict `MASK_DISTURBS`, stands) failed kws on a fixed 1 % band that is narrower than
kws's own RUN-to-RUN spread, and had one boot per arm, so a boot-to-boot drift could not be told from a mask effect.
This contract does not change that verdict; it asks the question again with new data.

Question: with `PMCR.mask_en = 1` and `NPU_OP_PMU_MASK` in the command stream, (a) does enabling the mask for the whole
stream leave every count where the control's own variation puts it (passthrough), and (b) do two halves of the stream
add up to the whole (additive)? Asked for **all seven MLEK models**, because Stage 2B-2 will gate groups in all seven.

**Disclosure.** The criterion below was written after seeing the 2B-0 data. Applied to the 2B-0 data with the first
control boot standing in for the second (smoke run, not a verdict), it still gives kws `MASK_DISTURBS`
(`mac_stalled_by_ib` +3.9 % against a control width of 2.1 %; NPU cycles −1.86 % against 1.85 %) and mobilenet
`MASK_WORKS`. It was not tuned to make kws pass.

## Image and blobs

- Image `d0cd4775` (as 2B-0: APP `d0cd47756c0b…c191`, VECTORS `4c11ff9874f3…2bc8a`, DDR `81d37a219a6b…de98`).
- Blobs from the fi101_s013 blob of each model (TA profile 1) by `evidence/s2_probe/make_probe_blobs.py`: `ctl`
  (unchanged), `m_all`, `m_a`, `m_b` as in 2B-0 (split after kernel op n/2), `ctl2` = a byte copy of `ctl`.
  kws and mobilenet blobs are byte-identical to the 2B-0 blobs.

| model | kernel ops n (split) | ctl | m_all | m_a | m_b |
| --- | --- | --- | --- | --- | --- |
| kws_micronet_m | 14 (7) | `f11271cb6a2d` | `5f1a7dc75647` | `c2218c4bd526` | `9e3841eaae36` |
| ad_medium_int8 | 14 (7) | `55fa924c7e60` | `7175ee5bbd18` | `60305fa10996` | `809ffdfab9bc` |
| rnnoise_INT8 | 48 (24) | `5c3990a9c991` | `ce47cdff0b61` | `9442e4f300d4` | `451b0f5bb3b6` |
| vww4_128_128_INT8 | 85 (42) | `b7c15f01c4be` | `db2a354cb503` | `83a3c2b4c521` | `ab83c2c9c691` |
| yolo-fastest_192_face_v4 | 112 (56) | `1f71e47582c5` | `89c350e789dc` | `0734f00b2c8c` | `e5fd0979e802` |
| mobilenet_v2_1.0_224_INT8 | 208 (104) | `0d51cf9eaf86` | `6673ec377dca` | `4e5adb4741f8` | `c472e082eff4` |
| wav2letter_pruned_int8 | 39 (19) | `5b8c9d06dea1` | `5388e4b951fe` | `c8e287954a47` | `e25346b3f614` |

## Boots (`plan.txt`): boots 177–211, set A (`ids_a.txt`, same as 2B-0), **20 RUNs per boot, 2 warm-up, 18 measured**

Per model, in this order: `ctl`, `m_all`, `m_a`, `m_b`, `ctl2` (the second control brackets the masked boots).
Models: kws, ad, rnnoise, vww4, yolo, mobilenet, wav2letter.

A boot that fails before any RUN (no answer to the first PING, as boot 170) is re-run once with the same blob after
the campaign, into the same root; the failed folder is kept. Recorded as an amendment, rules unchanged.

## Rules (preregistered; `host/analysis/s2_mask_confirm.py`, tests `host/tests/test_s2_mask_confirm.py`, 28 mutations RED)

Validity: as fi101_s013 (model mode incl. `knobs_honoured`). Any invalid measured RUN or a missing boot → the model is
`UNPROVEN`. Keys judged: every event of set A plus NPU cycles (`infer_npu_cycles`). Medians over measured RUNs.

1. Width w of a key = (max − min) / median over the RUNs of the **first control boot** (0 if all zero; ∞ if the
   median is 0 and some RUN is not). Class: `DETERMINISTIC` w ≤ 0.1 %; `NOISY` w > 5 % (not judged, reported);
   `JITTERY` otherwise.
2. Tolerance for "same as the control": `DETERMINISTIC` 0.1 %; `JITTERY` max(1 %, w). A zero control median requires
   exactly 0.
3. Preconditions → else `UNPROVEN`: NPU cycles are `DETERMINISTIC` or `JITTERY`; every key of the control is present in
   every arm; **A/A**: `ctl2` median equals `ctl` median within the tolerance for every judged key (otherwise the
   boot-to-boot drift exceeds what the criterion can see).
4. `passthrough`: `m_all` median equals `ctl` median within the tolerance for every judged key (NPU cycles included).
5. `additive`: for every judged event (NPU cycles excluded), median(m_a) + median(m_b) = median(m_all) within
   max(1 %, w).
6. Model: `MASK_DISTURBS` if not passthrough; else `MASK_WORKS` if additive, else `MASK_NOT_ADDITIVE`. Overall:
   `MASK_WORKS` only if all seven work; else the worst of DISTURBS > NOT_ADDITIVE; `UNPROVEN` if any model is.

## What the outcomes mean

- `MASK_WORKS` (overall): Stage 2B can gate groups along the command stream in all seven models, to the stated
  tolerances. It does not say a gated part equals the work of those operators (ops overlap via BLOCKDEP and the command
  processor parses ahead); that is 2B-1's question.
- Per-model `MASK_WORKS` with others not: 2B-2 uses the mask only in the models that work and names the rest.
- `MASK_DISTURBS` / `MASK_NOT_ADDITIVE`: the mask changes execution or loses counts at the split; Stage 2B needs another
  path (split command streams or STOP+IRQ).
- `UNPROVEN` with A/A failing: this board's boot-to-boot drift is larger than the control's within-boot range; the
  question cannot be answered at this RUN count.

## Limits

- The width is the full RUN range of one boot (18 RUNs); it grows with RUN count and with outliers. The claim is
  "indistinguishable from the control's own variation", not "no effect".
- `NOISY` keys are reported, not judged.
- vww4, yolo, wav2letter OFM correctness not claimed (MLEK goldens pending).

## Results (recorded 2026-11-04, after boots 177–211) — `results/fi101_stage2_mask/`

700/700 RUNs valid, no failed boot. A/A holds and passthrough holds in all seven models. Additive holds in ad, yolo,
mobilenet (`MASK_WORKS`) and fails in kws, rnnoise, vww4, wav2letter (`MASK_NOT_ADDITIVE`) → overall
**`MASK_NOT_ADDITIVE`**. Every failing difference is a deficit (m_a + m_b < m_all).

## Amendment 1 (2026-11-04, after the Results; verdict unchanged) — the outcome's meaning for Stage 2B

"What the outcomes mean" read `MASK_NOT_ADDITIVE` as "Stage 2B needs another path". Stage 2B-2 proceeds with the mask
instead, **dropping additivity as a precondition**, for these reasons:

1. The other paths (split command streams, STOP+IRQ between groups) serialise the operators at every group boundary,
   i.e. remove the overlap the NPU uses (BLOCKDEP, parse-ahead). They change the execution being measured; the mask was
   shown not to (passthrough and A/A hold in 7/7).
2. The failure is one-sided and bounded: every miss is a deficit (counts lost at the split, never added), 12–1,980
   cycles per split. That is a measurable quantity, not an unknown error.
3. So 2B-2 measures the loss directly (deficit = unattributed share of NPU-active cycles) and judges group comparisons
   only where |deficit| ≤ 5 % (`evidence/s2_groups/contract.md`, rule 5). Where the deficit is larger the group values
   are lower bounds and the comparisons are `UNPROVEN`.

What this does **not** claim: that a group's count equals the work of its operators, or that the mask partitions the
stream exactly. Recorded by the owner's request ("왜 해당 조건을 빼는지도 기록해놔", 2026-11-04).
