"""The generator refuses before it generates.

Every input this experiment rests on is pinned, and the check happens before a
single byte is transformed. That ordering is the whole point: a generator that
produces output and then notices the input was wrong has already created an
artifact somebody can pick up.

The input that matters most is the V14 Q reference. V15's claim is that it is
Q with one observable replaced, so the Q it was derived from has to be the
qualified one -- not a structurally similar file that happens to be at hand.
There is a fixture for exactly that: same shape, wrong identity, refused.
"""

import hashlib
import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "patches"))

import patch_pmu_completion_s5_only_control as patcher  # noqa: E402


RUNNER = """
static uint32_t v14_primary_observe(void)
{
    uint32_t qread = 0U;
    uint32_t i;
    for (i = 1U; i <= V14_ITERATION_BOUND; ++i) {
        qread = *qread_reg;
        if (qread == qsize_expected) { break; }
    }
    return i;
}
"""

VENDOR = """
/* pinned Arm u85.c stand-in for the fixture */
void ethosu_irq_handler(void) { }
"""


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _identity(**overrides):
    identity = {
        "runner_sha256": _digest(RUNNER),
        "vendor_sha256": _digest(VENDOR),
        "q_reference_preboard_anchor": "619e957",
        "q_reference_board_evidence_anchor": "153f368",
        "design_anchor": "58b0cad",
        "plan_anchor": "3ca7bb1",
    }
    identity.update(overrides)
    return identity


def _refusal_rule(**overrides):
    try:
        patcher.generate(RUNNER, VENDOR, _identity(**overrides))
    except patcher.GeneratorError as exc:
        return patcher.refusal_rule(exc)
    return None


class TheInputsArePinned(unittest.TestCase):
    def test_the_matching_pair_generates(self):
        document = patcher.generate(RUNNER, VENDOR, _identity())
        self.assertIn("runner", document)
        self.assertIn("vendor", document)
        self.assertEqual(document["identity"], _identity())

    def test_a_drifted_runner_is_refused_before_generating(self):
        self.assertEqual(
            _refusal_rule(runner_sha256="0" * 64), patcher.RULE_INPUT_IDENTITY
        )

    def test_a_drifted_vendor_is_refused(self):
        self.assertEqual(
            _refusal_rule(vendor_sha256="0" * 64), patcher.RULE_INPUT_IDENTITY
        )

    def test_nothing_is_produced_when_an_input_is_wrong(self):
        # The ordering is the point: refusing after producing output would leave
        # an artifact behind that somebody can pick up later.
        try:
            patcher.generate(RUNNER, VENDOR, _identity(runner_sha256="0" * 64))
        except patcher.GeneratorError as exc:
            self.assertNotIn("v15_primary_observe", "%s" % exc)
            return
        self.fail("the generator produced output from a drifted input")


class TheQReferenceIsTheQualifiedOne(unittest.TestCase):
    def test_a_wrong_preboard_anchor_is_refused(self):
        self.assertEqual(
            _refusal_rule(q_reference_preboard_anchor="deadbee"),
            patcher.RULE_Q_REFERENCE_IDENTITY,
        )

    def test_a_wrong_board_evidence_anchor_is_refused(self):
        self.assertEqual(
            _refusal_rule(q_reference_board_evidence_anchor="deadbee"),
            patcher.RULE_Q_REFERENCE_IDENTITY,
        )

    def test_a_structurally_similar_but_unpinned_q_is_refused(self):
        # The failure mode this exists for: a Q that looks right and is not the
        # one the campaign qualified.
        self.assertEqual(
            _refusal_rule(q_reference_preboard_anchor=""),
            patcher.RULE_Q_REFERENCE_IDENTITY,
        )


class TheAnchorsAreCarried(unittest.TestCase):
    def test_a_wrong_design_anchor_is_refused(self):
        self.assertEqual(
            _refusal_rule(design_anchor="0000000"), patcher.RULE_ANCHOR_IDENTITY
        )

    def test_a_wrong_plan_anchor_is_refused(self):
        self.assertEqual(
            _refusal_rule(plan_anchor="0000000"), patcher.RULE_ANCHOR_IDENTITY
        )


class TheInterventionSurfaceIsBounded(unittest.TestCase):
    def test_the_generated_runner_changes_only_the_observable(self):
        document = patcher.generate(RUNNER, VENDOR, _identity())
        surface = patcher.intervention_surface(RUNNER, document["runner"])
        self.assertTrue(surface["within_expected_surface"], surface)

    def test_drift_outside_the_surface_is_refused(self):
        # A generator that also reorganised something else would be changing two
        # things at once, and the control would no longer be minimal.
        with self.assertRaises(patcher.GeneratorError) as caught:
            patcher.check_intervention_surface(
                RUNNER, patcher.generate(RUNNER, VENDOR, _identity())["runner"]
                + "\nstatic void something_else(void) { }\n"
            )
        self.assertEqual(patcher.refusal_rule(caught.exception),
                         patcher.RULE_INTERVENTION_SURFACE)

    def test_the_vendor_is_not_touched_at_all(self):
        document = patcher.generate(RUNNER, VENDOR, _identity())
        self.assertEqual(document["vendor"], VENDOR)


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_generator_declares(self):
        tripped = {
            _refusal_rule(runner_sha256="0" * 64),
            _refusal_rule(q_reference_preboard_anchor="deadbee"),
            _refusal_rule(design_anchor="0000000"),
        }
        try:
            patcher.check_intervention_surface(RUNNER, RUNNER + "\nstatic void x(void){}\n")
        except patcher.GeneratorError as exc:
            tripped.add(patcher.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(patcher, name) for name in patcher.RULES})


if __name__ == "__main__":
    unittest.main()
