#!/usr/bin/env python3
"""Figures for the raw-data audit. Input is always a generated CSV in tables/."""
import csv, os, collections
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
# Deterministic SVG: without these, every run rewrites the embedded date and
# re-randomizes clip-path ids, producing a large diff with no visual change.
plt.rcParams["svg.hashsalt"] = "raw_data_report"

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.dirname(HERE)
T=os.path.join(OUT,"tables"); F=os.path.join(OUT,"figures"); os.makedirs(F,exist_ok=True)
def rd(n):
    with open(os.path.join(T,n)) as f: return list(csv.DictReader(f))
SHORT={"rnnoise_INT8":"rnnoise","kws_micronet_m":"kws","ad_medium_int8":"ad_medium",
 "vww4_128_128_INT8":"vww4","yolo-fastest_192_face_v4":"yolo","mobilenet_v2_1.0_224_INT8":"mobilenet",
 "wav2letter_pruned_int8":"wav2letter"}
def save(fig,name,src):
    fig.text(0.01,0.01,"source: tables/%s"%src,fontsize=6,color="#666")
    for ext in ("png","svg"):
        kw = {"metadata": {"Date": None}} if ext == "svg" else {}
        fig.savefig(os.path.join(F,"%s.%s"%(name,ext)),dpi=160,bbox_inches="tight",**kw)
    plt.close(fig); return name
made=[]

# ---- 3.2-A memory traffic share (U55/U65 only; U85 has no whole-model beats)
tr=[r for r in rd("3_2_memory_traffic.csv") if r["status"]=="OK"]
for npu in ("ethos-u55","ethos-u65"):
    s=[r for r in tr if r["npu"]==npu]
    if not s: continue
    s.sort(key=lambda r:(r["workload"],int(r["mac"])))
    lab=["%s\n%s"%(SHORT.get(r["workload"],r["workload"]),r["mac"]) for r in s]
    p0=[float(r["port0_share"]) for r in s]; p1=[float(r["port1_share"]) for r in s]
    fig,ax=plt.subplots(figsize=(max(8,len(s)*0.30),3.4))
    ax.bar(range(len(s)),p0,label="AXI0 (rd+wr)",color="#0072b2")
    ax.bar(range(len(s)),p1,bottom=p0,label="AXI1 (rd only)",color="#d55e00")
    ax.set_xticks(range(len(s))); ax.set_xticklabels(lab,fontsize=5,rotation=90)
    ax.set_ylabel("share of collected beats"); ax.set_ylim(0,1)
    ax.set_title("3.2-A  Memory-traffic share, %s (AXI1_WR not collected)"%npu,fontsize=9)
    ax.legend(fontsize=7)
    made.append(save(fig,"3_2_A_traffic_share_%s"%npu.replace("ethos-",""),"3_2_memory_traffic.csv"))

# ---- 3.2-B ACTIVE/TOTAL
al=rd("3_2_memory_traffic.csv")
fig,ax=plt.subplots(figsize=(9,3.4))
for i,npu in enumerate(("ethos-u55","ethos-u65","ethos-u85")):
    s=[r for r in al if r["npu"]==npu]
    ax.scatter([int(r["mac"]) for r in s],[float(r["active_over_total"]) for r in s],
               s=14,label=npu.replace("ethos-",""),alpha=0.8)
ax.set_xscale("log",base=2); ax.set_xlabel("MAC"); ax.set_ylabel("ACTIVE / TOTAL")
ax.set_ylim(0.9,1.005)
ax.set_title("3.2-B  ACTIVE/TOTAL ratio.  ACTIVE is not compute utilization and does not imply compute-bound",fontsize=8)
ax.legend(fontsize=7); ax.grid(alpha=.3)
made.append(save(fig,"3_2_B_active_over_total","3_2_memory_traffic.csv"))

# ---- 3.3-A/B/C raw cycles per architecture
cyc=[r for r in rd("3_3_cycles_by_mac.csv") if r["cycles"]]
for tag,npu in (("A","ethos-u55"),("B","ethos-u65"),("C","ethos-u85")):
    s=[r for r in cyc if r["npu"]==npu]
    if not s: continue
    fig,ax=plt.subplots(figsize=(5.6,3.6))
    for w in sorted({r["workload"] for r in s}):
        p=sorted([r for r in s if r["workload"]==w],key=lambda r:int(r["mac"]))
        ax.plot([int(r["mac"]) for r in p],[int(r["cycles"]) for r in p],
                marker="o",ms=3.5,lw=1.3,label=SHORT.get(w,w))
    ax.set_xscale("log",base=2); ax.set_yscale("log")
    ax.set_xlabel("MAC"); ax.set_ylabel("cycles (raw)")
    ax.set_title("3.3-%s  Raw cycles, %s"%(tag,npu.replace("ethos-","")),fontsize=9)
    ax.legend(fontsize=6); ax.grid(alpha=.3,which="both")
    made.append(save(fig,"3_3_%s_raw_cycles_%s"%(tag,npu.replace("ethos-","")),"3_3_cycles_by_mac.csv"))

# ---- 3.3-D/E/F normalized to each ladder's own baseline
for tag,npu in (("D","ethos-u55"),("E","ethos-u65"),("F","ethos-u85")):
    s=[r for r in cyc if r["npu"]==npu]
    if not s: continue
    fig,ax=plt.subplots(figsize=(5.6,3.6))
    for w in sorted({r["workload"] for r in s}):
        p=sorted([r for r in s if r["workload"]==w],key=lambda r:int(r["mac"]))
        if len(p)<2: continue
        b=int(p[0]["cycles"])
        ax.plot([int(r["mac"]) for r in p],[int(r["cycles"])/b for r in p],
                marker="o",ms=3.5,lw=1.3,label=SHORT.get(w,w))
    ax.axhline(1.0,color="#999",lw=.8,ls="--")
    ax.set_xscale("log",base=2); ax.set_xlabel("MAC")
    ax.set_ylabel("cycles / cycles(baseline MAC)")
    ax.set_title("3.3-%s  Normalized cycles, %s (within-ladder only)"%(tag,npu.replace("ethos-","")),fontsize=9)
    ax.legend(fontsize=6); ax.grid(alpha=.3)
    made.append(save(fig,"3_3_%s_normalized_%s"%(tag,npu.replace("ethos-","")),"3_3_cycles_by_mac.csv"))

# ---- 3.3-G incremental efficiency heatmap
tt=[r for r in rd("3_3_scaling_transitions.csv") if r["incremental_efficiency"]]
keys=sorted({(r["platform"],r["npu"],r["workload"]) for r in tt})
cols=sorted({"%s->%s"%(r["mac_prev"],r["mac_next"]) for r in tt},
            key=lambda s:int(s.split("->")[0]))
M=[[None]*len(cols) for _ in keys]
for r in tt:
    i=keys.index((r["platform"],r["npu"],r["workload"]))
    j=cols.index("%s->%s"%(r["mac_prev"],r["mac_next"]))
    M[i][j]=float(r["incremental_efficiency"])
fig,ax=plt.subplots(figsize=(7.4,7.0))
im=ax.imshow([[(v if v is not None else float("nan")) for v in row] for row in M],
             cmap="RdYlGn",vmin=0,vmax=1.1,aspect="auto")
ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols,rotation=45,fontsize=7,ha="right")
ax.set_yticks(range(len(keys)))
ax.set_yticklabels(["%s/%s/%s"%(k[0],k[1].replace("ethos-",""),SHORT.get(k[2],k[2])) for k in keys],fontsize=6)
for i,row in enumerate(M):
    for j,v in enumerate(row):
        if v is not None:
            ax.text(j,i,"%.2f"%v,ha="center",va="center",fontsize=5.5,
                    color=("white" if v<0.45 else "black"))
fig.colorbar(im,ax=ax,shrink=.6,label="incremental efficiency")
ax.set_title("3.3-G  Incremental efficiency per adjacent transition\n(blank = NOT_AVAILABLE; <0.50 at 2x MAC means cycles increased)",fontsize=8)
made.append(save(fig,"3_3_G_incremental_efficiency","3_3_scaling_transitions.csv"))

# ---- 3.3-H rnnoise/U85 full ladder with metadata
s=sorted([r for r in cyc if r["npu"]=="ethos-u85" and r["workload"]=="rnnoise_INT8"],
         key=lambda r:int(r["mac"]))
fig,ax=plt.subplots(figsize=(8.6,4.8))
x=[int(r["mac"]) for r in s]; y=[int(r["cycles"]) for r in s]
ax.plot(x,y,marker="o",ms=6,lw=1.8,color="#0072b2")
lo,hi=min(y),max(y); pad=(hi-lo)*0.42
ax.set_ylim(lo-pad*0.55, hi+pad*0.75)
# stagger so neighbouring labels never collide
OFF={0:(-4,-46),1:(4,14),2:(6,-46),3:(-6,16),4:(-4,-46)}
for i,(r,xx,yy) in enumerate(zip(s,x,y)):
    dx,dy=OFF[i]
    ha = "left" if i==0 else ("right" if i==len(s)-1 else "center")
    ax.annotate("%s\n%s\nmem=%s"%(yy,r["system_config"].replace("Ethos_U85_SYS_",""),r["memory_mode"]),
                (xx,yy),textcoords="offset points",
                xytext=(dx,dy), ha=ha, fontsize=6.5)
for i in range(1,len(y)):
    if y[i]>y[i-1]:
        ax.annotate("",xy=(x[i],y[i]),xytext=(x[i-1],y[i-1]),
                    arrowprops=dict(arrowstyle="->",color="#d55e00",lw=1.8))
        ax.text((x[i-1]*x[i])**.5,(y[i-1]+y[i])/2,"+%d"%(y[i]-y[i-1]),
                color="#d55e00",fontsize=9,ha="center",va="center",fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18",fc="white",ec="none",alpha=.85))
ax.set_xscale("log",base=2); ax.set_xticks(x); ax.set_xticklabels(x)
ax.set_xlabel("MAC"); ax.set_ylabel("cycles")
ax.set_title("3.3-H  rnnoise / SSE-320 / U85 — full ladder\nTA config per MAC: NOT_VERIFIED_LOCALLY",fontsize=9,pad=14)
ax.grid(alpha=.3)
made.append(save(fig,"3_3_H_rnnoise_u85_ladder","3_3_cycles_by_mac.csv"))

# ---- 4.1-A estimate vs observation (LEGACY_ONLY)
pr=[r for r in rd("4_1_vela_fvp_pairs.csv")
    if r["pairing_status"]=="PAIRED" and r["vela_metric_name"]=="vela_cycles_total"]
fig,ax=plt.subplots(figsize=(4.8,4.6))
for npu,c in (("ethos-u55","#0072b2"),("ethos-u65","#009e73"),("ethos-u85","#d55e00")):
    s=[r for r in pr if r["npu"]==npu]
    ax.scatter([int(r["fvp_value"]) for r in s],[int(r["vela_value"]) for r in s],
               s=12,alpha=.75,label=npu.replace("ethos-",""),color=c)
lo=min(int(r["fvp_value"]) for r in pr); hi=max(int(r["fvp_value"]) for r in pr)
ax.plot([lo,hi],[lo,hi],ls="--",color="#999",lw=.9)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("FVP npu_total_cycles (observation)"); ax.set_ylabel("Vela cycles_total (estimate)")
ax.set_title("4.1-A  LEGACY_ONLY — absolute estimate-vs-observation\ncomparison is refused by the frozen semantics",fontsize=8)
ax.legend(fontsize=7); ax.grid(alpha=.3,which="both")
made.append(save(fig,"4_1_A_estimate_vs_observation","4_1_vela_fvp_pairs.csv"))

# ---- 4.1-B ranking rho by config
am=rd("4_1_accuracy_metrics.csv")
fig,ax=plt.subplots(figsize=(7.4,3.2))
lab=["%s/%s/%s"%(r["platform"],r["npu"].replace("ethos-",""),r["mac"]) for r in am]
ax.bar(range(len(am)),[float(r["spearman_rho_ranking"]) for r in am],color="#009e73")
ax.set_xticks(range(len(am))); ax.set_xticklabels(lab,rotation=45,ha="right",fontsize=6)
ax.set_ylabel("Spearman rho"); ax.set_ylim(0,1.05)
ax.set_title("4.1-B  Workload-ranking agreement, Vela vs FVP (admissible: ranking only)",fontsize=9)
ax.grid(alpha=.3,axis="y")
made.append(save(fig,"4_1_B_ranking_rho","4_1_accuracy_metrics.csv"))

# ---- 4.2-B direction agreement per transition
tpr=rd("4_2_transition_prediction.csv")
cnt=collections.Counter((r["fvp_direction"],r["vela_direction"]) for r in tpr)
fig,ax=plt.subplots(figsize=(5.4,3.2))
ks=sorted(cnt); ax.bar(range(len(ks)),[cnt[k] for k in ks],color="#cc79a7")
ax.set_xticks(range(len(ks)))
ax.set_xticklabels(["FVP %s\nVela %s"%(a,b or "n/a") for a,b in ks],fontsize=6)
ax.set_ylabel("transitions")
ax.set_title("4.2-B  Adjacent-transition direction, observed vs predicted",fontsize=9)
for i,k in enumerate(ks): ax.text(i,cnt[k],str(cnt[k]),ha="center",va="bottom",fontsize=7)
made.append(save(fig,"4_2_B_direction_match","4_2_transition_prediction.csv"))

# ---- 4.2-C rnnoise/U85 predicted vs observed, full ladder
s=sorted([r for r in pr if r["npu"]=="ethos-u85" and r["workload"]=="rnnoise_INT8"],
         key=lambda r:int(r["mac"]))
fig,ax=plt.subplots(figsize=(6.4,3.6))
ax.plot([int(r["mac"]) for r in s],[int(r["fvp_value"]) for r in s],
        marker="o",lw=1.6,label="FVP observation",color="#0072b2")
ax.plot([int(r["mac"]) for r in s],[int(r["vela_value"]) for r in s],
        marker="s",lw=1.6,ls="--",label="Vela estimate",color="#d55e00")
ax.set_xscale("log",base=2); ax.set_xticks([int(r["mac"]) for r in s])
ax.set_xticklabels([r["mac"] for r in s])
ax.set_xlabel("MAC"); ax.set_ylabel("cycles")
ax.set_title("4.2-C  rnnoise / U85 full ladder — the two curves are different\nkinds of number and are not compared in absolute terms",fontsize=8)
ax.legend(fontsize=7); ax.grid(alpha=.3)
made.append(save(fig,"4_2_C_rnnoise_predicted_vs_observed","4_1_vela_fvp_pairs.csv"))

print("figures:",len(made))
for m in made: print("  ",m)
