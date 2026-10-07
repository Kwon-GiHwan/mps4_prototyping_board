F = "test_pmu_board.py"
s = open(F).read()
old = '''check("sample valid, cycle valid, no overflow",
      q["pmu_sample_valid"] == 1 and q["npu_pmu_cycle_valid"] == 1
      and q["npu_pmu_cycle_overflow"] == 0,
      "retries=%d" % q["npu_pmu_cycle_read_retry_count"])'''
new = '''check("cycle counter ARMED (PMCNTENSET readback)", q["cycle_counter_armed"] == 1)
check("global enable VERIFIED (PMCR readback)",
      q["cycle_global_enable_verified"] == 1)
check("stable read, progress observed, no overflow",
      q["cycle_read_stable"] == 1 and q["cycle_progress_observed"] == 1
      and q["npu_pmu_cycle_overflow"] == 0,
      "retries=%d" % q["npu_pmu_cycle_read_retry_count"])
check("sample valid and cycle valid",
      q["pmu_sample_valid"] == 1 and q["npu_pmu_cycle_valid"] == 1)'''
assert s.count(old) == 1
s = s.replace(old, new)

old2 = '''    if not (d["npu_pmu_cycle_valid"] == 1 and d["npu_pmu_cycle_overflow"] == 0
            and cc == GOLDEN and rc == 0):'''
new2 = '''    if not (d["npu_pmu_cycle_valid"] == 1 and d["npu_pmu_cycle_overflow"] == 0
            and d["cycle_counter_armed"] == 1
            and d["cycle_global_enable_verified"] == 1
            and d["cycle_progress_observed"] == 1
            and cc == GOLDEN and rc == 0):'''
assert s.count(old2) == 1
s = s.replace(old2, new2)
open(F, "w").write(s)
print("board test: armed/enabled/progress asserted")
