# PMU_COMPLETION_VISIBILITY_DIAG_V14 design

Date: 2026-08-15

## Objective

`PMU_COMPLETION_VISIBILITY_DIAG_V14` asks two narrow diagnostic questions:

1. Does the separate-register completion cursor `QREAD == QSIZE` retain a
   floor/excursion observation structure when it is polled without STATUS?
2. In a dual-read loop, does the first CPU-visible ordering between
   `QREAD == QSIZE` and `STATUS.cmd_end_reached` persist when the MMIO read
   order is reversed?

V13 is frozen and established, for its fixed image and workload, that all
variable `P0 -> P1` cycles were explained by the number of STATUS polls:

```text
poll_cycles = 66 + 26 * poll_iterations
```

V13 did not separate later NPU command completion from later visibility of a
STATUS field. V14 compares the strongest available separate-register cursor
with `STATUS.cmd_end_reached`; it still cannot recover an internal hardware
completion timestamp.

V14 is diagnostic only. It is not latency, `T_npu`, an NPU performance
measurement, Production END_ONLY, or MLEK evidence. V13 and all earlier
variants remain frozen.

## Frozen provenance

V14 branches from the completion-observable audit, which in turn is based on
the V13 post-board evidence anchor:

```text
V13 board result  d49fa5fe5b3ae87ca0cf2c2bd829887bd4b408aa
V13 result tag    pmu-completion-poll-count-v13-board-evidence
observable audit 3a32b17c85a9b11444306d9336b5beb9cd23cad8
audit tag         pmu-completion-observable-audit
V14 design branch pmu-completion-visibility-v14-design
```

The fixed V13 board result, firmware, generated images, host evidence, and
tags must remain byte-untouched. V14 is a new diagnostic variant. The
wire schema is `14`; the common build ID is `0x34314950` (`PI14` in
little-endian byte order), with a required explicit variant identifier in the
payload and manifest.

## Register facts that constrain the design

The design uses the Arm Ethos-U85 TRM Issue 05 and the audited U85 core-driver
interface.

```text
STATUS.state             bit 0, 0 = stopped, 1 = running
STATUS.irq_raised        bit 1, mask 0x002
STATUS.bus_status        bit 2, mask 0x004
STATUS.reset_status      bit 3, mask 0x008
STATUS.cmd_parse_error   bit 4, mask 0x010
STATUS.cmd_end_reached   bit 5, mask 0x020
STATUS.pmu_irq_raised    bit 6, mask 0x040
STATUS.ecc_fault         bit 8, mask 0x100
STATUS.branch_fault      bit 9, mask 0x200
STATUS.irq_history_mask  bits 31:16
```

The vendor fault predicate is frozen as:

```text
fault_mask = bus_status | cmd_parse_error | ecc_fault | branch_fault
           = 0x314
```

`reset_status` is not folded into that fault mask; it is a separate invalid
state and must be zero at pre-run validation and convergence.

`QREAD` is read-only and may be read while the NPU is stopped or running.
Commands before `QBASE + QREAD` are complete, and `QREAD == QSIZE` means all
commands in the stream are complete. This is an architected command-stream
completion cursor, not an internal completion timestamp.

`QSIZE` may be accessed only while the NPU is stopped. An access while running
is UNPREDICTABLE. V14 therefore reads `QSIZE` exactly once after final queue
programming and before submit, and performs zero QSIZE reads on every running
path.

`STATUS.cmd_end_reached` is set when `QREAD == QSIZE`, commands are complete,
and the NPU enters stopped state. It is cleared by writing `QBASE` or `QSIZE`
while stopped. `CMD.clear_irq` (`CMD=2` in the frozen path) clears
`irq_raised`; it does not establish that `cmd_end_reached` was cleared.

## Alternatives considered

### 1. QREAD-only plus one fixed-order dual loop

This minimizes the number of variants but cannot distinguish a real visibility
ordering from the fact that one register was always read first. Rejected as
insufficient.

### 2. Fresh STATUS-bit5 control plus QREAD-only

This measures each register separately but cannot observe a transition tuple
within one run. It also does not address dual-read ordering directly. Deferred
as the conditional `S5` control rather than selected for the first campaign.

### 3. Q / QS / SQ matrix with common post-observation convergence — selected

Use one QREAD-only variant and two dual variants whose only intended primary
loop difference is MMIO read order. This provides a low-MMIO QREAD
characterization and a direct read-order-bias test. After the first tuple is
frozen, all variants enter one common bounded convergence and cleanup path so
cleanup cannot become a variant-specific confound.

## Variant matrix

All three variants retain the V12/V13 stock runtime vector and IRQ hard-bypass:
the exact stock `u85_irq_handler` is installed, `NPU0_IRQn` remains disabled
through the measured run, and `irq_triggered` remains false. The raw peripheral
IRQ latch may still become set and is observed through STATUS.

```text
variant Q   id=1   primary reads QREAD only
variant QS  id=2   primary reads QREAD, then STATUS
variant SQ  id=3   primary reads STATUS, then QREAD
```

The historical V13 evidence is a STATUS `irq_raised` bit1 reference. It is not
a STATUS `cmd_end_reached` bit5 control and must not be described as one.

### Q primary loop

```text
P0 = primary-loop entry timestamp

repeat at most 10000 iterations:
    qread = QREAD
    if qread == qsize_expected:
        P1 = first QREAD-complete observation timestamp
        freeze first_qread and primary iteration state
        exit primary loop
```

Q performs no STATUS read in its primary loop. Its first STATUS read occurs in
the common convergence tail after P1, outside authoritative primary timing.

### QS primary loop

Every iteration executes both reads before any completion decision:

```text
qread  = QREAD
status = STATUS
q_done = qread == qsize_expected
s_done = (status & 0x20) != 0

if (status & 0x008) != 0:
    freeze this qread/status as failure evidence
    fail RESET_IN_PROGRESS

if (status & 0x314) != 0:
    freeze this qread/status as failure evidence
    fail HARDWARE_FAULT

if q_done || s_done:
    P1 = first-observation timestamp
    freeze qread and that same status value
    exit primary loop
```

The same STATUS value supplies `cmd_end_reached`, `irq_raised`, `state`, fault
bits, and history. No success reread is permitted.

### SQ primary loop

SQ is identical in intent and branch topology to QS except for the MMIO read
order:

```text
status = STATUS
qread  = QREAD
```

Both reads still execute before `q_done || s_done` is evaluated. Source-level
appearance is not sufficient; final-ELF qualification must prove the read
order and the absence of a short-circuit exit between the two reads. The same
reset/fault checks and priority used by QS apply to SQ; an offending tuple must
exit immediately rather than being mislabeled as primary timeout.

Q deliberately has no STATUS visibility inside its primary loop. If its 10000
QREAD observations time out, it freezes the final QREAD and performs exactly
one STATUS diagnostic read after authoritative timing has ended. That tuple
classifies reset/fault if present; otherwise it remains `PRIMARY_TIMEOUT`.
The diagnostic read cannot create a valid first-observation tuple and cannot
enter convergence or normal cleanup.

### First-observation categories

QS and SQ classify the frozen same-iteration tuple as:

```text
Q_FIRST         q_done=1, s_done=0
S5_FIRST        q_done=0, s_done=1
SAME_ITERATION  q_done=1, s_done=1
```

`SAME_ITERATION` means only that both values were observed in the same software
loop iteration. It does not mean the hardware transitions occurred in the
same cycle.

## Pre-run stale-state gate

Every run must validate a clean stopped-state baseline outside authoritative
timing:

```text
NPU is in known powered/held and stopped state
-> pre_program_status = STATUS exactly once
-> require:
     state=stopped, reset_status=0, fault_mask=0
-> no state-transitioning CMD write
-> normal vendor QBASE/QSIZE programming completes
-> qsize_expected = QSIZE exactly once
-> baseline_status = STATUS exactly once
-> require all:
     (baseline_status & 0x001) == 0       state=stopped
     (baseline_status & 0x002) == 0       irq_raised=0
     (baseline_status & 0x020) == 0       cmd_end_reached=0
     (baseline_status & 0x008) == 0       reset_status=0
     (baseline_status & 0x314) == 0       no vendor fault
```

The pre-program check must dominate every QBASE/QSIZE access, and no command
may transition the NPU to running between that check and those writes. The
post-program check does not substitute for this proof.

`qsize_expected` must be captured after the final QSIZE programming write and
immediately before submit-side setup. It must equal the fixed workload and
manifest value `0x00000110`. A stale bit, reset-in-progress, fault, wrong state,
wrong queue size, or any second/running QSIZE read fails closed before
submission. It is never repaired silently inside the measured run.

This gate is required because `CMD=2` clears `irq_raised` but does not by itself
clear `cmd_end_reached`. Without the post-programming baseline read, a prior
run's bit5 could corrupt the QS/SQ first-observation result.

## Authoritative observation boundary

The primary observation ends when P1 and the values from the triggering
iteration are frozen:

```text
T2  NPU command submit completed
P0  primary loop entry
P1  first qualifying observation after all scheduled iteration reads
```

The primary diagnostic intervals are:

```text
submit_to_first_observation_cycles = u32(P1 - T2)
primary_observation_cycles         = u32(P1 - P0)
```

Q/QS/SQ absolute cycle values are not subtracted or compared as latency. The
variant loops deliberately have different MMIO loads and read order. The Q
distribution may be compared with V13 only for qualitative structure such as
the recurrence of a floor/excursion pattern, not for absolute values.

## Common bounded convergence tail

P1 does not immediately authorize `CMD=2`. A QREAD-first observation can occur
before `irq_raised` is CPU-visible, and clearing at that point could perturb
the state still being studied.

After the first tuple is frozen, Q, QS, and SQ join one shared helper/path. Its
read order is fixed for every variant:

```text
for at most 10000 iterations:
    qread  = QREAD
    status = STATUS

    if (status & 0x008) != 0:
        fail RESET_IN_PROGRESS

    if (status & 0x314) != 0:
        fail HARDWARE_FAULT

    if qread == qsize_expected
       && (status & 0x020) != 0       cmd_end_reached
       && (status & 0x002) != 0       irq_raised
       && (status & 0x001) == 0:      stopped
        freeze this same qread/status tuple
        succeed

fail CONVERGENCE_TIMEOUT
```

Convergence is based on one same-iteration tuple. It must not OR together a
QREAD completion observed in one iteration and STATUS bits observed later.
All predicate fields are derived from the one STATUS load in that iteration;
no additional STATUS read is permitted.

The bound of 10000 is a deterministic failure escape, not a vendor-equivalent
wall-clock timeout and not performance evidence. The counter remains
register-local in the tail and is stored once after exit. There is no
per-iteration SRAM store, timestamp, log, call, QSIZE read, or extra MMIO.

The convergence tuple is cleanup-safety evidence. It is not a second
completion timestamp, and `irq_raised` must not be interpreted as the instant
of final command completion.

## Common success cleanup

Only a successful convergence predicate reaches normal stock-equivalent
cleanup. All three variants share one CFG and ordering:

```text
convergence_final_status -> irq_history_mask semantics
-> CMD=2 #1                         ISR-equivalent acknowledgement
-> QREAD
-> CMD=2 #2                         frozen caller acknowledgement
-> QREAD verification
-> NVIC pending cleanup/verification
-> CMD=0
-> H-PRINTF pre-release seam / PMU snapshot and disable
-> vendor terminal CMD=0xC
```

The exact two-CMD sequence follows the frozen successful V12/V13 path. The
history value must come from `convergence_final_status`, which is the same raw
STATUS value that satisfied convergence; no cleanup STATUS reread substitutes
for it.

Q/QS/SQ must use the same convergence-helper source/object, bound, MMIO
sequence, normalized final-ELF CFG, and cleanup CFG. The final ELF must prove
that no variant-specific path exists between primary tuple freeze and terminal
release except the data values carried into the common path.

After successful cleanup and all final readbacks, the vendor publishes the
same mailbox-valid magic as its last appendix store before returning. Thus
success and failure use one mailbox structure and one runner copy path; only
their reachable peripheral cleanup paths and field-validity rules differ.

## Failure state machine

The following are separate failure classes:

- `PRE_RUN_STALE_OR_INVALID`
- `PRIMARY_TIMEOUT`
- `RESET_IN_PROGRESS`
- `HARDWARE_FAULT`
- `CONVERGENCE_TIMEOUT`

On any of them:

```text
sample_valid = false
primary timing is not promoted to the distribution dataset
failure tuple and reason are preserved
normal success CMD=2/QREAD/CMD=0/CMD=0xC cleanup is not entered
same-boot subsequent runs are prohibited
fresh full boot is required
```

Failure evidence egress is mandatory and has a separate interface from normal
success cleanup:

```text
runner, before calling the private V14 vendor diagnostic
-> call the named mailbox-reset entry outside authoritative timing
-> set all appendix fields to their invalid values
-> set mailbox_valid = 0 and DSB

private V14 vendor diagnostic
-> write result/phase/reason/qread/status to the fixed volatile SRAM mailbox
-> publish mailbox_valid = 0x5631344D last and DSB
-> return explicit V14 failure code without any NPU CMD/QBASE/QSIZE write

runner
-> require mailbox_valid == 0x5631344D
-> copy the complete 34-word mailbox before any local cleanup
-> preserve raw appendix fields exactly as allowed by the phase-validity matrix
-> invalidate every derived/promotable measurement verdict and every retained
   PMU/performance output
-> optionally disable only the CPU-side PMU to stop further counting
-> serialize one COMPLETE/GET raw result carrying the exact failure evidence

host
-> write the raw/reread/hash/manifest failure bundle to a quarantine directory
-> do not add it to the formal sample dataset
-> stop the campaign and require a fresh full boot
```

The mailbox layout is exactly the same 34-word V14 appendix defined below;
`mailbox_valid` is its final serialized word, not a hidden side channel.
The vendor owns the mailbox storage and all post-reset field writes. The runner
owns the pre-call reset invocation, post-return read/copy, and transport
serialization; it never writes a valid value. The manifest binds the mailbox
symbol, size, `mailbox_valid` address, reset entry, and exact valid magic.
Final-ELF and runner-record/wire dataflow gates must prove that the valid store
is last, the runner copy is dominated by the magic check, and the response is
serialized before reboot. Failure egress must not execute
`CMD=2`, `CMD=0`, `CMD=0xC`, QBASE, or QSIZE and must not invoke the H-PRINTF
hook. The optional runner-local PMU disable is non-authoritative, is recorded
as such, and does not make the sample valid. Board recovery/reboot is an
operational action outside the measured path.

A `CLEANUP_INVARIANT` is distinct: it can be detected only after successful
convergence has already authorized part of the stock CMD/QREAD cleanup, so it
cannot satisfy the no-clear evidence-preservation contract above. It still
makes the sample invalid, records `failure_phase=CLEANUP` and the exact cleanup
readbacks, aborts the campaign, and requires a fresh boot. It must never be
reported as a convergence or primary-observation failure.

## Exact wire and host evidence

Schema 14 retains the 85-word schema-v8 qualification body as its frozen
prefix and appends exactly 34 little-endian `uint32_t` words in this order:

| Appendix word | Field |
|---:|---|
| 0 | `variant_id` |
| 1 | `qsize_expected` |
| 2 | `pre_program_status` |
| 3 | `pre_submit_status` |
| 4 | `t_submit_after_cmd` |
| 5 | `t_primary_entry` |
| 6 | `t_first_observation` |
| 7 | `primary_result` |
| 8 | `primary_iterations` |
| 9 | `first_qread` |
| 10 | `first_status` |
| 11 | `first_q_done` |
| 12 | `first_cmd_end_reached` |
| 13 | `first_irq_raised` |
| 14 | `first_state` |
| 15 | `convergence_result` |
| 16 | `convergence_iterations` |
| 17 | `convergence_final_qread` |
| 18 | `convergence_final_status` |
| 19 | `convergence_timeout` |
| 20 | `failure_phase` |
| 21 | `failure_reason` |
| 22 | `failure_qread` |
| 23 | `failure_status` |
| 24 | `installed_vector` |
| 25 | `nvic_enabled_before_submit` |
| 26 | `nvic_pending_after_initial_clear` |
| 27 | `nvic_active_before_submit` |
| 28 | `irq_triggered_before_submit` |
| 29 | `nvic_pending_before_final_clear` |
| 30 | `nvic_pending_after_final_clear` |
| 31 | `nvic_active_after_cleanup` |
| 32 | `irq_triggered_after_cleanup` |
| 33 | `mailbox_valid` |

The exact frame is therefore:

```text
header words  8
body words    85 + 34 = 119
total words   127
payload bytes 508
```

Constants and enums are:

```text
V14_U32_INVALID = 0xFFFFFFFF
V14_MAILBOX_VALID = 0x5631344D

variant_id:
  1=Q, 2=QS, 3=SQ

primary_result:
  0=NOT_RUN, 1=OBSERVED, 2=TIMEOUT, 3=RESET, 4=FAULT

convergence_result:
  0=NOT_RUN, 1=SUCCESS, 2=TIMEOUT, 3=RESET, 4=FAULT

failure_phase:
  0=NONE, 1=PRE_PROGRAM, 2=PRE_SUBMIT,
  3=PRIMARY, 4=CONVERGENCE, 5=CLEANUP

failure_reason:
  0=NONE
  1=STATE_RUNNING
  2=RESET_IN_PROGRESS
  3=HARDWARE_FAULT
  4=STALE_IRQ
  5=STALE_CMD_END
  6=QSIZE_MISMATCH
  7=PRIMARY_TIMEOUT
  8=CONVERGENCE_TIMEOUT
  9=CLEANUP_INVARIANT
```

Valid success iterations are `1..10000`. `primary_iterations` and
`convergence_iterations` are zero on timeout, reset, fault, or not-run; zero is
never a successful count. `convergence_timeout` is exactly one only when
`convergence_result=TIMEOUT`, otherwise zero.

For Q, `first_status` and all STATUS-derived first fields are
`V14_U32_INVALID`; they are never synthesized from the later convergence tail.
On convergence success, `convergence_final_qread/status` hold the one predicate
tuple and `failure_qread/status` are invalid. On reset, fault, or timeout, the
convergence-final fields are invalid while `failure_qread/status` hold the
offending or final observed tuple. A pre-run failure uses its exact STATUS and
an invalid QREAD. A Q primary timeout uses the last primary QREAD plus its one
post-timeout diagnostic STATUS read. Success and failure publication must be
path-sensitive and stale-value safe.

The host applies this exact phase-validity matrix:

| Outcome | T2/P0/P1 | first tuple | convergence tuple | failure tuple | retained PMU/golden/release |
|---|---|---|---|---|---|
| success | valid | Q: Q-only; QS/SQ: full | valid | invalid | validity-gated, diagnostic only |
| pre-program failure | invalid | invalid | invalid | STATUS only | invalid |
| pre-submit failure | invalid | invalid | invalid | STATUS only | invalid |
| primary timeout | T2/P0 valid, P1 invalid | invalid | invalid | final QREAD/STATUS | invalid |
| primary reset/fault | T2/P0 valid, P1 invalid | invalid | invalid | offending tuple | invalid |
| convergence timeout/reset/fault | valid | valid | invalid | final/offending tuple | invalid |
| cleanup invariant | valid | valid | valid | cleanup readbacks | partially observed, sample invalid |

Every serialized result requires `mailbox_valid=V14_MAILBOX_VALID`. A missing,
early, stale, or wrong magic is a transport-contract failure, never a sample.

The retained PMU/golden/release fields remain available for validity and
functional non-interference checks, but V14 must classify:

```text
perturbed_by_convergence_tail = true
not_comparable_to_v13         = true
not_performance_metric        = true
```

`npu_pmu_window_cycles` includes the added convergence MMIO work and must not
be used to compare Q/QS/SQ or any earlier variant.

## Final-ELF qualification gates

Source inspection is supporting evidence only. Each real ARM image must prove:

### Pre-run and QSIZE safety

- one pre-program STATUS load dominates QBASE/QSIZE programming and proves
  stopped, reset clear, and fault clear;
- no running transition can occur between that gate and final programming;
- one exact QSIZE load supplies `qsize_expected` after final programming and
  before submit;
- that value equals the manifest-bound fixed value `0x00000110`;
- reachable QSIZE loads while running are zero;
- a distinct post-program STATUS load supplies stopped, stale-bit, reset, and
  fault gates;
- failure cannot fall through to submit.

### Primary loops

- Q has exactly one QREAD load and zero STATUS loads per iteration;
- QS has one QREAD then one STATUS load per iteration;
- SQ has one STATUS then one QREAD load per iteration;
- QS/SQ perform both loads before the predicate and have equivalent normalized
  branch/loop semantics except for the MMIO read order;
- completion masks are exactly QREAD equality and STATUS `0x20`;
- bit1 is auxiliary provenance, not the primary STATUS exit predicate;
- QS/SQ reset/fault checks dominate the ordinary completion predicate and
  freeze the offending same-iteration tuple;
- Q timeout performs exactly one post-primary STATUS diagnostic read and that
  path cannot become a valid first observation;
- the first frozen values are the exact loads that drove the exit;
- no success reread, QSIZE load, per-iteration store, timestamp, log, or call
  exists in a primary loop;
- timeout cannot publish a valid first tuple.

### Common convergence and cleanup

- all variants reach the exact same convergence helper;
- its loop order is QREAD then STATUS;
- it derives stopped, bit1, bit5, reset, and mask `0x314` from the same STATUS
  load;
- its success predicate uses one same-iteration QREAD/STATUS tuple;
- its bound and normalized CFG are identical across Q/QS/SQ;
- its evidence stores occur only after loop exit;
- reset/fault/timeout edges cannot reach normal cleanup;
- failure mailbox publication/DSB/return dominates runner copy and raw
  serialization without any failure-path NPU state-clearing write;
- mailbox reset sets valid to zero before the call, vendor magic publication is
  the final appendix write, and runner copy is reachable only after the exact
  magic check;
- only convergence success reaches the frozen history/CMD2/QREAD/CMD2/NVIC/
  CMD0/H-PRINTF/CMD0xC sequence;
- success retains the V12/V13 stock vector and NVIC hard-bypass contract.

If compiler lowering introduces extra per-iteration loads/stores, a hidden
QSIZE access, short-circuit dual reads, tail merging across failure/success, or
variant-specific convergence cleanup, qualification fails. The checker is not
relaxed; the implementation is redesigned.

## Fail-closed negative tests

The firmware/final-ELF checker must deliberately reject at least:

1. QSIZE read after submit or in either loop;
2. qsize snapshot before final QSIZE programming;
3. missing stopped/stale-bit/reset/fault pre-run gate;
4. stale pre-run failure falling through to submit;
5. Q primary STATUS read;
6. QS/SQ missing the second read after the first observable becomes true;
7. QS and SQ compiled to the same read order;
8. STATUS mask changed from bit5 `0x20` to bit1 `0x02` as primary completion;
9. success tuple populated by a reread rather than the branch-driving loads;
10. convergence accumulated across different iterations;
11. convergence omitting Q equality, bit5, bit1, stopped, or reset/fault gate;
12. fault/reset waiting until the convergence timeout;
13. different convergence helper, read order, bound, or cleanup for a variant;
14. convergence evidence store inside the loop;
15. convergence timeout entering normal CMD=2 cleanup;
16. fault/reset failure entering normal CMD=2 cleanup;
17. history derived from a post-convergence STATUS reread;
18. success CMD=2/QREAD/CMD=2 ordering drift;
19. Q first-status fields synthesized from convergence values;
20. V13 or another frozen artifact modified.
21. pre-program stopped check moved after QBASE/QSIZE access;
22. qsize snapshot differs from manifest value `0x110`;
23. QS/SQ observable fault classified only after primary timeout;
24. Q timeout missing or duplicating its single diagnostic STATUS read;
25. failure mailbox-valid stored before a tuple field;
26. failure path clearing NPU state before raw serialization;
27. convergence success tuple and failure tuple both published as valid.
28. mailbox-valid omitted, published early, or not reset before a run;
29. stale mailbox-valid accepted from an earlier run;
30. runner appendix copy executed before the final valid publication.
31. convergence failure raw T2/P0/P1 or first tuple discarded, or those raw
    fields used to emit distribution metrics/a valid-sample verdict.

Positive fixtures cover Q/STATUS-first/same-iteration outcomes, success on the
first and last allowed iteration, pre-run stale bit5, each fault bit,
reset-in-progress, primary timeout, convergence timeout, and the boundary where
Q completes before the IRQ latch becomes visible.

## First campaign and interpretation

After unit, two-build determinism, real-ELF, host, regression, independent
review, and pre-board qualification, run the three fixed images in balanced
boot order:

```text
round 1  Q  -> QS -> SQ
round 2  QS -> SQ -> Q
round 3  SQ -> Q  -> QS

each image position = one independent full boot x 10 consecutive valid runs
total                = 90 valid samples
```

Any invalid sample stops all acquisition immediately. It is quarantined and
excluded; collection does not silently replace it with another run or boot.
After review and board restore, only the complete affected cell (one fresh boot
and runs 1..10) restarts with a new `cell_attempt` identifier. Valid samples
from the failed cell attempt are discarded; already completed cells remain
eligible because their fixed image and contract did not change. Acquisition of
later cells resumes only after the retried cell completes. If source, image,
host classifier, manifest, or contract changes during disposition, the entire
90-sample campaign restarts and no earlier cell is reused. The final formal
dataset therefore contains exactly nine uninterrupted valid cells of ten runs
each and preserves variant, round, boot, `cell_attempt`, and within-boot run
index.

Primary interpretation is categorical:

| QS result | SQ result | First interpretation |
|---|---|---|
| Q first | S5 first | read-order/sampling bias dominates |
| Q first | Q first | QREAD-earlier candidate; fresh S5 control required |
| same iteration | same iteration | no gap resolved at software observation resolution |
| S5 first | S5 first | STATUS-earlier candidate; fresh S5 control is valuable |
| mixed/unstable | mixed/unstable | unresolved; audit raw transitions before any V15 |

Q-only retains a floor/excursion structure only if that structure is reproduced
across independent boots. This would show that polling the STATUS register
itself is not required for the variability, but it still would not separate
internal completion from QREAD visibility.

The conditional `S5` control is a fresh V14-family image that polls only
`STATUS.cmd_end_reached` bit5. It is not in the first campaign. It becomes
required before a visibility-order claim when both dual variants consistently
favor the same register, or when Q-only and dual distributions differ enough
that dual-read perturbation must be assessed. Historical V13 bit1 data is not a
substitute.

## Qualification phases

1. Freeze this design and a separate implementation plan.
2. TDD source/fixture contracts for QSIZE safety, primary read order, common
   convergence, failure isolation, and stock cleanup.
3. Generate Q/QS/SQ only from frozen raw runner/vendor inputs.
4. Perform two isolated clean ARM builds for each variant and compare all
   declared artifacts.
5. Qualify each final ELF and cross-variant primary/tail equivalence contracts.
6. Qualify the schema, parser, collector, analyzer, invalidation, and raw
   reread/manifest bindings.
7. Run all V8-V13/CFG/DIAG regressions and independent correctness/security
   review.
8. Create a pre-board anchor only after all prior gates pass.
9. Run the balanced 90-sample campaign under the existing deploy/restore
   procedure.

Until phase 8, V14 is not pre-board qualified. Until phase 9, it has no board
evidence. Production END_ONLY remains frozen and MLEK remains blocked
throughout.

## State after design approval

```text
V13                                FROZEN / EVIDENCE COMPLETE
P0->P1 variability                 EXPLAINED BY POLL ITERATION COUNT
QREAD==QSIZE                       STRONG SEPARATE-REGISTER CURSOR
Internal completion instant        NOT OBSERVABLE
V14 Q/QS/SQ design                 APPROVED / DOCUMENTED
V14 implementation                 NOT STARTED
Production END_ONLY                FROZEN
MLEK                                BLOCKED
```

## Sources

- Arm Ethos-U85 NPU Technical Reference Manual, document
  `102685_0000_05_en`, Issue 05:
  <https://documentation-service.arm.com/static/67b5ba01ce2747241fce860f>
  (audited PDF SHA-256
  `3fc6287d861b482e12f29ecd02103128fece6a78ffbe4656332ebb08aaffb8ca`)
- Arm Ethos-U core-driver commit
  `03567073fe2b9802c0bd73f9534da6f8a03924d1`
  (`src/ethosu85_interface.h` SHA-256
  `8a5cbe762158db15651d65b278d71495e27b174ecacc1c7f988413f5dd665f41`)
- `firmware/Selftest_pmu_diag/PMU_COMPLETION_OBSERVABLE_AUDIT.md`
- `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_BOARD_RESULT.md`
