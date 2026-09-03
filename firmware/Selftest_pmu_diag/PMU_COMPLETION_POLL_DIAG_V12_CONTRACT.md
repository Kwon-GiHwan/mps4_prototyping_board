# PMU_COMPLETION_POLL_DIAG_V12

`PMU_COMPLETION_POLL_DIAG_V12` is a diagnostic-only hard-bypass variant. It does not qualify Production, latency, `T_npu`, or MLEK measurement.

Frozen identity:
- Schema version: `12`
- Build ID: `0x32314950`
- Runner source SHA-256: `69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b`
- Vendor source SHA-256: `bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf`

Frozen pre-board ARM identity (two independent clean builds, 10/10 byte-identical):
- APP.BIN: `8826f3399e4666f59061e3c5d0e76c494e9660663f400d536a3c6dcd3a553513`
- VECTORS.BIN: `66430b664782848c9d9ce3d1443308fc91ea89dc820b2ed2d71f9599bdfe4071`
- DDR.BIN: `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`
- ELF: `cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401`
- map: `d437dd79bac71b48a4691407462826a1726a7de49e00acaa449d25cdface9355`
- generated runner: `f0dc834a5df38232374550984968eabde203db0d0e3fd2985f5944fa78c156dd`
- generated vendor: `f2b1beda5d008daed815222ac2ffa520c4f5318e25bf9e36d11074ae0f17262c`
- generated vendor object: `c590d987cd97f601a88478f3a6b798a4e27608249ef261cad77b0712ab2dce9f`
- preprocessed runner: `cca101f6fda77347300db837cab0b46bc39f0ef358f1d4ecb207767bee20cf31`
- manifest: `611f095f54f4eaeac47db0b69a666e30e0a694eb313a7728cf839cec5f91ba29`
- Build A/B hash diff: empty (0 bytes)

Key final-ELF bindings:
- helper / stock handler: `0x31002344` / `0x3100238C`
- STATUS load / test: `0x31002354` / `0x31002356`
- P0 / P1 / P2: `0x3100234A` / `0x3100236C` / `0x31002372`
- submit / T2 / helper call: `0x31002494` / `0x3100249C` / `0x3100249E`
- success CMD2 #1 / QREAD / CMD2 #2: `0x31002530` / `0x31002532` / `0x31002534`
- timeout QREAD / CMD2: `0x310024C4` / `0x310024C8`
- H-PRINTF call / terminal CMD0xC: `0x31002518` / `0x3100251E`
- runtime vector slot store: `0x310025CA`, exact target `u85_irq_handler`

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

## Host-only Thumb vector binding qualification

The board returns the raw Cortex-M vector-table entry. A valid Thumb handler
therefore carries bit 0 set even though the ELF symbol address in the manifest
is the canonical even code address. Host qualification keeps those two facts
separate:

- `runtime_vector_thumb_entry`: `installed_vector_raw & 1 == 1`
- `runtime_vector_code_address_matches_manifest`:
  `(installed_vector_raw & ~1) == (runtime_vector_target_address & ~1)`
- `runtime_vector_matches_manifest`: the conjunction of those two terms

The classifier preserves `installed_vector_raw`,
`installed_vector_canonical`, the actual `manifest_vector_symbol`,
`manifest_vector_address`, `manifest_vector_canonical`,
`runtime_vector_thumb_bit`, and the aggregate verdict in `vector_identity`.
An even runtime entry fails even when its code address matches. An odd entry
for any other handler, including a nearby address, also fails.

The preserved boot45 latch from the stopped first board attempt is a host
regression fixture only. Its raw vector `0x3100238D` canonicalizes to the
manifest's `u85_irq_handler` symbol `0x3100238C`, so it must reclassify valid
under this host contract. It remains excluded from the formal 3 x 10 campaign.

This is a host-only qualification change. The frozen firmware/ELF/BIN and
manifest bytes above remain bound to commit `126ef064a3eff8b41429bb8a82c4756dc20fd000`
and tag `pmu-completion-poll-v12-preboard`; they are not rebuilt or relabeled
as products of the later host qualification anchor.
