# What the operator-type groups contain — Vela 5.0.0 compile, per command-stream kernel op

`POST_HOC_DESCRIPTIVE`, compile-time only (no board data). Recorded 2026-11-04 for Stage 2B-1/2B-2
(`evidence/s2_groups/contract.md`). Reproduce in the benchmark-runner container:
`python3 host/container/vela_op_map.py <out> <seven MLEK .tflite>` (Vela options = `pack_vela_workload.VELA_OPTIONS`,
plus `--enable-debug-db --verbose-high-level-command-stream`).

Checks: the command stream of this compile is **byte-identical** to the stream in the measured fi101_s013 blob for all
seven models (`<model>.cms.sha256`); the debug-db `queue` offsets equal `cms.kernel_offsets` of that stream exactly;
installed Vela = PyPI `ethos-u-vela 5.0.0`, all 295 files match the wheel's RECORD hashes (unmodified).

Files: `<model>.op_map.csv` — one row per command-stream kernel op: stream type (the 2B-2 group), Vela optimised
operator, original TFLite operator; `<model>.stages.csv` — counts per stage.

## Where one TFLite operator becomes several stream operations

For Ethos-U85 Vela 5.0.0 never uses its Python compiler: `vela.py` sends every U85 (and TOSA) compile to the C++
compilation core **Regor** (`ethosu/regor.cpython-310-*.so`, `regor.compile()`; comment in `vela.py`: "All Ethos-U85 or
TOSA network compilations always use Vela's C++ compilation core (Regor)"). The Python modules
(`graph_optimiser.py`, `scheduler.py`, …) are the deprecated legacy core for U55/U65. Inside Regor there are three
places where the count changes:

1. **Graph optimiser (lowering / decomposition)** — TFLite operator → Vela "optimised" operators.
   - `Softmax` is decomposed into ~28 NPU operations: Mul ×11, Sub ×6, Add ×4, Asr ×2, CLZ, SHL (ELEMENTWISE) and
     MaxPool, ReduceSum (POOL), plus Transpose in wav2letter.
   - Data-movement operators become `MemoryCopy` (a POOL-type NPU op): Pad (vww4 ×16), Concat (rnnoise, yolo), Pack,
     Reshape (rnnoise).
   - Fused activations (Relu6) are absorbed as sub-operations; pure Reshape at the end disappears.
2. **Scheduler (striping / cascading / weight buffering)** — one optimised operator → several high-level commands.
   - **Cascading**: mobilenet's first layers run as a cascade in height stripes (e.g. 6 OFM rows at a time):
     conv stripe, depthwise stripe, conv, conv, then the next stripe — so 7 Conv2D and 4 DepthwiseConv2D become up to
     19 stream ops each, interleaved with each other ("cascaded" in the high-level command stream).
   - **Weight buffering**: a Conv2D whose weights are DMA-buffered is split along OFM depth (kws first conv:
     channels 0–16 then 16–140, "buffered"; ad's first conv is split the same way, 7 → 8; vww4 has 2 Conv2D split in
     two — reason not inspected).
3. **Register command stream generator (chaining)** — a high-level command with an elementwise sub-operation
   (`subOps:[ Add ]`) is emitted as **two** kernel ops: the main op and, right after it, a chained ELEMENTWISE op.
   Chained this way (checked in the HL operator list, `subOps`): mobilenet 10 of 10 residual Adds (after Conv2D),
   yolo 17 of 18 Adds, vww4 2 of 10 Adds; rnnoise 3 Adds (after Mul) and 6 Muls (after Add, Sub); and several Softmax
   pieces in mobilenet/wav2letter (Mul/Sub/Add/SHL/Asr). Activations (Relu6, Relu, LUT for sigmoid/tanh) are fused
   into the op and never become a separate kernel op.

| model | TFLite ops (reaching the NPU) | Vela optimised ops | stream kernel ops |
| --- | --- | --- | --- |
| kws | 13 | 13 | 14 |
| ad | 13 | 13 | 14 |
| rnnoise | 44 | 48 | 48 |
| vww4 | 73 | 83 | 85 |
| yolo | 108 | 112 | 112 |
| mobilenet | 65 | 91 | 208 |
| wav2letter | 12 | 39 | 39 |

(The earlier "mobilenet 69 → 208" in the plan used the `--verbose-schedule` operator count; the debug-db counts above
replace it.)

## What each 2B-2 group holds (stream kernel ops; "A→B" = TFLite A lowered to B)

| model | CONV | DEPTHWISE | POOL | ELEMENTWISE | RESIZE |
| --- | --- | --- | --- | --- | --- |
| kws | Conv2D 8 | DepthwiseConv2D 5 | AvgPool 1 | — | — |
| ad | Conv2D 8 | DepthwiseConv2D 5 | AvgPool 1 | — | — |
| rnnoise | FullyConnected 9 | — | Concat→MemoryCopy 6, Quantize 4, Pack→MemoryCopy 3, Reshape→MemoryCopy 2 | Add 12 (3 chained), Mul 9 (6 chained), Sub 3 (GRU gates) | — |
| vww4 | Conv2D 39 | DepthwiseConv2D 17 | Pad→MemoryCopy 16, Relu6 2, AvgPool 1 | Add 10 (2 chained, 8 standalone) | — |
| yolo | Conv2D 56 | DepthwiseConv2D 28 | Concat→MemoryCopy 6, MaxPool 3 | Add 18 (17 chained, 1 standalone) | ResizeNearestNeighbor 1 |
| mobilenet | Conv2D 113 (cascade stripes) | DepthwiseConv2D 57 (cascade stripes) | AvgPool 1, Softmax→MaxPool 1, Softmax→ReduceSum 1 | Add 10 (residual, chained); Softmax pieces 25 | — |
| wav2letter | Conv2D 11 | — | Softmax→Transpose/MaxPool/ReduceSum 3 | Softmax pieces 25 | — |

## Consequences for reading 2B-2

- **ELEMENTWISE is not one kind of work.** In wav2letter it is entirely the Softmax decomposition; in mobilenet it is
  25 Softmax pieces plus 10 residual Adds chained to convolutions; in rnnoise the GRU gate arithmetic; in yolo
  chained residual Adds; in vww4 residual Adds, mostly standalone.
- **POOL is mostly data movement** in rnnoise, vww4 and yolo (MemoryCopy from Pad/Concat/Pack/Reshape), not pooling.
- **Chained ops overlap their convolution by design**: a residual Add starts while its Conv2D produces output.
  Gating the Add in a different group than its Conv puts a boundary exactly where the two run together — a place where
  boundary loss can be expected (yolo, mobilenet) — a hypothesis, not tested.
- **Cascades interleave CONV and DEPTHWISE stripes** in mobilenet: each group's windows alternate stripe by stripe
  (CONV 67 windows, DEPTHWISE 55), the most boundaries of any model.
- Vela-operator groups (e.g. "low block-fill convolutions") are now possible from `op_map.csv` (`optimised_id` per
  stream op); they are not part of the frozen 2B-2 contract.
