#!/usr/bin/env python3
"""Stage 6-M (evidence/stage6m/contract.md §1–2): facts for the board-free model-level reassessment. Recompiles each of the
seven original MLEK models with the packer's MLEK Vela options (unchanged, the same call as
stage6b_revision_a_models.original) and records the source sha256, the Vela output sha256, every Ethos-U command stream's
sha256 and the register state at every kernel instruction (cms_regs.kernels). No new shape, no Vela option change, no rule.

  python3 stage6m_models.py kernels <out.json>
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
import cms_regs  # noqa: E402
from stage6b_models import MLEK, SOURCES  # noqa: E402

MODELS = ("kws_micronet_m", "ad_medium_int8", "mobilenet_v2_1.0_224_INT8", "vww4_128_128_INT8", "rnnoise_INT8",
          "yolo-fastest_192_face_v4", "wav2letter_pruned_int8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def facts(model: str) -> dict:
    from pack_vela_workload import VELA_OPTIONS, extract_cms
    import tflite
    src = MLEK / SOURCES[model] / f"{model}.tflite"
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", str(src), *VELA_OPTIONS, "--output-dir", d], check=True, capture_output=True)
        blob = open(glob.glob(os.path.join(d, "*_vela.tflite"))[0], "rb").read()
    m = tflite.Model.GetRootAsModel(blob, 0); g = m.Subgraphs(0)
    eu = [g.Operators(k) for k in range(g.OperatorsLength())
          if (m.OperatorCodes(g.Operators(k).OpcodeIndex()).CustomCode() or b"").startswith(b"ethos-u")]
    streams = [extract_cms(m.Buffers(g.Tensors(op.Inputs(0)).Buffer()).DataAsNumpy().tobytes()) for op in eu]
    return dict(model_sha256=sha(src.read_bytes()), vela_sha256=sha(blob), vela_options=list(VELA_OPTIONS),
                n_ethosu_ops=len(eu), cms_sha256=[sha(s) for s in streams],
                kernels=[cms_regs.kernels(s) for s in streams])


if __name__ == "__main__":
    cmd, out = sys.argv[1], pathlib.Path(sys.argv[2])
    assert cmd == "kernels", cmd
    out.write_text(json.dumps({mdl: facts(mdl) for mdl in MODELS}, indent=1, sort_keys=True))
    print(out, sha(out.read_bytes()))
