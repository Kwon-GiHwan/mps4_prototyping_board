---
description: Run the offline baseline and refactoring regression tests
---

Run the reviewed offline baseline from the repo root. The runner uses
explicit test modules and standalone scripts; it does not discover board tests.
It isolates bytecode in a temporary cache and reports each process exit status.

```sh
python3 host/run_offline_tests.py
python3 -B -m unittest host.tests.test_run_offline_tests host.tests.test_v15_imports
```

Inspect both exit statuses and report failures. The baseline summary counts
execution units, not test cases. V15 tests now live in `host/tests/s5_only/`;
the baseline includes all ten V15 modules and six V14 modules (including the
offline runner boundary tests) under `host/tests/completion_visibility/`.
It also runs the five standalone V9-V13 contract scripts in `host/tests/interval/`
and `host/tests/completion_poll/`, and their package/CLI regression tests. Shared archive/exchange tests and
synthetic V14/V15 manifest recipe tests are included, along with the V14 Makefile
contract script.
The runner regression intentionally launches a failing child fixture; its outer
unittest result is authoritative for that fixture. This is not the full repository
suite and does not qualify firmware builds or board behavior.
