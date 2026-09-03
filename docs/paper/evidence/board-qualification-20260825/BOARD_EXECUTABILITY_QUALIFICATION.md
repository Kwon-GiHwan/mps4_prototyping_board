# Board executability qualification — 7/7 workloads QUALIFIED

```
BOARD_EXECUTABILITY_QUALIFICATION   7 / 7 QUALIFIED
FORMAL_BOARD_SAMPLES                0
Stage B1                            HOLD
```

Compile and link success is not runtime executability on a concrete target — the
FVP pass established that with six `NOT_EXECUTABLE_MEMORY` cells. So every
workload was executed once on hardware before any formal sample.

| workload | verdict | NPU TOTAL | ACTIVE | IDLE | `TOTAL==A+I` | family | restore |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rnnoise_INT8` | QUALIFIED | 56,460 | 50,381 | 6,079 | ✅ | ✅ | 4/4 |
| `kws_micronet_m` | QUALIFIED | 97,273 | 91,336 | 5,937 | ✅ | ✅ | 4/4 |
| `ad_medium_int8` | QUALIFIED | 152,528 | 146,587 | 5,941 | ✅ | ✅ | 4/4 |
| `vww4_128_128_INT8` | QUALIFIED | 242,265 | 236,320 | 5,945 | ✅ | ✅ | 4/4 |
| `yolo-fastest_192_face_v4` | QUALIFIED | 454,619 | 448,625 | 5,994 | ✅ | ✅ | 4/4 |
| `mobilenet_v2_1.0_224_INT8` | QUALIFIED | 1,456,543 | 1,450,608 | 5,935 | ✅ | ✅ | 4/4 |
| `wav2letter_pruned_int8` | QUALIFIED | 4,141,085 | 4,135,110 | 5,975 | ✅ | ✅ | 4/4 |

Seven distinct `TOTAL` values — no two workloads produced the same record, so no
cell ran a stale or wrong binary.

Every run: exact deployment read-back, fresh boot health, one inference,
completion marker, no fatal/NPU error, complete profile block, `TOTAL > 0`,
`TOTAL == ACTIVE + IDLE`, `U85_SRAM_EXT_FAMILY`, clean restore and postflight.

**The seven-workload RQ3 universe is ESTABLISHED.** No workload was dropped and
no reduction to six was needed.

## `wav2letter` runs here, and does not on U55

`wav2letter_pruned_int8` was `NOT_EXECUTABLE_MEMORY` on all three low-MAC
SSE-300/U55 cells under `Shared_Sram`, and it executes on U85/`Dedicated_Sram`
hardware. That is consistent with the FVP finding — the constraint was the
platform memory map with SRAM-resident weights, not the workload itself.

Stated as consistency, not as a new result. RQ3 board data is not yet acquired.

## Postflight ordering fix — confirmed on hardware

Both earlier attempts recorded `postflight /dev/sdb absent = FAIL`, because the
postflight reboot re-presents the debug USB card. The corrected contract

```
REBOOT -> wait for postflight state -> USB_OFF -> assert absent
```

now reports **PASS** in all six runs with no manual intervention. `USB_OFF ->
REBOOT -> assert absent` is wrong and is rejected by a guard that raises before
any serial I/O.

Thirteen offline mutation tests cover both orderings (8 capture, 5 postflight).

## Not performed

These are qualification data, not paper samples. No ranking, normalized cost,
repeatability, or FVP-versus-board comparison was computed from them.

```
FORMAL_BOARD_SAMPLES   0
```

## Board state at close

Original image restored 4/4 by hash after every run; `/dev/sdb` absent, mounts 0,
root-inclusive UART holders 0, DDR PASSED, CPUWAIT cleared.
