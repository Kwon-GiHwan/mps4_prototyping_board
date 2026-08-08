F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()

DECL_COMMENT = "/* Set the first time the counters are armed. RESET_RUNNER uses it to"
i = s.find(DECL_COMMENT)
assert i != -1, "declaration comment not found"
j = s.index("static uint32_t pmu_ever_enabled;\n", i) + len("static uint32_t pmu_ever_enabled;\n")
block = s[i:j]
s = s[:i] + s[j:]

anchor = "static uint32_t pmu_hw_event_counters;\n"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + "\n" + block)

open(F, "w").write(s)
print("moved pmu_ever_enabled above its users")
