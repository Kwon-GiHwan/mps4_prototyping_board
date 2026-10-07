# V14 board campaign

Round-level evidence. Each cell is one deploy, one fresh full boot, and ten
sequential runs, driven by `host/run_pmu_completion_visibility_v14.py` against
the artifacts the pre-board anchor qualified (`FINAL8_A/<variant>`). No firmware
or gate code was changed during the campaign.

## Pre-campaign backup

The original card contents were read out before the first write, through the
bounded SD path, and match the known-good hashes exactly:

| Artifact | sha256 (16) |
| --- | --- |
| APP.BIN | `ffa3e5bd0363f791` |
| VECTORS.BIN | `45e943c577e37441` |
| DDR.BIN | `81d37a219a6b4141` |

`PRE_V14_BOARD_BACKUP.sha256` carries the full digests; the files themselves sit
on the authorized host, outside this repository.

The user mount failed first -- `udisksctl` needs an interactive polkit agent that
a non-interactive SSH session does not have, and the exact error the procedure
names was observed. That opened the procedure's 2-EXC bounded sudo mount
exception, whose two conditions were both met and recorded: the polkit failure
was observed rather than assumed, and the operator approved the exception. The
credential itself is recorded nowhere.

## Round 1: Q -> QS -> SQ

30 valid samples from three independent boots, 10/10 in every cell. Every run's
re-read matched its first read, run sequences were 1..10 with no gap or repeat,
and every cell passed its gates: deployment destination hashes equal to source,
root-inclusive UART holders zero, DDR self-test PASSED, CPUWAIT cleared, runner
answering from IDLE with all seven protocol counters at zero.

| Cell | Boot | Valid | Categories |
| --- | --- | --- | --- |
| Q | `Q-1787115071` | 10/10 | none -- Q observes one register and has no read order |
| QS | `QS-1787115175` | 10/10 | SAME_ITERATION 8, S5_FIRST 2 |
| SQ | `SQ-1787115243` | 10/10 | SAME_ITERATION 7, Q_FIRST 3 |

Two observations, stated as observations:

- the dominant category in both dual variants is SAME_ITERATION, which is a
  statement about the resolution of the polling loop and not about hardware
  simultaneity
- where a category does separate, the minority in each variant names the
  register that variant reads *second* -- S5_FIRST in QS, Q_FIRST in SQ. That is
  the opposite direction from a naive read-order bias, and it is recorded here
  without a conclusion attached to it

Neither is a verdict. The campaign's verdict comes from the analyzer over all
nine cells, and this file exists so the rounds can be read before it runs.

## Round 2: QS -> SQ -> Q

30 valid samples from three more independent boots, 10/10 in every cell, every
gate held, every re-read equal to its first read, run sequences 1..10.

| Cell | Boot | Valid | Categories |
| --- | --- | --- | --- |
| QS | `QS-1787115422` | 10/10 | SAME_ITERATION 7, S5_FIRST 3 |
| SQ | `SQ-1787115490` | 10/10 | SAME_ITERATION 7, Q_FIRST 3 |
| Q | `Q-1787115558` | 10/10 | none |

The R1 pattern repeats on independent boots and in a different position within
the round: SAME_ITERATION dominates both dual variants, and the minority in each
names the register that variant reads second. Still recorded, still not
concluded -- the balanced design exists so that position and time effects are
separated from the variant effect, and that separation needs all three rounds.

Running total: 60 of 90 formal samples, 0 contract violations.
