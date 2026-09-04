#!/usr/bin/env python3
"""Regression fixtures for the F4 sentence class (PHASE 1.5, finding F15).

The Phase-1 checker's rule 11 matched only `X caused`, so the F4 sentence
("differed ~4x purely by adapter state") passed. These fixtures pin the
extended detector's behaviour in both directions: it must FIRE on affirmative
causal isolation of a confounded factor, and must NOT fire on the paper's many
legitimate refusals, qualifications and historical framings of the same words.

    python3 docs/paper/review/phase1_5_checker_fixtures.py
"""
import unittest
import phase1_consistency_check as C


class MustFire(unittest.TestCase):
    """Affirmative causal isolation of a NOT_SEPARATED factor."""

    def test_f4_original_sentence(self):
        """The exact sentence Phase-1 shipped and rule 11 missed."""
        t = ("A simulator's timing adapter can silently change what is being "
             "measured: two platforms running a byte-identical command stream "
             "differed ~4x purely by adapter state, and nothing in the cycle "
             "counts signalled it.")
        self.assertTrue(C.causal_isolation_hits(t))

    def test_ta_caused_plain(self):
        self.assertTrue(C.causal_isolation_hits(
            "The timing adapter caused the scaling-class disagreements."))

    def test_solely_due_to_subsystem(self):
        self.assertTrue(C.causal_isolation_hits(
            "The eight class changes are solely due to the subsystem."))

    def test_attributable_to_adapter(self):
        self.assertTrue(C.causal_isolation_hits(
            "The 4x magnitude is attributable to adapter state."))

    def test_driven_by_bandwidth(self):
        self.assertTrue(C.causal_isolation_hits(
            "The rnnoise regression is driven by memory-system bandwidth."))

    def test_ublock_causes_regression(self):
        self.assertTrue(C.causal_isolation_hits(
            "Ublock enlargement causes the whole-model regression."))


class MustNotFire(unittest.TestCase):
    """The paper says these words constantly, to refuse the claim."""

    def test_f4_corrected_sentence(self):
        """The Phase-1.5 replacement must pass."""
        t = ("Because timing-adapter state, subsystem and Fast Models timing "
             "implementation differ together across that pair, the magnitude "
             "cannot be attributed to the timing adapter alone; the three "
             "contributions are NOT_SEPARATED. The observation is therefore "
             "treated as a methodology warning against raw cross-platform "
             "cycle comparison, not as a performance result.")
        self.assertFalse(C.causal_isolation_hits(t))

    def test_not_separated_qualification(self):
        self.assertFalse(C.causal_isolation_hits(
            "In CLASS B the timing-adapter state, the subsystem and the Fast "
            "Models implementation change together, so their contributions "
            "remain NOT_SEPARATED."))

    def test_associated_with_framing(self):
        self.assertFalse(C.causal_isolation_hits(
            "All observed scaling-class disagreements occurred in comparisons "
            "where TA state also differed; they are ASSOCIATED_WITH those "
            "comparisons. They are not attributed to the timing adapter."))

    def test_retired_single_factor_account(self):
        self.assertFalse(C.causal_isolation_hits(
            "Retired - the single-factor ublock account. Ublock enlargement "
            "causes the regression is not supported: ublock change is a ~95% "
            "background rate in every direction class."))

    def test_unavailable_single_factor_claims(self):
        self.assertFalse(C.causal_isolation_hits(
            "Single-factor claims (shared-SRAM contention causes..., bandwidth "
            "causes...) are unavailable: the memory-mode axis is a "
            "configuration intervention, not a bandwidth intervention."))

    def test_bridge_residual_refusal(self):
        self.assertFalse(C.causal_isolation_hits(
            "The beat residual cannot be attributed specifically to the "
            "instrumentation backend; the residual is ASSOCIATED_WITH "
            "container re-serialization."))

    def test_historical_withdrawn_observation(self):
        self.assertFalse(C.causal_isolation_hits(
            "An earlier auxiliary record reported that an FVP accepted an "
            "unsupported num_macs value, and was used to argue that the model "
            "range-checks bounds; it is classified NOT_REPRODUCIBLE."))

    def test_causal_word_without_confounded_subject(self):
        """'caused by' about something outside the confounded set is not ours."""
        self.assertFalse(C.causal_isolation_hits(
            "The build failure was caused by an unpinned SOURCE_DATE_EPOCH."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
