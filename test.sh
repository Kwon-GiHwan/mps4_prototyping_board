#!/bin/sh
# Every test module, one process each; exits non-zero if any fails.
cd "$(dirname "$0")" || exit 2
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
fail=0
run() {  # run <label> <dir> <command...>
  label=$1; dir=$2; shift 2
  out=$(cd "$dir" && "$@" 2>&1); rc=$?
  printf '%-45s rc=%s  %s\n' "$label" "$rc" "$(echo "$out" | tail -1)"
  [ $rc -eq 0 ] || fail=1
}
for m in test_pmwl test_pmwl_firmware_contract test_reference_results test_pmu_events_parse test_pack_vela_workload test_baseline_gate test_ofm_compare; do
  run "host/$m" . python3 -B -m unittest host.tests.$m
done
run "host/test_proto_unit" . python3 -B host/tests/test_proto_unit.py
run "firmware/patches" firmware/patches python3 -B -m unittest test_patch_pmu_events_source test_patch_u85_vendor_timeout
run "firmware/Selftest_pmu_events" firmware/Selftest_pmu_events python3 -B -m unittest test_check_pmu_events
[ $fail -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
