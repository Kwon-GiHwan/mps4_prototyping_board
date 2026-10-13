# Board measurement-path qualification — QUALIFIED

```
BOARD_MEASUREMENT_PATH        QUALIFIED
BOARD_QUALIFICATION_RUNS      2 cumulative  (1 valid observation)
FORMAL_BOARD_SAMPLES          0
210-sample campaign           HOLD
runner patch                  none
```

Target: FPGA / Corstone-320 / Ethos-U85 / 1024 MAC, `rnnoise_INT8`, anchored
artifact `paper-board-rnnoise-preprobe-anchor`. The board reported `MACs/cc: 1024`,
confirming the intended configuration from the device itself.

## Attempt #1 — preserved, not rewritten

```
deployment / boot / restore     PASS
measurement observation         NOT_OBSERVED
reason                          CAPTURE_STARTED_AFTER_APPLICATION_COMPLETION
```

Kept as its own record. It is **not** relabelled `FAILED` or `NOT_QUALIFIED` and
not deleted. The distinction is load-bearing: `NOT_QUALIFIED` is a finding about
the board, and attempt #1 produced no evidence for one. The listener was opened
after `boot_and_gate()` returned, and `rnnoise` completes in well under a second
on hardware, so the output arrived while no process held the tty — where it is
discarded, not buffered.

## The ordering is now enforced, not observed

```
open ttyUSB1
-> reader thread confirms itself running (threading.Event, 5 s deadline)
-> only then REBOOT
-> continuous capture from before reset
-> wait for completion or fatal condition
```

`assert_capture_before_reset()` raises `CaptureOrderViolation` **before any
serial I/O**, and `boot_and_gate()` refuses to run without a confirmed-running
capture. Postflight reboot is exempt explicitly (`require_capture=False`) rather
than by omission.

Eight offline mutation tests, including the one required: a reset attempted
without a running capture is rejected, and no serial I/O occurs before the guard.

## Attempt #2 — gates

| gate | result |
| --- | --- |
| device absent, mounts 0, root-inclusive holders 0 | PASS |
| **ttyUSB1 holders before capture** | PASS (0) |
| capture owns expected tty, exclusively | PASS (pid in sole holder list) |
| capture-before-reset guard | **ENFORCED** |
| deploy `source == declared == destination` | **4/4 MATCH** |
| DDR self-test / CPUWAIT cleared | PASS |
| marker observed within window | PASS (3,546 bytes) |
| restore | **4/4 MATCH** |
| postflight DDR / CPUWAIT / mounts / UART holders | PASS |

## STATIC and LIVE evidence, kept separate

**STATIC — PASS.** Source-level chain: `StartProfiling` → `hal_pmu_reset` →
`CYCCNT_Reset` + `EVCNTR_ALL_Reset` → start snapshot → exactly one
`RunInference` → `StopProfiling` → end snapshot → delta.
(`UseCaseCommonUtils.cc:69-75`, `Profiler.cc:32-75`, `ethosu_profiler.c:150-190`.)

**LIVE — PASS.** The board's own profile block:

```
INFO - Total number of inferences: 1
INFO - Profile for Inference:
INFO - NPU ACTIVE: 50381 cycles
INFO - NPU ETHOSU_PMU_SRAM_RD_DATA_BEAT_RECEIVED: 143 beats
INFO - NPU ETHOSU_PMU_SRAM_WR_DATA_BEAT_WRITTEN: 135 beats
INFO - NPU ETHOSU_PMU_EXT_RD_DATA_BEAT_RECEIVED: 7838 beats
INFO - NPU ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN: 36 beats
INFO - NPU IDLE: 6079 cycles
INFO - NPU TOTAL: 56460 cycles
```

```
event family      U85_SRAM_EXT_FAMILY          as expected
NPU TOTAL         56460                        present, nonzero
TOTAL == ACTIVE + IDLE   56460 == 50381 + 6079  holds
zero auxiliary counters  none
```

Both must pass for the path to be qualified. Both did.

## Stale exclusion

```
fresh boot                        true
pre-inference PMU reset path      true
exactly one inference             true
complete live profile block       true
nonzero TOTAL                     true
consistency relation holds        true
```

With that chain closed, "the runner reported a stale counter from an earlier
execution" is not a supportable explanation for this observation.

## RQ3 event admissibility

Board-emitted and validly collected on U85: `TOTAL`, `ACTIVE`, `IDLE`,
`SRAM_RD_DATA_BEAT_RECEIVED`, `SRAM_WR_DATA_BEAT_WRITTEN`,
`EXT_RD_DATA_BEAT_RECEIVED`, `EXT_WR_DATA_BEAT_WRITTEN`.

The board set matches the U85 set the FVP builds emit, which is the precondition
for the conditional bottleneck-consistency analysis. That analysis is **not**
performed here.

`CC_STALLED_ON_BLOCKDEP` remains `NOT_EVALUABLE` — present in the driver enum,
never configured by the stock profiler, on either target.

## Not performed

This value is qualification data. No FVP-versus-board difference, ratio, ranking
entry, or relative-cost contribution was computed, and none may be. A comparison
is *available* in the evidence and is deliberately left uncomputed pending
authorization.

```
FORMAL_BOARD_SAMPLES   0
```

## Board state at close

```
original image restored     4/4 by hash
/dev/sdb                    absent
mounts                      0
root-inclusive UART holders 0
DDR                         PASSED
CPUWAIT                     cleared
```

A reproducible detail worth recording: the postflight reboot **re-presents the
USB card**, so `/dev/sdb absent` fails at that point in both attempts. The probe
reports it rather than hiding it, and a follow-up `USB_OFF` closes it. A future
harness should issue `USB_OFF` after the postflight reboot rather than before it.
