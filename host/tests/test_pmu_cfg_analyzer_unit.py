"""PMU_CFG aggregate analyzer (90-sample campaign) host-side unit tests.

CHARACTERIZATION ONLY. Nothing here is latency, T_npu, a performance baseline,
a Production GO, Gate 7, or MLEK data, and the +514 Q1 identity is not
generalized.

No board, no serial port, no real campaign. Every case below builds a COMPLETE
synthetic 90-sample campaign on disk -- real schema-v8 wire payloads, real
CRCs, real manifest bytes, archived through run_pmu_cfg.build_cfg_record so the
files have exactly the shape the collector writes -- and then either analyses it
or tampers with one specific thing and requires the analyzer to refuse.

The positive campaign is the control: if it did not pass, every negative below
would be passing for the wrong reason, so each negative is built by mutating
that same known-good campaign in exactly one place.

The load-bearing claim of this file is that the analyzer trusts NOTHING inside
the archive. A tampered payload, a recomputed digest over tampered bytes, a
spoofed `derived` verdict, a manifest edited after the fact, a BIN hash that is
merely self-consistent, a reused boot, a duplicated cell, a re-served latch --
all of them are refusals, and none of them depends on the archive being honest
about itself.
"""

import copy
import dataclasses
import hashlib
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import analyze_pmu_cfg as ac
import run_pmu_cfg as rc
import run_pmu_qual as rq
import runner_proto as rp

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  PASS %s" % name)
    else:
        failed += 1
        print("  FAIL %s %s" % (name, detail))


GLOBAL = 1 << rp.PMU_PMCR_CNT_EN_BIT
ARMED = 1 << rp.PMU_PMCNTEN_CYCLE_BIT
LR = 0x3100078C
B_VALUE = 0x11

# The MMIO shape the predeclared contract expects: A is the baseline, B and C
# each add exactly one PMCCNTR_CFG write and its readback.
MMIO = {"A": (58, 8), "B": (59, 9), "C": (59, 9)}
HOOK_MMIO = (16, 1)

# Nine cells in schedule order get nine strictly increasing boot indices. The
# gaps are deliberate: a failed or preflight boot legitimately consumes an
# index, so only the ORDER is contractual.
BOOT_ORDER = [11, 12, 13, 15, 16, 17, 19, 20, 21]

# Per-repeat functional fingerprints: identical across every cell, distinct
# across the ten repeats. This is the freshness contract, not a statistic.
OUTPUT_CRC = {n: 0x0A000000 + n * 0x1111 for n in range(1, 11)}
POISON_CRC = {n: 0x0B000000 + n * 0x2222 for n in range(1, 11)}

# Cycle values: a hard floor plus a per-boot/per-repeat wobble, so the
# descriptive statistics have something to describe. Never a claim about the
# hardware -- these are fixture numbers.
def cycles_for(case, boot, repeat):
    base = {"A": 3200, "B": 3260, "C": 3210}[case]
    return base + (boot % 3) * 4 + (repeat % 5)


HOOK_EVIDENCE = {
    "hook_order_sha256": "ee" * 32,
    "hook_address": 0x0002B000,
    "hook_wrapper_call_address": 0x0002B004,
    "hook_internal_pre_release_cycle_read_address": 0x0002B010,
    "hook_pre_release_pmcr_address": 0x0002B012,
    "hook_pre_release_pmcntenset_address": 0x0002B014,
    "hook_pre_release_pmccntr_cfg_address": 0x0002B016,
    "hook_pre_release_pmovsset_address": 0x0002B018,
    "hook_pmu_disable_address": 0x0002B020,
    "hook_dsb_address": 0x0002B024,
    "hook_pmcr_readback_address": 0x0002B028,
    "hook_internal_post_disable_capture_address": 0x0002B030,
    "hook_snapshot_valid_latch_address": 0x0002B040,
    "hook_return_address": 0x0002B044,
}

# DDR.BIN is the same model payload in all three builds, exactly as the real
# frozen set is; APP and VECTORS differ because each case is a separate link.
DDR_DIGEST = hashlib.sha256(b"cfg-ddr-shared").hexdigest()


def artifacts_for(case):
    return {
        "APP.BIN": hashlib.sha256(b"cfg-app-%s" % case.encode()).hexdigest(),
        "VECTORS.BIN":
            hashlib.sha256(b"cfg-vectors-%s" % case.encode()).hexdigest(),
        "DDR.BIN": DDR_DIGEST,
    }


def manifest_doc(case):
    value = {"A": None, "B": "0x%08X" % B_VALUE, "C": "0x00000000"}[case]
    doc = {
        "schema_version": 8,
        "qualification_mode": "Q1",
        "characterization_only": True,
        "not_a_performance_baseline": True,
        "cfg_case": case,
        "cfg_case_id": rp.PMU_CFG_CASE_IDS[case],
        "cfg_expected_write_count": 0 if case == "A" else 1,
        "cfg_expected_value": value,
        "build_id": "0x%08X" % rp.PMU_CFG_BUILD_IDS[case],
        "expected_return_address": LR,
        "caller_symbol": "test_u85",
        "callsite_disassembly_sha256": "cc" * 32,
        "vendor_source_sha256": "aa" * 32,
        "vendor_object_sha256": "bb" * 32,
        "stop_store_address": LR - 0x10,
        "target_call_address": LR - 4,
        "release_store_address": LR + 8,
        "release_immediate_address": LR + 4,
        "release_immediate_value": 12,
        "object_target_relocation_symbol": "printf",
        "object_target_relocation_type": "R_ARM_THM_CALL",
        "test_cpm": 1,
        "compiler_flags": "-O2 -fno-builtin-printf -DPMU_QUAL_CFG_EXPERIMENT",
        "artifact_sha256": artifacts_for(case),
    }
    doc.update(HOOK_EVIDENCE)
    return doc


MANIFEST_BLOB = {case: json.dumps(manifest_doc(case), indent=2).encode("utf-8")
                 for case in rp.PMU_CFG_CASES}

# The fixture's own frozen reference, standing in for the constants the real
# analyzer ships. The shipped constants are asserted separately below.
FIXTURE_FROZEN = {
    case: {
        "manifest_sha256": hashlib.sha256(MANIFEST_BLOB[case]).hexdigest(),
        "artifact_sha256": artifacts_for(case),
    }
    for case in rp.PMU_CFG_CASES
}


def snap(cfg=0, cyc=0, armed=True, glob=True, stable=1, ovs=0):
    return rp.PmuDiagSnapshot(
        pmcr=GLOBAL if glob else 0,
        pmcntenset=ARMED if armed else 0,
        pmccntr_cfg=cfg,
        cycle_lo=cyc & 0xFFFFFFFF,
        cycle_hi=(cyc >> 32) & 0xFFFF,
        cycle_read_stable=stable,
        cycle_read_retries=0,
        pmovsset=ovs,
    )


def result(case, seq, cycles, output_crc, poison_crc, **over):
    """One fully valid CFG record for the given case."""
    final = 0 if case in ("A", "C") else B_VALUE
    written = 0 if case in ("A", "C") else B_VALUE
    reads, writes = MMIO[case]
    defaults = {f.name: 0 for f in dataclasses.fields(rp.PmuQualResult)}
    defaults.update(
        schema_version=8,
        build_id=rp.PMU_CFG_BUILD_IDS[case],
        diag_case=rp.PMU_CFG_CASE_IDS[case],
        nc_control_id=0,
        run_sequence=seq,
        cfg_write_performed=0 if case == "A" else 1,
        cfg_write_value=written,
        cfg_readback_after_write=written,
        qualification_mode=rp.PMU_QUAL_MODES["Q1"],
        run_rc=0,
        valid_flags=rp.RUN_VALID_REQUIRED_MASK,
        output_crc=output_crc,
        poison_crc=poison_crc,
        power_seam_id=rp.PMU_QUAL_POWER_SEAM_ID,
        power_guard_cycles=rp.PMU_DIAG_POWER_GUARD_CYCLES,
        reset_guard_cycles=rp.PMU_DIAG_RESET_GUARD_CYCLES,
        start_sequence_id=rp.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
        pmcr_after_program=GLOBAL,
        armed_after_program=1,
        program_stable=1,
        program_stability_reads=rp.PMU_DIAG_STABILITY_SAMPLES,
        hook_armed=1,
        hook_arm_consumed=1,
        hook_detected_count=1,
        hook_fired_count=1,
        hook_snapshot_valid=1,
        hook_callsite_lr_observed=LR,
        npu_cmd_after_return=0xC,
        pmu_mmio_read_count_delta=reads,
        pmu_mmio_write_count_delta=writes,
        hook_pmu_mmio_read_count=HOOK_MMIO[0],
        hook_pmu_mmio_write_count=HOOK_MMIO[1],
        golden_window_base=rp.PMU_DIAG_GOLDEN_WINDOW_BASE,
        golden_window_len=rp.PMU_DIAG_GOLDEN_WINDOW_LEN,
        golden_window_crc=rp.GOLDEN_WINDOW_CRC,
        pre=snap(cfg=final, cyc=1000),
        internal_pre_release=snap(cfg=final, cyc=1000 + cycles),
        internal_post_disable=snap(cfg=final, cyc=1000 + cycles + 90, glob=False),
        after_return=snap(cfg=0, cyc=0, armed=False, glob=False),
        trailing_words=0,
    )
    defaults.update(over)
    return rp.PmuQualResult(**defaults)


SCALARS = [f.name for f in dataclasses.fields(rp.PmuQualResult)][
    :rp.PMU_QUAL_BASE_FIELDS + rp.PMU_QUAL_HOOK_FIELDS]
SNAP_FIELDS = [f.name for f in dataclasses.fields(rp.PmuDiagSnapshot)]


def encode(res, corrupt_crc=False):
    body = [getattr(res, name) for name in SCALARS]
    for snapshot in (res.pre, res.internal_pre_release,
                     res.internal_post_disable, res.after_return):
        body += [getattr(snapshot, name) for name in SNAP_FIELDS]
    total = rp.PMU_QUAL_HEADER_WORDS + len(body)
    head = struct.pack("<8I", rp.PMU_QUAL_MAGIC, res.schema_version, total,
                       rp.PMU_QUAL_HEADER_WORDS, res.run_sequence,
                       res.valid_flags, res.run_rc, 0)
    blob = bytearray(head + b"".join(struct.pack("<I", w & 0xFFFFFFFF)
                                     for w in body))
    crc = rp.measurement_payload_crc(bytes(blob), total)
    struct.pack_into("<I", blob, 28, crc ^ 0xFFFFFFFF if corrupt_crc else crc)
    return bytes(blob)


def plan_for(case, round_index, position, boot, root):
    return rc.CampaignPlan(
        case=case, round_index=round_index, position=position,
        host_boot_index=boot,
        bins_dir=os.path.join(root, "bins_%s" % case),
        manifest_path=os.path.join(root, "manifest_%s.json" % case),
        manifest_doc=json.loads(MANIFEST_BLOB[case].decode("utf-8")),
        manifest_blob=MANIFEST_BLOB[case],
        artifact_sha256=artifacts_for(case))


CELLS_IN_ORDER = [(r, p) for r in rc.ROUNDS for p in rc.POSITIONS]


def write_campaign(root, patch=None, extra=None, skip=None):
    """A complete, known-good 90-sample campaign on disk.

    `patch(case, round, position, boot, repeat, doc)` may return a modified
    archive document; `skip` drops one (cell, repeat); `extra` writes an
    additional file. Everything else is identical between the positive control
    and every negative case.
    """
    os.makedirs(root, exist_ok=True)
    written = []
    for index, (round_index, position) in enumerate(CELLS_IN_ORDER):
        case = rc.POSITION_SCHEDULE[round_index][position - 1]
        boot = BOOT_ORDER[index]
        plan = plan_for(case, round_index, position, boot, root)
        cell_dir = os.path.join(root, "cfg_R%dP%d_%s" % (round_index, position,
                                                         case))
        os.makedirs(cell_dir, exist_ok=True)
        for repeat in range(1, rc.REPEATS + 1):
            if skip == ((round_index, position), repeat):
                continue
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat])
            raw = encode(res)
            doc = rc.build_cfg_record(plan, repeat, res, raw, raw)
            if patch is not None:
                doc = patch(case, round_index, position, boot, repeat, doc)
                if doc is None:
                    continue
            path = os.path.join(cell_dir, rc.repeat_filename(plan, repeat))
            with open(path, "w") as handle:
                json.dump(doc, handle, indent=2)
            written.append(path)
    if extra is not None:
        name, doc = extra
        path = os.path.join(root, name)
        with open(path, "w") as handle:
            json.dump(doc, handle, indent=2)
        written.append(path)
    return written


def analyze(root):
    return ac.analyze(root, FIXTURE_FROZEN)


def refuses(name, root, expect=None):
    """The analyzer must refuse -- and, when `expect` is given, refuse FOR THAT
    REASON. A negative test that passes because the fixture happened to break
    something else is worse than no test, so the reason is asserted too."""
    try:
        analyze(root)
    except (SystemExit, rp.ProtocolError) as exc:
        message = str(exc).replace("\n", " ")
        if expect is not None and expect not in message:
            check(name, False, "refused for the WRONG reason: %s" % message[:90])
            return
        check(name, True, message[:56])
        return
    check(name, False, "the analyzer ACCEPTED it")


def campaign_with(tmp, tag, **kw):
    root = os.path.join(tmp, tag)
    write_campaign(root, **kw)
    return root


# ---------------------------------------------------------------------------

print("=== the shipped frozen identity is the one that was attested ===")
check("three cases are frozen",
      sorted(ac.PMU_CFG_FROZEN) == ["A", "B", "C"])
check("case A manifest digest",
      ac.PMU_CFG_FROZEN["A"]["manifest_sha256"]
      == "49da8efc6ae30840b07ca93fa8d4723fae5429f8469daee9d1ae3a044bbafb00")
check("case B manifest digest",
      ac.PMU_CFG_FROZEN["B"]["manifest_sha256"]
      == "5e87cc018d2715acaaf5f4af41e297a7e162dd30232ab98e2873dece5488b082")
check("case C manifest digest",
      ac.PMU_CFG_FROZEN["C"]["manifest_sha256"]
      == "a0a39fa6cdc540100db599815c34b20c8abf83e24876a52597d38b51778715b4")
check("case A APP/VECTORS",
      ac.PMU_CFG_FROZEN["A"]["artifact_sha256"]["APP.BIN"]
      == "b9cbea463617264116f3e80eccb2517cc6322f93643a5d307fc209022234e789"
      and ac.PMU_CFG_FROZEN["A"]["artifact_sha256"]["VECTORS.BIN"]
      == "5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9")
check("case B APP/VECTORS",
      ac.PMU_CFG_FROZEN["B"]["artifact_sha256"]["APP.BIN"]
      == "535809259bf1b2dc4ad521c2e38aba99abf826e1393d2ded210a6daf4a25fe36"
      and ac.PMU_CFG_FROZEN["B"]["artifact_sha256"]["VECTORS.BIN"]
      == "c0cd22e5f88cd2f5de0572f222d8e0e0a658877507e39bdffa4da3b7088fee4f")
check("case C APP/VECTORS",
      ac.PMU_CFG_FROZEN["C"]["artifact_sha256"]["APP.BIN"]
      == "00b24f0d3b8c0dfec9c271ad5e216168b5b1c2c71726d911e8c3709e8a32cdbe"
      and ac.PMU_CFG_FROZEN["C"]["artifact_sha256"]["VECTORS.BIN"]
      == "b498835ad63e18030799699868e0fed8e6c8395d5164181662b1c7535aba88d5")
check("DDR.BIN is the same payload in all three builds",
      len({ac.PMU_CFG_FROZEN[c]["artifact_sha256"]["DDR.BIN"]
           for c in rp.PMU_CFG_CASES}) == 1
      and ac.PMU_CFG_FROZEN["A"]["artifact_sha256"]["DDR.BIN"]
      == "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98")
check("the three cases are distinguishable by their artifacts",
      len({json.dumps(ac.PMU_CFG_FROZEN[c]["artifact_sha256"], sort_keys=True)
           for c in rp.PMU_CFG_CASES}) == 3)
check("every frozen digest is a SHA-256",
      all(rq.HEX64.match(ac.PMU_CFG_FROZEN[c]["manifest_sha256"])
          and all(rq.HEX64.match(v) for v in
                  ac.PMU_CFG_FROZEN[c]["artifact_sha256"].values())
          for c in rp.PMU_CFG_CASES))
check("campaign shape constants", (ac.CELLS, ac.SAMPLES_PER_CELL,
                                   ac.TOTAL_SAMPLES, ac.BOOTS_PER_CASE)
      == (9, 10, 90, 3))

print()
print("=== positive control: a complete honest campaign analyses ===")
with tempfile.TemporaryDirectory() as tmp:
    root = campaign_with(tmp, "good")
    report = analyze(root)
    camp = report["campaign"]
    check("90 samples across 9 cells",
          camp["samples"] == 90 and camp["cells"] == 9
          and camp["repeats_per_cell"] == 10)
    check("nine distinct boots, in schedule order",
          camp["boots"] == sorted(BOOT_ORDER) == BOOT_ORDER)
    check("the balanced schedule is reported as run",
          camp["schedule"] == {"1": ["A", "B", "C"], "2": ["B", "C", "A"],
                               "3": ["C", "A", "B"]})
    check("golden CRC 0x27084C4C verified on every sample",
          camp["golden_window"]["crc"] == "0x27084C4C"
          and camp["golden_window"]["verified_on_every_sample"])
    check("the experimental unit is the boot, n=3 per case",
          camp["experimental_unit"] == "boot"
          and camp["independent_units_per_case"] == 3)
    check("every cell reports its ten cycle values",
          all(len(cell["cycles"]) == 10 for cell in report["cells"].values())
          and len(report["cells"]) == 9)

    for case in rp.PMU_CFG_CASES:
        stats = report["per_case"][case]
        check("case %s pooled n=30 over 3 boots" % case,
              stats["pooled"]["n"] == 30 and len(stats["boots"]) == 3
              and stats["n_independent_units"] == 3)
        check("case %s reports min/max/median/MAD/IQR/CV" % case,
              all(stats["pooled"][k] is not None
                  for k in ("min", "max", "median", "mad", "iqr", "cv")))
        check("case %s reports a per-boot median and within-boot CV" % case,
              all(b["within_boot"]["median"] is not None
                  and b["within_boot"]["cv"] is not None
                  for b in stats["boots"].values()))
        check("case %s reports between-boot spread over 3 units" % case,
              stats["between_boot"]["n"] == 3
              and stats["between_boot"]["range"] is not None)
        check("case %s keeps case/round/boot/run nesting" % case,
              all(len(b["run_values"]) == 10 for b in stats["boots"].values()))

    check("MMIO is within the predeclared contract",
          report["mmio"]["within_contract"]
          and report["mmio"]["violations"] == [])
    check("hook-local MMIO invariance is reported",
          report["mmio"]["hook_local_invariant"]
          and report["mmio"]["hook_local_reads"] == [HOOK_MMIO[0]]
          and report["mmio"]["hook_local_writes"] == [HOOK_MMIO[1]])
    check("B and C totals are equal, and both are A+1/+1",
          report["mmio"]["equal_totals_hold"]
          and report["mmio"]["cross_case"]["B"]["reads_vs_A"] == 1
          and report["mmio"]["cross_case"]["C"]["writes_vs_A"] == 1
          and report["mmio"]["cross_case"]["A"]["reads_vs_A"] == 0)
    check("freshness holds across cells and repeats",
          report["freshness"]["identical_across_all_cells"]
          and report["freshness"]["distinct_across_repeats"]
          and len(report["freshness"]["per_repeat_pair"]) == 10)
    check("the STATUS bracket limitation survives into the report",
          "not observed" in report["status_bracket"]["limitation"]
          and report["status_bracket"]["preserved_from_every_sample"])
    check("no status-at-hook is invented anywhere in the report",
          "status_at_hook" not in json.dumps(report["status_bracket"])
          .replace("npu_status_at_hook field exists", ""))
    check("the report declares its own scope",
          report["campaign"]["semantics"] == "characterization_descriptive_only"
          and report["campaign"]["characterization_only"]
          and report["campaign"]["not_a_performance_baseline"])
    check("the report names what it may not claim",
          "latency" in camp["prohibited_claims"]
          and "T_npu" in camp["prohibited_claims"]
          and "Production GO" in camp["prohibited_claims"]
          and "case equivalence" in camp["prohibited_claims"])
    check("DDR self-test / CPUWAIT are declared to live outside this analyzer",
          "DDR self-test" in camp["outside_this_analyzer"]
          and "CPUWAIT" in camp["outside_this_analyzer"])
    check("the printable report renders without error",
          ac.print_report(report) is None)

print()
print("=== the comparison is INCONCLUSIVE, whatever the data says ===")
with tempfile.TemporaryDirectory() as tmp:
    root = campaign_with(tmp, "good2")
    report = analyze(root)
    comparison = report["comparison"]
    check("verdict is INCONCLUSIVE", comparison["verdict"] == "INCONCLUSIVE")
    check("the reason names the experimental unit and n",
          "boot" in comparison["reason"] and "3" in comparison["reason"])
    check("overlap is not equivalence, separation is not significance",
          "not equivalence" in comparison["interpretation_limits"]
          and "not significance" in comparison["interpretation_limits"])
    check("three pairwise descriptive comparisons are emitted",
          sorted(comparison["pairwise_descriptive"]) == ["A_vs_B", "A_vs_C",
                                                         "B_vs_C"])
    check("no p-value, tolerance or equivalence field is emitted anywhere",
          not [k for k in json.dumps(report).lower().split('"')
               if k in ("p_value", "pvalue", "equivalence_tolerance",
                        "tolerance", "significant", "equivalent")])

    # Identical cycle values in every case must STILL be INCONCLUSIVE. This is
    # the case where a careless analyzer would announce equivalence.
    def flatten(case, r, p, boot, repeat, doc):
        return doc

    root = os.path.join(tmp, "identical")
    saved = cycles_for
    try:
        ac_globals = globals()
        ac_globals["cycles_for"] = lambda case, boot, repeat: 3207
        write_campaign(root)
    finally:
        ac_globals["cycles_for"] = saved
    identical = analyze(root)
    check("three cases with byte-identical numbers are still INCONCLUSIVE",
          identical["comparison"]["verdict"] == "INCONCLUSIVE")
    check("...and the spans do overlap, which is reported as description only",
          identical["comparison"]["pairwise_descriptive"]["A_vs_B"]
          ["boot_median_spans_overlap"])
    check("...and no equivalence claim appears in the report",
          "equivalent" not in json.dumps(identical).lower())

print()
print("=== descriptive statistics are computed, not guessed ===")
d = ac.describe([1, 2, 3, 4, 100])
check("min/max/range", (d["min"], d["max"], d["range"]) == (1, 100, 99))
check("median is robust to the outlier", d["median"] == 3)
check("MAD is the median absolute deviation", d["mad"] == 1)
check("IQR uses inclusive quartiles", d["iqr"] == d["q3"] - d["q1"])
check("CV is stdev over mean",
      abs(d["cv"] - (d["stdev"] / d["mean"])) < 1e-12)
check("distinct values are counted", d["distinct_values"] == 5)
d3 = ac.describe([10, 20, 30])
check("n=3 reports no quartiles rather than inventing them",
      d3["q1"] is None and d3["iqr"] is None and d3["n"] == 3)
check("n=1 reports no stdev or CV",
      ac.describe([7])["stdev"] is None and ac.describe([7])["cv"] is None)
try:
    ac.describe([])
    check("an empty group is refused", False, "accepted")
except SystemExit:
    check("an empty group is refused", True)

print()
print("=== tampering with the archived bytes ===")
with tempfile.TemporaryDirectory() as tmp:
    def flip_payload(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 1, 4):
            blob = bytearray(bytes.fromhex(doc["raw"]["payload_hex"]))
            blob[40] ^= 0xFF
            doc["raw"]["payload_hex"] = blob.hex()
        return doc

    refuses("a tampered payload no longer matches its digest",
            campaign_with(tmp, "t1", patch=flip_payload),
            expect='does not match its recorded payload_sha256')

    def flip_and_rehash(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 2, 5):
            blob = bytearray(bytes.fromhex(doc["raw"]["payload_hex"]))
            blob[40] ^= 0xFF
            doc["raw"]["payload_hex"] = blob.hex()
            doc["raw"]["payload_sha256"] = hashlib.sha256(bytes(blob)).hexdigest()
            doc["raw"]["reread_payload_hex"] = blob.hex()
            doc["raw"]["reread_payload_sha256"] = doc["raw"]["payload_sha256"]
        return doc

    refuses("re-hashing the tampered bytes does not defeat the payload CRC",
            campaign_with(tmp, "t2", patch=flip_and_rehash),
            expect='CRC mismatch')

    def truncate(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 1, 1):
            blob = bytes.fromhex(doc["raw"]["payload_hex"])[:-8]
            doc["raw"]["payload_hex"] = blob.hex()
            doc["raw"]["payload_sha256"] = hashlib.sha256(blob).hexdigest()
            doc["raw"]["reread_payload_hex"] = blob.hex()
            doc["raw"]["reread_payload_sha256"] = doc["raw"]["payload_sha256"]
        return doc

    refuses("a truncated payload is refused by the parser",
            campaign_with(tmp, "t3", patch=truncate))

    def not_hex(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 3, 9):
            doc["raw"]["payload_hex"] = "zz" * 8
        return doc

    refuses("a payload that is not hex fails closed with a verdict",
            campaign_with(tmp, "t4", patch=not_hex))

    def drop_raw(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 3, 2):
            doc["raw"].pop("payload_hex")
        return doc

    refuses("a sample with no archived payload is refused",
            campaign_with(tmp, "t5", patch=drop_raw))

print()
print("=== the two halves of a sample must agree ===")
with tempfile.TemporaryDirectory() as tmp:
    def reread_differs(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 2, 6):
            other = encode(result(case, repeat, 4000, OUTPUT_CRC[repeat],
                                  POISON_CRC[repeat]))
            doc["raw"]["reread_payload_hex"] = other.hex()
            doc["raw"]["reread_payload_sha256"] = hashlib.sha256(other).hexdigest()
        return doc

    refuses("an archived re-read that differs from the COMPLETE payload",
            campaign_with(tmp, "r1", patch=reread_differs),
            expect='the two halves of the sample disagree')

    def reread_unproven(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 3, 3):
            doc["raw"]["reread_matches_run_payload"] = False
        return doc

    refuses("a sample whose re-read was never proven equal",
            campaign_with(tmp, "r2", patch=reread_unproven),
            expect='did not prove the GET re-read')

print()
print("=== the archive cannot mark its own homework ===")
with tempfile.TemporaryDirectory() as tmp:
    def spoof_valid(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 1, 1):
            doc["derived"]["terms"]["run_rc_ok"] = False
        return doc

    refuses("a derived term edited to disagree with the bytes",
            campaign_with(tmp, "v1", patch=spoof_valid),
            expect='does not match the verdict re-derived')

    def spoof_cycles(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 2, 2):
            doc["derived"]["npu_pmu_window_cycles"] = 1
        return doc

    refuses("a cycle value edited in the derived block",
            campaign_with(tmp, "v2", patch=spoof_cycles),
            expect='does not match the verdict re-derived')

    def spoof_invalid_as_valid(case, r, p, boot, repeat, doc):
        """An INVALID sample re-labelled valid: the bytes say run_rc=1, the
        archive claims it passed. This is the archive-spoofing case that
        matters most, because such a file is the only way a broken run could
        reach an aggregate."""
        if (r, p, repeat) == (3, 1, 7):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat], run_rc=1)
            raw = encode(res)
            doc["raw"]["payload_hex"] = raw.hex()
            doc["raw"]["payload_sha256"] = hashlib.sha256(raw).hexdigest()
            doc["raw"]["reread_payload_hex"] = raw.hex()
            doc["raw"]["reread_payload_sha256"] = doc["raw"]["payload_sha256"]
            doc["target"] = rq.target_fields(res)
            # `derived` deliberately left as the VALID verdict from the good run
        return doc

    refuses("an invalid run wearing a valid archived verdict",
            campaign_with(tmp, "v3", patch=spoof_invalid_as_valid),
            expect='does not match the verdict re-derived')

    def honestly_invalid(case, r, p, boot, repeat, doc):
        """The same broken run, archived honestly. Still refused -- an invalid
        sample is evidence, but never an aggregate input."""
        if (r, p, repeat) == (3, 2, 8):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat], run_rc=1)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("an honestly-archived invalid sample never enters the aggregate",
            campaign_with(tmp, "v4", patch=honestly_invalid),
            expect='is INVALID')

    def drop_derived(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 3, 4):
            doc.pop("derived")
        return doc

    refuses("a sample with no derived verdict at all",
            campaign_with(tmp, "v5", patch=drop_derived))

print()
print("=== manifest and BIN identity are bound to the FROZEN reference ===")
with tempfile.TemporaryDirectory() as tmp:
    def edit_manifest_text(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 1, 3):
            doc["host"]["manifest_text"] = doc["host"]["manifest_text"].replace(
                '"test_cpm": 1', '"test_cpm": 0')
        return doc

    refuses("manifest bytes edited without updating their digest",
            campaign_with(tmp, "m1", patch=edit_manifest_text))

    def edit_manifest_and_hash(case, r, p, boot, repeat, doc):
        """Change something NO identity rule inspects, then re-sign the whole
        archive consistently. Nothing inside the file disagrees with anything
        else, so only the externally frozen digest can catch it."""
        if (r, p, repeat) == (1, 2, 3):
            text = doc["host"]["manifest_text"].replace(
                '"compiler_flags": "-O2', '"compiler_flags": "-O1')
            assert text != doc["host"]["manifest_text"]
            doc["host"]["manifest_text"] = text
            doc["host"]["manifest_sha256"] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            doc["manifest"] = json.loads(text)
        return doc

    refuses("a fully self-consistent re-signed manifest is still not frozen",
            campaign_with(tmp, "m2", patch=edit_manifest_and_hash),
            expect="is not the frozen case")

    def parsed_copy_lies(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 1, 5):
            doc["manifest"] = dict(doc["manifest"], cfg_expected_write_count=9)
        return doc

    refuses("the parsed manifest copy disagreeing with the bytes",
            campaign_with(tmp, "m3", patch=parsed_copy_lies),
            expect='disagrees with the manifest bytes')

    def bin_mismatch_vs_manifest(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 2, 5):
            doc["host"]["artifact_sha256"]["APP.BIN"] = "ab" * 32
        return doc

    refuses("a deployed BIN hash that is not the manifest's",
            campaign_with(tmp, "m4", patch=bin_mismatch_vs_manifest),
            expect="is not the manifest's")

    def bin_swapped_case(case, r, p, boot, repeat, doc):
        """Self-consistent, but the artifacts belong to another case. Only the
        external frozen reference can catch this."""
        if case == "A":
            other = artifacts_for("C")
            doc["host"]["artifact_sha256"] = dict(other)
            text = doc["host"]["manifest_text"].replace(
                artifacts_for("A")["APP.BIN"], other["APP.BIN"]).replace(
                artifacts_for("A")["VECTORS.BIN"], other["VECTORS.BIN"])
            doc["host"]["manifest_text"] = text
            doc["host"]["manifest_sha256"] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            doc["manifest"] = json.loads(text)
        return doc

    refuses("a self-consistent archive carrying another case's artifacts",
            campaign_with(tmp, "m5", patch=bin_swapped_case),
            expect="frozen")

    def drop_bin(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 3, 1):
            doc["host"]["artifact_sha256"].pop("DDR.BIN")
        return doc

    refuses("a missing deployed BIN hash",
            campaign_with(tmp, "m6", patch=drop_bin))

print()
print("=== the campaign must be exactly the designed 90 ===")
with tempfile.TemporaryDirectory() as tmp:
    refuses("89 samples is not a campaign",
            campaign_with(tmp, "n1", skip=((2, 2), 5)),
            expect='campaign has 89 samples')

    good = result("A", 1, 3207, OUTPUT_CRC[1], POISON_CRC[1])
    raw = encode(good)
    extra_doc = rc.build_cfg_record(plan_for("A", 1, 1, BOOT_ORDER[0], ""), 1,
                                    good, raw, raw)
    refuses("91 samples is not a campaign either",
            campaign_with(tmp, "n2",
                          extra=("cfg_A_round1_pos1_boot11_repeat01.json",
                                 extra_doc)),
            expect='campaign has 91 samples')

    empty = os.path.join(tmp, "empty")
    os.makedirs(empty, exist_ok=True)
    refuses("an empty results root", empty)
    try:
        analyze(os.path.join(tmp, "nowhere"))
        check("a results root that does not exist is refused", False)
    except SystemExit:
        check("a results root that does not exist is refused", True)

print()
print("=== cells, repeats and sequence numbers ===")
with tempfile.TemporaryDirectory() as tmp:
    def duplicate_repeat(case, r, p, boot, repeat, doc):
        """Repeat 4 replaced by a SECOND, internally consistent repeat 3. Every
        per-sample rule still passes, so only the cell-level coverage rule is
        left to catch the duplicate."""
        if (r, p) == (1, 1) and repeat == 4:
            res = result(case, 3, cycles_for(case, boot, 3), OUTPUT_CRC[3],
                         POISON_CRC[3])
            raw = encode(res)
            return rc.build_cfg_record(plan_for(case, r, p, boot, ""), 3, res,
                                       raw, raw)
        return doc

    refuses("a cell whose repeats do not cover 1..10 exactly once",
            campaign_with(tmp, "c1", patch=duplicate_repeat),
            expect='repeats are')

    def wrong_case_for_cell(case, r, p, boot, repeat, doc):
        """The B cell relabelled as case A, consistently enough that the
        case/case-id agreement rule passes and the SCHEDULE rule is what has
        to catch it."""
        if (r, p) == (1, 2):
            doc["campaign"]["cfg_case"] = "A"
            doc["campaign"]["cfg_case_id"] = rp.PMU_CFG_CASE_IDS["A"]
        return doc

    refuses("a cell holding the wrong case for its schedule slot",
            campaign_with(tmp, "c2", patch=wrong_case_for_cell),
            expect="round 1 position 2 is case B, not A")

    def case_id_contradicts_case(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 3, 6):
            doc["campaign"]["cfg_case_id"] = 9
        return doc

    refuses("a campaign case id that contradicts its own case",
            campaign_with(tmp, "c2b", patch=case_id_contradicts_case),
            expect="contradicts case")

    def sequence_not_repeat(case, r, p, boot, repeat, doc):
        """The bytes say run_sequence=7 but the archive calls it repeat 6."""
        if (r, p, repeat) == (2, 1, 6):
            res = result(case, 7, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat])
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            spoofed = rc.build_cfg_record(plan, repeat, res, raw, raw)
            spoofed["campaign"]["repeat_index"] = repeat
            return spoofed
        return doc

    refuses("run_sequence disagreeing with the repeat index",
            campaign_with(tmp, "c3", patch=sequence_not_repeat),
            expect='run_sequence')

    def repeat_out_of_range(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 1, 2):
            doc["campaign"]["repeat_index"] = 11
        return doc

    refuses("a repeat index outside 1..10",
            campaign_with(tmp, "c4", patch=repeat_out_of_range))

    def wrong_total(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 2, 2):
            doc["campaign"]["repeat_total"] = 30
        return doc

    refuses("a sample claiming a different block size",
            campaign_with(tmp, "c5", patch=wrong_total))

print()
print("=== one fresh boot per cell, nine distinct, in order ===")
with tempfile.TemporaryDirectory() as tmp:
    def reuse_boot(case, r, p, boot, repeat, doc):
        if (r, p) == (2, 1):
            doc["campaign"]["host_boot_index"] = BOOT_ORDER[0]
        return doc

    refuses("two cells sharing one boot",
            campaign_with(tmp, "b1", patch=reuse_boot),
            expect='is claimed by cell')

    def split_cell_across_boots(case, r, p, boot, repeat, doc):
        if (r, p) == (1, 3) and repeat > 5:
            doc["campaign"]["host_boot_index"] = boot + 100
        return doc

    refuses("one cell built from two boots",
            campaign_with(tmp, "b2", patch=split_cell_across_boots),
            expect='spans boots')

    def boot_goes_backwards(case, r, p, boot, repeat, doc):
        if (r, p) == (2, 2):
            doc["campaign"]["host_boot_index"] = 1
        return doc

    refuses("boot indices that do not increase along the schedule",
            campaign_with(tmp, "b3", patch=boot_goes_backwards),
            expect='do not increase along the schedule')

    def boot_not_positive(case, r, p, boot, repeat, doc):
        if (r, p) == (3, 3):
            doc["campaign"]["host_boot_index"] = 0
        return doc

    refuses("a non-positive boot index",
            campaign_with(tmp, "b4", patch=boot_not_positive),
            expect='is not a positive integer')

print()
print("=== a case must be ONE image across its three boots ===")
with tempfile.TemporaryDirectory() as tmp:
    def rebuilt_midway(case, r, p, boot, repeat, doc):
        """Case A's third boot ran a different link: same case, different LR."""
        if case == "A" and (r, p) == (3, 2):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         hook_callsite_lr_observed=LR + 8)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            man = json.loads(MANIFEST_BLOB[case].decode("utf-8"))
            man["expected_return_address"] = LR + 8
            blob = json.dumps(man, indent=2).encode("utf-8")
            plan = dataclasses.replace(plan, manifest_doc=man,
                                       manifest_blob=blob)
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("a case whose callsite moved between its boots",
            campaign_with(tmp, "s1", patch=rebuilt_midway),
            expect='frozen')

print()
print("=== functional freshness: the workload and the poison ===")
with tempfile.TemporaryDirectory() as tmp:
    def crc_differs_across_cells(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 3, 4):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat] ^ 0xFFFF, POISON_CRC[repeat])
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("one cell producing a different output_crc for the same repeat",
            campaign_with(tmp, "f1", patch=crc_differs_across_cells),
            expect='does not produce one (output_crc, poison_crc) pair')

    def latch_reserved(case, r, p, boot, repeat, doc):
        """Repeat 6 re-serves repeat 5's functional fingerprint everywhere."""
        if repeat == 6:
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[5], POISON_CRC[5])
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("a repeat re-serving the previous repeat's output/poison pair",
            campaign_with(tmp, "f2", patch=latch_reserved),
            expect='distinct (output_crc, poison_crc) pairs')

print()
print("=== the predeclared MMIO contract is falsifiable ===")
with tempfile.TemporaryDirectory() as tmp:
    def mmio_varies_within_case(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 1, 5):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         pmu_mmio_read_count_delta=MMIO[case][0] + 3)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("window MMIO counts that vary within one case",
            campaign_with(tmp, "x1", patch=mmio_varies_within_case),
            expect='not constant across its')

    def b_and_c_differ(case, r, p, boot, repeat, doc):
        if case == "C":
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         pmu_mmio_read_count_delta=MMIO["C"][0] + 1,
                         pmu_mmio_write_count_delta=MMIO["C"][1] + 1)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("case C drifting off the contract B still satisfies",
            campaign_with(tmp, "x2", patch=b_and_c_differ),
            expect="predeclared CFG-access contract permits only")

    def extra_access_beyond_cfg(case, r, p, boot, repeat, doc):
        if case in ("B", "C"):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         pmu_mmio_read_count_delta=MMIO[case][0] + 4,
                         pmu_mmio_write_count_delta=MMIO[case][1] + 4)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("a cross-case difference larger than the one CFG access",
            campaign_with(tmp, "x3", patch=extra_access_beyond_cfg),
            expect='predeclared CFG-access contract permits only')

    def hook_moved(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 3, 3):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         hook_pmu_mmio_read_count=HOOK_MMIO[0] + 1)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("hook-local MMIO counts that are not invariant",
            campaign_with(tmp, "x4", patch=hook_moved),
            expect='hook-local MMIO counts vary')

print()
print("=== the golden window and the STATUS bracket ===")
with tempfile.TemporaryDirectory() as tmp:
    def wrong_golden(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 1, 9):
            res = result(case, repeat, cycles_for(case, boot, repeat),
                         OUTPUT_CRC[repeat], POISON_CRC[repeat],
                         golden_window_crc=0xDEADBEEF)
            raw = encode(res)
            plan = plan_for(case, r, p, boot, "")
            return rc.build_cfg_record(plan, repeat, res, raw, raw)
        return doc

    refuses("a sample whose golden window CRC is not 0x27084C4C",
            campaign_with(tmp, "g1", patch=wrong_golden),
            expect='golden window is')

    def invent_status(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 2, 2):
            doc["target"]["npu_status_at_hook"] = "0x00000000"
        return doc

    refuses("a sample that invents a hook-instant STATUS field",
            campaign_with(tmp, "g2", patch=invent_status),
            expect='claims a hook-instant STATUS')

    def invent_status_in_bracket(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 3, 2):
            doc["derived"]["status_bracket"]["status_at_hook"] = 0
        return doc

    refuses("a status-at-hook smuggled into the bracket",
            campaign_with(tmp, "g3", patch=invent_status_in_bracket),
            expect='claims a hook-instant STATUS')

    def scope_limit_dropped(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 1, 1):
            doc["campaign"]["characterization_only"] = False
        return doc

    refuses("a sample that drops its own scope limit",
            campaign_with(tmp, "g4", patch=scope_limit_dropped),
            expect='does not carry its own scope limit')

    def target_edited(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (3, 2, 4):
            doc["target"]["t_call_enter"] += 1
        return doc

    refuses("an edited parsed target block",
            campaign_with(tmp, "g5", patch=target_edited),
            expect='target block does not exactly match')

    def derived_extra_key(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (1, 2, 3):
            doc["derived"]["unattested_extra"] = True
        return doc

    refuses("an archived verdict with an extra un-derived key",
            campaign_with(tmp, "g6", patch=derived_extra_key),
            expect='archived verdict does not match')

    def campaign_metadata_edited(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 1, 8):
            doc["campaign"]["position_schedule"]["1"] = ["C", "B", "A"]
        return doc

    refuses("campaign metadata that contradicts the frozen schedule",
            campaign_with(tmp, "g7", patch=campaign_metadata_edited),
            expect='campaign metadata does not match')

    def structural_mode_edited(case, r, p, boot, repeat, doc):
        if (r, p, repeat) == (2, 3, 9):
            doc["host"]["structural_mode"] = "Q0"
        return doc

    refuses("a host structural mode other than Q1",
            campaign_with(tmp, "g8", patch=structural_mode_edited),
            expect='host structural_mode')

print()
print("=== aggregate report output is append-only ===")
with tempfile.TemporaryDirectory() as tmp:
    report_path = os.path.join(tmp, "campaign_report.json")
    ac.write_json_report(report_path, {"first": True})
    with open(report_path) as handle:
        first_report = json.load(handle)
    check("the first report write succeeds",
          first_report == {"first": True})
    try:
        ac.write_json_report(report_path, {"second": True})
    except ac.CampaignError as exc:
        check("a second report write is refused for overwrite",
              "never overwritten" in str(exc))
    else:
        check("a second report write is refused for overwrite", False,
              "the existing report was replaced")

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
