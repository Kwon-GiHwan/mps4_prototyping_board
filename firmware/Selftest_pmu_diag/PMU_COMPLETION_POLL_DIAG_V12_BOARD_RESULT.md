# PMU_COMPLETION_POLL_DIAG_V12 board result

Date: 2026-08-14

## Provenance

- Firmware/ELF anchor: `126ef064a3eff8b41429bb8a82c4756dc20fd000`
  (`pmu-completion-poll-v12-preboard`)
- Host Thumb classifier anchor: `de50534b1b92595a04f73ae82e0e5d0d96eb01e3`
  (`pmu-completion-poll-v12-host-thumb-fix-preboard`)
- Evidence root:
  `/home/gihwan/mps4/PMU_COMPLETION_POLL_V12_HOSTFIX_20260814T061500Z/`
- `FINAL_REPORT.json` SHA-256:
  `07003a36d5ba5ee10f656cc088019306b674ee69880c0d4ef4e11356c57aa846`
- `FINAL_EVIDENCE.sha256` SHA-256:
  `0d72f82c8060958ff5a5100877f4710492adbea1088a6e47b3373f2c8ac1304b`

The firmware, ELF, BIN, and manifest bytes were not rebuilt for the host-only
Thumb fix. Their frozen SHA-256 values remained:

```text
APP.BIN     8826f3399e4666f59061e3c5d0e76c494e9660663f400d536a3c6dcd3a553513
VECTORS.BIN 66430b664782848c9d9ce3d1443308fc91ea89dc820b2ed2d71f9599bdfe4071
DDR.BIN     81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
ELF         cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401
manifest    611f095f54f4eaeac47db0b69a666e30e0a694eb313a7728cf839cec5f91ba29
```

The stopped boot45 payload is a regression fixture for the host classifier
only and is not part of this formal dataset.

## Campaign

Fresh boots 47, 48, and 49 each produced run sequences 1 through 10.
All 30 samples were valid, all 61 validity terms were true for every sample,
and no polling timeout occurred. Raw COMPLETE and GET payloads were
byte-identical and their archived SHA-256 values were re-derived independently.

```text
submit_to_status_completion_observed_cycles
  min / max       737 / 5859
  median          1907
  hard floor      737, 11/30
  excursions      19/30

d0 = P0 - T2      22, 30/30
d2 = P2 - P1      11, 30/30
```

The floor/excursion structure occurred in all three independent boots while
the NPU IRQ remained disabled and completion was observed by STATUS polling.
Therefore IRQ handler execution, NVIC exception servicing, and Cortex-M
exception entry are not required for the observed variability. The remaining
observation region contains NPU command execution/completion, STATUS
visibility, and polling-sampling interaction; this campaign does not separate
those mechanisms.

## Interpretation limits

This result is diagnostic only. It is not numerically comparable to V11-A and
must not be named latency, `T_npu`, a performance baseline, Production data, or
MLEK data. Production END_ONLY remains frozen.

## Restoration

The pre-deployment APP/VECTORS/DDR files were restored byte-for-byte. Restore
boot50 passed DDR self-test and CPUWAIT clear; runner PING was 3/3 IDLE with all
seven protocol-error counters zero. Final state was USB_OFF, `/dev/sdb` absent,
zero mounts, and zero userspace holders (including root-owned processes) on all
four FTDI tty nodes at the checked instant.
