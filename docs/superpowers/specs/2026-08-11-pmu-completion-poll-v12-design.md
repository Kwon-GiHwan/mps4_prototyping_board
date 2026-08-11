# PMU_COMPLETION_POLL_DIAG_V12 design

Date: 2026-08-11

## Objective

`PMU_COMPLETION_POLL_DIAG_V12` asks one causal-localization question:

> When NPU completion is observed by direct CPU polling while NPU0 IRQ
> delivery is hard-bypassed at the NVIC, does the previously observed
> hard-floor/excursion distribution remain?

V11-A localized the variable interval to `T2 submit -> J0
first-veneer-probe`. V12 changes the completion-observation mechanism rather
than subdividing the ISR further. It removes NPU0 IRQ delivery, NVIC exception
servicing, and ISR execution from the observation path, then polls the stock
NPU STATUS completion bit directly.

V12 is diagnostic only. It is not numerically comparable to V11-A, an NPU
latency measurement, `T_npu`, a performance baseline, Production END_ONLY, or
MLEK evidence. Repeated STATUS MMIO traffic is an intentional intervention.
Only distribution structure may be compared between V11-A and V12; their
absolute cycle values must never be subtracted to infer IRQ latency.

## Frozen provenance and identity

V12 branches from the V11-A post-board evidence anchor:

```text
commit  f1948bcda5232c89f3468585a4099bc2f94ae300
tag     pmu-interval-v11a-board-evidence
```

The V12 generator consumes the same frozen raw inputs as V11-A rather than a
V11-generated output:

```text
runner SHA-256  69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b
vendor SHA-256  bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf
```

V12 uses schema version `12` and proposed build ID `0x32314950` (`PI12` in
little-endian byte order). It produces separate generated source, build,
manifest, artifact, parser, and evidence paths. V8, V9, V10, V11-A, CFG,
DIAG, and Production artifacts remain frozen and byte-untouched.

## Stock behavior established by audit

The frozen vendor source has a `void wait_for_irq()` with no error return. On
success the stock path performs two `CMD=2` writes:

```text
stock ISR:
  STATUS read
  irq_history_mask = STATUS >> 16
  irq_triggered = true
  CMD=2                         # first, ISR acknowledgement

wait_for_irq() return
  QREAD read
  CMD=2                         # second, stock caller write
  QREAD verify
  CMD=0
  TEST_CPM=1 terminal CMD=0xC
```

On timeout, the ISR has not run. `wait_for_irq()` sets the sticky
`irq_never_triggered` flag, performs an additional STATUS read for its failure
message, clears `irq_triggered` to false, and returns normally. The caller then
continues rather than resetting or aborting:

```text
stock timeout:
  irq_never_triggered = true
  extra STATUS read and failure report
  return
  QREAD read
  CMD=2                         # stock caller write only
  QREAD verify
  CMD=0
  TEST_CPM=1 terminal CMD=0xC
```

After `test_commands()` returns, `test_u85()` verifies the output, checks
`irq_history_mask` against the expected mask, and increments its return code
if `irq_never_triggered` is true. V12 must therefore reproduce the successful
ISR's history-mask side effect from the exact successful polling load while
deliberately not reproducing the transient `irq_triggered=true` side effect.

## Selected architecture

Use a generated C polling helper and replace only the stock
`wait_for_irq()` callsite in the V12 generated vendor copy. Do not edit the
stock `wait_for_irq()` body, do not use an assembly poll loop, and do not
inherit the V11-A entry veneer.

The runtime vector is explicitly installed to the exact stock handler:

```c
NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
```

The NPU0 interrupt stays disabled for the complete measured run. Source and
final-ELF gates jointly prove that neither `NVIC_EnableIRQ()` nor an inlined
write to the NPU0 bit in NVIC ISER occurs on the active measured path.

The start precondition is performed idempotently on every run:

```text
irq_triggered = false
NVIC_DisableIRQ(NPU0_IRQn)
NVIC_ClearPendingIRQ(NPU0_IRQn)
verify enabled == 0
verify pending == 0
verify active  == 0
verify irq_triggered == false
```

If pending immediately returns after the initial clear, or any other start
precondition fails, the run is rejected before submit.

## Timestamp and interval contract

The boundaries are:

```text
T2  immediately after the NPU CMD submit write
P0  helper entry, before the first STATUS poll read
P1  immediately after the exact STATUS load that first satisfies bit 0x02
P2  success path after leaving the poll loop and immediately before helper return
```

The success order is strictly:

```text
successful STATUS load
  -> test completion bit 0x02
  -> P1
  -> success tail
  -> P2                 # last timestamp in helper
  -> helper return
  -> caller-side effects
```

P2 is not a post-return timestamp. The final ELF must prove
`P1 < P2 < helper return < first success CMD=2`.

All arithmetic is unsigned 32-bit modular arithmetic:

```text
v12_d0 = u32(P0 - T2)
v12_d1 = u32(P1 - P0)
v12_d2 = u32(P2 - P1)

submit_to_status_completion_observed_cycles = u32(P1 - T2)

u32(v12_d0 + v12_d1)
  == submit_to_status_completion_observed_cycles

u32(v12_d0 + v12_d1 + v12_d2)
  == u32(P2 - T2)
```

The only primary V12 diagnostic field is
`submit_to_status_completion_observed_cycles`. It includes NPU command
processing/completion, STATUS visibility, and polling cadence. It is not pure
NPU execution time or latency.

## Poll helper contract

The helper has one static STATUS-load loop site and a register-local bounded
iteration count:

```text
P0
repeat at most 10000 times:
  status = read exact NPU STATUS address
  if (status & 0x02) != 0:
    P1
    success tail
    P2
    return SUCCESS and the same status value
return TIMEOUT
```

The numeric poll limit `10000` is only a bounded failure escape. It does not
have the same wall-clock duration as the vendor `sleep()` busy loop because
V12 performs a STATUS MMIO read on every iteration.

Allowed helper effects:

- DWT CYCCNT reads for P0, P1, and P2;
- one SRAM timestamp store for each reached checkpoint;
- reads from the exact NPU STATUS address;
- the completion-bit test and control branches;
- a register-local loop counter and minimal timeout result bookkeeping;
- returning the successful STATUS value to the caller.

Forbidden helper effects:

- any NPU CMD write;
- PMU MMIO;
- NVIC read or write;
- printf or other nested helper call;
- DSB, ISB, or another added barrier;
- per-iteration SRAM counter, log, or timestamp;
- a successful-path STATUS reread;
- any MMIO in the loop body other than the one STATUS load site.

The exact STATUS load that drives the bit-0x02 success branch must also be the
sole producer of the returned `status_at_success` value. A reread after the
success branch is forbidden.

Exactly-once P0/P1/P2 behavior is established without extra hit counters:

- the final ELF has one helper callsite;
- P0, P1, and P2 each have one static store site;
- P0 precedes the loop;
- P1 and P2 are success-only;
- no edge after P1 or P2 returns to the polling loop;
- runtime timestamps are nonzero and satisfy the two modular identities.

## Success state machine

The V12 success path preserves both stock `CMD=2` writes and their ordering:

```text
T2
-> P0
-> STATUS polling
-> successful STATUS load and bit-0x02 test
-> P1
-> P2
-> helper return(status_at_success)

-> serialize/reuse status_at_success
-> irq_history_mask = status_at_success >> 16
-> CMD=2 #1                    # stock ISR acknowledgement equivalent
-> QREAD read
-> CMD=2 #2                    # unchanged stock caller write
-> QREAD verify

-> pending_before_final_clear record
-> NVIC_ClearPendingIRQ(NPU0_IRQn)
-> verify pending == 0
-> verify active == 0
-> verify irq_triggered == false

-> CMD=0
-> existing H-PRINTF pre-release seam
-> authoritative PMU snapshot and disable
-> vendor terminal CMD=0xC
```

The history-mask store uses the same successful STATUS value returned by the
helper. No additional STATUS read is permitted. `irq_triggered=true` is not
reproduced: it is an ISR-to-wait handoff side effect removed by the hard
bypass, and the stock caller-visible state is false after `wait_for_irq()`.

The final NVIC pending cleanup occurs only after both stock-equivalent CMD
writes and QREAD verification. This avoids inserting diagnostic NVIC behavior
inside the preserved peripheral sequence.

Success-path CMD semantics are path-sensitive and mandatory:

```text
CMD=2 #1  after P2, helper return, and history-mask store;
          before QREAD read
CMD=2 #2  after QREAD read;
          before QREAD verification
total     exactly two executions on the success path
```

There is no CMD write inside the helper and no third CMD=2 on the success
path.

## Timeout state machine

Timeout must not execute P1, P2, or the success CMD branch. It preserves the
audited stock timeout behavior and adds only the required final NVIC cleanup:

```text
P0
-> bounded polling exhausts limit
-> poll_result = TIMEOUT
-> P1/P2 remain invalid
-> helper timeout return

-> irq_never_triggered = true
-> stock-style extra STATUS read and failure report
-> QREAD read
-> CMD=2 exactly once          # stock caller write only
-> QREAD verify

-> pending_before_final_clear record
-> NVIC_ClearPendingIRQ(NPU0_IRQn)
-> verify pending == 0
-> verify active == 0
-> verify irq_triggered == false

-> CMD=0
-> existing H-PRINTF/PMU cleanup path may execute
-> vendor terminal CMD=0xC
```

The timeout-only STATUS read/report is separate from the success dataflow and
cannot populate `status_at_success`. If the H-PRINTF hook and PMU snapshot are
reached during cleanup, `poll_result != SUCCESS` keeps the sample invalid and
prevents any performance-like value from being emitted.

Timeout-path CMD semantics are:

```text
QREAD read -> one CMD=2 -> QREAD verification
total exactly one execution on the timeout path
```

After any timeout, the sample is invalid, excluded from every distribution,
and the host aborts the remaining consecutive runs in that boot. A fresh full
boot is required because `irq_never_triggered` is sticky.

## Wire schema and validity

V12 adds the following per-sample fields to the retained qualification record:

```text
t_submit_after_cmd
t_poll_entry
t_status_completion_seen
t_poll_exit
poll_result
status_at_success
installed_vector
nvic_enabled_before_submit
nvic_pending_after_initial_clear
nvic_active_before_submit
irq_triggered_before_submit
nvic_pending_before_final_clear
nvic_pending_after_final_clear
nvic_active_after_cleanup
irq_triggered_after_cleanup
```

`nvic_pending_before_final_clear` is diagnostic evidence and is not required
to equal either zero or one. Disabled interrupts may become pending without
being taken. The required final cleanup observation is pending zero, active
zero, and `irq_triggered` false.

A sample is valid only when all of the following hold:

- schema, build, frozen source, artifact, callsite, golden-window, and raw
  reread identity gates pass;
- the installed runtime vector is the exact stock `u85_irq_handler` Thumb
  entry, not the V11-A veneer;
- NVIC enabled, pending-after-initial-clear, and active are all zero before
  submit, and `irq_triggered` is false;
- source plus final ELF prove no NPU0 NVIC enable operation on the measured
  path;
- polling succeeds, the exact successful STATUS value has bit `0x02` set, and
  timeout is false;
- P0, P1, and P2 are nonzero, correctly ordered, and satisfy both modular
  consistency equations;
- success performs exactly two path-ordered CMD=2 writes;
- final pending and active are zero and `irq_triggered` remains false;
- all retained PMU PRE/POST, stable-read, no-overflow, golden output,
  H-PRINTF, vendor terminal-release, MMIO-count, and transport gates pass.

On timeout, P1/P2 and all derived diagnostic cycles are invalid/absent. The
host must not emit `submit_to_status_completion_observed_cycles`.

## Final-ELF attack gates

The final ELF, disassembly, symbols, relocations, and control-flow graph are
authoritative over source spelling.

### Polling dataflow

The gate proves:

1. exactly one helper callsite;
2. exactly one P0, P1, and P2 store site;
3. one static loop STATUS-load instruction resolved to exact
   `U85_BASE_ADDRESS + NPU_REG_STATUS` (`0x50004004` for the frozen source);
4. completion mask exactly `0x02` and an identified success edge;
5. the same STATUS load value drives both the bit test and returned
   `status_at_success` dataflow;
6. P1 and P2 are reachable only from success, in the order
   `STATUS load -> test -> P1 -> P2 -> return`;
7. no loop-back edge after P1 or P2;
8. no success-path STATUS reread.

### Path-specific CMD semantics

The success CFG must prove:

```text
P2
< helper return
< irq_history_mask store from status_at_success
< CMD=2 #1
< QREAD read
< CMD=2 #2
< QREAD verification
< final pending cleanup
< CMD=0
< H-PRINTF seam
< CMD=0xC
```

Exactly two resolved stores of value two to the exact NPU CMD register execute
on this path. The timeout CFG proves exactly one resolved CMD=2 store in
`QREAD read -> CMD=2 -> QREAD verification` order. The helper contains zero
CMD stores.

### IRQ hard-bypass and V11 isolation

The gate proves:

- runtime vector installation writes the exact stock handler Thumb entry to
  the active NPU0 vector slot;
- the V11-A veneer is not installed and is not reachable on the active path;
- J0, I0, and T3 V11 instrumentation is not active/reachable;
- no `NVIC_EnableIRQ()` call and no inlined/direct write sets the NPU0 bit in
  NVIC ISER on the measured path;
- expected DisableIRQ, initial ClearPending, and final ClearPending accesses
  resolve to the correct NPU0 bit/register and are recorded in the manifest;
- the stock handler body remains source/object-proven unchanged even though it
  is not executed during valid samples.

### Helper side effects

The helper gate rejects PMU/CMD/NVIC MMIO, printf, barriers, nested calls,
per-iteration memory stores, or any loop-body MMIO beyond the exact STATUS
load. Compiler inlining is permitted only if all semantic gates remain
provable on the inlined region; otherwise the build fails closed.

## Required negative tests

Deliberate mutations must prove that gates reject at least:

1. missing success CMD=2 #1;
2. missing success CMD=2 #2;
3. a third success CMD=2;
4. success CMD=2 #1 moved after QREAD;
5. success CMD=2 #2 moved before QREAD;
6. missing timeout CMD=2;
7. two timeout CMD=2 executions;
8. CMD=2 inserted inside the helper;
9. `NVIC_EnableIRQ()` inserted on the active path;
10. a direct/inlined NPU0 ISER write;
11. runtime vector changed to the V11-A veneer;
12. V11 J0/I0/T3 path made reachable;
13. a success-path STATUS reread;
14. `status_at_success` sourced from the reread rather than the branch-driving
    load;
15. a loop-back edge after P1;
16. timeout falling into the success P1/P2 path;
17. completion mask changed from `0x02`;
18. extra PMU, CMD, or NVIC MMIO in the helper;
19. per-iteration SRAM counter/log/timestamp;
20. broken modular interval identity;
21. cross-schema/parser acceptance or manifest/artifact drift.

All retained V11-A, V10, V9, V8, CFG, and DIAG tests must still pass.

## Build and board qualification boundaries

Pre-board qualification requires:

- generator unit and negative tests;
- analyzer/parser unit and negative tests;
- final-ELF semantic and CFG proof;
- frozen input/output manifest and exact callsite identity;
- two clean ARM builds with byte-identical generated sources, objects, ELF,
  APP, VECTORS, DDR, map, and manifest;
- no regression in frozen V11-A/V10/V9/V8/CFG/DIAG artifacts;
- Production END_ONLY unchanged.

Only after a separate pre-board anchor and explicit deployment approval may
V12 run on hardware. The first board campaign is three independent full boots
by ten consecutive runs. Every accepted run must pass the entire V12 validity
contract. A timeout aborts the rest of that boot and requires a fresh boot.

The board analysis compares only whether V12 retains a hard-floor/excursion or
multimodal distribution:

```text
V12 polling remains variable
  -> IRQ handler/NVIC exception servicing alone is insufficient to explain
     the variability; NPU completion, STATUS visibility, and polling cadence
     remain in scope.

V12 polling is stable while V11-A remains variable
  -> completion-to-IRQ assertion/delivery/exception-entry becomes the stronger
     candidate region.
```

Neither outcome qualifies a Production measurement or permits numerical
subtraction between V11-A and V12.

## Frozen exclusions

V12 must not:

- modify Production END_ONLY;
- collect or label MLEK performance data;
- emit `T_npu`, latency, or NPU execution cycles;
- change PMCCNTR_CFG as part of this experiment;
- add STATUS/CMD/PMU/NVIC logging inside the poll loop;
- re-enable NPU0 IRQ during a measured sample;
- alter V11-A evidence or artifacts;
- proceed to a board campaign before pre-board qualification and explicit
  approval.
