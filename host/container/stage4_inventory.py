#!/usr/bin/env python3
"""Stage 4 Phase 0: operator / shape inventory of the seven MLEK models from Vela's own compile record. Compile-time
only (POST_HOC_DESCRIPTIVE); nothing here is measured on the board.

Runs in the benchmark-runner container (vela 5.0.0, tflite):

  python3 stage4_inventory.py <out.csv> <model.tflite>...

Vela options = pack_vela_workload.VELA_OPTIONS (MLEK's for ethos-u85-1024, Dedicated_Sram, SYS_DRAM_Mid_1024) plus
--enable-debug-db. One row per Vela scheduled operation (what runs on the NPU), joined to the TFLite operator it came
from (the debug database's `source.ext_key` = the TFLite operator index, checked against the operator type) — the two
are kept in separate columns because they differ (fused activations, MemoryCopy for Concat, Reshape removed, ...).
TFLite operators that have no scheduled NPU operation of their own are listed with npu_op empty and `cpu` = 1 when
they stay in the Vela output as CPU operators.
"""
import csv, glob, hashlib, os, pathlib, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

import tflite
from tflite.BuiltinOperator import BuiltinOperator

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pack_vela_workload import VELA_OPTIONS  # noqa: E402

OPNAME = {v: k for k, v in BuiltinOperator.__dict__.items() if not k.startswith("_")}
ACT = {0: "NONE", 1: "RELU", 2: "RELU_N1_TO_1", 3: "RELU6", 4: "TANH", 5: "SIGN_BIT"}


def tables(xml_path):
    out = {}
    for tb in ET.parse(xml_path).getroot().iter("table"):
        text = (tb.text or "").strip()
        out[tb.get("name")] = list(csv.DictReader(text.splitlines())) if text else []
    return out


def tflite_ops(path):
    """[(index, op name, [input shapes], [output shapes], options dict)] of subgraph 0."""
    m = tflite.Model.GetRootAsModel(open(path, "rb").read(), 0)
    g = m.Subgraphs(0)
    def shape(t):
        if t < 0:
            return ""
        x = g.Tensors(t)
        return "x".join(str(x.Shape(k)) for k in range(x.ShapeLength())) or "scalar"

    out = []
    for i in range(g.OperatorsLength()):
        op = g.Operators(i)
        code = m.OperatorCodes(op.OpcodeIndex())
        b = max(code.BuiltinCode(), code.DeprecatedBuiltinCode())
        name = OPNAME.get(b, str(b)) if b != BuiltinOperator.CUSTOM else "CUSTOM:" + code.CustomCode().decode()
        ins = [shape(op.Inputs(j)) for j in range(op.InputsLength())]
        outs = [shape(op.Outputs(j)) for j in range(op.OutputsLength())]
        opt = {}
        o = op.BuiltinOptions()
        if o is not None and name in ("CONV_2D", "DEPTHWISE_CONV_2D"):
            cls = tflite.Conv2DOptions if name == "CONV_2D" else tflite.DepthwiseConv2DOptions
            x = cls(); x.Init(o.Bytes, o.Pos)
            opt = dict(stride=f"{x.StrideH()}x{x.StrideW()}", padding="SAME" if x.Padding() == 0 else "VALID",
                       activation=x.FusedActivationFunction())
        elif o is not None and name == "FULLY_CONNECTED":
            x = tflite.FullyConnectedOptions(); x.Init(o.Bytes, o.Pos)
            opt = dict(activation=x.FusedActivationFunction())
        out.append((i, name, ins, outs, opt))
    return out


def main(out_csv, *models):
    rows = []
    for mp in models:
        model = pathlib.Path(mp).stem
        ops = tflite_ops(mp)
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["vela", mp, *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"], check=True,
                           capture_output=True)
            t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
            vela_out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
            cpu_ops = [o for o in tflite_ops(vela_out) if not o[1].startswith("CUSTOM:ethos-u")]
            vela_sha = hashlib.sha256(open(vela_out, "rb").read()).hexdigest()
        src = {r["id"]: r for r in t["source"]}
        dbg = {r["id"]: r for r in t["perf_debug"]}
        main_ = {r["id"]: r for r in t["perf_debug_main"]}
        offsets = {}
        for q in t["queue"]:
            offsets.setdefault(q["scheduled_id"], []).append(int(q["offset"]))
        seen = set()
        for p in t["perf"]:
            s = src.get(p["source_id"], {})
            idx = int(s["ext_key"]) if s.get("ext_key", "") != "" else None
            to = ops[idx] if idx is not None and idx < len(ops) else None
            seen.add(idx)
            dq, mq = dbg.get(p["id"], {}), main_.get(p["id"], {})
            hwc = lambda pre: "x".join(dq.get(f"{pre}_shape_{a}", "") for a in "hwc")
            rows.append(dict(
                model=model, vela_sha256=vela_sha[:16], scheduled_id=p["id"], tflite_op_index=idx,
                tflite_op=to[1] if to else "", source_op=s.get("operator", ""), npu_op=p["operator"],
                tflite_inputs=";".join(to[2]) if to else "", tflite_outputs=";".join(to[3]) if to else "",
                npu_ifm_hwc=hwc("ifm"), npu_ofm_hwc=hwc("ofm"),
                kernel=f"{dq.get('kernel_size_y', '')}x{dq.get('kernel_size_x', '')}",
                stride=f"{dq.get('kernel_stride_y', '')}x{dq.get('kernel_stride_x', '')}",
                padding="t{}b{}l{}r{}".format(*(dq.get(f"kernel_padding_{k}", "") for k in "TBLR")),
                tflite_stride=to[4].get("stride", "") if to else "", tflite_padding=to[4].get("padding", "") if to else "",
                tflite_activation=ACT.get(to[4].get("activation"), "") if to else "",
                depth_multiplier=dq.get("kernel_depth_multiplier", ""),
                cin=dq.get("ifm_shape_c", ""), cout=dq.get("ofm_shape_c", ""), mac_count=p["mac_count"],
                vela_op_cycles=p["op_cycles"], vela_npu_cycles=p["npu_cycles"], vela_mac_cycles=mq.get("mac_cycles", ""),
                vela_ao_cycles=mq.get("ao_cycles", ""), vela_cmd_cycles=mq.get("cmd_cycles", ""),
                ofm_block="x".join(mq.get(f"ofm_block_{a}", "") for a in "hwc"),
                ifm_block="x".join(mq.get(f"ifm_block_{a}", "") for a in "hwc"),
                ofm_ublock="x".join(mq.get(f"ofm_ublock_{a}", "") for a in "hwc"), traversal=mq.get("traversal", ""),
                cascade=dq.get("cascade", ""), fused_names=p["name"].count(";") + 1 if p["name"] else 0,
                ifm_memory=dq.get("ifm_memory", ""), ofm_memory=dq.get("ofm_memory", ""),
                ifm_format=dq.get("ifm_format", ""), ofm_format=dq.get("ofm_format", ""),
                weight_bytes=dq.get("weight_total_bytes", ""), staging_usage=p["staging_usage"],
                sram_ac=p["Sram_ac"], dram_ac=p["Dram_ac"],
                cms_offsets=" ".join(str(o) for o in sorted(offsets.get(p["id"], []))), cpu=0, name=p["name"]))
        for o in ops:
            if o[0] not in seen:
                rows.append(dict(model=model, vela_sha256=vela_sha[:16], tflite_op_index=o[0], tflite_op=o[1],
                                 tflite_inputs=";".join(o[2]), tflite_outputs=";".join(o[3]),
                                 tflite_stride=o[4].get("stride", ""), tflite_padding=o[4].get("padding", ""),
                                 cpu=int(any(c[1] == o[1] and c[3] == o[3] for c in cpu_ops))))
    keys = list(rows[0])
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(out_csv, len(rows), "rows")


if __name__ == "__main__":
    main(*sys.argv[1:])
