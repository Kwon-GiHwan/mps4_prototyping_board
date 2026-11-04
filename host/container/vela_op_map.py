#!/usr/bin/env python3
"""Map every kernel operation of a model's NPU command stream to Vela's optimised operator and the original TFLite
operator, from Vela's debug database (`--enable-debug-db`). POST_HOC_DESCRIPTIVE; compile-time only.

Runs in the benchmark-runner container (vela, tflite):

  python3 vela_op_map.py <out dir> <model.tflite>...

Per model: <out dir>/<model>.op_map.csv (one row per command-stream kernel op) and <model>.cms.sha256 (the command
stream of this compile, to compare with the measured blob). Vela options = pack_vela_workload.VELA_OPTIONS.
<model>.stages.csv counts kernel work at each Vela stage per operator name: optimised operators (graph optimiser),
high-level kernel commands (scheduler; `--verbose-high-level-command-stream`, non-DMA lines) and command-stream kernel
ops (register command stream generator). Debug-db tables used: `queue` (command-stream byte offset -> optimised_id), `optimised` (id -> source_id, operator),
`source` (id -> TFLite operator).
"""
import csv, glob, hashlib, os, pathlib, subprocess, sys, tempfile
import re
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import cms  # noqa: E402
from pack_vela_workload import VELA_OPTIONS, inspect_vela  # noqa: E402


def tables(xml_path):
    """{table name: [row dict, ...]}; each table body is CSV text."""
    out = {}
    for tb in ET.parse(xml_path).getroot().iter("table"):
        text = (tb.text or "").strip()
        out[tb.get("name")] = list(csv.DictReader(text.splitlines())) if text else []
    return out


HLC = re.compile(r"^\d+ (\S+) OFM area ")


def hlc_ops(log):
    """Operator name of each kernel command of the high-level command stream, in order."""
    text = log.split("High level command stream:", 1)[1]
    return [m.group(1) for m in (HLC.match(line) for line in text.splitlines()) if m]


def stages(rows, hl):
    """Per optimised-operator name: optimised operators that reach the stream, high-level commands, stream ops."""
    names = sorted({r["optimised_op"] for r in rows} | set(hl))
    return [dict(operator=n, optimised_ops=len({r["optimised_id"] for r in rows if r["optimised_op"] == n}),
                 hl_commands=hl.count(n), stream_ops=sum(r["optimised_op"] == n for r in rows)) for n in names]


def op_map(stream, t):
    queue = {int(r["offset"]): r for r in t["queue"]}
    opt = {r["id"]: r for r in t["optimised"]}
    src = {r["id"]: r for r in t["source"]}
    offs = cms.kernel_offsets(stream)
    if sorted(queue) != offs:
        raise SystemExit(f"debug-db queue offsets {sorted(queue)[:5]}... != command-stream kernel ops {offs[:5]}...")
    rows = []
    for i, (off, typ) in enumerate(zip(offs, cms.kernel_types(stream))):
        o = opt[queue[off]["optimised_id"]]
        s = src.get(o["source_id"], {})
        rows.append(dict(index=i, offset=off, stream_op=typ, optimised_id=o["id"], optimised_op=o["operator"],
                         ofm_hwc=f'{o["ofm_h"]}x{o["ofm_w"]}x{o["ofm_d"]}', source_id=o["source_id"],
                         source_op=s.get("operator", "")))
    return rows


def main(out, *models):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    for model in models:
        name = pathlib.Path(model).stem
        with tempfile.TemporaryDirectory() as d:
            log = subprocess.run(["vela", model, *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db",
                                  "--verbose-high-level-command-stream"], check=True, capture_output=True, text=True).stdout
            stream = inspect_vela(glob.glob(os.path.join(d, "*_vela.tflite"))[0])["cms"]
            rows = op_map(stream, tables(glob.glob(os.path.join(d, "*_debug.xml"))[0]))
        for kind, rs in (("op_map", rows), ("stages", stages(rows, hlc_ops(log)))):
            with open(out / f"{name}.{kind}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n"); w.writeheader(); w.writerows(rs)
        (out / f"{name}.cms.sha256").write_text(hashlib.sha256(stream).hexdigest() + "\n")
        print(name, len(rows), "kernel ops")


if __name__ == "__main__":
    main(*sys.argv[1:])
