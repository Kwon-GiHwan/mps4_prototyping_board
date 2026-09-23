import sys, unittest, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_pmu_events as g
# Real shapes from the Tier B objdump: immediate-offset calls (base runner) and the
# register-offset loop calls that only the EVENTS edits produce.
OBJ = """
310019f0:	f241 1084 	movw	r0, #4484	@ 0x1184
310019f4:	f7ff ffc6 	bl	31000984 <pmu_reg_write>
31001a36:	9b0b      	ldr	r3, [sp, #44]	@ 0x2c
31001a38:	1918      	adds	r0, r3, r4
31001a3a:	f854 1f04 	ldr.w	r1, [r4, #4]!
31001a3e:	f7ff ffa1 	bl	31000984 <pmu_reg_write>
31001b00:	1918      	adds	r0, r3, r4
31001b04:	f7ff ff30 	bl	3100096c <pmu_reg_read>
31001c00: .word 0x504d4556
"""
NM = "31000000 T main\n31000700 T apU85Conv_TEST\n3100096c t pmu_reg_read\n31000984 t pmu_reg_write\n"
GEN = "#define INSTRUMENTATION_EVENTS    2U\n if (count != 0U && mode != INSTRUMENTATION_EVENTS) {\n"
BID = 0x504D4556


def without_loop(callee):
    return "\n".join(l for l in OBJ.split("\n") if not (("adds" in l) or (callee in l and "31001" in l)))


CASES = {
    "RULE_INFERENCE_LINKED": (OBJ, NM.replace("apU85Conv_TEST", "other"), GEN, BID),
    # store loop lost its register add (offset became an immediate)
    "RULE_PMEVTYPER_LOOP_STORE": (OBJ.replace("31001a38:\t1918      \tadds\tr0, r3, r4", "31001a38:\tf641 3080 \tmovw\tr0, #4992"), NM, GEN, BID),
    # read loop lost its register add; the write loop's add must NOT be borrowed across the bl
    "RULE_PMEVCNTR_LOOP_LOAD": (OBJ.replace("31001b00:\t1918      \tadds\tr0, r3, r4\n", ""), NM, GEN, BID),
    "RULE_BUILD_ID": (OBJ, NM, GEN, 0x45565357),
    "RULE_MAIN_PRESENT": (OBJ, NM.replace("T main", "T nomain"), GEN, BID),
    "RULE_GEN_MODE2": (OBJ, NM, GEN.replace("&& mode != INSTRUMENTATION_EVENTS", ""), BID),
}


class T(unittest.TestCase):
    def test_green(self): self.assertTrue(g.check(OBJ, NM, GEN, BID))

    def test_immediate_offset_alone_is_not_programming(self):
        # Only base-runner-style calls (movw r0,#imm ; bl) -> the store rule must trip.
        base_only = "\n".join(l for l in OBJ.split("\n") if "31001a" not in l and "31001b" not in l)
        with self.assertRaises(g.GateFail) as cm: g.check(base_only, NM, GEN, BID)
        self.assertEqual(cm.exception.rule, "RULE_PMEVTYPER_LOOP_STORE")

    def test_each_rule(self):
        tripped = set()
        for rule, args in CASES.items():
            with self.subTest(rule=rule):
                with self.assertRaises(g.GateFail) as cm: g.check(*args)
                self.assertEqual(cm.exception.rule, rule); tripped.add(cm.exception.rule)
        self.assertEqual(tripped, set(g.RULES))


if __name__ == "__main__":
    unittest.main()
