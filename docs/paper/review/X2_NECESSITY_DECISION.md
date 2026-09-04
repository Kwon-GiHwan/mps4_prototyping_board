# X2 necessity decision

**Verdict: `X2_NOT_NEEDED`** (conditional on the RQ1 rewording described
below, which is a text edit, not an experiment).

## The question

Does the paper's main conclusion materially depend on a controlled
same-platform U55-versus-U65 comparison that has not been executed?

## Audit of the dependency

Every cross-generation statement in the manuscript was located and read.

| location | statement | depends on a controlled U55/U65 contrast? |
| --- | --- | --- |
| §4.5 (RQ1 statement) | generations differ in normalized scaling, ordering, deployability, **not** in comparable absolute cycles; "U85 is faster than U55" explicitly *not established* | no |
| §8.2 | absolute cross-generation comparison unsupportable | no |
| §8.3 | the available SSE-300 U55@256 vs U65@256 pair is a **system-level configuration comparison only** (memory mode differs by NPU) | no — already scoped down |
| §6 (mechanism) | entirely within U85; the ublock single-factor account is explicitly **retired** | no |
| §7 Discussion | ordering is the portable quantity; MAC upgrades must be validated per workload | no |
| contributions | characterization, board validation, U85 mechanism, methodology | no |

Searches for "core replication is better/superior", "U65 scales better
because it replicates cores", "U85 non-monotonicity is caused by block
enlargement" return **zero** instances. The only occurrence of "ublock
enlargement causes the regression" is the framing the paper explicitly
retires.

## Why X2 would not change what the paper may conclude

X2 would provide a same-Corstone U55-versus-U65 contrast at MAC 256. Even
with it:

- absolute cross-generation comparison would remain refused (FM skew, and the
  memory mode still differs by NPU on this stack — §8.3);
- no U65↔U85 controlled pair would exist, so the generation the mechanism
  study is about would still be connected only structurally;
- the paper's conclusions are ordinal/structural and are already supported by
  the frozen sweep plus the X1/X3 robustness evidence.

The single place where the paper currently *promises* more than it delivers is
the wording of **RQ1**, which asks how performance characteristics change
across generations while the answer is restricted to structural and
deployability characteristics. That gap is closed by rewording the question to
match the evidence (`TEXT_ONLY`), not by running X2.

## When X2 would become necessary

If a future revision wants to claim an architecture-level contrast — for
example that one MAC-organization strategy scales better than another — then a
controlled same-platform pair becomes load-bearing and the classification would
move to `X2_REQUIRED`. Nothing in the current manuscript makes such a claim.

Classification per the manager's rules: architecture-only causality is not
claimed, cross-generation conclusions are explicitly structural, and the
X1/X3 robustness evidence is sufficient for the manuscript's actual claim →
**`X2_NOT_NEEDED`**. Its value would be `X2_OPTIONAL_STRENGTHENING` at most,
and only for a discussion paragraph that does not currently exist.
