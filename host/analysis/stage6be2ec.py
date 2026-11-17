#!/usr/bin/env python3
"""Stage 6B-E2E-C (evidence/stage6b/stage6be2ec/contract.md), board-free: residual EXT path attribution and pipeline
characterisation. Everything that reads E2E-B / E2D board data is POSTHOC_DIAGNOSTIC.

  python3 stage6be2ec.py run <out dir>
"""
from __future__ import annotations

import csv
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / "lib")]
import stage6be2eb as EB  # noqa: E402

EB_RAW = REPO / "evidence/stage6b/stage6be2eb/raw"
EB_WL = REPO / "evidence/stage6b/stage6be2eb/workloads"
EB_SUMMARY = REPO / "results/fi101_stage6b/stage6be2eb/stage6be2eb_summary.json"
REF375 = REPO / "evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe"
E2D_SUMMARY = REPO / "results/fi101_stage6b/stage6be2d/stage6be2d_summary.json"
VELA_FACTS = REPO / "evidence/stage6b/stage6be2ea/facts/vela.json"
EA_TRACKB = REPO / "results/fi101_stage6b/stage6be2ea/trackB/trackB_summary.json"
TRM = REPO / "docs/reference/trm_events_110.json"
S3_EVENTS = REPO / "results/fi101_stage3/events_pass_B_to_G.csv"
S3_CHANNELS = REPO / "results/fi101_stage3_channels/channel_verdicts.csv"
DRIVER_RUNNER = REPO / "firmware/driver_runner"
LEGACY_PMWL = REPO / "firmware/runner/pmwl.c"

REQUIRED = {"B0": {500: 99044.0, 1000: 159122.5, "le": 60078.5, "ext_rd": 27066.0, "ext_tr": 10417.0},
            "B3": {500: 60320.0, 1000: 72526.5, "le": 12206.5, "ext_rd": 11322.0, "ext_tr": 793.0}}
H1UC = 20736
REMOVED = (15744.0, 9624.0)                     # EXT read beats, transactions B0 -> B3
INVARIANT_REL = 0.01
EVENTS = {384: "ext_rd_trans_accepted", 385: "ext_rd_trans_completed", 386: "ext_rd_data_beat_received",
          387: "ext_rd_tran_req_stalled", 398: "ext_rd_stall_limit", 643: "ext0_rd_tran_req_stalled",
          659: "ext1_rd_tran_req_stalled", 640: "ext0_rd_trans_accepted", 642: "ext0_rd_data_beat_received",
          656: "ext1_rd_trans_accepted", 658: "ext1_rd_data_beat_received", 160: "axi_latency_any",
          161: "axi_latency_32", 164: "axi_latency_256", 166: "axi_latency_1024", 53: "reserved_53", 55: "reserved_55"}
CHANNELS = ("rd_cmd", "rd_ifm", "rd_weights", "rd_scale_bias", "rd_mem2mem", "rd_ifm_stream", "rd_mem2mem_idx",
            "wr_ofm", "wr_mem2mem")
# MLEK core-driver dependencies/core-driver/src/ethosu_device_u85.c (container; identical to its .bak copies)
DRIVER_SOURCE = dict(file="/opt/arm/ml-embedded-evaluation-kit/dependencies/core-driver/src/ethosu_device_u85.c",
                     remap_weak_line=54, config_select_weak_line=60, qbase_remap_line=147, qconfig_line=154,
                     basep_remap_line=158, regioncfg_line=163)
SRAM_LIMIT, SRAM_ALIGN, ARENA_LEN = 0x31400000, 0x10000, 0x200000
LOW, HIGH = 0.25, 0.75                          # method B prediction bands, fraction of LE(B3)
BUDGET = (5, 50)


# ---- Phase 0 ----------------------------------------------------------------------------------------------------------
def rerun_e2eb() -> tuple[dict, bytes]:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        s = EB.judge(str(EB_RAW / "evsweep_s6be2eb_run_l500"), str(EB_RAW / "evsweep_s6be2eb_run_l1000"), str(EB_WL),
                     str(REF375), str(tmp))
        return s, (tmp / "stage6be2eb_summary.json").read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def phase0_checks(s: dict, same_bytes: bool, committed: dict, drwl_diff: list) -> dict:
    r, k = s["results"], EB.key
    met = lambda c, L: r[k(c, L)]["metrics"]
    tr = lambda c, L: r[k(c, L)]["traffic"]
    c = dict(summary_bytes=same_bytes, verdicts=s["verdicts"] == committed.get("verdicts"))
    for cell, want in REQUIRED.items():
        c[f"{cell}_npu"] = all(met(cell, L)["npu_active"] == want[L] for L in (500, 1000))
        c[f"{cell}_le"] = met(cell, 1000)["npu_active"] - met(cell, 500)["npu_active"] == want["le"]
        c[f"{cell}_mac"] = all(met(cell, L)["mac_active"] == H1UC for L in (500, 1000))
        c[f"{cell}_ext"] = all((tr(cell, L)["ext_rd_beats"], tr(cell, L)["ext_rd_trans"]) == (want["ext_rd"], want["ext_tr"])
                               for L in (500, 1000))
    c["removed"] = all((tr("B0", L)["ext_rd_beats"] - tr("B3", L)["ext_rd_beats"],
                        tr("B0", L)["ext_rd_trans"] - tr("B3", L)["ext_rd_trans"]) == REMOVED for L in (500, 1000))
    tot = lambda c_, L, a, b: tr(c_, L)[a] + tr(c_, L)[b]
    c["conservation"] = all(tot("B0", L, x, y) == tot("B3", L, x, y) for L in (500, 1000)
                            for x, y in (("sram_rd_beats", "ext_rd_beats"), ("sram_rd_trans", "ext_rd_trans"),
                                         ("sram_wr_beats", "ext_wr_beats")))
    c["ao_wd_invariant"] = all(abs(met("B3", L)[x] - met("B0", L)[x]) <= INVARIANT_REL * met("B0", L)[x]
                               for L in (500, 1000) for x in ("ao_active", "wd_active"))
    c["outputs_valid"] = all(r[k(cell, L)]["status"] == "VALID" for cell in ("B0", "B3") for L in (500, 1000))
    c["command_stream_identical"] = drwl_diff == [(28, 0, 1)]
    return dict(ok=all(c.values()), checks=c)


def phase0() -> dict:
    s, b = rerun_e2eb()
    a, d = (EB_WL / "e2d_w1p1.drwl").read_bytes(), (EB_WL / "e2eb_b3.drwl").read_bytes()
    diff = [(i, a[i], d[i]) for i in range(min(len(a), len(d))) if a[i] != d[i]] if len(a) == len(d) else [None]
    res = phase0_checks(s, b == EB_SUMMARY.read_bytes(), json.loads(EB_SUMMARY.read_text()), diff)
    return dict(res, label="POSTHOC_DIAGNOSTIC", summary=s)


# ---- Phase 1 ----------------------------------------------------------------------------------------------------------
def event_status(ev: int, trm_ids: set, audit: dict) -> str:
    """audit: {ev: [verdict, ...]} from FI101 raw-data audits."""
    if ev not in trm_ids:
        return "RESERVED"
    v = audit.get(ev, [])
    if "INCONSISTENT" in v:
        return "INCONSISTENT_ON_FI101"
    if "COUNTED_NONZERO" in v:
        return "VERIFIED_ON_FI101"
    return "TRM_ONLY_UNVERIFIED"


def channel_status(ch: str, filter_works: set) -> str:
    if ch == "wr_ofm":
        return "WRITE_NOT_INTERPRETABLE"
    return "READ_FILTER_VERIFIED" if ch in filter_works else "UNVERIFIED"


def pmu_capability() -> dict:
    trm = {e[0] for e in json.loads(TRM.read_text())}
    audit: dict = {}
    with open(S3_EVENTS) as f:
        for row in csv.DictReader(f):
            audit.setdefault(int(row["ev_type"]), []).append(row["verdict"])
    with open(S3_CHANNELS) as f:
        rows = list(csv.DictReader(f))
    works = set.intersection(*[set(r["channels"].split(",")) for r in rows if r["verdict"] == "CHANNEL_FILTER_WORKS"]) \
        if rows and all(r["verdict"] == "CHANNEL_FILTER_WORKS" for r in rows) else set()
    drv = any("PMCAXI" in p.read_text(errors="ignore") for p in DRIVER_RUNNER.rglob("*") if p.is_file())
    legacy = LEGACY_PMWL.read_text()
    legacy_rb = "pmu_reg_write(NPU_REG_PMCAXI_CHAN_ABS" in legacy and "pmu_reg_read(NPU_REG_PMCAXI_CHAN_ABS)" in legacy
    events = {ev: dict(name=n, status=event_status(ev, trm, audit)) for ev, n in sorted(EVENTS.items())}
    channels = {ch: channel_status(ch, works) for ch in CHANNELS}
    items = {
        "1 PMCAXI_CHAN interface": dict(status="VERIFIED_SOURCE", evidence="TRM PMCAXI_CHAN @ PMU+0x2C (abs 0x11AC): CH_SEL[3:0], AXI_SEL[8], BW_CH_SEL_EN[10]; docs/reference/ETHOS_U85_PMU_REFERENCE.md"),
        "2 CH_SEL vs AXI_SEL": dict(status="VERIFIED_BOARD" if works else "UNVERIFIED",
                                    evidence="Stage 3 used AXI_SEL = 0 (SRAM) and both SRAM_* and EXT_* read beats/transactions were filtered: BW filter does not depend on AXI_SEL; AXI_SEL selects the port for axi_latency events (TRM)"),
        "3 BW_CH_SEL_EN scope": dict(status="VERIFIED_BOARD" if works else "UNVERIFIED",
                                     evidence="read beats and read transactions filtered (SRAM and EXT); write beats read 0 and write transactions unfiltered (not interpretable); npu_active unchanged"),
        "4 one filter for all counters": dict(status="VERIFIED_SOURCE", evidence="one PMCAXI_CHAN register: every bw event of a pass sees the same channel; one channel per pass"),
        "5 per-channel beats and transactions": dict(status="VERIFIED_BOARD" if works else "UNVERIFIED", evidence="Stage 3 tables report both per channel"),
        "6 filter does not change execution": dict(status="VERIFIED_BOARD" if works else "UNVERIFIED", evidence="CHANNEL_FILTER_WORKS rule includes npu_active and mac_active unchanged"),
        "7 sum vs unfiltered total": dict(status="VERIFIED_BOARD" if works else "UNVERIFIED", evidence="Stage 3: three channels cover 83.6-96 % of unfiltered read beats; rd_cmd / rd_scale_bias never measured"),
        "8 eight counters": dict(status="VERIFIED_SOURCE", evidence="PMCR.num_event_cnt = 8; NPU_ACTIVE anchor takes one"),
        "9 driver runner set/readback": dict(status="NOT_IMPLEMENTED" if not drv else "IMPLEMENTED",
                                             evidence=f"firmware/driver_runner has no PMCAXI_CHAN write; legacy runner writes and reads it back: {legacy_rb}"),
    }
    return dict(events=events, channels=channels, items=items, driver_runner_pmcaxi=drv, legacy_readback=legacy_rb)


# ---- Phase 2 ----------------------------------------------------------------------------------------------------------
def cell_row(name: str, L: int, npu: float, mac: float, pb: dict) -> dict:
    g = lambda c: pb.get(c, pb.get(str(c)))
    rd, tr = g(386), g(384)
    return dict(cell=name, latency=L, npu_active=npu, mac_active=mac, ext_rd_beats=rd, ext_rd_trans=tr,
                ext_beats_per_trans=rd / tr if tr else None, ext_trans_per_knpu=1000 * tr / npu,
                sram_rd_beats=g(130), sram_rd_trans=g(128),
                sram_beats_per_trans=g(130) / g(128) if g(128) else None, ext_wr_beats=g(391))


def pair(a: dict, b: dict) -> dict:
    """a, b: {500: row, 1000: row}; a = more EXT, b = graph IO on SRAM."""
    le = lambda x: x[1000]["npu_active"] - x[500]["npu_active"]
    db, dt = a[500]["ext_rd_beats"] - b[500]["ext_rd_beats"], a[500]["ext_rd_trans"] - b[500]["ext_rd_trans"]
    d_le = le(a) - le(b)
    return dict(removed_beats=db, removed_trans=dt, removed_beats_per_trans=db / dt if dt else None,
                le_from=le(a), le_to=le(b), delta_le=d_le, delta_le_per_removed_trans=d_le / dt if dt else None,
                residual_le_per_trans=le(b) / b[500]["ext_rd_trans"] if b[500]["ext_rd_trans"] else None,
                same_traffic_both_latencies=all(a[500][x] == a[1000][x] and b[500][x] == b[1000][x]
                                                for x in ("ext_rd_beats", "ext_rd_trans")),
                label="DESCRIPTIVE: not a per-transaction service time")


def transactions(eb: dict) -> dict:
    d = json.loads(E2D_SUMMARY.read_text())["results"]
    rows = {}
    for k, r in d.items():
        if k == "REF" or r.get("status") != "VALID":
            continue
        cell, L = k.rsplit("-L", 1)
        m = r["metrics"]
        rows.setdefault(cell, {})[int(L)] = cell_row(cell, int(L), m["npu_active"], m["mac_active"], r["pass_b"])
    for k, r in eb["results"].items():
        if k == "REF":
            continue
        cell, L = k.rsplit("-L", 1)
        m, t = r["metrics"], r["traffic"]
        pb = {386: t["ext_rd_beats"], 384: t["ext_rd_trans"], 130: t["sram_rd_beats"], 128: t["sram_rd_trans"],
              391: t["ext_wr_beats"]}
        rows.setdefault(cell, {})[int(L)] = cell_row(cell, int(L), m["npu_active"], m["mac_active"], pb)
    pairs = {"B0->B3": pair(rows["B0"], rows["B3"]), "W0-P0->W0-P1": pair(rows["W0-P0"], rows["W0-P1"])}
    weight_path = {c: dict(ext_rd_trans=rows[c][500]["ext_rd_trans"], ext_rd_beats=rows[c][500]["ext_rd_beats"],
                           le=rows[c][1000]["npu_active"] - rows[c][500]["npu_active"]) for c in ("W0-P1", "B3")}
    return dict(rows=rows, pairs=pairs, weight_path_only=weight_path, label="POSTHOC_DIAGNOSTIC")


VELA_MODEL = [
    ("read bytes", "element bytes inflated by burst efficiency (EstimateMemoryTransfer); NHWC read burst = block depth x 8 bit"),
    ("burst length", "enters ChannelBW: burst x min(RB/(burst/16), outstanding x ports x 0.8) / latency x 0.8"),
    ("read latency", "only through ChannelBW (a throughput limit, Little's law); no per-request or dependency stall"),
    ("outstanding", "max_reads x ports x 0.8 in ChannelBW; assumed fully used by full-size bursts"),
    ("port bandwidth", "clock_scale x 16 B x ports_used"),
    ("small requests", "not costed: transfer size per request is the configured burst; request count does not appear"),
    ("per-operation MAX", "op = max(npu, SRAM access, DRAM access); graph = sum of ops; no overlap or dependency between ops"),
]


def vela_ops() -> dict:
    v = json.loads(VELA_FACTS.read_text())["a2io"]["A2-base"]
    out = {}
    for L in ("L500", "L1000"):
        out[L] = [dict(operator=o["operator"], npu=int(o["npu_cycles"]), sram=int(o["Sram_ac"]), dram=int(o["Dram_ac"]),
                       op=int(o["op_cycles"])) for o in v[L]["perf"] if o["operator"] != "Relu6"]
    return out


# ---- Phase 3 ----------------------------------------------------------------------------------------------------------
def residual_channels(b3_ext_rd_beats: float) -> dict:
    s = json.loads(VELA_FACTS.read_text())["a2io"]["A2-base"]["L500"]["summary"]
    w = int(s["dram_weight_read_bytes"])
    total = int(s["dram_total_bytes"])
    fm = int(s["dram_feature_map_read_bytes"]) + int(s["dram_feature_map_write_bytes"])
    scale = total - fm - w
    cms = json.loads((EB_WL / "e2d_w1p1.drwl.json").read_text())["cms_len"]
    tb = json.loads(EA_TRACKB.read_text())["b2"]
    ch = dict(rd_weights=w, rd_scale_bias=scale, rd_cmd=cms, rd_ifm=0, rd_mem2mem=0)
    expected = sum(ch.values()) / 16
    return dict(channel_bytes=ch, channel_beats={k: v / 16 for k, v in ch.items()}, expected_beats=expected,
                board_beats=b3_ext_rd_beats, difference_bytes=(b3_ext_rd_beats - expected) * 16,
                region0_tensors=sorted(k for k, v in tb["tensor_regions"].items() if v == [0]),
                ext_regions_b3=tb["regions_on_ext_placement1"],
                note="difference not apportioned to channels; WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED kept")


HYPOTHESES = {
    "H-R1 weight/scale supply": dict(
        observable="method B: LE(B3w) <= 0.25 LE(B3), EXT read ~39 beats",
        not_separable="weight decode vs scale/bias fetch (both region 0); its pipeline consequences (H-R3)"),
    "H-R2 command fetch": dict(
        observable="method B: LE(B3w) >= 0.75 LE(B3) while EXT read falls to ~39 beats (command stream only)",
        not_separable="command fetch latency vs kernel-start dependency (H-R3)"),
    "H-R3 pipeline dependency": dict(
        observable="no direct observable here; mediates either H-R1 or H-R2",
        not_separable="DMA / WD / AO / MAC overlap; no public counter attributes cycles to it"),
}


# ---- Phase 4 ----------------------------------------------------------------------------------------------------------
def sram_copy_fits(arena_base: int, region0_base: int, region0_size: int) -> dict:
    """Method B: region 0 copied after the 2 MiB SRAM arena, 64 KiB aligned, keeping the low 16 address bits."""
    start = (arena_base + ARENA_LEN + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)
    base = start + (region0_base & (SRAM_ALIGN - 1))
    return dict(copy_base=base, copy_end=base + region0_size, fits=base + region0_size <= SRAM_LIMIT)


def method_status(prereqs: dict) -> str:
    return "UNAVAILABLE" if "FAILS" in prereqs.values() else "AVAILABLE"


def discriminating(predictions: dict) -> bool:
    return predictions.get("H-R1") is not None and predictions.get("H-R1") != predictions.get("H-R2")


def gate(m: dict) -> dict:
    instr_ok = all(m["prereqs"][p] in ("VERIFIED_SOURCE", "VERIFIED_BOARD") for p in m["instrumentation"])
    g = {"1 controlled variable": m["controlled_variable"] is not None,
         "2 different predictions": discriminating(m["predictions"]),
         "3 verifiable instrumentation": instr_ok,
         "4 not answerable from existing data": m["needs_new_data"],
         "5 small budget": m["budget"][0] <= BUDGET[0] and m["budget"][1] <= BUDGET[1]}
    return dict(criteria=g, passed=method_status(m["prereqs"]) == "AVAILABLE" and all(g.values()))


def methods(pmu: dict, b3_record: dict) -> dict:
    ch = pmu["channels"]
    fits = sram_copy_fits(b3_record["arena_base"], b3_record["base0"], b3_record["base_size0"])
    a = dict(controlled_variable="PMCAXI_CHAN channel (measurement only)",
             prereqs={"TRM fields": "VERIFIED_SOURCE",
                      "FI101 read-side filter": "VERIFIED_BOARD" if ch["rd_weights"] == "READ_FILTER_VERIFIED" else "BOARD_CHECK_REQUIRED",
                      "rd_cmd / rd_scale_bias filter": "VERIFIED_BOARD" if ch["rd_cmd"] == "READ_FILTER_VERIFIED" else "BOARD_CHECK_REQUIRED",
                      "driver runner set/readback": "VERIFIED_SOURCE" if pmu["driver_runner_pmcaxi"] else "BOARD_CHECK_REQUIRED",
                      "8 counters": "VERIFIED_SOURCE"},
             instrumentation=["FI101 read-side filter"],
             predictions={"H-R1": "channel bytes = static (weights 174,752 / scale 5,760 / cmd 628)",
                          "H-R2": "channel bytes = static (weights 174,752 / scale 5,760 / cmd 628)"},
             needs_new_data=True, budget=(4, 40))
    b = dict(controlled_variable="region 0 (weights + scale/bias) memory: EXT (B3) vs on-chip SRAM (B3w)",
             prereqs={"driver remap hook per base index": "VERIFIED_SOURCE",
                      "runner already overrides remap / config_select": "VERIFIED_SOURCE",
                      "region 0 holds only WEIGHT and SCALE": "VERIFIED_SOURCE",
                      "command stream outside region 0 (QBASE, QCONFIG unchanged)": "VERIFIED_SOURCE",
                      "SRAM capacity": "VERIFIED_SOURCE" if fits["fits"] else "FAILS",
                      "same DRWL / command stream": "VERIFIED_SOURCE",
                      "new image reproduces E2E-B B3 (control arm)": "BOARD_CHECK_REQUIRED",
                      "copy outside the measured window, cache clean": "BOARD_CHECK_REQUIRED",
                      "EXT read beats and REGIONCFG read-back": "VERIFIED_BOARD"},
             instrumentation=["EXT read beats and REGIONCFG read-back"],
             predictions={"H-R1": f"LE(B3w) <= {LOW} LE(B3); EXT read ~39 beats",
                          "H-R2": f"LE(B3w) >= {HIGH} LE(B3); EXT read ~39 beats",
                          "between": "MIXED"},
             needs_new_data=True, budget=(5, 50), sram_copy=fits)
    out = {}
    for name, m in (("A", a), ("B", b)):
        out[name] = dict(m, status=method_status(m["prereqs"]), discriminating=discriminating(m["predictions"]),
                         board_checks=sum(v == "BOARD_CHECK_REQUIRED" for v in m["prereqs"].values()), gate=gate(m))
    return out


def verdict(phase0_ok: bool, ms: dict) -> dict:
    if not phase0_ok:
        return dict(verdict="INVALID", selected=None)
    passed = [n for n in ("B", "A") if ms[n]["gate"]["passed"]]
    if passed:
        sel = min(passed, key=lambda n: (ms[n]["board_checks"], ("B", "A").index(n)))
        return dict(verdict="READY_FOR_TARGETED_BOARD_REVIEW", selected=sel)
    if not any(m["discriminating"] for m in ms.values()):
        return dict(verdict="MECHANISM_NOT_IDENTIFIABLE", selected=None)
    return dict(verdict="STATIC_CHARACTERIZATION_COMPLETE", selected=None)


# ---- run ----------------------------------------------------------------------------------------------------------------
def b3_record() -> dict:
    f = EB_RAW / "evsweep_s6be2eb_run_l500/conds/e2eb_b3/wfe/raw_runs.json"
    r = json.loads(f.read_text())[1]["record"]
    return {k: r[k] for k in ("arena_base", "base0", "base_size0", "regioncfg_irq", "qconfig_irq")}


def run(out: str) -> dict:
    p0 = phase0()
    eb = p0.pop("summary")
    pmu = pmu_capability()
    tx = transactions(eb)
    b3 = eb["results"]["B3-L500"]["traffic"]["ext_rd_beats"]
    ms = methods(pmu, b3_record())
    v = verdict(p0["ok"], ms)
    summary = dict(contract="evidence/stage6b/stage6be2ec/contract.md", ta="TA profile 1 (all board data reused)",
                   phase0=p0, pmu=pmu, transactions=tx, vela_model=VELA_MODEL, vela_ops=vela_ops(),
                   residual=residual_channels(b3), hypotheses=HYPOTHESES, driver_source=DRIVER_SOURCE,
                   methods=ms, final=v)
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    (o / "stage6be2ec_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str))
    with open(o / "ext_transactions.csv", "w", newline="") as f:
        rows = [r for c in tx["rows"].values() for r in c.values()]
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r["cell"], r["latency"])))
    return summary


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"]:
        r = run(sys.argv[2])
        print(json.dumps(dict(phase0=r["phase0"]["ok"], final=r["final"],
                              methods={n: (m["status"], m["discriminating"], m["gate"]["passed"]) for n, m in r["methods"].items()}),
                         indent=1))
    else:
        raise SystemExit(__doc__)
