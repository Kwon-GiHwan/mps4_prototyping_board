#!/usr/bin/env python3
"""P0-E2 stage 3: assemble the analyzer view for the two new workloads and
bundle the evidence. Launch enumeration reuses assemble_view.py's decoder."""
import json, os, shutil, sys
sys.path.insert(0, "/tmp")
from insert_irq import decode_cms, parse_payload, CMD0, OP_LAUNCH
from ethosu.vela.tflite.Model import Model

OUT = "/work/u85e2"; PD = OUT + "/pd"; ART = OUT + "/artifacts"; V = OUT + "/view"

def launch_list(art):
    m = Model.GetRootAsModel(open(art, "rb").read(), 0)
    sg = m.Subgraphs(0)
    for i in range(sg.OperatorsLength()):
        oc = m.OperatorCodes(sg.Operators(i).OpcodeIndex())
        if oc.CustomCode() and b"ethos-u" in oc.CustomCode().lower():
            t = sg.Tensors(sg.Operators(i).Inputs(0))
            pay = bytes(m.Buffers(t.Buffer()).DataAsNumpy().tobytes())
            _, _, cms, _ = parse_payload(pay)
            out, off = [], 0
            for c, o, _, _ in decode_cms(cms):
                if c == 0 and CMD0[o] in OP_LAUNCH:
                    out.append([off, CMD0[o].replace("CMD0_OPCODE_NPU_OP_", "")])
                off += 4 if c == 0 else 8
            return out

def stream_irq_count(art):
    """NPU_OP_IRQ opcodes actually present in a written command stream."""
    m = Model.GetRootAsModel(open(art, "rb").read(), 0)
    sg = m.Subgraphs(0)
    for i in range(sg.OperatorsLength()):
        oc = m.OperatorCodes(sg.Operators(i).OpcodeIndex())
        if oc.CustomCode() and b"ethos-u" in oc.CustomCode().lower():
            t = sg.Tensors(sg.Operators(i).Inputs(0))
            pay = bytes(m.Buffers(t.Buffer()).DataAsNumpy().tobytes())
            _, _, cms, _ = parse_payload(pay)
            return sum(1 for c, o, _, _ in decode_cms(cms)
                       if c == 0 and CMD0[o] == "CMD0_OPCODE_NPU_OP_IRQ")

cells = json.load(open(OUT + "/cells.json"))
shutil.rmtree(V, ignore_errors=True)
summary = []
for c in cells:
    cell = c["cell"]; s = os.path.join(PD, cell); d = os.path.join(V, cell)
    os.makedirs(d)
    shutil.copy2(os.path.join(s, "debug.xml"), d)
    os.makedirs(os.path.join(d, "vela_verbose"))
    shutil.copy2(os.path.join(s, "vela_verbose", "verbose.log"),
                 os.path.join(d, "vela_verbose"))
    for f in ("clean.run1.json", "prof.run1.json", "instr.meta.json"):
        shutil.copy2(os.path.join(s, f), d)
    json.dump(launch_list(c["art"]), open(os.path.join(d, "launches.json"), "w"))
    rec = {"cell": cell, "model": c["model"], "binding": c["label"],
           "macs": c["macs"], "system_config": c["syscfg"],
           "vela_sha256": c["vela_sha"],
           "instr_status": c["meta"]["profiled"],
           "irq_count": c["meta"]["irq_count"],
           "instr_sha256": c["meta"]["instr_sha256"],
           "stream_irq_count_clean": stream_irq_count(c["art"]),
           "stream_irq_count_instr": stream_irq_count(c["instr"]),
           "clean_build": json.load(open(os.path.join(s, "clean.build.json"))),
           "prof_build": json.load(open(os.path.join(s, "prof.build.json"))),
           "runs": {}}
    for arm in ("clean", "prof"):
        rec["runs"][arm] = [json.load(open(os.path.join(s, "%s.run%d.json" % (arm, r))))
                            for r in (1, 2, 3)]
    summary.append(rec)
    print("[view]", cell, "launches", len(json.load(open(os.path.join(d, "launches.json")))),
          "stream_irq", rec["stream_irq_count_instr"])

json.dump(summary, open(OUT + "/summary.json", "w"), indent=1)
os.system("cd %s && tar czf /work/u85e2_bundle.tar.gz view summary.json cells.json "
          "PRESTATE.sha256 stage2.log" % OUT)
print("BUNDLE /work/u85e2_bundle.tar.gz")
