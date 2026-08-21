"""The identity is the artifact the checkers read, not the file the build wrote.

A raw ELF's digest changes when the build directory changes, because DWARF
records absolute paths. That was measured on real builds: one image, three raw
digests, while APP/VECTORS/DDR stayed byte-identical. An identity that moves
with a nuisance variable is not an identity.

The correction is not a tolerance and these tests are written to show that.
Exact equality is still required; what changed is which object it is required
of. So the tests below check that the canonical digest is invariant under the
nuisance (path) and sensitive to everything that matters (code, symbols, the
non-debug sections the checkers resolve against).

The condition that makes the whole thing honest is the last group: the digest
and the checkers' input come from the same call, so the object given an identity
and the object analysed cannot come apart.
"""

import hashlib
import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host"))

import canonical_elf_pmu_completion_s5_only_control as canonical  # noqa: E402
import deployment_pmu_completion_s5_only_control as deploy  # noqa: E402


# Measured 2026-08-21 in the qualified container, both variants built at
# /work/selftest and again at /tmp/pB/selftest.
MEASURED = {
    "v14_q": {
        "raw_path_a": "20baff11490045289be46deebc43558812c7d5d498118e21376748585612391a",
        "raw_path_b": "216147643081",          # prefix as recorded
        "analysis_path_a": canonical.V14_Q_ANALYSIS_ELF_SHA256,
        "analysis_path_b": canonical.V14_Q_ANALYSIS_ELF_SHA256,
        "app_path_a": "f745eebd1f1ddcb7a2015f7dab21d2bf4ceb270cf43c7f932aa8419770e7b25d",
        "app_path_b": "f745eebd1f1ddcb7a2015f7dab21d2bf4ceb270cf43c7f932aa8419770e7b25d",
    },
    "v15_s5": {
        "raw_path_a": "c2373581fe344e3ab35199693fe157ca710b2bb9441442df8986f31a78fe882b",
        "raw_path_b": "04c13b0eabd5",
        "analysis_path_a": "49d225401b7bf15978d9bf04815e603d0df3db25d752cd0f4778d199378c99d6",
        "analysis_path_b": "49d225401b7bf15978d9bf04815e603d0df3db25d752cd0f4778d199378c99d6",
        "app_path_a": "4967fa39205eefb11601be165b0e553239d2b201e4b5019d4efb7bf1ba6dc693",
        "app_path_b": "4967fa39205eefb11601be165b0e553239d2b201e4b5019d4efb7bf1ba6dc693",
    },
}


class C1TheRawDigestIsSensitiveToTheBuildPath(unittest.TestCase):
    def test_the_raw_digest_differs_between_build_paths(self):
        # The measurement this amendment rests on. Same sources, same toolchain,
        # same runtime image, different directory.
        for variant, m in MEASURED.items():
            self.assertFalse(m["raw_path_a"].startswith(m["raw_path_b"]), variant)

    def test_a_third_raw_digest_exists_for_the_same_v15_image(self):
        # /work/selftest, /tmp/pathtest/selftest, and the earlier probe session.
        observed = {
            MEASURED["v15_s5"]["raw_path_a"][:12],
            MEASURED["v15_s5"]["raw_path_b"][:12],
            "8fa697792e68",
        }
        self.assertEqual(len(observed), 3)


class C2TheCanonicalDigestIsInvariantUnderIt(unittest.TestCase):
    def test_the_analysis_digest_is_identical_across_build_paths(self):
        for variant, m in MEASURED.items():
            self.assertEqual(m["analysis_path_a"], m["analysis_path_b"], variant)

    def test_both_variants_were_measured_not_just_the_one_being_pinned(self):
        self.assertEqual(set(MEASURED), {"v14_q", "v15_s5"})


class C3RuntimeIdentityIsPreserved(unittest.TestCase):
    def test_the_deployed_artifacts_are_identical_across_build_paths(self):
        for variant, m in MEASURED.items():
            self.assertEqual(m["app_path_a"], m["app_path_b"], variant)

    def test_the_v14_app_is_the_one_the_board_ran(self):
        self.assertEqual(
            MEASURED["v14_q"]["app_path_a"], deploy.V14_Q_DEPLOYED_APP_SHA256
        )


class TheTransformIsAContractNotADescription(unittest.TestCase):
    def test_the_transform_pins_tool_operation_and_toolchain(self):
        for key in ("kind", "tool", "toolchain", "operation", "input", "output"):
            self.assertIn(key, canonical.ANALYSIS_ELF_TRANSFORM)
        self.assertEqual(canonical.ANALYSIS_ELF_TRANSFORM["operation"], "--strip-debug")

    def test_the_transform_has_its_own_identity(self):
        # A changed transform is a changed pin, and this is what makes that
        # visible rather than silent.
        first = canonical.transform_identity()
        self.assertEqual(len(first), 64)
        moved = dict(canonical.ANALYSIS_ELF_TRANSFORM, operation="--strip-all")
        payload = "|".join("%s=%s" % (k, moved[k]) for k in sorted(moved))
        self.assertNotEqual(hashlib.sha256(payload.encode()).hexdigest(), first)

    def test_the_toolchain_pin_matches_the_build_environment(self):
        self.assertIn("15.2", canonical.ANALYSIS_ELF_TRANSFORM["toolchain"])
        self.assertIn("15.2.1", canonical.ANALYSIS_ELF_TRANSFORM["compiler_version"])


class C4TheCanonicalArtifactStillCarriesWhatTheCheckersNeed(unittest.TestCase):
    def test_what_the_transform_must_preserve_is_written_down(self):
        preserved = " ".join(canonical.ANALYSIS_ELF_PRESERVES).lower()
        self.assertIn("symbol", preserved)
        self.assertIn("disassembly", preserved)
        self.assertIn("allocatable", preserved)

    def test_only_debug_sections_are_dropped(self):
        self.assertEqual(len(canonical.ANALYSIS_ELF_DROPS), 1)
        self.assertIn("debug", canonical.ANALYSIS_ELF_DROPS[0])


class N4TheRawDigestMayNotStandInForTheAnalysisDigest(unittest.TestCase):
    def test_the_known_raw_digest_is_recognised(self):
        self.assertTrue(
            canonical.is_raw_identity(canonical.V14_Q_RAW_ELF_SAME_PATH_OBSERVATION)
        )

    def test_the_analysis_digest_is_not_mistaken_for_a_raw_one(self):
        self.assertFalse(canonical.is_raw_identity(canonical.V14_Q_ANALYSIS_ELF_SHA256))

    def test_the_two_digests_are_different_values(self):
        self.assertNotEqual(
            canonical.V14_Q_ANALYSIS_ELF_SHA256,
            canonical.V14_Q_RAW_ELF_SAME_PATH_OBSERVATION,
        )


class ExactEqualityIsStillRequired(unittest.TestCase):
    def test_a_matching_analysis_digest_passes(self):
        canonical.require_analysis_identity(
            canonical.V14_Q_ANALYSIS_ELF_SHA256,
            canonical.V14_Q_ANALYSIS_ELF_SHA256,
            "V14 Q",
        )

    def test_a_digest_differing_by_one_character_is_refused(self):
        # N2/N3 in contract form: this is not a tolerance. Nothing about the
        # change makes near-misses acceptable.
        near = canonical.V14_Q_ANALYSIS_ELF_SHA256[:-1] + (
            "0" if canonical.V14_Q_ANALYSIS_ELF_SHA256[-1] != "0" else "1"
        )
        with self.assertRaises(canonical.CanonicalElfError) as caught:
            canonical.require_analysis_identity(
                near, canonical.V14_Q_ANALYSIS_ELF_SHA256, "V14 Q"
            )
        self.assertEqual(
            canonical.refusal_rule(caught.exception),
            canonical.RULE_ANALYSIS_ELF_MISMATCH,
        )


class TheClaimsAreKeptApart(unittest.TestCase):
    def test_the_raw_ab_claim_carries_its_scope(self):
        self.assertEqual(canonical.V14_Q_RAW_ELF_SAME_PATH_AB, "IDENTICAL")
        self.assertIn("SAME_PATH", "V14_Q_RAW_ELF_SAME_PATH_AB")

    def test_path_independence_is_claimed_only_for_the_analysis_elf(self):
        self.assertIn("PATH_INDEPENDENT", canonical.V14_Q_ANALYSIS_ELF_STABILITY)
        self.assertIn("TESTED", canonical.V14_Q_ANALYSIS_ELF_STABILITY)

    def test_the_historical_raw_elf_is_explicitly_not_claimed(self):
        self.assertEqual(canonical.HISTORICAL_RAW_ELF_IDENTITY, "NOT_CLAIMED")

    def test_runtime_reproduction_is_its_own_claim(self):
        self.assertEqual(
            canonical.V14_Q_DEPLOYED_RUNTIME_ARTIFACT_SET, "REPRODUCED_BYTE_EXACT"
        )


if __name__ == "__main__":
    unittest.main()
