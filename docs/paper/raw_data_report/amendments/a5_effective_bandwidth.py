"""A5 -- effective memory bandwidth against the Timing Adapter cap (POST_HOC_DESCRIPTIVE).

Contract (docs/superpowers/plans/2026-09-14-unresolved-items-evaluation-plan.md, section 1),
refined before any value was computed:

  effective_bytes_per_cycle = sum(beat) * bytes_per_beat / npu_total_cycles
  cap_per_port              = bwcap * bytes_per_word / (pulse_on + pulse_off)
  utilisation               = effective / cap_per_port          (conservative: one TA per port group)

Closed outcome set per (cell, port group):
  SATURATION_RULED_OUT   utilisation <= 0.50 and the beat set is complete
  NEAR_LIMIT             0.50 < utilisation <= 0.90 and complete
  AT_LIMIT               utilisation > 0.90 (valid even on a lower bound)
  LOWER_BOUND_ONLY       write beats not collected and utilisation <= 0.90
  NOT_EVALUABLE          an input is missing or the cap is zero

Assumptions recorded, not verified: one TA word == one AXI data beat; the TA cap applies per
port group and the NPU cycle counter and the TA run on the same clock.
"""
import csv, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = ROOT / "docs/paper/raw_data_report/source_data"

RULE_INPUT_MISSING = "RULE_A5_INPUT_MISSING"
RULE_CAP_ZERO = "RULE_A5_CAP_ZERO"
OUTCOMES = ("SATURATION_RULED_OUT", "NEAR_LIMIT", "AT_LIMIT", "LOWER_BOUND_ONLY", "NOT_EVALUABLE")
RULES = (RULE_INPUT_MISSING, RULE_CAP_ZERO)

PORTS = {  # (npu, mac) -> (sram_ports, ext_ports); Arm U85 configuration table, U55/U65 single AXI each
    ("ethos-u55", 32): (1, 1), ("ethos-u55", 64): (1, 1), ("ethos-u55", 128): (1, 1), ("ethos-u55", 256): (1, 1),
    ("ethos-u65", 256): (1, 1), ("ethos-u65", 512): (1, 1),
    ("ethos-u85", 128): (2, 1), ("ethos-u85", 256): (2, 1), ("ethos-u85", 512): (2, 1),
    ("ethos-u85", 1024): (2, 2), ("ethos-u85", 2048): (4, 2),
}


def ta_config_for(npu, mac):
    if npu == "ethos-u55":
        return "u55_high_end"
    if npu == "ethos-u65":
        return "u65_high_end"
    return {128: "u85_sys_dram_low", 256: "u85_sys_dram_low", 512: "u85_sys_dram_mid",
            1024: "u85_sys_dram_mid", 2048: "u85_sys_dram_high"}[mac]


def load_ta(path=HERE / "ta_parameters.csv"):
    return {r["ta_config"]: r for r in csv.DictReader(open(path))}


class Refusal(Exception):
    def __init__(self, rule, msg):
        super().__init__(msg); self.rule = rule


def cap_bytes_per_cycle(ta, group):
    try:
        bwcap = int(ta[f"{group}_bwcap"]); on = int(ta[f"{group}_pulse_on"]); off = int(ta[f"{group}_pulse_off"])
        bpw = int(ta["bytes_per_word"])
    except (KeyError, ValueError, TypeError) as e:
        raise Refusal(RULE_INPUT_MISSING, f"TA field missing for {group}: {e}")
    if bwcap <= 0 or on + off <= 0:
        raise Refusal(RULE_CAP_ZERO, f"TA cap is zero/infinite for {group}")
    return bwcap * bpw / (on + off)


def classify(util, complete):
    if util > 0.90:
        return "AT_LIMIT"
    if not complete:
        return "LOWER_BOUND_ONLY"
    if util > 0.50:
        return "NEAR_LIMIT"
    return "SATURATION_RULED_OUT"


def evaluate(cell, ta):
    """cell: dict with npu, mac, cycles, sram_rd, sram_wr, ext_rd, ext_wr (None if not collected)."""
    out = {}
    for group, rd, wr in (("sram", cell["sram_rd"], cell["sram_wr"]), ("ext", cell["ext_rd"], cell["ext_wr"])):
        try:
            if cell["cycles"] in (None, "", 0) or rd in (None, ""):
                raise Refusal(RULE_INPUT_MISSING, f"cycles or {group} read beats missing")
            cap = cap_bytes_per_cycle(ta, group)
            complete = wr not in (None, "") or cell.get(f"{group}_wr_structurally_zero", False)
            beats = int(rd) + (int(wr) if wr not in (None, "") else 0)
            eff = beats * int(ta["bytes_per_word"]) / int(cell["cycles"])
            util = eff / cap
            ports = PORTS[(cell["npu"], int(cell["mac"]))][0 if group == "sram" else 1]
            out[group] = {"effective_B_per_cycle": round(eff, 4), "cap_per_port_B_per_cycle": round(cap, 4),
                          "ports": ports, "utilisation_vs_one_port": round(util, 4),
                          "utilisation_vs_all_ports": round(util / ports, 4), "complete": complete,
                          "outcome": classify(util, complete), "rule": ""}
        except Refusal as e:
            out[group] = {"effective_B_per_cycle": None, "cap_per_port_B_per_cycle": None, "ports": None,
                          "utilisation_vs_one_port": None, "utilisation_vs_all_ports": None, "complete": None,
                          "outcome": "NOT_EVALUABLE", "rule": e.rule}
    return out


def load_cells():
    cells = []
    for r in csv.DictReader(open(SRC / "3_1_methodology/canonical_cells.csv")):
        if r["npu"] == "ethos-u85":
            continue  # U85 memory fields come from R1
        cells.append({"cell_id": r["cell_id"], "npu": r["npu"], "mac": int(r["mac_config"]), "workload": r["workload"],
                      "cycles": int(r["canonical_cycles"]), "sram_rd": r["axi0_rd_beats"], "sram_wr": r["axi0_wr_beats"],
                      "ext_rd": r["axi1_rd_beats"], "ext_wr": None,
                      # U55 Shared_Sram: AXI1 is read-only flash, Vela places no writable tensor there
                      "ext_wr_structurally_zero": r["npu"] == "ethos-u55", "source": "canonical_cells.csv"})
    seen = set()
    for r in csv.DictReader(open(SRC / "3_2_inference_time/R1_MEMORY_COUNTERS.csv")):
        if r["cell_id"] in seen:
            continue
        seen.add(r["cell_id"])
        cells.append({"cell_id": r["cell_id"], "npu": "ethos-u85", "mac": int(r["mac_config"]), "workload": r["workload"],
                      "cycles": int(r["npu_total_cycles"]), "sram_rd": r["sram_rd_beats"], "sram_wr": r["sram_wr_beats"],
                      "ext_rd": r["ext_rd_beats"], "ext_wr": r["ext_wr_beats"], "source": "R1_MEMORY_COUNTERS.csv"})
    return cells


def main(out_path=HERE / "a5_effective_bandwidth.csv"):
    ta = load_ta(); cells = load_cells()
    cols = ["cell_id", "workload", "npu", "mac", "ta_config", "cycles", "source",
            "sram_effective_B_per_cycle", "sram_cap_per_port", "sram_ports", "sram_util_one_port", "sram_util_all_ports",
            "sram_outcome", "ext_effective_B_per_cycle", "ext_cap_per_port", "ext_ports", "ext_util_one_port",
            "ext_util_all_ports", "ext_complete", "ext_outcome", "rule", "analysis_type"]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for c in cells:
            tc = ta_config_for(c["npu"], c["mac"]); res = evaluate(c, ta[tc])
            s, e = res["sram"], res["ext"]
            w.writerow([c["cell_id"], c["workload"], c["npu"], c["mac"], tc, c["cycles"], c["source"],
                        s["effective_B_per_cycle"], s["cap_per_port_B_per_cycle"], s["ports"], s["utilisation_vs_one_port"],
                        s["utilisation_vs_all_ports"], s["outcome"], e["effective_B_per_cycle"], e["cap_per_port_B_per_cycle"],
                        e["ports"], e["utilisation_vs_one_port"], e["utilisation_vs_all_ports"], e["complete"], e["outcome"],
                        s["rule"] or e["rule"], "POST_HOC_DESCRIPTIVE"])
    print("wrote", out_path, len(cells), "cells")


if __name__ == "__main__":
    sys.exit(main())
