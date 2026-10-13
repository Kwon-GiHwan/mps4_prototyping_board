# V15 implementation protocol — Amendment 2

**`comparison_mode` is not a wire field and is not target-observable.**

Discovered before the Task 10 parser was written and before any V15 board
execution. The frozen design (`58b0cad`) and plan (`3ca7bb1`) are **not**
modified, and neither is the schema-15 wire layout.

## What was found

Two things, one leading to the other.

### A host constant that described the wrong schema

`contract.APPENDIX_FIELDS` carried the comment *"the appendix, in wire order"*
and did not describe the wire appendix.

| | |
| --- | --- |
| frozen firmware appendix | 34 words |
| host contract list | 24 names |
| names in the host list absent from the wire | 11 |

The two sets were never the same schema. Eleven of the host names are frame
header words or host-derived values. No parser had consumed the constant yet —
Task 10 would have been the first, and `dict(zip(names, words))` truncates to
the shorter side without raising, so a parser built on it would have produced
plausible numbers from misaligned words and gone green.

### `comparison_mode` has no serialized origin

Every word slot of the 127-word frame was enumerated.

| region | words | carries `comparison_mode` |
| --- | --- | --- |
| frame header (fixed v8 ABI) | 0–7 | no |
| legacy v8 body | 8–92 | no |
| V15 appendix | 93–126 | no |
| emitted firmware C, entire tree | — | no, 0 occurrences |

This is not a missing `put32`. `comparison_mode` records whether the V15
primary loop is semantically equivalent to the frozen V14 Q reference, which is
decided by host-side ELF analysis. **The target cannot know it.** A frame is the
wrong place to look for it, and adding a word to carry it would be asking the
firmware to assert something it has no way to determine.

The earlier eight-layer contract, which said the mode is transported from
firmware evidence onward, therefore described a chain that could not exist. Task
11's fixtures were green over synthetic objects and were never raw-frame
propagation proof.

## The hole this exposed

`build_id` is not in the frame either — in V14 it is a manifest field checked by
`verify_manifest()`. So the only frame content bearing on image identity is
`schema_version` (15) and `variant_id` (S5 = 1), and V15 has exactly one of
each. **Every V15 frame satisfies both.**

That is reachable, not theoretical. The no-count scratch build from Amendment 1
is schema 15, variant 1, and *fails* equivalence at
`RULE_EQUIVALENCE_LOOP_SHAPE`. Its frames are indistinguishable from the shipped
build's. Only the procedural fact that it was never flashed stands between it
and being analysed under `Q_S5_EQUIVALENT`.

## Decision

The wire is unchanged. The mode is bound to board runs outside the frame.

```
comparison_mode origin      STATIC_IMAGE_EVIDENCE
frame-to-image relation     VERIFIED_DEPLOYMENT_CONTEXT
wire schema 15              UNCHANGED / FROZEN
```

The chain the earlier contract named is replaced by one that is true:

```
static_image_evidence -> build manifest -> verified deployment context
  -> collector -> normalized record -> classifier -> analyzer -> report
```

The wire parser knows nothing of the mode. `ParsedFrame` has no
`comparison_mode`; `VerifiedCellContext` and `NormalizedRecord` do, with origin
`STATIC_IMAGE_EVIDENCE`. `parse_frame(raw_bytes) -> ParsedFrame` is the whole of
the parser's authority, and a separate `normalize(parsed, context)` step is what
attaches externally-bound facts. A parser that reads a manifest is a parser that
has re-mixed the two provenances this amendment exists to separate.

### Three field layers, not one list

| layer | authority | contents |
| --- | --- | --- |
| `runner_proto_v15.APPENDIX_FIELDS` | exact firmware tuple, 34 words | wire only |
| `contract.RECORD_FIELDS` | normalizer output, 24 names | logical record |
| `contract.RECORD_FIELD_ORIGINS` | provenance of each record field | the mapping |

`RECORD_FIELD_ORIGINS` is a blocking requirement rather than documentation:
without one authoritative mapping, wire, derived and static metadata drift back
into a single list under a better name.

## What this claims, and what it does not

> The campaign pipeline binds live collection to a hash-verified deployed
> artifact set and its static qualification evidence.

It does **not** claim that a frame cryptographically proves which image emitted
it. The target emits no image identity, so a raw frame replayed against a
different cell context cannot be detected from frame content alone. This is
external deployment provenance, not target-generated frame attestation. Should
the stronger property ever be required, it needs a schema revision in which the
target emits build identity — which the present threat model does not justify.

### Why not the alternatives

**A new wire identity word** is the strongest option and was rejected as
disproportionate: it changes the wire ABI, forces a schema migration, and widens
firmware and parser requalification, to solve a problem that separating build
provenance from run provenance already solves.

**Repurposing the unused header `flags` word** was rejected as worse than A. The
byte length is unchanged but the semantics of a frozen ABI word are not, so it
costs approximately what A costs while delivering a small flag rather than a
complete artifact identity.

## Provenance

| | |
| --- | --- |
| design anchor | `58b0cad`, unchanged |
| plan anchor | `3ca7bb1`, unchanged |
| Task 1 contract anchor | `d96fa97`, not rewritten |
| wire layout | unchanged: 8 + 85 + 34 = 127 words, 508 bytes |
| amendment 1 | poll count, unchanged |
| amendment | this document |
