P = "Selftest_pmu/gen_npu_pmu_regs.py"
s = open(P).read()

old = '''def _bitfields(text, struct_name):
    """Ordered (name, shift, width) for one register's C bitfield struct."""'''
new = '''def _bitfields(text, struct_name, span=32):
    """Ordered (name, shift, width) for one register's C bitfield struct.

    `span` is the register's width in bits. It is 32 for the single-word
    control registers, but PMCCNTR is a TWO-word register (CYCLE_CNT_LO 32 +
    CYCLE_CNT_HI 16), so capping at 32 there silently drops the HI field.
    """'''
assert s.count(old) == 1
s = s.replace(old, new)

old2 = """        if shift >= 32:
            break"""
new2 = """        if shift >= span:
            break"""
assert s.count(old2) == 1
s = s.replace(old2, new2)

old3 = '    cc = _bitfields(text, "pmccntr_r")'
new3 = '    cc = _bitfields(text, "pmccntr_r", span=64)'
assert s.count(old3) == 1
s = s.replace(old3, new3)

open(P, "w").write(s)
print("span parameterised")
