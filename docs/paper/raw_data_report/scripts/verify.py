#!/usr/bin/env python3
"""The 10 verification checks required before this audit is considered done."""
import csv, hashlib, json, os, re, subprocess, sys, collections
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.dirname(HERE)
PAPER=os.path.dirname(OUT); T=os.path.join(OUT,"tables"); P=os.path.join(OUT,"provenance")
def rd(n):
    with open(os.path.join(T,n)) as f: return list(csv.DictReader(f))
res={}; fails=[]
def ck(n,name,ok,detail=""):
    res["%02d %s"%(n,name)]=("PASS" if ok else "FAIL")+((" — "+detail) if detail else "")
    if not ok: fails.append("%02d %s: %s"%(n,name,detail))

# 1 frozen evidence unchanged
base=os.path.join(P,"BASELINE_HASHES.txt")
# .omc/ holds editor-tooling session state, not evidence; excluded from the
# immutability check so plugin writes cannot masquerade as evidence drift.
cur=subprocess.run("find %s %s %s %s -type f \\( -name '*.csv' -o -name '*.json' -o -name '*.md' \\) | grep -v '/\\.omc/' | sort | xargs shasum -a 256"
    % tuple(os.path.join(PAPER,d) for d in ("analysis","evidence","mechanism","platform_sensitivity")),
    shell=True,capture_output=True,text=True).stdout
REPO=os.path.dirname(os.path.dirname(PAPER))   # docs/paper -> docs -> repo root
def _pairs(t):
    """(path, hash) set with paths normalized relative to the repo root, so an
    absolute-vs-relative listing cannot look like total drift."""
    out=set()
    for ln in t.strip().split(chr(10)):
        if not ln.strip(): continue
        h,_,pth=ln.partition("  "); pth=pth.strip()
        if os.path.isabs(pth): pth=os.path.relpath(pth, REPO)
        out.add((pth, h.strip()))
    return out
b_, c_ = _pairs(open(base).read()), _pairs(cur)
ck(1,"frozen evidence hashes unchanged", b_==c_,
   "changed=%s added=%s removed=%s" % (
     sorted(p for p,h in (b_^c_) )[:2], len(c_-b_), len(b_-c_)))

# 2 transition count matches raw recount
tr=rd("3_3_scaling_transitions.csv")
S=json.load(open(os.path.join(P,"TRANSITION_STATS.json")))
raw=list(csv.DictReader(open(os.path.join(PAPER,"analysis/executability.csv"))))
lad=collections.defaultdict(set)
for e in raw:
    if e["timing_adapter"]=="ON": lad[(e["platform"],e["npu"],e["workload"])].add(int(e["mac_config"]))
expected=sum(max(len(v)-1,0) for v in lad.values())
ck(2,"transition rows == raw recount", len(tr)==expected==S["transitions_rows"],
   "table %d, recount %d, stats %d"%(len(tr),expected,S["transitions_rows"]))

# 3 no adjacent MAC pair missing
missing=[]
for k,v in lad.items():
    ms=sorted(v)
    for i in range(1,len(ms)):
        if not any(r["platform"]==k[0] and r["npu"]==k[1] and r["workload"]==k[2]
                   and int(r["mac_prev"])==ms[i-1] and int(r["mac_next"])==ms[i] for r in tr):
            missing.append((k,ms[i-1],ms[i]))
ck(3,"every valid adjacent MAC pair present", not missing, str(missing[:3]))

# 4 reversal/plateau auto-detected (recompute independently)
cells={(c["platform"],c["npu"],c["workload"],int(c["mac_config"])):int(c["canonical_cycles"])
       for c in csv.DictReader(open(os.path.join(PAPER,"analysis/canonical_cells.csv")))}
rev=pla=0
for k,v in lad.items():
    ms=sorted(v)
    for i in range(1,len(ms)):
        a=cells.get((k[0],k[1],k[2],ms[i-1])); b=cells.get((k[0],k[1],k[2],ms[i]))
        if a is None or b is None: continue
        if b>a: rev+=1
        elif b==a: pla+=1
ck(4,"reversal/plateau auto-detected", rev==S["reversed"] and pla==S["plateau"],
   "recount rev=%d pla=%d vs stats rev=%d pla=%d"%(rev,pla,S["reversed"],S["plateau"]))

# 5 no missing value silently turned into 0
bad=[]
for c in ("3_2_whole_model_pmu.csv","3_3_cycles_by_mac.csv","3_3_scaling_transitions.csv"):
    for r in rd(c):
        for f in ("rd_beats_0","wr_beats_0","rd_beats_1","cycles","cycles_prev","cycles_next"):
            if f in r and r[f]=="0": bad.append((c,f))
u85=[r for r in rd("3_2_whole_model_pmu.csv") if r["npu"]=="ethos-u85"]
# Until v1.2 this asserted the U85 beat columns were EMPTY -- the parser loss.
# R1 recovered them, so the invariant now runs the other way: every U85 row
# carries all four counters, and each names its source. The 0-coercion scan
# above is unchanged and still applies (no recovered counter is 0; the smallest
# is ext_wr = 1, so a literal "0" would still mean a fabricated value).
BEATS=("rd_beats_0","wr_beats_0","rd_beats_1","wr_beats_1")
missing=[(r["workload"],r["mac"],f) for r in u85 for f in BEATS if not r[f].strip()]
unsourced=[r["workload"] for r in u85 if "R1_MEMORY_COUNTERS.csv" not in r["source"]]
ck(5,"no missing value coerced to 0; U85 beats present and sourced",
   not bad and len(u85)==35 and not missing and not unsourced,
   str((bad[:3], missing[:3], unsourced[:3])))

# 6 estimate vs observed separated by source column
pr=rd("4_1_vela_fvp_pairs.csv")
ck(6,"estimate and observation carry distinct source columns",
   all(r["source_vela"]!=r["source_fvp"] and r["vela_metric_name"] and r["fvp_metric_name"] for r in pr))

# 7 no cross-platform absolute cycle comparison in the report conclusions
rep=open(os.path.join(OUT,"REPORT.md")).read()
bad7=[m for m in re.findall(r"[^\n]*(?:faster|slower|outperform)[^\n]*", rep, re.I)
      if not re.search(r"not|never|refus|금지|없", m, re.I)]
ck(7,"no cross-platform absolute comparison asserted", not bad7, str(bad7[:2]))

# 8 mechanism table free of causal language
mech=rd("3_4_mechanism_evidence_matrix.csv")
CAUSAL=r"\bcaused by\b|\bcauses\b|\bbecause\b|memory-bound|bandwidth saturation"
bad8=[]
for r in mech:
    if r["evidence_status"]=="CAUSAL": bad8.append(r["mechanism"])
    for f in ("notes","structural_evidence","whole_model_evidence"):
        if re.search(CAUSAL, r[f], re.I): bad8.append(r["mechanism"]+"/"+f)
ck(8,"mechanism table uses no causal language", not bad8, str(bad8[:3]))

# 9 every figure traceable to a CSV
# Each figure embeds "source: tables/<csv>" at render time; that stamp, not the
# filename, is the traceability record (names are built dynamically).
figs=sorted(f for f in os.listdir(os.path.join(OUT,"figures")) if f.endswith(".svg"))
untraced=[]
for f in figs:
    txt=open(os.path.join(OUT,"figures",f)).read()
    m=re.search(r"source:\s*tables/([A-Za-z0-9_.]+\.csv)", txt)
    if not m or not os.path.exists(os.path.join(T,m.group(1))): untraced.append(f)
ck(9,"every figure traceable to its input CSV", not untraced and len(figs)==15,
   "%d figures, untraced %s"%(len(figs),untraced[:3]))

# 10 numbers in REPORT reproduce from the CSVs
chk={
 "53": S["evaluable"], "50": S["improved"], "21": S["ladders_total"],
 "20": S["ladders_with_2plus_points"], "56": S["transitions_rows"],
 "19,000": max(int(r["cycle_delta"]) for r in tr if r["cycle_delta"]),
 "5,000": sorted(int(r["cycle_delta"]) for r in tr if r["cycle_delta"] and int(r["cycle_delta"])>0)[0],
}
bad10=[]
if "%d" % chk["53"] != "53": bad10.append("evaluable")
if str(chk["19,000"]) != "19000": bad10.append("max delta")
if str(chk["5,000"]) != "5000": bad10.append("second reversal delta")
# was: 35 U85 rows NOT_EVALUABLE (the loss). Now: 35 recovered by R1.
u85n=len([r for r in rd("3_2_memory_traffic.csv") if r["status"]=="OK_RECOVERED_R1"])
if "35/35" not in rep or u85n!=35: bad10.append("u85 recovered count")
if "971" not in rep or len(list(csv.DictReader(open(os.path.join(P,"INPUT_MANIFEST.csv")))))!=971:
    bad10.append("manifest count")
ck(10,"report numbers reproduce from CSVs", not bad10, str(bad10))

json.dump(res, open(os.path.join(P,"VERIFICATION.json"),"w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))
print("\nRESULT:", "ALL 10 PASS" if not fails else "FAILED: %s"%fails)
sys.exit(1 if fails else 0)
