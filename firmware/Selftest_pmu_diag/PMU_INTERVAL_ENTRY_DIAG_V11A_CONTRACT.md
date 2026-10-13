# PMU_INTERVAL_ENTRY_DIAG_V11A

`PMU_INTERVAL_ENTRY_DIAG_V11A` is a diagnostic-only schema-11 variant. It extends the V10 interval split with one additional `J0` timestamp from a standalone Thumb veneer.

Contract freeze:
- `PMU_INTERVAL_ENTRY_DIAG_V11A` / schema 11 is frozen to build ID `0x41314950`.

Checkpoints:
- `T0`: existing `t_call_enter`
- `T1`: immediately before the vendor submit `NPU_REG_CMD` write
- `T2`: immediately after that submit write and before `wait_for_irq()`
- `J0`: first-veneer-probe inside `v11a_u85_irq_entry_veneer`
- `I0`: existing V10 first stock-handler probe, before the stock `STATUS` read
- `T3`: immediately after the existing completion-confirming `STATUS` read and before `irq_triggered=true`
- `T4`: existing target hook entry
- `T5`: existing `t_call_return`

Rules:
- Active path is runtime `NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer)`. Startup vector changes alone do not qualify.
- The veneer may do only one DWT `CYCCNT` read, one SRAM store to `pmu_interval_v11a_t_vector_probe`, and one unconditional tail branch to the unchanged stock `u85_irq_handler`.
- The veneer may not touch the stack, `LR`, interrupt mask, PMU/NPU/CMD/STATUS MMIO, barriers, `printf`, or helper calls.
- `J0` is `first-veneer-probe`, not IRQ assertion time, not exception-entry time, and not pure NPU execution time.
- Host-side interpretation must use:
  - `A0 = delta32(J0 - T2)`
  - `A1 = delta32(I0 - J0)`
  - `A2 = delta32(T3 - I0)`
  - `D23 = delta32(T3 - T2)`
  - `(A0 + A1 + A2) & 0xffffffff == D23`
- Diagnostic only. Not Production, not latency, not `T_npu`, and not MLEK.

Real-build evidence:
- Remote evidence root: `/home/gihwan/mps4/PMU_INTERVAL_V11A_20260810T140216Z`
- Build context stayed inside `benchmark-runner:/work/selftest`; board was not touched.
- `REPRO_BUILD_A` transcript SHA-256: `8158d6d2d49445085fd30c233ec50c33b5f939aaf292de9fa09090bc520c62d4`
- `REPRO_BUILD_B` transcript SHA-256: `8158d6d2d49445085fd30c233ec50c33b5f939aaf292de9fa09090bc520c62d4`
- Empty byte-identity diff SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Explicit clean-build byte identity: `diff -u /tmp/v11a_build_hashes_1.txt /tmp/v11a_build_hashes_2.txt` was empty and hashed to the empty file digest above.
- Frozen artifact hashes:
  - `APP.BIN`: `9fc3632b44d50a038296fe98220cab76426f5532dfa44b9994829e958222c781`
  - `VECTORS.BIN`: `79a1cb9c1ca058ecedd3aa04dd9b65452d8f8e642f2f5701ce867d483b5ad992`
  - `DDR.BIN`: `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`
  - `runner_pmu_interval_v11a.elf`: `9e5143dc5c2114130ad33c65f537d778411dd22afe5fc7a779d6133a61d5723f`
  - `runner_pmu_interval_v11a.map`: `86115990c85231a36db446ad7bb55ec776d4513c8607bf0c2c8923c470239413`
  - `generated_runner.c`: `7d82534dd75af86936bff29e59a95f23161686de7fb62f917392c678d91deb56`
  - `generated_vendor_u85.c`: `a9763c64436c60808110fdab89f27e3e57e4d26e82bfa1c07641b19f82453ecb`
  - `generated_vendor_u85.o`: `637c89aa4d16965d74d71da53d69fd7c0dcd78a8084f56714fe0d6cf63888f22`
  - `preprocessed_runner.i`: `f3f238b75b1cfbea8f41f0451cc63142dd32380e1fd88ba6995d1781198908f0`
  - `pmu_interval_v11a_manifest.json`: `5211b8f0d32f5de34051bf7d7355d013a86ccef2162442bd6c8031b8f73202ba`

Board qualification is complete. The frozen post-board result and claim
boundary are recorded in `PMU_INTERVAL_ENTRY_DIAG_V11A_BOARD_RESULT.md`.
The firmware, schema, manifest, and frozen artifact identity above were not
changed by the board campaign.
