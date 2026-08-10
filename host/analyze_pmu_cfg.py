"""Re-derive a whole PMU_CFG A/B/C campaign from its 90 archived JSON samples.

CHARACTERIZATION ONLY. Nothing this analyzer prints is latency, T_npu, a
performance number, a performance baseline, a Production GO, Gate 7, or MLEK
data, and the +514 identity observed in the Gate 1 fixed-image Q1 campaign is
NOT generalized to these images. The only measured quantity is
npu_pmu_window_cycles, a PMU cycle-counter window over the vendor call for ONE
case of ONE build.

  python3 analyze_pmu_cfg.py --results-root results/cfg_campaign \
      --json-out results/cfg_campaign/campaign_report.json

WHAT THIS FILE REFUSES TO TRUST
------------------------------
Nothing inside a collected file is taken at its word. For every sample the
archived COMPLETE payload and the archived GET re-read are each proven against
their own digest, proven byte-equal, and RE-PARSED (which re-verifies magic,
schema, declared length and payload CRC); the archived manifest BYTES are
re-hashed and re-parsed and required to agree with the parsed copy stored
beside them; identity is re-checked with run_pmu_cfg's own functions; and the
verdict is RE-DERIVED with classify_pmu_cfg. The `derived` block the collector
wrote is then compared against that re-derivation, and a disagreement is a hard
failure -- an archive cannot mark its own homework, and a file edited to claim
a verdict it does not support must not be able to pass.

Comparing hashes that all live inside the same JSON proves only that the file
is self-consistent, which is exactly what a doctored file also is. Every case
is therefore bound to the FROZEN digests below, which were produced by the ELF
gate before the campaign and are embedded here as constants: the archived
manifest bytes must hash to that case's frozen manifest digest, and the three
deployed BINs must be that case's frozen artifacts.

THE EXPERIMENTAL UNIT IS THE BOOT, n = 3 PER CASE
-------------------------------------------------
Ten repeats on one boot are ten observations of ONE boot, not ten independent
samples: they share a power-up, a DRAM training, a cache state and a thermal
point. The campaign therefore has THREE independent units per case, and three
units cannot support an equivalence claim, a difference claim, a tolerance or a
p-value. This file computes descriptive statistics at both levels, reports the
between-boot spread a reader needs in order to judge the within-boot numbers,
and returns INCONCLUSIVE for every cross-case comparison BY CONSTRUCTION --
there is no data set for which it emits any other comparison verdict. Deciding
that something is equivalent is a human decision made with more boots than
this, and it is not delegated to this script.

WHAT LIVES OUTSIDE THIS FILE
----------------------------
The per-boot DDR self-test result and the CPUWAIT/reset proof are NOT
schema-v8 JSON fields and cannot be re-derived here. They are a
board-procedure gate, captured in the per-boot external logs named by
PMU_CFG_ABC_CONTRACT.md, and a campaign is not complete without them even when
this analyzer passes.
"""

import argparse
import hashlib
import json
import os
import statistics

import run_pmu_cfg as rc
import run_pmu_qual as rq
from runner_proto import (GOLDEN_WINDOW_CRC, PMU_CFG_BUILD_IDS,
                          PMU_CFG_CASE_IDS, PMU_CFG_CASES,
                          PMU_DIAG_GOLDEN_WINDOW_BASE,
                          PMU_DIAG_GOLDEN_WINDOW_LEN, classify_pmu_cfg,
                          parse_pmu_qual_payload)

CELLS = len(rc.ROUNDS) * len(rc.POSITIONS)          # 9
SAMPLES_PER_CELL = rc.REPEATS                       # 10
TOTAL_SAMPLES = CELLS * SAMPLES_PER_CELL            # 90
BOOTS_PER_CASE = CELLS // len(PMU_CFG_CASES)        # 3

# ---------------------------------------------------------------------------
# The FROZEN build identity
#
# Produced by check_pmu_cfg.py in the authoritative container build and frozen
# BEFORE the campaign. Embedded as constants so the reference lives outside the
# evidence it judges: a sample can only pass by matching a digest that was
# already written down. DDR.BIN is deliberately identical across the three
# cases -- it is the same model payload -- while APP.BIN and VECTORS.BIN differ
# because each case is a separate link.
#
# The ELF and .map digests for the three builds belong to this frozen set too
# (see PMU_CFG_ABC_CONTRACT.md); they are not deployed-BIN fields and are not
# checkable from schema-v8 JSON, so they are recorded in the contract rather
# than here.
# ---------------------------------------------------------------------------
_DDR_ALL_CASES = "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98"
PMU_CFG_FROZEN = {
    "A": {
        "manifest_sha256":
            "49da8efc6ae30840b07ca93fa8d4723fae5429f8469daee9d1ae3a044bbafb00",
        "artifact_sha256": {
            "APP.BIN":
                "b9cbea463617264116f3e80eccb2517cc6322f93643a5d307fc209022234e789",
            "VECTORS.BIN":
                "5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9",
            "DDR.BIN": _DDR_ALL_CASES,
        },
    },
    "B": {
        "manifest_sha256":
            "5e87cc018d2715acaaf5f4af41e297a7e162dd30232ab98e2873dece5488b082",
        "artifact_sha256": {
            "APP.BIN":
                "535809259bf1b2dc4ad521c2e38aba99abf826e1393d2ded210a6daf4a25fe36",
            "VECTORS.BIN":
                "c0cd22e5f88cd2f5de0572f222d8e0e0a658877507e39bdffa4da3b7088fee4f",
            "DDR.BIN": _DDR_ALL_CASES,
        },
    },
    "C": {
        "manifest_sha256":
            "a0a39fa6cdc540100db599815c34b20c8abf83e24876a52597d38b51778715b4",
        "artifact_sha256": {
            "APP.BIN":
                "00b24f0d3b8c0dfec9c271ad5e216168b5b1c2c71726d911e8c3709e8a32cdbe",
            "VECTORS.BIN":
                "b498835ad63e18030799699868e0fed8e6c8395d5164181662b1c7535aba88d5",
            "DDR.BIN": _DDR_ALL_CASES,
        },
    },
}

# The scope statements this campaign is allowed to make, and the ones it is
# not. Carried into the emitted report so a JSON that outlives this file still
# says what it is -- and what it is not.
CAMPAIGN_SEMANTICS = "characterization_descriptive_only"
COMPARISON_VERDICT = "INCONCLUSIVE"
PROHIBITED_CLAIMS = (
    "latency",
    "T_npu",
    "performance baseline",
    "Production GO",
    "Gate 7",
    "MLEK data",
    "case equivalence",
    "case difference significance",
)

# ---------------------------------------------------------------------------
# The PREDECLARED MMIO contract
#
# Declared from the case definitions alone, BEFORE any campaign data is read.
# It is not fitted to observations and it is falsifiable: if the board
# disagrees the analyzer says the contract was violated rather than widening
# itself to accommodate what it saw.
#
# Derivation, confirmed against the source by the coordinator: the three images
# are byte-identical apart from the one PMCCNTR_CFG action, so every PMU access
# in the measurement window is common to all three EXCEPT the accesses that
# action performs:
#
#   A  no PMCCNTR_CFG write at all             0 extra writes, 0 extra reads
#   B  one generated write + immediate readback 1 extra write,  1 extra read
#   C  one explicit-zero write + its readback   1 extra write,  1 extra read
#
# So: counts constant within each case, B and C totals EQUAL, and B/C exactly
# one read and one write above A. Any other cross-case difference means the
# images differ somewhere else too, which destroys the single-variable claim
# the whole campaign rests on. The hook is identical in all three images, so
# hook-local counts must be invariant across all 90 samples.
# ---------------------------------------------------------------------------
MMIO_CFG_ACCESS_CONTRACT = {
    "A": {"reads": 0, "writes": 0},
    "B": {"reads": 1, "writes": 1},
    "C": {"reads": 1, "writes": 1},
}
MMIO_CONTRACT_BASELINE_CASE = "A"
MMIO_EQUAL_CASES = ("B", "C")


class CampaignError(SystemExit):
    """Every refusal in this file. A SystemExit so the CLI exits non-zero with
    the reason as its message, and a distinct type so tests can require that a
    refusal came from a contract rather than from an unexpected traceback."""


def fail(message: str) -> "CampaignError":
    return CampaignError("FAIL %s" % message)


# ---------------------------------------------------------------------------
# One sample
# ---------------------------------------------------------------------------

def _hex_payload(path: str, raw_meta: dict, key: str, digest_key: str) -> bytes:
    if key not in raw_meta:
        raise fail("%s: no %s archived -- parsed fields alone are not evidence"
                   % (path, key))
    try:
        blob = bytes.fromhex(raw_meta[key])
    except (TypeError, ValueError) as exc:
        # A hand-edited or truncated archive must fail closed with a verdict,
        # not with a traceback that reads like a tool bug.
        raise fail("%s: %s is not a hex payload: %s" % (path, key, exc))
    if hashlib.sha256(blob).hexdigest() != raw_meta.get(digest_key):
        raise fail("%s: %s does not match its recorded %s"
                   % (path, key, digest_key))
    return blob


def _no_invented_status(path: str, doc: dict) -> None:
    """schema v8 has no status-at-hook field. A sample that claims one is a
    fabrication regardless of how plausible the value looks."""
    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                if "status_at_hook" in key:
                    raise fail(
                        "%s: %s.%s claims a hook-instant STATUS that schema v8 "
                        "does not record -- the bracket is the limitation, not "
                        "a placeholder to fill in" % (path, where, key))
                walk(value, "%s.%s" % (where, key))
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    walk(doc, "root")


def load_sample(path: str, frozen: dict = None) -> dict:
    """Admit one archived repeat, or refuse it.

    Everything is re-derived from the archived bytes. The collector's own
    `derived` block is read ONLY to be compared against the re-derivation.
    `frozen` exists so the synthetic-campaign tests can bind to their own
    fixture identity; production callers never pass it and get the constants
    frozen above.
    """
    frozen = PMU_CFG_FROZEN if frozen is None else frozen
    try:
        with open(path) as handle:
            doc = json.load(handle)
    except OSError as exc:
        raise fail("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise fail("%s is not JSON: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise fail("%s is not a JSON object" % path)

    _no_invented_status(path, doc)

    campaign = doc.get("campaign")
    host = doc.get("host")
    raw_meta = doc.get("raw")
    if not isinstance(campaign, dict) or not isinstance(host, dict) \
            or not isinstance(raw_meta, dict):
        raise fail("%s: missing campaign/host/raw blocks -- this is not a "
                   "run_pmu_cfg.py archive" % path)

    # --- the two halves of the sample, each against its own digest ---
    raw = _hex_payload(path, raw_meta, "payload_hex", "payload_sha256")
    reread = _hex_payload(path, raw_meta, "reread_payload_hex",
                          "reread_payload_sha256")
    if raw != reread:
        raise fail("%s: the archived GET re-read differs from the archived "
                   "COMPLETE payload -- the two halves of the sample disagree"
                   % path)
    if raw_meta.get("reread_matches_run_payload") is not True:
        raise fail("%s: the collector did not prove the GET re-read matched "
                   "the completion payload -- re-collect" % path)

    # Re-parsing re-verifies magic, schema version, declared length and the
    # payload CRC. The stored `target` block is never the source of a field.
    res = parse_pmu_qual_payload(raw)

    # --- the manifest, re-derived from its archived bytes ---
    text = host.get("manifest_text")
    if not isinstance(text, str):
        raise fail("%s: no manifest bytes archived -- the callsite attestation "
                   "cannot be re-derived" % path)
    manifest_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if manifest_sha != host.get("manifest_sha256"):
        raise fail("%s: archived manifest bytes do not match their recorded "
                   "SHA-256" % path)
    try:
        manifest = json.loads(text)
    except ValueError as exc:
        raise fail("%s: archived manifest bytes are not JSON: %s" % (path, exc))
    if doc.get("manifest") != manifest:
        raise fail("%s: the archived manifest document disagrees with the "
                   "manifest bytes it claims to be a parse of" % path)

    # --- the cell this sample says it belongs to ---
    case = campaign.get("cfg_case")
    round_index = campaign.get("round")
    position = campaign.get("position")
    repeat = campaign.get("repeat_index")
    boot = campaign.get("host_boot_index")
    if case not in PMU_CFG_CASES:
        raise fail("%s: campaign cfg_case=%r is not one of %s"
                   % (path, case, ", ".join(PMU_CFG_CASES)))
    if case not in frozen:
        raise fail("%s: case %s has no frozen build identity" % (path, case))
    if campaign.get("cfg_case_id") != PMU_CFG_CASE_IDS[case]:
        raise fail("%s: campaign cfg_case_id=%r contradicts case %s"
                   % (path, campaign.get("cfg_case_id"), case))
    rc.verify_schedule(case, round_index, position)
    if not isinstance(repeat, int) or isinstance(repeat, bool) \
            or not 1 <= repeat <= SAMPLES_PER_CELL:
        raise fail("%s: repeat_index=%r is not in 1..%d"
                   % (path, repeat, SAMPLES_PER_CELL))
    if campaign.get("repeat_total") != SAMPLES_PER_CELL:
        raise fail("%s: repeat_total=%r, expected %d"
                   % (path, campaign.get("repeat_total"), SAMPLES_PER_CELL))
    if not isinstance(boot, int) or isinstance(boot, bool) or boot <= 0:
        raise fail("%s: host_boot_index=%r is not a positive integer -- a boot "
                   "that cannot be named cannot be shown to be distinct"
                   % (path, boot))
    if campaign.get("characterization_only") is not True \
            or campaign.get("not_a_performance_baseline") is not True:
        raise fail("%s: the sample does not carry its own scope limit" % path)
    expected_schedule = {str(r): list(rc.POSITION_SCHEDULE[r])
                         for r in rc.ROUNDS}
    expected_boot_policy = (
        "all %d repeats come from ONE fresh MCU boot; between repeats only the "
        "runner protocol state is reset and re-primed, the MCU is never "
        "rebooted and no power path is touched" % SAMPLES_PER_CELL)
    if campaign.get("experiment") != "pmu_cfg_characterization" \
            or campaign.get("position_schedule") != expected_schedule \
            or campaign.get("boot_policy") != expected_boot_policy:
        raise fail("%s: campaign metadata does not match the frozen CFG "
                   "characterization contract" % path)
    if host.get("structural_mode") != rc.CFG_STRUCTURAL_MODE:
        raise fail("%s: host structural_mode=%r, expected %s"
                   % (path, host.get("structural_mode"), rc.CFG_STRUCTURAL_MODE))

    # --- identity, by the collector's own rules, re-run here ---
    rc.verify_cfg_manifest_identity(manifest, case, path)
    rc.verify_cfg_record_identity(res, rc.CampaignPlan(
        case=case, round_index=round_index, position=position,
        host_boot_index=boot, bins_dir=host.get("bins_dir", ""),
        manifest_path=host.get("manifest_path", ""), manifest_doc=manifest,
        manifest_blob=text.encode("utf-8"),
        artifact_sha256=host.get("artifact_sha256") or {}), repeat)
    # verify_cfg_record_identity already required run_sequence == repeat; this
    # states the campaign-level rule in its own right so a future change to
    # that function cannot silently remove it.
    if res.run_sequence != repeat:
        raise fail("%s: run_sequence=%d but this is repeat %d"
                   % (path, res.run_sequence, repeat))

    # --- bound to the FROZEN identity, not merely to itself ---
    want = frozen[case]
    if manifest_sha != want["manifest_sha256"]:
        raise fail("%s: archived manifest digest %s is not the frozen case %s "
                   "manifest %s -- this sample was collected against a "
                   "manifest nobody froze"
                   % (path, manifest_sha, case, want["manifest_sha256"]))
    deployed = host.get("artifact_sha256") or {}
    attested = manifest.get("artifact_sha256") or {}
    for name in rq.BIN_FILES:
        if not deployed.get(name):
            raise fail("%s: missing deployed %s hash -- deployment provenance "
                       "incomplete" % (path, name))
        if deployed[name] != attested.get(name):
            raise fail("%s: deployed %s %s is not the manifest's %s"
                       % (path, name, deployed[name], attested.get(name)))
        if deployed[name] != want["artifact_sha256"][name]:
            raise fail("%s: deployed %s %s is not the frozen case %s artifact "
                       "%s" % (path, name, deployed[name], case,
                               want["artifact_sha256"][name]))

    # --- the golden window, on every sample ---
    if (res.golden_window_base, res.golden_window_len, res.golden_window_crc) \
            != (PMU_DIAG_GOLDEN_WINDOW_BASE, PMU_DIAG_GOLDEN_WINDOW_LEN,
                GOLDEN_WINDOW_CRC):
        raise fail("%s: golden window is 0x%08X +0x%X CRC 0x%08X, expected "
                   "0x%08X +0x%X CRC 0x%08X -- the inference did not produce "
                   "the attested output"
                   % (path, res.golden_window_base, res.golden_window_len,
                      res.golden_window_crc, PMU_DIAG_GOLDEN_WINDOW_BASE,
                      PMU_DIAG_GOLDEN_WINDOW_LEN, GOLDEN_WINDOW_CRC))

    # --- the verdict, re-derived and then compared with the archived one ---
    derived = classify_pmu_cfg(res, manifest)
    expected_target = rq.target_fields(res)
    if doc.get("target") != expected_target:
        raise fail("%s: the archived target block does not exactly match the "
                   "fields re-derived from the archived payload" % path)
    stored = doc.get("derived")
    if not isinstance(stored, dict):
        raise fail("%s: no derived verdict archived" % path)
    if stored != derived:
        raise fail("%s: the archived verdict does not match the verdict "
                   "re-derived from the archived bytes -- the file has been "
                   "edited or was written by a different classifier" % path)
    if not derived["valid"]:
        raise fail("%s: sample is INVALID (%s) -- an invalid sample is "
                   "evidence and is archived, but it can never enter an "
                   "aggregate" % (path, ", ".join(derived["invalid_reasons"])))
    cycles = derived["npu_pmu_window_cycles"]
    if not isinstance(cycles, int) or cycles <= 0:
        raise fail("%s: a valid sample published npu_pmu_window_cycles=%r"
                   % (path, cycles))

    bracket = derived.get("status_bracket") or {}
    if "limitation" not in bracket:
        raise fail("%s: the STATUS bracket limitation is missing from the "
                   "verdict" % path)

    return {
        "path": path,
        "case": case,
        "round": round_index,
        "position": position,
        "boot": boot,
        "repeat": repeat,
        "run_sequence": res.run_sequence,
        "cycles": cycles,
        "build_id": res.build_id,
        "callsite_lr": res.hook_callsite_lr_observed,
        "manifest_sha256": manifest_sha,
        "artifact_sha256": {n: deployed[n] for n in rq.BIN_FILES},
        "payload_sha256": raw_meta["payload_sha256"],
        "output_crc": res.output_crc,
        "poison_crc": res.poison_crc,
        "mmio_read_delta": res.pmu_mmio_read_count_delta,
        "mmio_write_delta": res.pmu_mmio_write_count_delta,
        "hook_mmio_reads": res.hook_pmu_mmio_read_count,
        "hook_mmio_writes": res.hook_pmu_mmio_write_count,
        "status_bracket": bracket,
        "derived": derived,
    }


# ---------------------------------------------------------------------------
# The campaign
# ---------------------------------------------------------------------------

def discover(results_root: str) -> list:
    """Every archived repeat under the root, in a stable order."""
    if not os.path.isdir(results_root):
        raise fail("results root %s is not a directory" % results_root)
    found = []
    for dirpath, _dirnames, filenames in os.walk(results_root):
        for name in sorted(filenames):
            if name.startswith("cfg_") and "_repeat" in name \
                    and name.endswith(".json"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def _check_schedule_and_boots(cells: dict) -> dict:
    """Cell coverage, one boot per cell, distinct boots, and boot order."""
    expected_cells = {(r, p) for r in rc.ROUNDS for p in rc.POSITIONS}
    if set(cells) != expected_cells:
        missing = sorted(expected_cells - set(cells))
        extra = sorted(set(cells) - expected_cells)
        raise fail("the campaign does not cover the balanced schedule exactly "
                   "-- missing cells %s, unexpected cells %s" % (missing, extra))

    boots = {}
    for (round_index, position), group in sorted(cells.items()):
        want_case = rc.POSITION_SCHEDULE[round_index][position - 1]
        if len(group) != SAMPLES_PER_CELL:
            raise fail("cell R%d P%d has %d samples, expected %d"
                       % (round_index, position, len(group), SAMPLES_PER_CELL))
        if {s["case"] for s in group} != {want_case}:
            raise fail("cell R%d P%d must be case %s, found %s"
                       % (round_index, position, want_case,
                          sorted({s["case"] for s in group})))
        repeats = sorted(s["repeat"] for s in group)
        if repeats != list(range(1, SAMPLES_PER_CELL + 1)):
            raise fail("cell R%d P%d repeats are %s, expected 1..%d exactly "
                       "once each"
                       % (round_index, position, repeats, SAMPLES_PER_CELL))
        if sorted(s["run_sequence"] for s in group) != repeats:
            raise fail("cell R%d P%d run_sequence values do not cover 1..%d"
                       % (round_index, position, SAMPLES_PER_CELL))
        cell_boots = {s["boot"] for s in group}
        if len(cell_boots) != 1:
            raise fail("cell R%d P%d spans boots %s -- ten repeats are ten "
                       "observations of ONE boot, and a cell built from more "
                       "than one boot is not the unit this design measures"
                       % (round_index, position, sorted(cell_boots)))
        boot = cell_boots.pop()
        if boot in boots:
            raise fail("boot %d is claimed by cell R%d P%d and by cell R%d P%d "
                       "-- each cell needs its own fresh boot, so a reused "
                       "index means two cells were not independent"
                       % (boot, boots[boot][0], boots[boot][1], round_index,
                          position))
        boots[boot] = (round_index, position)

    if len(boots) != CELLS:
        raise fail("the campaign used %d distinct boots, expected %d"
                   % (len(boots), CELLS))

    # Chronology: the boot counter only ever goes up, so reading the cells in
    # schedule order must read the boot indices in increasing order too. Gaps
    # are fine (a failed boot, a preflight boot); going backwards is not,
    # because it would mean the cells were not run in the declared order and
    # the balance that separates position from case was never realised.
    ordered = [(r, p) for r in rc.ROUNDS for p in rc.POSITIONS]
    sequence = [next(b for b, cell in boots.items() if cell == c)
                for c in ordered]
    for index in range(1, len(sequence)):
        if sequence[index] <= sequence[index - 1]:
            prev_cell, cur_cell = ordered[index - 1], ordered[index]
            raise fail("boot indices do not increase along the schedule: cell "
                       "R%dP%d used boot %d but the preceding cell R%dP%d used "
                       "boot %d -- the cells were not run in the declared "
                       "order, so position and case are confounded"
                       % (cur_cell[0], cur_cell[1], sequence[index],
                          prev_cell[0], prev_cell[1], sequence[index - 1]))
    return boots


def _check_case_stability(samples: list) -> dict:
    """One image, one manifest, one callsite per case, across its three boots."""
    by_case = {}
    for case in PMU_CFG_CASES:
        group = [s for s in samples if s["case"] == case]
        if len(group) != BOOTS_PER_CASE * SAMPLES_PER_CELL:
            raise fail("case %s has %d samples, expected %d"
                       % (case, len(group), BOOTS_PER_CASE * SAMPLES_PER_CELL))
        for field, label in (("build_id", "build id"),
                             ("callsite_lr", "observed callsite LR"),
                             ("manifest_sha256", "manifest digest")):
            values = {s[field] for s in group}
            if len(values) != 1:
                raise fail("case %s does not hold its %s stable across its %d "
                           "boots: %s" % (case, label, BOOTS_PER_CASE,
                                          sorted(values)))
        artifacts = {json.dumps(s["artifact_sha256"], sort_keys=True)
                     for s in group}
        if len(artifacts) != 1:
            raise fail("case %s deployed more than one artifact set across its "
                       "%d boots -- the image was rebuilt or replaced mid-"
                       "campaign" % (case, BOOTS_PER_CASE))
        if {s["build_id"] for s in group} != {PMU_CFG_BUILD_IDS[case]}:
            raise fail("case %s samples do not carry the case %s build id"
                       % (case, case))
        by_case[case] = group

    fingerprints = {case: json.dumps(by_case[case][0]["artifact_sha256"],
                                     sort_keys=True) for case in PMU_CFG_CASES}
    if len(set(fingerprints.values())) != len(PMU_CFG_CASES):
        raise fail("two cases were collected from the same artifacts -- the "
                   "single variable was not varied")
    return by_case


def _check_freshness(cells: dict) -> dict:
    """The functional/freshness contract on output_crc and poison_crc.

    The workload is fixed and the run-sequence poison is a function of the run
    index, so for a given repeat index every cell must produce the SAME
    (output_crc, poison_crc) pair -- that is what makes the 90 samples nine
    repetitions of one workload rather than nine different ones. Across repeat
    indices the pairs must all DIFFER: identical pairs on consecutive repeats
    would be the signature of a latch re-serving the previous run instead of a
    fresh one.

    This is functional evidence about freshness. It is never a performance
    statistic and never enters the cycle numbers.
    """
    per_repeat = {}
    for cell, group in sorted(cells.items()):
        for sample in group:
            per_repeat.setdefault(sample["repeat"], []).append((cell, sample))

    expected = {}
    for repeat in range(1, SAMPLES_PER_CELL + 1):
        entries = per_repeat.get(repeat, [])
        if len(entries) != CELLS:
            raise fail("repeat %d appears in %d cells, expected %d"
                       % (repeat, len(entries), CELLS))
        pairs = {(s["output_crc"], s["poison_crc"]) for _cell, s in entries}
        if len(pairs) != 1:
            disagreeing = sorted(
                "R%dP%d=(0x%08X,0x%08X)" % (cell[0], cell[1], s["output_crc"],
                                            s["poison_crc"])
                for cell, s in entries)
            raise fail("repeat %d does not produce one (output_crc, "
                       "poison_crc) pair across the %d cells: %s -- the "
                       "workload or the run-sequence poison was not fixed"
                       % (repeat, CELLS, ", ".join(disagreeing)))
        expected[repeat] = pairs.pop()

    if len(set(expected.values())) != SAMPLES_PER_CELL:
        repeated = sorted(r for r in expected
                          if list(expected.values()).count(expected[r]) > 1)
        raise fail("the %d repeat indices do not produce %d distinct "
                   "(output_crc, poison_crc) pairs -- repeats %s share a pair, "
                   "which is what a latch re-serving an earlier run looks like"
                   % (SAMPLES_PER_CELL, SAMPLES_PER_CELL, repeated))

    return {
        "per_repeat_pair": {
            str(r): {"output_crc": "0x%08X" % expected[r][0],
                     "poison_crc": "0x%08X" % expected[r][1]}
            for r in sorted(expected)},
        "identical_across_all_cells": True,
        "distinct_across_repeats": True,
        "evidence_kind": "functional freshness, never a performance statistic",
    }


def build_campaign(samples: list) -> dict:
    """Fold the admitted samples into case/round/boot/run nesting, refusing
    anything the balanced design does not describe."""
    if len(samples) != TOTAL_SAMPLES:
        raise fail("campaign has %d samples, expected exactly %d (%d cells x "
                   "%d repeats) -- a partial or padded campaign is not the "
                   "campaign that was designed"
                   % (len(samples), TOTAL_SAMPLES, CELLS, SAMPLES_PER_CELL))

    cells = {}
    for sample in samples:
        cells.setdefault((sample["round"], sample["position"]), []).append(sample)

    boots = _check_schedule_and_boots(cells)
    by_case = _check_case_stability(samples)
    freshness = _check_freshness(cells)

    return {"cells": cells, "boots": boots, "by_case": by_case,
            "freshness": freshness, "samples": samples}


# ---------------------------------------------------------------------------
# Descriptive statistics (stdlib only)
# ---------------------------------------------------------------------------

def describe(values: list) -> dict:
    """Robust descriptives. No distributional assumption is made anywhere: the
    Q1 campaign showed a hard floor with singleton tail values, which is not a
    shape a mean and a standard deviation describe honestly. Mean, stdev and CV
    are reported because they were asked for, next to the robust numbers that
    should be read first."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise fail("descriptive statistics were asked for an empty group")
    median = statistics.median(ordered)
    mad = statistics.median([abs(v - median) for v in ordered])
    if n >= 4:
        q1, _q2, q3 = statistics.quantiles(ordered, n=4, method="inclusive")
    else:
        # Too few points for quartiles to mean anything; say so rather than
        # emit a number a reader would take at face value.
        q1 = q3 = None
    mean = statistics.fmean(ordered)
    stdev = statistics.stdev(ordered) if n >= 2 else None
    return {
        "n": n,
        "min": ordered[0],
        "max": ordered[-1],
        "range": ordered[-1] - ordered[0],
        "median": median,
        "mad": mad,
        "q1": q1,
        "q3": q3,
        "iqr": None if q1 is None else q3 - q1,
        "mean": mean,
        "stdev": stdev,
        "cv": None if (stdev is None or mean == 0) else stdev / mean,
        "distinct_values": len(set(ordered)),
    }


def case_statistics(group: list) -> dict:
    """Descriptives that PRESERVE the nesting: per run, per boot, and across
    boots -- the last of which is the only level with independent units."""
    per_boot = {}
    for sample in group:
        per_boot.setdefault(sample["boot"], []).append(sample)

    boots = {}
    for boot, samples in sorted(per_boot.items()):
        values = [s["cycles"] for s in sorted(samples, key=lambda s: s["repeat"])]
        boots[boot] = {
            "round": samples[0]["round"],
            "position": samples[0]["position"],
            "run_values": values,
            "within_boot": describe(values),
        }

    boot_medians = [boots[b]["within_boot"]["median"] for b in sorted(boots)]
    return {
        "pooled": describe([s["cycles"] for s in group]),
        "boots": boots,
        "boot_medians": boot_medians,
        # THE experimental-unit level: n = 3.
        "between_boot": describe(boot_medians),
        "experimental_unit": "boot",
        "n_independent_units": len(boot_medians),
        # Pooling 30 runs would understate the spread by treating within-boot
        # repeats as independent; it is reported above only as description.
        "pooled_is_not_n30": (
            "the pooled block describes %d observations of %d boots, not %d "
            "independent samples"
            % (len(group), len(boot_medians), len(group))),
    }


def compare_cases(stats: dict) -> dict:
    """Cross-case comparison. Always INCONCLUSIVE, by construction.

    Three boots per case cannot establish equivalence or difference, and this
    function will not be the place where that gets forgotten: it computes the
    descriptive facts a reader needs -- each case's boot-median span, and
    whether those spans overlap -- and returns INCONCLUSIVE regardless of what
    they show. Overlap is not equivalence and separation is not significance;
    both are observations awaiting more boots.
    """
    spans = {}
    for case in PMU_CFG_CASES:
        medians = stats[case]["boot_medians"]
        spans[case] = {"min": min(medians), "max": max(medians),
                       "medians": list(medians)}

    overlaps = {}
    for index, left in enumerate(PMU_CFG_CASES):
        for right in PMU_CFG_CASES[index + 1:]:
            a, b = spans[left], spans[right]
            separated = a["max"] < b["min"] or b["max"] < a["min"]
            overlaps["%s_vs_%s" % (left, right)] = {
                "boot_median_spans_overlap": not separated,
                "span_gap": (max(b["min"] - a["max"], a["min"] - b["max"])
                             if separated else 0),
            }

    return {
        "verdict": COMPARISON_VERDICT,
        "reason": (
            "the experimental unit is the boot and there are %d per case; %d "
            "units cannot support an equivalence claim, a difference claim, a "
            "tolerance or a p-value, so no comparison verdict other than "
            "INCONCLUSIVE is available from this campaign"
            % (BOOTS_PER_CASE, BOOTS_PER_CASE)),
        "boot_median_spans": spans,
        "pairwise_descriptive": overlaps,
        "interpretation_limits": (
            "overlap is not equivalence; separation is not significance; "
            "neither becomes a claim without more independent boots"),
    }


# ---------------------------------------------------------------------------
# The predeclared MMIO contract, checked
# ---------------------------------------------------------------------------

def mmio_report(campaign: dict) -> dict:
    """Check the predeclared contract and report hook-local invariance."""
    by_case = campaign["by_case"]

    hook_reads = {s["hook_mmio_reads"] for s in campaign["samples"]}
    hook_writes = {s["hook_mmio_writes"] for s in campaign["samples"]}
    hook_invariant = len(hook_reads) == 1 and len(hook_writes) == 1

    per_case = {}
    violations = []
    for case in PMU_CFG_CASES:
        reads = {s["mmio_read_delta"] for s in by_case[case]}
        writes = {s["mmio_write_delta"] for s in by_case[case]}
        per_case[case] = {
            "window_read_delta_values": sorted(reads),
            "window_write_delta_values": sorted(writes),
            "constant_within_case": len(reads) == 1 and len(writes) == 1,
            "hook_read_values": sorted({s["hook_mmio_reads"]
                                        for s in by_case[case]}),
            "hook_write_values": sorted({s["hook_mmio_writes"]
                                         for s in by_case[case]}),
        }
        if not per_case[case]["constant_within_case"]:
            violations.append(
                "case %s window MMIO counts are not constant across its %d "
                "samples (reads %s, writes %s)"
                % (case, len(by_case[case]), sorted(reads), sorted(writes)))

    if not hook_invariant:
        violations.append(
            "hook-local MMIO counts vary across the campaign (reads %s, "
            "writes %s) -- the hook is identical in all three images, so a "
            "variation means the seam itself moved"
            % (sorted(hook_reads), sorted(hook_writes)))

    cross_case = {}
    equal_cases_ok = None
    if not violations:
        base = MMIO_CONTRACT_BASELINE_CASE
        base_reads = per_case[base]["window_read_delta_values"][0]
        base_writes = per_case[base]["window_write_delta_values"][0]
        for case in PMU_CFG_CASES:
            want_reads = (MMIO_CFG_ACCESS_CONTRACT[case]["reads"]
                          - MMIO_CFG_ACCESS_CONTRACT[base]["reads"])
            want_writes = (MMIO_CFG_ACCESS_CONTRACT[case]["writes"]
                           - MMIO_CFG_ACCESS_CONTRACT[base]["writes"])
            got_reads = per_case[case]["window_read_delta_values"][0] - base_reads
            got_writes = (per_case[case]["window_write_delta_values"][0]
                          - base_writes)
            cross_case[case] = {
                "reads_vs_%s" % base: got_reads,
                "writes_vs_%s" % base: got_writes,
                "permitted_reads": want_reads,
                "permitted_writes": want_writes,
                "within_contract": (got_reads == want_reads
                                    and got_writes == want_writes),
            }
            if not cross_case[case]["within_contract"]:
                violations.append(
                    "case %s differs from case %s by %+d reads and %+d writes, "
                    "but the predeclared CFG-access contract permits only %+d "
                    "and %+d -- a difference outside the one varied action "
                    "means the images differ somewhere else too"
                    % (case, base, got_reads, got_writes, want_reads,
                       want_writes))

        # B and C both perform exactly one write plus one readback, so their
        # totals must be equal to each other, not merely each within bounds.
        totals = {case: (per_case[case]["window_read_delta_values"][0],
                         per_case[case]["window_write_delta_values"][0])
                  for case in MMIO_EQUAL_CASES}
        equal_cases_ok = len(set(totals.values())) == 1
        if not equal_cases_ok:
            violations.append(
                "cases %s must have identical window MMIO totals (both perform "
                "one PMCCNTR_CFG write plus one readback) but they are %s"
                % (" and ".join(MMIO_EQUAL_CASES),
                   ", ".join("%s=(reads %d, writes %d)" % (c, t[0], t[1])
                             for c, t in sorted(totals.items()))))

    return {
        "predeclared_contract": MMIO_CFG_ACCESS_CONTRACT,
        "baseline_case": MMIO_CONTRACT_BASELINE_CASE,
        "equal_total_cases": list(MMIO_EQUAL_CASES),
        "equal_totals_hold": equal_cases_ok,
        "per_case": per_case,
        "cross_case": cross_case,
        "hook_local_invariant": hook_invariant,
        "hook_local_reads": sorted(hook_reads),
        "hook_local_writes": sorted(hook_writes),
        "violations": violations,
        "within_contract": not violations,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def analyze(results_root: str, frozen: dict = None) -> dict:
    paths = discover(results_root)
    samples = [load_sample(path, frozen) for path in paths]
    campaign = build_campaign(samples)

    stats = {case: case_statistics(campaign["by_case"][case])
             for case in PMU_CFG_CASES}
    mmio = mmio_report(campaign)
    if not mmio["within_contract"]:
        raise fail("the predeclared MMIO contract was violated:\n  %s"
                   % "\n  ".join(mmio["violations"]))

    limitations = {s["status_bracket"].get("limitation") for s in samples}
    if len(limitations) != 1:
        raise fail("STATUS bracket limitation text is not stable across all "
                   "samples")
    per_sample_brackets = {
        "R%dP%d-repeat%02d" % (s["round"], s["position"], s["repeat"]): {
            "npu_status_after_power_request":
                s["status_bracket"].get("npu_status_after_power_request"),
            "npu_status_after_seam":
                s["status_bracket"].get("npu_status_after_seam"),
        }
        for s in samples
    }
    unique_brackets = sorted({
        (v["npu_status_after_power_request"], v["npu_status_after_seam"])
        for v in per_sample_brackets.values()
    })
    return {
        "campaign": {
            "semantics": CAMPAIGN_SEMANTICS,
            "characterization_only": True,
            "not_a_performance_baseline": True,
            "prohibited_claims": list(PROHIBITED_CLAIMS),
            "results_root": results_root,
            "samples": TOTAL_SAMPLES,
            "cells": CELLS,
            "repeats_per_cell": SAMPLES_PER_CELL,
            "boots": sorted(campaign["boots"]),
            "boot_order_matches_schedule": True,
            "schedule": {str(r): list(rc.POSITION_SCHEDULE[r])
                         for r in rc.ROUNDS},
            "experimental_unit": "boot",
            "independent_units_per_case": BOOTS_PER_CASE,
            "frozen_identity": {
                case: {"build_id": "0x%08X" % PMU_CFG_BUILD_IDS[case],
                       "manifest_sha256":
                           (frozen or PMU_CFG_FROZEN)[case]["manifest_sha256"],
                       "artifact_sha256":
                           dict((frozen or PMU_CFG_FROZEN)[case]
                                ["artifact_sha256"])}
                for case in PMU_CFG_CASES
            },
            "golden_window": {
                "base": "0x%08X" % PMU_DIAG_GOLDEN_WINDOW_BASE,
                "len": "0x%X" % PMU_DIAG_GOLDEN_WINDOW_LEN,
                "crc": "0x%08X" % GOLDEN_WINDOW_CRC,
                "verified_on_every_sample": True,
            },
            "outside_this_analyzer": (
                "the per-boot DDR self-test result and the CPUWAIT/reset proof "
                "are not schema-v8 JSON fields; they are a board-procedure "
                "gate held in the per-boot external logs named by "
                "PMU_CFG_ABC_CONTRACT.md"),
        },
        "cells": {
            "R%dP%d" % (r, p): {
                "case": rc.POSITION_SCHEDULE[r][p - 1],
                "boot": campaign["cells"][(r, p)][0]["boot"],
                "cycles": [s["cycles"] for s in
                           sorted(campaign["cells"][(r, p)],
                                  key=lambda s: s["repeat"])],
            }
            for r in rc.ROUNDS for p in rc.POSITIONS
        },
        "per_case": stats,
        "comparison": compare_cases(stats),
        "mmio": mmio,
        "freshness": campaign["freshness"],
        "status_bracket": {
            "per_sample": per_sample_brackets,
            "unique_brackets": [
                {"npu_status_after_power_request": before,
                 "npu_status_after_seam": after}
                for before, after in unique_brackets
            ],
            "limitation": limitations.pop(),
            "preserved_from_every_sample": True,
        },
    }


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def print_report(report: dict) -> None:
    camp = report["campaign"]
    print("PMU_CFG A/B/C campaign -- CHARACTERIZATION ONLY")
    print("  %d samples, %d cells x %d repeats, boots %s"
          % (camp["samples"], camp["cells"], camp["repeats_per_cell"],
             camp["boots"]))
    print("  schedule R1 %s / R2 %s / R3 %s (boot order matches)"
          % ("-".join(camp["schedule"]["1"]), "-".join(camp["schedule"]["2"]),
             "-".join(camp["schedule"]["3"])))
    print("  golden window %s +%s CRC %s verified on every sample"
          % (camp["golden_window"]["base"], camp["golden_window"]["len"],
             camp["golden_window"]["crc"]))
    for case in PMU_CFG_CASES:
        ident = camp["frozen_identity"][case]
        print("  case %s frozen build %s manifest %s"
              % (case, ident["build_id"], ident["manifest_sha256"][:16]))

    print()
    print("npu_pmu_window_cycles (a PMU counter window, NOT latency/T_npu)")
    for case in PMU_CFG_CASES:
        stats = report["per_case"][case]
        pooled = stats["pooled"]
        between = stats["between_boot"]
        print("  case %s  pooled n=%d min=%s median=%s max=%s mad=%s iqr=%s "
              "cv=%s"
              % (case, pooled["n"], _fmt(pooled["min"]), _fmt(pooled["median"]),
                 _fmt(pooled["max"]), _fmt(pooled["mad"]), _fmt(pooled["iqr"]),
                 _fmt(pooled["cv"])))
        for boot in sorted(stats["boots"]):
            b = stats["boots"][boot]
            print("    boot %-3d R%dP%d median=%s mad=%s cv=%s min=%s max=%s"
                  % (boot, b["round"], b["position"],
                     _fmt(b["within_boot"]["median"]),
                     _fmt(b["within_boot"]["mad"]),
                     _fmt(b["within_boot"]["cv"]),
                     _fmt(b["within_boot"]["min"]),
                     _fmt(b["within_boot"]["max"])))
        print("    between-boot (n=%d, the experimental unit): medians=%s "
              "range=%s mad=%s"
              % (between["n"], stats["boot_medians"], _fmt(between["range"]),
                 _fmt(between["mad"])))

    print()
    mmio = report["mmio"]
    print("MMIO, against the contract predeclared before any data was read")
    for case in PMU_CFG_CASES:
        per = mmio["per_case"][case]
        cross = mmio["cross_case"][case]
        print("  case %s window reads=%s writes=%s | vs %s: %+d reads %+d "
              "writes (permitted %+d/%+d)"
              % (case, per["window_read_delta_values"],
                 per["window_write_delta_values"], mmio["baseline_case"],
                 cross["reads_vs_%s" % mmio["baseline_case"]],
                 cross["writes_vs_%s" % mmio["baseline_case"]],
                 cross["permitted_reads"], cross["permitted_writes"]))
    print("  %s totals equal: %s" % ("=".join(mmio["equal_total_cases"]),
                                     mmio["equal_totals_hold"]))
    print("  hook-local counts invariant across all %d samples: %s "
          "(reads=%s writes=%s)"
          % (camp["samples"], mmio["hook_local_invariant"],
             mmio["hook_local_reads"], mmio["hook_local_writes"]))

    print()
    fresh = report["freshness"]
    print("Functional freshness (never a performance statistic)")
    print("  each repeat index produced ONE (output_crc, poison_crc) pair "
          "across all %d cells: %s" % (camp["cells"],
                                       fresh["identical_across_all_cells"]))
    print("  the %d repeat indices produced %d distinct pairs: %s"
          % (camp["repeats_per_cell"], camp["repeats_per_cell"],
             fresh["distinct_across_repeats"]))

    print()
    comparison = report["comparison"]
    print("Cross-case comparison: %s" % comparison["verdict"])
    print("  %s" % comparison["reason"])
    for pair, data in sorted(comparison["pairwise_descriptive"].items()):
        print("    %s boot-median spans overlap: %s (gap %s)"
              % (pair, data["boot_median_spans_overlap"], data["span_gap"]))
    print("  %s" % comparison["interpretation_limits"])

    print()
    print("STATUS at the hook instant: %s"
          % report["status_bracket"]["limitation"])
    print("  observed bracket pairs across all samples: %s"
          % report["status_bracket"]["unique_brackets"])

    print()
    print("Outside this analyzer: %s" % camp["outside_this_analyzer"])
    print("This campaign is %s. It is not %s."
          % (camp["semantics"], ", not ".join(camp["prohibited_claims"])))


def write_json_report(path: str, report: dict) -> None:
    """Write the aggregate once. A second analysis gets a new path; it never
    replaces the first report that an operator may already have reviewed."""
    try:
        with open(path, "x") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    except FileExistsError:
        raise fail("report path already exists; evidence is never overwritten: "
                   "%s" % path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", required=True,
                    help="directory tree holding the 90 archived repeats")
    ap.add_argument("--json-out", help="write the full report as JSON")
    a = ap.parse_args(argv)

    report = analyze(a.results_root)
    if a.json_out:
        write_json_report(a.json_out, report)
        print("wrote %s" % a.json_out)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
