# PMU_INTERVAL_FINE_DIAG_V10

`PMU_INTERVAL_FINE_DIAG_V10` is a V10-only diagnostic variant. It is separate from V9 and from Production.

Checkpoints:
- `T0`: existing `t_call_enter`
- `T1`: immediately before the vendor submit `NPU_REG_CMD` write
- `T2`: immediately after that submit write and before `wait_for_irq()`
- `I0`: first executed instruction block inside the stock `u85_irq_handler`, before the existing `STATUS` read
- `T3`: immediately after the existing completion-confirming `STATUS` read and before `irq_triggered=true`
- `T4`: existing target hook entry
- `T5`: existing `t_call_return`

Rules:
- New fine-grain checkpoint: `I0` only. `W1`, `W2`, and `I1` do not exist in V10.
- `I0` may perform only one direct `DWT->CYCCNT` load plus one SRAM timestamp store.
- No `STATUS`/`PMU`/`CMD` MMIO, no `printf`, and no barrier are allowed at `I0`.
- `T3` remains after the existing `STATUS` read and before the flag store.
- Runtime `I0`/`T3` hit counters are updated only after the corresponding timestamp;
  the `I0` invocation counter is after the existing `CMD=2` clear. Both must equal one.
- The static gate must fail closed unless final ELF order proves `T2 < I0 < STATUS read < T3 < flag store < CMD2 < target hook < release`.
- `E0 = T2->I0`, `E1 = I0->T3`, and `D23 = T2->T3`. Host-side interpretation must require `delta32(E0) + delta32(E1) == delta32(D23)` modulo `u32`.
- Characterization only. Not latency, not `T_npu`, not Production, and not MLEK.
- First-pass board gate: 3 independent full boots × 10 consecutive runs. `W1`, `W2`,
  post-T3 flag visibility, and wait-return timing stay outside this diagnostic.
