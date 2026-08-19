# V14 comparator adversarial review

Step 5. `compare_declared_builds.py` is the tool every determinism claim in this
contract comes from, including the two `mismatches=[]` results reported earlier
today. It was reviewed by attacking it rather than by reading it.

## What it already refused

Thirty-nine tests, and the symlink surface is covered thoroughly: a symlinked
build root, a symlinked variant directory, a symlinked manifest, a declared
artifact whose path traverses a symlink, absolute artifact keys, `..` and `.`
components, an empty artifact table, a manifest for the wrong variant or schema,
a byte count that disagrees with the file, and absolute-path or timestamp
leakage in the manifest.

## What it accepted

Four attacks, all reporting `mismatches=[]` and exit zero:

| Attack | Before | After |
| --- | --- | --- |
| `--left R --right R` | `mismatches=[]`, exit 0 | exit 2, "same directory" |
| `--left R --right R/.` | `mismatches=[]`, exit 0 | exit 2, "same directory" |
| `--left R --right R/Q/..` | `mismatches=[]`, exit 0 | exit 2, "same directory" |
| every artifact hardlinked to the other side | `mismatches=[]`, exit 0 | `alias` mismatches, exit 1 |

None of these is a symlink, which is why the existing rules did not see them. A
hardlink carries no marker a path check can find: the file is one inode under
two names, and it agrees with itself forever. A directory compared with itself
is the same failure at the top of the tree, and it is the one an operator
reaches by accident -- build twice into one output directory and compare the
result with itself.

This is the eleventh silent gate found in this contract, and the one with the
widest blast radius: it does not refuse a bad build, it manufactures a passing
determinism result out of a comparison that never had two builds in it.

## The correction

- the two roots must resolve to different directories, must not be nested, and
  must not be one directory under two device/inode identities -- refused as a
  caller error, before anything is read
- the two variant directories, the two manifests, and every pair of declared
  artifacts must be distinct `(st_dev, st_ino)` -- reported as an `alias`
  mismatch

## Regression

The two real comparisons from today were re-run against the corrected tool:

| Comparison | Result |
| --- | --- |
| `SAMEPATH_A` vs `SAMEPATH_B` (step 3.5) | `mismatches=[]`, exit 0 |
| `T4_A` vs `T4_B` (after helper hardening) | `mismatches=[]`, exit 0 |
| `T4_A` vs `T4_A` (control) | exit 2, refused |

The artifacts are physically distinct, which the tool now proves rather than
assumes: `T4_A/Q/APP.BIN` is inode `2053:3052334` and `T4_B/Q/APP.BIN` is
`2053:3052860`.

So today's determinism claims stand, and they now rest on a comparator that is
able to fail.

What this tool proves, and what it does not: it establishes that the two sides
are independent artifacts -- distinct files, distinct inodes, distinct roots --
and that their declared bytes agree. It does not prove that A and B were two
clean builds run at two times. That is temporal provenance, and it comes from
the orchestration instead: build A, capture it, clean, build B, capture it, each
side copied out of the container before the next began.

## Mutation tests

| Mutation | Caught by |
| --- | --- |
| remove the root identity check | the same-root, path-alias and nesting tests (3) |
| neuter the per-artifact alias check | the hardlinked-artifact test |
| neuter the manifest alias check | the hardlinked-manifest test |
| make `_same_file` always answer no | both hardlink tests |

Host comparator suite: 45 tests, all passing.

## Verification level

- Executed: the four attacks before and after, the four mutations, the 45-test
  comparator suite, and both real comparisons re-run on `gihwan`.
- Not executed: the board, SD or UART. `origin/main` remains on hold.
