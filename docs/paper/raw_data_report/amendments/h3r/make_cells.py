"""H3-R cell/arm definitions (plan A8 conditions table) -> h3r_cells.json + ta_matrix.csv.  /usr/bin/python3 make_cells.py

126 arms: 27 models x {256, 512} x {base, equalized} + dw3x3 9 models x {256, 512} x bridge_legacy_relaxed.
Every arm carries the FULL 16-value TA define set (nothing left to MLEK profile selection). bridge_legacy_relaxed is
asserted byte-identical to the H3 relaxed `defines` recorded in h13/results.jsonl for the same MAC (GO section 3.3).
The qualification cell (h3r_conv1x1_6x6_c128 x 256, arms base first) is listed first.
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from h3r_analyze import TA_KEYS, applied  # noqa: E402

FVP = "/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320"
SYSCFG = {256: "Ethos_U85_SYS_DRAM_Low", 512: "Ethos_U85_SYS_DRAM_Mid_512"}
RELAXED = {"EXT_RLATENCY": 0, "EXT_WLATENCY": 0, "EXT_BWCAP": 0, "SRAM_RLATENCY": 0, "SRAM_WLATENCY": 0}   # h13/gen_h3_models.py
EQUALIZED = {"SRAM_MAXR": 8, "SRAM_MAXW": 8, "SRAM_MAXRW": 0, "SRAM_RLATENCY": 0, "SRAM_WLATENCY": 0, "SRAM_PULSE_ON": 3999,
             "SRAM_PULSE_OFF": 1, "SRAM_BWCAP": 4000, "EXT_MAXR": 0, "EXT_MAXW": 0, "EXT_MAXRW": 0, "EXT_RLATENCY": 0,
             "EXT_WLATENCY": 0, "EXT_PULSE_ON": 4000, "EXT_PULSE_OFF": 1000, "EXT_BWCAP": 0}                # plan A8 (GO section 3.1)
assert set(EQUALIZED) == set(TA_KEYS) and EQUALIZED["EXT_PULSE_OFF"] != 0


def profiles():
    p = {}
    for r in csv.DictReader(open(os.path.join(HERE, "..", "h13", "ta_parameters.csv"))):
        p[r["ta_config"]] = {"%s_%s" % (s.upper(), k): (0 if k == "MAXRW" else int(r["%s_%s" % (s, k.lower())]))
                             for s in ("sram", "ext") for k in ("MAXR", "MAXW", "MAXRW", "RLATENCY", "WLATENCY", "PULSE_ON", "PULSE_OFF", "BWCAP")}
    return {256: p["u85_sys_dram_low"], 512: p["u85_sys_dram_mid"]}


def h3_relaxed_defines():
    """The exact H3 relaxed define sets per MAC from h13/results.jsonl (dw3x3 area-36 cells)."""
    out = {}
    for line in open(os.path.join(HERE, "..", "h13", "results.jsonl")):
        r = json.loads(line)
        if r.get("arm") == "relaxed" and r["cell_id"].startswith("h3_dw3x3_") and "measurement" in r:
            mac = int(r["cell_id"].split("ethos-u85-")[1])
            out.setdefault(mac, set()).add(json.dumps(r["defines"], sort_keys=True))
    assert all(len(v) == 1 for v in out.values()), {k: len(v) for k, v in out.items()}
    return {mac: json.loads(next(iter(v))) for mac, v in out.items()}


def cell(name, mac, arms):
    return {"cell_id": "%s__SSE-320__ethos-u85-%d" % (name, mac), "model": name, "model_path": "/tmp/h3r/models/%s.tflite" % name,
            "platform": "SSE-320", "npu": "ethos-u85", "mac_config": mac, "accelerator_config": "ethos-u85-%d" % mac,
            "system_config": SYSCFG[mac], "memory_mode": "Dedicated_Sram", "target_platform": "mps4", "target_subsystem": "sse-320",
            "fvp": FVP, "verbose": True, "experiment": "H3R", "arms": arms}


def main():
    prof = profiles(); legacy = h3_relaxed_defines()
    man = json.load(open(os.path.join(HERE, "h3r_manifest.json")))
    assert all(m["g1prime_pass"] for m in man), "G1' must pass before cells are defined"
    order = sorted(man, key=lambda m: (m["model"] != "h3r_conv1x1_6x6_c128", m["op"], m["H"]))   # qualification cell first
    cells, rows = [], []
    for m in order:
        for mac in (256, 512):
            arms = [["base", {}], ["equalized", dict(EQUALIZED)]]
            if m["op"] == "dw3x3":
                bridge = dict(prof[mac]); bridge.update(RELAXED)
                assert bridge == legacy[mac], ("bridge_legacy_relaxed != H3 relaxed defines", mac, bridge, legacy[mac])
                arms.append(["bridge_legacy_relaxed", dict(RELAXED)])
            cells.append(cell(m["model"], mac, arms))
            for arm, ov in arms:
                full = dict(prof[mac]); full.update(ov)
                ap = applied(full)
                rows.append(dict({"model": m["model"], "op": m["op"], "H": m["H"], "W": m["W"], "mac": mac, "arm": arm,
                                  "profile": "u85_sys_dram_low" if mac == 256 else "u85_sys_dram_mid"},
                                 **{"%s_requested" % k: full[k] for k in TA_KEYS}, **{"%s_applied" % k: ap[k] for k in TA_KEYS}))
    eq = {}
    for r in rows:
        if r["arm"] == "equalized":
            eq.setdefault(r["model"], {})[r["mac"]] = tuple(r["%s_applied" % k] for k in TA_KEYS)
    assert all(v[256] == v[512] for v in eq.values()), "equalized applied values differ across MACs"
    json.dump(cells, open(os.path.join(HERE, "h3r_cells.json"), "w"), indent=1)
    with open(os.path.join(HERE, "ta_matrix.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    n_arms = sum(len(c["arms"]) for c in cells)
    print("cells", len(cells), "arms", n_arms, "bridge == H3 relaxed defines for", sorted(legacy))
    assert n_arms == 126, n_arms


if __name__ == "__main__":
    main()
