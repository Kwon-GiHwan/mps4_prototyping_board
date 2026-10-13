# MPS4 FI101 — Ethos-U85 PMU measurement

Measures Arm Ethos-U85 (1024 MAC) PMU counters on the MPS4 FI101 board with a custom runner (vendor
`test_u85` + Vela workload blobs) and compares with stock MLEK on the same board.

**Measurement condition that must always be fixed and stated: the NPU timing-adapter state** (see `CLAUDE.md`).

```
host/        packer, workload metadata, board driver, parser, metrics, A/B outcome (+ tests)
firmware/    mirror of the container build tree subset (/work/selftest): patchers, gate, runner source
board/       board-host scripts (~/evsweep): deploy / restore / postflight / inspect / run_campaign
config/      workload metadata, PMU event set
docs/        reference/ (event lists, PMU reference, MLEK board values), specs/ (contracts in force)
evidence/    ta_ab/ (timing-adapter finding + MLEK-TA baseline arm), runner_gap/
environment/ board card config, build environment, host setup
```

Tests: `sh test.sh`. Sync to board host / container: `sh sync.sh board|container|check`. Pipeline and rules: `CLAUDE.md`. Earlier history: branch `refactor/unified-mlek-campaigns`.
