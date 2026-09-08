#!/usr/bin/env python3
"""Inventory every frozen artifact this audit reads. Read-only."""
import csv, hashlib, os, json
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.dirname(HERE)
PAPER=os.path.dirname(OUT); P=os.path.join(OUT,"provenance")

KIND=[("analysis/board_rq3/","board derived result","board PMU"),
      ("analysis/","derived frozen result","FVP whole-model PMU"),
      ("evidence/vela-matrix","Vela summary CSV","compiler estimate"),
      ("evidence/executability","executability result","build outcome"),
      ("evidence/stage","stage evidence (parsed JSON + tarball)","FVP whole-model PMU"),
      ("evidence/board","board stage evidence","board PMU"),
      ("evidence/fpga","fpga build evidence","build metadata"),
      ("evidence/pre-sweep","qualification evidence","FVP whole-model PMU"),
      ("evidence/fvp-qual","qualification evidence","FVP whole-model PMU"),
      ("evidence/","frozen evidence","mixed"),
      ("mechanism/","mechanism derived result","per-layer / IRQ profiling PMU"),
      ("platform_sensitivity/","platform-sensitivity result","FVP whole-model PMU")]
def classify(rel):
    for pre,kind,mt in KIND:
        if rel.startswith(pre): return kind,mt
    return "other",""
def sha(p):
    try:
        with open(p,"rb") as f: return hashlib.sha256(f.read()).hexdigest()
    except OSError: return ""

rows=[]
for base in ("analysis","evidence","mechanism","platform_sensitivity"):
    for dp,_,fs in os.walk(os.path.join(PAPER,base)):
        for fn in sorted(fs):
            full=os.path.join(dp,fn); rel=os.path.relpath(full,PAPER)
            kind,mt=classify(rel)
            ext=os.path.splitext(fn)[1].lower()
            rows.append(dict(artifact_type=kind, path="docs/paper/"+rel,
                sha256=sha(full), source_stage=rel.split("/")[1] if "/" in rel else "",
                platform="", npu="", mac="", workload="", memory_mode="",
                system_config="", timing_adapter="", measurement_type=mt,
                file_ext=ext, size_bytes=os.path.getsize(full),
                notes="read-only input"))
rows.sort(key=lambda r:r["path"])
cols=["artifact_type","path","sha256","source_stage","platform","npu","mac","workload",
      "memory_mode","system_config","timing_adapter","measurement_type","file_ext",
      "size_bytes","notes"]
with open(os.path.join(P,"INPUT_MANIFEST.csv"),"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)

tools=[dict(component="Vela", version="5.0.0", source="vela_matrix.csv vela_version"),
  dict(component="Vela core clock (U85 Mid_512)", version="1000000000.0 Hz", source="vela_matrix.csv"),
  dict(component="FVP SSE-300", version="11.22.35", source="MAIN_EXPERIMENT_MATRIX.md"),
  dict(component="FVP SSE-310", version="11.24.13", source="MAIN_EXPERIMENT_MATRIX.md"),
  dict(component="FVP SSE-315", version="11.31.28", source="MAIN_EXPERIMENT_MATRIX.md"),
  dict(component="FVP SSE-320", version="11.27.25", source="MAIN_EXPERIMENT_MATRIX.md"),
  dict(component="SOURCE_DATE_EPOCH", version="1776763519 (2026-04-21 09:25:19 UTC)", source="stage1.py"),
  dict(component="activation buffer", version="0x00200000", source="stage1.py"),
  dict(component="MLEK git commit", version="NOT_VERIFIED_LOCALLY", source="remote host only"),
  dict(component="arm-none-eabi-gcc", version="NOT_VERIFIED_LOCALLY", source="remote host only"),
  dict(component="TA_CONFIG_FILE", version="NOT_VERIFIED_LOCALLY", source="remote host only")]
with open(os.path.join(P,"TOOL_VERSIONS.csv"),"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["component","version","source"]); w.writeheader(); w.writerows(tools)
print("manifest rows:", len(rows), "| tool rows:", len(tools))
