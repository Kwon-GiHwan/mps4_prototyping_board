# PMU_INTERVAL_ENTRY_DIAG_V11A board result

This file is the post-board provenance anchor for the frozen V11-A diagnostic.
It does not change the V11-A firmware, host classifier, or build identity.

## Frozen implementation

- Pre-board commit: `c9a58ca5fdc8c2908e75d244b8aa1eecfc6ef6be`
- Pre-board tag: `pmu-interval-v11a-preboard`
- Variant/schema/build ID: `PMU_INTERVAL_ENTRY_DIAG_V11A` / `11` / `0x41314950`
- Manifest SHA-256: `5211b8f0d32f5de34051bf7d7355d013a86ccef2162442bd6c8031b8f73202ba`
- APP.BIN SHA-256: `9fc3632b44d50a038296fe98220cab76426f5532dfa44b9994829e958222c781`
- VECTORS.BIN SHA-256: `79a1cb9c1ca058ecedd3aa04dd9b65452d8f8e642f2f5701ce867d483b5ad992`
- DDR.BIN SHA-256: `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98`
- ELF SHA-256: `9e5143dc5c2114130ad33c65f537d778411dd22afe5fc7a779d6133a61d5723f`

## Preflight recovery

The initial equipment STOP was closed before deployment. Interactive,
root-inclusive `fuser` and `lsof` checks found no userspace holder of the four
FTDI tty nodes at the checked instant. Without an intervening UART tool, the
known-good image was rebooted and passed DDR self-test, CPUWAIT clear, and
three PINGs in IDLE with all seven protocol error counters zero.

No credential was written to a script, environment variable, evidence file,
or repository file.

## Board campaign

- Evidence root: `/home/gihwan/mps4/PMU_INTERVAL_V11A_20260810T140216Z/`
- Independent full boots: `41`, `42`, `43`
- Samples: `3 x 10 = 30`
- Valid samples and all validity terms: `30/30`
- Per-boot run sequence: `1..10`
- I0/T3 hit count: exactly one in every sample
- J0 path: exactly once follows from the qualified active vector/veneer path
  and the exactly-once I0/T3 observations; there is no independent J0 counter
- `(A0 + A1 + A2) & 0xffffffff == D23`: `30/30`
- Exact golden window, PMU MMIO, overflow, raw reread, manifest, and vendor
  terminal-release gates: `30/30`

Observed intervals:

```text
A0 = T2 -> J0   min 738   max 5805   distinct 17
A1 = J0 -> I0   min 26    max 27     distinct 2
A2 = I0 -> T3   min 83    max 83     distinct 1
D23             min 848   max 5914   distinct 17
```

The perturbed V11-A outer window had an observed floor of `3322` in `13/30`
samples. All `17` excursions first diverged in A0; none was unresolved.

## Claim boundary

V11-A resolves its single question: the V10 D23 variation is present before
the first-veneer-probe. The stock-handler C prologue and STATUS handling after
J0 do not account for the large excursion.

A0 still includes:

```text
NPU command processing/completion
-> IRQ assertion and NVIC recognition/delivery
-> architectural exception entry and vector fetch
-> veneer instructions before the DWT CYCCNT load
-> J0
```

A0 is not pure NPU execution time, latency, `T_npu`, a performance baseline,
Production evidence, Gate 7 evidence, or MLEK data. Separating NPU completion
from interrupt delivery requires a different diagnostic mechanism.

## Evidence and restoration

- `SAMPLES.sha256`: `0b9b5193dd07da4ab5e42c4aa0bc6966c44c56277de96a24a23a82d1a86db153`
- `CAMPAIGN_REPORT.json`: `1604c4d459d31f754fa4c3141b891bb6dc112b5ca31633c01c5efef0c0cf10ac`
- `CAMPAIGN_REPORT.txt`: `ad519aa8a3d66914fa35b148359c51583cd6ffb5f5594567a8862427b821816b`
- `RUNTIME_AUDIT.txt`: `c23467a9f3ceca45667f37dc82f8eef2b1c03fd602b15f4711a97caafd8cc857`
- `FINAL_EVIDENCE.sha256`: `687c31f3f6717f71c9dc18d994117d8ad9599deb86df089b8ddfef4be876c397`

The original APP/VECTORS/DDR images were restored byte-for-byte. Restore boot
44 passed DDR self-test, CPUWAIT clear, and the MCC prompt gate. PING returned
IDLE three times with all seven error counters zero. Final state was unmounted,
USB off, `/dev/sdb` absent, and root-inclusive userspace UART holder checks
were empty.

The first USB_OFF after restoration reported an MCC mass-storage activity
warning even though host `sync` and unmount had succeeded. `/dev/sdb`
disappeared, restore boot passed, and the final post-boot USB_OFF completed
without that warning. The warning is retained in the raw log.

## Frozen verdict

```text
PMU_INTERVAL_FINE_DIAG_V10  FROZEN / EVIDENCE COMPLETE
PMU_INTERVAL_ENTRY_V11-A    FROZEN / BOARD EVIDENCE COMPLETE
D23 variation               LOCALIZED TO T2 -> J0 (A0)
J0 -> I0                    FIXED 26..27 / 30 OF 30
I0 -> T3                    FIXED 83 / 30 OF 30
Mechanism inside A0         UNRESOLVED
Production END_ONLY         FROZEN
MLEK performance            BLOCKED
```
