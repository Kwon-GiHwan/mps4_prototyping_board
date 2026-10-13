# Platform role audit — SSE-300 / 310 / 315 / 320

Priority review item. Audited against the frozen X0 comparability matrix, the
frozen timing-adapter audit, and every manuscript location where more than one
Corstone variant appears.

## Intended roles (from frozen evidence)

| platform | NPU | TA | role |
| --- | --- | --- | --- |
| SSE-300 | U55, U65 | `TA_ON` | primary memory-aware simulated substrate |
| SSE-310 | U55, U65 | `TA_OFF` | diagnostic / platform-sensitivity control |
| SSE-315 | U65 | `TA_OFF` | U65-specific diagnostic reference substrate |
| SSE-320 | U85 | `TA_ON` | primary U85 substrate and board-related anchor |

## What the manuscript does correctly

- §3.1 states the TA split from build-configuration authority and reduces the
  benchmarking-valid set to 11 of 19 configurations, with the 56 TA-OFF cells
  explicitly "capability and diagnostic evidence only".
- §3.7 adds the missing role note for the validation study: TA-OFF platforms
  enter as *validation subjects for metric behaviour, not sources of
  performance figures*, and are excluded from the Section 4 performance
  analysis.
- §8.1 preserves the ~4× byte-identical-program observation as a **methodology
  warning, not a performance comparison**, and records the retracted
  "same NPU across generations" isolation claim.
- §8.2 forbids absolute cross-generation comparison (FM skew + configuration).
- §4.6 keeps CLASS A and CLASS B separate and never pools them.
- No sentence anywhere implies "later Corstone number = better", raw-cycle
  comparability, TA_OFF ≡ memory-aware platform, SSE-315 as the uniquely
  correct U65 substrate, or SSE-310/315 as silicon-performance references.
  Scanned every multi-variant location; zero hits.

## Finding — the roles are never stated in one place (MAJOR, TEXT_ONLY)

The information above is distributed across §3.1, §3.7, §8.1 and §8.2. A
reader who reaches §4 without having assembled it can still read "19 simulated
configurations" as one comparable series, because:

1. §3.1 lists all 19 configurations in a single sentence before the TA caveat
   arrives;
2. Section 4's title, "Cross-generation simulated characterization", implies a
   platform series;
3. no table in the paper maps platform → NPU → TA → role, although both the
   TA state and the role are load-bearing for every comparison in §4 and §4.6.

**Required correction**: add one compact role table (the table at the top of
this file, or equivalent) in §3.1, and one sentence distinguishing *primary
measurement substrate* from *diagnostic/robustness substrate*. Text only; the
underlying evidence already exists in X0.

## Secondary finding — SSE-300 and SSE-320 are the only two benchmarking-valid substrates and they still differ (MODERATE, TEXT_ONLY)

The 74-cell formal sweep spans SSE-300 (U55/U65) and SSE-320 (U85), which are
both `TA_ON` but differ in Fast Models version (11.22.35 vs 11.27.25) and
subsystem. §8.2 covers this in Limitations, but Section 4 presents the two
sides together without restating it locally. One in-place reminder in §4.5
would prevent a reader from treating the sweep as one homogeneous series.
