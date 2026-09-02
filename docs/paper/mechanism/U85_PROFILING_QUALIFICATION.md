# U85 per-layer profiling qualification — P0-C

Date: 2026-09-02. Verdict first:

```
PROFILING_PATH_NOT_QUALIFIED  (as designed — the prior Vela-insertion path
                               does not exist for U85)
tag paper-u85-layer-profiling-qualified   NOT ISSUED
formal measurement (P0-D)                 BLOCKED pending manager decision
```

No formal sample was taken. No frozen artifact was touched.

## Finding — the U85 compile path bypasses the prior insertion point

The prior methodology patches
`ethosu/vela/register_command_stream_generator.py` at the
`generate_operation_code(emit, npu_op)` anchor. That anchor exists in Vela
5.0.0 (verified), **but U85 does not flow through it**:

- `ethosu/vela/vela.py:50` — `from ethosu import regor`
- `vela.py:135` — U85 networks are compiled by
  `regor.compile(accelerator, network, fmt, system_config, options=…)`,
  a compiled C++ extension
  (`ethosu/regor.cpython-310-x86_64-linux-gnu.so`); the Python code generator
  is the U55/U65 path only.
- `strings` over the regor binary shows it knows the `NPU_OP_IRQ` opcode but
  exposes no insertion/instrumentation option (no matching option strings;
  `regor.compile` has no such parameter surface).

Therefore `patch-vela.py` cannot instrument a U85 command stream, and the
prior methodology is **not portable as designed**. This is a property of the
pinned toolchain, discovered before any measurement — exactly what P0-C
exists to catch.

## What remains valid from the prior path

The driver side is architecture-neutral and still applies: mid-stream IRQ
handling (`cmd_end_reached == 0` → snapshot/reset/clear/resume) in
`ethosu_driver.c`, the per-layer record buffer, and the determinism-first
test harness. Only the **insertion mechanism** is void for U85.

## Alternative with verified source authority (design sketch — NOT approved)

Post-process the compiled U85 command stream (the Ethos-U custom-op payload
inside `*_vela.tflite`), inserting `NPU_OP_IRQ(param=op_index)` after each
operation-launch command. Authority established during this audit:

- `dependencies/core-driver/src/ethosu85_interface.h` (vendor header, 24,620
  lines) defines the complete U85 command stream encoding:
  `cmd0_opcode { NPU_OP_STOP=0, NPU_OP_IRQ=1, NPU_OP_CONV=2, … }` (line 549)
  and the exact word encoding
  `(cmd_ctrl::CMD0_CTRL << 14) | cmd0_opcode` (line 14336, the header's own
  disassembler switch). Opcode tables can be extracted mechanically, in line
  with this repository's extract-don't-derive rule.
- `regor` can emit an optimisation database (`enable_debug_db`,
  `regor.Database`) as a candidate op-identity source for matching.

Known risks to resolve before this design could qualify:

1. `NPU_OP_BRANCH = 256` exists in the U85 opcode space — if generated
   streams contain branches with position-dependent targets, naive insertion
   corrupts them. The tool must fail closed on any branch/offset construct it
   cannot prove unaffected.
2. Stream length fields (flatbuffer payload size, any header word) must be
   located from authority and updated, or the tool fails closed.
3. `param` width for op_index in a cmd0 word must be taken from the header,
   not assumed.
4. Every instrumented stream must round-trip through a header-derived
   disassembler check (same authority) before it may boot.

## Decision requested (manager)

- **Option 1 — build the U85 command-stream instrumentation tool** per the
  sketch above, then re-run P0-C qualification (items 1–7 of the plan)
  against it. New engineering; keeps runtime per-layer decomposition (Q1/Q3).
- **Option 2 — descend to compiler-side decomposition only**: no runtime
  per-layer data; Q1/Q3 become NOT_EVALUABLE; Q2/Q4/Q5/Q6 proceed on Vela
  verbose schedule/performance captures plus whole-model clean runs (which
  need no instrumentation and remain fully qualified).
- **Option 3 — stop the mechanism study here** and report the boundary as
  characterized only at whole-model granularity.

Until one is chosen: P0-D formal acquisition does not start, per the frozen
plan's gate ("Do not proceed without a frozen qualification artifact").
