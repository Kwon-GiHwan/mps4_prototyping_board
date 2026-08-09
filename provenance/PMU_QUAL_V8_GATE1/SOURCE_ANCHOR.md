# PMU qualification schema-v8 Gate 1 source anchor

Recorded: 2026-08-10 (Asia/Seoul)

This anchor freezes the source and artifact identity used for the completed
schema-v8 H-PRINTF qualification and 30-sample Gate 1 characterization. It is
a provenance checkpoint before the separate PMCCNTR_CFG A/B/C experiment.

## Scope and boundaries

- Git branch: `main`
- Base commit before anchoring: `7827e5caa39d2802e461e698e44480268f61e71d`
- Worktree state at capture: dirty, with one tracked append-only change and 18
  untracked PMU files. The canonical file list is explicit in
  `SOURCE_ANCHOR.sha256`; it is not derived from Git because required Arm
  linker inputs are intentionally gitignored.
- Container image:
  `fpga-simulator@sha256:85731c8b4754eb57919e735009f9d1d2938d86348424206fe26feb44d9ecd4a1`
- Complete container worktree archive:
  `/home/gihwan/mps4/PMU_V8_PROVENANCE_20260809T160300Z/selftest-v8-complete.tgz`
- Archive SHA-256:
  `56d56e8a39bf8b488dd3f1c018ee27b6a03ac09cd42292d171bc79456240b41a`
- Archive members: `4090`

The earlier `build-env/selftest-worktree.tgz` predates schema v8 and contains
no `pmu_diag` or `pmu_qual` inputs. It remains a valid earlier baseline but is
not a schema-v8 recovery source. The complete archive above closes that gap.

## Qualified artifact identity

| Mode | Artifact | SHA-256 |
|---|---|---|
| Q0 | `APP.BIN` | `727563fd252f574e19145b6d2beac388e4eed5205cf5f7cd92ff94f88a8e111d` |
| Q0 | `VECTORS.BIN` | `eff245cd435a34c50c5ac2cd834a89c9e9114cef0131fcc5a7fb0b0ebc562309` |
| Q0 | `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| Q0 | `runner_pmu_qual.elf` | `a52f929b81d9c0661f0ede179a6fb8a9176435ab6709d453a577582268701288` |
| Q0 | `runner_pmu_qual.map` | `ee9fba81e9cbd78e7309f5f9fae01fc5a3c0f1c9ff074181f28686a5e40dc556` |
| Q0 | `pmu_qual_manifest.json` | `6d98025153fef18cd96e4962da5acc54848ccef6d08c497952fb78e58e5b4687` |
| Q1 | `APP.BIN` | `dc66915a26f95e983b28b160d9acdec48e3091d989f02636b8399c97865754cb` |
| Q1 | `VECTORS.BIN` | `5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9` |
| Q1 | `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| Q1 | `runner_pmu_qual.elf` | `2eba134593d5481141b651d5867c19554100c7357051aa2a87544f35b5875eb6` |
| Q1 | `runner_pmu_qual.map` | `8449fb6278f33c749a3614d98e145e49425a9e50dfe5a92ff7c7a4015423e7f2` |
| Q1 | `pmu_qual_manifest.json` | `e2c1ebe0c140bb144032351dd81ddfd031e527ec37ad859663cef05cdad72f33` |

ELF and map hashes are recorded as qualified-image identity. Only the three
BIN files are used as path-independent clean-rebuild determinism gates because
the debug ELF embeds `/work/selftest` and the map contains build-directory
paths.

## Gate 1 evidence link

Evidence root: `/home/gihwan/mps4/PMU_STABILITY_V8_20260809T130131Z`

| Evidence file | SHA-256 |
|---|---|
| `CAMPAIGN_CONTRACT.md` | `70db00aaaac1d06e58a90ac1c574276debaa91f86c98a896570f0dc9479940c3` |
| `samples.tsv` | `a259ecd7d3c0b251aa24a3989185cfdcfd1aabbe24aaaa5c66851cc8699587c7` |
| `STABILITY_CHARACTERIZATION.txt` | `8ea489600b375555eece03f10bd9437028e696564e543f87a4c0ca40261b25ad` |
| `LOCALIZATION_FINDING.txt` | `95af0ff7f1479abf4d8c326810b30ed3dd20fbe1f1fd7c3d59cfd7f2d2d03765` |

This sidecar does not modify either frozen evidence root. The values remain
qualification data only: `npu_pmu_window_cycles` is not latency, `T_npu`, a
performance baseline, Production GO, Gate 7, or MLEK data. The empirical
`+514` localization offset belongs only to the byte-exact Q1 image above.

## Build-metadata finding

The schema-v8 Makefiles contain no Git command, dirty-state substitution,
timestamp macro, or source-date input. Q0/Q1 build IDs are fixed literals
passed as `RUNNER_FIRMWARE_BUILD_ID`, and `/work/selftest` is not a Git
repository. A local commit or tag is therefore provenance metadata, not a
firmware input. This static conclusion is still checked empirically by
comparing post-anchor rebuild BIN hashes against the table above.

## Dirty-tree clean rebuild verification

Before the local commit, both modes were rebuilt from `clean` in the anchored
container at the same `/work/selftest` path:

```text
make -f Makefile.pmu_qual QUAL=Q0 clean bins check manifest hashes
make -f Makefile.pmu_qual QUAL=Q1 clean bins check manifest hashes
```

Every static gate passed. All six recorded files per mode (`APP.BIN`,
`VECTORS.BIN`, `DDR.BIN`, ELF, map, and manifest) were byte-identical to the
qualified artifacts above. The rebuild evidence is append-only under the
provenance root:

- `Q0_DIRTY_REBUILD.log`:
  `aaea29faa8af388d6fa096f9845ce9387fa5c34bfc6f10eb96679d163ed07bcd`
- `Q1_DIRTY_REBUILD.log`:
  `1ca026ab840951232a9d3977c8662e98464849e294f8e07a925a439b1912449e`
- `DIRTY_REBUILD_EVIDENCE.sha256` verifies both logs and both rebuilt artifact
  manifests.
