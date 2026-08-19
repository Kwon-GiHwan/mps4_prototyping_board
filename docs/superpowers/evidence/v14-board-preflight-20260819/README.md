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
