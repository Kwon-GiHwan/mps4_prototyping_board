# Runner vs MLEK — remaining differences (static audit, 2026-10-13)

Question: with TA profile 1 fixed, what else in the custom runner still differs from the MLEK board run?
Static only (sources, linker scripts, ELF symbols, recorded hashes); nothing here was measured.

Sources: MLEK `b2c0bb2` in the container (`/opt/arm/ml-embedded-evaluation-kit`; tracked files unmodified per
`git status`), its SSE-320 linker `scripts/cmake/platforms/mps4/sse-320/mps4-sse-320.gnu.ld`, an SSE-320 U85 MLEK
ELF on the board host (`~/mps4/U85_MECH_P0D_*/pd/kws_micronet_m__512_Mid512/prof.axf`, same platform code),
`docs/reference/mlek_board_reference.json`, runner ELF `/work/selftest/build_pmu_events_model/runner_pmu_events.elf`,
`firmware/`, and `register_diff.csv` / `control_flow_diff.md` beside this file.

| # | item | MLEK board run | runner (stage-0 profile) | status |
| --- | --- | --- | --- | --- |
| 1 | Vela output | MLEK build | `pack_vela_workload.py` (Vela 5.0.0, MLEK options) | **same bytes**: `vela_sha256` equal for kws, ad, mobilenet |
| 2 | command stream / weights | from the Vela output | from the same Vela output | same (follows from 1) |
| 3 | timing adapters | `ta_config_u85_sys_dram_mid` | profile 1 (read back every RUN) | aligned |
| 4 | AXI_SRAM / AXI_EXT | 0x20F0B / 0x21F3F | knob 0x20F0B / 0x21F3F | aligned |
| 5 | MEM_ATTR0..3, REGIONCFG, QCONFIG | 0/0/4/4; cmd, const, arena on EXT; fast on SRAM port | knobs, same values | aligned |
| 6 | model + arena memory | DDR (`nn_model` at 0x70000000, `activation_buf_dram` after it) | DDR from `EXT_DRAM_BASE` 0x70100000 | aligned (same DDR region, different offsets) |
| 7 | fast scratch memory | on-chip SRAM, `cache_arena` at **0x31000000**, 0x60000 B | on-chip SRAM at **0x31100000** (knob) | aligned in memory and port; base differs because runner code/data/stack occupy 0x31000000–0x31029FC0 |
| 8 | POWER_CTRL | 0 (driver default) | knob 0 (vendor would write 2) | aligned by knob |
| 9 | soft reset + PROT before the job | yes, secure + privileged | no reset; vendor path | **differs** (firmware change needed) |
| 10 | CFG_SRAM_CAP / CFG_EXT_CAP writes | not written | vendor writes 0x21F3F | **differs** (firmware change needed) |
| 11 | CPU while the NPU runs | `__WFE()`, code in BRAM, I/D-cache **on** | busy loop on `irq_triggered`, code + data + stack in on-chip SRAM, caches **off** | **differs** (firmware change needed); with fast scratch now in on-chip SRAM, the CPU's polling reads the same SRAM the NPU uses |
| 12 | PMU events | ACTIVE, SRAM rd/wr beats, EXT rd/wr beats (+ cycle counter) | profile set includes those five ids (35, 130, 135, 386, 391) | aligned (same events) |
| 13 | PMU window | `ethosu_inference_begin/end` | armed before `test_u85`; PMCCNTR includes staging copies | differs for PMCCNTR only; NPU-active cycles are counted only while the NPU is active |
| 14 | runs per boot | 1 inference per boot (B1–B3 = 3 boots) | 35 RUNs per boot, first 5 dropped | protocol difference |
| 15 | input data | MLEK's bundled sample | seeded random int8 (seed 1) | differs; EXT beats were equal to MLEK's under TA 1 |
| 16 | output check | none in the profile counters | OFM byte-compare with the tflite reference (`ofm_mismatch_count`) | runner is stricter |

Not required to explain the measured gap: under TA profile 1 the runner was within −0.4 % / +0.4 % / +0.3 % of
MLEK (kws / ad / mobilenet, `hypothesis_status.md`), inside MLEK's own B1–B3 spread. Items 9–11 have not been tested
and are not claimed to be inert. Item 11 is new: it matters only once fast scratch sits in on-chip SRAM, which the
stage-0 profile does.
