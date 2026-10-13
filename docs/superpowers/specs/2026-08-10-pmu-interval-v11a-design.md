# PMU_INTERVAL_ENTRY_DIAG_V11A design

Date: 2026-08-10

## Objective

Split the frozen V10 `E0 = T2 -> I0` interval once, and only once, by adding a
first-veneer-probe timestamp `J0` on the active NPU0 interrupt path.

V11-A asks one question:

> Is the V10 variation already present before the first veneer probe, or is it
> introduced between that probe and the existing V10 I0 probe?

V11-A is diagnostic only. It is not Production code, a performance baseline,
an NPU latency measurement, or MLEK evidence. V9, V10, the Production END_ONLY
candidate, and their frozen artifacts remain unchanged.

## Terminology and interval contract

`J0` is the **first-veneer-probe**, not the IRQ assertion time, exception-entry
instant, vector target's first instruction, or pure NPU completion time. The
veneer must materialize the DWT address before it can load `DWT->CYCCNT`.

Derived unsigned 32-bit intervals are:

```text
A0 = delta32(T2, J0)
A1 = delta32(J0, I0)
A2 = delta32(I0, T3)
D23 = delta32(T2, T3)

(A0 + A1 + A2) mod 2^32 == D23
```

`A0` includes NPU command processing/completion, IRQ assertion, NVIC
recognition/delivery, architectural exception entry and hardware stacking,
vector fetch, veneer entry, and the instructions before the CYCCNT load. It is
not NPU execution cycles.

## Selected architecture

Use a standalone Thumb assembly source for an entry veneer. Do not use a naked
C function and do not modify the startup vector table as the qualification
mechanism.

The generated diagnostic vendor copy retains the original stock
`u85_irq_handler` body. Its runtime vector installation alone changes from:

```c
NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
```

to:

```c
NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer);
```

For Cortex-M Thumb execution, the value installed in the vector slot must be
the veneer Thumb entry value, `v11a_u85_irq_entry_veneer | 1`. Clearing bit 0
from that installed value must resolve to the exact even ELF symbol address.
The source expression above is accepted only if the compiled function pointer
and relocation produce that Thumb entry value.

The active runtime path must be:

```text
NPU0 IRQ
  -> NVIC vector
  -> v11a_u85_irq_entry_veneer
  -> J0 direct DWT CYCCNT load and SRAM store
  -> unconditional tail branch
  -> original stock u85_irq_handler
  -> existing V10 I0 probe
  -> stock STATUS read and completion test
  -> existing T3 probe
```

Startup-vector changes alone never qualify the image because `test_u85()`
reinstalls the runtime vector.

## Assembly veneer contract

The semantic instruction sequence is:

```asm
materialize 0xE0001004
load DWT CYCCNT             // J0 timestamp event
materialize exact J0 slot
store timestamp to J0 slot
unconditional tail transfer to exact stock u85_irq_handler
```

The assembler may encode address materialization with literal loads or
`movw`/`movt`; the final-ELF gate validates resolved semantics, not source
spelling.

Allowed effects:

- use only `r0` and `r1` as scratch registers;
- one resolved read from `0xE0001004`;
- one resolved store to the exact J0 SRAM symbol;
- one unconditional tail transfer to the exact stock handler.

Forbidden effects:

- `push`, `pop`, or any stack access;
- `bl`, `blx`, calls, returns, or LR modification;
- conditional branches or added control logic;
- `cpsid`, `cpsie`, interrupt-mask changes, `mrs`, or `msr`;
- DSB, ISB, or other barriers;
- PMU, NPU, STATUS, or CMD MMIO;
- printf/logging;
- any additional memory load or store beyond address materialization, the one
  CYCCNT load, and the one J0 store.

If the assembler implements either address materialization with a PC-relative
literal-pool load, that read is allowed only as a constant-address
materialization effect. The gate must resolve its literal value to either
`0xE0001004` or the exact J0 symbol and prove the literal address lies in the
veneer's own read-only literal pool. At most two such literal-pool reads are
allowed. They do not count as data/MMIO reads; every other non-instruction
memory read remains forbidden. A `movw`/`movt` encoding is also valid.

The tail transfer preserves the live EXC_RETURN value in LR. `r0` and `r1` are
permitted because Cortex-M exception entry hardware-stacks the interrupted
values and the stock handler takes no arguments.

An intermediate linker thunk is not accepted. The final ELF must prove one
direct or semantically single unconditional transfer from the named veneer to
the exact stock handler. If a thunk appears, the build fails rather than
silently changing A1.

## Source and final-ELF gates

Source gates require exactly one:

- V11-A schema/build branch;
- J0 storage definition and serializer field;
- runtime `NVIC_SetVector(NPU0_IRQn, &v11a_u85_irq_entry_veneer)` install;
- veneer declaration;
- retained T1, T2, I0, and T3 markers from the V10 diagnostic shape.

They also prove the original stock handler body remains present and that the
runtime vector is not reinstalled to the stock handler elsewhere in the active
generated vendor path.

Final-ELF gates fail closed unless they prove:

1. the runtime vector-install argument resolves to the exact veneer address;
2. the veneer performs exactly one CYCCNT read from `0xE0001004`;
3. that value reaches exactly one store to the exact J0 symbol;
4. the veneer has no forbidden instruction or extra memory effect;
5. the only control transfer is an unconditional tail transfer to the exact
   stock `u85_irq_handler` with no LR modification and no intermediate thunk;
6. the existing path order remains `T2 < J0 < I0 < STATUS read < T3 < flag
   store < CMD=2 < H-PRINTF seam < CMD=0xC release` in execution semantics;
7. I0 and T3 are still exactly-once, and the vector-to-veneer path is unique.

For item 1, "exact veneer address" means the installed vector value is the
Thumb entry value (`symbol | 1`) and masking bit 0 produces the exact veneer
symbol. The gate must inspect the compiled `NVIC_SetVector` effect, not merely
the C argument: it must prove the write targets the active
`SCB->VTOR + NPU0 vector-slot offset`, stores the veneer Thumb entry value, and
is not followed by another NPU0 vector write that restores the stock handler
before the command can run. The active VTOR/vector-RAM setup is therefore a
build precondition recorded in the manifest. If this write cannot be resolved
from the final ELF, the build fails closed.

At runtime, a nonzero J0 plus exactly-one I0 and T3 is sufficient to establish
one J0 hit because every statically admitted veneer path unconditionally enters
the stock handler. A separate J0 counter is intentionally omitted to avoid
adding load/modify/store work before I0.

## Wire and host contract

V11-A uses a new schema and build identity on a separate host path. It extends
the V10 diagnostic body by one 32-bit J0 timestamp and must be rejected by the
V8, V9, and V10 parsers.

The classifier requires:

- frozen manifest, artifact, build-evidence, callsite, and case identity;
- nonzero monotonic T2/J0/I0/T3 checkpoints under `delta32`;
- exactly-one I0 and T3 counts;
- `(A0 + A1 + A2) & 0xffffffff == D23`;
- all retained PMU, stable-read, overflow, golden-window, MMIO-count, transport,
  raw-reread, and vendor-release gates;
- no retained re-hold or Production-only interpretation.

The only outer value name is `v11a_perturbed_window_cycles`. Host output must
state that it is not comparable to V8, V9, or V10 absolute values.

## Build and negative tests

The pre-board gate requires two clean ARM builds with byte-identical APP,
VECTORS, DDR, ELF, map, generated sources/object, and preprocessed runner.

Negative tests must reject at least:

- runtime vector still targeting the stock handler;
- a second vector installation overriding the veneer;
- missing or duplicate J0 store;
- wrong DWT or J0 address;
- stack access, call, conditional branch, barrier, interrupt-state change, LR
  write, extra load/store, PMU/NPU MMIO, or logging in the veneer;
- linker thunk or a tail target other than the exact stock handler;
- missing/duplicate I0 or T3;
- broken A0+A1+A2 identity;
- V10/V11 parser cross-acceptance;
- manifest, artifact, golden, MMIO, overflow, release, and raw-reread drift.

All existing V10, V9, V8, CFG, and DIAG test suites must remain unchanged and
pass.

## Board qualification plan

Board deployment is a separate approval boundary after pre-board build and ELF
qualification.

The first campaign is three independent full boots by ten consecutive runs.
Every sample must pass J0 presence, I0/T3 exactly-once, interval identity,
golden CRC, retained PMU validity, no overflow, raw reread, and vendor release.

Interpretation is limited to:

```text
A0 variable, A1 fixed, A2 fixed
  -> variation is present before first-veneer-probe

A0 fixed, A1 variable
  -> investigate veneer-to-I0/prologue path

A0 variable, A1 variable
  -> stop; audit perturbation or multiple variability sources before V12
```

No V11-A absolute cycle value is compared to V10. If variation is localized to
A0, later NPU-completion and IRQ-delivery questions require separate diagnostic
mechanisms rather than more software checkpoints in V11-A.
