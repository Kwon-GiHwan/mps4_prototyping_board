# Ethos-U85 first-pass performance screening (contract)

Frozen 2026-10-12, **before any data exists**. Authorization: owner, 2026-10-12 ("일단 내 의견 물을 필요없이
끝까지 한번 진행하고, 이후에 내 피드백을 받아"), on the owner's screening guideline (pasted in chat).
Analysis code `host/screening_metrics.py` is committed with this contract and not changed after the data exists;
any change is an amendment.

## What the guideline asks, and what this environment allows

| guideline item | here | why |
| --- | --- | --- |
| event numbers #4, #5, #36… | **by name**: `npu_active` 35, `mac_active` 48, `ext_rd_data_beat_received` 386, `ext_wr_data_beat_written` 391, `ext_rd_tran_req_stalled` 387, `ext_wr_tran_req_stalled` 392, `ext_wr_data_beat_stalled` 393, `ext_enabled_cycles` 396 | the guideline's numbers are not U85 ids; all 8 are TRM-described |
| 8 counters in one run | yes — one set of 8, so all 8 come from the **same** run | U85 has 8 PMEVCNTR |
| PMCCNTR | `npu_pmu_window_cycles` (the CPM-seam snapshot) | |
| PMCCNTR boundary | opens when the runner arms the PMU (before `__wrap_test_u85`), closes at the vendor's "Testing CPM signals" seam after the NPU IRQ. **Includes CPU staging copies** (cms, weights, IFM into DRAM; OFM poison) and the vendor's register setup; excludes UART and host | fixed by firmware `0f215ef5…`; same for every workload |
| latency_ms | **N/A** — reported in cycles only | the FI101 NPU clock is not verified; Vela's 500 MHz is an assumption of its system config, not the board |
| bytes per beat | **N/A** — beats only | AXI data width not verified on this board |
| configured_MAC_count | 1024 (config value: Vela `ethos-u85-1024`, FI101 app note 109762 "1024 MAC") | peak = 1024 int8 MACs/cycle is the Vela convention; **not verified against the TRM** — M3 is labelled with this |
| warm-up 5–10, 30 measured | 35 RUNs per workload; RUNs 1–5 are warm-up and excluded, 6–35 measured | runner `--repeats 35` (host change only) |
| vela_predicted_cycles | Vela 5.0 summary `cycles_total` (also `cycles_npu` reported), packer's options (`Ethos_U85_SYS_DRAM_Low`, `Dedicated_Sram`) | |

Scope rules that follow from the boundary:

- **M1 latency = `npu_active` cycles** (NPU running). PMCCNTR is reported as `window_cycles`, never as latency.
- **M2 `npu_active / PMCCNTR`** is computed but reads "share of this window", not NPU utilisation and not CPU
  overhead: the window contains staging copies whose length scales with the blob, not with inference.
- **M7 compares Vela with `npu_active`**, not with PMCCNTR. Vela also models a 500 MHz core with DRAM at 0.47× core
  clock; the FPGA's clock ratio is unknown, so M7 mixes model error with this system mismatch. That is stated with
  every M7 value.

## Workloads (dissimilar on purpose; not a sweep)

| workload | character | MAC ops / other | N_MAC (formula) | Vela nn_macs | Vela cycles_total |
| --- | --- | --- | --- | --- | --- |
| `kws_micronet_m` | small DS-CNN, audio | 12 / 2 | 15 556 352 | 14 208 852 | 103 661 |
| `mobilenet_v2_1.0_224_INT8` | large, depthwise-heavy, 3.4 MB weights | 53 / 13 | 300 775 552 | 300 840 274 | 2 730 598 |
| `ad_medium_int8` | conv + FWD weight decoder | 12 / 2 | 62 346 720 | 61 466 400 | 183 743 |
| `conv3x3_56x56x64` (isolated) | one Conv2D, compute-dense, static weights | 1 / 0 | 115 605 504 | 115 605 504 | 1 166 666 |
| `matmul_xxT` (isolated) | one BATCH_MATMUL, dynamic weights (tensor core) | 1 / 0 | 1 048 576 | 1 048 576 | 8 333 |

N_MAC: guideline formulas over the original tflite (`host/screening_workload_meta.py`); non-MAC ops are excluded,
not zero. Where N_MAC ≠ Vela nn_macs (kws +9.5 %, ad +1.4 %), both are kept; M3/M5 use the formula value.
Metadata + blobs: `evidence/u85_screening/workloads/`.

Routing (all five): `cmd=ext, const=ext, arena=ext, fast=sram` — the placement Vela's `Dedicated_Sram` assumes
(const/arena on Axi1 = DRAM, cache on Axi0 = SRAM). This routing combination has not run on the board before.
**Fallback (preregistered):** a workload with no valid RUN under it is rerun once with all-EXT routing (no
`--ports`), recorded as such and not pooled with the split-routing results.

## Protocol

MODEL image (APP `0f215ef5…`, already on the card). One boot per workload, `--keep-model --validity model
--repeats 35`, one set = the 8 ids above. Boots 24–28 in the order of the table.

## Metrics (per measured run, then median / mean / std / CV / min / max over the 30)

- M1 `npu_active_cycles`; `window_cycles` alongside.
- M2 `npu_active_ratio = npu_active / window_cycles`.
- M3 `peak_mac_efficiency = N_MAC / (1024 × npu_active)`; secondary `mac_active_cycle_efficiency = N_MAC / (1024 × mac_active)`.
- M4 `mac_active_ratio = mac_active / npu_active`.
- M5 `ext_beats_per_mac = (rd_beats + wr_beats) / N_MAC`; read and write also separately.
- M6 `ext_read_req_stall_ratio`, `ext_write_req_stall_ratio`, `ext_write_data_stall_ratio` = each / `ext_enabled_cycles`.
  Never summed. (`ext_enabled_cycles` and the stalls are both sums over the two EXT ports.)
- M7 `vela_signed_error = (vela_cycles_total − median npu_active) / median npu_active`; absolute = |·|.

## Per-workload outcome (closed set)

- `SCREENED`: ≥ 30 valid measured runs, and every consistency check PASS.
- `UNPROVEN`: fewer than 30 valid measured runs, or a consistency check FAIL — the metrics are shown but marked.
- `NOT_EXECUTABLE`: no valid run (after the fallback, if used).

Consistency checks, per run: `npu_active ≤ window`, `mac_active ≤ npu_active`, each EXT stall ≤ `ext_enabled`,
no counter overflow.

## What this run does not do

- No anomaly classification. Five workloads are not a distribution; the guideline itself forbids absolute
  thresholds. The output is the fingerprint table and the rank of each workload per metric. Any routing to
  second-pass profiling is written as `POST_HOC_DESCRIPTIVE` suggestion.
- No bytes, no milliseconds, no "end-to-end", no "data reuse", no summed stalls (guideline §11).
