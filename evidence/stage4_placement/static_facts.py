"""Stage 4 placement plan: re-derive, from the existing conv_base artifacts, the facts the plan relies on (no board, no
container). Prints facts.json; exits 1 and names the failed fact if any check fails.

    python3 evidence/stage4_placement/static_facts.py [--regs F] [--drwl F] [--runs F] [--caps F] [--summary F]

Inputs (defaults = Stage 4 conv_base, image 83398c7, TA profile 1): the decoded command stream (Vela
--verbose-high-level-command-stream + register stream), the DRWL metadata, one boot's raw_runs.json and
capabilities.json, and the Stage 4 summary row (pass-B traffic, used only for the auxiliary traffic prediction).
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
S4 = REPO / "evidence/stage4"
COND = S4 / "raw/conds/s4_conv_base/wfe"

# MLEK mps4-sse-320 linker / mem_regions.h (container_facts.txt)
SRAM_BASE, SRAM_END = 0x31000000, 0x31400000
ISRAM1_BASE = 0x31200000
# MLEK Dedicated_Sram driver config (container_facts.txt: CMakeLists + ethosu_config_select machine code)
MLEK_DEDICATED = {-1: 3, 0: 3, 1: 3, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1}
SRAM_PORT_ATTR = 0          # MLEK Shared_Sram's choice for region 1 (MEM_ATTR0 = SRAM AXI port)
BEAT_BYTES = 16


def regioncfg(n_base, select):
    return sum(select[i] << (2 * i) for i in range(n_base))


def parse_regs(text):
    regions = {}
    for m in re.finditer(r"NPU_SET_(\w+?)_REGION\s+\d+, region = (\d+)", text):
        regions.setdefault(m.group(1), set()).add(int(m.group(2)))
    bases = {k: [int(v, 16) for v in re.findall(rf"NPU_SET_{k}_BASE0?\s+\d+, addr = (0x[0-9a-f]+)", text)]
             for k in ("IFM", "OFM")}
    ops = re.findall(r"NPU_OP_(\w+)", text)
    return regions, bases, ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regs", default=S4 / "registers/conv_base.regs.txt")
    ap.add_argument("--drwl", default=S4 / "workloads/s4_conv_base.drwl.json")
    ap.add_argument("--runs", default=COND / "raw_runs.json")
    ap.add_argument("--caps", default=COND.parent / "capabilities.json")
    ap.add_argument("--summary", default=REPO / "results/fi101_stage4/stage4_summary.csv")
    a = ap.parse_args()

    regions, bases, ops = parse_regs(Path(a.regs).read_text())
    d = json.loads(Path(a.drwl).read_text())
    runs = json.loads(Path(a.runs).read_text())
    caps = json.loads(Path(a.caps).read_text())
    row = next(r for r in csv.DictReader(open(a.summary)) if r["config"] == "conv_base")

    recs = [r["record"] for r in runs if "record" in r]   # entry 0 is the boot PING
    keys = ("model_base", "model_len", "arena_base", "arena_len", "n_base") + tuple(
        f"base{i}" for i in range(8)) + tuple(f"base_size{i}" for i in range(8))
    distinct = {tuple(r[k] for k in keys) for r in recs}
    r = recs[0]
    ifm_end, ofm_end = d["ifm_off"] + d["ifm_len"], d["ofm_off"] + d["ofm_len"]
    fast_end = caps["fast_base"] + caps["fast_size"]
    b_arena = fast_end + (r["arena_base"] - r["model_base"])
    a_rcfg = regioncfg(r["n_base"], MLEK_DEDICATED)
    b_rcfg = regioncfg(r["n_base"], {**MLEK_DEDICATED, 1: SRAM_PORT_ATTR})
    ifm_beats, ofm_beats = d["ifm_len"] // BEAT_BYTES, d["ofm_len"] // BEAT_BYTES
    n_ifm_reads = ops.count("CONV")          # every kernel reads the whole IFM (OFM depth split 16 + 80)

    checks = {
        "ifm_ofm_region_is_1": regions.get("IFM") == {1} and regions.get("OFM") == {1},
        "weights_scale_region_is_2": regions.get("WEIGHT") == {2} and regions.get("SCALE") == {2},
        "dma_region0_to_region2_only": regions.get("DMA0_SRC") == {0} and regions.get("DMA0_DST") == {2},
        "no_other_region_used": set().union(*regions.values()) == {0, 1, 2},
        "ifm_ofm_offsets_match_drwl": bases["IFM"][0] == d["ifm_off"] and bases["OFM"][0] == d["ofm_off"],
        "region1_holds_only_ifm_ofm": max(ifm_end, ofm_end) == d["arena_size"] == d["ifm_len"] + d["ofm_len"],
        "records_identical_over_runs": len(distinct) == 1 and len(recs) == 10,
        "base1_is_arena_head": r["base1"] == r["arena_base"] and r["base_size1"] == d["arena_size"],
        "base3_base4_are_ifm_ofm": r["base3"] == r["base1"] + d["ifm_off"] and r["base4"] == r["base1"] + d["ofm_off"],
        "base2_is_fast_memory": r["base2"] == caps["fast_base"] and SRAM_BASE <= caps["fast_base"] < SRAM_END,
        "base0_base1_in_ddr": all(0x70000000 <= r[k] < caps["ddr_limit"] for k in ("base0", "base1")),
        "fast_memory_is_whole_cache_arena": caps["fast_base"] == SRAM_BASE and caps["fast_size"] == 0x60000,
        "b_arena_fits_sram": SRAM_BASE <= fast_end <= b_arena and b_arena + r["arena_len"] <= SRAM_END,
        "b_region1_in_isram0": b_arena + d["arena_size"] <= ISRAM1_BASE,
        "b_keeps_low_16_bits": (b_arena & 0xFFFF) == (r["arena_base"] & 0xFFFF),
        "ext_wr_beats_equal_ofm": float(row["B_391"]) == ofm_beats,
        "ta_profile_1": d.get("ta_profile") == 1 and caps["ta_ext_rlatency"] == 500 and caps["ta_sram_rlatency"] == 32,
    }
    facts = {
        "regions_used": {k: sorted(v) for k, v in sorted(regions.items())},
        "ifm_base_offsets": [hex(x) for x in bases["IFM"]], "ofm_base_offsets": [hex(x) for x in bases["OFM"]],
        "n_conv_kernels": n_ifm_reads,
        "arena_size_vela": d["arena_size"], "ifm": [d["ifm_off"], d["ifm_len"]], "ofm": [d["ofm_off"], d["ofm_len"]],
        "fast_size_used_by_payload": d["fast_size"],
        "record": {k: hex(r[k]) for k in keys if r[k] or k.startswith(("base0", "base1", "base2", "base3", "base4"))},
        "fast_memory": [hex(caps["fast_base"]), hex(caps["fast_size"])],
        "sram_free_after_cache_arena": [hex(fast_end), hex(SRAM_END), SRAM_END - fast_end],
        "b_arena_base": hex(b_arena), "b_arena_end": hex(b_arena + r["arena_len"]),
        "b_region1_end": hex(b_arena + d["arena_size"]),
        "regioncfg_expected": {"A": hex(a_rcfg), "B": hex(b_rcfg)}, "qconfig_expected": MLEK_DEDICATED[-1],
        "traffic_stage4_passB_median": {k: float(row[k]) for k in ("B_130", "B_135", "B_386", "B_391")},
        "traffic_shift_if_ifm_ofm_follow_region1": {
            "ext_rd_beats_minus": n_ifm_reads * ifm_beats, "ext_wr_beats_minus": ofm_beats,
            "sram_rd_beats_plus": n_ifm_reads * ifm_beats, "sram_wr_beats_plus": ofm_beats},
        "checks": checks,
    }
    print(json.dumps(facts, indent=1))
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        print("FAIL: " + ", ".join(failed), file=sys.stderr)
        return 1
    print(f"OK: {len(checks)} checks", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
