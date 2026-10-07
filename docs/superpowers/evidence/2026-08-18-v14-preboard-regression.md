# V14 pre-board regression matrix

Run at `76511c6` plus the manifest self-hash, against the container toolchain
(`arm-none-eabi-gcc 15.2.1`) whose staged files were SHA-identical on the local
host, the remote host and inside the container.

## V14 suites

| suite | result |
|---|---|
| `test_check_pmu_completion_visibility_v14.py` | passed=1128 failed=0 |
| `test_makefile_pmu_completion_visibility_v14.py` | passed=115 failed=0 |
| `host.tests.test_compare_declared_builds` | 39 tests, OK |
| `host.tests.test_pmu_completion_visibility_v14` | 42 tests, OK |
| `host.tests.test_collect_pmu_completion_visibility_v14` | 17 tests, OK |
| `host.tests.test_analyze_pmu_completion_visibility_v14` | 18 tests, OK |

`py_compile` clean over the generator, the gate, the parser, the collector and
the analyzer.

## Retained V8-V13 / CFG / DIAG suites

| suite | result |
|---|---|
| `test_check_pmu_qual.py` | exit 0 |
| `test_check_pmu_interval_v9/v10/v11a.py` | exit 0 |
| `test_check_pmu_completion_poll_v12.py` | exit 0 |
| `test_check_pmu_cfg.py` | exit 0 |
| `host.tests.test_pmu_qual_unit` | 281 passed, 0 failed |
| `host.tests.test_pmu_interval_v9_unit` | passed=49 failed=0 |
| `host.tests.test_pmu_interval_v10_unit` | passed=52 failed=0 |
| `host.tests.test_pmu_interval_v11a_unit` | passed=53 failed=0 |
| `host.tests.test_pmu_completion_poll_count_v13_unit` | 62 / 62 |
| `host.tests.test_pmu_cfg_unit` | 274 passed, 0 failed |
| `host.tests.test_pmu_cfg_analyzer_unit` | 108 passed, 0 failed |
| `host.tests.test_pmu_diag_unit` | 159 passed, 0 failed |

### Two suites that need their invocation stated

`test_pmu_abi_unit`, `test_abi_unit` and `test_proto_unit` import
`runner_proto` rather than `host.runner_proto`, so they pass under
`PYTHONPATH=host` and fail under `python3 -m unittest host.tests.…`. This is
not a V14 regression: it reproduces identically at `efe7402`, before any of
this work.

### One pre-existing failure, not a regression

`test_check_pmu_completion_poll_count_v13.py` reports `passed=306 failed=4`.
All four failures demand probe artifacts under
`/tmp/v13-arm-loop-probe-20260815T073000Z/`, a scratch directory from the V13
session that `/tmp` no longer holds. The V13 test file and both frozen V13/V12
checkers are byte-identical to `efe7402`.

Worth stating rather than filing away: V13's regression suite is not
reproducible on a clean machine. Four of its checks are anchored to a path in
`/tmp`, so they pass only on the machine that produced them and only until it
is rebooted.

## ARM builds

Six clean builds -- Q, QS, SQ, twice, at one build path so determinism is a
claim about the compiler and not about path strings:

- every build reports `REAL_ELF PASS`
- `compare_declared_builds` reports `mismatches=[]` over 16 declared artifacts
  per variant
- all three manifests replay as `MANIFEST PASS` with 16 artifacts each
- the campaign check reports `READ_ORDER EQUIVALENT`

## Not covered here

The board. Chunk 6 begins after an explicit GO and nothing in this matrix
touches SD, UART or the target.
