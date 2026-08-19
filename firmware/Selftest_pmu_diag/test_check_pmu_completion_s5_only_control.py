"""The S5 primary loop contract, on the generated source.

Four things must be impossible to write, and each has a fixture that tries:
a second STATUS read, a QREAD read inside the measured loop, a QSIZE read
inside it, and `irq_raised` taken from a word other than the one the deciding
test used.

The fourth is the one that would be easiest to get wrong and hardest to notice.
Reading bit1 from a fresh STATUS is a one-line change that looks like tidiness
and quietly rebuilds the second MMIO access this whole control exists to remove.

Every refusal is required to carry its own rule identifier, on the same terms
V14's thirty-six do: a fixture that trips a neighbouring rule is a failed
fixture, not a passing test.
"""

import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_pmu_completion_s5_only_control as gate  # noqa: E402


CANONICAL = """
static uint32_t v15_primary_observe(void)
{
    uint32_t status = 0U;
    uint32_t observed = 0U;
    uint32_t i;

    t_primary_entry = read_cycles();
    for (i = 1U; i <= V15_ITERATION_BOUND; ++i) {
        status = *status_reg;
        if ((status & V15_STATUS_RESET) != 0U) { result = V15_PRIMARY_RESET; break; }
        if ((status & V15_STATUS_FAULT_MASK) != 0U) { result = V15_PRIMARY_FAULT; break; }
        if ((status & V15_STATUS_CMD_END) != 0U) {
            observed = status;
            t_first_observation = read_cycles();
            result = V15_PRIMARY_SUCCESS;
            break;
        }
    }
    status_at_success = observed;
    irq_raised_at_success = (observed & V15_STATUS_IRQ_RAISED) != 0U ? 1U : 0U;
    primary_iterations = i;
    return result;
}
"""


def _mutate(old, new, source=CANONICAL):
    assert old in source, "fixture anchor missing: %r" % old
    return source.replace(old, new, 1)


# One place, so the fixtures and the rule registry cannot drift apart without a
# test noticing. Keyed by the rule each is aimed at.
FIXTURES = {
    "second_status_read": (
        "        if ((status & V15_STATUS_CMD_END) != 0U) {",
        "        if ((*status_reg & V15_STATUS_CMD_END) != 0U) {",
        "RULE_S5_ONE_STATUS_READ",
    ),
    "qread_in_loop": (
        "        status = *status_reg;",
        "        status = *status_reg;\n        cursor = *qread_reg;",
        "RULE_S5_NO_QREAD_IN_LOOP",
    ),
    "qsize_in_loop": (
        "        status = *status_reg;",
        "        status = *status_reg;\n        expected = *qsize_reg;",
        "RULE_S5_NO_QSIZE_IN_LOOP",
    ),
    "irq_from_a_fresh_read": (
        "    irq_raised_at_success = (observed & V15_STATUS_IRQ_RAISED) != 0U ? 1U : 0U;",
        "    irq_raised_at_success = (*status_reg & V15_STATUS_IRQ_RAISED) != 0U ? 1U : 0U;",
        "RULE_S5_IRQ_FROM_DECIDING_WORD",
    ),
    # The completion condition replaced outright: no bit5 exit at all.
    "completion_is_some_other_bit": (
        "        if ((status & V15_STATUS_CMD_END) != 0U) {",
        "        if ((status & V15_STATUS_IRQ_RAISED) != 0U) {",
        "RULE_S5_EXIT_IS_CMD_END",
    ),
    # And the realistic version, which the first one hides: bit5 still exits,
    # and so does the interrupt. Without this fixture the branch that refuses an
    # irq exit is never reached by any test, and deleting it changes nothing.
    "irq_added_as_a_second_exit": (
        "        if ((status & V15_STATUS_CMD_END) != 0U) {",
        "        if ((status & V15_STATUS_IRQ_RAISED) != 0U) { result = V15_PRIMARY_SUCCESS; break; }\n"
        "        if ((status & V15_STATUS_CMD_END) != 0U) {",
        "RULE_S5_EXIT_IS_CMD_END",
    ),
    "bound_is_not_the_contracts": (
        "i <= V15_ITERATION_BOUND",
        "i <= 100000U",
        "RULE_S5_ITERATION_BOUND",
    ),
}


def _refusal_rule(source):
    try:
        gate.verify_s5_primary_contract(source)
    except gate.GateError as exc:
        return gate.refusal_rule(exc)
    return None


class TheCanonicalSourceIsAccepted(unittest.TestCase):
    def test_the_canonical_loop_passes(self):
        document = gate.verify_s5_primary_contract(CANONICAL)
        self.assertEqual(document["status_reads_per_iteration"], 1)
        self.assertEqual(document["qread_reads_in_loop"], 0)
        self.assertEqual(document["qsize_reads_in_loop"], 0)
        self.assertTrue(document["irq_from_the_deciding_word"])


class TheFourThingsThatMustBeImpossible(unittest.TestCase):
    def test_a_second_status_read_in_the_loop_is_refused(self):
        source = _mutate(
            "        if ((status & V15_STATUS_CMD_END) != 0U) {",
            "        if ((*status_reg & V15_STATUS_CMD_END) != 0U) {",
        )
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_ONE_STATUS_READ)

    def test_a_qread_read_inside_the_loop_is_refused(self):
        source = _mutate(
            "        status = *status_reg;",
            "        status = *status_reg;\n        cursor = *qread_reg;",
        )
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_NO_QREAD_IN_LOOP)

    def test_a_qsize_read_inside_the_loop_is_refused(self):
        source = _mutate(
            "        status = *status_reg;",
            "        status = *status_reg;\n        expected = *qsize_reg;",
        )
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_NO_QSIZE_IN_LOOP)

    def test_irq_raised_from_a_separate_read_is_refused(self):
        # The one-line change that looks like tidiness and rebuilds the second
        # MMIO access the control exists to remove.
        source = _mutate(
            "    irq_raised_at_success = (observed & V15_STATUS_IRQ_RAISED) != 0U ? 1U : 0U;",
            "    irq_raised_at_success = (*status_reg & V15_STATUS_IRQ_RAISED) != 0U ? 1U : 0U;",
        )
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_IRQ_FROM_DECIDING_WORD)


class TheExitConditionIsBit5Alone(unittest.TestCase):
    def test_leaving_on_irq_raised_is_refused(self):
        # V14 had this rule and V15 inherits the claim, requalified: irq is
        # observed, never an exit.
        source = _mutate(
            "        if ((status & V15_STATUS_CMD_END) != 0U) {",
            "        if ((status & V15_STATUS_IRQ_RAISED) != 0U) {",
        )
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_EXIT_IS_CMD_END)

    def test_a_loop_without_the_contract_bound_is_refused(self):
        source = _mutate("i <= V15_ITERATION_BOUND", "i <= 100000U")
        self.assertEqual(_refusal_rule(source), gate.RULE_S5_ITERATION_BOUND)


class EveryRuleHasAFixtureThatFailsAtIt(unittest.TestCase):
    def test_each_registered_fixture_trips_its_own_rule(self):
        for name, (old, new, rule) in FIXTURES.items():
            with self.subTest(fixture=name):
                self.assertEqual(_refusal_rule(_mutate(old, new)), getattr(gate, rule))

    def test_the_fixtures_cover_every_rule_the_gate_declares(self):
        # Measured by running them, not by asserting the registry against
        # itself. A rule with no fixture is the shape of a silent gate.
        tripped = {
            _refusal_rule(_mutate(old, new)) for old, new, _rule in FIXTURES.values()
        }
        declared = {getattr(gate, name) for name in gate.RULES}
        self.assertEqual(tripped, declared)

    def test_no_fixture_is_accepted_by_accident(self):
        for name, (old, new, _rule) in FIXTURES.items():
            with self.subTest(fixture=name):
                self.assertIsNotNone(_refusal_rule(_mutate(old, new)))

    def test_the_irq_exit_branch_is_reached_by_a_fixture_of_its_own(self):
        # The replace-the-condition fixture trips the same rule through the
        # earlier branch, so on its own it would let the irq-exit refusal be
        # deleted without any test noticing. This one keeps bit5 exiting and
        # adds the interrupt beside it.
        old, new, rule = FIXTURES["irq_added_as_a_second_exit"]
        source = _mutate(old, new)
        self.assertIn("V15_STATUS_CMD_END", source)
        self.assertEqual(_refusal_rule(source), getattr(gate, rule))


if __name__ == "__main__":
    unittest.main()
