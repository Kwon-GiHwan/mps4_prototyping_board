# V14 requirements coverage and host semantic attack

Step 7, in the two axes the manager redefined it as: the coverage matrix, and an
attack on the part of the system that can produce a wrong research conclusion
from a correct executable and correct raw samples.

## 7-A Requirements coverage matrix

29 load-bearing requirements, each naming exactly one **authority** -- the layer
whose answer is the answer. That is the column that makes this more than a table
of function names: a claim checked in four places and decided in none of them,
or decided in two places that mean different things by it, is the failure the
authority column exists to prevent.

| Authority | Requirements |
| --- | --- |
| linked ELF | 16 |
| host parser/classifier | 3 |
| analyzer | 3 |
| collector | 2 |
| manifest/provenance | 2 |
| board preflight | 2 |
| source/generator | 1 |

Only one requirement is decided on the source: `R04_GATE_SHAPE`, because "the
gate reads STATUS once, in one function" is a statement about how the gate is
written and the compiler is free to schedule the read it produces. Everything
else about the measured code is decided on the image.

The table is data and the suite checks the data rather than trusting it:

- every firmware rule named must exist **and be in the checker's claim matrix**,
  which is what guarantees it carries a targeted negative that fails at that rule
  and that its detector runs against the real images
- the reverse direction too: all 36 claim-matrix rules are carried by some
  requirement, so no load-bearing rule is unaccounted for
- every host function named must exist, methods resolved through their class
- every test named must exist in the module named
- no requirement may name a corroborating layer that is also its authority

Writing it caught four stale references in its own first draft -- a function
that had been renamed, and three tests that never existed under the names the
table gave them.

### Exit criteria

```
Load-bearing requirements    29
QUALIFIED                    29/29
UNTESTED                     0
NO NEGATIVE                  0   (via claim-matrix membership)
REAL-ARTIFACT UNAPPLIED      0   (of the 16 ELF-authority rows; 19 rows overall
                                  reach a real artifact, the rest await a board)
VACUOUS-ONLY EVIDENCE        0
AMBIGUOUS AUTHORITY          0
```

The build-determinism row records both halves the manager asked for: artifact
identity is decided by `compare_declared_builds`, adversarially qualified at
step 5; that A and B were two clean runs at two times is temporal provenance and
belongs to the build orchestration.

## 7-B Host semantic attack

### What was already closed

The collector's 34 tests already refuse a boot change mid-cell, a gap or a
repeat in the run sequence, an eleventh run, a sample from another variant, a
retry without a disposition, a completed cell being reopened, a campaign
continuing after a failure, and a caller asserting validity for itself.

### What was not

The analyzer took `sample["category"]` at face value. Whoever computes that
field decides the conclusion, which makes the campaign a test of the classifier
rather than of the runs. Relabel every sample and the verdict follows the label.

The analyzer now re-derives the category from the record's own words -- the
queue cursor it read, the queue size it expected, the STATUS word it sampled in
the same iteration -- and refuses any sample whose recorded label disagrees with
what its fields produce. The collector was changed to carry those three raw
fields so this is possible at all.

| Attack | Result |
| --- | --- |
| relabel one sample | refused |
| relabel every SQ sample so the campaign reads as read-order bias | refused |
| flip one first-tuple flag | refused as a self-contradicting record |
| swap which variant is QS and which is SQ | conclusion changes, as it must |
| a sample missing a raw field | refused, not defaulted |
| a first tuple that observed neither register | refused |

One existing test had to be rewritten: it built a "mixed campaign" by rewriting
labels, which is exactly the manipulation now refused. It changes the record's
own fields instead -- and the fact that it had to is the demonstration.

### Mutation tests

| Mutation | Caught by |
| --- | --- |
| read the label instead of deriving | the derivation handed label-free samples |
| treat same-iteration as Q-first | the same-iteration and mixed-campaign scenarios |
| drop the label/derivation comparison | all three relabelling attacks |

The first survived the first attempt. Validation already refuses a disagreeing
label, which makes reading the label afterwards equivalent -- today, and only by
the grace of a second rule. The derivation is now handed samples with no label
at all, so reading one raises.

## Verdict names

The manager's scenario list names five outcomes; this analyzer has four. They
correspond, except that where the manager separates `QREAD_EARLIER_CANDIDATE`
from `STATUS_EARLIER_CANDIDATE`, the analyzer maps both to
`CONTROL_REQUIRED_NO_FINAL_ORDERING`. That is deliberate and stricter: naming
which register is earlier is a claim the design forbids until a fresh
bit5-only S5 control exists, so both dual variants agreeing on a register is
reported as "the control comes first" rather than as a candidate ordering. The
register they agreed on is still recorded, as data, in `per_boot_categories`.

## Status

```
Requirements:
  load-bearing            29/29 qualified
  untested                0
  authority ambiguous     0
  negative missing        0
  real-artifact unapplied 0

Collector:
  campaign state-machine attacks   all rejected

Analyzer:
  synthetic verdict scenarios      all correct
  mutations                        all RED for intended reason
  raw-evidence rederivation        PASS

Suites: firmware 1241/0; host requirements 11, preflight 51, comparator 45,
protocol 60, analyzer 29, collector 34 -- all passing.
```

## Verification level

- Executed: every suite above, and the mutations named.
- Not executed: the board, SD or UART. `origin/main` remains on hold.
