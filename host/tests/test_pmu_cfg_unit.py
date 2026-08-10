"""PMU_CFG (schema-v8 CFG A/B/C characterization) host-side unit tests.

CHARACTERIZATION ONLY. Nothing here is latency, T_npu, a performance baseline,
a Production GO, Gate 7, or MLEK data, and the +514 Q1 identity is not
generalized.

No board, no serial port. The classifier cases construct records directly as
PmuQualResult objects; the collector cases put those SAME records back on the
wire and drive run_pmu_cfg.py through a scripted fake link, so a payload and a
record can never describe different things in this file.

Three load-bearing groups:

  - the substitution check proves MECHANICALLY that classify_pmu_cfg differs
    from classify_pmu_qual by exactly the declared term set and that every
    inherited term has an identical value for the same record. That is what
    stops the two classifiers silently diverging if the qualification rules
    are ever edited, and a base term that goes MISSING invalidates the sample
    rather than quietly shrinking the contract.

  - the impossible-manifest group proves a manifest cannot redefine what a
    case IS: an "A" that declares a write, a "B" that declares a zero value or
    a "C" that declares a non-zero one is rejected even when the record obeys
    the document exactly.

  - the collector group asserts on what reached DISK: which repeat files exist,
    which do not, and what is inside them. An unattributable record writes
    nothing; an invalid one is archived with a null window and stops the block.
"""

import dataclasses
import hashlib
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

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


def manifest(case="A", **over):
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
    }
    doc.update(over)
    return doc


def result(case="A", **over):
    """A fully valid CFG record for the given case."""
    final = 0 if case in ("A", "C") else B_VALUE
    wrote = 0 if case == "A" else 1
    written = 0 if case == "A" else (0 if case == "C" else B_VALUE)
    defaults = {}
    for f in dataclasses.fields(rp.PmuQualResult):
        defaults[f.name] = 0
    defaults.update(
        schema_version=8,
        build_id=rp.PMU_CFG_BUILD_IDS[case],
        diag_case=rp.PMU_CFG_CASE_IDS[case],
        nc_control_id=0,
        run_sequence=1,
        cfg_write_performed=wrote,
        cfg_write_value=written,
        cfg_readback_after_write=written,
        qualification_mode=rp.PMU_QUAL_MODES["Q1"],
        run_rc=0,
        valid_flags=rp.RUN_VALID_REQUIRED_MASK,
        power_seam_id=rp.PMU_QUAL_POWER_SEAM_ID,
        rehold_guard_cycles=0,
        power_guard_cycles=rp.PMU_DIAG_POWER_GUARD_CYCLES,
        reset_guard_cycles=rp.PMU_DIAG_RESET_GUARD_CYCLES,
        start_sequence_id=rp.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
        npu_cmd_after_power_request=0,
        npu_status_after_power_request=0,
        npu_status_after_seam=0,
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
        npu_cmd_at_hook=0,
        npu_cmd_after_return=0xC,
        pmcr_disable_readback_at_hook=0,
        pmu_mmio_read_count_delta=58,
        pmu_mmio_write_count_delta=8,
        hook_pmu_mmio_read_count=16,
        hook_pmu_mmio_write_count=1,
        golden_window_base=rp.PMU_DIAG_GOLDEN_WINDOW_BASE,
        golden_window_len=rp.PMU_DIAG_GOLDEN_WINDOW_LEN,
        golden_window_crc=rp.GOLDEN_WINDOW_CRC,
        pre=snap(cfg=final, cyc=1000),
        internal_pre_release=snap(cfg=final, cyc=4207),
        internal_post_disable=snap(cfg=final, cyc=4300, glob=False),
        after_return=snap(cfg=0, cyc=0, armed=False, glob=False),
        trailing_words=0,
    )
    defaults.update(over)
    return rp.PmuQualResult(**defaults)


def terms_of(case="A", res_over=None, man_over=None):
    res = result(case, **(res_over or {}))
    man = manifest(case, **(man_over or {}))
    return rp.classify_pmu_cfg(res, man)


print("=== positive: all three cases classify valid ===")
for case in ("A", "B", "C"):
    c = terms_of(case)
    check("case %s valid" % case, c["valid"],
          "reasons=%s" % c["invalid_reasons"])
    check("case %s publishes npu_pmu_window_cycles" % case,
          c["npu_pmu_window_cycles"] == 3207,
          "got %r" % c["npu_pmu_window_cycles"])
    check("case %s labelled characterization only" % case,
          c["characterization_only"] and c["not_a_performance_baseline"])

print()
print("=== the substituted term set is EXACTLY as declared (mechanical) ===")
res = result("A")
man = manifest("A")
qual = rp.classify_pmu_qual(res, man)
cfg = rp.classify_pmu_cfg(res, man)
q_names, c_names = set(qual["terms"]), set(cfg["terms"])
check("removed set is exactly PMU_CFG_SUBSTITUTED_OUT",
      q_names - c_names == set(rp.PMU_CFG_SUBSTITUTED_OUT),
      "got %s" % sorted(q_names - c_names))
check("added set is exactly PMU_CFG_SUBSTITUTED_IN",
      c_names - q_names == set(rp.PMU_CFG_SUBSTITUTED_IN),
      "got %s" % sorted(c_names - q_names))
shared = q_names & c_names
check("every inherited term has an identical value",
      all(qual["terms"][k] == cfg["terms"][k] for k in shared),
      "differing=%s" % [k for k in shared if qual["terms"][k] != cfg["terms"][k]])
check("inherited set is non-trivial", len(shared) >= 30, "shared=%d" % len(shared))

print()
print("=== negatives: every substituted CFG term ===")
neg = [
    ("build_id_matches_case", "A", {"build_id": rp.PMU_QUAL_BUILD_IDS["Q1"]}, None),
    ("diag_case_matches_case", "A", {"diag_case": 2}, None),
    ("cfg_write_count_ok", "A", {"cfg_write_performed": 1}, None),
    ("cfg_write_count_ok", "B", {"cfg_write_performed": 0}, None),
    ("cfg_write_value_ok", "B", {"cfg_write_value": 0x12}, None),
    ("cfg_write_value_ok", "A", {"cfg_write_value": 0x11}, None),
    ("cfg_readback_ok", "B", {"cfg_readback_after_write": 0}, None),
    ("cfg_readback_ok", "C", {"cfg_readback_after_write": 0x11}, None),
    ("cfg_pre_matches_case", "B", {"pre": snap(cfg=0, cyc=1000)}, None),
    ("cfg_internal_matches_case", "B",
     {"internal_pre_release": snap(cfg=0, cyc=4207)}, None),
    ("cfg_pre_matches_case", "C", {"pre": snap(cfg=0x11, cyc=1000)}, None),
]
for term, case, over, man_over in neg:
    c = terms_of(case, over, man_over)
    check("case %s: %s fails and blocks publication" % (case, term),
          (not c["valid"]) and term in c["invalid_reasons"]
          and c["npu_pmu_window_cycles"] is None,
          "reasons=%s" % c["invalid_reasons"])

print()
print("=== negatives: identity and manifest binding ===")
c = terms_of("A", None, {"cfg_case": "B"})
check("manifest case B vs record case A is rejected",
      not c["valid"], "reasons=%s" % c["invalid_reasons"])
c = terms_of("A", {"hook_callsite_lr_observed": LR + 4}, None)
check("observed LR must match this case's own manifest",
      (not c["valid"]) and "hook_callsite_lr_matches_manifest" in c["invalid_reasons"])
c = terms_of("A", None, {"build_id": "0xDEADBEEF"})
check("manifest build id must match the case",
      not c["valid"], "reasons=%s" % c["invalid_reasons"])
c = terms_of("A", None, {"schema_version": 7})
check("manifest schema must be 8",
      (not c["valid"]) and "manifest_schema_matches" in c["invalid_reasons"])
c = terms_of("A", {"nc_control_id": 1}, None)
check("negative-control record is rejected",
      (not c["valid"]) and "is_normal_build" in c["invalid_reasons"])
c = terms_of("B", None, {"cfg_expected_value": "not-hex"})
check("unparsable manifest cfg value fails closed",
      not c["valid"], "reasons=%s" % c["invalid_reasons"])
c = terms_of("A", None, {"cfg_case": "Z"})
check("unknown manifest case fails closed", not c["valid"])

print()
print("=== inherited Q1 rules still bite ===")
for term, over in (("no_overflow", {"pre": snap(cfg=0, cyc=1000, ovs=1 << 31)}),
                   ("hook_fired_once", {"hook_fired_count": 0}),
                   ("golden_window_ok", {"golden_window_crc": 0xDEAD}),
                   ("vendor_release_after_return", {"npu_cmd_after_return": 0}),
                   ("npu_power_held_at_hook", {"npu_cmd_at_hook": 4}),
                   ("run_rc_ok", {"run_rc": 1})):
    c = terms_of("A", over, None)
    check("inherited %s still fails closed" % term,
          (not c["valid"]) and term in c["invalid_reasons"],
          "reasons=%s" % c["invalid_reasons"])

print()
print("=== STATUS bracket archived, no status-at-hook invented ===")
c = terms_of("A")
check("status bracket archived", "status_bracket" in c)
check("bracket carries both surrounding observations",
      "npu_status_after_power_request" in c["status_bracket"]
      and "npu_status_after_seam" in c["status_bracket"])
check("limitation declared", "not observed" in c["status_bracket"]["limitation"])
check("no npu_status_at_hook is claimed",
      not any("status_at_hook" in k for k in c))

print()
print("=== Q0/Q1 qualification behaviour unchanged ===")
q1_man = {"schema_version": 8, "qualification_mode": "Q1",
          "build_id": "0x%08X" % rp.PMU_QUAL_BUILD_IDS["Q1"],
          "expected_return_address": LR}
q1_res = result("A", build_id=rp.PMU_QUAL_BUILD_IDS["Q1"], diag_case=1)
qv = rp.classify_pmu_qual(q1_res, q1_man)
check("a genuine Q1 record still classifies valid", qv["valid"],
      "reasons=%s" % qv["invalid_reasons"])
check("Q1 verdict still exposes 38 terms", len(qv["terms"]) == 38,
      "got %d" % len(qv["terms"]))
cfg_res = result("B")
qv2 = rp.classify_pmu_qual(cfg_res, manifest("B"))
check("a CFG record is NOT accepted by the qualification verdict",
      not qv2["valid"])
check("constants match Makefile.pmu_cfg",
      rp.PMU_CFG_BUILD_IDS == {"A": 0x31414350, "B": 0x31424350,
                               "C": 0x31434350}
      and rp.PMU_CFG_CASE_IDS == {"A": 1, "B": 2, "C": 3})

print()
print("=== a manifest cannot redefine what a case IS ===")
check("the intrinsic write contract is A=0 B=1 C=1",
      rp.PMU_CFG_INTRINSIC_WRITE_COUNT == {"A": 0, "B": 1, "C": 1})

# Each entry is a manifest that is not a possible description of its own case,
# paired with a record that OBEYS that impossible manifest. Before the
# intrinsic contract existed, cfg_expected_write_count could redefine the case
# and these records classified valid.
impossible = [
    ("A declaring one write", "A", {"cfg_expected_write_count": 1},
     {"cfg_write_performed": 1}),
    ("A declaring a written value", "A",
     {"cfg_expected_value": "0x00000011"}, {}),
    ("A declaring a value and a write", "A",
     {"cfg_expected_write_count": 1, "cfg_expected_value": "0x00000011"},
     {"cfg_write_performed": 1, "cfg_write_value": B_VALUE,
      "cfg_readback_after_write": B_VALUE,
      "pre": snap(cfg=B_VALUE, cyc=1000),
      "internal_pre_release": snap(cfg=B_VALUE, cyc=4207)}),
    ("B declaring a zero generated value", "B",
     {"cfg_expected_value": "0x00000000"},
     {"cfg_write_value": 0, "cfg_readback_after_write": 0,
      "pre": snap(cfg=0, cyc=1000),
      "internal_pre_release": snap(cfg=0, cyc=4207)}),
    ("B declaring no write", "B", {"cfg_expected_write_count": 0},
     {"cfg_write_performed": 0}),
    ("B declaring no value at all", "B", {"cfg_expected_value": None}, {}),
    ("C declaring a non-zero value", "C",
     {"cfg_expected_value": "0x00000011"},
     {"cfg_write_value": B_VALUE, "cfg_readback_after_write": B_VALUE,
      "pre": snap(cfg=B_VALUE, cyc=1000),
      "internal_pre_release": snap(cfg=B_VALUE, cyc=4207)}),
    ("C declaring no write", "C", {"cfg_expected_write_count": 0},
     {"cfg_write_performed": 0}),
    ("a case id that is not this case's", "A", {"cfg_case_id": 3}, {}),
]
for name, case, man_over, res_over in impossible:
    c = terms_of(case, res_over, man_over)
    check("%s is rejected even when the record obeys it" % name,
          (not c["valid"])
          and "cfg_manifest_case_coherent" in c["invalid_reasons"]
          and c["npu_pmu_window_cycles"] is None,
          "reasons=%s" % c["invalid_reasons"])

c = terms_of("A", {"cfg_write_performed": 1}, {"cfg_expected_write_count": 1})
check("the write count is judged against the case, not the manifest",
      "cfg_write_count_ok" in c["invalid_reasons"],
      "reasons=%s" % c["invalid_reasons"])
c = terms_of("B", None, {"cfg_expected_write_count": 0})
check("the declared count is archived alongside the intrinsic one",
      c["cfg_expected_write_count"] == 1
      and c["cfg_manifest_declared_write_count"] == 0)
c = terms_of("C")
check("case C's expected written value is an explicit zero",
      c["cfg_expected_write_value"] == 0 and c["cfg_expected_final_value"] == 0)
c = terms_of("B")
check("case B's expected written value comes from its own manifest",
      c["cfg_expected_write_value"] == B_VALUE
      and c["cfg_expected_final_value"] == B_VALUE)
check("pmu_cfg_expected_final_value refuses an incoherent manifest",
      rp.pmu_cfg_expected_final_value(manifest("C", cfg_expected_value="0x11"))
      is None)

print()
print("=== a missing base term fails closed, it is not silently dropped ===")
_real_classify_qual = rp.classify_pmu_qual
for dropped in sorted(rp.PMU_CFG_SUBSTITUTED_OUT):
    def without(res, man, _drop=dropped):
        out = _real_classify_qual(res, man)
        terms = {k: v for k, v in out["terms"].items() if k != _drop}
        return dict(out, terms=terms, valid=all(terms.values()))

    rp.classify_pmu_qual = without
    try:
        c = rp.classify_pmu_cfg(result("A"), manifest("A"))
    finally:
        rp.classify_pmu_qual = _real_classify_qual
    check("base term %s absent invalidates the sample" % dropped,
          (not c["valid"])
          and "substitution_contract_intact" in c["invalid_reasons"]
          and c["substitution_missing_base_terms"] == [dropped]
          and c["npu_pmu_window_cycles"] is None,
          "reasons=%s missing=%s"
          % (c["invalid_reasons"], c["substitution_missing_base_terms"]))
check("with every base term present the contract is intact",
      terms_of("A")["terms"]["substitution_contract_intact"]
      and terms_of("A")["substitution_missing_base_terms"] == [])

# ---------------------------------------------------------------------------
# Collector: run_pmu_cfg.py
#
# No serial port is opened anywhere below. The link is a fake that scripts the
# schema-v8 exchange frame by frame, and every case asserts on what reached
# DISK -- which files exist, which do not, and what is inside them.
# ---------------------------------------------------------------------------

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
check("the fixture carries every hook field the host requires",
      not [k for k in rq.Q1_HOOK_REQUIRED if k not in HOOK_EVIDENCE],
      str([k for k in rq.Q1_HOOK_REQUIRED if k not in HOOK_EVIDENCE]))


def full_manifest(case="A", artifacts=None, **over):
    """A check_pmu_cfg.py manifest slice: the qualification callsite and hook
    attestation plus the case identity the CFG gate adds."""
    doc = manifest(case)
    doc.update({
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
        "artifact_sha256": dict(artifacts or {}),
    })
    doc.update(HOOK_EVIDENCE)
    doc.update(over)
    return doc


def bin_digests(case):
    """What a case's manifest attests about its three artifacts."""
    return {name: hashlib.sha256(
        b"%s|cfg-%s-image" % (name.encode(), case.encode())).hexdigest()
        for name in rq.BIN_FILES}


def write_bins(dirpath, case):
    """The three artifacts actually deployed, with their real hashes."""
    for name in rq.BIN_FILES:
        with open(os.path.join(dirpath, name), "wb") as handle:
            handle.write(b"%s|cfg-%s-image" % (name.encode(), case.encode()))
    return bin_digests(case)


SCALAR_FIELDS = [f.name for f in dataclasses.fields(rp.PmuQualResult)][
    :rp.PMU_QUAL_BASE_FIELDS + rp.PMU_QUAL_HOOK_FIELDS]
SNAP_FIELDS = [f.name for f in dataclasses.fields(rp.PmuDiagSnapshot)]


def encode(res, corrupt_crc=False):
    """A PmuQualResult back onto the wire, so the collector parses real bytes.

    Built from the SAME fixture the classifier cases use, so a payload and a
    record can never describe different things in this file.
    """
    body = [getattr(res, name) for name in SCALAR_FIELDS]
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


def wire(case="A", seq=1, corrupt_crc=False, **over):
    return encode(result(case, run_sequence=seq, **over), corrupt_crc)


def block(case="A", count=rc.REPEATS, **over):
    """The nominal block: `count` payloads numbered 1..count."""
    return [wire(case, seq=n, **over) for n in range(1, count + 1)]


def frame_command(blob):
    _magic, _ver, cmd, _flags, seq, _plen = struct.unpack_from(rp.HEADER, blob)
    return cmd, seq


class FakeCfgLink:
    """Just enough RunnerLink for the schema-v8 exchange and rq.prime().

    It deliberately does NOT provide run_pmu_diag()/get_pmu_diag_result(): if
    the collector ever reached for the v7 transport -- which refuses v8 -- these
    tests would die with an AttributeError instead of quietly passing.
    """

    def __init__(self, payloads, gets=None):
        self.payloads = list(payloads)
        self.gets = None if gets is None else list(gets)
        self._seq = 100
        self.queue = []
        self.late_frames = 0
        self.runs = 0
        self.resets = 0
        self.pings = 0
        self.closed = False
        self.last_payload = None

    # --- lifecycle and the protocol state rq.prime() walks ---
    def ping(self):
        self.pings += 1

    def close(self):
        self.closed = True

    def reset_runner(self):
        self.resets += 1

    def load_model_begin(self, size, crc):
        pass

    def load_model_chunk(self, offset, blob):
        pass

    def load_model_end(self):
        pass

    def load_input(self, blob):
        pass

    # --- framing ---
    def next_sequence(self):
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    def send_raw(self, blob):
        cmd, seq = frame_command(blob)
        if cmd == rp.CMD_RUN_PMU_DIAG:
            if self.runs >= len(self.payloads):
                raise AssertionError(
                    "collector started repeat %d; only %d were scripted"
                    % (self.runs + 1, len(self.payloads)))
            self.last_payload = self.payloads[self.runs]
            self.runs += 1
            self.queue.append(
                rp.Frame(1, rp.CMD_RUN_PMU_DIAG | 0x80, 0, seq, b""))
            self.queue.append(
                rp.Frame(1, rp.CMD_PMU_DIAG_COMPLETE, 0, seq,
                         self.last_payload))
        elif cmd == rp.CMD_GET_PMU_DIAG_RESULT:
            index = self.runs - 1
            payload = (self.gets[index]
                       if self.gets is not None and index < len(self.gets)
                       else self.last_payload)
            self.queue.append(
                rp.Frame(1, rp.CMD_GET_PMU_DIAG_RESULT | 0x80, 0, seq, payload))
        else:
            raise AssertionError("unexpected command 0x%02X" % cmd)

    def read_frame(self, timeout=5.0):
        if not self.queue:
            raise rp.ProtocolError("timed out waiting for a frame")
        return self.queue.pop(0)


def campaign(tmp, case="A", round_index=None, position=None, boot=1,
             payloads=None, gets=None, man=None, bins_case=None, tag="",
             opened=None, out_dir=None):
    """run_pmu_cfg.main() end to end with a fake link instead of a port.

    Every link the run opens is appended to `opened`, which the caller may
    supply so it survives an exception -- a list that is still EMPTY after a
    refusal is what proves the refusal happened before the port was opened.
    """
    if round_index is None:
        round_index = 1
    if position is None:
        position = rc.POSITION_SCHEDULE[round_index].index(case) + 1
    bins_dir = os.path.join(tmp, "bins_%s%s" % (case, tag))
    os.makedirs(bins_dir, exist_ok=True)
    # What the manifest ATTESTS is always this case's build; what is DEPLOYED
    # is bins_case, so the two disagree exactly when a test says they should.
    write_bins(bins_dir, bins_case or case)
    attested = bin_digests(case)
    doc = full_manifest(case, artifacts=attested) if man is None else (
        man(attested) if callable(man) else man)
    man_path = os.path.join(tmp, "manifest_%s%s.json" % (case, tag))
    with open(man_path, "w") as handle:
        json.dump(doc, handle, indent=2)
    if out_dir is None:
        out_dir = os.path.join(tmp, "out_%s_r%d_p%d%s"
                               % (case, round_index, position, tag))

    opened = [] if opened is None else opened

    def opener(port):
        link = FakeCfgLink(block(case) if payloads is None else payloads, gets)
        opened.append(link)
        return link

    code = rc.main(["--case", case, "--round", str(round_index),
                    "--position", str(position),
                    "--host-boot-index", str(boot),
                    "--bins-dir", bins_dir, "--manifest", man_path,
                    "--out-dir", out_dir], open_link=opener)
    return code, out_dir, opened


def archived(out_dir):
    return sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []


def load_repeat(out_dir, name):
    with open(os.path.join(out_dir, name)) as handle:
        return json.load(handle)


def refuses(name, fn):
    """The call must fail. Returns the links the call opened, so a caller can
    prove the port was never touched."""
    try:
        outcome = fn()
    except (SystemExit, rp.ProtocolError, rp.Nack) as exc:
        check(name, True, str(exc)[:56])
        return []
    check(name, False, "accepted: %r" % (outcome,))
    return outcome[2] if isinstance(outcome, tuple) and len(outcome) == 3 else []


print()
print("=== collector: the balanced schedule is enforced ===")
check("R1 is A/B/C, R2 is B/C/A, R3 is C/A/B",
      rc.POSITION_SCHEDULE == {1: ("A", "B", "C"), 2: ("B", "C", "A"),
                               3: ("C", "A", "B")})
check("every case appears once per round",
      all(sorted(row) == ["A", "B", "C"]
          for row in rc.POSITION_SCHEDULE.values()))
check("every case appears once in every position",
      all(sorted(rc.POSITION_SCHEDULE[r][p] for r in (1, 2, 3))
          == ["A", "B", "C"] for p in (0, 1, 2)))
check("the block is 10 repeats", rc.REPEATS == 10)
try:
    for round_index, row in rc.POSITION_SCHEDULE.items():
        for position, case in enumerate(row, start=1):
            rc.verify_schedule(case, round_index, position)
    check("all nine scheduled cells are accepted", True)
except SystemExit as exc:
    check("all nine scheduled cells are accepted", False, str(exc)[:56])
for bad in (("B", 1, 1), ("A", 1, 2), ("C", 2, 3), ("A", 4, 1), ("A", 0, 1),
            ("A", 1, 0), ("A", 1, 4), ("Z", 1, 1)):
    refuses("cell %r is refused" % (bad,),
            lambda bad=bad: rc.verify_schedule(*bad))

print()
print("=== collector: manifest and BIN preflight happen BEFORE the port ===")
with tempfile.TemporaryDirectory() as tmp:
    bad_manifests = [
        ("schema is not 8", {"schema_version": 7}),
        ("mode is not the Q1 structure", {"qualification_mode": "Q0"}),
        ("scope limit not declared", {"characterization_only": False}),
        ("performance-baseline disclaimer missing",
         {"not_a_performance_baseline": None}),
        ("case identity missing", {"cfg_case": None}),
        ("case id missing", {"cfg_case_id": None}),
        ("write count missing", {"cfg_expected_write_count": None}),
        ("build id is another case's",
         {"build_id": "0x%08X" % rp.PMU_CFG_BUILD_IDS["C"]}),
        ("build id is the Q1 qualification image",
         {"build_id": "0x%08X" % rp.PMU_QUAL_BUILD_IDS["Q1"]}),
        ("build id unparseable", {"build_id": "not-hex"}),
        ("case A declares a write", {"cfg_expected_write_count": 1}),
        ("case A declares a value", {"cfg_expected_value": "0x00000011"}),
        ("case id contradicts the case", {"cfg_case_id": 2}),
        ("callsite digest missing", {"callsite_disassembly_sha256": None}),
        ("callsite address is not numeric",
         {"expected_return_address": "0x3100078C"}),
        ("caller symbol is not test_u85", {"caller_symbol": "main"}),
        ("target relocation is not a call",
         {"object_target_relocation_type": "R_ARM_ABS32"}),
        ("not built with TEST_CPM=1", {"test_cpm": 0}),
        ("hook order digest missing", {"hook_order_sha256": None}),
        ("hook address missing", {"hook_return_address": None}),
        ("vendor object digest is not a SHA-256",
         {"vendor_object_sha256": "short"}),
    ]
    for index, (name, over) in enumerate(bad_manifests):
        opened = []
        refuses("manifest rejected: %s" % name,
                lambda over=over, index=index, opened=opened: campaign(
                    tmp, "A", tag="_m%02d" % index, opened=opened,
                    man=lambda d, o=over: full_manifest("A", artifacts=d, **o)))
        check("  ... and the port was never opened", opened == [])

    refuses("manifest file does not exist",
            lambda: rc.preflight("A", 1, 1, 1, tmp,
                                 os.path.join(tmp, "absent.json")))
    refuses("host boot index must be positive",
            lambda: rc.preflight("A", 1, 1, 0, tmp,
                                 os.path.join(tmp, "absent.json")))
    bad_json = os.path.join(tmp, "bad.json")
    with open(bad_json, "w") as handle:
        handle.write("{not json")
    refuses("manifest is not JSON",
            lambda: rc.preflight("A", 1, 1, 1, tmp, bad_json))

    opened = []
    refuses("BIN hashes disagree with the manifest",
            lambda: campaign(tmp, "A", bins_case="C", tag="_binmismatch",
                             opened=opened))
    check("  ... and the port was never opened", opened == [])

    # Positive control for the two checks above: a failure that happens AFTER
    # preflight does open the port, so "opened == []" is a real observation
    # rather than a property of the way these tests are written.
    opened = []
    refuses("a wrong-image record is refused after the port opens",
            lambda: campaign(tmp, "A", tag="_afterport", opened=opened,
                             payloads=[wire("A", seq=1, diag_case=2)]))
    check("  ... and that one DID open the port",
          len(opened) == 1 and opened[0].runs == 1 and opened[0].closed)

    # A manifest whose hashes are real, pointed at a directory that has no
    # BINs in it at all.
    src = os.path.join(tmp, "bins_src")
    os.makedirs(src, exist_ok=True)
    man_path = os.path.join(tmp, "man_missing_bin.json")
    with open(man_path, "w") as handle:
        json.dump(full_manifest("A", artifacts=write_bins(src, "A")), handle)
    empty = os.path.join(tmp, "no_bins")
    os.makedirs(empty, exist_ok=True)
    refuses("a deployed BIN is missing",
            lambda: rc.preflight("A", 1, 1, 1, empty, man_path))
    check("the same manifest passes against the directory it describes",
          rc.preflight("A", 1, 1, 1, src, man_path).artifact_sha256
          == write_bins(src, "A"))
    refuses("manifest carries no artifact hashes at all",
            lambda: rq.verify_local_bins(full_manifest("A"), src))

    nonempty = os.path.join(tmp, "existing_evidence")
    os.makedirs(nonempty)
    with open(os.path.join(nonempty, "repeat01.json"), "w") as handle:
        handle.write("preserve me")
    opened = []
    refuses("a non-empty output directory is refused before UART",
            lambda: campaign(tmp, "A", tag="_existing", opened=opened,
                             out_dir=nonempty))
    check("  ... and existing evidence is untouched",
          open(os.path.join(nonempty, "repeat01.json")).read()
          == "preserve me")
    check("  ... and the port was never opened", opened == [])

print()
print("=== collector: ten valid repeats for every case ===")
with tempfile.TemporaryDirectory() as tmp:
    for round_index, row in rc.POSITION_SCHEDULE.items():
        for position, case in enumerate(row, start=1):
            code, out_dir, opened = campaign(
                tmp, case, round_index=round_index, position=position,
                boot=round_index * 10 + position,
                tag="_r%dp%d" % (round_index, position))
            names = archived(out_dir)
            check("case %s R%d P%d: exit 0" % (case, round_index, position),
                  code == 0, "code=%r" % code)
            check("case %s R%d P%d: exactly 10 repeats archived"
                  % (case, round_index, position), len(names) == 10,
                  str(names))
            check("case %s R%d P%d: named repeat01..repeat10"
                  % (case, round_index, position),
                  [n.split("_")[-1] for n in names]
                  == ["repeat%02d.json" % n for n in range(1, 11)], str(names))
            records = [load_repeat(out_dir, n) for n in names]
            check("case %s R%d P%d: every sample is valid"
                  % (case, round_index, position),
                  all(r["derived"]["valid"] for r in records),
                  str([r["derived"]["invalid_reasons"] for r in records
                       if not r["derived"]["valid"]]))
            check("case %s R%d P%d: run_sequence is exactly 1..10"
                  % (case, round_index, position),
                  [r["target"]["run_sequence"] for r in records]
                  == list(range(1, 11)))
            check("case %s R%d P%d: every sample publishes a window"
                  % (case, round_index, position),
                  all(r["derived"]["npu_pmu_window_cycles"] == 3207
                      for r in records))
            check("case %s R%d P%d: one link, opened once, closed"
                  % (case, round_index, position),
                  len(opened) == 1 and opened[0].pings == 1
                  and opened[0].closed)
            check("case %s R%d P%d: protocol state reset once per repeat"
                  % (case, round_index, position),
                  opened[0].resets == 10 and opened[0].runs == 10)

print()
print("=== collector: what one archived repeat carries ===")
with tempfile.TemporaryDirectory() as tmp:
    code, out_dir, _ = campaign(tmp, "B", round_index=1, position=2, boot=7)
    check("case B round 1 position 2 collected", code == 0)
    rec = load_repeat(out_dir, archived(out_dir)[2])
    camp = rec["campaign"]
    check("campaign names the cell",
          (camp["cfg_case"], camp["cfg_case_id"], camp["round"],
           camp["position"], camp["repeat_index"], camp["repeat_total"],
           camp["host_boot_index"]) == ("B", 2, 1, 2, 3, 10, 7), str(camp))
    check("campaign carries the whole balanced schedule",
          camp["position_schedule"] == {"1": ["A", "B", "C"],
                                        "2": ["B", "C", "A"],
                                        "3": ["C", "A", "B"]})
    check("campaign declares the one-boot policy",
          "ONE fresh MCU boot" in camp["boot_policy"]
          and "never rebooted" in camp["boot_policy"])
    check("campaign declares the scope limit",
          camp["characterization_only"] and camp["not_a_performance_baseline"])

    man_path = rec["host"]["manifest_path"]
    with open(man_path, "rb") as handle:
        blob = handle.read()
    check("the exact manifest bytes are archived",
          rec["host"]["manifest_text"].encode("utf-8") == blob)
    check("the manifest digest is over those bytes",
          rec["host"]["manifest_sha256"] == hashlib.sha256(blob).hexdigest())
    check("the archived manifest re-parses to the parsed copy",
          json.loads(rec["host"]["manifest_text"]) == rec["manifest"])
    check("the deployed BIN hashes are archived",
          sorted(rec["host"]["artifact_sha256"]) == sorted(rq.BIN_FILES)
          and all(len(v) == 64
                  for v in rec["host"]["artifact_sha256"].values()))

    raw = rec["raw"]
    check("both wire payloads are archived with their own digests",
          raw["payload_hex"] == raw["reread_payload_hex"]
          and raw["payload_sha256"]
          == hashlib.sha256(bytes.fromhex(raw["payload_hex"])).hexdigest()
          and raw["reread_payload_sha256"]
          == hashlib.sha256(bytes.fromhex(raw["reread_payload_hex"])).hexdigest()
          and raw["reread_matches_run_payload"])
    check("the archived payload re-parses to the archived target fields",
          rq.target_fields(rp.parse_pmu_qual_payload(
              bytes.fromhex(raw["payload_hex"]))) == rec["target"])
    for field in ("run_sequence", "cfg_write_performed", "cfg_write_value",
                  "cfg_readback_after_write", "hook_callsite_lr_observed",
                  "npu_status_after_power_request", "npu_status_after_seam",
                  "snapshots"):
        check("target carries %s" % field, field in rec["target"])
    check("case B archives its written value",
          rec["target"]["cfg_write_value"] == "0x%08X" % B_VALUE
          and rec["target"]["cfg_write_performed"] == 1)

    derived = rec["derived"]
    check("the verdict is the case-aware one",
          derived["cfg_case"] == "B" and derived["characterization_only"]
          and derived["not_a_performance_baseline"])
    check("the STATUS bracket limitation is archived",
          "not observed" in derived["status_bracket"]["limitation"]
          and "npu_status_after_power_request" in derived["status_bracket"]
          and "npu_status_after_seam" in derived["status_bracket"])
    check("no npu_status_at_hook field is invented",
          not [k for k in rec["target"] if "status_at_hook" in k]
          and not [k for k in derived if "status_at_hook" in k])

print()
print("=== collector: a record that is not attributable writes NO sample ===")
with tempfile.TemporaryDirectory() as tmp:
    unattributable = [
        ("run_sequence does not start at 1", {"payloads": block("A")[2:]}),
        ("the CRC does not cover the payload",
         {"payloads": [wire("A", seq=1, corrupt_crc=True)]}),
        ("the re-read disagrees with the run payload",
         {"payloads": [wire("A", seq=1)], "gets": [wire("A", seq=1, run_rc=1)]}),
        ("the callsite LR is not the attested one",
         {"payloads": [wire("A", seq=1, hook_callsite_lr_observed=LR + 4)]}),
        ("the build id is another case's",
         {"payloads": [wire("A", seq=1,
                            build_id=rp.PMU_CFG_BUILD_IDS["C"])]}),
        ("the build id is the Q1 qualification image",
         {"payloads": [wire("A", seq=1,
                            build_id=rp.PMU_QUAL_BUILD_IDS["Q1"])]}),
        ("the diag case is another case's",
         {"payloads": [wire("A", seq=1, diag_case=3)]}),
        ("the image is a negative control",
         {"payloads": [wire("A", seq=1, nc_control_id=1)]}),
        ("the image is not the Q1 structure",
         {"payloads": [wire("A", seq=1,
                            qualification_mode=rp.PMU_QUAL_MODES["Q0"])]}),
    ]
    for index, (name, kw) in enumerate(unattributable):
        tag = "_bad%02d" % index
        refuses("%s: refused" % name,
                lambda kw=kw, tag=tag: campaign(tmp, "A", tag=tag, **kw))
        out_dir = os.path.join(tmp, "out_A_r1_p1%s" % tag)
        check("  ... and no sample is on disk", archived(out_dir) == [],
              str(archived(out_dir)))

    # A failure mid-block keeps the repeats that WERE attributable, and only
    # those: the gap itself never becomes a file.
    tag = "_gap"
    refuses("a gap at repeat 3 stops the block",
            lambda: campaign(tmp, "A", tag=tag, payloads=[
                wire("A", seq=1), wire("A", seq=2), wire("A", seq=4)]))
    out_dir = os.path.join(tmp, "out_A_r1_p1%s" % tag)
    check("repeats 1 and 2 survive the failure at repeat 3",
          [n.split("_")[-1] for n in archived(out_dir)]
          == ["repeat01.json", "repeat02.json"], str(archived(out_dir)))

    tag = "_dupseq"
    refuses("a repeated run_sequence stops the block",
            lambda: campaign(tmp, "A", tag=tag,
                             payloads=[wire("A", seq=1), wire("A", seq=1)]))
    out_dir = os.path.join(tmp, "out_A_r1_p1%s" % tag)
    check("the second record carrying sequence 1 is never archived",
          [n.split("_")[-1] for n in archived(out_dir)] == ["repeat01.json"],
          str(archived(out_dir)))

print()
print("=== collector: an INVALID sample is archived, then the block stops ===")
with tempfile.TemporaryDirectory() as tmp:
    payloads = block("A")
    payloads[2] = wire("A", seq=3, run_rc=1)
    code, out_dir, opened = campaign(tmp, "A", payloads=payloads, tag="_inv")
    names = archived(out_dir)
    check("the block exits non-zero", code != 0, "code=%r" % code)
    check("the invalid sample and everything before it is archived",
          [n.split("_")[-1] for n in names]
          == ["repeat%02d.json" % n for n in (1, 2, 3)], str(names))
    check("repeat 4 was never started", opened[0].runs == 3)
    bad = load_repeat(out_dir, names[2])
    check("the invalid sample publishes no window",
          bad["derived"]["valid"] is False
          and bad["derived"]["npu_pmu_window_cycles"] is None)
    check("the invalid sample names why",
          "run_rc_ok" in bad["derived"]["invalid_reasons"],
          str(bad["derived"]["invalid_reasons"]))
    check("npu_pmu_window_cycles is archived as JSON null",
          '"npu_pmu_window_cycles": null' in
          open(os.path.join(out_dir, names[2])).read())
    check("the samples before it are untouched and valid",
          all(load_repeat(out_dir, n)["derived"]["valid"] for n in names[:2]))
    check("the link was still closed", opened[0].closed)

    # A case-aware failure the qualification classifier would NOT have caught:
    # the register did not end where this case requires.
    payloads = block("C")
    payloads[0] = wire("C", seq=1, pre=snap(cfg=B_VALUE, cyc=1000))
    code, out_dir, opened = campaign(tmp, "C", round_index=1, position=3,
                                     payloads=payloads, tag="_caseinv")
    names = archived(out_dir)
    check("a case-aware failure stops the block at repeat 1",
          code != 0 and [n.split("_")[-1] for n in names] == ["repeat01.json"],
          str(names))
    bad = load_repeat(out_dir, names[0])
    check("it names the case-aware term",
          "cfg_pre_matches_case" in bad["derived"]["invalid_reasons"]
          and bad["derived"]["npu_pmu_window_cycles"] is None,
          str(bad["derived"]["invalid_reasons"]))

print()
print("=== collector: evidence is never overwritten, boot index is real ===")
with tempfile.TemporaryDirectory() as tmp:
    # A cell that already holds evidence must be refused BEFORE the port opens.
    code, out_dir, _ = campaign(tmp, "A", tag="_first")
    check("the first run of a cell succeeds", code == 0)
    opened = []
    refuses("re-running a cell over its own evidence is refused",
            lambda: campaign(tmp, "A", tag="_first", opened=opened))
    check("  ... and the port was never opened for the re-run", opened == [])
    check("the original ten samples are still on disk",
          len(archived(out_dir)) == 10, str(len(archived(out_dir))))

    # Exclusive creation is the backstop if the directory check is bypassed.
    plan = rc.preflight("A", 1, 1, 1, os.path.join(tmp, "bins_A_first"),
                        os.path.join(tmp, "manifest_A_first.json"))
    # Exclusive creation raises FileExistsError rather than a FAIL verdict;
    # what matters here is that the archived byte stays on disk untouched.
    before = open(os.path.join(out_dir, archived(out_dir)[0])).read()
    try:
        rc.archive_repeat(plan, out_dir, 1,
                          rp.parse_pmu_qual_payload(wire("A", seq=1)),
                          wire("A", seq=1), wire("A", seq=1))
        check("archive_repeat refuses to replace an existing sample", False,
              "accepted")
    except (SystemExit, OSError) as exc:
        check("archive_repeat refuses to replace an existing sample", True,
              type(exc).__name__)
    check("the existing sample was not modified",
          open(os.path.join(out_dir, archived(out_dir)[0])).read() == before)

    for bad in (0, -1, -7):
        opened = []
        refuses("host boot index %d is refused" % bad,
                lambda bad=bad, opened=opened: campaign(
                    tmp, "A", boot=bad, tag="_boot%d" % abs(bad),
                    opened=opened))
        check("  ... and the port was never opened", opened == [])

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
