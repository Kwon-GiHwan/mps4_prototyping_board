# V14 Q reconstruction — the provenance bridge, closed

Run 2026-08-21 in the qualified build environment. Board not touched.

## Why this was needed

`comparison_mode` says the V15 primary loop is equivalent to the frozen V14 Q
reference. That comparison is made between two ELFs. But the V14 campaign
recorded only the *deployed binaries* — no ELF digest was ever written down — so
there was nothing tying the ELF the equivalence gate reads to the image the
board actually ran. That gap was the last unresolved link in the chain.

## Environment

The original container, still running, not a substitute.

| | |
| --- | --- |
| host | `gihwan` (`ssh.gihwan.uk` via cloudflared), x86_64 |
| container | `benchmark-runner`, up 4 days, writable layer intact |
| toolchain | `arm-none-eabi-gcc 15.2.1 20251203` (Arm GNU Toolchain 15.2.Rel1, Build arm-15.86) |
| tree | `/work/selftest` |

Build inputs verified byte-identical to the frozen lineage before building —
`153f368` has zero commits touching any of them:

```
0e6e86a360e59083…  Makefile.pmu_completion_visibility_v14
6b733095a50ce8b3…  patches/patch_pmu_completion_visibility_v14.py
bcd877bbd42a35d8…  Drivers/u85_driver/u85.c      (matches the Makefile's pinned VENDOR_SHA256)
```

## Procedure

Two independent clean builds, as directed:

```sh
make -f Makefile.pmu_completion_visibility_v14 V14_VARIANT=Q clean
make -f Makefile.pmu_completion_visibility_v14 V14_VARIANT=Q bins
```

## Result — Case R1

Build A and build B agree on every artifact, **including the ELF**:

| artifact | build A | build B | historically deployed |
| --- | --- | --- | --- |
| `APP.BIN` | `f745eebd…7b25d` | identical | `f745eebd…7b25d` ✓ |
| `VECTORS.BIN` | `6864a22b…4d0d91` | identical | `6864a22b…4d0d91` ✓ |
| `DDR.BIN` | `81d37a21…4ade98` | identical | `81d37a21…4ade98` ✓ |
| `runner_pmu_completion_visibility_v14.elf` | `20baff11…12391a` | identical | never recorded |

Deployed digests are from `v14-campaign-20260819/R1/cell_Q.json`, where source
and destination read-back were equal across nine boots.

All three deployed artifacts match byte-exact. This is Case R1, not R3: full-file
ELF determinism across clean rebuilds also holds.

## The ELF-to-APP relation, proved separately

A rebuild producing a matching APP is not by itself proof that *this* ELF
produces that APP — the build could have matched for other reasons. So the
`objcopy` step was replayed against the pinned ELF alone, in a scratch
directory, with no build involved:

```
f745eebd…7b25d  APP.BIN
6864a22b…4d0d91  VECTORS.BIN
81d37a21…4ade98  DDR.BIN
```

The chain therefore is:

```
reconstructed V14 Q ELF   20baff11…12391a
        ↓ objcopy, replayed independently of the build
reconstructed APP/VECTORS/DDR
        ↓ byte equality
deployed V14 Q artifacts  f745eebd… / 6864a22b… / 81d37a21…
```

## What this licenses, and what it does not

Claimed:

> An ELF reconstructed from the frozen V14 Q lineage produces, by the recorded
> build relation, the exact runtime image set the board ran.

Not claimed: that this is byte-identical to the historical ELF. No historical ELF
digest exists to compare against, and an ELF carries debug sections, a symbol
table and build metadata that never reach the APP. The pin is a **reconstructed
analysis reference**, not a recovered artifact — which is all the equivalence
comparison needs, since it compares code.

```
V14_Q_DEPLOYED_REFERENCE      APP/VECTORS/DDR, as recorded by the campaign
V14_Q_ANALYSIS_REFERENCE      reconstructed ELF 20baff11…, produced_app f745eebd…
V14_Q_RECONSTRUCTION_STATUS   APP_ARTIFACT_SET_MATCHED
AB_DETERMINISM                ELF_IDENTICAL_ACROSS_CLEAN_REBUILDS
```
