F = "runner_proto.py"
s = open(F).read()

old_attach = """    # Absent, not zero: an image without the PMU block must be distinguishable
    # from one that measured zeros.
    m.pmu = (decode_pmu_block(body[RME_KNOWN_FIELDS_V1:])
             if total_words >= RME_PMU_TOTAL_WORDS else None)
    return m"""
assert s.count(old_attach) == 1
s = s.replace(old_attach, "    return m")

assert s.count("    m = Measurement(\n") == 1
s = s.replace("    m = Measurement(\n", "    m = Measurement(\n")

old_ctor = """        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
    )"""
new_ctor = """        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
        # Absent, not zero: an image without the PMU block must stay
        # distinguishable from one that measured zeros.
        pmu=(decode_pmu_block(body[RME_KNOWN_FIELDS_V1:])
             if total_words >= RME_PMU_TOTAL_WORDS else None),
    )"""
assert s.count(old_ctor) == 1
s = s.replace(old_ctor, new_ctor)

import re
m = re.search(r"class Measurement:\n(.*?)\n\n", s, re.S)
assert m, "Measurement dataclass not found"
block = m.group(1)
assert "pmu" not in block
s = s.replace(block, block + "\n    pmu: dict | None = None", 1)

open(F, "w").write(s)
print("pmu is now a dataclass field")
