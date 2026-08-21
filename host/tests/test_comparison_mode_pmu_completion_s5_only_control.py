"""The comparison mode has to be carried, not described.

The design says that if Q-to-S5 equivalence fails, V15 retreats to
within-variant claims. Left as prose that is a retreat the program never takes:
the document says one thing and the analyzer goes on comparing. So the mode is a
value, every layer carries it, and disagreement between any two layers is a
failure rather than a vote.

The four attacks below are the ones the review named. Each is a way the fallback
could exist on paper and not in the code, and each has to be refused.
"""

import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import comparison_mode_pmu_completion_s5_only_control as chain  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402


def _layers(**overrides):
    """One mode, agreed by every layer, unless a test says otherwise."""

    layers = {name: contract.Q_S5_EQUIVALENT for name in chain.LAYERS}
    layers.update(overrides)
    return layers


def _equivalence(status="PASS", reference="153f368", evidence="a" * 16):
    return {
        "status": status,
        "reference_anchor": reference,
        "evidence_sha256": evidence,
    }


class TheModeIsCarriedByEveryLayer(unittest.TestCase):
    def test_the_layer_list_spans_firmware_to_report(self):
        self.assertEqual(chain.LAYERS[0], "firmware_evidence")
        self.assertEqual(chain.LAYERS[-1], "report")
        for expected in ("manifest", "parser", "classifier", "collector", "analyzer", "preflight"):
            self.assertIn(expected, chain.LAYERS)

    def test_an_agreed_mode_resolves(self):
        document = chain.resolve(_layers(), _equivalence())
        self.assertEqual(document["comparison_mode"], contract.Q_S5_EQUIVALENT)
        self.assertEqual(document["layers_agreeing"], len(chain.LAYERS))

    def test_a_missing_layer_is_refused(self):
        layers = _layers()
        del layers["analyzer"]
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(layers, _equivalence())
        self.assertEqual(chain.refusal_rule(caught.exception), chain.RULE_MODE_MISSING_LAYER)


class DisagreementIsAFailureNotAVote(unittest.TestCase):
    def test_one_layer_disagreeing_is_refused(self):
        # N1 in the review's list: the manifest says fallback and the analyzer
        # assumes equivalence. Neither wins.
        layers = _layers(analyzer=contract.S5_WITHIN_VARIANT_ONLY)
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(layers, _equivalence())
        self.assertEqual(chain.refusal_rule(caught.exception), chain.RULE_MODE_DISAGREEMENT)

    def test_the_majority_does_not_win(self):
        # Seven layers saying one thing and one saying another is still a
        # disagreement. A mode decided by counting would be a mode nobody set.
        layers = _layers(preflight=contract.S5_WITHIN_VARIANT_ONLY)
        with self.assertRaises(chain.ComparisonModeError):
            chain.resolve(layers, _equivalence())

    def test_an_unknown_mode_value_is_refused(self):
        layers = _layers(collector="PROBABLY_EQUIVALENT")
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(layers, _equivalence())
        self.assertEqual(chain.refusal_rule(caught.exception), chain.RULE_MODE_UNKNOWN_VALUE)


class TheModeMustMatchTheEvidence(unittest.TestCase):
    def test_equivalence_failing_while_the_chain_claims_equivalent_is_refused(self):
        # N1 proper: the detector refused and the manifest was forged to PASS.
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(_layers(), _equivalence(status="FAIL"))
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_a_valid_evidence_status_with_the_wrong_mode_is_refused(self):
        # The forgery in its most plausible form: the equivalence detector
        # recorded the fallback honestly, and the chain claims equivalence
        # anyway. The status is a legal value here, so the earlier check that
        # rejects nonsense statuses does not fire -- without this fixture the
        # branch that compares mode against evidence is never reached, and
        # deleting it changes nothing.
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(_layers(), _equivalence(status="FALLBACK_WITHIN_VARIANT"))
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_the_fallback_claimed_while_the_evidence_passed_is_refused(self):
        layers = {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS}
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(layers, _equivalence(status="PASS"))
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_equivalence_passing_against_the_wrong_reference_is_refused(self):
        # N2: same structure, wrong identity.
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(_layers(), _equivalence(reference="deadbee"))
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_REFERENCE_IDENTITY
        )

    def test_a_pass_with_no_evidence_digest_is_refused(self):
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(_layers(), _equivalence(evidence=""))
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_CONTRADICTS_EVIDENCE
        )

    def test_the_fallback_resolves_when_the_evidence_says_so(self):
        layers = {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS}
        document = chain.resolve(layers, _equivalence(status="FALLBACK_WITHIN_VARIANT"))
        self.assertEqual(document["comparison_mode"], contract.S5_WITHIN_VARIANT_ONLY)
        self.assertFalse(document["cross_variant_claims_enabled"])
        self.assertEqual(document["reason"], contract.FALLBACK_REASON)


class FallbackDisablesCrossVariantClaims(unittest.TestCase):
    def test_fallback_with_cross_variant_enabled_is_refused(self):
        # N3: the mode says fallback and something downstream still believes it
        # may compare.
        layers = {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS}
        with self.assertRaises(chain.ComparisonModeError) as caught:
            chain.resolve(
                layers,
                _equivalence(status="FALLBACK_WITHIN_VARIANT"),
                cross_variant_claims_enabled=True,
            )
        self.assertEqual(
            chain.refusal_rule(caught.exception), chain.RULE_MODE_CROSS_VARIANT_LEAK
        )

    def test_s3_is_not_permitted_under_fallback(self):
        layers = {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS}
        document = chain.resolve(layers, _equivalence(status="FALLBACK_WITHIN_VARIANT"))
        self.assertNotIn("S3", document["outcomes_permitted"])

    def test_every_other_outcome_survives(self):
        layers = {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS}
        document = chain.resolve(layers, _equivalence(status="FALLBACK_WITHIN_VARIANT"))
        self.assertEqual(set(document["outcomes_permitted"]), {"S1", "S2", "S4", "S5", "S6"})


class EveryRuleHasAFixture(unittest.TestCase):
    def test_the_fixtures_trip_every_rule_the_chain_declares(self):
        tripped = set()
        attempts = (
            (lambda: chain.resolve({k: v for k, v in list(_layers().items())[:-1]}, _equivalence())),
            (lambda: chain.resolve(_layers(analyzer=contract.S5_WITHIN_VARIANT_ONLY), _equivalence())),
            (lambda: chain.resolve(_layers(collector="MAYBE"), _equivalence())),
            (lambda: chain.resolve(_layers(), _equivalence(status="FAIL"))),
            (lambda: chain.resolve(_layers(), _equivalence(reference="deadbee"))),
            (
                lambda: chain.resolve(
                    {name: contract.S5_WITHIN_VARIANT_ONLY for name in chain.LAYERS},
                    _equivalence(status="FALLBACK_WITHIN_VARIANT"),
                    cross_variant_claims_enabled=True,
                )
            ),
        )
        for attempt in attempts:
            try:
                attempt()
            except chain.ComparisonModeError as exc:
                tripped.add(chain.refusal_rule(exc))
        self.assertEqual(tripped, {getattr(chain, name) for name in chain.RULES})


if __name__ == "__main__":
    unittest.main()
