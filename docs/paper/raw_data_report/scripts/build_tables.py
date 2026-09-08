#!/usr/bin/env python3
"""Raw-data audit: regenerate every table from frozen evidence.

Read-only on all inputs. Nothing outside docs/paper/raw_data_report/ is written.
Missing values stay empty or NOT_EVALUABLE -- never 0.
"""
import csv, hashlib, json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.dirname(HERE)
PAPER= os.path.dirname(OUT)
T    = os.path.join(OUT, "tables")
P    = os.path.join(OUT, "provenance")
for d in (T, P): os.makedirs(d, exist_ok=True)

def rd(rel):
    with open(os.path.join(PAPER, rel)) as f: return list(csv.DictReader(f))
def wr(name, rows, cols):
    with open(os.path.join(T, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    return len(rows)
def sha(p):
    try:
        with open(p,"rb") as f: return hashlib.sha256(f.read()).hexdigest()
    except OSError: return ""

# ---- frozen inputs -------------------------------------------------------
EXEC = rd("analysis/executability.csv")
CELLS= rd("analysis/canonical_cells.csv")
SCAL = rd("analysis/scaling.csv")
SAT  = rd("analysis/saturation.csv")
VELA = [r for r in rd("evidence/vela-matrix-20260824/vela_matrix.csv") if r["success"]=="True"]
VFA  = rd("analysis/vela_fvp_trend_agreement.csv")
DIFF = rd("mechanism/U85_256_512_DIFFERENTIAL.csv")
ATTR = rd("mechanism/U85_ATTRIBUTION_UNITS.csv")
FMTX = rd("mechanism/U85_FORMAL_MATRIX.csv")

FVP_VER = {"SSE-300":"11.22.35","SSE-310":"11.24.13","SSE-315":"11.31.28","SSE-320":"11.27.25"}
FVP_BIN = {("SSE-300","ethos-u55"):"FVP_Corstone_SSE-300_Ethos-U55",
           ("SSE-300","ethos-u65"):"FVP_Corstone_SSE-300_Ethos-U65",
           ("SSE-310","ethos-u55"):"FVP_Corstone_SSE-310",
           ("SSE-310","ethos-u65"):"FVP_Corstone_SSE-310_Ethos-U65",
           ("SSE-315","ethos-u65"):"FVP_Corstone_SSE-315",
           ("SSE-320","ethos-u85"):"FVP_Corstone_SSE-320"}
# TA config file selection is a build-time MLEK choice; not present in local
# frozen evidence. Recorded as unverified rather than guessed.
TA_FILE = "NOT_VERIFIED_LOCALLY"

n_files = {}

# =========================================================================
# 3.1-A platform / configuration matrix
# =========================================================================
syscfg = {(r["platform"],r["npu"],int(r["mac_config"])): (r["system_config"], r["memory_mode"])
          for r in VELA}
rows=[]
seen=set()
for r in EXEC:
    k=(r["platform"], r["npu"], int(r["mac_config"]))
    if k in seen: continue
    seen.add(k)
    sc, mm = syscfg.get(k, ("", r["memory_mode"]))
    cells=[x for x in EXEC if (x["platform"],x["npu"],int(x["mac_config"]))==k]
    ok=[x for x in cells if x["classification"]=="EXECUTABLE"]
    formal=[x for x in CELLS if (x["platform"],x["npu"],int(x["mac_config"]))==k]
    rows.append(dict(platform=k[0], corstone_sse=k[0], npu=k[1], mac=k[2],
        fvp_binary=FVP_BIN.get((k[0],k[1],),""), fast_models_version=FVP_VER.get(k[0],""),
        system_config=sc, memory_mode=mm,
        timing_adapter_enabled=r["timing_adapter"],
        ta_config_file=TA_FILE,
        workload_count=len(cells), executability_count=len(ok),
        formal_sample_count=len(formal)*3 if formal else 0,
        formal_cell_count=len(formal)))
rows.sort(key=lambda r:(r["platform"], r["npu"], r["mac"]))
n_files["3_1_platform_matrix.csv"]=wr("3_1_platform_matrix.csv", rows,
  ["platform","corstone_sse","npu","mac","fvp_binary","fast_models_version",
   "system_config","memory_mode","timing_adapter_enabled","ta_config_file",
   "workload_count","executability_count","formal_cell_count","formal_sample_count"])

# =========================================================================
# 3.1-B workload matrix  (config-dependent values kept per configuration)
# =========================================================================
TASK={"rnnoise_INT8":"noise reduction","kws_micronet_m":"keyword spotting",
      "ad_medium_int8":"anomaly detection","vww4_128_128_INT8":"visual wake word",
      "yolo-fastest_192_face_v4":"object detection",
      "mobilenet_v2_1.0_224_INT8":"image classification",
      "wav2letter_pruned_int8":"speech recognition",
      "dnn_s_quantized":"generic DNN (excluded from scaling)"}
SRC={"ad_medium_int8":"ad/ad_medium_int8.tflite","kws_micronet_m":"kws/kws_micronet_m.tflite",
     "mobilenet_v2_1.0_224_INT8":"img_class/mobilenet_v2_1.0_224_INT8.tflite",
     "rnnoise_INT8":"noise_reduction/rnnoise_INT8.tflite",
     "vww4_128_128_INT8":"vww/vww4_128_128_INT8.tflite",
     "wav2letter_pruned_int8":"asr/wav2letter_pruned_int8.tflite",
     "yolo-fastest_192_face_v4":"object_detection/yolo-fastest_192_face_v4.tflite"}
rows=[]
for r in VELA:
    w=r["model"]
    nx=[x for x in EXEC if x["workload"]==w and x["platform"]==r["platform"]
        and x["npu"]==r["npu"] and x["mac_config"]==r["mac_config"]]
    rows.append(dict(workload=w, task=TASK.get(w,""), model_file=SRC.get(w,""),
        model_sha256=r["model_sha256"], platform=r["platform"], npu=r["npu"],
        mac=int(r["mac_config"]), memory_mode=r["memory_mode"],
        system_config=r["system_config"],
        npu_operators=r["npu_operators"], cpu_operators=r["cpu_operators"],
        cpu_operator_pct=r["cpu_operator_pct"],
        vela_total_npu_encoded_weights=r["vela_total_npu_encoded_weights"],
        vela_sram_memory_used=r["vela_sram_memory_used"],
        vela_dram_memory_used=r["vela_dram_memory_used"],
        vela_artifact_sha256=r["output_sha256"],
        executability=(nx[0]["classification"] if nx else "NOT_IN_UNIVERSE"),
        input_shape="NOT_COLLECTED", output_shape="NOT_COLLECTED",
        dtype="INT8", total_macs="NOT_COLLECTED",
        operator_types="NOT_COLLECTED", dwconv_count="NOT_COLLECTED",
        vela_launch_count="NOT_COLLECTED",
        notes="shape/op-type/DWConv/launch counts are not present in local frozen evidence"))
rows.sort(key=lambda r:(r["workload"],r["platform"],r["npu"],r["mac"]))
n_files["3_1_workload_matrix.csv"]=wr("3_1_workload_matrix.csv", rows,
  ["workload","task","model_file","model_sha256","platform","npu","mac","memory_mode",
   "system_config","npu_operators","cpu_operators","cpu_operator_pct",
   "vela_total_npu_encoded_weights","vela_sram_memory_used","vela_dram_memory_used",
   "vela_artifact_sha256","executability","input_shape","output_shape","dtype",
   "total_macs","operator_types","dwconv_count","vela_launch_count","notes"])

# =========================================================================
# 3.1-C measurement availability
# =========================================================================
def whole_model_status(npu, field):
    s=[x for x in CELLS if x["npu"]==npu]
    if not s: return "NOT_COLLECTED"
    filled=sum(1 for x in s if x.get(field,"").strip())
    if filled==len(s): return "AVAILABLE"
    if filled==0:      return "PARSER_LOSS" if npu=="ethos-u85" else "NOT_COLLECTED"
    return "AVAILABLE_PARTIAL"
rows=[]
for plat,npu in sorted({(x["platform"],x["npu"]) for x in EXEC}):
    formal = any(x["platform"]==plat and x["npu"]==npu for x in CELLS)
    base = "AVAILABLE" if formal else "NOT_COLLECTED"
    u85  = (npu=="ethos-u85")
    rows.append(dict(platform=plat, npu=npu,
      TOTAL=base, ACTIVE=base,
      IDLE=(base if not formal else "AVAILABLE_DERIVED"),
      AXI0_RD=whole_model_status(npu,"axi0_rd_beats") if not u85 and formal else ("PARSER_LOSS" if u85 and formal else "NOT_COLLECTED"),
      AXI0_WR=whole_model_status(npu,"axi0_wr_beats") if not u85 and formal else ("PARSER_LOSS" if u85 and formal else "NOT_COLLECTED"),
      AXI1_RD=whole_model_status(npu,"axi1_rd_beats") if not u85 and formal else ("PARSER_LOSS" if u85 and formal else "NOT_COLLECTED"),
      AXI1_WR="NOT_COLLECTED",
      SRAM_RD=("AVAILABLE_PARTIAL" if u85 else "NOT_EVALUABLE"),
      SRAM_WR=("AVAILABLE_PARTIAL" if u85 else "NOT_EVALUABLE"),
      EXT_RD=("AVAILABLE_PARTIAL" if u85 else "NOT_EVALUABLE"),
      EXT_WR=("AVAILABLE_PARTIAL" if u85 else "NOT_EVALUABLE"),
      stall_counters="SEMANTICS_UNVERIFIED" if u85 else "NOT_COLLECTED",
      per_layer_cycles=("AVAILABLE" if u85 else "NOT_COLLECTED"),
      ublock_schedule=("AVAILABLE" if u85 else "NOT_COLLECTED"),
      notes=("whole-model memory fields empty in all %d U85 formal cells; the same "
             "event family is present in the mechanism dataset" % len([x for x in CELLS if x["npu"]=="ethos-u85"])) if u85
            else "AXI beats present in whole-model formal cells; SRAM/EXT names do not exist on this generation"))
n_files["3_1_measurement_availability.csv"]=wr("3_1_measurement_availability.csv", rows,
  ["platform","npu","TOTAL","ACTIVE","IDLE","AXI0_RD","AXI0_WR","AXI1_RD","AXI1_WR",
   "SRAM_RD","SRAM_WR","EXT_RD","EXT_WR","stall_counters","per_layer_cycles",
   "ublock_schedule","notes"])

# =========================================================================
# 3.2 whole-model PMU (long form)
# =========================================================================
rows=[]
for c in CELLS:
    u85 = c["npu"]=="ethos-u85"
    rows.append(dict(platform=c["platform"], npu=c["npu"], mac=int(c["mac_config"]),
      workload=c["workload"], memory_mode=c["memory_mode"],
      total_cycles=c["canonical_cycles"], active_cycles=c["npu_active_cycles"],
      idle_cycles=c["npu_idle_cycles"],
      memory_event_family=("SRAM/EXT (U85)" if u85 else "AXI0/AXI1 (U55/U65)"),
      rd_beats_0=c["axi0_rd_beats"], wr_beats_0=c["axi0_wr_beats"],
      rd_beats_1=c["axi1_rd_beats"], wr_beats_1="",
      source="analysis/canonical_cells.csv",
      status=("MEMORY_PARSER_LOSS" if u85 else "OK")))
rows.sort(key=lambda r:(r["platform"],r["npu"],r["mac"],r["workload"]))
n_files["3_2_whole_model_pmu.csv"]=wr("3_2_whole_model_pmu.csv", rows,
  ["platform","npu","mac","workload","memory_mode","total_cycles","active_cycles",
   "idle_cycles","memory_event_family","rd_beats_0","wr_beats_0","rd_beats_1",
   "wr_beats_1","source","status"])

# 3.2 traffic composition -- only where beats exist
rows=[]
for c in CELLS:
    if c["npu"]=="ethos-u85":
        rows.append(dict(platform=c["platform"], npu=c["npu"], mac=int(c["mac_config"]),
          workload=c["workload"], event_family="SRAM/EXT (U85)",
          port0_beats="", port1_beats="", total_beats="",
          port0_share="", port1_share="",
          active_over_total=round(int(c["npu_active_cycles"])/int(c["canonical_cycles"]),6),
          status="NOT_EVALUABLE", note="whole-model memory counters absent (parser loss)"))
        continue
    r0=int(c["axi0_rd_beats"])+int(c["axi0_wr_beats"]); r1=int(c["axi1_rd_beats"])
    tot=r0+r1
    rows.append(dict(platform=c["platform"], npu=c["npu"], mac=int(c["mac_config"]),
      workload=c["workload"], event_family="AXI0/AXI1 (U55/U65)",
      port0_beats=r0, port1_beats=r1, total_beats=tot,
      port0_share=round(r0/tot,6) if tot else "",
      port1_share=round(r1/tot,6) if tot else "",
      active_over_total=round(int(c["npu_active_cycles"])/int(c["canonical_cycles"]),6),
      status="OK",
      note="AXI1_WR not collected, so port1 is read-only; shares are of the collected subset"))
rows.sort(key=lambda r:(r["platform"],r["npu"],r["mac"],r["workload"]))
n_files["3_2_memory_traffic.csv"]=wr("3_2_memory_traffic.csv", rows,
  ["platform","npu","mac","workload","event_family","port0_beats","port1_beats",
   "total_beats","port0_share","port1_share","active_over_total","status","note"])

# 3.2 per-layer (mechanism dataset -- a different program from the formal sweep)
rows=[]
for a in ATTR:
    rows.append(dict(dataset="U85 mechanism (post-compilation IRQ instrumentation)",
      workload=a["workload"], binding=a["binding"], unit=a["unit"],
      launches=a["launches"], op_types=a["op_types"], ccnt=a["ccnt"], tail=a["tail"],
      active=a["evt_active"], sram_rd=a["evt_sram_rd"], sram_wr=a["evt_sram_wr"],
      ext_rd=a["evt_ext_rd"], ext_wr=a["evt_ext_wr"],
      source="mechanism/U85_ATTRIBUTION_UNITS.csv",
      note="NOT the formal sweep binary; do not merge with 3_2_whole_model_pmu.csv"))
n_files["3_2_per_layer_pmu.csv"]=wr("3_2_per_layer_pmu.csv", rows,
  ["dataset","workload","binding","unit","launches","op_types","ccnt","tail","active",
   "sram_rd","sram_wr","ext_rd","ext_wr","source","note"])

print(json.dumps(n_files, indent=1))

# =========================================================================
# 3.3 scaling -- recomputed from frozen cycles, nothing hard-coded
#
# Point source is canonical_cells.csv (the 74 measured formal cells) crossed with
# executability.csv (the TA-ON MAC grid), NOT analysis/scaling.csv. scaling.csv
# drops SSE-300/U55/wav2letter@256 -- a measured cell whose ladder baseline is
# non-executable -- and this audit must not lose a measured point.
# =========================================================================
SYS = {(r["platform"],r["npu"],int(r["mac_config"])): r["system_config"] for r in VELA}
MEM = {(r["platform"],r["npu"],int(r["mac_config"])): r["memory_mode"] for r in VELA}
CYC = {(c["platform"],c["npu"],c["workload"],int(c["mac_config"])): int(c["canonical_cycles"])
       for c in CELLS}
TAON = [e for e in EXEC if e["timing_adapter"]=="ON"]

rows=[]
for e in TAON:
    key=(e["platform"],e["npu"],e["workload"],int(e["mac_config"]))
    k3=(e["platform"],e["npu"],int(e["mac_config"]))
    rows.append(dict(platform=e["platform"], npu=e["npu"], workload=e["workload"],
      mac=int(e["mac_config"]), cycles=CYC.get(key,""),
      system_config=SYS.get(k3,""), memory_mode=MEM.get(k3,""), ta_config=TA_FILE,
      executability=e["classification"],
      source="analysis/canonical_cells.csv + analysis/executability.csv"))
rows.sort(key=lambda r:(r["platform"],r["npu"],r["workload"],r["mac"]))
n_files["3_3_cycles_by_mac.csv"]=wr("3_3_cycles_by_mac.csv", rows,
  ["platform","npu","workload","mac","cycles","system_config","memory_mode",
   "ta_config","executability","source"])

lad=collections.defaultdict(list)
for e in TAON:
    key=(e["platform"],e["npu"],e["workload"],int(e["mac_config"]))
    lad[(e["platform"],e["npu"],e["workload"])].append(
        (int(e["mac_config"]), e["classification"], CYC.get(key)))
trans=[]; summary=[]
for k,v in sorted(lad.items()):
    v.sort()
    ok=[(m,c) for m,st,c in v if st=="EXECUTABLE" and c is not None]
    base = ok[0] if ok else None
    n_imp=n_pla=n_rev=n_na=0
    for i in range(1,len(v)):
        pm,pst,pc = v[i-1]; m,st,c = v[i]
        kp=(k[0],k[1],pm); kn=(k[0],k[1],m)
        d=dict(platform=k[0],npu=k[1],workload=k[2],mac_prev=pm,mac_next=m,
               system_config_prev=SYS.get(kp,""), system_config_next=SYS.get(kn,""),
               system_config_changed=str(SYS.get(kp,"")!=SYS.get(kn,"")),
               memory_mode_changed=str(MEM.get(kp,"")!=MEM.get(kn,"")),
               ta_config_changed="NOT_VERIFIED_LOCALLY",
               source="analysis/canonical_cells.csv")
        if pst!="EXECUTABLE" or st!="EXECUTABLE" or pc is None or c is None:
            d.update(cycles_prev="",cycles_next="",cycle_delta="",cycle_delta_pct="",
                     adjacent_speedup="",incremental_efficiency="",
                     speedup_vs_base="",cumulative_efficiency="",
                     transition_status="NOT_AVAILABLE",legacy_saturation_rule="")
            n_na+=1; trans.append(d); continue
        adj=pc/c; inc=adj/(m/pm)
        st_="IMPROVED" if c<pc else ("PLATEAU" if c==pc else "REVERSED")
        if st_=="IMPROVED": n_imp+=1
        elif st_=="PLATEAU": n_pla+=1
        else: n_rev+=1
        d.update(cycles_prev=pc, cycles_next=c, cycle_delta=c-pc,
                 cycle_delta_pct=round(100*(c-pc)/pc,4),
                 adjacent_speedup=round(adj,6),
                 incremental_efficiency=round(inc,6),
                 speedup_vs_base=(round(base[1]/c,6) if base else ""),
                 cumulative_efficiency=(round((base[1]/c)/(m/base[0]),6) if base else ""),
                 transition_status=st_,
                 legacy_saturation_rule=("TRIGGERED" if inc<0.50 else ""))
        trans.append(d)
    summary.append(dict(platform=k[0],npu=k[1],workload=k[2],
        mac_points_total=len(v), mac_points_executable=len(ok),
        transitions_total=max(len(v)-1,0),
        transitions_evaluable=n_imp+n_pla+n_rev,
        improved=n_imp, plateau=n_pla, reversed_=n_rev, not_available=n_na,
        contains_reversal=str(n_rev>0), contains_plateau=str(n_pla>0),
        source="analysis/canonical_cells.csv"))
n_files["3_3_scaling_transitions.csv"]=wr("3_3_scaling_transitions.csv", trans,
  ["platform","npu","workload","mac_prev","mac_next","cycles_prev","cycles_next",
   "cycle_delta","cycle_delta_pct","adjacent_speedup","incremental_efficiency",
   "speedup_vs_base","cumulative_efficiency","system_config_prev","system_config_next",
   "system_config_changed","memory_mode_changed","ta_config_changed",
   "transition_status","legacy_saturation_rule","source"])
n_files["3_3_ladder_summary.csv"]=wr("3_3_ladder_summary.csv", summary,
  ["platform","npu","workload","mac_points_total","mac_points_executable",
   "transitions_total","transitions_evaluable","improved","plateau","reversed_",
   "not_available","contains_reversal","contains_plateau","source"])

_c=collections.Counter(t["transition_status"] for t in trans)
STATS=dict(transitions_rows=len(trans),
           improved=_c["IMPROVED"], plateau=_c["PLATEAU"],
           reversed=_c["REVERSED"], not_available=_c["NOT_AVAILABLE"],
           evaluable=_c["IMPROVED"]+_c["PLATEAU"]+_c["REVERSED"],
           ladders_total=len(summary),
           ladders_with_reversal=sum(1 for s in summary if s["contains_reversal"]=="True"),
           ladders_with_plateau=sum(1 for s in summary if s["contains_plateau"]=="True"),
           ladders_with_2plus_points=sum(1 for s in summary if s["mac_points_executable"]>=2),
           legacy_rule_triggered=sum(1 for t in trans if t["legacy_saturation_rule"]=="TRIGGERED"))
with open(os.path.join(P,"TRANSITION_STATS.json"),"w") as f: json.dump(STATS,f,indent=1)
print(json.dumps(STATS, indent=1))

# =========================================================================
# 3.4 mechanism evidence matrix -- support level only, never causal
# =========================================================================
u85_diff=[d for d in DIFF if d["binding_pair"]=="B-frozen"]
ub_changed=sum(1 for d in u85_diff if d.get("UBLOCK_CHANGED")=="1")
mech=[
 dict(mechanism="SRAM bandwidth pressure",
   structural_evidence="U85 SRAM_* counters exist and are stock-exposed (PMU authority)",
   whole_model_evidence="ABSENT - U85 whole-model memory fields empty (parser loss)",
   per_layer_evidence="evt_sram_rd / evt_sram_wr present in mechanism dataset",
   memory_counter_evidence="per-unit only; no whole-model U85 traffic",
   compiler_schedule_evidence="Vela sram-access cycle estimate exists",
   controlled_intervention="NONE - no bandwidth-only intervention was run",
   representative_workload="rnnoise_INT8 (U85)",
   evidence_status="NOT_EVALUABLE",
   notes="effective bandwidth needs beat size, clock and TA config; none confirmed locally"),
 dict(mechanism="External-memory service latency",
   structural_evidence="U85 EXT_* counters exist and are stock-exposed",
   whole_model_evidence="ABSENT for U85",
   per_layer_evidence="evt_ext_rd / evt_ext_wr present in mechanism dataset",
   memory_counter_evidence="per-unit only",
   compiler_schedule_evidence="Vela dram-access cycle estimate exists",
   controlled_intervention="NONE - TA latency was never varied independently",
   representative_workload="rnnoise_INT8 (U85)",
   evidence_status="NOT_EVALUABLE",
   notes="stall counters are SEMANTICS_UNVERIFIED and were never collected"),
 dict(mechanism="Weight streaming / on-chip capacity",
   structural_evidence="Vela reports encoded weight size and SRAM usage per cell",
   whole_model_evidence="6 cells link-fail with RETRY_LINK_REGION_OVERFLOW",
   per_layer_evidence="none isolating weight traffic",
   memory_counter_evidence="ABSENT for U85 whole-model",
   compiler_schedule_evidence="Vela memory placement per memory_mode",
   controlled_intervention="NONE",
   representative_workload="wav2letter_pruned_int8 (U55)",
   evidence_status="STRUCTURAL_CONTEXT",
   notes="link-time SRAM overflow is a build outcome and is a separate status from a runtime streaming bottleneck"),
 dict(mechanism="DWConv / output-channel parallelism mismatch",
   structural_evidence="operator types recorded per attribution unit",
   whole_model_evidence="none",
   per_layer_evidence="per-unit op_types and cycles available (U85)",
   memory_counter_evidence="n/a",
   compiler_schedule_evidence="ublock / block / stripe fields present in the 256-512 differential",
   controlled_intervention="NONE",
   representative_workload="rnnoise_INT8",
   evidence_status="NOT_ESTABLISHED",
   notes="DWConv counts per model are NOT_COLLECTED in local evidence"),
 dict(mechanism="Small feature map / tile-level parallelism",
   structural_evidence="IFM/OFM shape strings appear in the 256-512 differential",
   whole_model_evidence="none",
   per_layer_evidence="regressing groups are dominated by small elementwise and FC units",
   memory_counter_evidence="n/a",
   compiler_schedule_evidence="stripes / cascade fields present",
   controlled_intervention="NONE",
   representative_workload="rnnoise_INT8",
   evidence_status="CONSISTENT_WITH",
   notes="shape/MAC ratios must not be reported as measured PE utilization"),
 dict(mechanism="Low compute volume / execution-cost floor",
   structural_evidence="model-level MAC counts NOT_COLLECTED",
   whole_model_evidence="one PLATEAU transition observed (U85 rnnoise 128->256, delta 0)",
   per_layer_evidence="per-unit ccnt available",
   memory_counter_evidence="n/a",
   compiler_schedule_evidence="Vela cycle estimates per MAC",
   controlled_intervention="NONE",
   representative_workload="rnnoise_INT8 (U85)",
   evidence_status="ASSOCIATED_WITH",
   notes="a plateau is observed; that compute volume is its reason is not established"),
 dict(mechanism="Ublock geometry mismatch",
   structural_evidence="ublock_256 / ublock_512 recorded per operator",
   whole_model_evidence="none",
   per_layer_evidence="UBLOCK_CHANGED flag on %d of %d rnnoise operators" % (ub_changed, len(u85_diff)),
   memory_counter_evidence="n/a",
   compiler_schedule_evidence="BLOCK_CONFIG_CHANGED / TILE_GEOMETRY_CHANGED flags present",
   controlled_intervention="NONE",
   representative_workload="rnnoise_INT8 256->512",
   evidence_status="ASSOCIATED_WITH",
   notes="ublock changes co-occur with the transition in every direction class; co-occurrence is not attribution"),
]
n_files["3_4_mechanism_evidence_matrix.csv"]=wr("3_4_mechanism_evidence_matrix.csv", mech,
  ["mechanism","structural_evidence","whole_model_evidence","per_layer_evidence",
   "memory_counter_evidence","compiler_schedule_evidence","controlled_intervention",
   "representative_workload","evidence_status","notes"])

# U85 256->512 combined view (MAC / ublock / system_config / TA / cycle)
rows=[]
for d in u85_diff:
    rows.append(dict(workload=d["workload"], source_id=d["source_id"],
      op_type=d["op_type"], cycles_256=d["cycles_256"], cycles_512=d["cycles_512"],
      cycle_delta=(int(d["cycles_512"])-int(d["cycles_256"]) if d["cycles_256"] and d["cycles_512"] else ""),
      direction=d["observed_direction"],
      ublock_256=d["ublock_256"], ublock_512=d["ublock_512"],
      UBLOCK_CHANGED=d["UBLOCK_CHANGED"], BLOCK_CONFIG_CHANGED=d["BLOCK_CONFIG_CHANGED"],
      TILE_GEOMETRY_CHANGED=d["TILE_GEOMETRY_CHANGED"],
      system_config_256="Ethos_U85_SYS_DRAM_Low", system_config_512="Ethos_U85_SYS_DRAM_Mid_512",
      ta_config_changed="NOT_VERIFIED_LOCALLY",
      vela_cycles_256=d.get("vela_cycles_256",""), vela_cycles_512=d.get("vela_cycles_512",""),
      source="mechanism/U85_256_512_DIFFERENTIAL.csv"))
n_files["3_4_u85_256_512_combined.csv"]=wr("3_4_u85_256_512_combined.csv", rows,
  ["workload","source_id","op_type","cycles_256","cycles_512","cycle_delta","direction",
   "ublock_256","ublock_512","UBLOCK_CHANGED","BLOCK_CONFIG_CHANGED",
   "TILE_GEOMETRY_CHANGED","system_config_256","system_config_512","ta_config_changed",
   "vela_cycles_256","vela_cycles_512","source"])
print(json.dumps({k:v for k,v in n_files.items() if k.startswith("3_4")}, indent=1))

# =========================================================================
# 4.1 Vela estimate vs FVP observation
#
# The frozen measurement-semantics contract refuses absolute
# estimate-versus-observation comparison. Absolute error is therefore emitted
# as LEGACY_ONLY and is not used in any conclusion of this report.
# =========================================================================
V = {(r["platform"],r["npu"],int(r["mac_config"]),r["model"]): r for r in VELA}
pairs=[]
for c in CELLS:
    k=(c["platform"],c["npu"],int(c["mac_config"]),c["workload"])
    v=V.get(k)
    for vname, fname, compat in (
        ("vela_cycles_total","npu_total_cycles",
         "REFUSED_ABSOLUTE: compiler performance-model prediction vs cycle-model observation"),
        ("vela_cycles_npu","npu_active_cycles",
         "REFUSED_ABSOLUTE: Vela npu-cycle estimate is not defined as the ACTIVE PMU event")):
        pairs.append(dict(platform=c["platform"], npu=c["npu"], mac=int(c["mac_config"]),
          workload=c["workload"], memory_mode=c["memory_mode"],
          system_config=(v["system_config"] if v else ""),
          vela_metric_name=vname, vela_value=(v[vname] if v else ""),
          fvp_metric_name=fname, fvp_value=c["canonical_cycles"] if fname=="npu_total_cycles" else c["npu_active_cycles"],
          pairing_status=("PAIRED" if v else "NO_VELA_ROW"),
          semantic_compatibility=compat,
          source_vela="evidence/vela-matrix-20260824/vela_matrix.csv",
          source_fvp="analysis/canonical_cells.csv"))
n_files["4_1_vela_fvp_pairs.csv"]=wr("4_1_vela_fvp_pairs.csv", pairs,
  ["platform","npu","mac","workload","memory_mode","system_config","vela_metric_name",
   "vela_value","fvp_metric_name","fvp_value","pairing_status","semantic_compatibility",
   "source_vela","source_fvp"])

def spearman(a,b):
    n=len(a)
    if n<2: return ""
    def rank(v):
        o=sorted(range(n), key=lambda i:v[i]); r=[0.0]*n
        i=0
        while i<n:
            j=i
            while j+1<n and v[o[j+1]]==v[o[i]]: j+=1
            av=(i+j)/2.0+1
            for t in range(i,j+1): r[o[t]]=av
            i=j+1
        return r
    ra,rb=rank(a),rank(b); ma=sum(ra)/n; mb=sum(rb)/n
    num=sum((x-ma)*(y-mb) for x,y in zip(ra,rb))
    da=sum((x-ma)**2 for x in ra)**0.5; db=sum((y-mb)**2 for y in rb)**0.5
    return round(num/(da*db),6) if da and db else ""

acc=[]
for (plat,npu,mac) in sorted({(c["platform"],c["npu"],int(c["mac_config"])) for c in CELLS}):
    sub=[c for c in CELLS if (c["platform"],c["npu"],int(c["mac_config"]))==(plat,npu,mac)]
    fv=[]; ve=[]; ape=[]
    for c in sub:
        v=V.get((plat,npu,mac,c["workload"]))
        if not v: continue
        f=int(c["canonical_cycles"]); e=int(v["vela_cycles_total"])
        fv.append(f); ve.append(e); ape.append(abs(e-f)/f*100)
    if len(fv)<2: continue
    ape.sort()
    acc.append(dict(platform=plat,npu=npu,mac=mac,n_workloads=len(fv),
      metric_pair="vela_cycles_total vs npu_total_cycles",
      spearman_rho_ranking=spearman(ve,fv),
      admissible_analysis="ranking only",
      MAPE_percent_LEGACY_ONLY=round(sum(ape)/len(ape),4),
      median_APE_percent_LEGACY_ONLY=round(ape[len(ape)//2],4),
      absolute_comparison_status="LEGACY_ONLY - refused by frozen measurement semantics",
      source="analysis/canonical_cells.csv + vela_matrix.csv"))
n_files["4_1_accuracy_metrics.csv"]=wr("4_1_accuracy_metrics.csv", acc,
  ["platform","npu","mac","n_workloads","metric_pair","spearman_rho_ranking",
   "admissible_analysis","MAPE_percent_LEGACY_ONLY","median_APE_percent_LEGACY_ONLY",
   "absolute_comparison_status","source"])

# =========================================================================
# 4.2 transition prediction -- every adjacent transition, both reversals kept
# =========================================================================
tp=[]
for t in trans:
    if t["transition_status"]=="NOT_AVAILABLE":
        continue
    k=(t["platform"],t["npu"])
    vp=V.get((k[0],k[1],t["mac_prev"],t["workload"]))
    vn=V.get((k[0],k[1],t["mac_next"],t["workload"]))
    vpv=int(vp["vela_cycles_total"]) if vp else None
    vnv=int(vn["vela_cycles_total"]) if vn else None
    vdir = "" if vpv is None or vnv is None else (
        "IMPROVED" if vnv<vpv else ("PLATEAU" if vnv==vpv else "REVERSED"))
    tp.append(dict(platform=t["platform"],npu=t["npu"],workload=t["workload"],
      mac_prev=t["mac_prev"],mac_next=t["mac_next"],
      vela_prev=(vpv if vpv is not None else ""), vela_next=(vnv if vnv is not None else ""),
      fvp_prev=t["cycles_prev"], fvp_next=t["cycles_next"],
      vela_direction=vdir, fvp_direction=t["transition_status"],
      direction_match=("" if not vdir else str(vdir==t["transition_status"])),
      fvp_reversal=str(t["transition_status"]=="REVERSED"),
      vela_predicted_reversal=("" if not vdir else str(vdir=="REVERSED")),
      system_config_changed=t["system_config_changed"],
      ta_config_changed=t["ta_config_changed"],
      ublock_changed=("SEE_3_4_TABLE" if (t["npu"]=="ethos-u85" and t["mac_prev"]==256
                                          and t["mac_next"]==512) else "NOT_COLLECTED"),
      source="analysis/canonical_cells.csv + vela_matrix.csv"))
n_files["4_2_transition_prediction.csv"]=wr("4_2_transition_prediction.csv", tp,
  ["platform","npu","workload","mac_prev","mac_next","vela_prev","vela_next",
   "fvp_prev","fvp_next","vela_direction","fvp_direction","direction_match",
   "fvp_reversal","vela_predicted_reversal","system_config_changed",
   "ta_config_changed","ublock_changed","source"])

assoc=[]
for t in tp:
    assoc.append(dict(platform=t["platform"],npu=t["npu"],workload=t["workload"],
      transition="%s->%s"%(t["mac_prev"],t["mac_next"]),
      fvp_direction=t["fvp_direction"], direction_match=t["direction_match"],
      mac_size=t["mac_next"], system_config_changed=t["system_config_changed"],
      memory_traffic_available=("NO (U85 parser loss)" if t["npu"]=="ethos-u85" else "YES (AXI)"),
      dwconv_count="NOT_COLLECTED", feature_map_size="NOT_COLLECTED",
      ublock_transition=t["ublock_changed"],
      analysis_type="ASSOCIATION_ONLY - not a causal decomposition",
      source="tables/4_2_transition_prediction.csv"))
n_files["4_2_error_associations.csv"]=wr("4_2_error_associations.csv", assoc,
  ["platform","npu","workload","transition","fvp_direction","direction_match",
   "mac_size","system_config_changed","memory_traffic_available","dwconv_count",
   "feature_map_size","ublock_transition","analysis_type","source"])

with open(os.path.join(P,"TABLE_COUNTS.json"),"w") as f: json.dump(n_files,f,indent=1)
print(json.dumps(n_files, indent=1))
