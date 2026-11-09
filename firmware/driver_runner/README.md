# Driver Runner (Ethos-U core driver, MLEK platform)

Design: `docs/plan/driver_runner_plan.md`. An MLEK out-of-tree use case: the image is built by MLEK `b2c0bb2`'s own cmake with
the stock-MLEK platform options plus `-DUSE_CASES_SEARCH_DIR_LIST=<this dir>/use_case -DUSE_CASE_BUILD=pmu_runner`, so
startup, caches, TA, NPU init, driver definitions, linker and memory map are MLEK's. The MLEK tree is not modified.

`firmware/common/` (`timing.c`, `mmio.h`, `npu_pmu_regs.h`) is reused unchanged; nothing else of the legacy runner is
linked. Build: `host/container/build_driver_runner.sh`.
