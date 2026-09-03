# V15 actual board preflight — 2026-08-23

Authorized scope: **actual board preflight only.** V15 deployment and campaign
remained on HOLD throughout and nothing was written to the card.

Run against the pre-board anchor `v15-preboard-anchor` with no code changed.

## Verdict

```
STORAGE   PASS
BASELINE  PASS

FAIL      = 0
UNPROVEN  = 0

BOARD_BASELINE_READY
CANDIDATE_SOURCE_VERIFIED
V15_DEPLOYMENT = NOT_STARTED
```

The CANDIDATE stage was **not entered**. Entering it sets
`DEPLOYMENT_AUTHORIZED` in the inherited contract, which is exactly what is on
hold, so candidate verification was done as source verification instead.

| Stage | Gate | Verdict | |
| --- | --- | --- | --- |
| STORAGE | `MOUNT_COUNT` | PASS | no card mount |
| STORAGE | `BLOCK_WRITE_HOLDERS` | PASS | zero |
| STORAGE | `UART_OWNERSHIP` | PASS | four ports free, **root-inclusive** |
| STORAGE | `USB_OFF` | PASS | confirmed, `/dev/sdb` absent |
| BASELINE | `DDR_SELFTEST` | PASS | `PASSED` |
| BASELINE | `CPUWAIT` | PASS | cleared |
| BASELINE | `PING_LIVENESS` | PASS | 3/3 answered from IDLE |
| BASELINE | `PROTOCOL_ERRORS` | PASS | all seven counters zero |

The root-inclusive claim is not assumed: the same elevated shell reported
`uid=0`, so a check that could not see root-owned holders would have been
visible as such. This is the gate that stopped the first V14 attempt.

## The card, read-only

`PRE_V15_BOARD_BACKUP` was taken with the card mounted `ro`, so a write was not
merely avoided but impossible. The mount options were read back and asserted to
begin with `ro` before any file was touched.

| | on card | expected baseline |
| --- | --- | --- |
| `APP.BIN` | `ffa3e5bd…3597d` | `ffa3e5bd…3597d` ✓ |
| `VECTORS.BIN` | `45e943c5…f06c92` | `45e943c5…f06c92` ✓ |
| `DDR.BIN` | `81d37a21…4ade98` | `81d37a21…4ade98` ✓ |

Byte-identical to `PRE_V14_BOARD_BACKUP`: V14's restore was exact and the board
is at the known-good baseline. The backup copy and an independent on-card read
agree.

## Candidate source, re-verified

Re-measured in the container and unchanged since the anchor:

| | |
| --- | --- |
| `APP.BIN` | `4967fa39…` |
| `VECTORS.BIN` | `6864a22b…` |
| `DDR.BIN` | `81d37a21…` |
| analysis ELF | `49d22540…` |
| raw ELF | `c2373581…` (informational) |
| candidate identity | `0c3ac91a…` |
| manifest | `42bb2310…` |
| comparison mode | `Q_S5_EQUIVALENT` |

The V15 pre-board gate returns eight board-independent checks PASS and
`overall: PENDING_DEPLOYMENT`.

## Two operational facts worth recording

**The images are not at the card root.** They live in `/mnt/SOFTWARE/`. A
collector that assumed the root found nothing, which is a stop rather than a
silent empty backup only because the missing file was reported.

**REBOOT turns the debug USB back on.** After the baseline reboot `/dev/sdb`
and `/dev/sdb1` were present again, so `USB_OFF` had to be reissued to reach
the required terminal state. The correct ordering ends with USB_OFF *after* the
reboot, not before it. Both times, USB_OFF was issued only after the mount was
confirmed gone.

## Not performed

No V15 `APP/VECTORS/DDR` write. No deploy. No V15 UART measurement. No
`VerifiedCellContext` production issuance. No Task 11 final E2E closure. No
campaign. Production `END_ONLY` FROZEN, MLEK BLOCKED.

Deployment authorization is a separate decision and was not requested here.
