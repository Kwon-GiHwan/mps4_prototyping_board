#!/usr/bin/env python3
"""Fidelity conversion of the frozen Markdown manuscript into LaTeX.

SE1, section 5. This is a *transformation*, not an edit: no prose is rewritten,
no number changed, no claim strengthened or weakened, no section reordered. The
script is the provenance record, and it re-derives main.tex from the frozen
source on every run.

Source of truth is the frozen commit, read through git rather than the working
tree, so the conversion cannot silently pick up an uncommitted change:

    git show d137a7d:docs/paper/MANUSCRIPT.md

Deliberate, documented omissions (recorded in CONVERSION_PROVENANCE.md):
  - the header provenance block and the trailing "Integration status" note.
    Both are internal process metadata listing frozen git tags and repository
    paths; they carry no scientific claim and would deanonymize the authors
    under the double-anonymous policy.
  - the Markdown "## References" list, which is replaced by BibTeX.

Deliberate presentational transformations:
  - box-drawing and arrow glyphs inside fenced code blocks are ASCII-folded,
    because pdfTeX cannot typeset them in verbatim with the default fonts. The
    diagram structure is preserved; only the glyphs change.
  - Markdown tables become inline tabulars at their original position. The
    source tables carry no captions, and inventing captions would be adding
    content.

    python3 docs/paper/submission/scripts/md2tex.py
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(SUB)))
FROZEN = "d137a7d"

# in-text citation number -> BibTeX key (see references.bib and
# CONVERSION_PROVENANCE.md for the per-entry authority record)
CITE = {
    1: "arm:ethosu85trm", 2: "arm:ethosu85to", 3: "arm:mldevguide",
    4: "arm:corstone320", 5: "arm:fvpsse320", 6: "arm:fastmodels",
    7: "arm:vela", 8: "arm:mlek", 9: "jouppi2017tpu",
    10: "samajdar2018scalesim", 11: "parashar2019timeloop",
    12: "gutierrez2014sources", 13: "banbury2021mlperftiny",
    14: "banbury2021micronets", 15: "david2021tflm",
    16: "arm:ethosu55trm", 17: "arm:ethosu65trm",
}

# prose (non-verbatim) unicode -> LaTeX
UNI = {
    "\u2014": "---", "\u2013": "--", "\u2212": "$-$", "\u00d7": "$\\times$",
    "\u2264": "$\\leq$", "\u2265": "$\\geq$", "\u00b1": "$\\pm$",
    "\u2026": "\\ldots{}", "\u2192": "$\\rightarrow$",
    "\u2194": "$\\leftrightarrow$", "\u2193": "$\\downarrow$",
    "\u00a0": "~", "\u2018": "`", "\u2019": "'", "\u201c": "``", "\u201d": "''",
}
# inside verbatim, glyphs pdfTeX cannot set are folded to ASCII
VERB_FOLD = {
    "\u2500": "-", "\u2502": "|", "\u250c": "+", "\u2510": "+", "\u2534": "+",
    "\u2192": "->", "\u2194": "<->", "\u2193": "v", "\u2014": "--",
    "\u00d7": "x", "\u2265": ">=", "\u2264": "<=", "\u2212": "-",
}

TRACE = []


def frozen_source():
    out = subprocess.run(["git", "-C", REPO, "show",
                          "%s:docs/paper/MANUSCRIPT.md" % FROZEN],
                         capture_output=True, text=True, check=True)
    return out.stdout


def esc(s):
    """Escape LaTeX specials in prose. Order matters: backslash first."""
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in (("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"),
                 ("~", "\\textasciitilde{}"), ("^", "\\textasciicircum{}")):
        s = s.replace(a, b)
    return s


def inline(s):
    """Markdown inline markup -> LaTeX, with escaping done inside segments."""
    out, i = [], 0
    # protect `code` first so escaping does not mangle it
    parts = re.split(r"(`[^`]*`)", s)
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            body = p[1:-1]
            for a, b in UNI.items():
                body = body.replace(a, b if not b.startswith("$") else b.strip("$"))
            out.append("\\texttt{%s}" % esc(body))
        else:
            t = esc(p)
            # bold then italic (bold uses ** which would otherwise eat *)
            t = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", t)
            t = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\\emph{\1}", t)
            for a, b in UNI.items():
                t = t.replace(a, b)
            # straight ASCII quotes -> proper TeX quotes (typography only)
            t = re.sub(r'"([^"]*)"', r"``\1''", t)
            out.append(t)
    t = "".join(out)

    # citations: [9] or [1, 2] -> \cite{...}
    def _cite(m):
        nums = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
        return "~\\cite{%s}" % ",".join(CITE[n] for n in nums)
    t = re.sub(r"\s*\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]", _cite, t)

    # cross-references
    t = re.sub(r"Sections?~?\s*(\d+(?:\.\d+)?)",
               lambda m: "Section~\\ref{sec:%s}" % m.group(1), t)
    t = re.sub(r"Figure\s+(\d)", lambda m: "Figure~\\ref{fig:%s}" % m.group(1), t)
    t = re.sub(r"Appendix\s+([AB])",
               lambda m: "Appendix~\\ref{app:%s}" % m.group(1), t)
    return t


WRAP_AT = 26          # a column wider than this wraps instead of overflowing


def table(lines):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    align = rows[1]
    body = [rows[0]] + rows[2:]
    ncol = len(align)
    widest = [max((len(r[i]) for r in body if i < len(r)), default=0)
              for i in range(ncol)]

    def base(c):
        if c.endswith(":") and not c.startswith(":"):
            return "r"
        if c.startswith(":") and c.endswith(":"):
            return "c"
        return "l"

    # Long text columns become wrapping X columns; short ones keep their
    # alignment. Without this, a wide table overflows the acmsmall text block.
    spec = "".join("L" if widest[i] > WRAP_AT else base(align[i])
                   for i in range(ncol))
    env = "tabularx" if "L" in spec else "tabular"
    open_ = ("\\begin{tabularx}{\\linewidth}{%s}" % spec if env == "tabularx"
             else "\\begin{tabular}{%s}" % spec)
    out = ["\\begin{center}\\small", open_, "\\toprule"]
    for k, r in enumerate(body):
        out.append(" & ".join(inline(c) for c in r) + " \\\\")
        if k == 0:
            out.append("\\midrule")
    out += ["\\bottomrule", "\\end{%s}" % env, "\\end{center}"]
    return out


def code_block(lines):
    folded = []
    for ln in lines:
        for a, b in VERB_FOLD.items():
            ln = ln.replace(a, b)
        folded.append(ln)
    return ["\\begin{quote}\\small\\begin{verbatim}"] + folded + \
           ["\\end{verbatim}\\end{quote}"]


def convert(md):
    # ---- strip the internal process blocks ---------------------------------
    body = md[md.index("## Abstract"):]
    if "\n---\n\n*Integration status:" in body:
        a = body.index("\n---\n\n*Integration status:")
        b = body.index("## References")
        body = body[:a] + "\n" + body[b:]
    body = body[:body.index("## References")]

    lines = body.split("\n")
    out, i, in_appendix = [], 0, False
    while i < len(lines):
        ln = lines[i]

        # fenced code block
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out += code_block(lines[i + 1:j])
            i = j + 1
            continue

        # table
        if ln.startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\|[\s:|-]+\|\s*$", lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out += table(lines[i:j])
            i = j
            continue

        # figure: ![alt](figures/figN_*.svg) then blank then **Figure N.** caption
        m = re.match(r"^!\[(.*)$", ln)
        if m:
            blk = [ln]
            while "](" not in blk[-1]:
                i += 1
                blk.append(lines[i])
            whole = " ".join(blk)
            alt = re.match(r"^!\[(.*?)\]\((.*?)\)", whole)
            alt_text, path = alt.group(1), alt.group(2)
            num = re.search(r"fig(\d)", path).group(1)
            stem = os.path.basename(path).replace(".svg", "")
            # caption block follows
            k = i + 1
            while k < len(lines) and not lines[k].startswith("**Figure "):
                k += 1
            cap = []
            k2 = k
            while k2 < len(lines) and lines[k2].strip():
                cap.append(lines[k2])
                k2 += 1
            cap_text = " ".join(cap)
            cap_text = re.sub(r"^\*\*Figure \d\.\*\*\s*", "", cap_text)
            out += [
                "\\begin{figure}[t]", "  \\centering",
                "  \\includegraphics[width=\\linewidth]{figures/%s.pdf}" % stem,
                "  \\Description{%s}" % inline(re.sub(r"\s+", " ", alt_text)),
                "  \\caption{%s}" % inline(re.sub(r"\s+", " ", cap_text)),
                "  \\label{fig:%s}" % num, "\\end{figure}",
            ]
            i = k2
            continue

        # headings
        m = re.match(r"^## (Appendix ([AB]))\. (.+)$", ln)
        if m:
            if not in_appendix:
                # ACM ordering: main text, then references, then appendices.
                out.append("\\bibliographystyle{ACM-Reference-Format}")
                out.append("\\bibliography{references}")
                out.append("\\appendix")
                in_appendix = True
            out.append("\\section{%s}\\label{app:%s}" % (inline(m.group(3)),
                                                         m.group(2)))
            TRACE.append(("## " + m.group(1), "\\section (appendix %s)" % m.group(2)))
            i += 1
            continue
        m = re.match(r"^## Abstract\s*$", ln)
        if m:
            out.append("\\begin{abstract}")
            i += 1
            # abstract runs to the horizontal rule
            buf = []
            while i < len(lines) and lines[i].strip() != "---":
                buf.append(lines[i])
                i += 1
            out += paragraphs(buf)
            out.append("\\end{abstract}")
            out.append("\\maketitle")
            TRACE.append(("## Abstract", "\\begin{abstract}"))
            i += 1
            continue
        m = re.match(r"^## (\d+)\. (.+)$", ln)
        if m:
            out.append("\\section{%s}\\label{sec:%s}" % (inline(m.group(2)),
                                                          m.group(1)))
            TRACE.append(("## %s. %s" % m.groups(), "\\section{...}\\label{sec:%s}"
                          % m.group(1)))
            i += 1
            continue
        m = re.match(r"^### (\d+\.\d+) (.+)$", ln)
        if m:
            out.append("\\subsection{%s}\\label{sec:%s}" % (inline(m.group(2)),
                                                             m.group(1)))
            TRACE.append(("### %s %s" % m.groups(),
                          "\\subsection{...}\\label{sec:%s}" % m.group(1)))
            i += 1
            continue
        if ln.strip() == "---":
            i += 1
            continue

        # ordinary paragraph / list
        buf = []
        while i < len(lines) and lines[i].strip() and \
                not lines[i].startswith(("#", "|", "```", "![")):
            buf.append(lines[i])
            i += 1
        if buf:
            out += paragraphs(buf)
        else:
            i += 1
    return "\n".join(out)


def paragraphs(buf):
    """Render a run of non-empty lines: bullet/numbered lists or a paragraph."""
    out = []
    if any(re.match(r"^\s*[-*] ", b) for b in buf):
        out.append("\\begin{itemize}")
        item = []
        for b in buf:
            m = re.match(r"^\s*[-*] (.*)$", b)
            if m:
                if item:
                    out.append("  \\item " + inline(" ".join(item)))
                item = [m.group(1)]
            else:
                item.append(b.strip())
        if item:
            out.append("  \\item " + inline(" ".join(item)))
        out.append("\\end{itemize}")
    elif any(re.match(r"^\s*\d+\. ", b) for b in buf):
        out.append("\\begin{enumerate}")
        item = []
        for b in buf:
            m = re.match(r"^\s*\d+\. (.*)$", b)
            if m:
                if item:
                    out.append("  \\item " + inline(" ".join(item)))
                item = [m.group(1)]
            else:
                item.append(b.strip())
        if item:
            out.append("  \\item " + inline(" ".join(item)))
        out.append("\\end{enumerate}")
    else:
        out.append(inline(" ".join(b.strip() for b in buf)))
        out.append("")
    return out


PREAMBLE = r"""%% ACM SIGMETRICS 2027 -- Fall cycle submission (double anonymous)
%% Class line is mandated verbatim by the official CFP:
%%   \documentclass[acmsmall, screen, review]{acmart}
%% Generated by docs/paper/submission/scripts/md2tex.py from the frozen
%% manuscript %(frozen)s. Do not edit main.tex by hand -- edit the frozen
%% Markdown (which is closed) or the converter, and regenerate.
\documentclass[acmsmall, screen, review, anonymous]{acmart}

\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{tabularx}
%% wrapping, left-aligned variable-width column for wide text columns
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
%% Long machine identifiers (e.g. software_visible_completion_observation_cycles)
%% cannot break by default and overflow the text block. Allow hyphenation inside
%% \texttt and give TeX a little emergency stretch. Typesetting only.
\usepackage[htt]{hyphenat}
\emergencystretch=2em

%% Double-anonymous: no author, affiliation, funding or acknowledgement data is
%% present anywhere in this file. See ANONYMITY_AUDIT.md.
\settopmatter{printacmref=false}
\acmConference[SIGMETRICS '27]{ACM SIGMETRICS}{2027}{}
\acmISBN{}
\acmDOI{}
\copyrightyear{2027}
\acmYear{2027}
\setcopyright{none}

\begin{document}

\title{%(title)s}

"""


def main():
    md = frozen_source()
    title = md.split("\n", 1)[0].lstrip("# ").strip()
    tex = convert(md)
    doc = (PREAMBLE % {"title": inline(title), "frozen": FROZEN}) + tex + \
        "\n\n\\end{document}\n"
    with open(os.path.join(SUB, "main.tex"), "w") as fh:
        fh.write(doc)
    with open(os.path.join(SUB, "SECTION_TRACE.md"), "w") as fh:
        fh.write("# Markdown -> LaTeX section trace\n\n"
                 "Source: `%s:docs/paper/MANUSCRIPT.md`\n\n"
                 "| markdown | latex |\n| --- | --- |\n" % FROZEN)
        for a, b in TRACE:
            fh.write("| `%s` | `%s` |\n" % (a, b))
    print("wrote main.tex (%d lines) and SECTION_TRACE.md (%d sections)"
          % (doc.count("\n"), len(TRACE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
