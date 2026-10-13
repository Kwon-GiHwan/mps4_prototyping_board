# V15 implementation protocol — Amendment 4

**The wire ABI version is 14. "V15" is the qualification generation.**

Found by the one authorized live qualification run. Prior anchors are not
rewritten. The firmware is not changed and was not redeployed: the deployed
`APP`/`VECTORS`/`DDR` identity remains valid.

## What the live frame showed

The board answered, and the production parser rejected its own firmware's frame:

```
unsupported schema 14: PMU_COMPLETION_S5_ONLY_CONTROL_V15 reads schema 15 only
```

The deployed firmware writes **14** into the frame header. The host read 15
only. No real frame was parseable.

## Why 245 tests did not catch it

`verify_wire_contract()` compared the generator's Python constant
`SCHEMA_VERSION = 15` against the parser's `SCHEMA_VERSION = 15` and passed —
while the C those same files emit says:

```c
#define PMU_DIAG_SCHEMA_VERSION 14U
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 14U, "...: schema must be 14");
```

Two host-side declarations descended from one assumption are not two
independent declarations. Amendment 2 called this check a strength because the
two tuples were declared separately rather than imported; separate authorship is
not independence when both authors believed the same wrong thing.

Every V15 test frame was then built from `wire.SCHEMA_VERSION`, so both sides of
every fixture carried the same wrong number and the suite agreed with itself.

## The correction

```
WIRE_SCHEMA_VERSION      = 14   the ABI the firmware writes
QUALIFICATION_GENERATION = 15   the experiment, never on the wire
```

The wire format genuinely *is* V14's: 8-word header, 85-word body, 34-word
appendix, 127 words, `V14M` mailbox marker. Nothing about it is new, so nothing
about it should have carried a new number.

### Amendment 2's discrimination claim is retracted

Amendment 2 said *"schema_version is what separates a V15 frame from a V14 one,
and it is checked before any appendix word is believed."*

It does not. V15 emits 14. Together with the identical appendix, geometry and
mailbox marker, **a V15 frame is shaped exactly like a V14 frame.**

```
FRAME_ESTABLISHES_EXPERIMENT_IDENTITY = False
EXPERIMENT_IDENTITY_AUTHORITY         = "VerifiedCellContext"
```

A schema-14 frame establishes the wire format and nothing about which experiment
produced it. This does not weaken the deployment binding — that is what actually
ties a frame to an image, and it is now the only thing that does.

## The check now reads the firmware

`verify_wire_contract(generated_c)` parses the generated source that was
compiled, whose digest is the one the manifest declares, for:

| | |
| --- | --- |
| `PMU_DIAG_SCHEMA_VERSION` | 14 |
| its `_Static_assert` | 14 |
| `V15_APPENDIX_WORDS` | 34 |
| `V15_MAILBOX_VALID` | `0x5631344D` |
| appendix slot → field | all 34, in order, from the firmware's own writes |

The appendix order is no longer two Python tuples compared to each other. It is
the host tuple against the firmware's `d.<field> = mailbox[N]` assignments.

## A second defect the same run exposed

The classifier read a **successful** run as failed.

It used `VENDOR_SUCCESS = 0`, borrowed from the runner's `VENDOR_RETURN` table.
The firmware's mailbox uses a different encoding entirely:

```c
#define V15_PRIMARY_NOT_RUN     0U
#define V15_PRIMARY_OBSERVED    1U
#define V15_CONVERGENCE_NOT_RUN 0U
#define V15_CONVERGENCE_SUCCESS 1U
```

So `0` means the phase never ran. The check was not merely wrong, it was
inverted: it would have rejected every valid run, and treated "never ran" as
success. `verify_result_enums()` now checks all ten values against the emitted
vendor C.

Same root cause as the schema: a host constant asserted about firmware and never
compared to it.

## The qualification frame is not campaign data

The one live frame is isolated in its own namespace, and the analyzer refuses a
campaign containing a qualification boot:

```
RULE_QUALIFICATION_FRAME_IN_CAMPAIGN
```

That is how "just one run to check" becomes a sample, so it is a rule rather
than a convention.

## Result of reprocessing the captured frame

The full production path, on the frame already in hand — no redeploy, no second
run:

| stage | |
| --- | --- |
| verified deployment context | `Q_S5_EQUIVALENT` |
| parser | schema 14, variant S5, run_sequence 1 |
| collector | accepted, `sample_valid = True` |
| normalized record | mode carried, origin `STATIC_IMAGE_EVIDENCE` |
| classifier | valid |
| analyzer | **refused**: `RULE_CELL_INCOMPLETE`, 1 of 10 runs |

The analyzer stopping is correct, not a shortfall. No one-shot mode was added
and the collector was not bypassed.

```
TASK11 = LIVE_PATH_VERIFIED_PENDING_CAMPAIGN
```

Not `E2E_REQUALIFIED`. The final closure belongs to the 3×10 campaign.

## Provenance

| | |
| --- | --- |
| design `58b0cad`, plan `3ca7bb1`, Task 1 `d96fa97` | unchanged |
| amendments 1, 2, 3 | unchanged; A2's discrimination claim retracted here |
| firmware | unchanged, not redeployed |
| deployed artifact identity | unchanged and still valid |
