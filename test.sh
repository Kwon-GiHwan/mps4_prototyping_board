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
for m in test_pmwl test_cms test_pmwl_firmware_contract test_reference_results test_pmu_events_parse test_run_pmu_events test_fi101_s013 test_s0_3_ta test_s0_3_clk test_s2_probe test_s2_mask_confirm test_s2_groups test_cms_timeline test_s2b3_existing test_s2b3_select test_s2b3_windows test_equiv_existing test_equiv_a test_mlek_counters test_equiv_c test_drwl test_driver_runner_contract test_driver_runner_sim test_record_v2 test_driver_p3 test_driver_reval test_var_w2l_vww4 test_qread_trace test_qread_timeline test_qread_pilot test_qread_checked test_qread_op_pilot test_stage4 test_stage4p test_placement test_stage4c1 test_stage4c2 test_stage4c2b test_stage4k test_stage4ao test_stage4aoe test_stage4wd test_stage6 test_stage6b test_stage6b_revision_a test_stage6b_amendment_b test_stage6bb test_stage6br test_stage6be1 test_stage6be1r test_stage6m test_stage6be2a test_stage6be2b test_stage6be2c test_stage6be2d test_stage6be2ea test_identity_placement test_stage5 test_ad64k_static test_sudo_session test_vela_block_fill test_pack_vela_workload test_baseline_gate test_ofm_compare test_mlek_golden test_stage1 test_stage2a; do
  run "host/$m" . python3 -B -m unittest host.tests.$m
done
run "host/test_proto_unit" . python3 -B host/tests/test_proto_unit.py
run "firmware/runner" firmware/runner python3 -B -m unittest test_runner_sources
run "firmware/gate" firmware/gate python3 -B -m unittest test_check_runner
run "firmware/vendor" firmware/vendor python3 -B -m unittest test_patch_u85_vendor_timeout test_patch_u85_diag
[ $fail -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
