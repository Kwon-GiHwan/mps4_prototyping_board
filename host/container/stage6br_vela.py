#!/usr/bin/env python3
"""Stage 6B-R: Vela's full performance summary (every CSV field, bytes included) for the Revision A A2 compiles, with
the same options; the Vela output must equal the record's vela_sha256. Facts only.

  stage6br_vela.py <compile dir> <out.json> <group>...
"""
import csv, glob, hashlib, json, os, pathlib, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pack_vela_workload import VELA_OPTIONS  # noqa: E402


def main(cdir: str, out: str, groups: list) -> None:
    res = {}
    for g in groups:
        rec = json.loads(pathlib.Path(cdir, f"s6b_{g.lower()}.ra.json").read_text())["forms"]["A2"]
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["vela", str(pathlib.Path(cdir, f"s6b_{g.lower()}_f_ctx_self.tflite")), *VELA_OPTIONS,
                            "--output-dir", d], check=True, capture_output=True)
            blob = open(glob.glob(os.path.join(d, "*_vela.tflite"))[0], "rb").read()
            row = next(csv.DictReader(open(glob.glob(os.path.join(d, "*_summary_*.csv"))[0])))
        h = hashlib.sha256(blob).hexdigest()
        res[g] = dict(vela_sha256=h, vela_equals_record=h == rec["vela_sha256"], summary=row, options=VELA_OPTIONS)
        print(g, res[g]["vela_equals_record"], flush=True)
    pathlib.Path(out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
