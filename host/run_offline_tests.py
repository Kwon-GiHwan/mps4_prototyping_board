#!/usr/bin/env python3
"""Run the reviewed offline baseline without discovering or importing board tests.

Usage: python3 host/run_offline_tests.py (also works outside the repository).
This is the reviewed refactoring baseline, not the complete repository suite.
Each unit retains its original unittest or standalone-script entry point.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
UNITTEST_MODULES = (
    "host.tests.s5_only.test_analysis",
    "host.tests.s5_only.test_canonical_elf",
    "host.tests.s5_only.test_collector",
    "host.tests.s5_only.test_comparison_mode",
    "host.tests.s5_only.test_contract",
    "host.tests.s5_only.test_deployment",
    "host.tests.s5_only.test_inheritance",
    "host.tests.s5_only.test_normalize",
    "host.tests.s5_only.test_preflight",
    "host.tests.s5_only.test_protocol",
    "host.tests.completion_visibility.test_protocol",
    "host.tests.completion_visibility.test_collector",
    "host.tests.completion_visibility.test_analysis",
    "host.tests.completion_visibility.test_preflight",
    "host.tests.completion_visibility.test_requirements",
    "host.tests.completion_visibility.test_runner",
    "host.tests.test_versioned_experiments",
    "host.tests.interval.test_stats",
    "host.tests.interval.test_archive",
    "host.tests.test_experiment_exchange",
    "firmware.build_tools.test_write_completion_manifest",
)
SCRIPT_TESTS = (
    "host/tests/interval/test_v9.py",
    "host/tests/interval/test_v10.py",
    "host/tests/interval/test_v11a.py",
    "host/tests/completion_poll/test_v12.py",
    "host/tests/completion_poll/test_v13.py",
    "host/tests/test_proto_unit.py",
    "host/tests/test_abi_unit.py",
    "host/tests/test_pmu_abi_unit.py",
    "host/tests/test_pmu_qual_unit.py",
    "host/tests/test_pmu_cfg_unit.py",
    "host/tests/test_pmu_diag_unit.py",
    "host/tests/test_harness_policy.py",
    "firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py",
)
TEST_TIMEOUT_SECONDS = 90


def main() -> int:
    commands = [
        (name, [sys.executable, "-u", "-m", "unittest", name])
        for name in UNITTEST_MODULES
    ] + [
        (name, [sys.executable, "-u", name])
        for name in SCRIPT_TESTS
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix="mps4-offline-cache-") as cache:
        env = dict(
            os.environ,
            PYTHONPATH=str(REPO_ROOT / "host"),
            PYTHONPYCACHEPREFIX=cache,
        )
        for name, command in commands:
            print(f"\nRunning {name}", flush=True)
            try:
                completed = subprocess.run(
                    command,
                    cwd=REPO_ROOT,
                    env=env,
                    timeout=TEST_TIMEOUT_SECONDS,
                )
                status = "PASS" if completed.returncode == 0 else "FAIL"
                detail = f"exit {completed.returncode}"
            except subprocess.TimeoutExpired:
                status, detail = "FAIL", f"timeout after {TEST_TIMEOUT_SECONDS}s"
            except OSError as exc:
                status, detail = "FAIL", f"could not start: {exc}"
            results.append((name, status, detail))

    print("\nOffline baseline results (execution units, not test cases):", flush=True)
    for name, status, detail in results:
        print(f"{status} {name}: {detail}", flush=True)
    failed = sum(status == "FAIL" for _, status, _ in results)
    print(f"{len(results) - failed} passed, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
