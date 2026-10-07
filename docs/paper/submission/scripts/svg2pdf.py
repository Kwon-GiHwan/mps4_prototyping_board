#!/usr/bin/env python3
"""Deterministic SVG -> vector PDF for the submission layer (SE1, section 7).

The five authoritative SVGs under docs/paper/figures/ are NOT modified. This
script derives a vector PDF for each into docs/paper/submission/figures/ and
records source/derived digests and dimensions.

svglib + reportlab is used because it is pure Python (no native cairo/inkscape
dependency) and produces true vector output -- no rasterization, so figure text
remains selectable and scalable.
"""
import hashlib, json, os, sys
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# ACM/TAPS expects every font embedded. ReportLab would otherwise reference the
# non-embedded base-14 Helvetica for the figures' sans-serif text. Arimo is
# metric-compatible with Helvetica/Arial and Apache-2.0 licensed, so embedding
# it keeps the layout identical and the PDF self-contained.
_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", "..", ".."))
ARIMO = os.path.join(_REPO,
    ".toolchain/TinyTeX/TinyTeX/texmf-dist/fonts/truetype/google/arimo")


def register_fonts():
    faces = {"Helvetica": "Arimo-Regular.ttf",
             "Helvetica-Bold": "Arimo-Bold.ttf",
             "Helvetica-Oblique": "Arimo-Italic.ttf",
             "Helvetica-BoldOblique": "Arimo-BoldItalic.ttf"}
    for name, fn in faces.items():
        path = os.path.join(ARIMO, fn)
        if not os.path.exists(path):
            print("WARNING: %s not found; falling back to base-14 (not embedded)"
                  % fn)
            return False
        pdfmetrics.registerFont(TTFont(name, path))
    addMapping("Helvetica", 0, 0, "Helvetica")
    addMapping("Helvetica", 1, 0, "Helvetica-Bold")
    addMapping("Helvetica", 0, 1, "Helvetica-Oblique")
    addMapping("Helvetica", 1, 1, "Helvetica-BoldOblique")
    # ReportLab's canvas default is Times-Roman; every text element in these
    # figures sets a sans family, so the default is declared but never drawn.
    # Point it at the embedded face too, so no non-embedded font is referenced.
    for nm in ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"):
        pdfmetrics.registerFont(TTFont(nm, os.path.join(ARIMO, "Arimo-Regular.ttf")))
    return True

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.dirname(HERE)
PAPER = os.path.dirname(SUB)
SRC = os.path.join(PAPER, "figures")
DST = os.path.join(SUB, "figures")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    embedded = register_fonts()
    os.makedirs(DST, exist_ok=True)
    rec = []
    for f in sorted(os.listdir(SRC)):
        if not f.endswith(".svg"):
            continue
        s = os.path.join(SRC, f)
        d = os.path.join(DST, f[:-4] + ".pdf")
        drawing = svg2rlg(s)
        renderPDF.drawToFile(drawing, d)
        rec.append({
            "figure": f[:-4],
            "source_svg": os.path.relpath(s, PAPER),
            "source_sha256": sha(s),
            "derived_pdf": os.path.relpath(d, SUB),
            "derived_sha256": sha(d),
            "width_pt": round(drawing.width, 2),
            "height_pt": round(drawing.height, 2),
            "vector": True,
            "rasterized": False,
            "fonts_embedded": embedded,
            "font_substitution": ("Helvetica -> Arimo (metric-compatible, "
                                  "Apache-2.0) so the PDF embeds all fonts"
                                  if embedded else "none"),
        })
        print("%-34s -> %-34s %.0fx%.0f pt" %
              (f, os.path.basename(d), drawing.width, drawing.height))
    with open(os.path.join(SUB, "FIGURE_CONVERSION.json"), "w") as fh:
        json.dump({"converter": "svglib+reportlab, pure Python, vector",
                   "sources_modified": False, "figures": rec}, fh, indent=1)
    print("wrote FIGURE_CONVERSION.json (%d figures)" % len(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
