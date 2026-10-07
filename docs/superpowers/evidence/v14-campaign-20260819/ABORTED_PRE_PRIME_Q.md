# Aborted attempt: Q before priming

**Formal sample count: 0.** Nothing from this attempt entered the dataset.

## What happened

```
CELL ABORT Q: NACK STATE (cmd 0x60, state IDLE)
```

The cell deployed, gated and booted correctly -- destination hashes equal to
source, root-inclusive UART holders zero, DDR self-test PASSED, CPUWAIT cleared,
runner answering from IDLE with all seven protocol counters at zero -- and then
the board refused the first run.

It was right to. `CB_RUN_PMU_DIAG` is accepted only from `ST_INPUT_READY` or
`ST_RESULT_READY`, and the runner was in `ST_IDLE`. The campaign runner had not
walked the state machine to `INPUT_READY` first.

This is an operational failure of the campaign driver, not a V14 observation
failure. The board behaved exactly as its own state table says it should, and no
measurement was taken.

## What was done about it

A priming step was added -- reset, a 64-byte dummy blob, an empty input, the same
walk the qualification runs have always used -- placed **after** the protocol
counter gate so that gate remains a statement about the boot rather than about
what priming left behind. The measured inference is compiled in and reads
neither the blob nor the input.

The cell was then run again from the beginning: fresh deploy, fresh boot, ten
runs. Nothing was carried over from the aborted attempt.

## Execution protocol freeze

From R1 onward every cell in the 90-sample campaign runs the identical protocol.
The runner is frozen at the commit that contains the priming step:

| Item | Value |
| --- | --- |
| campaign runner | `7c3c124` |
| staged on the authorized host | sha256 `b6853c75d42e5270` |
| R1 formal evidence | `7c3c124` |
| aborted pre-prime attempt | this file, 0 samples |

A correction to the record: the runner commit `3e14a06` is the version *without*
priming, which is the one that aborted. The primed runner -- the one every
counted sample has been and will be taken with -- landed in `7c3c124`. The freeze
point is `7c3c124`.

Neither the V14 firmware, the ELF gates, the parser, the classifier, the
collector nor the analyzer changed at any point in this.
