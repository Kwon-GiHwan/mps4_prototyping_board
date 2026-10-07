# PMU_INTERVAL_FINE_DIAG_V10 board result

This file is the post-board provenance anchor for the frozen V10 diagnostic.
It does not change the V10 firmware, host classifier, or frozen build identity.

## Frozen implementation

- Pre-board commit: `b794cb6718f9a1b9918763dd02ac6eef7e7fe135`
- Pre-board tag: `pmu-interval-fine-v10-preboard`
- Variant/schema/build ID: `PMU_INTERVAL_FINE_DIAG_V10` / `10` / `0x30314950`
- Manifest SHA-256: `1a0eb13c6dbc7181bd85544307d6c643efdfe5e1352b95aa1234eed6c2518792`
- APP.BIN SHA-256: `92e81e5ac51ed56c89eb3cc447ef421334142ec9a2a941990995025d546b00b9`
- VECTORS.BIN SHA-256: `1b86143c1bf9ba06263ffe1744b41f57b79f5d50f9db67bd9fc0eac33b67c81f`
- DDR.BIN SHA-256: `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`
- ELF SHA-256: `6f99df6a35da87be8dca41af7dbe7e16a3c1af84796ac1e159273b3051469dac`

The clean ARM rebuild after the pre-board commit reproduced every frozen hash.

## Board campaign

- Evidence root: `/home/gihwan/mps4/PMU_INTERVAL_FINE_V10_20260810T091906Z/`
- Independent full boots: `36`, `37`, `38`
- Samples: `3 x 10 = 30`
- Valid samples: `30/30`
- Per-boot run sequence: `1..10`
- I0/T3 hit count: exactly one in every sample
- `delta32(E0) + delta32(E1) == delta32(D23)`: `30/30`
- Exact golden window and retained PMU/MMIO/release gates: `30/30`

Observed intervals:

```text
E0 = T2 -> I0   min 743   max 5798   distinct 22
E1 = I0 -> T3   min 76    max 76     distinct 1
D23             min 819   max 5874   distinct 22
```

The outer V10 window had a floor of `3321` in `2/30` samples. All `28`
excursions first diverged in E0; none diverged in E1.

## Terminology correction

E0 is **submit-to-first-ISR-probe**, also called the **pre-I0 interval**. It is
not strictly "pre-ISR": I0 is emitted after hardware exception entry/stacking,
the compiler prologue, and preparation of the DWT base address.

E0 includes at least:

```text
NPU command processing/completion
-> IRQ assertion
-> NVIC recognition/delivery
-> Cortex-M85 exception entry and hardware stacking
-> compiler prologue and DWT base preparation
-> I0
```

The result therefore establishes that the variation is already present before
I0 and is not introduced by the stock STATUS read/completion-bit path from I0
to T3. E0 is not NPU execution time, latency, `T_npu`, or a performance value.

## Evidence and restoration

- `RUNTIME_AUDIT.txt`: `61ce24c622a7ba1bcf3bad1fa51c491d96edacbf29024e6bfd012e5ba9611a4c`
- `CAMPAIGN_REPORT.txt`: `e8cb97b8eed8a3d36e899311425d73ae3780b51bb822e31bde7cc06ea473000f`
- `CAMPAIGN_REPORT.json`: `70ff60acdb51cc551e6985f7eaf9ce68dc349741bc1b846e2edbbe0ee66e547b`
- `SAMPLES.sha256`: `2014841813e893154d3e292d341266a7cb75e7118b6611b0e62e8a452d110262`
- `FINAL_EVIDENCE.sha256`: `f52a0fc1e97d51cfb399e87b51defa04488d03871023a026b3b44f6518028cc2`

The original APP/VECTORS/DDR images were restored byte-for-byte. Restore boot
39 passed DDR and CPUWAIT gates; PING returned IDLE with all seven error
counters zero. Final state was unmounted, USB off, `/dev/sdb` absent, and all
four UARTs free.

## Frozen verdict

```text
PMU_INTERVAL_DIAG_V9        FROZEN / EVIDENCE COMPLETE
PMU_INTERVAL_FINE_DIAG_V10  FROZEN / EVIDENCE COMPLETE
D23 variation               LOCALIZED TO T2 -> I0
I0 -> T3                    FIXED 76 / 30 OF 30
T2 -> I0 mechanism          UNRESOLVED
Production END_ONLY         FROZEN
MLEK performance            BLOCKED
```
