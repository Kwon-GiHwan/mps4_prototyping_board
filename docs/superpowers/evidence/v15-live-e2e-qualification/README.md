# V15 live E2E qualification — one run, two defects, path closed to the analyzer

Authorized: exactly one `CB_RUN_PMU_DIAG` as a live E2E qualification probe.
**Not a campaign sample.**

```
formal_campaign_sample = false      qualification_runs    = 1
campaign_id            = none       campaign_sample_count = 0
purpose                = LIVE_E2E_QUALIFICATION
```

## What the run found

The board answered with a 508-byte frame whose independent re-read matched. The
production parser then rejected it, and the classifier misread it. Both were
host defects; the firmware was correct throughout and was never redeployed.

**1. Wire schema.** The firmware writes 14; the host read 15 only. See
Amendment 4. The check that should have caught it compared two host-side Python
constants instead of the emitted C.

**2. Result encoding, inverted.** The classifier used `VENDOR_SUCCESS = 0`.
The firmware writes `0 = NOT_RUN`, `1 = OBSERVED/SUCCESS`. It would have
rejected every valid run and accepted a phase that never ran. This run reported
`primary_result = 1`, `convergence_result = 1` — **it succeeded**, and was being
read as a failure.

## The frame

| | |
| --- | --- |
| magic | `0x31474450` |
| wire schema | 14 |
| total words | 127 (508 bytes) |
| variant_id | 1 (S5) |
| run_sequence | 1 |
| run_rc | 0 |
| primary_result | 1 — `V15_PRIMARY_OBSERVED` |
| convergence_result | 1 — `V15_CONVERGENCE_SUCCESS` |
| first_cmd_end_reached | 1 |
| mailbox_valid | `0x5631344D` |

No cycle or poll value has been read, interpreted, or carried into analysis.

## Reprocessed through the corrected path

Same frame, no redeploy, no second run:

| stage | result |
| --- | --- |
| verified deployment context | `Q_S5_EQUIVALENT` |
| parser | accepted |
| collector | accepted, `sample_valid = True` |
| normalized record | mode carried, origin `STATIC_IMAGE_EVIDENCE` |
| classifier | valid |
| **analyzer** | **refused — `RULE_CELL_INCOMPLETE`, 1 of 10** |

The analyzer refusing is the correct behaviour, not a shortfall. No one-shot
mode was added, the collector was not bypassed, and no cell was dressed up as
complete.

```
TASK11 = LIVE_PATH_VERIFIED_PENDING_CAMPAIGN
```

## Isolation

`RULE_QUALIFICATION_FRAME_IN_CAMPAIGN` refuses any campaign containing a
qualification boot. The boot id carries the marker, so this frame cannot be
counted as a measurement later.

This boot is **not** a campaign boot. When the campaign is authorized it starts
from a fresh full boot as formal Boot 1, `run_sequence 1..10`. The nine
remaining runs are not to be taken here.

## State

```
V15_DEPLOYED              YES        QUALIFICATION_RUNS 1
SOURCE_DESTINATION_HASHES MATCH      CAMPAIGN_SAMPLES   0
VERIFIED_CELL_CONTEXT     PRODUCTION_ISSUED
V15_3x10_CAMPAIGN         NOT_STARTED
```

Candidate identity `0c3ac91a…` and manifest `4be8f268…` are unchanged by the
correction, so the cell context did not need reissuing.

Board closed: USB_OFF, `/dev/sdb*` absent, four UART ports free.
