# V14 helper soundness

Step 4. The two helpers every ELF claim in this contract rests on were found
unsound by review rather than by a fixture, which is the wrong order. The point
of this step is not to have a test that catches the bug; it is for the helpers
to have a correct model, with the verdict on the shipping image pinned so the
correction cannot quietly change what the gate believes about it.

## Step 3.5 first: the current gate against the current ARM artifacts

The gate changed in step 3, so the six builds were repeated before anything was
stacked on them -- same container, compiler, environment and command, one build
path, A then B, each copied out before the next began.

| Check | Result |
| --- | --- |
| builds | 6/6 exit zero, `REAL_ELF PASS` 6/6 |
| `compare_declared_builds` A vs B | `mismatches=[]` |
| `MANIFEST PASS` | 6/6, 16 declared artifacts each |
| A/B bundle hash per variant | identical |
| `READ_ORDER EQUIVALENT` | yes; tail shared, `differ_only_in_read_order` true |

And against the previous qualification build (`FINAL2_A`), which is the question
that matters: 45 of the 48 declared artifacts are byte-identical, including
every one of `APP.BIN`, `VECTORS.BIN`, `DDR.BIN`, the ELF, the map, the nm, the
objdump, the DWARF dump, the preprocessed source and both generated sources.

The three that differ are the gate's own `linked_image_evidence.json`, one per
variant. Their diff is additive only -- `mailbox_publication/residual` and a
six-entry `writer_scope` list appear, and no existing value changes. So the
hardening changed what the gate *reports*, not what it *decides*, and the
restored gate examined the same executable as the earlier board candidate and
passed it.

## _elf_transfer: AAPCS

The model kept register values across instructions that destroy them. Two ways:

- a call left `r0`-`r3`, `r12` and `lr` believed, though AAPCS lets the callee
  use all of them
- a `pop` or `ldm` left the pre-push value believed, though the loaded value
  comes from a stack this gate does not model

The second is the sharper one: pushing a value, changing the register, and
popping it back would carry the old provenance across the change, which is a
bypass anyone writing the firmware could take by accident.

Both are fixed by killing provenance rather than by trying to model more. The
fixtures are unit-level, on a synthetic function, because the property is about
the model and not about any image:

| Fixture | Requires |
| --- | --- |
| `ldr r3, =0x50004000` then `bl` | `r3` known before, unknown after |
| the same call | `r0` unknown after |
| `movs r0,#17`; `push`; `movs r0,#0`; `pop` | `r0` unknown after the pop |
| `ldr r4, =…`; `push {r4}`; `pop {r4}` | `r4` unknown after the pop |
| `ldr r4, =…`; `push {r0}`; `bl` | `r4` still known -- the fix costs nothing it should not |

## _elf_word_writes: the CFG, not the address range

The frame length is a count of executions and was a count of call sites. Three
corrections, in the order they now run:

1. reachability is computed first, and everything after it is asked of reachable
   code only -- dominance over unreachable nodes is vacuous, and asking the loop
   question about them reported back edges that do not exist
2. a call the entry cannot reach is skipped, because counting it counts the
   source rather than any execution
3. a call that is reachable but that some path skips is refused, because either
   answer -- counted or not -- is wrong on half the executions

| Fixture | Requires |
| --- | --- |
| `b.n` over the first of two `bl put32` | count is 1 |
| the same two calls, branch removed | count is 2 |
| `bne.n` over the serializer's first `bl put32` | refused at `RULE_SERIALIZATION_COUNTABLE` |

The third also asserts the identifier, so a mutation that trips the length rule
instead of the countability rule is a failed fixture rather than a passing test.

## The verdict on the shipping image does not move

| Variant | frame words | MMIO accesses | access-set digest |
| --- | --- | --- | --- |
| Q | 127 | 74 | `5ca4394245d8fcb29877924c56e948d5` |
| QS | 127 | 74 | `fe2f139636f1b6ade222d7292347118f` |
| SQ | 127 | 74 | `b738278631abaab34fdee11a0cdb6a31` |

The digest covers instruction address, resolved address, width, direction, role
and reachability for every access. Pinning the count alone would let the model
lose one access and gain another with nothing failing.

## The vacuity registry, as asked

Each of the seventeen entries now records what its owner proves, the artifacts
it was measured over, why the loop is idle on them, and what evidence proves the
claim instead. The suite goes RED on five conditions: an undeclared vacuity, a
declared one that starts running, a change in the total count, an entry missing
any of its four fields, and a load-bearing claim whose only evidence path
examined nothing.

All seventeen are source-side helpers. No rule in the linked-image layer has a
vacuous loop, and no claim in the matrix rests on one.

## Mutation tests

| Mutation | Caught by |
| --- | --- |
| remove the AAPCS call clobber | the two call fixtures |
| remove the pop/ldm handling | the two stack fixtures |
| neuter the path-invariance test | the conditional-call fixture, at its own rule |
| remove the reachability filter | the unreachable-call fixture |
| delete a registry entry | undeclared vacuity, and the count |
| empty a claim detector's only evidence loop | all three vacuity conditions, including "rests only on a path that examined nothing" |

## Verification level

- Executed: firmware suite 1241 passed / 0 failed; the six mutation tests above;
  `verify_linked_image` and the source gate against the real artifacts.
- Not executed: the board, SD or UART. `origin/main` remains on hold.

## Requalification after the correction

The helpers changed, so the six builds were run again with the corrected gate
staged by hash into the container (`60154b1279a48236…`).

| Check | Result |
| --- | --- |
| builds | 6/6 exit zero, `REAL_ELF PASS` 6/6 |
| `compare_declared_builds` A vs B | `mismatches=[]` |
| vs the previous qualification build | 45 of 48 declared artifacts byte-identical |
| the three that differ | the gate's own `linked_image_evidence.json`, 7 keys added, 0 removed, 0 values changed |

Twice now, across two rounds of hardening, the correction has changed what the
gate reports and nothing it decides, and the executable has not moved at all.
