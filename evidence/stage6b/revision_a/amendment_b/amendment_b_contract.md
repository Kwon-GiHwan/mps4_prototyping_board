# Stage 6B Revision A — Amendment B (fusion rule, saturation diagnosis, input fixture)

Written 2026-11-15 after the Original Contract Result (`original_result_snapshot.md`, commit `ab02431`) and committed
before any Amendment B fact is extracted or any re-judgement is run. Approved scope: "Stage 6B Revision A — Amendment B
공식 지시" (B안 승인). Board measurement is **not** approved.

**This is a post-hoc amendment.** Its rules were written after the Original Contract Result was seen. Every judgement made
with them on the original compile is labelled `POSTHOC_AMENDMENT`; results on the new input fixture are labelled
`ADDITIONAL_VALIDATION`. Neither is reported as a result of the original contract. The original contract
(`revision_a_contract.md`), its judge (`host/analysis/stage6b_revision_a.py`), its records and its result files are not
edited; the amendment adds its own judge (`host/analysis/stage6b_amendment_b.py`), container script
(`host/container/stage6b_amendment_b.py`) and output directories (`amendment_b/`, `results/fi101_stage6b/revision_a/amendment_b/`).

Unchanged from the original contract: the 26 candidates, the A0/A1/A2 forms, the EXACT_A definition, the params,
repeat, registers and package gates, the reference gate **including the 10 % saturation rule on the original input**,
the selection rule (max 10, Stage 6B MAC contribution and tie rules, no model exception), coverage arithmetic, and the
Stage 4–6 data. No PARTIAL_A is promoted.

## B-1 Fusion gate (replaces the fixed operator list of the original `fusion` check)

The original check required the scheduled NPU operator list to be exactly `[Add, Conv2D, Add]` (A1/A2) or `[Conv2D]` (A0).
Vela lists a Conv's fused activation as its own logical row (`npu_op` `Relu6`/`Relu`, same `tflite_op_index` as the
Conv). The amended gate allows that row **only** when the original model's Conv had the same activation, and only after
the facts below are verified. It is not a general exception for extra operators.

Facts (per candidate and form):
- original: the Stage 4 inventory rows of the representative op (`model`, `tflite_op_index`, inventory compile); the
  candidate manifest's `activation`; the Conv kernel registers of the recompiled original (same compile whose
  `vela_sha256` equals the inventory's, the condition of the `registers` gate) at the manifest's `cms_offsets`;
- form: the record's scheduled rows; the form's command stream (`<name>.drwl.cms.bin`, digest = the record's
  `cms_sha256`); the type of every kernel instruction in it; the activation registers at each Conv kernel.

Activation registers (cmd0 opcodes from the core driver's `ethosu85_interface.h`): `NPU_SET_ACTIVATION` 293,
`NPU_SET_ACTIVATION_MIN` 294, `NPU_SET_ACTIVATION_MAX` 295, `NPU_SET_OFM_ZERO_POINT` 280; cmd1 `NPU_SET_OFM_SCALE` 36.

Conditions (the instruction's six questions):

| # | condition | fact |
| --- | --- | --- |
| F1 | the original Conv had this activation | manifest `activation` ∈ {RELU, RELU6} ⇔ the inventory has exactly one activation row (`Relu`/`Relu6` matching it) for the op; NONE ⇔ no activation row |
| F2 | same activation kind and parameters in the form | form Conv row `tflite_activation` = original; activation registers at every Conv kernel equal the original's, kernel by kernel |
| F3 | Conv execution settings equal | Conv kernel registers `REG_CONFIG` + `REG_REGION` of the original contract equal, kernel by kernel, same kernel count |
| F4 | no extra kernel / changed structure from the activation | every activation row (original and form) has no `cms_offsets`, `mac_count` 0, `vela_op_cycles` 0; the form's kernel instruction types are exactly `[ELEMENTWISE] + [CONV]×n + [ELEMENTWISE]` (A1/A2) or `[CONV]×n` (A0), n = the original Conv's kernel count |
| F5 | traversal, block, ublock and the related registers | F3 plus the original contract's `params` gate (conv row: block, ublock, traversal, kernel, stride, padding, shapes) — F5 is not re-implemented, the gate stays required |
| F6 | no unexpected fusion, split or removal | logical rows = `[Add, Conv2D, <act>?, Add]` (A1/A2) / `[Conv2D, <act>?]` (A0) with `<act>` = exactly the original Conv's activation rows (F1 checks those against the manifest; a changed activation row is caught here); `tflite_op_index` 0 / 1 / 1 / 2 (A1/A2) and 0 (A0); every row `fused_names` = 1; no CPU rows; Conv output tensor `conv_out` (A1/A2) / `ofm` (A0) |

Classification:
- `FUSION_UNVERIFIED` — any fact missing: original compile not the inventory compile, original kernels or activation
  registers missing, stream digest ≠ the record's `cms_sha256`, form not packed.
- `EXECUTION_CHANGED` — every fact present and any of F1, F2, F3, F4, F6 fails.
- `ORIGINAL_ACTIVATION_PRESERVED` — every fact present and F1–F4, F6 hold. A source Conv without activation (NONE)
  takes this class when its form has no activation row and F2–F4, F6 hold.

Only `ORIGINAL_ACTIVATION_PRESERVED` passes the amended fusion gate. A stream whose digest differs from the record makes
the whole run INVALID (the facts would not describe the judged compile).

## B-2a Saturation — definition check (diagnosis only, no rule change)

Read-only, on the original compile outputs, for G14, G23 and G41, forms A0, A1, A2. Reported, not gated:
1. which tensor each share is computed on (`conv_out` = BUILTIN_REF preserved Conv output **after** its fused
   activation; `final` = graph output), and that the recorded shares recompute exactly from the stored IFM;
2. quantisation (scale, zero point) of the graph inputs, Conv IFM, Conv OFM and final OFM;
3. the clamp bounds (`act_range`: RELU6 → [zp, zp + round(6/scale)], RELU → [zp, 127], NONE → [-128, 127], cut to int8);
4. histogram: count at the lower bound, at the upper bound, strictly inside; for `final`, at -128 and 127;
5. the IFM: source (seeded uniform int8, `S6B_SEED` 20261118), range, share at -128/127; for A1/A2 also the Conv IFM after
   the first ADD;
6. the pre-clamp requantised Conv output (independent int64/float64 Conv without the clip): share below / above the bounds,
   so the cause (input distribution vs. activation clamp vs. wrapper vs. a check error) can be separated;
7. that A0/A1/A2 were judged with the same formula.

A defect found here (wrong tensor, wrong bound) is reported as a separate defect; the original results are not
overwritten. If B-2a resolves the question (a check defect), B-2b is not run.

## B-2b Input fixture (only if B-2a finds no check defect)

Fixed here, before any fixture is generated. One input per model, no seed, no retry, no alternative input.

- Kind: **model-representative input** (not a synthetic diagnostic input). No synthetic input is used in Amendment B.
- Source: MLEK's own input of the source model, the equivalence-C file `/work/equiv_c/<model>/ifm.bin` in the container,
  accepted only if its sha256 equals `workloads.<model>.golden.input_sha256` of `evidence/equiv_c/manifest.json`
  (branch `refactor/firmware-modules`, `0f329a5`): kws `236ea3d6…`, ad `89ce99eb…`, mobilenet `be4e0171…`, vww4
  `906d4afb…`, wav2letter `dc8d69e0…`.
- Fixture: run the original MLEK tflite on that input (tflite_runtime, BUILTIN_REF, all tensors preserved) and take the
  representative Conv's input tensor `x` and output tensor `y_model` (operator `op_index` of the manifest).
- Applied to: the A2 form of every Original-Contract EXACT_A candidate (G09 G11 G12 G14 G23 G25 G28 G40 G41 G52 G53
  G56 G57) — all 13, not only the three failing ones. A2 graph inputs: `a = x`, `b` = all elements equal to the IFM zero
  point (real value 0). Weights, bias, scales, shapes, activation, the tflite and Vela options are not changed.
- Facts and pass rule (`ADDITIONAL_VALIDATION` PASS only if all hold):
  - V1 input digest as above; `x` shape = the Conv IFM shape;
  - V2 the A2 Conv input (after `ADD(a, b)`) equals `x` exactly;
  - V3 A2 `conv_out` (BUILTIN_REF) equals `y_model` exactly (the Conv reproduces the model's own Conv on real data);
  - V4 independent numpy Conv vs `conv_out`: max |Δ| ≤ 1 (the original contract's tolerance);
  - V5 `final` vs `conv_out`: max |Δ| ≤ 1 (A2 self-ADD), and the final output reported separately from `conv_out`;
  - V6 share strictly inside the clamp range ≥ 0.10 for `conv_out` **and** for `final` (the 10 % rule unchanged);
  - V7 repacked DRWL with this IFM and its BUILTIN_REF golden (same packer, profile, Vela options): `vela_sha256` and
    `cms_sha256` equal the original A2 record (execution settings and placement unchanged; only IFM and golden differ).
  - A missing fact (input file, digest, tensor) → `VALIDATION_UNRESOLVED` for that candidate; no further attempt.
- A candidate failing V6 keeps `SATURATION_GATE_FAIL`. A pass is recorded as "ADDITIONAL_VALIDATION PASS on MLEK's
  input"; it does not change the Original Contract Result nor the `POSTHOC_AMENDMENT` reference gate.

## Re-judgement and eligibility

- `POSTHOC_AMENDMENT` BOARD_ELIGIBLE = EXACT_A and params, reference (original input, 10 % rule), repeat, registers,
  package PASS and amended fusion `ORIGINAL_ACTIVATION_PRESERVED`.
- `BOARD_ELIGIBLE_WITH_ADDITIONAL_VALIDATION` = the same except the reference gate fails **only** by the saturation diffs
  and `ADDITIONAL_VALIDATION` PASS. Reported separately; such a candidate would be measured with the fixture DRWL, and
  its admission is a decision for the next instruction, not taken here.
- Selection: the Stage 6B rule on the `POSTHOC_AMENDMENT` BOARD_ELIGIBLE set (primary). The selection that would follow
  if the additional-validation candidates were admitted is reported as a labelled scenario only.
- Verdict: INVALID (provenance as in the original contract, or a fusion-fact stream digest mismatch);
  READY_FOR_BOARD_REVIEW (new BOARD_ELIGIBLE besides G14, selection equal between the two compiles, board contract
  written); otherwise NEEDS_REVISION.

## Vela estimates (recorded, no error computed)

Per form, the Vela per-operator estimates already in the records (`vela_op_cycles`, `vela_npu_cycles`,
`vela_mac_cycles`, `vela_ao_cycles`, `vela_cmd_cycles` of the Conv row; `vela_op_cycles` of each ADD row) and their sum
over the form's rows. Scope stated per value (Conv only vs. whole A2 graph). No prediction error is computed without a
board measurement.
