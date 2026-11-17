#!/usr/bin/env python3
"""Stage 6B-B board judge (evidence/stage6b/stage6bb/contract.md, frozen before boot 410). Every pass/fail rule of the
measurement is here; the Stage 4K / 4AO-E functions it reuses (identity, identity_a1, reproduce, output checks, metrics)
are imported unchanged.

  stage6bb.py manifest   <workloads dir>                                  (Mac, before the board: experiment manifest)
  stage6bb.py repro-gate <root> <workloads> <reference folder> <caps ref>  (boot 1; rc 1 = stop)
  stage6bb.py boot-check <root> <workloads> <cfg> <caps ref>               (every other boot; rc 1 = stop)
  stage6bb.py judge      <root> <workloads> <reference folder> <caps ref> <out dir>
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import stage4 as S4  # noqa: E402
import stage4ao as AO  # noqa: E402
import stage4aoe as AOE  # noqa: E402
import stage4k as K  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = "stage6bb_manifest.json"
REF = "s4c2_conv_cin48"
ORDER = [REF] + [f"s6bb_{g}" for g in ("g12", "g25", "g40", "g53", "g11", "g56", "g52", "g57", "g09", "g28")]
FIRST_BOOT = 410
IMAGE = dict(boot_sha256="718c456283bfd44863d5fb697360b680ff4dc6b297cc0dc74d7ed78a6ca7ef59",
             bram_sha256="c80e77df9fe14b908966a5cebc5045cca93c5fd98bcea50fb1a7aef35f9fe99c",
             ddr_sha256="374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb",
             images_txt_sha256="af688281435a73dda3b2247845149817ecc7a9bbdff5a3ccd2e4dfa52875423f")   # = 70090f1
FPGA = "FI101"
LOG2_MACS = 10                 # NPU CONFIG macs_per_cc field (bits 3:0) = log2(1024)
N_RUNS, SETS = 10, [1, 2]
AB_REL = AOE.AB_REL            # NPU_ACTIVE pass A vs pass B: |B - A| <= max(5 % of A, range A + range B)
RANGE_REL = 0.05               # NPU_ACTIVE pass A range <= 5 % of its median
STATES = ("VALID", "INVALID_OUTPUT", "INVALID_PMU", "UNSTABLE", "CONFIG_MISMATCH", "NOT_COMPARABLE", "UNMEASURED")
STOP = ("CONFIG_MISMATCH", "UNMEASURED")       # boot-check rc 1 -> the session stops
STAGE4K_RATES = (640, 768)                     # descriptive comparison only
IDENT_PMU = ("runs",)                          # identity terms that are a measurement (RUN count) failure
IDENT_OUTPUT = ("one_crc", "output_len")       # identity terms that are an output failure


# ---- manifest (static, before the board) -------------------------------------------------------------------------------
def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hwc(s: str) -> list[int]:
    return [int(x) for x in s.split("x")]


def blocks(ofm: str, blk: str) -> int:
    (h, w, c), (bh, bw, bc) = hwc(ofm), hwc(blk)
    return math.ceil(h / bh) * math.ceil(w / bw) * math.ceil(c / bc)


def manifest(wl: str) -> dict:
    """Experiment manifest from the committed Revision A / Amendment B evidence and the staged workloads."""
    wl = pathlib.Path(wl)
    ev = REPO / "evidence" / "stage6b" / "revision_a"
    fx = json.loads((ev / "amendment_b" / "facts" / "fixture" / "fixture.json").read_text())
    vt = json.loads((ev / "amendment_b" / "facts" / "vela_total.json").read_text())
    out, ident = {}, {}
    k4 = json.loads((wl / f"{REF}.compile.json").read_text())
    out[REF] = dict(order=0, boot=FIRST_BOOT, kind="reference", group="Stage4K_cin48", drwl_sha256=sha(wl / f"{REF}.drwl"),
                    tflite_ofm_sha256=sha(wl / f"{REF}.drwl.tflite_ofm.bin"), n_mac=k4["n_mac"], cin=48, cout=96,
                    ifm_hwc="24x24x48", ofm_hwc="24x24x96", ofm_block=k4["ofm_block"], ifm_block=k4["ifm_block"],
                    ofm_ublock=k4["ofm_ublock"], traversal=k4["traversal"], n_base=5, placement=0,
                    spatial_blocks=blocks("24x24x96", k4["ofm_block"]), cin_mod16=0, cout_mod16=0,
                    output_check="PASS_EXACT vs tflite_ofm (Stage 4K rule)", internal_conv="CONV_OUTPUT_OBSERVED",
                    vela=dict(status="NOT_COMPARABLE", why="reference: not an A2 compile; outside the fidelity analysis"))
    ident[REF] = dict(custom_op_inputs=5, custom_op_outputs=1, n_base=5, placement=0, drwl_sha256=out[REF]["drwl_sha256"])
    for i, cfg in enumerate(ORDER[1:], 1):
        g = cfg.split("_")[1].upper()
        rec = json.loads((ev / "compiled" / f"s6b_{g.lower()}.ra.json").read_text())
        a2, src, f = rec["forms"]["A2"], rec["source"], fx[g]
        row, meta = a2["conv_row"], json.loads((wl / f"{cfg}.drwl.json").read_text())
        i_t = src["tensors"]["ifm"]
        out[cfg] = dict(
            order=i, boot=FIRST_BOOT + i, kind="A2", group=g, drwl_sha256=sha(wl / f"{cfg}.drwl"),
            golden_sha256=sha(wl / f"{cfg}.ref_ofm.bin"), tflite_ofm_sha256=sha(wl / f"{cfg}.drwl.tflite_ofm.bin"),
            ifm_sha256=sha(wl / f"{cfg}.ifm.bin"), vela_sha256=meta["vela_sha256"], cms_sha256=sha(wl / f"{cfg}.drwl.cms.bin"),
            n_mac=int(row["mac_count"]), cin=int(row["cin"]), cout=int(row["cout"]), ifm_hwc=row["npu_ifm_hwc"],
            ofm_hwc=row["npu_ofm_hwc"], ofm_block=row["ofm_block"], ifm_block=row["ifm_block"], ofm_ublock=row["ofm_ublock"],
            traversal=row["traversal"], ifm_memory=row["ifm_memory"], ofm_memory=row["ofm_memory"],
            weight_bytes=int(row["weight_bytes"]), n_conv_kernels=len(a2["conv_kernels"]),
            spatial_blocks=blocks(row["npu_ofm_hwc"], row["ofm_block"]), cin_mod16=int(row["cin"]) % 16,
            cout_mod16=int(row["cout"]) % 16, n_base=a2["n_base"], placement=a2["placement"],
            output_check="output.bin = golden (BUILTIN_REF on the fixture input), every RUN output_match",
            internal_conv="INTERNAL_CONV_NOT_OBSERVED",
            input=dict(kind="MLEK model-internal Conv input (Amendment B fixture)", model=src["model"], op_index=src["op_index"],
                       shape=list(i_t["shape"]), dtype="int8", scale=i_t["scale"], zero_point=i_t["zp"],
                       mlek_input_sha256=f["input_sha256"], b_input="filled with the IFM zero point",
                       fixture_ifm_sha256=sha(wl / f"{cfg}.ifm.bin")),
            vela=dict(cycles_total=int(vt[g]["summary"]["cycles_total"]), scope="A2 graph (Vela summary cycles_total)",
                      vela_sha256=vt[g]["vela_sha256"], system_config=vt[g]["summary"]["system_config"],
                      core_clock=vt[g]["summary"]["core_clock"], conv_op_cycles=int(row["vela_op_cycles"]),
                      conv_mac_cycles=int(row["vela_mac_cycles"])))
        ident[cfg] = dict(custom_op_inputs=a2["n_base"], custom_op_outputs=1, n_base=a2["n_base"], placement=a2["placement"],
                          drwl_sha256=out[cfg]["drwl_sha256"])
    (wl / MANIFEST).write_text(json.dumps(out, indent=1))
    (wl / AOE.MANIFEST).write_text(json.dumps(ident, indent=1))
    return out


def static_checks(wl: pathlib.Path) -> dict:
    """Pre-board consistency of the manifest with the staged files (part of the preflight)."""
    man = json.loads((wl / MANIFEST).read_text())
    bad = []
    for cfg in ORDER:
        m = man.get(cfg)
        if not m:
            bad.append(f"{cfg}: not in manifest"); continue
        if sha(wl / f"{cfg}.drwl") != m["drwl_sha256"]:
            bad.append(f"{cfg}: drwl digest")
        h, w, c = hwc(m["ifm_hwc"]); oh, ow, co = hwc(m["ofm_hwc"])
        if (h, w, c, oh, ow, co) != (oh, ow, m["cin"], h, w, m["cout"]) or oh * ow * m["cin"] * m["cout"] != m["n_mac"]:
            bad.append(f"{cfg}: N_MAC != H*W*Cin*Cout")
        exp = AOE.expected_identity(wl, cfg)
        if not exp["agree"] or exp["n_base"] != m["n_base"]:
            bad.append(f"{cfg}: n_base manifest/header")
        if m["kind"] == "A2":
            if sha(wl / f"{cfg}.ref_ofm.bin") != m["golden_sha256"]:
                bad.append(f"{cfg}: golden digest")
            meta = json.loads((wl / f"{cfg}.drwl.json").read_text())
            if meta["golden_sha256"] != m["golden_sha256"] or meta["blob_sha256"] != m["drwl_sha256"]:
                bad.append(f"{cfg}: packer meta")
            if vela_source(m) is not None:
                bad.append(f"{cfg}: {vela_source(m)}")
    return dict(ok=not bad, problems=bad)


def vela_source(m: dict) -> str | None:
    """None when the Vela estimate belongs to the measured binary and covers the measured scope (the A2 graph)."""
    v = m.get("vela") or {}
    if not isinstance(v.get("cycles_total"), int) or v["cycles_total"] <= 0:
        return "Vela cycles missing"
    if v.get("vela_sha256") != m.get("vela_sha256"):
        return "Vela estimate from another compile"
    if not str(v.get("scope", "")).startswith("A2 graph"):
        return "Vela scope is not the A2 graph"
    return None


# ---- per-config board result -------------------------------------------------------------------------------------------
def rows_of(folder: pathlib.Path) -> list[dict]:
    with open(folder / "runs.csv") as f:
        return list(csv.DictReader(f))


def identity_of(folder: pathlib.Path, wl: pathlib.Path, cfg: str, m: dict, caps_ref: str) -> dict:
    exp = m.get("placement", 0)                  # the frozen manifest's placement (absent before E2D: 0)
    return K.identity(folder, wl, cfg, caps_ref, exp) if m["kind"] == "reference" \
        else AOE.identity_a1(folder, wl, cfg, caps_ref, exp)


def environment(folder: pathlib.Path, wl: pathlib.Path, cfg: str, m: dict, caps_ref: str, ident: dict) -> list[str]:
    """CONFIG_MISMATCH reasons: experiment / workload / image / board / NPU / TA identity."""
    bad = []
    rows = rows_of(folder)
    if not rows:
        return ["no RUN rows"]
    if {r["workload_sha256"] for r in rows} != {m["drwl_sha256"]}:
        bad.append("workload sha256")
    for k, v in IMAGE.items():
        if {r[k] for r in rows} != {v}:
            bad.append(f"image {k}")
    if not all(r["fpga_image"].startswith(FPGA) for r in rows):
        bad.append("fpga image")
    if {r["host_boot_index"] for r in rows} != {str(m["boot"])}:
        bad.append("boot index")
    if {r["condition"] for r in rows} != {"wfe"}:
        bad.append("condition")
    caps_p = folder.parent / "capabilities.json"          # equality with the reference (TA registers, AXI, NPU
    caps = json.loads(caps_p.read_text()) if caps_p.exists() else {}   # config) is the identity term "capabilities"
    if (caps.get("npu_config", 0) & 0xF) != LOG2_MACS:
        bad.append("NPU MAC count")
    bad += [f"identity {k}" for k, v in ident["checks"].items() if not v and k not in IDENT_PMU + IDENT_OUTPUT]
    return bad


def pmu(folder: pathlib.Path, runs: dict, n_mac: int) -> list[str]:
    """INVALID_PMU reasons: RUN validity (job, IRQ, overflow, armed codes, window), pass layout, missing counters."""
    bad = []
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    if len(raw) != N_RUNS or sorted({(x["set_id"], x["rep"]) for x in raw}) != [(s, r) for s in SETS for r in range(1, 6)]:
        bad.append("RUN layout (2 passes x (1 warm-up + 4))")
    for s, codes in ((1, S4.PASS_A), (2, S4.PASS_B)):
        for r in runs.get(s, []):
            if not r["valid"]:
                bad.append(f"set {s} RUN invalid")
            if any(r["ev"].get(c) is None for c in codes) or sorted(r["ev"]) != sorted(codes):
                bad.append(f"set {s} counters missing or wrong pass")
    for r in rows_of(folder):
        if r["event_overflow"] not in ("False", "0", ""):
            bad.append("counter overflow")
        if r["cycle_valid"] not in ("1", "True"):
            bad.append("measurement window")
    mac = [r["ev"].get(48) for r in runs.get(1, [])]
    if mac and all(isinstance(v, int) for v in mac) and min(mac) * 1024 < n_mac:
        bad.append("MAC_ACTIVE below N_MAC/1024 (implausible)")
    return sorted(set(bad))


def stability(s: dict) -> list[str]:
    m, bad = s["metrics"], []
    if len(set(s["mac_active"])) != 1:
        bad.append("MAC_ACTIVE differs across measured RUNs")
    if len(set(s["mac_dpu_active"])) != 1:
        bad.append("MAC_DPU_ACTIVE differs across measured RUNs")
    a, b, ra, rb = m.get("A_35"), m.get("B_35"), m.get("A_35_range") or 0, m.get("B_35_range") or 0
    if a is None or b is None or abs(b - a) > max(AB_REL * a, ra + rb):
        bad.append("NPU_ACTIVE pass A vs pass B")
    if a is None or ra > RANGE_REL * a:
        bad.append("NPU_ACTIVE pass A range")
    return bad


def output_ok(folder: pathlib.Path, wl: pathlib.Path, cfg: str, m: dict, runs: dict) -> bool:
    if m["kind"] == "reference":
        comp = json.loads((wl / f"{cfg}.compile.json").read_text())
        return S4.output_check(folder, comp, (wl / f"{cfg}.drwl.tflite_ofm.bin").read_bytes(), runs)["verdict"] == "PASS_EXACT"
    return AOE.output_exact(folder, (wl / f"{cfg}.ref_ofm.bin").read_bytes(), runs)


def c16_rate(cin: int) -> float:
    """Descriptive comparison value fixed before the data: 768 x Cin / (Cin rounded up to 16), the Stage 4K 1x1
    DepthFirst observations (Cin 40 -> 640, Cin 48/64 -> 768) written as one expression. Not a gate, not an expectation."""
    return 768 * cin / (math.ceil(cin / 16) * 16)


def rates(m: dict, met: dict) -> dict:
    n, a35, a48, a51 = m["n_mac"], met.get("A_35"), met.get("A_48"), met.get("A_51")
    r = dict(n_mac=n, npu_active=a35, npu_active_range=met.get("A_35_range"), npu_active_pass_b=met.get("B_35"),
             mac_active=a48, mac_dpu_active=a51, ao_active=met.get("A_64"), wd_active=met.get("A_80"),
             wd_stalled=met.get("A_81"), reserved_53=met.get("A_53"), reserved_55=met.get("A_55"),
             pass_b={c: met.get(f"B_{c}") for c in S4.PASS_B[1:]})
    if a35 and a48:
        rate = n / a48
        r.update(mac_activity=a48 / a35, macs_per_mac_active=rate, eff_1024=rate / 1024, dpu_over_mac=a51 / a48 if a51 is not None else None,
                 macs_per_1024_npu_active=n / (1024 * a35),
                 stage4k_nearest=min(STAGE4K_RATES, key=lambda x: abs(x - rate)),
                 rate_over_640=rate / 640, rate_over_768=rate / 768,
                 c16_rate_768=c16_rate(m["cin"]), rate_over_c16_768=rate / c16_rate(m["cin"]))
    return r


def config_result(root: pathlib.Path, wl: pathlib.Path, cfg: str, caps_ref: str) -> dict:
    m = json.loads((wl / MANIFEST).read_text())[cfg]
    folder = root / "conds" / cfg / "wfe"
    base = dict(config=cfg, group=m["group"], kind=m["kind"], internal_conv=m["internal_conv"])
    if not (folder / "raw_runs.json").exists() or not (folder / "runs.csv").exists():
        return dict(base, status="UNMEASURED", reasons=["no raw data"])
    ident = identity_of(folder, wl, cfg, m, caps_ref)
    env = environment(folder, wl, cfg, m, caps_ref, ident)
    if env:
        return dict(base, status="CONFIG_MISMATCH", reasons=env)
    s = K.summary_of(folder, m["n_mac"])
    met = rates(m, s["metrics"])
    if not output_ok(folder, wl, cfg, m, s["runs"]) or not all(ident["checks"][k] for k in IDENT_OUTPUT):
        return dict(base, status="INVALID_OUTPUT", reasons=["board output != reference"], output_board_verified=False)
    p = pmu(folder, s["runs"], m["n_mac"])      # the identity RUN count is the RUN layout term of pmu()
    if p:
        return dict(base, status="INVALID_PMU", reasons=p, output_board_verified=True)
    st = stability(s)
    res = dict(base, output_board_verified=True, metrics=met, mac_active_runs=s["mac_active"],
               mac_dpu_active_runs=s["mac_dpu_active"], output_sha256=s["output_sha256"])
    return dict(res, status="UNSTABLE", reasons=st) if st else dict(res, status="VALID", reasons=[])


def fidelity(m: dict, r: dict) -> dict:
    """Vela estimate vs NPU_ACTIVE for the same A2 binary, same scope; otherwise NOT_COMPARABLE (no number)."""
    if m["kind"] != "A2":
        return dict(status="NOT_COMPARABLE", why="reference config")
    why = vela_source(m)
    if why:
        return dict(status="NOT_COMPARABLE", why=why)
    if r["status"] != "VALID":
        return dict(status="NOT_COMPARABLE", why=f"board result {r['status']}")
    v, b = m["vela"]["cycles_total"], r["metrics"]["npu_active"]
    e = (b - v) / v * 100
    return dict(status="COMPARABLE", vela_cycles=v, npu_active=b, error_pct=e, abs_error_pct=abs(e),
                conditions="Vela Ethos_U85_SYS_DRAM_Mid_1024 at 1 GHz (NPU cycles) vs board NPU_ACTIVE (NPU cycles), TA profile 1")


# ---- gates and verdicts -------------------------------------------------------------------------------------------------
def repro_gate(root: str, wl: str, ref: str, caps_ref: str) -> dict:
    """Boot 1: the Stage 4K Cin48 binary on the same image against its boot 375: this config VALID (all Stage 6B-B checks),
    the same DRWL as boot 375, and stage4k.reproduce (MAC/DPU equal in every RUN and to boot 375, output sha256, constant
    counters, NPU_ACTIVE within max(1 %, ranges))."""
    root, wlp, ref = pathlib.Path(root), pathlib.Path(wl), pathlib.Path(ref)
    r = config_result(root, wlp, REF, caps_ref)
    if r["status"] != "VALID":
        return dict(verdict="FAIL", why=r["status"], reasons=r["reasons"])
    same_bin = {x["workload_sha256"] for x in rows_of(ref)} == {r_["workload_sha256"] for r_ in rows_of(root / "conds" / REF / "wfe")}
    m = json.loads((wlp / MANIFEST).read_text())[REF]
    rep = K.reproduce(K.summary_of(root / "conds" / REF / "wfe", m["n_mac"]), K.summary_of(ref, m["n_mac"]))
    return dict(verdict="PASS" if rep["ok"] and same_bin else "FAIL", same_binary=same_bin, reproduce=rep)


def boot_check(root: str, wl: str, cfg: str, caps_ref: str) -> dict:
    r = config_result(pathlib.Path(root), pathlib.Path(wl), cfg, caps_ref)
    return dict(config=cfg, status=r["status"], reasons=r["reasons"], stop=r["status"] in STOP)


def characterization(gate: dict, res: dict) -> str:
    reps = [c for c in ORDER[1:]]
    valid = [c for c in reps if res[c]["status"] == "VALID"]
    if gate.get("verdict") != "PASS" or any(res[c]["status"] == "CONFIG_MISMATCH" for c in ORDER) or not valid:
        return "MEASUREMENT_INVALID"
    return "CHARACTERIZATION_VALID" if len(valid) == len(reps) else "PARTIAL_CHARACTERIZATION"


def fidelity_verdict(fid: dict) -> str:
    reps = ORDER[1:]
    n = sum(fid[c]["status"] == "COMPARABLE" for c in reps)
    return "FIDELITY_COMPARABLE" if n == len(reps) else "FIDELITY_PARTIAL" if n else "FIDELITY_NOT_COMPARABLE"


def judge(root: str, wl: str, ref: str, caps_ref: str, out: str) -> dict:
    rootp, wlp = pathlib.Path(root), pathlib.Path(wl)
    man = json.loads((wlp / MANIFEST).read_text())
    gate = repro_gate(root, wl, ref, caps_ref) if (rootp / "conds" / REF / "wfe" / "runs.csv").exists() \
        else dict(verdict="FAIL", why="UNMEASURED")
    res = {c: config_result(rootp, wlp, c, caps_ref) for c in ORDER}
    fid = {c: fidelity(man[c], res[c]) for c in ORDER}
    summary = dict(contract="evidence/stage6b/stage6bb/contract.md", reference_gate=gate, results=res, fidelity=fid,
                   characterization=characterization(gate, res), fidelity_verdict=fidelity_verdict(fid),
                   counts={s: sum(r["status"] == s for r in res.values()) for s in STATES})
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6bb_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def main(argv: list) -> int:
    cmd, a = argv[0], argv[1:]
    if cmd == "manifest":
        manifest(a[0]); r = static_checks(pathlib.Path(a[0])); print(json.dumps(r, indent=1)); return 0 if r["ok"] else 1
    if cmd == "repro-gate":
        r = repro_gate(*a[:4]); print(json.dumps(r, indent=1, default=str)); return 0 if r["verdict"] == "PASS" else 1
    if cmd == "boot-check":
        r = boot_check(*a[:4]); print(json.dumps(r, indent=1, default=str)); return 1 if r["stop"] else 0
    if cmd == "judge":
        r = judge(*a[:5])
        print(json.dumps({k: r[k] for k in ("characterization", "fidelity_verdict", "counts")}, indent=1)); return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
