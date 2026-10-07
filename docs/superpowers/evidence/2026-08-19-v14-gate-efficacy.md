# V14 load-bearing gate efficacy

Step 3 of the manager's order. The question this answers is not "does the gate
pass" but "can the gate fail" -- whether the rules that carry the claim that V14
is correct are able to refuse an executable that is wrong, and whether they look
at anything at all when the artifacts that ship go through them.

## Claim matrix

Thirty-six load-bearing claims, each with one rule of its own, each with a
negative fixture aimed at it. The suite requires three things per claim: the
rule exists in the checker, a targeted negative exists, and the negative is
refused *at that rule* -- `refusal_rule(exc) == rule` -- rather than merely
refused.

| Column | Result |
| --- | --- |
| Load-bearing claims | 36 |
| QUALIFIED (4/4 columns) | 36 |
| UNTESTED | 0 |
| WRONG-REASON negatives | 0 |
| UNREACHABLE gates | 0 |
| REAL-ELF unapplied | 0 |

The three groups the manager named as zero-coverage are closed:

| Group | Rules | State |
| --- | --- | --- |
| mailbox (runner gate) | GATED, READONLY, ONE_CHECK, TUPLE_COMPLETE | CLOSED 4/4 |
| `_elf_word_writes` (serialization) | LENGTH, COUNTABLE, NAMED_CALLEES | CLOSED 3/3 |
| DWARF | RECORD_PRESENT, MEMBER_READABLE, SIZE_PRESENT | CLOSED 3/3 |

## What the rule-identity requirement found

`RULE_RUNNER_MAILBOX_GATED` could not fire. Its decision read `if False:`
instead of `if ungated:`, and the evidence field it returns said
`every_tuple_read_dominated_by_the_magic_check: True` unconditionally. The
neutering was deliberate -- it came from the mutation sweep in `9af15f2` -- and
was committed without being reverted.

Nothing was admitted that should not have been: none of the three images has an
ungated tuple read, which is why the defect was invisible to every positive
result. For one commit the runner's mailbox gate proved nothing, and it took a
negative fixture that *had to fail at that rule* to notice.

Three fixtures were written before one worked, and the two failures are the
reason the requirement is worth its cost:

- removing the magic check tripped `RULE_RUNNER_MAILBOX_ONE_CHECK`
- branching past it left mailbox reads unresolvable and tripped
  `RULE_RUNNER_TUPLE_COMPLETE`
- adding an extra, ungated tuple read at the top of the dispatcher -- leaving
  all 33 reads and the single check intact -- reaches the intended rule

## What the rules do on the real artifacts

A negative proves a rule can fire. It does not prove the rule examines the
artifact that ships. So the real verification is traced -- three linked images,
both cross-variant proofs, three generated source pairs -- and two properties
are measured from that trace and enforced by the suite:

1. every claim's detector executes against the real artifacts: **36/36**
2. no loop inside the gate runs zero times without being declared

The second is the general form of the most expensive defect this contract has
produced: a rotated convergence loop whose body set came out empty made every
per-iteration rule vacuously true, and looked exactly like a pass.

Eighteen loops do run zero times on the real artifacts. All eighteen are named
with a reason in `VACUOUS_ON_REAL_ARTIFACTS`; an undeclared one fails the suite,
and a declared one that starts running fails it too. They fall into two kinds:
alternative spellings the real sources do not use (register access through a
pointer dereference rather than `read_reg`, `#undef`, MMIO macros, address-taken
`irq_triggered`), and difference-reporting paths that only run on a failure.

Two were checked by hand rather than reasoned about:

- `dereference_sites` does produce effects where that spelling exists -- the
  convergence helper's `qread = *qread_reg` and `status = *status_reg` resolve
  to `load:QREAD` and `load:STATUS`
- the bare `NPU_REG_` scan finds nothing because the loop bodies reach the
  registers through pointers loaded before them, not because the pattern is broken

## Mutation tests

Both new checks were neutered and required to go RED:

| Mutation | Result |
| --- | --- |
| an empty `for _unreached in ():` loop added inside a detector that runs on the real images | caught by the vacuity check |
| `verify_npu_irq_never_enabled_image(...)` replaced with a literal result | caught by the detector-application check |

## Verification level

- Executed: firmware unit and integration suite, 1224 passed / 0 failed;
  `verify_linked_image` against the real Q/QS/SQ objdump, nm and DWARF; the
  source gate against three real generated pairs; the two mutation tests above.
- Not executed: the board, SD or UART; `origin/main` remains on hold.

## Rebuild with the corrected gate

The gate changed, so the ARM builds were repeated before anything was stacked on
top of them. The checker was staged by hash at all three hops -- working tree,
`gihwan`, container -- at `36c4278d233ff7ba…`, and six builds were run at one
build path, A then B, each copied out before the next began.

| Check | Result |
| --- | --- |
| builds | 6/6 exit zero |
| `REAL_ELF PASS` | 6/6 |
| `compare_declared_builds` | `mismatches=[]` |
| `MANIFEST PASS` | 6/6, 16 artifacts each |
| A/B bundle hash per variant | identical (`9ce2435b…`, `da97424a…`, `33251524…`) |
| `READ_ORDER EQUIVALENT` | yes; common tail shared, `differ_only_in_read_order` true |

The six tracked linked-image fixtures are byte-identical to this build:

| Artifact | sha256 (16) |
| --- | --- |
| Q.objdump | `a517fed4b4f0017a` |
| Q.nm | `5b7af19784cdf001` |
| QS.objdump | `6f283564e8c9c8b1` |
| QS.nm | `4bcec1e2b90a79e2` |
| SQ.objdump | `4a67a48c26bf9e10` |
| SQ.nm | `f1d0721d7fb400b9` |

So the unit suite and the ARM build are looking at the same bytes, and the
efficacy measurement above is a measurement about the image that would ship.
