import sys, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_runner as g
# Real shapes from the runner objdump: immediate-offset calls (fixed registers) and the register-offset loop calls
# that only event-slot programming and read-back produce.
OBJ = """
310019f0:	f241 1084 	movw	r0, #4484	@ 0x1184
310019f4:	f7ff ffc6 	bl	31000984 <pmu_reg_write>
31001a36:	9b0b      	ldr	r3, [sp, #44]	@ 0x2c
31001a38:	1918      	adds	r0, r3, r4
31001a3a:	f854 1f04 	ldr.w	r1, [r4, #4]!
31001a3e:	f7ff ffa1 	bl	31000984 <pmu_reg_write>
31002828:	460c      	mov	r4, r1
3100282a:	4608      	mov	r0, r1
3100282c:	f7fe f89e 	bl	3100096c <pmu_reg_read>
31001c00: .word 0x504d574c
 8000208: .word 0x4c574d50
"""
NM = ("31000000 T main\n31000700 T apU85Conv_TEST\n3100096c T pmu_reg_read\n31000984 T pmu_reg_write\n"
      "31001200 T __wrap_printf\n31000a00 00000080 T __wrap_test_u85\n310026b8 00000014 T u85_power_ctrl_value\n")
SRC = ("#define INSTRUMENTATION_EVENTS    2U\n if (count != 0U && mode != INSTRUMENTATION_EVENTS) {\n"
       "int __wrap_printf(const char *fmt, ...)\n{\n    if (strcmp(fmt, \"Testing CPM signals\\n\") == 0) {}\n"
       '    if (strcmp(fmt, "Updating POWER_CTRL register with MAC_RAMP_VAR=%d \\n") == 0) {}\n')
BID = 0x504D574C
ELF = b"\x7fELF....Enabling AXI EXT port testing\n...."
VEND = ("#define BUSY_SLEEP_TIMEOUT 200000000 /* Tier C step 1: was 10000 */\n"
        "\t  write_reg(NPU_REG_POWER_CTRL, u85_power_ctrl_value(MAC_RAMP_VAR)); /* runner gap: hook */\n")
GOOD = (OBJ, NM, SRC, BID, ELF, VEND)


def args(**kw):
    a = dict(zip(("obj", "nm", "src", "bid", "elf", "vend"), GOOD)); a.update(kw)
    return a["obj"], a["nm"], a["src"], a["bid"], a["elf"], a["vend"]


CASES = {
    "RULE_INFERENCE_LINKED": [args(nm=NM.replace("apU85Conv_TEST", "other"))],
    # store loop lost its register add (offset became an immediate)
    "RULE_PMEVTYPER_LOOP_STORE": [args(obj=OBJ.replace("31001a38:\t1918      \tadds\tr0, r3, r4",
                                                       "31001a38:\tf641 3080 \tmovw\tr0, #4992"))],
    # read loop lost its register move: r0 now comes from an immediate right before the bl
    "RULE_PMEVCNTR_LOOP_LOAD": [args(obj=OBJ.replace("3100282a:\t4608      \tmov\tr0, r1",
                                                     "3100282a:\tf44f 5098 \tmov.w\tr0, #4864"))],
    "RULE_BUILD_ID": [args(bid=0x45565357)],
    "RULE_MAIN_PRESENT": [args(nm=NM.replace("T main", "T nomain"))],
    "RULE_MODE2": [args(src=SRC.replace("&& mode != INSTRUMENTATION_EVENTS", "")),
                   args(src=SRC.replace("INSTRUMENTATION_EVENTS    2U", "INSTRUMENTATION_EVENTS    3U"))],
    "RULE_SEAM_HOOK": [args(src=SRC.replace("Testing CPM signals", "Testing CPX signals")),
                       args(nm=NM.replace("T __wrap_printf", "T __wrap_printx"))],
    "RULE_EXT_ATTR": [args(elf=b"\x7fELF....Testing CPM signals\n....")],
    "RULE_TEST_U85_WRAP": [args(nm=NM.replace(" T __wrap_test_u85", " T __wrap_test_u86"))],
    "RULE_MODEL": [args(obj=OBJ.replace(" 8000208: .word 0x4c574d50\n", "")),
                   args(src=SRC.replace("Updating POWER_CTRL", "Updating XOWER_CTRL")),
                   args(vend=VEND.replace("200000000", "10000")),
                   # vendor copy writes POWER_CTRL directly: the knob cannot act
                   args(vend=VEND.replace("u85_power_ctrl_value(MAC_RAMP_VAR)", "MAC_RAMP_VAR")),
                   # only the weak default linked: the knob would be ignored silently
                   args(nm=NM.replace("T u85_power_ctrl_value", "W u85_power_ctrl_value"))],
}


class T(unittest.TestCase):
    def test_green(self): self.assertTrue(g.check(*GOOD))

    def test_immediate_offset_alone_is_not_programming(self):
        # Only fixed-register calls (movw r0,#imm ; bl) -> the store rule must trip.
        base_only = "\n".join(l for l in OBJ.split("\n") if "31001a" not in l and "310028" not in l)
        with self.assertRaises(g.GateFail) as cm: g.check(*args(obj=base_only))
        self.assertEqual(cm.exception.rule, "RULE_PMEVTYPER_LOOP_STORE")

    def test_each_rule(self):
        for rule, cases in CASES.items():
            for i, a in enumerate(cases):
                with self.subTest(rule=rule, case=i):
                    with self.assertRaises(g.GateFail) as cm: g.check(*a)
                    self.assertEqual(cm.exception.rule, rule)
        self.assertEqual(set(CASES), set(g.RULES))


if __name__ == "__main__":
    unittest.main()
