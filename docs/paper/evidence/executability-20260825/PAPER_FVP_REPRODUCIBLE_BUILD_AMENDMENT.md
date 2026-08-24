# Amendment — reproducible formal build identity

**Formal samples observed before this finding: 0.**

Not a relaxed criterion. The formal identity contract required an equality that
was impossible to satisfy; this establishes a build under which it *can* be
satisfied exactly.

## Finding

```
source/app/main/Main.cc:38
    info("Version %s Build date: " __DATE__ " @ " __TIME__ "\n", PRJ_VER_STR);
```

The stock runner embeds its own build timestamp. Two builds at the identical
path, identical flags, identical arena differ in **exactly 3 bytes** — the clock
time in that literal. Every AXF is unique to the second it was linked, so the
AXF digests recorded during the 133-cell pass cannot be reproduced by any later
build, for any cell.

## Diagnostic

Pinning `SOURCE_DATE_EPOCH` makes the AXF byte-reproducible; nothing else in the
toolchain varies.

## Decision

The formal AXF reference is established under a pinned `SOURCE_DATE_EPOCH`
**derived from the pinned MLEK commit timestamp** — not from a value chosen at
diagnosis time, and unrelated to the current clock or to any result.

```
mlek_commit                  b2c0bb2884698b7328f65c41b7c8c51ca9bec386
FORMAL_SOURCE_DATE_EPOCH     1776763519
source_date_epoch_authority  MLEK_COMMIT_TIMESTAMP
commit date                  2026-04-21T09:25:19+00:00
expected embedded literal    "Build date: Apr 21 2026 @ 09:25:19"
```

## Two identities, not one overwritten

The qualification digests are **kept**, not corrected:

| identity | meaning |
| --- | --- |
| `EXECUTABILITY_AXF_SHA256` | timestamp-bearing artifact; historical evidence of the executability pass |
| `FORMAL_REFERENCE_AXF_SHA256` | `SOURCE_DATE_EPOCH`-pinned build; load-bearing formal measurement identity |

The qualification AXF was not wrong. It was valid to prove executability and
unusable as a byte-reproduction identity.

## Formal artifact identity

```
formal artifact identity =
    pinned source closure          (MLEK b2c0bb2, 0 tracked mods, 9 pinned deps)
  + pinned toolchain               (arm-none-eabi-gcc 15.2.1)
  + pinned SOURCE_DATE_EPOCH       (1776763519, from the commit)
  + pinned deterministic path      (/tmp/xq/<cell_id>/build-a1)
  + pinned build arguments
```

The canonical build path is part of the contract. No `-ffile-prefix-map` or other
normalization is introduced. If a path change alters the AXF hash, the hard stop
stands — it is not waived as harmless.

## Representative A/B determinism gate — 3/3 PASS

Run before re-baselining, so that "the epoch worked on one cell" is not
generalized to every build path.

| representative | vela A=B | gen `.cc` body A=B | AXF A=B | stamp = epoch | vela = qualification |
| --- | --- | --- | --- | --- | --- |
| `rnnoise / SSE-300 / u55-32` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rnnoise / SSE-300 / u65-256` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rnnoise / SSE-320 / u85-128` | ✅ | ✅ | ✅ | ✅ | ✅ |

The embedded literal was checked, not just the hash:

```
Version %s Build date: Apr 21 2026 @ 09:25:19
```

matching the pinned epoch exactly — which rules out the silent failure where the
variable is recorded but never reaches the compiler.

## A second embedded timestamp — open, needs a ruling

The gate's first run failed on the generated model `.cc`, for a **different**
reason than the AXF, and `SOURCE_DATE_EPOCH` does not govern it:

```
 * Original file:   rnnoise_INT8_vela.tflite * Date:  2026-08-24 18:52:45.594940
```

MLEK's generator stamps wall-clock time, at microsecond resolution, into a
leading **comment**. Two generations differ by exactly that one line.

The consequence is bounded and measurable: the comment does not reach the
binary. In the same A/B runs the `.cc` files differed while the **AXF hashes were
identical**. The model byte array is unchanged.

So the contract line

```
formal generated .cc SHA == formal-reference .cc SHA
```

is unsatisfiable as written, for the same class of reason as the AXF was —
except that here the difference provably cannot affect the executed artifact.

**Not decided unilaterally.** The re-baseline records **both**:

| field | meaning |
| --- | --- |
| `formal_generated_cc_sha256` | raw hash, including the generated comment |
| `formal_generated_cc_body_sha256` | hash of the content after the leading comment |

Either ruling can be applied without re-running anything.

Recommendation: drop the raw `.cc` hash from the load-bearing chain and keep the
body hash as the model-artifact binding. The `.cc` is an intermediate; the AXF is
what executes, it is now exactly reproducible, and it is byte-identical across
`.cc` files that differ only in that comment. Patching the generator is the other
option, and it would break the stock-tree contract.
