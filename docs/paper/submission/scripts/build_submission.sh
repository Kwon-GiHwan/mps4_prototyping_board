#!/bin/sh
# Deterministic submission build (SE1, section 4).
# One command; no manual sequence to reproduce.
#
#   ./docs/paper/submission/scripts/build_submission.sh
#
# Toolchain is project-local and pinned (.toolchain/TinyTeX); the host is not
# modified globally and nothing is installed system-wide.
set -e
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
SUB="$REPO/docs/paper/submission"
TEX="$REPO/.toolchain/TinyTeX/TinyTeX/bin/universal-darwin"

[ -x "$TEX/latexmk" ] || { echo "toolchain missing: $TEX"; exit 1; }
export PATH="$TEX:$PATH"

# 1. regenerate the figure PDFs from the authoritative SVGs
VENV="${SVG_VENV:-/private/tmp/claude-501/-Users-gihwan-Documents-Projects-mps4-prototyping-board/cacdc52d-41ab-4b19-8701-3b76597632c2/scratchpad/pdfvenv}"
if [ -x "$VENV/bin/python" ]; then
  "$VENV/bin/python" "$SUB/scripts/svg2pdf.py"
else
  echo "note: svg venv absent, reusing existing figures/*.pdf"
fi

# 2. regenerate main.tex from the FROZEN manuscript (never the working tree)
python3 "$SUB/scripts/md2tex.py"

# 3. build, with SOURCE_DATE_EPOCH pinned so the PDF is reproducible
export SOURCE_DATE_EPOCH="$(git -C "$REPO" show -s --format=%ct d137a7d)"
export FORCE_SOURCE_DATE=1
cd "$SUB"
latexmk -pdf -interaction=nonstopmode -halt-on-error \
        -outdir=build -jobname=paper-review main.tex
echo
echo "built: $SUB/build/paper-review.pdf"
