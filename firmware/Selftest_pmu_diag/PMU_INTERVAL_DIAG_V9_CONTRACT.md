# PMU_INTERVAL_DIAG_V9

`PMU_INTERVAL_DIAG_V9` is a separate diagnostic-only schema-9 image. It does not modify or reinterpret schema-v8 Q0/Q1/CFG/Production artifacts.

Checkpoints:
- `T0`: existing `t_call_enter`
- `T1`: immediately before the vendor start-submit `NPU_REG_CMD` sequence
- `T2`: immediately after the vendor start write and before `wait_for_irq()`
- `T3`: immediately after the ISR `NPU_REG_STATUS` read confirms completion and before `irq_triggered=true` / IRQ clear
- `T4`: existing `hook_entry_timestamp`
- `T5`: existing `t_call_return`

Rules:
- Only `T1/T2/T3` are appended to the v8 wire shape.
- `T1/T2/T3` each add exactly one direct `DWT->CYCCNT` load and one volatile timestamp store.
- No new PMU/NPU MMIO, no new logging, no barrier, no helper call, no count field, and no loop are allowed at the checkpoint itself.
- `VERIFY_OUTPUT` remains enabled. `T4->T5` therefore includes the existing verify-output work and must never be labeled as latency or `T_npu`.
- `T2->T3` is a contended busy-poll interval only. It is not NPU execution time.
- `T3->T4` includes the rest of the ISR and the vendor driver path up to the
  pre-release seam. It is not pure completion overhead.
- The generated private `u85.c` copy is a diagnostic mechanism only. It breaks
  reference-source provenance and can never be promoted as the Production
  END_ONLY implementation.
- The analyzer is characterization-only and must never present the data as latency, `T_npu`, performance, Gate 7, MLEK, or Production evidence.
- The V9 PMU delta is named `v9_perturbed_window_cycles`; it is explicitly not comparable to the v8/CFG `npu_pmu_window_cycles` because these timestamp probes perturb the image.

Final-ELF attestation:
- The final ELF must contain exactly one NPU CMD submit store at `0x50004008` strictly between the attested T1 and T2 stores.
- T3 must be inside the completion-condition body, after the existing STATUS read and condition test and before `irq_triggered=true`.
- T0/T5 use bounded instruction windows around the sole `dispatch -> run_fixed_inference` call. The gate also pins their record stack slots to `sp+96` and `sp+100`; a coincidental DWT load/store elsewhere in either window is rejected.

Fixed-image validity:
- `ts_source_valid` is exactly 1.
- The retained power seam tuple is exactly `(power_seam_id, power_rehold_performed, rehold_guard_cycles) = (3, 0, 0)`.
- PMU MMIO counts are fixed at window `r58/w8` and hook-local `r16/w1`; any other count invalidates the sample.
- The externally pinned APP/VECTORS/DDR, ELF/map, generated-source, and manifest digests are part of the archive/analyzer identity contract, not self-attested sample metadata.

Frozen pre-board identity (two clean ARM builds were byte-identical):

| item | SHA-256 |
|---|---|
| `APP.BIN` | `60886be93bd04c598af0e41147e512aca1940fd8ab4dbf23f3929cdb38f124ac` |
| `VECTORS.BIN` | `1b86143c1bf9ba06263ffe1744b41f57b79f5d50f9db67bd9fc0eac33b67c81f` |
| `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| `runner_pmu_interval_v9.elf` | `cabcf160f745a3923f71022e041e866ac33a2c3f23be04668147f3111cd93042` |
| `runner_pmu_interval_v9.map` | `b06130db4e771015c61a1fa6caa68e1ffeacaeb22d274dc9ecdcaaf31b22cb88` |
| generated runner | `8abe3a48bbbc2ae56ba698314e05b7a27299a959273f6e0d4aa815994f207a30` |
| generated vendor `u85.c` | `7515461fceeb08dad517e5031cab81832feaa7b163dce56dc3737ece64850aad` |
| generated vendor `u85.o` | `5e3ad64c83a2a961cc7b0662d93c0b7ad394e494b0259bb4336377f7e672bee0` |
| preprocessed runner | `8cd0356b491b11dceaf98e253924a1e5c61c75b9a26bb41976670f1b7e4abeec` |
| final manifest | `b2a5e98c5ceb82a2262fe64653498eca1a63f00ed5011a1b9973240b9a52d71e` |

The final ELF attests the sole submit store at `0x31002322`. The manifest also
pins the T0/T5 record offsets to 96/100 bytes. Any rebuild, changed compiler,
changed instrumentation, or changed manifest must establish a new identity;
these values are not portable constants.

Campaign and restoration contract:
- First pass is exactly three positive, distinct full-boot indices × ten consecutive records per boot. Each boot must restart target `run_sequence` at 1 and contain exactly 1..10.
- Every record is append-only, has byte-identical COMPLETE/GET evidence, and must pass the complete validity contract. A missing, duplicate, invalid, or identity-mismatched record is STOP, not a partial dataset.
- The campaign only localizes the earliest coarse interval where the observed V9 floor group and excursions diverge. It does not explain the mechanism and is not Gate 7.
- After collection, restore the pre-campaign APP/VECTORS/DDR backup, verify its hashes, boot/PING/idle state, unmount cleanly, and return the board to USB_OFF. Production END_ONLY remains frozen throughout.
- Deployment and restoration follow the fail-clean mount/backup boundaries in
  `PMU_QUAL_PROCEDURE.md` section 8. The existing verified backup is reused;
  no credential is placed in a command, log, archive, or document.
