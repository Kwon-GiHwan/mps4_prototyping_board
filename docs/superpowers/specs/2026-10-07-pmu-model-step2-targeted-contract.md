# Tier C step 2 (targeted) — mobilenet, split ports, AXI latency channel (contract)

Frozen 2026-10-07, **before any data exists**, after step 1 = MODEL_RUNS_CORRECT. Authorization: owner,
2026-10-07 ("전수형이 최종 목적인데, 지금은 표적형"). The full 171-id sweep stays the end goal; the same
tools run it by omitting `--ids`.

## Selectable knobs (all default OFF = step-1 behaviour)

PMWL header **v2** = v1's 16 words + `[16] pmcaxi_chan [17] regioncfg [18] qconfig [19..22] mem_attr0..3
[23] reserved`; `0xFFFFFFFF` = OFF. Firmware (MODEL=1):
- `pmcaxi_chan` ≠ OFF → written to PMU `PMCAXI_CHAN` (0x11AC) in the wrap, under cnt_en=1, read back.
- `regioncfg/qconfig/mem_attr*` ≠ OFF → written at the vendor's `"Updating POWER_CTRL…"` printf (after the
  vendor's own REGIONCFG/QCONFIG/MEM_ATTR writes, before the NPU start), each read back.
- Any readback ≠ written → the run returns rc **0x7D** (knob not honoured) → INVALID.
- Placement follows the port: a region whose MEM_ATTR selects EXT lives at S DRAM 0x7010_0000; SRAM-port
  regions live in the staging window (0x9012_0000 dev alias), constants/cmd in place inside the blob.
- Host: `--ids` selects event ids (default all 171); coverage is checked against the requested set.

## This run

Workload `mobilenet_v2_1.0_224_INT8` (ethos-u85-1024, SYS_DRAM_Low, Dedicated_Sram), seed 1.
Knobs: cmd + constants → EXT (MEM_ATTR2 = 0x4), arena + fast scratch → SRAM port (MEM_ATTR0 = 0x0);
REGIONCFG = region0→ATTR2, region1→ATTR0, region2→ATTR0; QCONFIG → ATTR2;
PMCAXI_CHAN = AXI_SEL ext, CH_SEL rd_weights (0x102).
Ids (48): TRM `sram_*`/`sram0_*`/`sram1_*` (30), `axi_latency_*` (7), `ext*_stall_limit` (6),
controls `cycle` 17, `npu_idle` 32, `npu_active` 35, `sram_enabled_cycles` 140, `ext_enabled_cycles` 396.
6 sets × 3 repeats, one boot.

## Validity and verdicts

Tier B's nine terms (golden not checked); correctness = rc 0 (vendor memcmp vs tflite_runtime reference).
Event verdicts: Tier B's closed set. Campaign: `MODEL_RUNS_CORRECT` / `MODEL_WRONG_OUTPUT` (rc 2) /
`KNOB_NOT_HONOURED` (rc 0x7D) / `MODEL_FAILS` / `MODEL_REFUSED` (rc 0x7E).
