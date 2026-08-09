"""PMU_QUAL (schema-v8 H-PRINTF qualification) host-side unit tests.

No board required. Covers the schema-v8 payload contract (93 words / 372
bytes, 40-word retained prefix + 13 appended hook words + 4 snapshots), the
strict separation from the schema-v7 parser, and the fail-closed classifier.

Two rules drive almost every case below:

  - the ONLY authoritative state pair is (pre, internal_pre_release). The
    after-return snapshot is expected to be wiped by the vendor release and
    must never invalidate a sample, nor contribute to the delta.
  - a performance value is emitted only when EVERY validity term holds. Q0 is
    a baseline image by construction and can never produce one, so a Q0 record
    parses cleanly and still yields None.
"""

import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import analyze_pmu_qual as aq
import run_pmu_qual as rq
import runner_proto as rp

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


GOLDEN_W = rp.GOLDEN_WINDOW_CRC
GW_BASE = rp.PMU_DIAG_GOLDEN_WINDOW_BASE
GW_LEN = rp.PMU_DIAG_GOLDEN_WINDOW_LEN
ARMED = 1 << rp.PMU_PMCNTEN_CYCLE_BIT
OVF = 1 << rp.PMU_PMOVS_CYCLE_OVF_BIT
GLOBAL = 1 << rp.PMU_PMCR_CNT_EN_BIT

# Normalized (Thumb bit cleared) return addresses. Q0 and Q1 are separate
# links, so their numeric callsites MAY differ -- the real pair currently
# links them at the SAME address (see REAL_CALLSITE below), and these fixtures
# deliberately differ. Neither outcome is a contract: each observed LR is only
# ever compared against its OWN mode manifest, so equality across modes is
# never required and never forbidden.
LR_Q1 = 0x0002ABCC
LR_Q0 = 0x00021234


def manifest(mode="Q1", lr=None, **kw):
    """The machine-readable build manifest slice the host classifier reads.

    build_id is a hex STRING here because that is what check_pmu_qual.py
    emits into JSON; the classifier must accept it without the caller
    pre-converting.
    """
    doc = {
        "schema_version": rp.PMU_QUAL_SCHEMA_VERSION,
        "qualification_mode": mode,
        "build_id": "0x%08X" % rp.PMU_QUAL_BUILD_IDS[mode],
        "expected_return_address": (LR_Q1 if mode == "Q1" else LR_Q0)
        if lr is None else lr,
    }
    doc.update(kw)
    return doc


def snap(pmcr=GLOBAL, cnten=ARMED, cfg=0, cyc=0, stable=1, retries=0, ovs=0):
    """One 8-word snapshot. cfg defaults to 0: schema v8 writes no PMCCNTR_CFG
    at all, so zero is the CONTRACT here, not a defect as it was in v7."""
    return (pmcr, cnten, cfg, cyc & 0xFFFFFFFF, (cyc >> 32) & 0xFFFF,
            stable, retries, ovs)


# The power transition after the vendor release takes the PMU bank with it.
# This is the EXPECTED after-return shape, not a failure.
WIPED = snap(pmcr=0, cnten=0, cfg=0, cyc=0)


def build(mode=1, build_id=None, seq=7, flags=0x1F, rc=0,
          diag_case=1, nc=0,
          cfg_written=0, cfg_value=0, cfg_readback=0,
          # Deliberately NON-golden: the whole-region CRC is corroboration
          # display only, so every passing case doubles as proof it gates
          # nothing in v8 either.
          region_crc=0xA5A50001, output_crc=0x2222,
          sequence_id=rp.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
          power_guard=rp.PMU_DIAG_POWER_GUARD_CYCLES,
          cmd_before=0xC, cmd_after_request=0, status_after_request=0,
          reset_guard=rp.PMU_DIAG_RESET_GUARD_CYCLES,
          pmcr_guard=0x4000, pmcr_program=0x4001, arm_program=1,
          stability_reads=rp.PMU_DIAG_STABILITY_SAMPLES, program_stable=1,
          cmd_after_return=0xC,
          # v8 pins the retained seam slots: there is no seam experiment here.
          seam_id=rp.PMU_QUAL_POWER_SEAM_ID, rehold_performed=0, rehold_guard=0,
          cmd_after_seam=0xC, status_after_seam=0,
          gw_base=GW_BASE, gw_len=GW_LEN, gw_crc=GOLDEN_W,
          hook_armed=1, hook_consumed=1, hook_detected=1, hook_fired=1,
          hook_snapshot_valid=1, hook_lr=None,
          hook_enter=1000, hook_exit=1100, cmd_at_hook=0,
          pmcr_disable_readback=0x4000,
          hook_mmio_reads=6, hook_mmio_writes=1,
          mmio_reads=20, mmio_writes=8,
          pre=None, internal=None, post_disable=None, after_return=None,
          schema=None, total_words=None, declared=None, header_seq=None,
          body_schema=None):
    if build_id is None:
        build_id = rp.PMU_QUAL_BUILD_IDS["Q1" if mode == 1 else "Q0"]
    if hook_lr is None:
        hook_lr = LR_Q1 if mode == 1 else LR_Q0
    schema = rp.PMU_QUAL_SCHEMA_VERSION if schema is None else schema
    pre = pre if pre is not None else snap(cyc=0)
    internal = internal if internal is not None else snap(cyc=1000)
    # Read immediately after the single in-hook disable write.
    post_disable = post_disable if post_disable is not None else snap(pmcr=0, cyc=1000)
    after_return = after_return if after_return is not None else WIPED

    prefix = [
        schema if body_schema is None else body_schema,
        build_id,
        diag_case, nc, seq,
        cfg_written, cfg_value, cfg_readback,
        rc, flags,
        0x1111, output_crc, region_crc,
        1, 100, 200, 300,             # ts_valid, t_enter, t_return, t_disable
        0,                            # pmcr_readback_after_disable
        mmio_reads, mmio_writes,      # whole-window mmio deltas
        sequence_id, power_guard, cmd_before, cmd_after_request,
        status_after_request, reset_guard, pmcr_guard, pmcr_program,
        arm_program, stability_reads, program_stable,
        cmd_after_return,             # v8 meaning of the v7 release slot
        seam_id, rehold_performed, rehold_guard,
        cmd_after_seam, status_after_seam,
        gw_base, gw_len, gw_crc,
    ]
    assert len(prefix) == 40, len(prefix)
    hook = [
        mode, hook_armed, hook_consumed, hook_detected, hook_fired,
        hook_snapshot_valid, hook_lr, hook_enter, hook_exit, cmd_at_hook,
        pmcr_disable_readback, hook_mmio_reads, hook_mmio_writes,
    ]
    assert len(hook) == 13, len(hook)

    body = prefix + hook + list(pre) + list(internal) + list(post_disable) \
        + list(after_return)
    total = total_words if total_words is not None else rp.PMU_QUAL_HEADER_WORDS + len(body)
    head = struct.pack("<8I", rp.PMU_QUAL_MAGIC, schema,
                       total if declared is None else declared,
                       rp.PMU_QUAL_HEADER_WORDS,
                       seq if header_seq is None else header_seq, flags, rc, 0)
    p = bytearray(head + b"".join(struct.pack("<I", w) for w in body))
    struct.pack_into("<I", p, 28,
                     zlib.crc32(bytes(p[16:28]) + bytes(p[32:])) & 0xFFFFFFFF)
    return bytes(p)


def cls(payload, man=None):
    return rp.classify_pmu_qual(rp.parse_pmu_qual_payload(payload),
                                manifest() if man is None else man)


def failed_terms(c):
    return sorted(k for k, v in c["terms"].items() if not v)


print("=== layout constants ===")
check("schema version is 8", rp.PMU_QUAL_SCHEMA_VERSION == 8)
check("modes Q0=0 Q1=1", rp.PMU_QUAL_MODES == {"Q0": 0, "Q1": 1})
check("build ids PQB0/PQH1",
      rp.PMU_QUAL_BUILD_IDS == {"Q0": 0x30425150, "Q1": 0x31485150})
check("header is 8 words", rp.PMU_QUAL_HEADER_WORDS == 8)
check("retained prefix is 40 words", rp.PMU_QUAL_BASE_FIELDS == 40)
check("appended hook block is 13 words", rp.PMU_QUAL_HOOK_FIELDS == 13)
check("four 8-word snapshots",
      rp.PMU_QUAL_SNAPSHOT_COUNT == 4 and rp.PMU_QUAL_SNAPSHOT_WORDS == 8)
check("known fields = 85", rp.PMU_QUAL_KNOWN_FIELDS == 85)
check("total = 93 words", rp.PMU_QUAL_TOTAL_WORDS == 93)
check("payload = 372 bytes", rp.PMU_QUAL_PAYLOAD_SIZE == 372)
check("retained seam id is 4", rp.PMU_QUAL_POWER_SEAM_ID == 4)

print("=== integrity ===")
p = build()
check("payload size is exactly 372 bytes", len(p) == 372, "%d bytes" % len(p))
r = rp.parse_pmu_qual_payload(p)
check("parses", r.schema_version == 8 and r.run_sequence == 7)
check("mode decoded", r.qualification_mode == rp.PMU_QUAL_MODES["Q1"])
check("build id decoded", r.build_id == rp.PMU_QUAL_BUILD_IDS["Q1"])
check("hook words decoded in order",
      (r.hook_armed, r.hook_arm_consumed, r.hook_detected_count,
       r.hook_fired_count, r.hook_snapshot_valid, r.hook_callsite_lr_observed,
       r.hook_entry_timestamp, r.hook_exit_timestamp, r.npu_cmd_at_hook,
       r.pmcr_disable_readback_at_hook, r.hook_pmu_mmio_read_count,
       r.hook_pmu_mmio_write_count)
      == (1, 1, 1, 1, 1, LR_Q1, 1000, 1100, 0, 0x4000, 6, 1))
check("four snapshots decoded in order",
      (r.pre.cycle48, r.internal_pre_release.cycle48,
       r.internal_post_disable.cycle48, r.after_return.cycle48)
      == (0, 1000, 1000, 0))
check("npu_cmd_after_return reuses the release prefix slot",
      r.npu_cmd_after_return == 0xC)
check("retained seam slots pinned",
      (r.power_seam_id, r.power_rehold_performed, r.rehold_guard_cycles)
      == (4, 0, 0))
check("no trailing words on the exact payload", r.trailing_words == 0)

for name, bad in [
    ("bad magic rejected", struct.pack("<I", 0xDEADBEEF) + p[4:]),
    ("schema 7 rejected by the v8 parser", p[:4] + struct.pack("<I", 7) + p[8:]),
    ("schema 9 rejected by the v8 parser", p[:4] + struct.pack("<I", 9) + p[8:]),
]:
    try:
        rp.parse_pmu_qual_payload(bytes(bad))
        check(name, False)
    except rp.ProtocolError:
        check(name, True)

try:
    rp.parse_pmu_qual_payload(p[:-4])
    check("truncated payload rejected", False)
except rp.ProtocolError:
    check("truncated payload rejected", True)

try:
    rp.parse_pmu_qual_payload(build(declared=rp.PMU_QUAL_TOTAL_WORDS + 5))
    check("declared/actual length mismatch rejected", False)
except rp.ProtocolError:
    check("declared/actual length mismatch rejected", True)

short = list(struct.unpack("<93I", build()))[:-1]
short[2] -= 1
s = bytearray(b"".join(struct.pack("<I", w) for w in short))
struct.pack_into("<I", s, 28,
                 zlib.crc32(bytes(s[16:28]) + bytes(s[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_qual_payload(bytes(s))
    check("a self-consistent 92-word payload is still rejected", False)
except rp.ProtocolError:
    check("a self-consistent 92-word payload is still rejected", True)

corrupt = bytearray(build())
corrupt[40] ^= 0xFF
try:
    rp.parse_pmu_qual_payload(bytes(corrupt))
    check("payload CRC corruption rejected", False)
except rp.ProtocolError:
    check("payload CRC corruption rejected", True)

try:
    rp.parse_pmu_qual_payload(build(header_seq=99))
    check("header/body seq disagreement rejected", False)
except rp.ProtocolError:
    check("header/body seq disagreement rejected", True)

try:
    rp.parse_pmu_qual_payload(build(body_schema=7))
    check("body/header schema disagreement rejected", False)
except rp.ProtocolError:
    check("body/header schema disagreement rejected", True)

# Forward compatibility: unknown trailing words are counted and skipped.
extra = list(struct.unpack("<93I", build()))
extra[2] += 2
extra += [0xAAAA, 0xBBBB]
q = bytearray(b"".join(struct.pack("<I", w) for w in extra))
struct.pack_into("<I", q, 28,
                 zlib.crc32(bytes(q[16:28]) + bytes(q[32:])) & 0xFFFFFFFF)
check("trailing words tolerated and counted",
      rp.parse_pmu_qual_payload(bytes(q)).trailing_words == 2)

print("=== v7 / v8 parser isolation ===")
try:
    rp.parse_pmu_diag_payload(build())
    check("v7 parser refuses a v8 payload", False)
except rp.ProtocolError as exc:
    check("v7 parser refuses a v8 payload", "schema version 8" in str(exc), str(exc))

print("=== retained-prefix invariants ===")
for name, kw in (
    ("power_seam_id != 4 rejected", dict(seam_id=3)),
    ("power_rehold_performed != 0 rejected", dict(rehold_performed=1)),
    ("rehold_guard_cycles != 0 rejected", dict(rehold_guard=65536)),
    ("qualification_mode out of range rejected", dict(mode=2)),
    ("diag_case out of range rejected", dict(diag_case=0)),
    ("nc_control_id out of range rejected", dict(nc=9)),
):
    try:
        rp.parse_pmu_qual_payload(build(**kw))
        check(name, False)
    except rp.ProtocolError:
        check(name, True)

print("=== Q1 valid sample ===")
c = cls(build())
check("valid", c["valid"], str(failed_terms(c)))
check("window cycles emitted", c["npu_pmu_window_cycles"] == 1000)
check("raw delta preserved as diagnostic", c["raw_delta_diagnostic"] == 1000)
check("no T_npu / latency key is exposed",
      not [k for k in c if "t_npu" in k.lower() or "latency" in k.lower()],
      str(sorted(c)))
check("region crc gates nothing", cls(build(region_crc=0xDEADBEEF))["valid"])

# The authoritative pair is (pre, internal_pre_release) ONLY. The release wipes
# the PMU bank; that is the expected shape and must not cost us the sample.
c = cls(build(after_return=WIPED))
check("after-return PMU wipe alone does not invalidate", c["valid"],
      str(failed_terms(c)))
check("after-return wipe still emits the window value",
      c["npu_pmu_window_cycles"] == 1000)
c = cls(build(after_return=snap(pmcr=0, cnten=0, cfg=0, cyc=0, stable=0, ovs=OVF)))
check("after-return instability/overflow does not invalidate", c["valid"],
      str(failed_terms(c)))

check("the case-A no-CFG image is the valid shape",
      cls(build(diag_case=1))["terms"]["is_case_a"])

# Subset, not strict superset: a window whose ONLY PMU accesses were the
# hook's own is exactly the shape the contract describes, so equality passes.
c = cls(build(mmio_reads=6, hook_mmio_reads=6, mmio_writes=1, hook_mmio_writes=1))
check("hook counts equal to the window totals are valid", c["valid"],
      str(failed_terms(c)))
c = cls(build(mmio_reads=200, hook_mmio_reads=6))
check("a window total far above the hook subset is valid", c["valid"],
      str(failed_terms(c)))

print("=== Q0 baseline is never a performance sample ===")
q0 = build(mode=0, hook_fired=0, hook_snapshot_valid=0,
           pmcr_disable_readback=0x4001, internal=snap(cyc=0),
           post_disable=snap(cyc=0), hook_mmio_writes=0)
r0 = rp.parse_pmu_qual_payload(q0)
check("Q0 payload parses", r0.qualification_mode == 0)
check("Q0 records the detection without firing",
      r0.hook_detected_count == 1 and r0.hook_fired_count == 0)
c = cls(q0, manifest("Q0"))
check("Q0 is not valid even against its own manifest", not c["valid"])
check("Q0 emits no performance value", c["npu_pmu_window_cycles"] is None)
check("Q0 matches its own manifest identity",
      c["terms"]["manifest_mode_matches"] and c["terms"]["manifest_build_id_matches"])
check("Q0 fails the H-PRINTF mode term", not c["terms"]["mode_is_hprintf"])
# Even a Q0 record doctored to look like a fired Q1 run stays invalid: the
# mode and build identity are independent terms.
c = cls(build(mode=0, hook_lr=LR_Q0), manifest("Q0"))
check("Q0 with a full hook shape is still not a performance sample",
      not c["valid"] and c["npu_pmu_window_cycles"] is None)

print("=== fail-closed negatives (each independently) ===")
negatives = [
    ("Q0 presented as a Q1 sample",
     build(mode=0, build_id=rp.PMU_QUAL_BUILD_IDS["Q0"], hook_lr=LR_Q1),
     manifest(), ["build_id_is_hprintf", "manifest_build_id_matches",
                  "manifest_mode_matches", "mode_is_hprintf"]),
    ("Q1 record carrying the Q0 build id",
     build(build_id=rp.PMU_QUAL_BUILD_IDS["Q0"]), manifest(),
     ["build_id_is_hprintf", "manifest_build_id_matches"]),
    ("unknown build id", build(build_id=0x11111111), manifest(),
     ["build_id_is_hprintf", "manifest_build_id_matches"]),
    ("negative-control build", build(nc=3), manifest(), ["is_normal_build"]),
    # Q0/Q1 are contractually case-A images: they write no PMCCNTR_CFG at all.
    # A record claiming case B or C describes a different image, so it can
    # never be a qualification sample even if every other term holds.
    ("case B record", build(diag_case=2), manifest(), ["is_case_a"]),
    ("case C record", build(diag_case=3), manifest(), ["is_case_a"]),
    ("manifest schema is not 8", build(), manifest(schema_version=7),
     ["manifest_schema_matches"]),
    ("manifest mode unknown", build(), dict(manifest(), qualification_mode="QX"),
     ["manifest_mode_matches"]),
    ("manifest without an expected LR",
     build(), dict(manifest(), expected_return_address=None),
     ["hook_callsite_lr_matches_manifest"]),
    ("observed LR mismatch", build(hook_lr=LR_Q1 + 4), manifest(),
     ["hook_callsite_lr_matches_manifest"]),
    ("observed LR from the other mode", build(hook_lr=LR_Q0), manifest(),
     ["hook_callsite_lr_matches_manifest"]),
    ("hook never armed", build(hook_armed=0), manifest(), ["hook_armed"]),
    ("hook arm never consumed", build(hook_consumed=0), manifest(),
     ["hook_arm_consumed"]),
    ("hook detected 0 times", build(hook_detected=0), manifest(),
     ["hook_detected_once"]),
    ("hook detected 2 times", build(hook_detected=2), manifest(),
     ["hook_detected_once"]),
    ("hook fired 0 times", build(hook_fired=0), manifest(), ["hook_fired_once"]),
    ("hook fired 2 times", build(hook_fired=2), manifest(), ["hook_fired_once"]),
    ("hook snapshot not valid", build(hook_snapshot_valid=0), manifest(),
     ["hook_snapshot_valid"]),
    # Design section 10 requires npu_cmd_at_hook to be EXACTLY 0, not merely
    # free of the release bits: at the hook the vendor driver has not yet
    # issued anything, so any set bit means the CMD register was already in a
    # state this sample cannot account for.
    ("power already released at the hook", build(cmd_at_hook=0xC), manifest(),
     ["npu_power_held_at_hook"]),
    ("non-release CMD bit 0 set at the hook", build(cmd_at_hook=0x1),
     manifest(), ["npu_power_held_at_hook"]),
    ("non-release CMD bit 1 set at the hook", build(cmd_at_hook=0x2),
     manifest(), ["npu_power_held_at_hook"]),
    ("high CMD bits set at the hook", build(cmd_at_hook=0x10), manifest(),
     ["npu_power_held_at_hook"]),
    ("partial release bits set at the hook", build(cmd_at_hook=0x4),
     manifest(), ["npu_power_held_at_hook"]),
    # The hook's PMU accesses happen INSIDE the measurement window, so the
    # hook-local counts are a subset of the whole-window deltas. A window
    # total below its own subset means the two counters were not counting the
    # same accesses, and neither number can then be trusted.
    ("hook reads exceed the window total",
     build(mmio_reads=5, hook_mmio_reads=6), manifest(),
     ["hook_mmio_reads_within_window"]),
    ("hook writes exceed the window total",
     build(mmio_writes=0, hook_mmio_writes=1), manifest(),
     ["hook_mmio_writes_within_window"]),
    ("window read total is zero while the hook read",
     build(mmio_reads=0), manifest(), ["hook_mmio_reads_within_window"]),
    ("CFG write performed", build(cfg_written=1, cfg_value=0x11,
                                  cfg_readback=0x11,
                                  pre=snap(cfg=0x11),
                                  internal=snap(cfg=0x11, cyc=1000)),
     manifest(), ["cfg_internal_zero", "cfg_no_write", "cfg_pre_zero"]),
    ("PRE CFG non-zero", build(pre=snap(cfg=0x11)), manifest(), ["cfg_pre_zero"]),
    ("internal CFG drifted non-zero", build(internal=snap(cfg=0x11, cyc=1000)),
     manifest(), ["cfg_internal_zero"]),
    ("PRE arm lost", build(pre=snap(cnten=0)), manifest(), ["pre_armed"]),
    ("internal arm lost", build(internal=snap(cnten=0, cyc=1000)), manifest(),
     ["internal_armed"]),
    ("PRE global enable lost", build(pre=snap(pmcr=0)), manifest(),
     ["pre_global_enable"]),
    ("internal global enable lost", build(internal=snap(pmcr=0, cyc=1000)),
     manifest(), ["internal_global_enable"]),
    ("PRE cycle read unstable", build(pre=snap(stable=0, retries=4)), manifest(),
     ["pre_read_stable"]),
    ("internal cycle read unstable",
     build(internal=snap(cyc=1000, stable=0, retries=4)), manifest(),
     ["internal_read_stable"]),
    ("PRE overflow sticky bit", build(pre=snap(ovs=OVF)), manifest(),
     ["no_overflow"]),
    ("internal overflow sticky bit", build(internal=snap(cyc=1000, ovs=OVF)),
     manifest(), ["no_overflow"]),
    ("zero delta", build(pre=snap(cyc=500), internal=snap(cyc=500)), manifest(),
     ["positive_delta"]),
    ("reset-to-zero modulo artifact",
     build(pre=snap(cyc=5000), internal=snap(cyc=0)), manifest(),
     ["positive_delta"]),
    ("PMU disable never acknowledged", build(pmcr_disable_readback=0x4001),
     manifest(), ["pmu_disable_acknowledged"]),
    ("vendor release not observed after return", build(cmd_after_return=0),
     manifest(), ["vendor_release_after_return"]),
    ("partial vendor release bits after return", build(cmd_after_return=0x4),
     manifest(), ["vendor_release_after_return"]),
    ("golden window base wrong", build(gw_base=0x90020000), manifest(),
     ["golden_window_ok"]),
    ("golden window len wrong", build(gw_len=0x80), manifest(),
     ["golden_window_ok"]),
    ("golden window CRC wrong", build(gw_crc=0x1234), manifest(),
     ["golden_window_ok"]),
    ("inference rc nonzero", build(rc=5), manifest(), ["run_rc_ok"]),
    ("required inference flags missing", build(flags=0x01), manifest(),
     ["required_flags_ok"]),
    ("wrong start sequence", build(sequence_id=0), manifest(),
     ["start_sequence_ok"]),
    ("power guard wrong", build(power_guard=0), manifest(), ["power_hold_ok"]),
    ("power request not held", build(cmd_after_request=0xC), manifest(),
     ["power_hold_ok"]),
    ("NPU still in reset", build(status_after_request=0x8), manifest(),
     ["power_hold_ok"]),
    ("reset guard wrong", build(reset_guard=0), manifest(),
     ["reset_guard_complete"]),
    ("arm missing after program", build(arm_program=0), manifest(),
     ["armed_after_program"]),
    ("global enable missing after program", build(pmcr_program=0x4000),
     manifest(), ["global_after_program"]),
    ("program not stable", build(program_stable=0), manifest(),
     ["program_stable"]),
    ("stability read count short", build(stability_reads=7), manifest(),
     ["program_stable"]),
]
for name, payload, man, want in negatives:
    c = cls(payload, man)
    got = failed_terms(c)
    ok = (not c["valid"]) and c["npu_pmu_window_cycles"] is None
    if want:
        # Naming the exact failing terms keeps each gate diagnostic: a record
        # that failed for an unrelated reason would otherwise look like proof.
        ok = ok and got == want
    check("invalid: %s" % name, ok, str(got))

# The modulus makes a "backwards" counter look enormously positive. That is a
# real hazard, so it is asserted explicitly rather than left implied: only the
# reset-to-zero shape is detectable from the pair, and a plain backwards read
# stays positive by construction.
c = cls(build(pre=snap(cyc=5000), internal=snap(cyc=4000)))
check("backwards read is modular-positive (documented limit)",
      c["raw_delta_diagnostic"] == ((4000 - 5000) & ((1 << 48) - 1))
      and c["terms"]["positive_delta"])

print("=== delta arithmetic ===")
c = cls(build(pre=snap(cyc=(1 << 48) - 10), internal=snap(cyc=90)))
check("48-bit wrap is positive progress, never negative",
      c["npu_pmu_window_cycles"] == 100, str(c["npu_pmu_window_cycles"]))
c = cls(build(pre=snap(cyc=0), internal=snap(cyc=1)))
check("smallest positive delta is emitted", c["npu_pmu_window_cycles"] == 1)
check("delta ignores the post-disable and after-return snapshots",
      cls(build(post_disable=snap(cyc=99), after_return=snap(cyc=12345)))
      ["npu_pmu_window_cycles"] == 1000)

print("=== v7 classifier semantics are not reused ===")
try:
    rp.classify_pmu_qual(rp.parse_pmu_qual_payload(build()))
    check("the manifest is a required argument, never defaulted", False)
except TypeError:
    check("the manifest is a required argument, never defaulted", True)
_v7_only = ("cfg_programmed", "cfg_write_path_ok", "progress_observed",
            "usable_diagnostic_delta", "measurement_usable")
c = cls(build())
check("no v7 verdict key leaks into the v8 classification",
      not [k for k in _v7_only if k in c or k in c["terms"]],
      str([k for k in _v7_only if k in c or k in c["terms"]]))

# ---------------------------------------------------------------------------
# Collector / analyzer: the evidence chain around the payload
#
# The parser above proves the bytes decode. Everything below proves the bytes
# are BOUND to a specific build: a manifest emitted by the ELF gate, the exact
# BIN files that were deployed, and a re-read that shows the latch is not
# serving an older run. No serial port is opened anywhere in this file.
# ---------------------------------------------------------------------------

BIN_BODIES = {"Q0": b"q0-image-bytes", "Q1": b"q1-image-bytes"}


def write_bins(dirpath, mode):
    """The three deployed artifacts, with their real hashes."""
    digests = {}
    for name in rq.BIN_FILES:
        body = b"%s|%s" % (name.encode(), BIN_BODIES[mode])
        with open(os.path.join(dirpath, name), "wb") as handle:
            handle.write(body)
        digests[name] = hashlib.sha256(body).hexdigest()
    return digests


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

# ---------------------------------------------------------------------------
# The REAL manifests, transcribed from the authoritative container build:
#   docker exec benchmark-runner cat \
#     /work/selftest/build_pmu_qual_q{0,1}/pmu_qual_manifest.json
#   q0 file sha256 6d98025153fef18cd96e4962da5acc54848ccef6d08c497952fb78e58e5b4687
#   q1 file sha256 e2c1ebe0c140bb144032351dd81ddfd031e527ec37ad859663cef05cdad72f33
#
# Every field verify_manifest_identity() reads is reproduced verbatim.
# compiler_flags is omitted (nothing here reads it) and artifact_sha256 is
# supplied per test, because these fixtures get hashed against local files.
#
# The load-bearing fact: THIS PAIR LINKS THE TARGET CALLSITE AT THE SAME
# ADDRESS in both modes. Any host rule that assumed the two addresses differ
# would reject a perfectly good build, which is why no such rule exists.
# ---------------------------------------------------------------------------
REAL_CALLSITE = {
    "schema_version": 8,
    "caller_symbol": "test_u85",
    "callsite_disassembly_sha256":
        "b3afd9963258a899ee3ee318f608cb86782c141d20a4197262fc4d58fffd06e3",
    "stop_store_address": 822085508,
    "target_call_address": 822085512,
    "expected_return_address": 822085516,
    "release_store_address": 822085518,
    "release_immediate_address": 822085516,
    "release_immediate_value": 12,
    "object_caller_symbol": "test_u85",
    "object_section": ".text.test_u85",
    "object_target_call_offset": 400,
    "object_target_literal_offset": 584,
    "object_target_relocation_symbol": "printf",
    "object_target_relocation_type": "R_ARM_THM_CALL",
    "object_target_string_offset": 396,
    "object_target_string_section": ".rodata.test_u85.str1.4",
    "printf_relocations": 12,
    "puts_relocations": 0,
    "test_cpm": 1,
    "vendor_object_sha256":
        "cf0e816e161186f6d25750d340867afb1a268f2ef949b97212c3c8b7964fead2",
    "vendor_source_sha256":
        "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf",
}
REAL_HOOK = {
    "hook_order_sha256":
        "0539a5b438ba7c824bb2a49b3c7af8822e94216f0c251abb22469c8c06babb75",
    "hook_address": 822087732,
    "hook_wrapper_call_address": 822092046,
    "hook_internal_pre_release_cycle_read_address": 822087762,
    "hook_pre_release_pmcr_address": 822087778,
    "hook_pre_release_pmcntenset_address": 822087790,
    "hook_pre_release_pmccntr_cfg_address": 822087802,
    "hook_pre_release_pmovsset_address": 822087814,
    "hook_pmu_disable_address": 822087820,
    "hook_dsb_address": 822087824,
    "hook_pmcr_readback_address": 822087832,
    "hook_internal_post_disable_capture_address": 822087842,
    "hook_snapshot_valid_latch_address": 822087878,
    "hook_return_address": 822087880,
}
# sha256 of the deployed artifacts in the same container build.
REAL_BIN_SHA256 = {
    "Q0": {
        "APP.BIN":
            "727563fd252f574e19145b6d2beac388e4eed5205cf5f7cd92ff94f88a8e111d",
        "VECTORS.BIN":
            "eff245cd435a34c50c5ac2cd834a89c9e9114cef0131fcc5a7fb0b0ebc562309",
        "DDR.BIN":
            "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
    },
    "Q1": {
        "APP.BIN":
            "dc66915a26f95e983b28b160d9acdec48e3091d989f02636b8399c97865754cb",
        "VECTORS.BIN":
            "5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9",
        "DDR.BIN":
            "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
    },
}


def real_manifest(mode, artifacts=None):
    doc = dict(REAL_CALLSITE,
               qualification_mode=mode,
               build_id="0x%08X" % rp.PMU_QUAL_BUILD_IDS[mode],
               artifact_sha256=dict(artifacts if artifacts is not None
                                    else REAL_BIN_SHA256[mode]))
    if mode == "Q1":
        doc.update(REAL_HOOK)
    return doc


def qual_manifest(mode="Q1", artifacts=None, **kw):
    """A check_pmu_qual.py manifest slice, shaped exactly as that gate emits
    it: build_id as a hex string, every address numeric, artifact hashes under
    artifact_sha256 keyed by file name, and hook evidence for Q1 ONLY."""
    lr = LR_Q1 if mode == "Q1" else LR_Q0
    doc = {
        "schema_version": 8,
        "qualification_mode": mode,
        "build_id": "0x%08X" % rp.PMU_QUAL_BUILD_IDS[mode],
        "vendor_source_sha256": "aa" * 32,
        "vendor_object_sha256": "bb" * 32,
        "caller_symbol": "test_u85",
        "stop_store_address": lr - 0x10,
        "target_call_address": lr - 4,
        "expected_return_address": lr,
        "release_store_address": lr + 8,
        "release_immediate_value": 12,
        "release_immediate_address": lr + 4,
        "object_target_relocation_symbol": "printf",
        "object_target_relocation_type": "R_ARM_THM_CALL",
        # Address-normalized, so the two separately linked images are
        # comparable on logical shape rather than on numeric addresses.
        "callsite_disassembly_sha256": "cc" * 32,
        "test_cpm": 1,
        "printf_relocations": 12,
        "puts_relocations": 0,
        "compiler_flags": "-O2 -fno-builtin-printf",
        "artifact_sha256": dict(artifacts or {}),
    }
    if mode == "Q1":
        doc.update(HOOK_EVIDENCE)
    doc.update(kw)
    return doc


def frame_command(blob):
    _magic, _ver, cmd, _flags, seq, _plen = struct.unpack_from(rp.HEADER, blob)
    return cmd, seq


def ack(seq):
    return rp.Frame(1, rp.CMD_RUN_PMU_DIAG | 0x80, 0, seq, b"")


def complete(payload, seq=None):
    return rp.Frame(1, rp.CMD_PMU_DIAG_COMPLETE, 0, seq, payload)


def reread_reply(payload, seq=None):
    return rp.Frame(1, rp.CMD_GET_PMU_DIAG_RESULT | 0x80, 0, seq, payload)


class FakeLink:
    """Just enough RunnerLink for the schema-v8 transport: a sequence counter,
    a sink for sent frames, and a scripted reply per command.

    It deliberately does NOT provide run_pmu_diag()/get_pmu_diag_result(): if
    the collector ever reached for the v7 transport -- which parses with
    parse_pmu_diag_payload() and refuses v8 -- these tests would die with an
    AttributeError instead of quietly passing.
    """

    def __init__(self, on_run, on_get=None, seq=40):
        self._seq = seq
        self.on_run = on_run
        self.on_get = on_get or (lambda seq: [])
        self.late_frames = 0
        self.sent = []
        self.queue = []

    def next_sequence(self):
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    def send_raw(self, blob):
        cmd, seq = frame_command(blob)
        self.sent.append((cmd, seq))
        handler = {rp.CMD_RUN_PMU_DIAG: self.on_run,
                   rp.CMD_GET_PMU_DIAG_RESULT: self.on_get}[cmd]
        for frame in handler(seq):
            # A frame scripted without an explicit sequence belongs to the
            # exchange that just went out; an explicit one is the whole point
            # of the stale-straggler cases.
            self.queue.append(frame if frame.sequence is not None
                              else rp.Frame(frame.version, frame.command,
                                            frame.flags, seq, frame.payload))

    def read_frame(self, timeout=5.0):
        if not self.queue:
            raise rp.ProtocolError("timed out waiting for a frame")
        return self.queue.pop(0)


def link_for(payload, run=None, get=None):
    """The nominal exchange: ACK, unsolicited COMPLETE, then a GET re-read."""
    return FakeLink(run or (lambda seq: [ack(seq), complete(payload)]),
                    get if get is not None
                    else (lambda seq: [reread_reply(payload)]))


def collected(tmp, mode="Q1", payload=None, man=None, boot=1, bins_mode=None):
    """Everything run_pmu_qual.main() does except opening the port: manifest
    identity, local BIN hashes, one collected sample, one archive."""
    bins_dir = os.path.join(tmp, "bins_%s_%d" % (mode, boot))
    os.makedirs(bins_dir, exist_ok=True)
    digests = write_bins(bins_dir, bins_mode or mode)
    if payload is None:
        payload = (build() if mode == "Q1"
                   else build(mode=0, hook_fired=0, hook_snapshot_valid=0))
    if man is None:
        man = qual_manifest(mode, artifacts=digests)
    elif callable(man):
        man = man(digests)
    man_path = os.path.join(tmp, "manifest_%s_%d.json" % (mode, boot))
    with open(man_path, "w") as handle:
        json.dump(man, handle)

    doc, blob = rq.read_manifest(man_path, mode)
    observed = rq.verify_local_bins(doc, bins_dir)
    res, raw, reread = rq.collect_pmu_qual(link_for(payload))
    rq.verify_record_identity(res, doc, mode)
    record = rq.build_record(mode, boot, bins_dir, doc, man_path, blob,
                             observed, res, raw, reread)
    out = os.path.join(tmp, "%s_boot%d.json" % (mode, boot))
    with open(out, "w") as handle:
        json.dump(record, handle, indent=2)
    return out, record


def rejects(name, fn):
    try:
        fn()
        check(name, False, "accepted")
    except (SystemExit, rp.ProtocolError, rp.Nack) as exc:
        check(name, True, str(exc)[:60])


print("=== collector: manifest identity is proven before the port opens ===")
with tempfile.TemporaryDirectory() as tmp:
    digests = write_bins(tmp, "Q1")

    def manifest_at(doc, name="m.json"):
        path = os.path.join(tmp, name)
        with open(path, "w") as handle:
            json.dump(doc, handle)
        return path

    good = manifest_at(qual_manifest("Q1", artifacts=digests))
    check("a well-formed Q1 manifest loads",
          rq.load_manifest(good, "Q1")["caller_symbol"] == "test_u85")

    rejects("missing manifest file",
            lambda: rq.load_manifest(os.path.join(tmp, "absent.json"), "Q1"))
    bad_json = os.path.join(tmp, "bad.json")
    with open(bad_json, "w") as handle:
        handle.write("{not json")
    rejects("unparseable manifest", lambda: rq.load_manifest(bad_json, "Q1"))
    rejects("manifest schema is not 8", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests, schema_version=7),
                    "s7.json"), "Q1"))
    rejects("manifest mode disagrees with --mode",
            lambda: rq.load_manifest(good, "Q0"))
    rejects("Q0 manifest carrying the Q1 build id", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q0", artifacts=digests,
                                  build_id="0x%08X" % rp.PMU_QUAL_BUILD_IDS["Q1"]),
                    "q0q1.json"), "Q0"))
    rejects("Q1 manifest carrying the Q0 build id", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests,
                                  build_id="0x%08X" % rp.PMU_QUAL_BUILD_IDS["Q0"]),
                    "q1q0.json"), "Q1"))
    rejects("manifest build id unparseable", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests, build_id="PQH1"),
                    "bid.json"), "Q1"))
    rejects("manifest without an expected return address",
            lambda: rq.load_manifest(
                manifest_at(qual_manifest("Q1", artifacts=digests,
                                          expected_return_address=None),
                            "nolr.json"), "Q1"))
    rejects("manifest expected return address is not numeric",
            lambda: rq.load_manifest(
                manifest_at(qual_manifest("Q1", artifacts=digests,
                                          expected_return_address="0x2ABCC"),
                            "strlr.json"), "Q1"))
    rejects("manifest missing the callsite digest", lambda: rq.load_manifest(
        manifest_at(dict((k, v) for k, v in
                         qual_manifest("Q1", artifacts=digests).items()
                         if k != "callsite_disassembly_sha256"), "nodig.json"),
        "Q1"))
    rejects("manifest not built with TEST_CPM=1", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests, test_cpm=0),
                    "cpm0.json"), "Q1"))
    rejects("manifest callsite digest is not a SHA-256",
            lambda: rq.load_manifest(manifest_at(
                qual_manifest("Q1", artifacts=digests,
                              callsite_disassembly_sha256="cc"), "shortdig.json"),
                "Q1"))
    rejects("manifest attests the wrong caller", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests,
                                  caller_symbol="main"), "caller.json"), "Q1"))
    rejects("the target call relocates against puts, not printf",
            lambda: rq.load_manifest(manifest_at(
                qual_manifest("Q1", artifacts=digests,
                              object_target_relocation_symbol="puts"),
                "puts.json"), "Q1"))
    rejects("the target relocation is not a CALL", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests,
                                  object_target_relocation_type="R_ARM_ABS32"),
                    "abs32.json"), "Q1"))
    rejects("the release immediate is not the vendor's terminal CMD",
            lambda: rq.load_manifest(manifest_at(
                qual_manifest("Q1", artifacts=digests,
                              release_immediate_value=4), "imm4.json"), "Q1"))
    check("the Q0 manifest carries no hook evidence at all",
          not [k for k in qual_manifest("Q0") if k.startswith("hook_")])
    rejects("a Q0 manifest carrying hook evidence", lambda: rq.load_manifest(
        manifest_at(dict(qual_manifest("Q0", artifacts=digests),
                         **HOOK_EVIDENCE), "q0hook.json"), "Q0"))
    for key in rq.Q1_HOOK_REQUIRED:
        rejects("Q1 manifest missing %s" % key, lambda key=key:
                rq.load_manifest(manifest_at(
                    dict((k, v) for k, v in
                         qual_manifest("Q1", artifacts=digests).items()
                         if k != key), "no_%s.json" % key), "Q1"))
    rejects("Q1 hook order digest is not a SHA-256", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests,
                                  hook_order_sha256="ee"), "hookdig.json"),
        "Q1"))
    rejects("Q1 hook address is not numeric", lambda: rq.load_manifest(
        manifest_at(qual_manifest("Q1", artifacts=digests,
                                  hook_pmu_disable_address="0x2b020"),
                    "hookaddr.json"), "Q1"))
    for key in ("vendor_source_sha256", "vendor_object_sha256"):
        rejects("manifest %s is not a SHA-256" % key, lambda key=key:
                rq.load_manifest(manifest_at(
                    qual_manifest("Q1", artifacts=digests,
                                  **{key: "not-a-digest"}),
                    "bad_%s.json" % key), "Q1"))
        rejects("manifest %s is truncated" % key, lambda key=key:
                rq.load_manifest(manifest_at(
                    qual_manifest("Q1", artifacts=digests, **{key: "ab" * 16}),
                    "short_%s.json" % key), "Q1"))

    print("=== collector: the ACTUAL container manifests are accepted ===")
    real_q0 = manifest_at(real_manifest("Q0"), "real_q0.json")
    real_q1 = manifest_at(real_manifest("Q1"), "real_q1.json")
    d0 = rq.load_manifest(real_q0, "Q0")
    d1 = rq.load_manifest(real_q1, "Q1")
    check("the real Q0 manifest passes preflight",
          d0["qualification_mode"] == "Q0"
          and d0["build_id"] == "0x30425150")
    check("the real Q1 manifest passes preflight",
          d1["qualification_mode"] == "Q1"
          and d1["build_id"] == "0x31485150")
    # The whole point of this pair: the two modes link the target callsite at
    # the SAME address, and BOTH manifests are still accepted.
    check("the real pair shares one expected_return_address, and both load",
          d0["expected_return_address"] == d1["expected_return_address"]
          == 822085516)
    check("the real pair shares one normalized callsite digest",
          d0["callsite_disassembly_sha256"]
          == d1["callsite_disassembly_sha256"])
    check("the real Q1 manifest carries every required hook field",
          not [k for k in rq.Q1_HOOK_REQUIRED if k not in d1])
    check("the real Q0 manifest carries no hook field at all",
          not [k for k in d0 if k.startswith("hook_")])
    check("the real release store follows the real return address",
          d1["release_store_address"] > d1["expected_return_address"])
    # A record from either real image binds against its own manifest, and the
    # shared address means a Q0 record also satisfies the Q1 manifest's LR --
    # which is exactly why mode and build id are separate terms.
    same_lr = build(hook_lr=822085516)
    check("a real-LR Q1 record binds to the real Q1 manifest",
          rq.verify_record_identity(rp.parse_pmu_qual_payload(same_lr), d1,
                                    "Q1") is None)
    rejects("a Q0 record still cannot pass as Q1 despite the shared LR",
            lambda: rq.verify_record_identity(
                rp.parse_pmu_qual_payload(build(mode=0, hook_lr=822085516)),
                d1, "Q1"))

    print("=== collector: the real BIN hashes gate the deployed files ===")
    check("the real manifests carry the container's artifact hashes",
          real_manifest("Q0")["artifact_sha256"] == REAL_BIN_SHA256["Q0"]
          and real_manifest("Q1")["artifact_sha256"] == REAL_BIN_SHA256["Q1"])
    check("both modes ship the same official DDR.BIN",
          REAL_BIN_SHA256["Q0"]["DDR.BIN"] == REAL_BIN_SHA256["Q1"]["DDR.BIN"]
          == "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98")
    check("the two modes ship DIFFERENT APP/VECTORS images",
          REAL_BIN_SHA256["Q0"]["APP.BIN"] != REAL_BIN_SHA256["Q1"]["APP.BIN"]
          and REAL_BIN_SHA256["Q0"]["VECTORS.BIN"]
          != REAL_BIN_SHA256["Q1"]["VECTORS.BIN"])
    rejects("local BINs that are not the container's are refused",
            lambda: rq.verify_local_bins(d1, tmp))
    check("the same real manifest passes once the local BINs match it",
          rq.verify_local_bins(real_manifest("Q1", artifacts=digests), tmp)
          == digests)

    # Opt-in: point PMU_QUAL_REAL_DIR at a directory holding q0/ and q1/
    # copies of the container's pmu_qual_manifest.json + the three BINs to run
    # the byte-exact preflight instead of the transcription above.
    real_dir = os.environ.get("PMU_QUAL_REAL_DIR")
    if real_dir:
        for mode, sub in (("Q0", "q0"), ("Q1", "q1")):
            base = os.path.join(real_dir, sub)
            doc = rq.load_manifest(
                os.path.join(base, "pmu_qual_manifest.json"), mode)
            check("byte-exact %s manifest + BINs accepted" % mode,
                  rq.verify_local_bins(doc, base) == REAL_BIN_SHA256[mode])
    else:
        print("  SKIP byte-exact container artifacts (set PMU_QUAL_REAL_DIR)")

    print("=== collector: the manifest is read exactly once ===")
    once = manifest_at(qual_manifest("Q1", artifacts=digests), "once.json")
    doc, blob = rq.read_manifest(once, "Q1")
    check("read_manifest returns the parsed doc and its exact bytes",
          json.loads(blob.decode()) == doc
          and blob == open(once, "rb").read())
    # The archive is built from THOSE bytes, so a manifest edited after
    # preflight cannot become the reference the sample is judged against.
    with open(once, "w") as handle:
        json.dump(qual_manifest("Q1", artifacts=digests,
                                caller_symbol="rewritten_after_preflight"),
                  handle)
    res, raw, reread = rq.collect_pmu_qual(link_for(build()))
    record = rq.build_record("Q1", 1, tmp, doc, once, blob, digests, res, raw,
                             reread)
    check("the archive carries the bytes preflight read, not the file's",
          json.loads(record["host"]["manifest_text"])["caller_symbol"]
          == "test_u85"
          and record["host"]["manifest_sha256"]
          == hashlib.sha256(blob).hexdigest())

    print("=== collector: the deployed BINs must be the manifest's BINs ===")
    doc = rq.load_manifest(good, "Q1")
    check("matching local BINs pass",
          rq.verify_local_bins(doc, tmp) == digests)
    rejects("APP.BIN hash mismatch", lambda: rq.verify_local_bins(
        dict(doc, artifact_sha256=dict(digests, **{"APP.BIN": "00" * 32})), tmp))
    rejects("VECTORS.BIN hash mismatch", lambda: rq.verify_local_bins(
        dict(doc, artifact_sha256=dict(digests, **{"VECTORS.BIN": "00" * 32})),
        tmp))
    rejects("DDR.BIN hash mismatch", lambda: rq.verify_local_bins(
        dict(doc, artifact_sha256=dict(digests, **{"DDR.BIN": "00" * 32})), tmp))
    rejects("manifest carries no artifact hashes", lambda: rq.verify_local_bins(
        dict(doc, artifact_sha256={}), tmp))
    rejects("bins dir does not hold the artifacts",
            lambda: rq.verify_local_bins(doc, os.path.join(tmp, "nowhere")))

print("=== collector: the v8 transport is local and isolated from v7 ===")
check("the v8 link only ADDS a sequence seam to RunnerLink",
      issubclass(rq.PmuQualLink, rp.RunnerLink)
      and rq.PmuQualLink.run_pmu_diag is rp.RunnerLink.run_pmu_diag
      and rq.PmuQualLink.get_pmu_diag_result is rp.RunnerLink.get_pmu_diag_result)
check("the collector never imports the v7 payload parser",
      not hasattr(rq, "parse_pmu_diag_payload"))

p1 = build()
link = link_for(p1)
res, raw, reread = rq.collect_pmu_qual(link)
check("one schema-v8 sample collected over the 0x60/0x61/0x62 framing",
      raw == p1 and reread == p1
      and res.build_id == rp.PMU_QUAL_BUILD_IDS["Q1"])
check("the re-read is an independent request with its own sequence",
      [cmd for cmd, _ in link.sent]
      == [rp.CMD_RUN_PMU_DIAG, rp.CMD_GET_PMU_DIAG_RESULT]
      and link.sent[0][1] != link.sent[1][1])
check("prior raw state is cleared before the run is sent",
      link.last_pmu_qual_raw == p1 and link.last_pmu_qual_reread_raw == p1)

# The v7 transport would have refused this payload outright; the v8 one takes
# it, and the v7 PARSER still refuses it (asserted in the isolation section
# above). That is the whole point of the split.
v7ish = bytes(build())
try:
    rp.parse_pmu_diag_payload(v7ish)
    check("the v7 parser still refuses what the v8 transport accepted", False)
except rp.ProtocolError:
    check("the v7 parser still refuses what the v8 transport accepted", True)

print("=== collector: COMPLETE + independent re-read ===")
# A COMPLETE carrying an earlier exchange's sequence is a straggler. Adopting
# one would report a PREVIOUS run's window as this run's evidence.
link = link_for(p1, run=lambda seq: [ack(seq), complete(p1, seq=seq - 7),
                                     complete(p1)])
res, raw, _ = rq.collect_pmu_qual(link)
check("a stale COMPLETE is dropped and the fresh one adopted",
      raw == p1 and link.late_frames == 1)
rejects("only a stale COMPLETE arrives -> no result",
        lambda: rq.collect_pmu_qual(link_for(
            p1, run=lambda seq: [ack(seq), complete(p1, seq=seq - 7)])))
rejects("no ACK at all",
        lambda: rq.collect_pmu_qual(link_for(p1, run=lambda seq: [])))
rejects("no COMPLETE at all",
        lambda: rq.collect_pmu_qual(link_for(p1, run=lambda seq: [ack(seq)])))
rejects("COMPLETE before its own ACK", lambda: rq.collect_pmu_qual(
    link_for(p1, run=lambda seq: [complete(p1), ack(seq)])))
rejects("duplicate ACK", lambda: rq.collect_pmu_qual(
    link_for(p1, run=lambda seq: [ack(seq), ack(seq), complete(p1)])))
rejects("duplicate COMPLETE", lambda: rq.collect_pmu_qual(
    link_for(p1, run=lambda seq: [ack(seq), complete(p1), complete(p1)])))
rejects("the run is NACKed", lambda: rq.collect_pmu_qual(link_for(
    p1, run=lambda seq: [rp.Frame(1, rp.NACK, 3, seq, bytes([0x60, 2]))])))
rejects("the re-read payload differs from the COMPLETE payload",
        lambda: rq.collect_pmu_qual(link_for(
            p1, get=lambda seq: [reread_reply(build(seq=8))])))
rejects("the re-read returns nothing", lambda: rq.collect_pmu_qual(
    link_for(p1, get=lambda seq: [reread_reply(b"")])))
rejects("no re-read response at all", lambda: rq.collect_pmu_qual(
    link_for(p1, get=lambda seq: [])))
rejects("the re-read answers with the wrong command",
        lambda: rq.collect_pmu_qual(link_for(
            p1, get=lambda seq: [rp.Frame(1, rp.CMD_PING | 0x80, 0, seq, p1)])))
rejects("the re-read is NACKed", lambda: rq.collect_pmu_qual(link_for(
    p1, get=lambda seq: [rp.Frame(1, rp.NACK, 3, seq, bytes([0x61, 2]))])))
rejects("a corrupt COMPLETE never reaches the archive",
        lambda: rq.collect_pmu_qual(link_for(
            p1, run=lambda seq: [
                ack(seq),
                complete(p1[:40] + bytes([p1[40] ^ 0xFF]) + p1[41:])])))

print("=== collector: the record must be the mode that was asked for ===")
man_q1 = qual_manifest("Q1")
check("a matching Q1 record is accepted", rq.verify_record_identity(
    rp.parse_pmu_qual_payload(build()), man_q1, "Q1") is None)
rejects("a Q0 record collected as Q1", lambda: rq.verify_record_identity(
    rp.parse_pmu_qual_payload(build(mode=0)), man_q1, "Q1"))
rejects("a Q1 record collected as Q0", lambda: rq.verify_record_identity(
    rp.parse_pmu_qual_payload(build()), qual_manifest("Q0"), "Q0"))
rejects("the record carries a foreign build id",
        lambda: rq.verify_record_identity(
            rp.parse_pmu_qual_payload(build(build_id=0x11111111)), man_q1, "Q1"))
rejects("a negative-control record", lambda: rq.verify_record_identity(
    rp.parse_pmu_qual_payload(build(nc=2)), man_q1, "Q1"))
rejects("observed LR does not match this mode's manifest",
        lambda: rq.verify_record_identity(
            rp.parse_pmu_qual_payload(build(hook_lr=LR_Q1 + 4)), man_q1, "Q1"))
rejects("observed LR matches the OTHER mode's manifest",
        lambda: rq.verify_record_identity(
            rp.parse_pmu_qual_payload(build(hook_lr=LR_Q0)), man_q1, "Q1"))
# Each mode is only ever compared with its own manifest. These fixtures use
# different addresses to prove the comparison is per-mode; the real pair uses
# the same address and is exercised further down. Both must work.
check("Q0's own LR is accepted against the Q0 manifest",
      rq.verify_record_identity(
          rp.parse_pmu_qual_payload(build(mode=0, hook_fired=0,
                                          hook_snapshot_valid=0)),
          qual_manifest("Q0"), "Q0") is None
      and qual_manifest("Q0")["expected_return_address"]
      != qual_manifest("Q1")["expected_return_address"])
# The same per-mode rule with the addresses EQUAL, which is what the current
# container builds actually produce.
check("an LR shared by both modes is accepted against either manifest",
      rq.verify_record_identity(
          rp.parse_pmu_qual_payload(build(hook_lr=822085516)),
          real_manifest("Q1"), "Q1") is None
      and rq.verify_record_identity(
          rp.parse_pmu_qual_payload(build(mode=0, hook_fired=0,
                                          hook_snapshot_valid=0,
                                          hook_lr=822085516)),
          real_manifest("Q0"), "Q0") is None)

print("=== collector: the archive carries both raw payloads ===")
with tempfile.TemporaryDirectory() as tmp:
    out, record = collected(tmp, "Q1", boot=1)
    check("both raw payload hex strings archived",
          record["raw"]["payload_hex"] == p1.hex()
          and record["raw"]["reread_payload_hex"] == p1.hex())
    check("both payload digests archived",
          record["raw"]["payload_sha256"] == hashlib.sha256(p1).hexdigest()
          and record["raw"]["reread_payload_sha256"]
          == hashlib.sha256(p1).hexdigest())
    check("the re-read equality is asserted in the archive",
          record["raw"]["reread_matches_run_payload"] is True)
    check("the exact manifest is archived",
          record["manifest"]["callsite_disassembly_sha256"] == "cc" * 32
          and record["manifest"]["expected_return_address"] == LR_Q1)
    check("the full artifact hashes are archived",
          sorted(record["host"]["artifact_sha256"]) == sorted(rq.BIN_FILES)
          and all(len(v) == 64 for v in record["host"]["artifact_sha256"].values()))
    check("the exact manifest bytes are archived with their digest",
          hashlib.sha256(record["host"]["manifest_text"].encode()).hexdigest()
          == record["host"]["manifest_sha256"]
          and json.loads(record["host"]["manifest_text"])
          == record["manifest"])
    check("the archived derived block is the v8 classification",
          record["derived"]["npu_pmu_window_cycles"] == 1000
          and record["derived"]["valid"])
    check("no performance name is invented in the archive",
          not [k for k in json.dumps(record).lower().split('"')
               if "t_npu" in k or "latency" in k])

print("=== analyzer: nothing is trusted but the raw payload ===")
with tempfile.TemporaryDirectory() as tmp:
    q1_path, q1_record = collected(tmp, "Q1", boot=2)
    q0_path, q0_record = collected(tmp, "Q0", boot=3)
    res, doc = aq.load(q1_path, "Q1")
    check("a well-formed archive loads", res.build_id
          == rp.PMU_QUAL_BUILD_IDS["Q1"] and doc["host"]["mode"] == "Q1")
    check("the Q0 archive loads too",
          aq.load(q0_path, "Q0")[0].qualification_mode == 0)
    rejects("the file was collected in the other mode",
            lambda: aq.load(q0_path, "Q1"))

    def tampered(name, mutate):
        doc = json.loads(json.dumps(q1_record))
        mutate(doc)
        path = os.path.join(tmp, name)
        with open(path, "w") as handle:
            json.dump(doc, handle)
        return path

    for name, mutate in (
        ("raw payload absent", lambda d: d["raw"].pop("payload_hex")),
        ("raw payload digest disagrees",
         lambda d: d["raw"].update(payload_sha256="00" * 32)),
        ("re-read payload absent", lambda d: d["raw"].pop("reread_payload_hex")),
        ("re-read payload differs from the run payload",
         lambda d: d["raw"].update(reread_payload_hex=build(seq=9).hex())),
        ("the collector did not prove the re-read",
         lambda d: d["raw"].update(reread_matches_run_payload=False)),
        # Re-hexed under a consistent digest, so only the manifest/record bind
        # can catch it -- and it must.
        ("payload swapped for another build's, digests rebuilt",
         lambda d: d["raw"].update(
             payload_hex=build(build_id=0x11111111).hex(),
             payload_sha256=hashlib.sha256(
                 build(build_id=0x11111111)).hexdigest(),
             reread_payload_hex=build(build_id=0x11111111).hex(),
             reread_payload_sha256=hashlib.sha256(
                 build(build_id=0x11111111)).hexdigest())),
        ("the manifest bytes are missing",
         lambda d: d["host"].pop("manifest_text")),
        ("the manifest bytes do not match their digest",
         lambda d: d["host"].update(manifest_sha256="00" * 32)),
        ("the parsed manifest disagrees with the archived bytes",
         lambda d: d["manifest"].update(caller_symbol="swapped_in_place")),
        ("the manifest was swapped for the other mode's",
         lambda d: d["host"].update(
             manifest_text=json.dumps(qual_manifest("Q0")),
             manifest_sha256=hashlib.sha256(
                 json.dumps(qual_manifest("Q0")).encode()).hexdigest())),
        ("the manifest LR no longer matches the record",
         lambda d: d["host"].update(
             manifest_text=json.dumps(
                 qual_manifest("Q1", artifacts=d["manifest"]["artifact_sha256"],
                               expected_return_address=LR_Q1 + 2)),
             manifest_sha256=hashlib.sha256(json.dumps(
                 qual_manifest("Q1", artifacts=d["manifest"]["artifact_sha256"],
                               expected_return_address=LR_Q1 + 2)
             ).encode()).hexdigest())),
        ("the deployed BIN hashes disagree with the manifest",
         lambda d: d["host"]["artifact_sha256"].update({"APP.BIN": "00" * 32})),
        ("the boot index is absent", lambda d: d["host"].pop("host_boot_index")),
        # Hand-edited archives must produce a VERDICT, not a traceback: a
        # ValueError escaping here would read as a broken tool rather than as
        # a refused sample.
        ("the payload hex is not hex",
         lambda d: d["raw"].update(payload_hex="zz" * 8)),
        ("the payload hex has an odd digit count",
         lambda d: d["raw"].update(payload_hex="abc")),
        ("the payload hex is not even a string",
         lambda d: d["raw"].update(payload_hex=1234)),
        ("the re-read hex is not hex",
         lambda d: d["raw"].update(reread_payload_hex="not hex at all")),
    ):
        rejects("analyzer refuses: %s" % name,
                (lambda p: lambda: aq.load(p, "Q1"))(tampered(
                    name.replace(" ", "_") + ".json", mutate)))

    # A wrong golden CRC is a CLASSIFIER term, not an admission gate: the
    # sample is real evidence about a real run and must archive, load and then
    # be reported INVALID. Refusing to load it would hide the failure.
    broken_golden = build(gw_crc=0x1234)
    path = tampered("bad_golden.json", lambda d: d["raw"].update(
        payload_hex=broken_golden.hex(),
        payload_sha256=hashlib.sha256(broken_golden).hexdigest(),
        reread_payload_hex=broken_golden.hex(),
        reread_payload_sha256=hashlib.sha256(broken_golden).hexdigest()))
    res, doc = aq.load(path, "Q1")
    cls = rp.classify_pmu_qual(res, doc["manifest"])
    check("a wrong-golden payload loads and then classifies INVALID",
          not cls["valid"] and cls["npu_pmu_window_cycles"] is None
          and cls["invalid_reasons"] == ["golden_window_ok"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report("Q1", res, doc)
    text = buf.getvalue()
    check("and the REPORT says INVALID, names the term, and shows the CRCs",
          "npu_pmu_window_cycles: INVALID" in text
          and "FAIL golden_window_ok" in text
          and "MISMATCH" in text
          and "0x00001234" in text
          and "0x%08X" % rp.GOLDEN_WINDOW_CRC in text)

print("=== analyzer: the report is raw evidence, never a latency ===")
with tempfile.TemporaryDirectory() as tmp:
    q1_path, _ = collected(tmp, "Q1", boot=4)
    q0_path, _ = collected(tmp, "Q0", boot=5)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report("Q1", *aq.load(q1_path, "Q1"))
    text = buf.getvalue()
    for needle in ("identity", "expected_return_address", "callsite_disassembly",
                   "start boundary", "internal_pre_release",
                   "internal_post_disable", "after_return",
                   "hook_detected_count", "hook_callsite_lr_observed",
                   "npu_cmd_at_hook", "hook_entry_timestamp",
                   "hook_pmu_mmio_read_count", "golden window", "output_crc",
                   "npu_pmu_window_cycles"):
        check("report prints %s" % needle, needle in text)
    check("report never names T_npu or a latency",
          "t_npu" not in text.lower() and "latency" not in text.lower())
    check("the window value is printed for a valid Q1", "1000" in text)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report("Q0", *aq.load(q0_path, "Q0"))
    text = buf.getvalue()
    check("the Q0 baseline reports INVALID, never a number",
          "INVALID" in text and "npu_pmu_window_cycles: 1000" not in text)
    check("the Q0 report names the terms that failed",
          "mode_is_hprintf" in text)

    # An otherwise perfect Q1 sample with one broken term prints INVALID and
    # says which term broke -- the analyzer never rounds up to a verdict.
    bad = os.path.join(tmp, "q1_bad.json")
    doc = json.loads(open(q1_path).read())
    broken = build(pmcr_disable_readback=0x4001)
    doc["raw"].update(payload_hex=broken.hex(),
                      payload_sha256=hashlib.sha256(broken).hexdigest(),
                      reread_payload_hex=broken.hex(),
                      reread_payload_sha256=hashlib.sha256(broken).hexdigest())
    with open(bad, "w") as handle:
        json.dump(doc, handle)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report("Q1", *aq.load(bad, "Q1"))
    text = buf.getvalue()
    check("a broken term makes the Q1 report INVALID",
          "INVALID" in text and "pmu_disable_acknowledged" in text)

print("=== analyzer: Q0/Q1 equivalence is logical, never numeric LR ===")
with tempfile.TemporaryDirectory() as tmp:
    q1_path, _ = collected(tmp, "Q1", boot=6)
    q0_path, _ = collected(tmp, "Q0", boot=7)
    q0 = aq.load(q0_path, "Q0")
    q1 = aq.load(q1_path, "Q1")
    ok, checks = aq.functional_equivalence(q0, q1)
    check("two independently linked images are equivalent", ok,
          str(sorted(k for k, v in checks.items() if not v)))
    check("equivalence has no numeric cross-mode LR term",
          not [k for k in checks if "lr" in k and "own" not in k], str(sorted(checks)))
    check("this fixture pair happens to sit at different addresses, and that "
          "is fine",
          q0[0].hook_callsite_lr_observed != q1[0].hook_callsite_lr_observed
          and ok)
    check("equivalence requires the inference flags on both sides",
          checks["both_required_flags_ok"])
    check("equivalence asserts the address-normalized callsite shape",
          checks["same_normalized_callsite_shape"])
    check("equivalence asserts Q0 never fired and Q1 fired once",
          checks["q0_never_fired"] and checks["q1_fired_once"])
    check("equivalence asserts independent boots", checks["independent_boots"])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report_equivalence(q0, q1)
    text = buf.getvalue()
    check("the equivalence report states the LR rule",
          "0x%08X" % LR_Q0 in text and "0x%08X" % LR_Q1 in text
          and "never" in text.lower())
    check("the equivalence report names no latency",
          "t_npu" not in text.lower() and "latency" not in text.lower())

print("=== analyzer: the REAL pair's shape -- one shared LR -- is equivalent ===")
with tempfile.TemporaryDirectory() as tmp:
    SHARED_LR = REAL_CALLSITE["expected_return_address"]
    q0 = aq.load(collected(
        tmp, "Q0", boot=20,
        payload=build(mode=0, hook_fired=0, hook_snapshot_valid=0,
                      hook_lr=SHARED_LR),
        man=lambda d: real_manifest("Q0", artifacts=d))[0], "Q0")
    q1 = aq.load(collected(
        tmp, "Q1", boot=21, payload=build(hook_lr=SHARED_LR),
        man=lambda d: real_manifest("Q1", artifacts=d))[0], "Q1")
    check("both modes observed the SAME callsite address",
          q0[0].hook_callsite_lr_observed == q1[0].hook_callsite_lr_observed
          == SHARED_LR)
    ok, checks = aq.functional_equivalence(q0, q1)
    check("an equal-LR pair is just as equivalent as a differing one", ok,
          str(sorted(k for k, v in checks.items() if not v)))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aq.report_equivalence(q0, q1)
    text = buf.getvalue()
    check("the report states the shared address plainly",
          "equal in this pair" in text and "MAY differ" in text)
    check("the report still refuses to require equality",
          "never required and never forbidden" in text)

    # Required inference flags are an equivalence term on BOTH sides.
    weak = rp.parse_pmu_qual_payload(build(flags=0x01, hook_lr=SHARED_LR))
    ok, checks = aq.functional_equivalence(q0, (weak, q1[1]))
    check("not equivalent: the Q1 run lost a required inference flag",
          not ok and not checks["both_required_flags_ok"])


def swap(loaded, **manifest_kw):
    res, doc = loaded
    fresh = json.loads(json.dumps(doc))
    fresh["manifest"].update(manifest_kw)
    return res, fresh


for name, mutate in (
    ("a different caller symbol", dict(caller_symbol="not_test_u85")),
    ("a different vendor source", dict(vendor_source_sha256="dd" * 32)),
    ("a different vendor object", dict(vendor_object_sha256="dd" * 32)),
    ("a different normalized callsite shape",
     dict(callsite_disassembly_sha256="dd" * 32)),
    ("a release store that precedes the return",
     dict(release_store_address=LR_Q1 - 8)),
):
    with tempfile.TemporaryDirectory() as tmp:
        q0 = aq.load(collected(tmp, "Q0", boot=8)[0], "Q0")
        q1 = aq.load(collected(tmp, "Q1", boot=9)[0], "Q1")
        ok, checks = aq.functional_equivalence(q0, swap(q1, **mutate))
        check("not equivalent: %s" % name, not ok,
              str(sorted(k for k, v in checks.items() if not v)))

with tempfile.TemporaryDirectory() as tmp:
    q0 = aq.load(collected(tmp, "Q0", boot=10)[0], "Q0")
    q1 = aq.load(collected(tmp, "Q1", boot=11)[0], "Q1")
    for name, payload in (
        ("Q1 that never fired", build(hook_fired=0)),
        ("Q1 whose output CRC differs", build(output_crc=0x3333)),
        ("Q1 whose golden window differs", build(gw_crc=0x1234)),
    ):
        res = rp.parse_pmu_qual_payload(payload)
        ok, checks = aq.functional_equivalence(q0, (res, q1[1]))
        check("not equivalent: %s" % name, not ok,
              str(sorted(k for k, v in checks.items() if not v)))
    # Same boot index for both modes: the two rows are not independent runs.
    same = json.loads(json.dumps(q1[1]))
    same["host"]["host_boot_index"] = q0[1]["host"]["host_boot_index"]
    ok, checks = aq.functional_equivalence(q0, (q1[0], same))
    check("not equivalent: both modes claim the same boot",
          not ok and not checks["independent_boots"])

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
