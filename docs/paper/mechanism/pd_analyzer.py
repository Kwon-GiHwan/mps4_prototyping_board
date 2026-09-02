#!/usr/bin/env python3
"""P0-E operator matching / differential analyzer.

Written BEFORE the formal evidence is examined (only the qualified formats
from P0-C are assumed). Joins 256 vs 512 by stable operation identity,
never by row position; fail-closed on every rejection rule of the frozen
plan. Computes; does not interpret.

Inputs (evidence root = the P0-D `pd/` tree):
  <cell>/vela_verbose/verbose.log   Vela schedule capture (per cell)
  <cell>/instr.meta.json            irq_count / NOT_AVAILABLE
  <cell>/{clean,prof}.run1.json     qualified run vectors (exact-equal x3)
  U85_FORMAL_MATRIX.csv             cell index

Outputs: U85_OPERATOR_MATCH.csv, U85_256_512_DIFFERENTIAL.csv (stdout paths).
"""
import csv
import json
import os
import re
import sys

WORKLOADS = ["rnnoise_INT8", "vww4_128_128_INT8", "yolo-fastest_192_face_v4",
             "kws_micronet_m", "ad_medium_int8", "dnn_s_quantized"]
PAIRS = [("B-frozen", "256_Low", "512_Mid512"),
         ("B-held", "256_Low", "512_Low")]


class Reject(Exception):
    pass


def parse_schedule(path):
    """Parse the verbose-schedule op list with the Q2 fields."""
    ops, cur = [], None
    for ln in open(path):
        m = re.match(r"\t(\d+): Operation (\S+)\s+- OFM ([0-9, ]+)", ln)
        if m:
            cur = {"idx": int(m.group(1)), "type": m.group(2),
                   "ofm": m.group(3).strip(), "slices": 1, "kernel": "",
                   "ublock": "", "block": "", "stripes": "", "cascade": "",
                   "weight_buf": "", "vela_cycles": None, "time_index": None}
            ops.append(cur)
            continue
        if cur is None:
            continue
        for key, rx in (("kernel", r"Kernel: (.+)"),
                        ("time_index", r"Time index = (\d+)"),
                        ("cascade", r"Assigned Cascade = (\d+)"),
                        ("weight_buf", r"Weight buffer = (\d+) bytes")):
            m = re.search(rx, ln)
            if m:
                cur[key] = m.group(1)
        m = re.search(r"Operator Config = OFM Block=(\[[0-9, ]+\]), "
                      r"IFM Block=(\[[0-9, ]+\]), OFM UBlock=(\[[0-9, ]+\])", ln)
        if m:
            cur["block"] = "OFM%s IFM%s" % (m.group(1), m.group(2))
            cur["ublock"] = m.group(3)
        m = re.search(r"(IFM|OFM) Stripe\s+= (\[[0-9, ]*\])", ln)
        if m:
            cur["stripes"] += "%s%s " % (m.group(1), m.group(2))
        m = re.search(r"Depth slices = \[([0-9, ]+)\]", ln)
        if m:
            cur["slices"] = len(m.group(1).split(",")) - 1
        m = re.search(r"Estimated Perf: Macs=\d+ Cycles=(\d+)", ln)
        if m:
            cur["vela_cycles"] = int(m.group(1))
    if not ops:
        raise Reject("no schedule ops parsed from " + path)
    return ops


def identity(op):
    """Stable operation identity: type + OFM shape + kernel geometry."""
    return (op["type"], op["ofm"], op["kernel"])


def op_cycles(ops, prof):
    """Map per-launch records to schedule-op cycle sums, per the qualified
    mapping: record k <-> launch k+1; final launch <-> tail TOTAL."""
    launches = []
    for o in ops:
        launches += [o["idx"]] * o["slices"]
    k = len(launches)
    rows = [l.split(",") for l in prof["plprof"].splitlines()
            if l.startswith("PLPROF,")]
    recs = [{"ccnt": int(r[2]), "evt": [int(x) for x in r[3:8]]} for r in rows]
    if prof["pl_count"] != len(recs):
        raise Reject("PLPROF count mismatch")
    if len(recs) == k - 1:
        segs = recs + [{"ccnt": prof["total"], "evt": [None] * 5,
                        "tail": True}]
    elif len(recs) == k:
        segs = recs
    else:
        raise Reject("records %d vs launches %d" % (len(recs), k))
    out = {}
    for launch_idx, op_idx in enumerate(launches):
        s = segs[launch_idx]
        agg = out.setdefault(op_idx, {"ccnt": 0, "evt": [0] * 5,
                                      "tail_in_op": False})
        agg["ccnt"] += s["ccnt"]
        if s.get("tail"):
            agg["tail_in_op"] = True
            agg["evt"] = [None] * 5
        elif agg["evt"] is not None and agg["evt"][0] is not None:
            agg["evt"] = [a + b for a, b in zip(agg["evt"], s["evt"])]
    return out


def load_cell(root, model, label):
    d = os.path.join(root, "%s__%s" % (model, label))
    meta = json.load(open(os.path.join(d, "instr.meta.json")))
    ops = parse_schedule(os.path.join(d, "vela_verbose", "verbose.log"))
    clean = json.load(open(os.path.join(d, "clean.run1.json")))
    prof = None
    if meta["profiled"] == "OK":
        prof = json.load(open(os.path.join(d, "prof.run1.json")))
        exp = sum(o["slices"] for o in ops)
        if meta["irq_count"] != exp:
            raise Reject("irq_count %s != schedule launches %d"
                         % (meta["irq_count"], exp))
    return {"ops": ops, "clean": clean, "prof": prof, "meta": meta}


def main(root):
    match_rows, diff_rows = [], []
    for model in WORKLOADS:
        cells = {}
        for label in ("256_Low", "512_Mid512", "512_Low"):
            try:
                cells[label] = load_cell(root, model, label)
            except FileNotFoundError as e:
                raise Reject("missing evidence for %s__%s: %s" % (model, label, e))
        for binding, a_lbl, b_lbl in PAIRS:
            A, B = cells[a_lbl], cells[b_lbl]
            ia = [identity(o) for o in A["ops"]]
            ib = [identity(o) for o in B["ops"]]
            if len(set(ia)) != len(ia) or len(set(ib)) != len(ib):
                raise Reject("duplicate operation identity in %s %s" % (model, binding))
            if ia != ib:
                raise Reject("identity sequence mismatch %s %s "
                             "(missing/reordered operations)" % (model, binding))
            ca = op_cycles(A["ops"], A["prof"]) if A["prof"] else None
            cb = op_cycles(B["ops"], B["prof"]) if B["prof"] else None
            for oa, ob in zip(A["ops"], B["ops"]):
                changed = {
                    "UBLOCK_CHANGED": oa["ublock"] != ob["ublock"],
                    "BLOCK_CONFIG_CHANGED": oa["block"] != ob["block"],
                    "TILE_GEOMETRY_CHANGED": (oa["stripes"], oa["slices"])
                                             != (ob["stripes"], ob["slices"]),
                    "MEMORY_PLACEMENT_CHANGED": (oa["cascade"], oa["weight_buf"])
                                                != (ob["cascade"], ob["weight_buf"]),
                    "COMMAND_OR_PASS_STRUCTURE_CHANGED":
                        (oa["slices"], oa["time_index"])
                        != (ob["slices"], ob["time_index"]),
                }
                cyc_a = ca[oa["idx"]] if ca else None
                cyc_b = cb[ob["idx"]] if cb else None
                d = {"workload": model, "binding_pair": binding,
                     "op_identity": "|".join(identity(oa)),
                     "op_type": oa["type"],
                     "cycles_256": cyc_a["ccnt"] if cyc_a else None,
                     "cycles_512": cyc_b["ccnt"] if cyc_b else None,
                     "observed_direction": (
                         None if not (cyc_a and cyc_b) else
                         "REGRESS" if cyc_b["ccnt"] > cyc_a["ccnt"] else
                         "IMPROVE" if cyc_b["ccnt"] < cyc_a["ccnt"] else "SAME"),
                     "vela_cycles_256": oa["vela_cycles"],
                     "vela_cycles_512": ob["vela_cycles"],
                     "vela_direction": (
                         "REGRESS" if ob["vela_cycles"] > oa["vela_cycles"] else
                         "IMPROVE" if ob["vela_cycles"] < oa["vela_cycles"] else "SAME"),
                     "ublock_256": oa["ublock"], "ublock_512": ob["ublock"],
                     "block_256": oa["block"], "block_512": ob["block"],
                     "stripes_256": oa["stripes"].strip(),
                     "stripes_512": ob["stripes"].strip(),
                     "slices_256": oa["slices"], "slices_512": ob["slices"],
                     "cascade_256": oa["cascade"], "cascade_512": ob["cascade"],
                     "tail_in_op_256": cyc_a["tail_in_op"] if cyc_a else None,
                     "tail_in_op_512": cyc_b["tail_in_op"] if cyc_b else None,
                     **{k: int(v) for k, v in changed.items()}}
                if cyc_a and cyc_a["evt"][0] is not None:
                    for i, nm in enumerate(("active", "sram_rd", "sram_wr",
                                            "ext_rd", "ext_wr")):
                        d["%s_256" % nm] = cyc_a["evt"][i]
                if cyc_b and cyc_b["evt"][0] is not None:
                    for i, nm in enumerate(("active", "sram_rd", "sram_wr",
                                            "ext_rd", "ext_wr")):
                        d["%s_512" % nm] = cyc_b["evt"][i]
                diff_rows.append(d)
                match_rows.append({"workload": model, "binding_pair": binding,
                                   "op_identity": d["op_identity"],
                                   "idx_256": oa["idx"], "idx_512": ob["idx"],
                                   "slices_256": oa["slices"],
                                   "slices_512": ob["slices"],
                                   "matched": 1})
    cols = sorted({k for r in diff_rows for k in r})
    lead = ["workload", "binding_pair", "op_identity", "op_type",
            "cycles_256", "cycles_512", "observed_direction",
            "vela_cycles_256", "vela_cycles_512", "vela_direction"]
    cols = lead + [c for c in cols if c not in lead]
    with open(os.path.join(root, "U85_256_512_DIFFERENTIAL.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(diff_rows)
    with open(os.path.join(root, "U85_OPERATOR_MATCH.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(match_rows[0]))
        w.writeheader()
        w.writerows(match_rows)
    print("rows:", len(diff_rows), "matches:", len(match_rows))
    print("wrote U85_256_512_DIFFERENTIAL.csv, U85_OPERATOR_MATCH.csv")


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else ".")
    except Reject as e:
        print("REJECT:", e)
        sys.exit(2)
