#!/usr/bin/env python3
"""Regression fixtures for the shared normalization layer.

Covers the seven cases the manager named, each drawn from a defect actually
observed in Phase 1 or Phase 1.5.
"""
import unittest
from manuscript_text import Manuscript


def M(s):
    return Manuscript(s)


class Normalization(unittest.TestCase):

    def test_phrase_split_across_one_newline(self):
        """Phase-1.5 defect: 'not an exact\\n   decomposition'."""
        m = M("The data is not an exact\n   decomposition of the executable.\n")
        self.assertTrue(m.has("not an exact decomposition"))

    def test_phrase_split_across_multiple_spaces(self):
        m = M("reported   separately    and  are not combined\n")
        self.assertTrue(m.has("reported separately and are not combined"))

    def test_section_pointer_wrapped_across_lines(self):
        m = M("...structural comparison is deferred (Section\n4.6) for detail.\n")
        self.assertEqual([h.text for h in m.section_pointers()], ["4.6"])

    def test_bold_inline_formatting_around_section_reference(self):
        m = M("see **Section 8.13** and *Section 5*\n")
        self.assertEqual(sorted(h.text for h in m.section_pointers()),
                         ["5", "8.13"])

    def test_bold_inline_subsections_are_indexed(self):
        """Phase-1.5 defect: 8.x pointers looked unresolved."""
        m = M("## 8. Limitations\n\n**8.13 Platform-sensitivity bounds.** text\n")
        self.assertIn("8.13", m.sections())
        self.assertIn("8", m.sections())

    def test_negated_causal_sentence_is_findable_as_written(self):
        m = M("the magnitude cannot be attributed to the timing\nadapter alone\n")
        self.assertTrue(m.has("cannot be attributed to the timing adapter alone"))

    def test_not_separated_qualification_survives_wrapping(self):
        m = M("their contributions\nremain `NOT_SEPARATED` in CLASS B.\n")
        self.assertTrue(m.has("remain `NOT_SEPARATED` in CLASS B"))

    def test_quoted_historical_framing_survives_wrapping(self):
        m = M("An earlier auxiliary record reported that an FVP\naccepted an "
              "unsupported num_macs value.\n")
        self.assertTrue(m.has("An earlier auxiliary record reported that an "
                              "FVP accepted an unsupported num_macs value"))


class Boundaries(unittest.TestCase):

    def test_paragraph_boundary_is_not_collapsed_to_a_space(self):
        """A pattern must not match across two unrelated paragraphs."""
        m = M("the adapter state\n\ncaused the failure\n")
        self.assertFalse(m.has("adapter state caused the failure"))

    def test_code_block_masked_for_prose_but_kept_in_flat(self):
        m = M("intro\n\n```\nTA caused the disagreement\n```\n\nafter\n")
        self.assertFalse(m.has("TA caused the disagreement", where="prose"))
        self.assertTrue(m.has("TA caused the disagreement", where="flat"))

    def test_masking_preserves_offsets_so_lines_stay_correct(self):
        m = M("line1\n\n```\nblock\n```\n\nthe target phrase here\n")
        hit = m.find(r"the target phrase here")[0]
        self.assertEqual(m.raw.splitlines()[hit.line - 1], "the target phrase here")


class LineMapping(unittest.TestCase):

    def test_line_of_first_and_last(self):
        m = M("a\nb\nc\n")
        self.assertEqual(m.line_of(0), 1)
        self.assertEqual(m.line_of(m.raw.index("c")), 3)

    def test_match_reports_the_line_it_starts_on(self):
        m = M("one\ntwo\nthree wrapped\nphrase here\n")
        hit = m.find(r"wrapped phrase here")[0]
        self.assertEqual(hit.line, 3)

    def test_tables_are_located(self):
        m = M("t\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertEqual(m.tables(), [(3, "a | b")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
