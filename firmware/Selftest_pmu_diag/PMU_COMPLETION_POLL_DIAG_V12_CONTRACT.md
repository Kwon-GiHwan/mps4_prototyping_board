# PMU_COMPLETION_POLL_DIAG_V12

`PMU_COMPLETION_POLL_DIAG_V12` is a diagnostic-only hard-bypass variant. It does not qualify Production, latency, `T_npu`, or MLEK measurement.

Frozen identity:
- Schema version: `12`
- Build ID: `0x32314950`
- Runner source SHA-256: `69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b`
- Vendor source SHA-256: `bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf`

Measured checkpoints:
- `T2`: after submit write and before completion observation helper
- `P0`: poll helper entry timestamp
- `P1`: first `STATUS & 0x02` success observation
- `P2`: helper exit timestamp, before helper return and before `CMD=2`

Hard-bypass rules:
- Runtime vector target remains the exact stock `u85_irq_handler`.
- The stock `wait_for_irq()` body and stock ISR body are retained in source. On the measured path, V12 replaces the runtime `NVIC_EnableIRQ()` site and the measured completion-wait block rooted at the single `wait_for_irq()` callsite, including the explicit poll result, success/timeout split, QREAD/CMD=2 sequencing, and final NVIC cleanup.
- `NPU0_IRQn` stays disabled on the measured path.
- Initial runtime order is fixed:
  - `NVIC_SetVector`
  - `irq_triggered = false`
  - `NVIC_DisableIRQ`
  - `NVIC_ClearPendingIRQ`
  - enabled / pending / active / irq-triggered readbacks
- No active-path `NVIC_EnableIRQ` or direct ISER enable write is allowed.

Polling helper rules:
- Helper symbol is `v12_poll_completion`.
- Helper is `noinline`.
- Helper may perform only:
  - one `P0` timestamp store
  - one `STATUS` load site
  - one completion-bit test using mask `0x02`
  - one `P1` timestamp store on success
  - one `P2` timestamp store on success
  - `return status` on success or `return 0U` on timeout
- Helper may not perform:
  - `CMD` writes
  - extra `STATUS` rereads
  - PMU/NVIC MMIO
  - barriers
  - `printf`
  - per-iteration SRAM stores
  - V10/V11 marker reachability

Wire-schema rules:
- V12 appends exactly 15 fields to the retained qualification record:
  - `t_submit_after_cmd`
  - `t_poll_entry`
  - `t_status_completion_seen`
  - `t_poll_exit`
  - `poll_result`
  - `status_at_success`
  - `installed_vector`
  - `nvic_enabled_before_submit`
  - `nvic_pending_after_initial_clear`
  - `nvic_active_before_submit`
  - `irq_triggered_before_submit`
  - `nvic_pending_before_final_clear`
  - `nvic_pending_after_final_clear`
  - `nvic_active_after_cleanup`
  - `irq_triggered_after_cleanup`
- `P1/P2` and `status_at_success` are explicitly emitted invalid/zero when `poll_result != V12_POLL_SUCCESS`.

Success-path rules:
- `status_at_success` comes from the helper return value.
- `irq_history_mask` is derived from that exact `status_at_success`.
- Ordering is fixed:
  - `CMD=2 #1`
  - `QREAD`
  - `CMD=2 #2`
- Success path contains exactly two `CMD=2` writes.

Timeout-path rules:
- Timeout path contains exactly one `CMD=2` write.
- Timeout ordering is fixed:
  - timeout report / sticky flag
  - timeout `QREAD`
  - timeout `CMD=2`
- Timeout must not synthesize `P1`, `P2`, or a success-style diagnostic cycle.
- Timeout leaves `poll_result != V12_POLL_SUCCESS`, so diagnostic-cycle fields stay invalid and must not be emitted as a usable completion-observation value.
- Timeout is fail-closed: after a timeout sample, the same boot is not reused for characterization and the next attempt requires a fresh boot.

Cleanup rules:
- Both branches converge at common cleanup.
- Cleanup order is fixed:
  - pending before clear
  - `NVIC_ClearPendingIRQ`
  - pending after clear
  - active after cleanup
  - irq-triggered after cleanup
  - `CMD=0`
  - H-PRINTF seam
  - terminal `CMD=0xC`
- The timeout branch may still reach the retained H-PRINTF / PMU cleanup path, but that does not upgrade the sample to valid characterization output.

Interpretation rules:
- `submit_to_status_completion_observed_cycles = delta32(P1 - T2)`
- `u32((P0 - T2) + (P1 - P0)) == submit_to_status_completion_observed_cycles`
- `u32((P0 - T2) + (P1 - P0) + (P2 - P1)) == u32(P2 - T2)`
- This value is characterization-only and not numerically comparable to V11 absolute cycles.
