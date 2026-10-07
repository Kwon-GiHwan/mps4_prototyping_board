# Ethos-U85 / FI101 completion-observable audit

Date: 2026-08-15

## Decision

V13 is frozen. No V14 firmware was implemented during this audit.

The audited software/register surface contains one useful separate-register
completion observable candidate:

```text
QREAD == QSIZE
```

`QREAD` is a separate read-only command-stream cursor. The Ethos-U85 TRM states
that commands before `QBASE + QREAD` are complete and that `QREAD == QSIZE`
means all commands in the stream are complete. This makes QREAD the strongest
software-visible candidate for a V14 causal diagnostic.

It is not an internal completion timestamp. A CPU observation of QREAD still
contains register visibility, interconnect, MMIO-read, and poll-sampling delay.
Therefore a QREAD diagnostic can compare completion-cursor visibility with
STATUS/IRQ-latch visibility, but cannot by itself recover the exact internal
NPU completion instant.

## Important correction to the V12/V13 name

V12/V13 poll `STATUS & 0x02`. In the U85 register definition this is
`STATUS.irq_raised`, not `STATUS.cmd_end_reached`.

The same STATUS register also exposes:

```text
STATUS.cmd_end_reached == bit 5 == 0x20
```

The fixed V13 campaign observed `status_at_success == 0xFFFF0022` in all 30
samples. Thus the successful STATUS load had both `irq_raised` and
`cmd_end_reached` set. V13 did not record which field became visible first.
Polling bit 5 may be a useful same-register comparison, but it is not
STATUS-independent and cannot separate internal completion from STATUS-register
visibility.

## Candidate classification

| Candidate | Audit result | Qualification boundary |
|---|---|---|
| `STATUS.irq_raised` (`0x02`) | Existing V12/V13 authority | Terminal IRQ latch, not generic completion bit |
| `STATUS.cmd_end_reached` (`0x20`) | Distinct semantic field, same STATUS register | Command-end indication, but same MMIO visibility surface |
| `QREAD == QSIZE` | **Separate-register completion candidate** | Architecturally means the whole stream is complete; observation can lag internally |
| NPU IRQ / NVIC pending | Not an independent terminal-event source for this workload | Terminal `NPU_OP_STOP` sets IRQ status and raises the level-triggered host IRQ |
| `CURRENT_QREAD` | Reject as completion authority | Described as the position being issued rather than completed |
| `COND_STATUS` | Reject | Tensor result flag, not command completion |
| PMU event | No supported whole-command-end event found | Activity/stall and memory-transaction completion events are not command-end timestamps |
| DWT/ETM/FPGA trace | No configured independent completion source found | DWT is used only as a software-read cycle counter; the encrypted FI101 bitstream cannot be audited for hidden nets |

## Exact fixed-workload semantics

The fixed convolution command stream ends in `NPU_OP_STOP` with mask `0xFFFF`
and has `QSIZE == 0x110`. The U85 TRM defines the terminal stop as waiting for
all preceding commands, transitioning to stopped state, setting the IRQ latch,
updating IRQ history, and raising the host IRQ. The frozen runner then expects
QREAD to equal the command queue size.

The terminal condition has these architecturally related effects:

```text
terminal NPU_OP_STOP, after all preceding commands complete
    +-- QREAD == QSIZE
    +-- stopped / STATUS.cmd_end_reached
    +-- STATUS.irq_raised / level-triggered NPU IRQ
```

The architecture establishes the completion meaning of QREAD equality, but the
available documentation does not establish a CPU-observable cycle-by-cycle
ordering between QREAD visibility, `cmd_end_reached`, and `irq_raised`.

## PMU audit

The exported U85 PMU event enumeration has no whole-command `CMD_END`,
`COMMAND_COMPLETE`, or equivalent event. `NPU_ACTIVE` and `NPU_IDLE` describe
activity, while `*_TRANS_COMPLETED` values describe individual SRAM or external
memory transactions. Event counters count occurrences; they are not completion
timestamps. PMCCNTR start/stop event selection does not solve this because no
qualified selectable event denotes whole-command completion.

Reserved or undocumented PMU encodings were not treated as usable evidence.

## FI101 / external-observation audit

The tracked project contains no HDL, constraints, ILA/ChipScope, ETM/TPIU/SWO,
or debugger-session configuration that exports raw NPU completion or IRQ
assertion. The board configuration selects an opaque encrypted/compressed
`fi101_00.bit`; its internal routing is outside the auditable mirror.

V11-A J0 remains the earliest qualified software checkpoint, but it observes
the delivered exception veneer after NVIC/exception entry. It is not the raw
IRQ assertion or internal NPU completion instant.

## Recommended next gate

V14 is **designable but not approved or implemented**. Its narrow question
should be:

```text
Does separate-register QREAD==QSIZE observation reproduce the V13
floor/excursion structure seen while polling STATUS.irq_raised?
```

The design review must choose and qualify an observation scheme before coding.
A QREAD-only variant minimizes per-iteration MMIO but permits distribution-
structure comparison only. A dual QREAD/STATUS variant can observe relative
visibility in one run but adds read-order bias and doubles loop MMIO. Neither
variant may subtract absolute cycles from V13 or claim an internal completion
timestamp.

Until that design is approved:

```text
V13                              FROZEN / EVIDENCE COMPLETE
P0->P1 variability                EXPLAINED BY POLL ITERATION COUNT
Separate-register candidate       QREAD == QSIZE
Internal completion timestamp     NOT AVAILABLE IN CURRENT SOFTWARE EVIDENCE
V14                               DESIGN REVIEW ONLY / NOT IMPLEMENTED
Production END_ONLY               FROZEN
MLEK                              BLOCKED
```

## Sources and audit scope

- Arm Ethos-U85 NPU Technical Reference Manual, document
  `102685_0000_05_en`, Issue 05:
  <https://documentation-service.arm.com/static/67b5ba01ce2747241fce860f>
  (audited PDF SHA-256:
  `3fc6287d861b482e12f29ecd02103128fece6a78ffbe4656332ebb08aaffb8ca`)
- Arm Ethos-U core-driver commit
  `03567073fe2b9802c0bd73f9534da6f8a03924d1`:
  <https://gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver/-/tree/03567073fe2b9802c0bd73f9534da6f8a03924d1>
  (`src/ethosu85_interface.h` SHA-256:
  `8a5cbe762158db15651d65b278d71495e27b174ecacc1c7f988413f5dd665f41`)
- Frozen V13 result: `PMU_COMPLETION_POLL_COUNT_DIAG_V13_BOARD_RESULT.md`
- Frozen V13 ELF: SHA-256
  `d12fc98510b63f5fa19b4fd4998d49479de3fc210a66dc4321ad734a7267fe11`
- Board evidence:
  `/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_20260815T061146Z`

The register/driver/PMU audit used the exact core-driver commit above. The
platform absence search covers the tracked repository and supplied board
configuration/recovery collateral. It does not claim that the encrypted FPGA
image contains no undocumented internal signal; it only records that no usable
configuration or evidence for one is available here.
