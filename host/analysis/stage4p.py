#!/usr/bin/env python3
"""Stage 4 placement comparison (docs/plan/stage4_memory_placement_plan.md; contract draft
evidence/stage4_placement/contract_draft.md): Stage 4 conv_base with region 1 (IFM + OFM) in DDR on the EXT port (A)
against the same workload with region 1 in on-chip SRAM on the SRAM port (B). TA profile 1, driver runner, one new image,
1 warm-up + 4 measured RUNs per pass. B changes the physical memory, the NPU port and the timing adapter on that port
together; a difference is a "DRAM path vs SRAM path under TA profile 1" difference, never a pure memory-latency one.

  python3 host/analysis/stage4p.py make-b <A.drwl> <B.drwl>          the B workload: header word 7 = 1, nothing else
  python3 host/analysis/stage4p.py gate-b <A.drwl> <B.drwl> <A.drwl.json> <A.drwl.cms.bin>
  python3 host/analysis/stage4p.py p1-gate <A folder> <compile dir> <Stage 4 capabilities.json>
      on the board host between the A boot and the B boot: exit 0 only if P0 + P1 pass (else the session stops, B never
      runs); writes <A folder>/p1_gate.json
  python3 host/analysis/stage4p.py analyse <A folder> <B folder> <compile dir> <out dir> <A.drwl> <B.drwl> <cms.bin>
      (a folder = run_driver_events.py's condition folder: raw_runs.json, runs.csv, output.bin; capabilities.json in it
       or in its parent)

Rules (fixed before the data):
  gate B      the two blobs differ only in header word 7 (A 0, B 1); A is byte-identical to the Stage 4 blob; model
              (Vela command stream, weights, bias, scales, tensor definitions), IFM and golden sections identical; the
              Stage 4 command stream occurs once in the model at the same offset in both
  poison      the first RUN after the load (set 1 rep 1, the only RUN whose OFM was poisoned with 0x5A at the load)
              matches its golden: the NPU wrote this output at this placement
  placement   every measured RUN: schema 4, placement, arena_base = base1, base_size1, REGIONCFG/QCONFIG at the IRQ and
              REGIONCFG_MATCH as EXPECTED; base0/base2/sizes/n_base/model/arena_len equal between A and B; capabilities
              (MEM_ATTR, AXI, TA, fast memory) equal between the two boots
  gate C      stage4.output_check PASS_EXACT, every measured RUN valid (record_v2.validity), passes 1 and 2 with 4 RUNs
  outputs     A and B output CRCs equal
  P0          the new image's capabilities equal Stage 4 conv_base's (boot 330) on the TA profile 1 registers, AXI limits,
              MEM_ATTR and the fast memory (CAPS_SAME)
  P1          A reproduces Stage 4 conv_base (image 83398c7, boot 330, TA profile 1): MAC_ACTIVE, MAC_DPU_ACTIVE and the
              pass-B beat counters (range 0 there) equal; NPU_ACTIVE pass A within max(1 %, Stage 4 range, A range);
              output CRC equal
  traffic     pass-B beat medians, each "changed" by the tolerance rule below: EXT wr (391) and EXT rd (386) lower, SRAM rd
              (130) and SRAM wr (135) higher in B -> TRAFFIC_CONSISTENT, else TRAFFIC_INCONSISTENT (stops the reading)
  cost        per pass (1 = pass A, 2 = pass B), NPU_ACTIVE (35): tol = max(1 % of the A median, A range, B range);
              both passes outside tol with the same sign -> B_LOWER / B_HIGHER, else UNRESOLVED
  compute     |dMAC_ACTIVE| and |dMAC_DPU_ACTIVE| (pass A) <= max(A range, B range) -> COMPUTE_SAME, else COMPUTE_CHANGED
  auxiliary   AO, WD, WD_STALLED and the pass-B beats: CHANGED / NOT_RESOLVED by the cost tolerance; no cause assigned
  any of gate B, placement, gate C, outputs, P1, traffic failing -> NOT_INTERPRETED (no cost or compute verdict).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drwl
import record_v2
import stage4

FLOOR = stage4.FLOOR
# Stage 4 conv_base, image 83398c7, boot 330, TA profile 1 (results/fi101_stage4/stage4_summary.csv, raw_runs.json)
STAGE4 = dict(blob_sha256="2681c566729ce568f4041df6a69d1b5c5c558d2172bb76b6d75ad64ca2b4f267", output_crc32=2368219480,
              npu_active=21207, npu_active_range=367,
              exact={(1, 48): 2304, (1, 51): 1152, (2, 128): 304, (2, 130): 2016, (2, 132): 16, (2, 135): 252,
                     (2, 384): 171, (2, 386): 1437, (2, 391): 3456})
EXPECTED = {0: dict(arena_base=0x700015C0, regioncfg=0x15F), 1: dict(arena_base=0x310615C0, regioncfg=0x153)}
QCONFIG, BASE_SIZE1 = 3, 0xFC00
SAME_FIELDS = ("n_base", "model_base", "model_len", "arena_len", "base0", "base2", "base_size0", "base_size1",
               "base_size2")
CAPS_SAME = ("fast_base", "fast_size", "axi_sram", "axi_ext", "mem_attr0", "mem_attr1", "mem_attr2", "mem_attr3",
             "ta_sram_version", "ta_ext_version") + tuple(f"ta_{p}_{n}" for p in ("sram", "ext") for n in record_v2.TA11)
TRAFFIC_SIGN = {391: -1, 386: -1, 130: +1, 135: +1}     # EXT wr, EXT rd, SRAM rd, SRAM wr (plan §6)
AUX = [(1, 64), (1, 80), (1, 81)] + [(2, c) for c in stage4.PASS_B[1:]]


# ---------------------------------------------------------------- workloads (gate B)
def make_b(a: bytes) -> bytes:
    if drwl.parse(a)["placement"] != drwl.PLACEMENT_DDR:
        raise ValueError("the A workload must be the DDR placement")
    return drwl.with_placement(a, drwl.PLACEMENT_SRAM)


def gate_b(a: bytes, b: bytes, meta: dict, cms: bytes) -> dict:
    ha, hb = drwl.parse(a), drwl.parse(b)
    sec = lambda blob, h: [blob[h["model_off"]:h["model_off"] + h["model_len"]]] + \
        [blob[o:o + n] for o, n in h["inputs"] + h["outputs"]]
    diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    model_a, model_b = sec(a, ha)[0], sec(b, hb)[0]
    checks = dict(
        a_is_stage4_blob=hashlib.sha256(a).hexdigest() == meta["blob_sha256"] == STAGE4["blob_sha256"],
        placements=(ha["placement"], hb["placement"]) == (0, 1),
        only_word_7_differs=len(a) == len(b) and all(4 * drwl.PLACEMENT_WORD <= i < 4 * drwl.PLACEMENT_WORD + 4
                                                     for i in diff) and bool(diff),
        headers_equal_but_placement=all(ha[k] == hb[k] for k in drwl.HEADER_FIELDS if k != "placement")
        and ha["inputs"] == hb["inputs"] and ha["outputs"] == hb["outputs"],
        sections_equal=sec(a, ha) == sec(b, hb),
        cms_sha256=hashlib.sha256(cms).hexdigest() == meta["cms_sha256"],
        cms_once_same_offset=model_a.count(cms) == model_b.count(cms) == 1 and model_a.find(cms) == model_b.find(cms),
        vela_sha256=hashlib.sha256(model_a).hexdigest() == hashlib.sha256(model_b).hexdigest() == meta["vela_sha256"])
    return dict(verdict="PASS" if all(checks.values()) else "FAIL", checks=checks, differing_bytes=diff,
                a_sha256=hashlib.sha256(a).hexdigest(), b_sha256=hashlib.sha256(b).hexdigest(),
                model_sha256=hashlib.sha256(model_a).hexdigest())


# ---------------------------------------------------------------- one condition
def caps_of(folder: pathlib.Path) -> dict:
    for p in (folder / "capabilities.json", folder.parent / "capabilities.json"):
        if p.exists():
            return json.loads(p.read_text())
    return {}


def placement_failures(records: list, placement: int) -> list:
    e, out = EXPECTED[placement], []
    for i, f in enumerate(records):
        want = dict(schema=4, placement=placement, arena_base=e["arena_base"], base1=e["arena_base"],
                    base_size1=BASE_SIZE1, regioncfg_irq=e["regioncfg"], qconfig_irq=QCONFIG)
        out += [f"run {i}: {k} {f.get(k)!r} != {v!r}" for k, v in want.items() if f.get(k) != v]
        if not f.get("valid_flags", 0) & record_v2.REGIONCFG_MATCH:
            out.append(f"run {i}: REGIONCFG_MATCH not set")
    if not records:
        out.append("no measured RUN")
    return out


def condition(folder: pathlib.Path, comp: dict, ref: bytes, placement: int, warmup: int = 1) -> dict:
    runs = stage4.load(folder, warmup)
    raw = json.loads((folder / "raw_runs.json").read_text())[1:]
    flags = {(x["set_id"], x["rep"]): x["valid_flags"] for x in raw}
    recs = [dict(r["record"], valid_flags=flags.get((s, rep), 0))
            for s, rs in sorted(runs.items()) for rep, r in enumerate(rs, start=warmup + 1)]
    oc = stage4.output_check(folder, comp, ref, runs)
    complete = sorted(runs) == [1, 2] and all(len(rs) == 4 for rs in runs.values())
    valid = all(r["valid"] for rs in runs.values() for r in rs)
    crcs = {r["crc"] for rs in runs.values() for r in rs}
    first = raw[0] if raw else {}
    poisoned_run_ok = (first.get("set_id"), first.get("rep")) == (1, 1) and first["record"].get("ofm_mismatch") == 0 \
        and first.get("output_crc32") in crcs
    return dict(runs=runs, records=recs, caps=caps_of(folder), output=oc, poisoned_run_ok=poisoned_run_ok,
                gate_c="PASS" if complete and valid and oc["verdict"] == "PASS_EXACT" else "FAIL",
                placement=placement_failures(recs, placement),
                output_crc32=crcs.pop() if len(crcs) == 1 else None, metrics=stage4.metrics(runs, comp["n_mac"]))


# ---------------------------------------------------------------- rules
def stat(c: dict, pas: int, code: int) -> tuple:
    return stage4.stats(c["runs"].get(pas, []), code)


def tolerance(a: dict, b: dict, pas: int, code: int) -> float:
    (ma, ra), (_, rb) = stat(a, pas, code), stat(b, pas, code)
    return max(FLOOR * ma, ra or 0, rb or 0)


def compare(a: dict, b: dict, pas: int, code: int) -> dict:
    ma, mb = stat(a, pas, code)[0], stat(b, pas, code)[0]
    t = tolerance(a, b, pas, code)
    return dict(a=ma, b=mb, delta=mb - ma, tol=t, outside=abs(mb - ma) > t,
                pct=(mb / ma - 1) * 100 if ma else None)


def same_between(a: dict, b: dict) -> list:
    out = []
    ra, rb = a["records"][:1], b["records"][:1]
    if ra and rb:
        out += [f"record {k}: A {ra[0].get(k)!r} B {rb[0].get(k)!r}" for k in SAME_FIELDS if ra[0].get(k) != rb[0].get(k)]
    out += [f"capabilities {k}: A {a['caps'].get(k)!r} B {b['caps'].get(k)!r}" for k in CAPS_SAME
            if a["caps"].get(k) != b["caps"].get(k) or k not in a["caps"]]
    return out


def p1(a: dict) -> dict:
    why = [f"pass {p} event {c}: {stat(a, p, c)[0]} != {v}" for (p, c), v in STAGE4["exact"].items()
           if stat(a, p, c)[0] != v]
    m, r = stat(a, 1, 35)
    t = max(FLOOR * STAGE4["npu_active"], STAGE4["npu_active_range"], r or 0)
    if m is None or abs(m - STAGE4["npu_active"]) > t:
        why.append(f"NPU_ACTIVE {m} vs Stage 4 {STAGE4['npu_active']} beyond {t}")
    if a["output_crc32"] != STAGE4["output_crc32"]:
        why.append(f"output CRC {a['output_crc32']} != Stage 4 {STAGE4['output_crc32']}")
    return dict(verdict="PASS" if not why else "FAIL", why=why, npu_active=m, npu_active_tol=t)


def traffic(a: dict, b: dict) -> dict:
    per = {c: compare(a, b, 2, c) for c in TRAFFIC_SIGN}
    ok = all(per[c]["outside"] and (per[c]["delta"] > 0) == (s > 0) for c, s in TRAFFIC_SIGN.items())
    return dict(verdict="TRAFFIC_CONSISTENT" if ok else "TRAFFIC_INCONSISTENT", per_event=per)


def cost(a: dict, b: dict) -> dict:
    per = {p: compare(a, b, p, 35) for p in (1, 2)}
    signs = {(x["delta"] > 0) for x in per.values()}
    if all(x["outside"] for x in per.values()) and len(signs) == 1:
        verdict = "B_HIGHER" if signs.pop() else "B_LOWER"
    else:
        verdict = "UNRESOLVED"
    return dict(verdict=verdict, per_pass=per)


def compute(a: dict, b: dict) -> dict:
    per = {}
    for code in (48, 51):
        (ma, ra), (mb, rb) = stat(a, 1, code), stat(b, 1, code)
        per[code] = dict(a=ma, b=mb, delta=mb - ma, tol=max(ra or 0, rb or 0), same=abs(mb - ma) <= max(ra or 0, rb or 0))
    return dict(verdict="COMPUTE_SAME" if all(x["same"] for x in per.values()) else "COMPUTE_CHANGED", per_event=per)


def auxiliary(a: dict, b: dict) -> dict:
    out = {}
    for p, c in AUX:
        x = compare(a, b, p, c)
        out[f"pass{p}_{c}"] = dict(x, verdict="CHANGED" if x["outside"] else "NOT_RESOLVED")
    return out


def verdict(a: dict, b: dict, gb: dict) -> dict:
    stops = []
    if gb["verdict"] != "PASS":
        stops.append("gate B: " + ", ".join(k for k, v in gb["checks"].items() if not v))
    for name, c in (("A", a), ("B", b)):
        if c["gate_c"] != "PASS":
            stops.append(f"gate C {name}: output {c['output']['verdict']}")
        stops += [f"placement {name}: {x}" for x in c["placement"]]
        if not c["poisoned_run_ok"]:
            stops.append(f"poison {name}: the first RUN after the load does not match its golden")
    stops += [f"A/B differ: {x}" for x in same_between(a, b)]
    if a["output_crc32"] is None or a["output_crc32"] != b["output_crc32"]:
        stops.append(f"output CRC A {a['output_crc32']} B {b['output_crc32']}")
    rep, tr = p1(a), traffic(a, b)
    if rep["verdict"] != "PASS":
        stops.append("P1: " + "; ".join(rep["why"]))
    if tr["verdict"] != "TRAFFIC_CONSISTENT":
        stops.append("traffic: " + tr["verdict"])
    res = dict(p1=rep, traffic=tr, stops=stops)
    if stops:
        return dict(res, outcome="NOT_INTERPRETED")
    return dict(res, outcome="INTERPRETED", cost=cost(a, b), compute=compute(a, b), auxiliary=auxiliary(a, b))


def p1_gate(a_dir, comp_dir, stage4_caps) -> dict:
    """P0 + P1 + A's own validity (gate C, placement, poisoned RUN): the condition for running B at all."""
    comp_dir = pathlib.Path(comp_dir)
    comp = json.loads((comp_dir / "s4_conv_base.compile.json").read_text())
    ref = (comp_dir / "s4_conv_base.drwl.tflite_ofm.bin").read_bytes()
    a = condition(pathlib.Path(a_dir), comp, ref, 0)
    s4 = json.loads(pathlib.Path(stage4_caps).read_text())
    why = [f"P0 capabilities {k}: new {a['caps'].get(k)!r} Stage 4 {s4.get(k)!r}" for k in CAPS_SAME
           if k not in s4 or a["caps"].get(k) != s4[k]]
    if a["gate_c"] != "PASS":
        why.append(f"gate C A: output {a['output']['verdict']}")
    why += [f"placement A: {x}" for x in a["placement"]]
    if not a["poisoned_run_ok"]:
        why.append("poison A: the first RUN after the load does not match its golden")
    rep = p1(a)
    why += [f"P1: {x}" for x in rep["why"]]
    return dict(verdict="PASS" if not why else "FAIL", why=why, p1=rep, ta_profile=1,
                metrics={k: v for k, v in a["metrics"].items() if not k.endswith("_range")})


def analyse(a_dir: str, b_dir: str, comp_dir: str, out: str, a_blob: str, b_blob: str, cms: str) -> dict:
    comp_dir, out = pathlib.Path(comp_dir), pathlib.Path(out)
    comp = json.loads((comp_dir / "s4_conv_base.compile.json").read_text())
    meta = json.loads((comp_dir / "s4_conv_base.drwl.json").read_text())
    ref = (comp_dir / "s4_conv_base.drwl.tflite_ofm.bin").read_bytes()
    gb = gate_b(pathlib.Path(a_blob).read_bytes(), pathlib.Path(b_blob).read_bytes(), meta,
                pathlib.Path(cms).read_bytes())
    a = condition(pathlib.Path(a_dir), comp, ref, 0)
    b = condition(pathlib.Path(b_dir), comp, ref, 1)
    res = dict(ta_profile=1, gate_b=gb, **verdict(a, b, gb),
               conditions={n: {k: v for k, v in c.items() if k not in ("runs", "records")} for n, c in (("A", a), ("B", b))})
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage4p_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main(argv: list) -> int:
    cmd, args = argv[0], argv[1:]
    if cmd == "make-b":
        a = pathlib.Path(args[0]).read_bytes()
        b = make_b(a)
        pathlib.Path(args[1]).write_bytes(b)
        print(json.dumps(dict(a_sha256=hashlib.sha256(a).hexdigest(), b_sha256=hashlib.sha256(b).hexdigest())))
        return 0
    if cmd == "gate-b":
        r = gate_b(*(pathlib.Path(p).read_bytes() for p in args[:2]), json.loads(pathlib.Path(args[2]).read_text()),
                   pathlib.Path(args[3]).read_bytes())
        print(json.dumps(r, indent=1))
        return 0 if r["verdict"] == "PASS" else 1
    if cmd == "p1-gate":
        r = p1_gate(*args[:3])
        (pathlib.Path(args[0]) / "p1_gate.json").write_text(json.dumps(r, indent=1, default=str))
        print(json.dumps(r, indent=1, default=str))
        return 0 if r["verdict"] == "PASS" else 1
    if cmd == "analyse":
        print(json.dumps(analyse(*args[:7]), indent=1, default=str))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
