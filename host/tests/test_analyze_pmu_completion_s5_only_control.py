"""S1 to S6 as an enum the analyzer must reach, not prose it may paraphrase.

The outcomes were preregistered before any firmware existed. That is worth
nothing if the analyzer can look at the data and write a sentence, so each
outcome is produced by a synthetic campaign built to land on it, and the
verdict is a value from a closed set.

Two things this file guards that the outcome table alone cannot. The permitted
set narrows under the fallback -- S3 is a comparison and there is nothing to
compare against -- and the poll count, present in every record and admitted as a
metric in none, may not reach the verdict by any path.

Floor and excursion are defined here the way V14's analyzer defines them, copied
rather than referred to: the same value must be the minimum of every boot taken
separately, pooling before classification is prohibited, and an excursion is a
sample above its own boot's minimum.
"""

import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import analyze_pmu_completion_s5_only_control as analyzer  # noqa: E402
import contract_pmu_completion_s5_only_control as contract  # noqa: E402


def boot(name, cycles, poll_counts=None):
    """One boot's ten runs, as the collector hands them over."""

    poll_counts = poll_counts or [7] * len(cycles)
    return {
        "boot_id": name,
        "samples": [
            {
                "run_id": index + 1,
                "boot_id": name,
                "sample_valid": True,
                "submit_to_s5_observed_cycles": value,
                "cmd_end_reached_observed": 1,
                "status_at_success": contract.STATUS_CMD_END,
                "poll_count": count,
            }
            for index, (value, count) in enumerate(zip(cycles, poll_counts))
        ],
    }


FLOOR = 732


def campaign(boots, mode=contract.Q_S5_EQUIVALENT):
    return {"comparison_mode": mode, "boots": boots}


# One floor reproduced in every boot, with excursions above it in each.
S1_BOOTS = [
    boot("b1", [FLOOR, FLOOR, 900, 1400, 2200, FLOOR, 3100, 980, FLOOR, 4400]),
    boot("b2", [FLOOR, 810, FLOOR, 2600, FLOOR, 1750, FLOOR, 5200, 990, FLOOR]),
    boot("b3", [FLOOR, FLOOR, 1220, FLOOR, 3300, FLOOR, 870, 4100, FLOOR, 1500]),
]
# The same floor, and nothing above it anywhere.
S2_BOOTS = [boot("b%d" % n, [FLOOR] * 10) for n in (1, 2, 3)]
# A floor, and excursion behaviour that differs qualitatively between boots.
S4_BOOTS = [
    boot("b1", [700 + n * 11 for n in range(10)]),
    boot("b2", [880 + n * 7 for n in range(10)]),
    boot("b3", [1010 + n * 13 for n in range(10)]),
]


class TheSixOutcomesAreReachable(unittest.TestCase):
    def test_s1_floor_and_excursions_reproduce(self):
        self.assertEqual(analyzer.analyze(campaign(S1_BOOTS))["outcome"], "S1")

    def test_s2_floor_reproduces_with_no_excursion(self):
        self.assertEqual(analyzer.analyze(campaign(S2_BOOTS))["outcome"], "S2")

    def test_s4_no_reproducible_floor(self):
        self.assertEqual(analyzer.analyze(campaign(S4_BOOTS))["outcome"], "S4")

    def test_s5_the_observable_was_never_seen(self):
        boots = [boot("b%d" % n, [FLOOR] * 10) for n in (1, 2, 3)]
        for entry in boots:
            for sample in entry["samples"]:
                sample["cmd_end_reached_observed"] = 0
                sample["sample_valid"] = False
        self.assertEqual(analyzer.analyze(campaign(boots))["outcome"], "S5")

    def test_s6_boots_disagreeing_do_not_become_a_majority(self):
        # Two boots with excursions and one without is not "reproduced in two of
        # three": it is boot-dependent, and registering that in advance is what
        # stops the criterion being invented afterwards.
        boots = [S1_BOOTS[0], S1_BOOTS[1], boot("b3", [FLOOR] * 10)]
        self.assertEqual(analyzer.analyze(campaign(boots))["outcome"], "S6")


class TheFloorIsDefinedNotJudged(unittest.TestCase):
    def test_a_floor_must_be_the_minimum_of_every_boot_separately(self):
        # One boot never reaching the others' minimum means no reproduced floor,
        # however good the pooled distribution looks.
        boots = [S1_BOOTS[0], S1_BOOTS[1], boot("b3", [FLOOR + 40] * 10)]
        outcome = analyzer.analyze(campaign(boots))["outcome"]
        self.assertIn(outcome, ("S4", "S6"))

    def test_pooling_is_refused_as_a_definition(self):
        self.assertIn("every boot", analyzer.FLOOR_DEFINITION)
        self.assertIn("pooling", analyzer.FLOOR_DEFINITION.lower())


class TheModeNarrowsWhatMayBeSaid(unittest.TestCase):
    def test_s3_is_unreachable_under_the_fallback(self):
        document = analyzer.analyze(campaign(S1_BOOTS, contract.S5_WITHIN_VARIANT_ONLY))
        self.assertNotEqual(document["outcome"], "S3")
        self.assertNotIn("S3", document["outcomes_permitted"])

    def test_emitting_s3_under_the_fallback_is_refused(self):
        with self.assertRaises(analyzer.AnalysisError) as caught:
            analyzer.emit("S3", contract.S5_WITHIN_VARIANT_ONLY)
        self.assertEqual(
            analyzer.refusal_rule(caught.exception), analyzer.RULE_OUTCOME_NOT_PERMITTED
        )

    def test_s3_is_emittable_when_equivalence_holds(self):
        self.assertEqual(analyzer.emit("S3", contract.Q_S5_EQUIVALENT), "S3")

    def test_an_outcome_outside_the_set_is_refused(self):
        with self.assertRaises(analyzer.AnalysisError) as caught:
            analyzer.emit("S7", contract.Q_S5_EQUIVALENT)
        self.assertEqual(
            analyzer.refusal_rule(caught.exception), analyzer.RULE_OUTCOME_UNKNOWN
        )


class ThePollCountReachesNothing(unittest.TestCase):
    def test_the_verdict_is_unchanged_when_every_poll_count_changes(self):
        # Admitted as a metric in nothing: the same cycles with wildly different
        # counts must produce the same outcome, or the count is deciding.
        low = analyzer.analyze(campaign(S1_BOOTS))
        loud = analyzer.analyze(
            campaign(
                [
                    boot(
                        entry["boot_id"],
                        [s["submit_to_s5_observed_cycles"] for s in entry["samples"]],
                        poll_counts=[9999 - n for n in range(10)],
                    )
                    for entry in S1_BOOTS
                ]
            )
        )
        self.assertEqual(low["outcome"], loud["outcome"])

    def test_the_verdict_document_records_the_count_as_not_admitted(self):
        document = analyzer.analyze(campaign(S1_BOOTS))
        self.assertEqual(
            document["poll_count_admission"], contract.POLL_COUNT_NOT_ADMITTED
        )
        self.assertEqual(document["poll_count_transport"], contract.POLL_COUNT_PRESENT)

    def test_deciding_by_poll_count_is_refused(self):
        with self.assertRaises(analyzer.AnalysisError) as caught:
            analyzer.emit("S1", contract.Q_S5_EQUIVALENT, decided_by="poll_count")
        self.assertEqual(
            analyzer.refusal_rule(caught.exception), analyzer.RULE_POLL_COUNT_NOT_ADMITTED
        )


class TheVocabularyIsBounded(unittest.TestCase):
    def test_the_verdict_carries_no_forbidden_term(self):
        document = analyzer.analyze(campaign(S1_BOOTS))
        text = repr(document).lower()
        for forbidden in ("latency", "t_npu", "faster", "slower", "internal completion"):
            self.assertNotIn(forbidden, text)

    def test_a_forbidden_term_in_a_narrative_is_refused(self):
        with self.assertRaises(analyzer.AnalysisError) as caught:
            analyzer.narrate("S1", "the S5 path shows a lower completion latency")
        self.assertEqual(
            analyzer.refusal_rule(caught.exception), analyzer.RULE_FORBIDDEN_VOCABULARY
        )

    def test_an_ordinary_narrative_passes(self):
        text = analyzer.narrate("S1", "a floor reproduced in every boot, with excursions above it")
        self.assertIn("S1", text)


if __name__ == "__main__":
    unittest.main()
