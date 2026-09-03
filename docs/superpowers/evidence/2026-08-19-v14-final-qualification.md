# V14 final qualification pass

Step 8, run against one HEAD. Everything below was executed at `619e957` with a
clean working tree; the container's checker was verified byte-identical to the
one in that commit before a single build ran.

## The eleven items

| # | Item | Result |
| --- | --- | --- |
| 1 | current HEAD clean | `619e957`, 0 modified files |
| 2 | host full suite | 234 tests, all passing (see breakdown) |
| 3 | firmware full suite | 1241 passed, 0 failed |
| 4 | comparator regression | 45 tests; real A/B `mismatches=[]`; same-root control refused |
| 5 | Q/QS/SQ clean ARM build A/B | 6/6 exit zero, `mismatches=[]` |
| 6 | real ELF gates | `REAL_ELF PASS` 6/6; `READ_ORDER EQUIVALENT` |
| 7 | manifest replay | 6/6 `MANIFEST PASS`, 16 artifacts each, A/B bundle hashes identical |
| 8 | frozen V11-A / V12 / V13 integrity | unmodified since `32b30d2`; V12 suite 110/0; V13 suite 306/4 (known) |
| 9 | board-preflight synthetic suite | 51 tests, all passing |
| 10 | requirements matrix recomputed | 29/29 |
| 11 | analyzer / collector semantic tests | 33 and 34 tests, all passing |

Host breakdown: requirements 11, preflight 51, comparator 45, protocol 60,
analyzer 33, collector 34.

## A. Requirements matrix, recomputed at this HEAD

```
Load-bearing requirements    29
QUALIFIED                    29/29
UNTESTED                     0
NO_NEGATIVE                  0
REAL_ARTIFACT_UNAPPLIED      0
VACUOUS_ONLY                 0
AMBIGUOUS_AUTHORITY          0
```

Authority distribution: linked ELF 16, parser/classifier 3, analyzer 3,
collector 2, provenance 2, preflight 2, source 1.

## B. Silent-gate telemetry

Treated as a pre-board release gate rather than an ancillary test, because this
contract has produced eleven silent gates and every one of them looked like a
pass.

```
load-bearing claims                 36
distinct rules                      36
targeted negatives                  36   (each failing at its own rule)
detectors executed on real artifacts 36/36
unexpected vacuity                  0
registered vacuity entries          17
registered vacuity occurrences      18   (frozen; a change in either direction is RED)
claims resting only on a vacuous path 0
```

## The executable has not moved

Compared against the previous qualification build (`FINAL2_A`), 45 of the 48
declared artifacts are byte-identical -- `APP.BIN`, `VECTORS.BIN`, `DDR.BIN`,
the ELF, map, nm, objdump, DWARF dump, preprocessed source and both generated
sources, for all three variants.

The three that differ are the gate's own `linked_image_evidence.json`, one per
variant, and their diff is additive: seven keys added, none removed, no value
changed. Across three rounds of hardening today the gate has changed what it
reports and nothing it decides.

A and B are physically distinct: `FINAL8_A/Q/APP.BIN` is inode `2053:2294867`,
`FINAL8_B/Q/APP.BIN` is `2053:2424732`. The comparator now proves that rather
than assuming it.

## Known, carried forward

V13's own suite reports 306 passed and 4 failed. All four are the checks anchored
to `/tmp/v13-arm-loop-probe-20260815T073000Z`, a scratch directory from the V13
session that no longer exists. V13's checker is byte-identical to its frozen
commit and was not touched. This is a pre-existing V13 infrastructure defect,
recorded in the pre-board regression matrix, and it is not a V14 regression --
but it does mean "the full V8-V13 regression reproduces on a clean machine" is
not a sentence anyone may write.

## Status

```
V14 PREBOARD QUALIFIED       for HEAD 619e957 only

ACTUAL BOARD PREFLIGHT       NOT RUN
V14 BOARD CAMPAIGN           NOT RUN
origin/main                  HOLD
```

Any change to functional or gate code invalidates this pass from the affected
stage onward: an ELF helper change re-runs the ARM A/B, the ELF gates and the
claim matrix; a host analyzer change re-runs the semantic attack, the matrix and
the host suite; a comparator change re-runs the comparator attack and the A/B
determinism check.

## Verification level

- Executed: all eleven items, A and B, on `gihwan` and locally, at one HEAD.
- Not executed: the board, SD or UART. No push to any remote.
