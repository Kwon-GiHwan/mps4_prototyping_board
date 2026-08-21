---
description: Run the V15 + V14 host test suites and report per-module counts
---

Run the host test suites from the repo root and report the result.

`pytest` does not work here — several test files call `sys.exit()` at import.
Use unittest per module, and clear stale bytecode first.

```sh
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
total=0
for f in host/tests/test_*s5_only_control.py; do
  m="host.tests.$(basename $f .py)"
  out=$(python3 -m unittest $m 2>&1)
  n=$(echo "$out" | grep '^Ran' | awk '{print $2}')
  st=$(echo "$out" | tail -1)
  total=$((total + n))
  printf '%-34s %3s %s\n' "$(basename $f .py | sed 's/_pmu_completion_s5_only_control//')" "$n" "$st"
done
echo "TOTAL V15: $total"
python3 -m unittest host.tests.test_pmu_completion_visibility_v14 2>&1 | tail -3
```

Report the counts and any failure verbatim. Do not summarise a failure as a
pass, and do not report a total without the V14 regression line.
