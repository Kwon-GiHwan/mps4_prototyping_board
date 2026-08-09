# PMU schema v8 Q1 fixed-image stability characterization

## Scope

This campaign is Gate 1 stability characterization. It is not a performance
baseline, Production qualification, Gate 7, or MLEK research data. Production
`END_ONLY` remains frozen. Values remain `npu_pmu_window_cycles`; they are not
`T_npu` or latency.

No firmware, CFG, driver, workload, hook, or PMU ordering change is permitted.
Reuse the byte-exact schema-v8 Q1 image qualified on 2026-08-09:

| Artifact | SHA-256 |
|---|---|
| `APP.BIN` | `dc66915a26f95e983b28b160d9acdec48e3091d989f02636b8399c97865754cb` |
| `VECTORS.BIN` | `5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9` |
| `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| `pmu_qual_manifest.json` | `e2c1ebe0c140bb144032351dd81ddfd031e527ec37ad859663cef05cdad72f33` |

## Sampling contract

- Evidence root: `/home/gihwan/mps4/PMU_STABILITY_V8_20260809T130131Z`.
- Independent full boots: `19`, `20`, `21`.
- Consecutive Q1 samples per boot: `10`.
- Paths: `results/q1/boot<N>/repeat01.json` through `repeat10.json`.
- Archive one reboot log per boot and collector/analyzer stdout per sample.
- Require DDR self-test and CPUWAIT gates on every boot.
- Require all existing 38 Q1 validity terms, raw payload/reread identity, and
  the fixed artifact/manifest identity on every sample.
- Retain every sample. Never overwrite or cherry-pick.
- Stop before the next sample on an invalid term, transport/CRC/reread failure,
  or reboot-gate failure. Do not stop solely because a valid positive cycle
  value is high or low.

Each JSON already retains boot ID, run sequence, raw pre/internal snapshots,
PMCR, PMCNTENSET, PMCCNTR_CFG, cycle high/low, PMOVSSET, stable-read state,
hook counts and LR, golden-window CRC, PMU MMIO totals/deltas, CMD state, and
the raw payload hashes. Armed/global/overflow/cycle48 are losslessly derived
from those raw registers.

The fixed image records exact `npu_cmd_at_hook`, but it has no exact
`npu_status_at_hook` field. Preserve and report the surrounding
`npu_status_after_power_request` and `npu_status_after_seam` values instead.
This is a declared characterization limitation; the image must not be changed
to add a field during this campaign.

## Frozen descriptive analysis

Use Python standard-library arithmetic only.

- Overall and per-boot: minimum, maximum, median.
- MAD: median of `abs(x - median(x))`.
- Quartiles: `statistics.quantiles(x, n=4, method="inclusive")`.
- IQR: `Q3 - Q1`.
- CV: sample standard deviation divided by mean; undefined for fewer than two
  samples or a zero mean.
- Report all per-boot medians and within-boot CVs.
- Between-boot spread: maximum minus minimum of the three boot medians, their
  maximum/minimum ratio, and sample CV of the three boot medians.
- Compare each boot's first run with runs 2-10; do not discard it as warm-up.
- Report exact-value frequencies.
- Exploratory bands, fixed from the earlier nine-sample pilot only:
  `<4000`, `4000-6499`, `>=6500`.
- Print the full run-sequence table and the ordinary least-squares slope of
  cycles versus run sequence for each boot.

Do not infer Gaussianity, latency, NPU arithmetic performance, or a production
baseline from this dataset. Its purpose is to describe within-boot,
between-boot, warm-up, sequence, and possible multimodal structure before the
separate CFG single-variable experiment is designed.

## Completed result (2026-08-09)

The frozen campaign completed without a stop condition. All three fresh boots
passed DDR self-test and CPUWAIT, and all 30 records passed all 38 validity
terms with raw payload/reread identity and the fixed artifact identity intact.

| Statistic | Result |
|---|---:|
| Minimum / maximum | `3207` / `7885` |
| Median / MAD | `3300` / `93` |
| Inclusive Q1 / Q3 / IQR | `3207` / `5603.25` / `2396.25` |
| Sample CV | `0.378709` |
| Per-boot medians | `3207`, `3811.5`, `4047.5` |
| Exact floor frequency | `3207` in `15/30` samples |

`pre_cycle48` was exactly `10592` in all 30 records. The internal snapshot had
16 distinct cycle values, so the variation is entirely at the window end.
Existing timestamps further localize it without changing the frozen analysis:

```
npu_pmu_window_cycles
  = u32(hook_entry_timestamp - t_call_enter) + 514    (30/30 exact)

call enter -> hook entry    2693..7371  (span 4678)
hook body                   1193..1234  (span 41)
hook exit -> call return    7991..8038  (span 47)
```

The hook body is `1193` on the first run of each boot and `1234` on the other
27 runs; the post-hook tail is effectively uncorrelated with the cycle window.
This locates the dispersion before the pre-release hook. It does not identify
its mechanism or turn the value into NPU arithmetic performance.

Evidence files under the campaign root:

| File | SHA-256 |
|---|---|
| `CAMPAIGN_CONTRACT.md` | `70db00aaaac1d06e58a90ac1c574276debaa91f86c98a896570f0dc9479940c3` |
| `samples.tsv` | `a259ecd7d3c0b251aa24a3989185cfdcfd1aabbe24aaaa5c66851cc8699587c7` |
| `STABILITY_CHARACTERIZATION.txt` | `8ea489600b375555eece03f10bd9437028e696564e543f87a4c0ca40261b25ad` |
| `LOCALIZATION_FINDING.txt` | `95af0ff7f1479abf4d8c326810b30ed3dd20fbe1f1fd7c3d59cfd7f2d2d03765` |
| `RESTORE_DESTINATION.sha256` | `0d1fe942f9ea2c64e4c5752ed544767e0aeb4c71a5e2f818ea3d64f6c5f3f790` |

The original board image was restored after collection. Its three BIN files
match the pre-campaign backup, the restore reboot passed DDR/CPUWAIT, PING
reported IDLE with all seven protocol error counters zero, and the final state
is unmounted, USB_OFF, `/dev/sdb` absent, and all four UARTs free.

Gate 1 therefore characterizes the instability but does not qualify a stable
cycle figure. The next measurement experiment must keep this v8 seam, vendor
`TEST_CPM=1` path, workload, and PMU ordering fixed while changing only the
`PMCCNTR_CFG` case (no-write, generated START=CYCLE/STOP=NO_EVENT, explicit
zero). Production `END_ONLY` remains frozen.
