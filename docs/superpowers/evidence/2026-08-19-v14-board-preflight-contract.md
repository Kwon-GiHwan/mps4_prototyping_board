# V14 board preflight contract

Step 6. The board is not touched here. What is built is the contract that
decides whether it may be.

## What this is, and what it is not

V14 does not write a new board safety policy. The operational contract that
V11-A, V12 and V13 each ran against a real board already exists and already
qualified; what did not exist was an executable form of it. Every inherited
threshold is cited rather than chosen, and pinned by commit and blob hash --
a threshold whose source is "the current version of a document" drifts.

| Gate | Threshold | Normative source |
| --- | --- | --- |
| `MOUNT_COUNT` | `mount_count == 0` | `PMU_QUAL_PROCEDURE.md` @ `82f9311021`, blob `fe6805acd5a5` |
| `BLOCK_WRITE_HOLDERS` | write holders == 0 | V12 board result @ `f7da7e85bb50`, blob `61bcc6c1ae37` |
| `UART_OWNERSHIP` | root-inclusive holders == 0 on ttyUSB0..3 | V11-A board result @ `f1948bcda523`, blob `7355f473b060` |
| `USB_OFF` | USB_OFF confirmed, `/dev/sdb` absent | `PMU_QUAL_PROCEDURE.md` |
| `DDR_SELFTEST` | self-test PASSED | `PMU_QUAL_PROCEDURE.md` |
| `CPUWAIT` | cleared | `PMU_QUAL_PROCEDURE.md` |
| `PING_LIVENESS` | 3/3 answered from IDLE | V13 board result @ `d49fa5fe5b3a`, blob `6c98a08221d2` |
| `PROTOCOL_ERRORS` | all seven counters zero | `PMU_QUAL_PROCEDURE.md` |

The seven counters are spelled as the procedure spells them: `rx_overrun`,
`bad_magic`, `bad_version`, `bad_crc`, `length_error`, `sequence_error`,
`parser_resync`. A reading carrying six of them proves nothing about the
seventh, and is UNPROVEN rather than PASS.

The V14 layer is kept separate, because a diagnostic has no business relaxing a
board safety threshold: `CANDIDATE_IDENTITY`, `VARIANT_IDENTITY`,
`MANIFEST_REPLAY` and `STATIC_GATE_EVIDENCE` are about this candidate and cite
no inherited authority. The suite checks the separation in both directions.

## Three values, not two

A gate answers PASS, FAIL or UNPROVEN, and `GO` requires every mandatory gate to
be PASS. The third value is not decoration. This project has already stopped at
exactly that state: no user-visible UART holder, and root ownership unprovable
because sudo was unavailable. A boolean would have had to call that true or
false, and either answer is a lie.

## The order is the safety property

```
INITIAL → STORAGE_SAFE → BASELINE_LIVE → DEPLOYMENT_AUTHORIZED
                ↓              ↓                    ↓
             STOPPED        STOPPED              STOPPED
```

Storage runs before anything on the board changes, so a mounted card or a held
UART stops the run while it is still reversible. The baseline gate proves the
known-good image is alive *before* V14 is deployed: a failure after deploying
onto a board that was already dead cannot be attributed to V14 or to the board.
`require_authorization()` raises rather than returning false, so a caller who
forgets to look at the answer still cannot deploy.

## Fixtures

51 tests. The gates are pushed at their thresholds rather than at their happy
paths:

| Gate | Cases |
| --- | --- |
| PING | 3/3 IDLE → PASS; 2/3 → FAIL; one unanswered → FAIL; three answers with one outside IDLE → FAIL; a ping with no state → UNPROVEN |
| protocol errors | all seven zero → PASS; each of the seven incremented in turn → FAIL; one counter absent → UNPROVEN |
| DDR / CPUWAIT | both → PASS; DDR fail → FAIL; DDR PASS with CPUWAIT uncleared → FAIL; absent reading → UNPROVEN |
| UART | four free → PASS; a user holder → FAIL; a root-owned holder → FAIL; root-inclusive check not run → UNPROVEN; a port with no reading → UNPROVEN |
| storage | card absent, zero mounts → PASS; card present after USB_OFF → FAIL; a mount → FAIL; a write holder → FAIL; unknown holder status → UNPROVEN |
| candidate | digests match → PASS; drifted, missing, extra → FAIL; empty qualified table → UNPROVEN |
| sequencing | storage failure stops before the baseline is read; a dead baseline stops before the candidate; UNPROVEN stops like a failure; stages out of order, twice, or after STOPPED all refuse; authorising without running the gates raises |

## Mutation tests

| Mutation | Caught by |
| --- | --- |
| treat UNPROVEN as PASS | the unproven-stops-the-run test |
| accept any PING count | the 2/3 test |
| ignore whether the UART check saw root | the unprovable-ownership test |
| authorise unconditionally | the authorisation test |
| remove the stage-order check | a refused stage evaluating nothing |
| let a state transition to itself | the transition-table tests |

The last two survived the first attempt. Two guards stood between a caller and
an out-of-order stage -- the order check and the transition table -- and either
alone made the call raise, so a test asserting only "it raises" could not tell
which one was working. Neuter either and the suite stayed green. Both are now
pinned separately.

## Status

```
BOARD PREFLIGHT CONTRACT     UNIT-QUALIFIED
ACTUAL BOARD PREFLIGHT       NOT RUN

Inherited board gates        8/8 QUALIFIED
V14-specific gates           4/4 QUALIFIED
mandatory UNKNOWN states     0
targeted negatives           all RED for intended reason
illegal state transitions    all rejected

actual board touched         NO
SD/UART touched              NO
```

## Verification level

- Executed: 51 preflight tests, six mutations, and the host modules alongside it
  (comparator 45, protocol 60).
- Not executed: the board, SD or UART. Nothing in this step reads hardware; the
  contract decides from readings someone else will collect.
