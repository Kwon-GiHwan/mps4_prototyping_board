# MPS4 FI101 — Ethos-U85 PMU measurement

Measures Arm Ethos-U85 (1024 MAC) PMU counters on the MPS4 FI101 board with a custom runner (vendor
`test_u85` + Vela workload blobs) and compares with stock MLEK on the same board.

**Measurement condition that must always be fixed and stated: the NPU timing-adapter state** (see `CLAUDE.md`).

```
host/        PMWL format, packer, board driver, parser, baseline gate, OFM comparison (+ tests)
firmware/    mirror of the container build tree subset (/work/selftest): patchers, gate, runner source
board/       board-host scripts (~/evsweep): deploy / restore / postflight / inspect / run_campaign, MLEK image deploy
config/      stage-0 profile, PMU event set, blob manifests
docs/        reference/ (event lists, PMU reference, MLEK board values), specs/mlek-baseline.md (contract in force)
evidence/    mlek_baseline(_a1)/, mobilenet_ofm/, runner_gap/; ta_ab/ and tools_check/ as summaries
environment/ board card config, build environment, host setup
```

Tests: `sh test.sh`. Sync to board host / container: `sh sync.sh board|container|check`. Pipeline and rules: `CLAUDE.md`. Earlier history: branch `refactor/unified-mlek-campaigns`.
