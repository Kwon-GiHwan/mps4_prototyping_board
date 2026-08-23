# V15 live E2E qualification — one run, and what it found

Authorized: exactly one `CB_RUN_PMU_DIAG` as a live E2E qualification probe.
**Not a campaign sample.**

```
formal_campaign_sample = false
campaign_id            = none
campaign_sample_count  = 0
qualification_runs     = 1
purpose                = LIVE_E2E_QUALIFICATION
```

## Result: the production path does not close

The run succeeded. The board answered with a 508-byte frame and the independent
re-read returned the same bytes. Then the production parser **rejected it**:

```
unsupported schema 14: PMU_COMPLETION_S5_ONLY_CONTROL_V15 reads schema 15 only
```

| frame header | |
| --- | --- |
| magic | `0x31474450` — correct |
| **schema_version** | **14** |
| total_words | 127 |
| header_words | 8 |
| run_sequence | 1 |
| run_rc | 0 |

The deployed V15 firmware emits **schema 14** on the wire. The host V15 contract
reads schema 15 only, so no real V15 frame can be parsed by it.

## Why nothing caught this before

The V15 generator carries a Python module constant `SCHEMA_VERSION = 15`, and
that is what `verify_wire_contract()` compares against the parser's 15. But the
C it emits says:

```c
#if defined(PMU_QUAL_SCHEMA_V15)
#define PMU_DIAG_SCHEMA_VERSION 14U
...
_Static_assert(PMU_DIAG_SCHEMA_VERSION == 14U,
               "PMU_COMPLETION_VISIBILITY_DIAG_V15: schema must be 14");
```

So the wire-contract check compared **two host-side Python constants** and never
looked at what the firmware actually writes into the header. The appendix check
next to it compares two Python name tuples and has the same blind spot.

And every V15 host test built its frames from `wire.SCHEMA_VERSION`, so both
sides of every fixture came from the same wrong number. 245 tests agreed with
themselves. This is the project's recurring defect in its purest form: a
contract "verified" between two things that were never independent.

## A documented claim that is false

Amendment 2 states that *"schema_version is what separates a V15 frame from a
V14 one, and it is checked before any appendix word is believed."*

It does not. V15 emits 14. Together with the identical 34-word appendix, the
identical 127-word geometry and the same `V14M` mailbox magic, **a V15 frame is
shaped identically to a V14 frame** — there is no in-frame discriminator at all.

This does not weaken the deployment binding, which is what actually ties frames
to an image; it removes a claim that was resting on nothing.

## Which side is wrong is not decided here

The static assert requires 14 and names V15, and the wire format genuinely *is*
V14's — same appendix, same geometry — so "schema 14" may describe the wire
correctly while "15" is the qualification generation. Under that reading the
host contract is the error. But `SCHEMA_VERSION = 15` was frozen at Task 1 and
Amendment 2 reasoned from it, so this is a frozen-contract decision and was
referred rather than taken.

## State

```
V15_DEPLOYED              YES
SOURCE_DESTINATION_HASHES MATCH
VERIFIED_CELL_CONTEXT     PRODUCTION_ISSUED
QUALIFICATION_RUNS        1
CAMPAIGN_SAMPLES          0
V15_3x10_CAMPAIGN         NOT_STARTED
TASK11                    LIVE_PATH_BLOCKED_AT_PARSER_SCHEMA_MISMATCH
```

Task 11 is **not** `REQUALIFIED` and not `LIVE_PATH_VERIFIED`. The chain reaches
the verified deployment context and stops at the parser.

No cycle or poll value from this frame has been read or interpreted.

Board left closed: USB_OFF, `/dev/sdb*` absent, four UART ports free.
