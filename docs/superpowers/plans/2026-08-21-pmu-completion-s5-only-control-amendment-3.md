# V15 implementation protocol — Amendment 3

**The comparison identity is the analysis ELF, not the raw ELF.**

Supersedes the reference pin made in `78cc627`. That commit is not rewritten;
what it claimed is corrected here.

## What was claimed, and what was wrong with it

`78cc627` pinned the V14 Q comparison reference as a raw ELF digest and recorded:

```
V14_Q_RECONSTRUCTED_ELF_SHA256 = 20baff11…
V14_Q_AB_DETERMINISM           = ELF_IDENTICAL_ACROSS_CLEAN_REBUILDS
```

Two clean builds did agree. Both ran in the same session from the same
directory, and the claim was written as though it were unconditional.

## The measurement

Found while building the V15 candidate: identical inputs, identical code, and a
raw ELF digest that did not match the earlier probe build. The cause is that
DWARF records absolute build paths. Copying the tree and building elsewhere:

| | `/work/selftest` | `/tmp/pB/selftest` | |
| --- | --- | --- | --- |
| V14 Q raw ELF | `20baff11…` | `21614764…` | **differs** |
| V14 Q analysis ELF | `24c31bf4…` | `24c31bf4…` | identical |
| V14 Q `APP.BIN` | `f745eebd…` | `f745eebd…` | identical |
| V15 S5 raw ELF | `c2373581…` | `04c13b0e…` | **differs** |
| V15 S5 analysis ELF | `49d22540…` | `49d22540…` | identical |
| V15 S5 `APP.BIN` | `4967fa39…` | `4967fa39…` | identical |

Three distinct raw digests have now been seen for the one V15 image, counting
the probe session. The disassembly of `v15_primary_s5` is byte-identical to the
objdump the probe recorded.

An identity that moves when a nuisance variable moves is not an identity. Left
alone, a legitimate rebuild from another directory would have been rejected as a
different image.

## The correction

```
RAW_ELF        the file the build wrote; full SHA is informational provenance
ANALYSIS_ELF   RAW_ELF through one pinned transform; its digest is the identity
```

The transform is frozen as a contract rather than described:

```
kind       GNU_OBJCOPY_STRIP_DEBUG
tool       arm-none-eabi-objcopy
toolchain  Arm GNU Toolchain 15.2.Rel1 (Build arm-15.86), 15.2.1 20251203
operation  --strip-debug
```

`V14_Q_ANALYSIS_ELF_SHA256 = 24c31bf4e7e338b888097953873d6511af3c6fd82eac2777ca1d12bbb2d10b2e`

### This is not a relaxation

Exact equality is still required. What changed is the object it is required of,
and that object was chosen because it depends on the code rather than on where
the code was compiled. `--strip-debug` is a deterministic transform fixed in
advance, not a tolerance — nothing here says "close enough", and a digest
differing by one character is still refused.

The distinction that matters: this replaces *raw digest exact equality* with
*canonical digest exact equality*. It does not permit a mismatch.

It also was not chosen to make a result pass. It was found before any V15 board
data existed, by perturbing the build path of identical code and watching the
raw hash move.

### The condition that makes it honest

The analysis ELF is what the checkers **consume**, not merely what gets hashed.
Hashing one artifact and analysing another would mean the object given an
identity and the object examined are different things. So the same
canonicalisation produces both, and Tasks 6, 7 and 8 were re-run against the
canonical artifacts rather than assumed to carry over.

## Applied symmetrically

Both sides move, not just the V14 reference:

```
manifest            raw_elf_sha256        informational
                    analysis_elf_sha256   load-bearing
static evidence     v15_analysis_elf_sha256
equivalence         v15_analysis_elf_sha256, v14_q_analysis_elf_sha256
```

The load-bearing equality is now
`equivalence.v15_analysis_elf == static.v15_analysis_elf == manifest.analysis_elf`.
Raw digests are deliberately absent from it.

## What the reconstruction established, in three separate claims

| | |
| --- | --- |
| `V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET` | `REPRODUCED_BYTE_EXACT` |
| `V14_Q_ANALYSIS_ELF_STABILITY` | `PATH_INDEPENDENT_ACROSS_TESTED_BUILD_PATHS` |
| `V14_Q_RAW_ELF_SAME_PATH_AB` | `IDENTICAL` (scope in the name) |
| `HISTORICAL_RAW_ELF_IDENTITY` | `NOT_CLAIMED` |

The provenance bridge splits in two rather than being discarded:

```
frozen V14 Q lineage
      ↓
reconstructed RAW ELF
      ├─ objcopy → APP/VECTORS/DDR → byte-exact → historically deployed
      └─ strip-debug → canonical ANALYSIS_ELF → equivalence checker reference
```

## Gates re-applied to the canonical artifacts

| gate | result |
| --- | --- |
| Task 6 S5-only boundary | PASS — 1 status read/iteration, deciding register `r2` |
| Task 7 Q↔S5 equivalence | PASS — 6 instructions/iteration, role sequence matched |
| Task 8 post-freeze tail | PASS — 40 instructions, MMIO sequence, mask `0x33F` |

Preservation was measured, not assumed: disassembly identical, all 363 symbols
identical, allocatable sections identical, ten debug sections dropped — on both
variants.

## Provenance

| | |
| --- | --- |
| design anchor | `58b0cad`, unchanged |
| plan anchor | `3ca7bb1`, unchanged |
| Task 1 contract | `d96fa97`, unchanged |
| amendment 1 | poll count, unchanged |
| amendment 2 | wire vs record, unchanged |
| superseded | `78cc627`'s raw-ELF pin, corrected here, not rewritten |
