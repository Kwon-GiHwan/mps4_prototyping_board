# V15 probe build

The first ARM build of the S5-only control. A probe rather than a candidate: it
exists to show the graph works and to let Tasks 6 to 9 be written against a real
image instead of an intention. No board was touched.

## What it took

Two integration faults, both real and both worth recording.

The first was the schema macro. The generated source carries the exemption that
lets a diagnostic build link the private driver copy, and that exemption is keyed
to the schema: `PMU_QUAL_SCHEMA_V15`. The derived Makefile still passed
`-DPMU_QUAL_SCHEMA_V14`, so the guards fired exactly as they should have --
`S1/S2 must link the reference vendor u85.c`. The macro is now V15's.

The second was dead weight rather than a fault: the dual-variant primary block
came across in the derivation and is meaningless in a single-variant experiment.
Removed, and generation produces the same bytes without it.

## The measured loop, as the compiler emitted it

```
310024ca:  ldr   r2, [r1, #4]     one STATUS load   (r1 = 0x50004000, +4 = STATUS)
310024cc:  tst.w r2, #32          bit5
310024d0:  bne   -> success
310024d2:  adds  r0, #1           iteration number
310024d4:  subs  r3, #1           bound, counting down from 10000
310024d6:  bne   -> loop
```

One MMIO load per iteration. No QREAD, no QSIZE. The deciding word stays in `r2`
and is stored to the record on both the success and the timeout path
(`str.w r2, [ip, #12]`), so the host can derive bit1 from the same word the bit5
test used -- which is what the contract asks for, without the firmware computing
anything.

This is the source contract holding in the emitted code, but it is not yet the
Task 6 gate: reading a disassembly and gating it are different things, and only
the second is evidence.

## Two things worth carrying forward

**Poll count may be free.** `r0` already counts iterations and is already
published as `obs->iterations`. Nothing was added to the loop to get it, which is
the Case A condition Task 9 has to decide -- to be decided there, on a comparison
of the two builds, not here on a reading.

**DDR.BIN is unchanged from V14.** `81d37a219a6b4141`, the same digest V14's
three variants share. The NPU command stream is what it always was, which is
what a control that changes only the observable should show.

## Digests

| Artifact | sha256 (16) |
| --- | --- |
| APP.BIN | `4967fa39205eefb1` |
| VECTORS.BIN | `6864a22bf98b0172` |
| DDR.BIN | `81d37a219a6b4141` |
| ELF | `8fa697792e68cdc3` |

Probe only. Not a determinism build, not a candidate, and not deployed.
