# MPS4 FI101 — Ethos-U85 PMU measurement

Measures Arm Ethos-U85 (1024 MAC) PMU counters on the MPS4 FI101 board with a custom runner (Arm selftest
`test_u85` path + Vela workload blobs) and compares with stock MLEK on the same board.

**Measurement condition that must always be fixed and stated: the NPU timing-adapter state** (see `CLAUDE.md`).

```
host/        lib/ (PMWL format, profile, parser, protocol), container/ (packer), board/ (driver), analysis/ (gate, OFM compare), tests/
firmware/    our sources on Arm's FI101 selftest tree (/work/selftest): common/, runner/, study/, gate/, vendor/
board/       board-host scripts (~/evsweep): deploy / restore / postflight / inspect / run_campaign, MLEK image deploy
config/      measurement profiles (mlek_baseline 35 RUNs, mlek_r10 10 RUNs), PMU event sets, blob manifests
docs/        reference/ (event lists, PMU reference, MLEK board values), specs/mlek-baseline.md (contract in force)
evidence/    stage0 (mlek_baseline*), stage1/, stage2a/, x1_mlek_models/, mobilenet_ofm/, runner_gap/; ta_ab/, tools_check/ as summaries
results/     reading copies: npu_utilization_mps4/ (board), npu_utilization_fvp/ (FVP)
environment/ board card config, build environment, host setup
```

Tests: `sh test.sh`. Sync to board host / container: `sh sync.sh board|container|check`. Pipeline and rules: `CLAUDE.md`. Earlier history: branch `refactor/unified-mlek-campaigns`.
