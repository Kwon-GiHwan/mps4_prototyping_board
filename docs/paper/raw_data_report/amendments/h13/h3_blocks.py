"""H3 block-mapping table (plan section 7: 'link the actual generated block mapping to the execution change').

Joins, per synthetic model x MAC x condition: OFM shape, Vela OFM/IFM block, ublock, traversal (from the
--verbose-schedule dump), Vela's own estimated op cycles and MAC utilisation (per-layer CSV, informational only),
the measured stock PMU total cycles and the 512/256 ratio r. Writes h3_blocks.csv. Descriptive, no judgement.
"""
import csv, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OP_RE = re.compile(r"^\s*(\d+): Operation (\S+)\s+- OFM ([\d, ]+)$")
CFG_RE = re.compile(r"OFM Block=\[([\d, ]+)\], IFM Block=\[([\d, ]+)\](?:, OFM UBlock=\[([\d, ]+)\])?(?: Traversal=(\w+))?")


def ints(s):
    return [int(x) for x in s.split(",")]


def parse_dump(path):
    ops = []
    cur = None
    for line in open(path, errors="replace"):
        m = OP_RE.match(line)
        if m:
            cur = {"op": m.group(2), "ofm": ints(m.group(3))}; ops.append(cur); continue
        c = CFG_RE.search(line)
        if c and cur is not None and "ofm_block" not in cur:
            cur["ofm_block"] = ints(c.group(1)); cur["ifm_block"] = ints(c.group(2))
            cur["ublock"] = ints(c.group(3)) if c.group(3) else None; cur["traversal"] = c.group(4)
    return ops


def vela_estimate(d):
    for f in d.glob("*per-layer.csv"):
        rows = list(csv.DictReader(open(f)))
        if rows:
            r = rows[0]; return int(float(r["Op Cycles"])), float(r["Util% (MAC)"])
    return None, None


def main():
    res = json.load(open(HERE / "h13_results.json"))["H3"]
    cyc = {}
    for k, v in res["cycles"].items():
        model, cond, mac = k.split("|"); cyc[(model, cond, int(mac))] = v
    ratios = {tuple(k.split("|")): v for k, v in res["ratios"].items()}
    meta = {m["model"]: m for m in json.load(open(HERE / "h3_manifest.json"))}
    out = []
    for d in sorted((HERE / "vela").glob("h3_*")):
        cell, arm = d.name.split("__SSE-320__ethos-u85-")[0], d.name.rsplit("__", 1)[1]
        mac_part = d.name.split("__SSE-320__ethos-u85-")[1]
        mac = int(mac_part.split("__")[0]); ctrl = "__syscfgMid" in mac_part
        cond = "syscfgMid" if ctrl else arm
        ops = parse_dump(d / "vela_verbose.txt")
        if not ops:
            continue
        o = ops[0]; est, util = vela_estimate(d); m = meta[cell]
        ob = o.get("ofm_block") or [None] * 4
        # OFM block is [N,H,W,C] for Conv, [H,W,C] for depthwise dumps
        bh, bw, bc = (ob[1], ob[2], ob[3]) if len(ob) == 4 else (ob[0], ob[1], ob[2])
        ub = o.get("ublock") or [None] * 3
        out.append({"model": cell, "op": m["op"], "H": m["H"], "W": m["W"], "area": m["area"], "mac": mac, "cond": cond,
                    "ofm_block_HWC": "%sx%sx%s" % (bh, bw, bc), "ifm_block": "x".join(map(str, o.get("ifm_block") or [])),
                    "ublock_HWC": "x".join(map(str, ub)), "traversal": o.get("traversal"),
                    "H_mod_bH": (m["H"] % bh) if bh else None, "W_mod_bW": (m["W"] % bw) if bw else None,
                    "H_mod_uH": (m["H"] % ub[0]) if ub[0] else None, "W_mod_uW": (m["W"] % ub[1]) if ub[1] else None,
                    "n_blocks": (-(-m["H"] // bh) * -(-m["W"] // bw) * -(-128 // bc)) if bh and bw and bc else None,
                    "vela_est_cycles": est, "vela_util_pct": round(util, 1) if util is not None else None,
                    "pmu_total": cyc.get((cell, cond, mac)),
                    "r_512_over_256": ratios.get((cell, cond)) if mac == 256 else None})
    out.sort(key=lambda r: (r["op"], r["area"], r["H"], r["cond"], r["mac"]))
    with open(HERE / "h3_blocks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("rows", len(out))
    for r in out:
        if r["cond"] == "base":
            print("%-8s %3dx%-3d %4d %-12s ub=%-8s %-10s est=%-7s util=%-5s pmu=%-7s r=%s" % (
                r["op"], r["H"], r["W"], r["mac"], r["ofm_block_HWC"], r["ublock_HWC"], r["traversal"], r["vela_est_cycles"],
                r["vela_util_pct"], r["pmu_total"], r["r_512_over_256"] if r["r_512_over_256"] is not None else ""))


if __name__ == "__main__":
    main()
