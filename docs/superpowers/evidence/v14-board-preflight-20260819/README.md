# Actual board preflight, first attempt

Run against the pre-board anchor `619e957` with no code changed. The contract
stopped at the storage stage. The board's own state was never read: the baseline
and candidate stages did not run, and nothing was written anywhere.

## Verdict

```
state                 STOPPED
authorized            false
mandatory UNPROVEN    BLOCK_WRITE_HOLDERS, UART_OWNERSHIP, USB_OFF
transition            INITIAL -> STOPPED  (STORAGE stage is UNPROVEN)
```

| Gate | Verdict | Why |
| --- | --- | --- |
| `MOUNT_COUNT` | PASS | `findmnt` shows no row for the card |
| `BLOCK_WRITE_HOLDERS` | UNPROVEN | a root-inclusive holder check could not be run |
| `UART_OWNERSHIP` | UNPROVEN | same: user-visible holders are zero on all four ports, root-owned ones could not be established |
| `USB_OFF` | UNPROVEN | USB_OFF was never issued or confirmed in this session, and `/dev/sdb` is present |

## What blocked it

Two operational preconditions, neither of them a defect in anything qualified:

1. **`sudo -n` is unavailable on `gihwan`** -- it asks for a password. The
   inherited contract requires the UART holder check to include root-owned
   processes, and a check that cannot see root proves nothing about root. This
   is the exact state this project stopped at once before, and it is why the
   gate has three values: `UART = UNPROVEN`, not `false` and not
   "probably clear".
2. **`/dev/sdb` and `/dev/sdb1` are present**, so the board is in a USB-on
   state. Entering a normal run requires USB_OFF confirmed and the device
   absent. Issuing USB_OFF is a board transition and was not performed: the GO
   for this step covers observation, and stopping here preserves the failure
   domain rather than changing state to make a gate go green.

Neither was fixed by deploying anything. The manager's rule was explicit --
do not try to repair a preflight failure by deploying V14 -- and there was
nothing to repair in the first place: the run stopped because two facts could
not be established, not because the board is unhealthy.

## Raw observations

`raw_observations.txt` carries the commands and their output verbatim.
`readings.json` is what those observations were transcribed into, and
`verdict.json` is what the contract returned for them. The transcription is the
only human step, and it is deliberately conservative: every fact that could not
be established is `null`, which the contract reads as UNPROVEN.

## To proceed

Either would unblock the storage stage:

- non-interactive `sudo` on `gihwan` for the holder checks, or another way to
  establish root-inclusive ownership of the four FTDI ports and the block device
- USB_OFF issued and confirmed through the qualified procedure, leaving
  `/dev/sdb` absent

Both are decisions for the operator. Nothing in the qualified code changes.

---

# Second attempt: 12/12 PASS

The two blockers were operational and both were cleared without touching any
qualified code.

1. **Root-inclusive ownership.** The operator supplied sudo credentials. The
   credential itself is not recorded here or anywhere in the evidence tree, per
   the standing rule in `PMU_QUAL_PROCEDURE.md`; only the fact that a
   root-inclusive check was performed. It found zero holders on `/dev/sdb`,
   `/dev/sdb1` and all four FTDI ports, and zero mounts.
2. **USB_OFF.** Re-examined before issuing, because the procedure calls
   USB_OFF-while-mounted the most dangerous action it defines. The precondition
   it demands -- not mounted, ownership established -- was satisfied first.
   `USB_ON`/`USB_OFF` are MCC console commands over serial, so no physical
   access was required and the action is reversible with `USB_ON`. MCC replied
   `Disabling debug USB...` and `/dev/sdb*` disappeared.

Ordering mattered: ownership was measured **before** the serial port was
opened, so the harness would not appear as a holder of the port it was about to
use. Holders were re-checked after closing it and were still zero.

## Storage stage

| Gate | Verdict |
| --- | --- |
| `MOUNT_COUNT` | PASS -- 0 |
| `BLOCK_WRITE_HOLDERS` | PASS -- 0, root-inclusive |
| `UART_OWNERSHIP` | PASS -- all four ports free, root-inclusive |
| `USB_OFF` | PASS -- confirmed, `/dev/sdb` absent |

## Baseline stage

Observed on the known-good image already on the card. Nothing was deployed.

| Gate | Verdict | Observation |
| --- | --- | --- |
| `DDR_SELFTEST` | PASS | `DDR memory test at 0x70000000: PASSED` |
| `CPUWAIT` | PASS | `Clearing SCC CPUWAIT` |
| `PING_LIVENESS` | PASS | 3/3 answered, every one `state=1` (IDLE) |
| `PROTOCOL_ERRORS` | PASS | all seven counters zero across all three pings |

`raw_ping_counters.json` carries the three replies verbatim.

## Candidate stage

Run once per variant, binding the four V14 gates to the bytes that would
actually be written -- `FINAL8_A/<variant>/{APP,VECTORS,DDR}.BIN` -- against the
digests that variant's manifest declares.

| Variant | Gates | State |
| --- | --- | --- |
| Q | 12/12 PASS | `DEPLOYMENT_AUTHORIZED` |
| QS | 12/12 PASS | `DEPLOYMENT_AUTHORIZED` |
| SQ | 12/12 PASS | `DEPLOYMENT_AUTHORIZED` |

## Result

```
ACTUAL BOARD PREFLIGHT

Inherited gates       8/8 PASS
V14-specific gates    4/4 PASS
FAIL                  0
UNPROVEN              0

Final state           DEPLOYMENT_AUTHORIZED   (Q, QS and SQ)

V14 deployment        NOT STARTED
Board campaign        NOT STARTED
```

The board was read and transitioned only as the qualified procedure defines --
`USB_OFF` and `REBOOT`, both MCC console commands. No SD write, no firmware
replacement, no configuration change, no V14 image deployed.
