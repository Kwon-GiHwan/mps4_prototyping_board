#!/usr/bin/env python3
"""Shared read-only text normalization for the manuscript checkers.

Checker infrastructure maintenance — this module is NOT manuscript evidence and
holds no claim about the paper.

Phase 1 and Phase 1.5 each lost time to the same failure family: the manuscript
is hard-wrapped, so a literal multi-word pattern fails to match text that is
semantically present, and each checker relaxed its own regex ad hoc. Six of the
six checker defects recorded across those phases were variants of this. This
module gives every checker one normalization behaviour instead.

Design rules:

- The source manuscript is never rewritten to satisfy a regex. Normalization
  happens on a read-only copy.
- Intra-paragraph whitespace is collapsed so semantic phrase matching works
  across line breaks; paragraph and block boundaries survive as sentinels.
- Fenced code blocks are masked (not deleted) for prose matching, because
  whitespace is semantically load-bearing inside them; offsets are preserved so
  line mapping still works. `flat` keeps them for callers that want them.
- Every normalized offset maps back to an original 1-based line number.

Typical use:

    from manuscript_text import Manuscript
    m = Manuscript.load("docs/paper/MANUSCRIPT.md")
    for hit in m.find(r"purely by adapter state"):
        print(hit.line, hit.text)
"""
import re
from collections import namedtuple

Hit = namedtuple("Hit", "text line raw_start context")

# A paragraph/block boundary survives collapsing as this sentinel, so a pattern
# cannot silently match across two unrelated blocks.
PARA = "   "


def _collapse(raw, mask_spans=()):
    """Collapse whitespace, returning (flat, idxmap).

    idxmap[i] is the offset in `raw` of flat[i], so any match can be located.
    Blank lines become a paragraph sentinel rather than a plain space.
    Characters inside `mask_spans` are emitted as spaces, preserving offsets.
    """
    masked = set()
    for a, b in mask_spans:
        masked.update(range(a, b))
    out, idx = [], []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch.isspace():
            j = i
            while j < n and raw[j].isspace():
                j += 1
            blank_line = raw[i:j].count("\n") >= 2
            token = PARA if blank_line else " "
            for c in token:
                out.append(c)
                idx.append(i)
            i = j
            continue
        out.append(" " if i in masked else ch)
        idx.append(i)
        i += 1
    return "".join(out), idx


class Manuscript:
    """Read-only normalized view of a Markdown manuscript."""

    def __init__(self, raw, path=None):
        self.raw = raw
        self.path = path
        self._line_starts = [0] + [m.end() for m in re.finditer(r"\n", raw)]
        self.code_spans = [(m.start(), m.end())
                           for m in re.finditer(r"^```.*?^```", raw,
                                                re.S | re.M)]
        self.flat, self._imap = _collapse(raw)
        self.prose, self._pmap = _collapse(raw, mask_spans=self.code_spans)

    @classmethod
    def load(cls, path):
        with open(path) as fh:
            return cls(fh.read(), path)

    # -- location ---------------------------------------------------------
    def line_of(self, raw_index):
        lo, hi = 0, len(self._line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._line_starts[mid] <= raw_index:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    # -- searching --------------------------------------------------------
    def find(self, pattern, where="prose", flags=re.I, context=160):
        """Search normalized text; report original line numbers.

        `pattern` is normalized the same way the text is, so a pattern may be
        written with the line breaks it has in the source.
        """
        text, imap = ((self.prose, self._pmap) if where == "prose"
                      else (self.flat, self._imap))
        pat = re.sub(r"\s+", " ", pattern.strip())
        return [Hit(m.group(0), self.line_of(imap[m.start()]), imap[m.start()],
                    text[max(0, m.start() - context):m.end() + context])
                for m in re.finditer(pat, text, flags)]

    def has(self, phrase, where="prose"):
        """True if a literal phrase is present, ignoring how it is wrapped."""
        return bool(self.find(re.escape(re.sub(r"\s+", " ", phrase.strip())),
                              where=where, flags=re.I))

    # -- structure --------------------------------------------------------
    def sections(self):
        """Numbered sections: markdown headings AND bold-inline subsections.

        Section 8's limitation items are written `**8.1 Title.**`, not as
        headings; omitting them made every `Section 8.x` pointer look
        unresolved in Phase 1.5.
        """
        out = {}
        for m in re.finditer(r"^#{2,4} (\d+(?:\.\d+)?)\.? (.+)$", self.raw,
                             re.M):
            out[m.group(1)] = m.group(2).strip()
        for m in re.finditer(r"\*\*(\d+\.\d+)\s+([^*]+)", self.raw):
            out.setdefault(m.group(1), m.group(2).strip().rstrip("."))
        return out

    def section_pointers(self):
        """Every `Section N` / `Section N.M` reference, with its line.

        Tolerates bold/inline formatting and a line break between the word and
        the number (`Section\n4.6`, `**Section 4.6**`).
        """
        return [Hit(m.group(1), self.line_of(self._pmap[m.start()]),
                    self._pmap[m.start()], "")
                for m in re.finditer(r"Sections?\s+\**(\d+(?:\.\d+)?)\**",
                                     self.prose)]

    def tables(self):
        """(line, header) for each Markdown table in the document."""
        out = []
        for m in re.finditer(r"^\|(.+)\|\s*\n\|[ :|-]+\|\s*$", self.raw, re.M):
            out.append((self.line_of(m.start()), m.group(1).strip()))
        return out


if __name__ == "__main__":  # tiny self-report, no assertions
    import sys
    m = Manuscript.load(sys.argv[1] if len(sys.argv) > 1
                        else "docs/paper/MANUSCRIPT.md")
    print("lines %d | sections %d | tables %d | pointers %d | code blocks %d"
          % (m.line_of(len(m.raw) - 1), len(m.sections()), len(m.tables()),
             len(m.section_pointers()), len(m.code_spans)))
