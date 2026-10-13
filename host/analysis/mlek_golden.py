#!/usr/bin/env python3
"""MLEK FI101 golden -> manifest entry, under the golden-validity checks G1-G5 of amendment 2
(docs/specs/mlek-baseline.md). A golden that fails any check gets no entry.

  python3 host/analysis/mlek_golden.py <app_uart.raw> <blob meta .pmwl.json> <MLEK Vela output sha256>
      <tflite_ofm.bin> <frozen manifest.json> <workload> <out entry.json>

The blob is the packer's output for --ifm <dumped input> --golden <dumped output>; its meta carries the model, Vela
output, cms, IFM, golden and tflite_runtime OFM digests. tflite_ofm.bin is tflite_runtime on the same input and is
used only for the numerical-difference diagnostic.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ofm_compare import IFM_MARK, OFM_MARK, compare, section

TA_LINES = ("Configured TA_SRAM\t@0x51102000", "Configured TA_EXT\t@0x51102400")
SOURCE = "MLEK b2c0bb2 inference_runner on FI101, VERIFY_TEST_OUTPUT dump (amendment 2)"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def validity(text: str, meta: dict, frozen: dict, mlek_vela_sha256: str) -> dict:
    """G1-G5 for one MLEK capture (text = app UART, CR removed) against the packed blob's meta."""
    ifm, ofm = section(text, IFM_MARK), section(text, OFM_MARK)
    return {
        "G1_lengths": len(ifm) == meta["ifm_len"] and len(ofm) == meta["ofm_len"],
        "G2_same_vela_output": mlek_vela_sha256 == meta["vela_sha256"],
        "G3_ta_configured": all(t in text for t in TA_LINES),
        "G4_model_and_cms_unchanged": (meta["model_sha256"] == frozen["model_sha256"]
                                       and meta["cms_sha256"] == frozen["cms_sha256"]),
        "G5_blob_holds_dump": meta["ifm_sha256"] == sha(ifm) and meta["golden_sha256"] == sha(ofm),
    }


def entry(text: str, meta: dict, frozen: dict, mlek_vela_sha256: str, tflite_ofm: bytes) -> dict:
    """The amendment-2 manifest entry; raises ValueError naming the failed checks."""
    g = validity(text, meta, frozen, mlek_vela_sha256)
    if not all(g.values()):
        raise ValueError("golden rejected: " + ", ".join(k for k, ok in g.items() if not ok))
    if sha(tflite_ofm) != meta["tflite_ofm_sha256"]:
        raise ValueError("tflite_ofm.bin is not the packer's tflite_runtime OFM for this input")
    ofm = section(text, OFM_MARK)
    diag = compare(ofm, tflite_ofm)
    e = dict(frozen, blob_sha256=meta["blob_sha256"], golden={
        "source": SOURCE, "input_sha256": meta["ifm_sha256"], "ofm_sha256": meta["golden_sha256"]})
    e.update(output_correctness="byte-exact vs MLEK FI101 golden (amendment 2)", ifm_seed=None,
             mlek_vela_sha256=mlek_vela_sha256, golden_validity=g,
             numerical_difference_diagnostic={
                 "vs": "tflite_runtime", "tflite_ofm_sha256": meta["tflite_ofm_sha256"],
                 "mismatch_count": diag["mismatch_count"], "positions": diag["positions"],
                 "signed_diff_mlek_minus_tflite": diag["signed_diff_a_minus_b"],
                 "max_abs_diff": diag["max_abs_diff"]})
    return e


def main() -> int:
    uart, meta, vsha, tfl, frozen, name, out = sys.argv[1:8]
    text = pathlib.Path(uart).read_bytes().decode("ascii", "replace").replace("\r", "")
    fz = json.loads(pathlib.Path(frozen).read_text())["workloads"][name]
    try:
        e = entry(text, json.loads(pathlib.Path(meta).read_text()), fz, vsha, pathlib.Path(tfl).read_bytes())
    except ValueError as err:
        print(f"{name}: {err}")
        return 1
    pathlib.Path(out).write_text(json.dumps(e, indent=1))
    d = e["numerical_difference_diagnostic"]
    print(f"{name}: G1-G5 pass; vs TFLite {d['mismatch_count']} bytes, max |diff| {d['max_abs_diff']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
