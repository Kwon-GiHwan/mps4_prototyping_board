#!/usr/bin/env python3
"""Copy the original frozen evidence into per-section folders.

Read-only on every source. Copies are byte-identical and verified by SHA-256
against the original after writing. Files feeding more than one section are
duplicated rather than symlinked, so each section folder stands alone; the
manifest records every place a file appears.
"""
import csv, hashlib, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.dirname(HERE)
PAPER= os.path.dirname(OUT)
DST  = os.path.join(OUT, "source_data")

# section -> [(role, path relative to docs/paper/)]
SECTIONS = {
 "3_1_methodology": [
   ("configuration universe, 133 cells",        "analysis/executability.csv"),
   ("74 formal cells, canonical PMU",           "analysis/canonical_cells.csv"),
   ("Vela compile matrix, per-cell metadata",   "evidence/vela-matrix-20260824/vela_matrix.csv"),
   ("FVP versions and matrix design",           "MAIN_EXPERIMENT_MATRIX.md"),
   ("frozen metric vector (equality fields)",   "evidence/stage1-formal-20260825/DETERMINISTIC_METRIC_VECTOR.md"),
 ],
 "3_2_inference_time": [
   ("whole-model PMU per formal cell",          "analysis/canonical_cells.csv"),
   ("per-unit PMU incl. SRAM/EXT (mechanism)",  "mechanism/U85_ATTRIBUTION_UNITS.csv"),
   ("PMU event availability authority",         "mechanism/U85_PMU_EVENT_AUTHORITY.csv"),
   ("within-generation PMU comparison",         "analysis/pmu_within_generation.csv"),
 ],
 "3_3_scaling": [
   ("cycles per cell (point source)",           "analysis/canonical_cells.csv"),
   ("MAC grid incl. non-executable cells",      "analysis/executability.csv"),
   ("frozen scaling table (cross-check)",       "analysis/scaling.csv"),
   ("frozen saturation verdicts",               "analysis/saturation.csv"),
   ("system_config per MAC",                    "evidence/vela-matrix-20260824/vela_matrix.csv"),
   ("workload ranking per config",              "analysis/workload_ranking.csv"),
   ("ranking preservation across configs",      "analysis/ranking_preservation.csv"),
 ],
 "3_4_limits": [
   ("256->512 per-operator differential",       "mechanism/U85_256_512_DIFFERENTIAL.csv"),
   ("256->512 per-group differential",          "mechanism/U85_GROUP_DIFFERENTIAL.csv"),
   ("per-unit attribution incl. memory events", "mechanism/U85_ATTRIBUTION_UNITS.csv"),
   ("cross-memory-mode group deltas",           "mechanism/U85_P1B_CROSSMODE_GROUPS.csv"),
   ("mechanism formal cell matrix",             "mechanism/U85_FORMAL_MATRIX.csv"),
   ("operator match across bindings",           "mechanism/U85_OPERATOR_MATCH.csv"),
   ("PMU event availability authority",         "mechanism/U85_PMU_EVENT_AUTHORITY.csv"),
 ],
 "4_1_estimation_accuracy": [
   ("Vela estimates (compiler prediction)",     "evidence/vela-matrix-20260824/vela_matrix.csv"),
   ("FVP observations",                         "analysis/canonical_cells.csv"),
   ("frozen Vela/FVP trend agreement",          "analysis/vela_fvp_trend_agreement.csv"),
 ],
 "4_2_error_sources": [
   ("Vela estimates",                           "evidence/vela-matrix-20260824/vela_matrix.csv"),
   ("FVP observations",                         "analysis/canonical_cells.csv"),
   ("per-operator estimate vs observation",     "mechanism/U85_256_512_DIFFERENTIAL.csv"),
 ],
 "_supporting_board": [
   ("board canonical cost per workload",        "analysis/board_rq3/canonical_board_cost.csv"),
   ("FVP vs board ranking",                     "analysis/board_rq3/fvp_board_ranking.csv"),
   ("independently normalized relative cost",   "analysis/board_rq3/normalized_relative_cost.csv"),
 ],
 "_supporting_platform_sensitivity": [
   ("X3 metric qualification",                  "platform_sensitivity/X3_METRIC_QUALIFICATION.csv"),
   ("X1 formal cells",                          "platform_sensitivity/X1_FORMAL_CELLS.json"),
   ("X1 structural results",                    "platform_sensitivity/X1_STRUCTURAL_RESULTS.json"),
 ],
 "_supporting_instrumentation": [
   ("U65 bridge runtime equivalence",           "mechanism/U65_BRIDGE_RUNTIME_EQUIVALENCE.csv"),
   ("U65 bridge structural equivalence",        "mechanism/U65_BRIDGE_STRUCTURAL_EQUIVALENCE.csv"),
 ],
}

def sha(p):
    with open(p,"rb") as f: return hashlib.sha256(f.read()).hexdigest()

def main():
    if os.path.isdir(DST): shutil.rmtree(DST)
    where = {}
    for sec, items in SECTIONS.items():
        for _, rel in items: where.setdefault(rel, []).append(sec)

    rows, bad = [], []
    for sec, items in SECTIONS.items():
        d = os.path.join(DST, sec); os.makedirs(d, exist_ok=True)
        for role, rel in items:
            src = os.path.join(PAPER, rel)
            if not os.path.exists(src):
                bad.append("MISSING SOURCE: " + rel); continue
            dst = os.path.join(d, os.path.basename(rel))
            shutil.copy2(src, dst)
            h_src, h_dst = sha(src), sha(dst)
            if h_src != h_dst: bad.append("HASH MISMATCH: " + rel)
            rows.append(dict(section=sec, role=role,
                original_path="docs/paper/" + rel,
                copied_path=os.path.relpath(dst, PAPER).replace(os.sep,"/"),
                sha256=h_src, bytes=os.path.getsize(src),
                verified_identical=str(h_src == h_dst),
                also_in_sections=";".join(s for s in where[rel] if s != sec) or "-"))
    rows.sort(key=lambda r:(r["section"], r["copied_path"]))
    with open(os.path.join(DST,"MANIFEST.csv"),"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["section","role","original_path","copied_path",
            "sha256","bytes","verified_identical","also_in_sections"])
        w.writeheader(); w.writerows(rows)
    print("sections %d | copies %d | unique sources %d | bytes %d"
          % (len(SECTIONS), len(rows), len(where), sum(r["bytes"] for r in rows)))
    if bad:
        print("PROBLEMS:"); [print("  ", b) for b in bad]; return 1
    print("all copies byte-identical to source")
    return 0

if __name__ == "__main__":
    sys.exit(main())
