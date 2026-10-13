# Stage 1 — performance / compute / memory-demand screening (frozen 2026-10-14, before boot 65)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Data from the TA reset state or any
other profile is never mixed into this dataset.

Purpose: a descriptive fingerprint per workload/operator, plus anomaly candidates routed to Stage 2/3. **No bottleneck
cause is decided in Stage 1.**

## 1. Configuration

All blobs are built through `config/mlek_baseline.json`: Vela 5.0.0 with MLEK options, ethos-u85-1024,
Dedicated_Sram, Ethos_U85_SYS_DRAM_Mid_1024, TA profile 1, AXI SRAM 0x20F0B / EXT 0x21F3F, regions as in stage 0,
fast scratch on-chip at 0x31100000, POWER_CTRL 0. Image APP `2c2fa435…`. 35 RUNs per boot: RUNs 1–5 are warm-up,
6–35 are measured. One boot per workload.

## 2. PMU event set

`config/stage1_ids.txt`; name → id mapping with TRM text in `event_mapping.json`. Ids come from the U85 driver table
and are cross-checked against the TRM table; no historical "#n" numbers are used.

| Stage 1 name | id |
| --- | --- |
| NPU_ACTIVE | 35 |
| MAC_ACTIVE | 48 |
| SRAM_RD_DATA_BEAT | 130 |
| SRAM_WR_DATA_BEAT | 135 |
| EXT_RD_DATA_BEAT | 386 |
| EXT_WR_DATA_BEAT | 391 |
| SRAM_ENABLED_CYCLES | 140 |
| EXT_ENABLED_CYCLES | 396 |

PMCCNTR (`window_cycles`) is recorded for every RUN. It is a sanity/reference value only: the window includes CPU
staging copies, so it is never called latency. NPU execution cost is NPU_ACTIVE.

## 3. Workloads (`workload_manifest/manifest.json`)

| workload | class | definition | N_MAC | output correctness |
| --- | --- | --- | --- | --- |
| kws_micronet_m | model | stage-0 blob `f11271cb…` | 15,556,352 | byte-exact vs tflite_runtime (stage 0 R3) |
| ad_medium_int8 | model | stage-0 blob `55fa924c…` | 62,346,720 | byte-exact vs tflite_runtime (stage 0 R3) |
| mobilenet_v2_1.0_224_INT8 | model | amendment-1 blob `0d51cf9e…` | 300,775,552 | byte-exact vs MLEK FI101 OFM (amendment 1) |
| conv3x3 | isolated_operator | CONV_2D, IFM 1×56×56×64 → OFM 1×56×56×64, kernel 3×3, stride 1, SAME, groups 1 | 115,605,504 | byte-exact vs tflite_runtime (R3) |
| dw3x3 | isolated_operator | DEPTHWISE_CONV_2D, 1×56×56×128 → 1×56×56×128, 3×3, stride 1, SAME, groups 128 (multiplier 1) | 3,612,672 | byte-exact vs tflite_runtime (R3) |
| pw1x1 | isolated_operator | CONV_2D, 1×56×56×64 → 1×56×56×128, 1×1, stride 1, SAME, groups 1 | 25,690,112 | byte-exact vs tflite_runtime (R3) |
| fc1024 | isolated_operator | FULLY_CONNECTED, 1×1024 → 1×1024, weights 1024×1024 | 1,048,576 | byte-exact vs tflite_runtime (R3) |

The manifest fixes, per workload: blob, command stream, input and golden sha256, knob words, and operator metadata
(type, shapes, kernel, stride, padding, groups, quantization, seeds).

**Operator models** come from `host/container/make_op_model.py`: INT8 flatbuffers written directly (no TensorFlow
in any environment), weights from seed 20261014, IFM = the packer's seed-1 input. The OFM scale is chosen from the
accumulator range on that input, so outputs span the int8 range; measured saturation is 0–0.1 %.

**N_MAC** (1 MAC = one multiply-accumulate, not FLOPs; M = 1024 fixed) is computed statically:
- Conv2D: Ho·Wo·Cout·Kh·Kw·(Cin/groups).
- Depthwise: Ho·Wo·Cout·Kh·Kw.
- FC: rows·Cin·Cout.
- Models: the sum over the MAC ops. Non-MAC ops (RESHAPE, AVERAGE_POOL_2D, ADD, SOFTMAX) count as N/A, not 0, and
  are listed per model in `workload_manifest/meta/`.

Independent agreement was checked before data:
- Operators: the generator's formula, `host/container/workload_meta.py` (from the tflite tensors) and Vela `nn_macs`
  are equal.
- Models: values equal the earlier independent records. N_MAC / Vela `nn_macs` = 1.095 (kws), 1.014 (ad) and
  1.000 (mobilenet); Vela's figure is stored, not used.

**Correctness of the new operators** uses the existing mechanism only: stage-0 R3, byte-exact against the
tflite_runtime golden, with no tolerance. An operator that fails R3 is `UNRESOLVED` in Stage 1. Any other golden
(for example an MLEK FI101 golden as in amendment 1) needs an owner decision and a recorded amendment.

## 4. Per-RUN gate (`host/analysis/stage1.py` on top of `host/analysis/baseline_gate.py`)

Per boot:
- B1: image digests equal the profile's.
- B2: blob, cms and knob words equal the manifest's / the profile's.
- B3: requested ids equal `stage1_ids.txt`; coverage complete; no refusal; 35 RUNs.
- B4: the blob's IFM and golden sha256 equal the manifest's, otherwise `INVALID`.

Per RUN:
- R1: run_valid.
- R2: `run_rc == 0`, which covers knob read-back 0x7D (TA / POWER_CTRL / register knobs).
- R3: `vendor_rc == 0` and OFM mismatch 0 against the manifest golden.
- R4: no PMU overflow.
- R5: `0 < NPU_ACTIVE ≤ PMCCNTR`.
- **R6s: `MAC_ACTIVE ≤ NPU_ACTIVE`.** This replaces stage-0 R6 (`cycle` within 1 % of PMCCNTR), because the 8
  programmable slots are all taken by the Stage 1 set and hold no `cycle` event. This is the one change to the
  stage-0 gate.

Every RUN is written to `per_run.csv`, valid or not, with the flags output_valid, knobs_honoured, overflow,
consistency_valid, run_valid and failed_checks. Workload policy is unchanged from stage 0: any failed boot or RUN
check makes the workload `UNRESOLVED`. Its RUNs are still reported (run_valid false), and it gets no aggregate or
fingerprint values. Valid RUNs are never cherry-picked out of a failed workload.

## 5. Metrics (per RUN, then aggregated)

- M1 NPU_ACTIVE.
- M2 N_MAC / NPU_ACTIVE.
- M3 N_MAC / (1024 · NPU_ACTIVE).
- M4 MAC_ACTIVE / NPU_ACTIVE.
- M5 N_MAC / (1024 · MAC_ACTIVE). An active-cycle proxy, not PE occupancy or spatial utilisation.
- M6 residual M3 − M4 · M5. This is algebraically 0 per RUN; it is reported as a numerical check. Medians are not
  multiplicative.
- M7 (SRAM rd + wr beats) / N_MAC.
- M8 (EXT rd + wr beats) / N_MAC.
- M9 SRAM beats / NPU_ACTIVE.
- M10 EXT beats / NPU_ACTIVE. M9 and M10 are observed traffic demand, not bandwidth; there is no ceiling judgement
  before Stage 3.
- M11 SRAM_ENABLED_CYCLES and EXT_ENABLED_CYCLES: **raw only**. Per the TRM they are memory-clock (aclken) cycles
  summed over the AXI ports, and they run over the whole window, not only while the NPU is active. Stage-0 data
  shows EXT_ENABLED ≈ 2 × PMCCNTR. The ratio to NPU_ACTIVE is stored but not interpreted.

Traffic is reported in beats; it is not converted to bytes until the beat width is verified from the TRM/source.

Aggregation over the 30 measured RUNs gives median, mean, sample standard deviation, CV, min and max. The
representative value is the median. Each metric is flagged deterministic (min == max) or variable.

## 6. Outputs

`per_run.csv`, `summary.csv`, `summary.json`, `fingerprint.md` (model and operator tables, descriptive observations
only), `anomaly_candidates.md`.

Routing follows guide patterns A–E by relative comparison across the 7 workloads, with no preset thresholds. Each
candidate lists the supporting metrics, competing explanations, the proposed Stage 2/3 event set and a priority.

Stage 1 succeeds when the items below hold. Whatever does not hold is reported as such.
- All 7 workloads pass the gate.
- Every operator has a valid fingerprint.
- Compute efficiency and traffic demand are comparable across models and operators.
- Anomaly candidates are named with their next event sets.

## Amendment 2 application (2026-10-14, recorded before the new boots and before their goldens exist)

The general correctness rule is `docs/specs/mlek-baseline.md` amendment 2. In Stage 1 it applies as follows:
- conv3x3 (boot 68), pw1x1 (boot 70) and fc1024 (boot 71) stay `UNRESOLVED` as recorded. Their RUNs, per-RUN rows
  and gate results are kept unchanged in `per_run.csv` / `summary.json` under dataset `s1`.
- Each of the three is re-measured on a new boot, one boot per operator, under amendment 2. These are dataset `a2`
  with manifest `workload_manifest/manifest.a2.json`. The manifest holds the MLEK input and golden sha256, the
  G1–G5 record, and the TFLite diagnostic. It is committed before the first `a2` boot.
- The gate is otherwise this contract's: B1–B4, R1–R5, R6s, 35 RUNs, RUNs 1–5 warm-up.
- An `a2` operator whose gate is `BASELINE_PASS` enters the Stage 1 fingerprint, labelled with its boot and
  "amendment 2". Its input (MLEK's) differs from the seed-1 input of boots 65–71; this is stated with the table.
- An `a2` operator that fails the gate stays `UNRESOLVED`; no other golden is tried without an owner decision.
- Analysis: `host/analysis/stage1.py <s1 root> <out> --add a2 <a2 root> <manifest.a2.json>`. It writes both datasets
  into one `per_run.csv` (column `dataset`) and one `summary.json`, where the `a2` entries are keyed `<workload>@a2`.
