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
