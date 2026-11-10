# Stage 4A/4B — operator type and channel alignment, isolated operators (frozen 2026-11-10, before boot 330)

Owner directive 2026-11-10 ("Stage 4 — Operator & Channel Alignment Characterization", 4A/4B minimum only) and the
owner's output-check decision (same day, below). **TA: MLEK's own sys_dram_mid set-up = TA profile 1.** Ethos-U85 1024
MAC on FI101. Official Ethos-U core driver (driver runner), WAIT_WFE (MLEK's wait). INT8. Vela 5.0.0 with MLEK's
options (Dedicated_Sram, Ethos_U85_SYS_DRAM_Mid_1024). Per config and PMU pass: 1 warm-up + 4 measured RUNs
(`config/driver_r5.json`). No QREAD, PMU mask, IRQ tracing, TA change, new model, or new PMU event set.

## Question

On FI101, how do Conv2D, DepthwiseConv2D and FullyConnected differ in execution (RQ4-1), does removing one channel
across a 16-channel boundary change cycles and MAC activity beyond the MAC-count change (RQ4-2), and how do Vela's
schedule and estimates relate to the board (RQ4-3)? **Not asked:** per-layer time of the source models; operator
baselines are a technical comparison of different MAC counts, not a controlled causal comparison.

## Configurations (Phase 1; `results/fi101_stage4/stage4_experiment_matrix.csv`)

Selection (static, from `stage4_operator_inventory.csv`): per operator, the first model in the owner's order with a
candidate whose TFLite operator compiles to one NPU operation with cycles (a fused activation of 0 cycles allowed),
then Cin and Cout multiples of 16, then the most MACs, then the lowest op index.

| config | source | shape | MACs |
| --- | --- | --- | ---: |
| conv_base | yolo-fastest op 36 | Conv2D 1×1, stride 1, VALID, RELU6, 1×24×24×16 → 96 | 884,736 |
| conv_cin15 | derived | Cin 15 | 829,440 |
| conv_cout95 | derived | Cout 95 | 875,520 |
| dw_base | mobilenet_v2 op 7 | DWConv 3×3, stride 1, SAME, multiplier 1, RELU6, 1×56×56×144 | 4,064,256 |
| dw_c143 | derived | C 143 | 4,036,032 |
| fc_base | rnnoise op 0 | FC 96 → 288, no activation | 27,648 |
| fc_in95 | derived | in 95 | 27,360 |
| fc_out287 | derived | out 287 | 27,552 |

Every other variable is held: H/W, kernel, stride, padding, activation, quantization policy (Stage 1's, OFM scale
data-derived per config), seeds, Vela options, memory mode, runner image, TA profile 1. MACs and sizes change with the
channel and are recorded.

## Gate B (Phase 2, done before this freeze): all 8 PASS — `results/fi101_stage4/stage4_compiler_report.md`

## Output check (owner decision: CPU reference + at most 1 LSB; Stage 4 isolated operators only)

Reference = tflite_runtime on the same model, IFM (seed 1), weights, bias and quantization (the DRWL golden). The NPU
output of the last RUN of each config is read back (`GET_OUTPUT`); every RUN's output CRC is recorded.

| verdict | condition |
| --- | --- |
| `INVALID` | output length ≠ shape or reference, RUNs' output CRCs differ from each other or from the read-back output, or the firmware's mismatch count / max diff (against the same reference) disagrees with the host's |
| `PASS_EXACT` | every element equal |
| `PASS_TOLERANCE` | max \|diff\| ≤ 1 LSB |
| `FAIL` | any element differs by > 1 LSB |

Recorded: max / mean \|diff\|, mismatch count and ratio, 1-LSB and > 1-LSB counts, CPU/NPU sha256, NPU and CPU
min/max, values at 127 / −128 / the RELU6 cap, mismatches at saturation, channels with mismatches and the top
channel's share, scales and zero points. A 1-LSB tolerance is a practical criterion, not bit-exactness; a difference is
not called rounding without checking. The tolerance is not widened after the data. The model-level byte-exact rules of
Stage 1/3 are unchanged.

## Gate C (per config)

Output `PASS_EXACT` or `PASS_TOLERANCE`, every measured RUN valid (`record_v2.validity`: completed, invoke ok, one arm,
one IRQ, no overflow, job OK, codes echoed, rc 0), both passes with 4 measured RUNs. A failing config keeps its raw
data, leaves every comparison, and is not re-run.

## PMU passes (`ids.txt`; reused, not new)

- Set 1 = Stage 1 pass A: 35 npu_active, 48 mac_active, 51 mac_dpu_active, 53, 55 (not in TRM 110 — reported only),
  64 ao_active, 80 wd_active, 81 wd_stalled.
- Set 2 = Stage 3 pass B: 35, 128 sram_rd_trans_accepted, 130 sram_rd_data_beat_received, 132 sram_wr_trans_accepted,
  135 sram_wr_data_beat_written, 384 ext_rd_trans_accepted, 386 ext_rd_data_beat_received, 391 ext_wr_data_beat_written.

## Rules (`host/analysis/stage4.py`, tests `host/tests/test_stage4.py`; mutation results below)

- Metrics (medians of 4 measured RUNs, pass A unless said): NPU_ACTIVE; MAC_ACTIVE, MAC_DPU_ACTIVE, AO_ACTIVE,
  WD_ACTIVE, WD_STALLED per NPU_ACTIVE; MACs / NPU_ACTIVE; MACs / (1024 × MAC_ACTIVE) (a MAC-count efficiency, not a
  measured lane occupancy); pass-B traffic. RUN ranges kept beside every median.
- Pair (base vs variant, Gate C PASS both): tol = max(1 % of the base median, either RUN range) of NPU_ACTIVE.
  |variant − base| ≤ tol → `UNRESOLVED`; else expected = base × MACs(variant)/MACs(base): |variant − expected| ≤ tol →
  `CONSISTENT_WITH_MAC_CHANGE`, else `NOT_PROPORTIONAL_TO_MAC`. Beside it: `schedule_changed` (Vela OFM block, ublock or
  kernel count differ) and `traffic_changed` (any pass-B event beyond the same rule). Otherwise `EXCLUDED`.
- Vela vs board: Vela's per-operator estimate (op cycles = max of compute and memory estimates; NPU cycles = compute)
  is compared with NPU_ACTIVE only as a ratio, after stating that NPU_ACTIVE also covers command-stream setup, weight
  and IFM/OFM DMA and the driver's job; it is not called an estimation error.
- Phase 5 links to the seven models are labelled `OBSERVED` / `CONSISTENT_WITH` / `NOT_SUPPORTED` / `UNRESOLVED`; no
  cause of a model's efficiency is concluded from isolated operators.

## Boots — `plan.txt`: 330–337, one per config, conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

Image: driver runner of this commit (adds `GET_OUTPUT`; the RUN path is unchanged), digests in `image.sha256`.

## Stop conditions

A boot failing before its RUNs: keep the data, continue with the next boot (no re-run); report. No Stage 4C/4D, no
extra repeats, no other shapes.

## Cost

8 boots × (reboot + upload ≤ 0.9 MB + 10 RUNs + DW output read-back ≈ 0.45 MB) ≈ 25–35 min, plus one deploy/restore
session ≈ 5 min.

## Mutation test

`evidence/stage4/mutate_stage4.py`: 18 mutations (output verdict bounds, INVALID terms, Gate C, pair rule, floor,
range tolerance, MAC expectation, schedule/traffic flags, EXCLUDED, counts; GET_OUTPUT CRC, offset, state). First pass
16/18 RED; the survivors (1 % floor, 1-LSB count) got fixtures; rerun 2/2 RED → **18/18 RED**, restored by digest.
