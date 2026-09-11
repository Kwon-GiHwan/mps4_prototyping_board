F = "runner_proto.py"
s = open(F).read()
assert s.count("RME_PMU_FIELDS_V1 = 51") == 1
s = s.replace("RME_PMU_FIELDS_V1 = 51", "RME_PMU_FIELDS_V1 = 55")
old = '''    "pmu_mmio_write_count_delta", "pmcr_at_disable",
]'''
new = '''    "pmu_mmio_write_count_delta", "pmcr_at_disable",
    # Independent evidence. "read cleanly" is not "was armed" is not "was
    # globally enabled" is not "actually counted" -- milestone 1 shipped a
    # build where the first was true and the rest were not.
    "cycle_counter_armed", "cycle_global_enable_verified",
    "cycle_read_stable", "cycle_progress_observed",
]'''
assert s.count(old) == 1
s = s.replace(old, new)
open(F, "w").write(s)
print("host parser: 55 PMU fields")
