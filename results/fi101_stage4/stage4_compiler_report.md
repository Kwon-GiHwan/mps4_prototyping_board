# Stage 4 Phase 2 — compiler report (Gate B)

Compile-time only (no board). Vela 5.0.0, options = MLEK's for Ethos-U85-1024 (`--accelerator-config ethos-u85-1024
--optimise Performance --config default_vela.ini --memory-mode Dedicated_Sram --system-config
Ethos_U85_SYS_DRAM_Mid_1024`, `pack_vela_workload.VELA_OPTIONS`, = `config/fi101_s013.json` vela block), the same
options as Stage 1/3 and the driver-runner measurements. TA state is a board condition (TA profile 1), not a compile
option. Tools: `host/container/make_op_model.py` (Stage 1's generator and quantization policy, extended with padding
and fused activation; the Stage 1 models stay byte-identical), `host/container/stage4_compile.py`. Artifacts and
digests: `evidence/stage4/workloads/` (`<cfg>.compile.json`, `.tflite`, `.drwl`, `.drwl.cms.bin`,
`.drwl.tflite_ofm.bin` = CPU reference OFM).

## Gate B checks (all 8 PASS)

| check | meaning |
| --- | --- |
| placement | the Vela output holds exactly one operator, the Ethos-U custom op: **no CPU fallback** |
| schedule | exactly one scheduled operation with cycles, of the intended type; the only other row is the fused RELU6 with 0 cycles and no command |
| kernels | every kernel instruction of the command stream is of one kind: CONV (Conv2D, and FullyConnected, which U85 runs as a CONV kernel), DEPTHWISE (DWConv) |
| macs | Vela's MAC count = the matrix's theoretical MACs |
| same_vela | the debug-database compile and the packer's compile produce the same Vela output |

## Schedule and estimates (Vela debug database; cycles are Vela's NPU-cycle estimates)

| config | MACs | kernels | OFM block | IFM block | ublock | traversal | Vela NPU cycles (MAC / AO / cmd) | Vela op cycles | DRAM AC | weight bytes | OFM scale |
| --- | ---: | ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| conv_base | 884,736 | 2 | 6×12×96 | 6×12×16 | 2×2×32 | PartKernel | 16,660 (8,019 / 4,224 / 1,004) | 24,999 | 24,999 | 2,752 | 0.05013 |
| conv_cin15 | 829,440 | 2 | **14×18×32** | 14×20×16 | 2×2×32 | PartKernel | **10,068** (4,081 / 3,960 / 1,155) | **61,523** | 61,523 | 2,624 | 0.04417 |
| conv_cout95 | 875,520 | 2 | 6×12×96 | 6×12×16 | 2×2×32 | PartKernel | 16,497 (7,999 / 4,192 / 997) | 24,999 | 24,999 | 2,736 | 0.05012 |
| dw_base | 4,064,256 | 2 | 26×28×16 | 28×32×16 | 2×4×16 | Depthwise | 112,225 (43,064 / 29,315 / 2,807) | 944,999 | 944,999 | 1,792 | 0.03806 |
| dw_c143 | 4,036,032 | 2 | 26×28×16 | 28×32×16 | 2×4×16 | Depthwise | 112,225 (same) | 938,437 | 938,437 | 1,776 | 0.03465 |
| fc_base | 27,648 | 1 | 2×2×288 | 2×2×64 | 2×2×32 | DepthFirst | 7,929 (7,929 / 2,322 / 2,177) | 7,929 | 7,031 | 32,208 | 0.07909 |
| fc_in95 | 27,360 | 1 | 2×2×288 | 2×2×64 | 2×2×32 | DepthFirst | 7,929 (same) | 7,929 | 7,031 | 31,920 | 0.08986 |
| fc_out287 | 27,552 | 1 | 2×2×288 | 2×2×64 | 2×2×32 | DepthFirst | 7,909 (7,909 / 2,322 / 2,171) | 7,909 | 7,031 | 32,112 | 0.07976 |

Vela "op cycles" = the larger of the NPU estimate and the memory-access estimate; "NPU cycles" = compute only.

## What changed with the channel (compile-time observations, POST_HOC_DESCRIPTIVE)

- **Conv Cin 16 → 15:** the only pair where Vela chose a different schedule — OFM block 6×12×96 → 14×18×32. Its
  compute estimate falls (16,660 → 10,068) while its memory estimate rises 2.5× (24,999 → 61,523 DRAM access cycles):
  Vela predicts the 15-channel IFM read from DRAM to dominate. Whether the board shows this is a Phase 3 question.
- **Conv Cout 96 → 95, DW 144 → 143, FC in 96 → 95, FC out 288 → 287:** same block, ublock, kernel count; estimates
  move by 0–1 % (DW and FC-in: NPU estimate identical).
- **Memory placement differs from the source models:** as standalone networks, IFM and OFM are graph I/O and sit in
  DRAM (`Dram`/`Dram`, NHWC) in every config; in the source models the layers' feature maps were in SRAM (yolo op 36
  Sram/Sram, mobilenet op 7 Sram/Dram, rnnoise op 0 Dram/Sram) and mobilenet op 7 was inside cascade 7. The standalone
  measurements describe the operator under graph-I/O-in-DRAM conditions, not its in-model execution.
- **Quantization:** Stage 1's policy (IFM 1/128, weights 1/128 per channel for Conv/DW, per tensor for FC, bias
  int32, OFM scale from the seed-1 accumulators, zero points 0). The OFM scale is data-derived and so differs per
  config (listed); weights and bias are drawn from the same seed for each shape, so a −1 config's weights are not a
  subset of the base's.

## Hashes

Per config in `stage4_experiment_matrix.csv` (model, Vela output, command stream, DRWL) and in
`evidence/stage4/workloads/<cfg>.compile.json` / `.drwl.json`.
