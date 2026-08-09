"""PMU_DIAG host-side unit tests. No board required.

Covers: payload integrity (magic / schema / total_payload_words authority /
two-slice CRC / header-body agreement), the 48-bit modular delta including
wrap, the collection-stage metric rule (no progress -> metric_delta is None),
the four negative-control classifications, the B proof conjunction, and the
root-cause verdict table applied to observed values only.
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import runner_proto as rp

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))
    if ok:
        passed += 1
    else:
        failed += 1


GOLDEN_W = rp.GOLDEN_WINDOW_CRC
GW_BASE = rp.PMU_DIAG_GOLDEN_WINDOW_BASE
GW_LEN = rp.PMU_DIAG_GOLDEN_WINDOW_LEN
CFG_B = 0x11        # cross-check value, same status as the firmware assert
ARMED = 1 << rp.PMU_PMCNTEN_CYCLE_BIT
OVF = 1 << rp.PMU_PMOVS_CYCLE_OVF_BIT
GLOBAL = 1 << rp.PMU_PMCR_CNT_EN_BIT


def snap(pmcr=GLOBAL, cnten=ARMED, cfg=CFG_B, cyc=0, stable=1, retries=0, ovs=0):
    return (pmcr, cnten, cfg, cyc & 0xFFFFFFFF, (cyc >> 32) & 0xFFFF,
            stable, retries, ovs)


def build(diag_case=2, nc=0, seq=7, flags=0x1F, rc=0,
          cfg_written=1, cfg_value=CFG_B, cfg_readback=CFG_B,
          # region_crc is deliberately NON-golden by default: the whole-region
          # CRC is corroboration display only, and every passing test below
          # doubles as proof that it gates nothing.
          region_crc=0xA5A50001, output_crc=0x2222,
          sequence_id=rp.PMU_DIAG_START_SEQUENCE_POWER_GUARD_PROGRAM,
          power_guard=rp.PMU_DIAG_POWER_GUARD_CYCLES,
          cmd_before=0xC, cmd_after_request=0, status_after_request=0,
          reset_guard=rp.PMU_DIAG_RESET_GUARD_CYCLES,
          pmcr_guard=0x4000, pmcr_program=0x4001, arm_program=1,
          stability_reads=rp.PMU_DIAG_STABILITY_SAMPLES, program_stable=1,
          cmd_after_release=0xC,
          # Default row is the S3 control: diag-private driver, so the runner
          # owns the terminal release and never re-holds.
          seam_id=3, rehold_performed=0, rehold_guard=0,
          cmd_after_seam=0, status_after_seam=0,
          gw_base=GW_BASE, gw_len=GW_LEN, gw_crc=GOLDEN_W,
          build_id=rp.PMU_DIAG_BUILD_IDS["B"],
          pre=None, post=None, post_disable=None,
          total_words=None, declared=None, header_seq=None):
    pre = pre if pre is not None else snap()
    post = post if post is not None else snap(cyc=1000)
    post_disable = post_disable if post_disable is not None else snap(pmcr=0, cyc=1000)
    body = [
        rp.PMU_DIAG_SCHEMA_VERSION,   # schema_version
        build_id,
        diag_case, nc, seq,
        cfg_written, cfg_value, cfg_readback,
        rc, flags,
        0x1111, output_crc, region_crc,  # poison / output / region crc
        1, 100, 200, 300,             # ts_valid, t_enter, t_return, t_disable
        0,                            # pmcr_readback_after_disable
        20, 8,                        # mmio deltas
        sequence_id, power_guard, cmd_before, cmd_after_request,
        status_after_request, reset_guard, pmcr_guard, pmcr_program,
        arm_program, stability_reads, program_stable, cmd_after_release,
        seam_id, rehold_performed, rehold_guard,
        cmd_after_seam, status_after_seam,
        gw_base, gw_len, gw_crc,
    ]
    body += list(pre) + list(post) + list(post_disable)
    total = total_words if total_words is not None else rp.PMU_DIAG_HEADER_WORDS + len(body)
    head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, rp.PMU_DIAG_SCHEMA_VERSION,
                       total if declared is None else declared,
                       rp.PMU_DIAG_HEADER_WORDS,
                       seq if header_seq is None else header_seq, flags, rc, 0)
    p = bytearray(head + b"".join(struct.pack("<I", w) for w in body))
    crc = zlib.crc32(bytes(p[16:28]) + bytes(p[32:])) & 0xFFFFFFFF
    struct.pack_into("<I", p, 28, crc)
    return bytes(p)


print("=== integrity ===")
p = build()
check("payload size is total_payload_words x 4",
      len(p) == rp.PMU_DIAG_TOTAL_WORDS_V7 * 4,
      "%d bytes" % len(p))
r = rp.parse_pmu_diag_payload(p)
check("parses", r.run_sequence == 7 and r.diag_case == 2)
check("snapshots decoded", r.post.cycle48 == 1000 and r.pre.cycle48 == 0)

for name, bad in [
    ("bad magic rejected", bytearray(p[:0]) + struct.pack("<I", 0xDEAD) + p[4:]),
    ("bad schema rejected", p[:4] + struct.pack("<I", 99) + p[8:]),
]:
    try:
        rp.parse_pmu_diag_payload(bytes(bad))
        check(name, False)
    except rp.ProtocolError:
        check(name, True)

try:
    rp.parse_pmu_diag_payload(build(declared=rp.PMU_DIAG_TOTAL_WORDS_V7 + 5))
    check("declared/actual length mismatch rejected", False)
except rp.ProtocolError:
    check("declared/actual length mismatch rejected", True)

corrupt = bytearray(build())
corrupt[40] ^= 0xFF
try:
    rp.parse_pmu_diag_payload(bytes(corrupt))
    check("payload CRC corruption rejected", False)
except rp.ProtocolError:
    check("payload CRC corruption rejected", True)

try:
    rp.parse_pmu_diag_payload(build(header_seq=99))
    check("header/body disagreement rejected", False)
except rp.ProtocolError:
    check("header/body disagreement rejected", True)

extra = build()
# trailing words: forward-compat, re-CRC a payload with 2 unknown words
body_words = list(struct.unpack("<%dI" % (len(extra) // 4), extra))
body_words[2] += 2      # total_payload_words
body_words += [0xAAAA, 0xBBBB]
q = bytearray(b"".join(struct.pack("<I", w) for w in body_words))
struct.pack_into("<I", q, 28, zlib.crc32(bytes(q[16:28]) + bytes(q[32:])) & 0xFFFFFFFF)
r2 = rp.parse_pmu_diag_payload(bytes(q))
check("trailing words tolerated and counted", r2.trailing_words == 2)

print("=== 48-bit modular delta ===")
check("normal", rp.pmu_diag_delta48(100, 1100) == 1000)
check("zero", rp.pmu_diag_delta48(500, 500) == 0)
near = (1 << 48) - 10
check("wrap is positive, never negative",
      rp.pmu_diag_delta48(near, 90) == 100)

print("=== classification: normal progress ===")
c = rp.classify_pmu_diag(rp.parse_pmu_diag_payload(build()))
check("progress observed", c["progress_observed"])
check("usable delta promoted", c["usable_diagnostic_delta"] == 1000)
check("usable", c["measurement_usable"])
check("golden window ok", c["golden_window_ok"])
check("power-guard-program start sequence ok", c["start_sequence_ok"])
check("NPU power hold established", c["power_hold_ok"])
check("NPU power release restored", c["power_release_restored"])
check("bounded reset guard recorded", c["reset_guard_complete"])
check("global enable observed after programming", c["global_after_program"])
check("arm observed after programming", c["armed_after_program"])
check("programmed state stable across spaced reads", c["program_stable"])
# The builder's default region CRC is NON-golden on purpose: usability and
# the golden gate hold anyway, proving the region value gates nothing.
check("region crc is not a validity gate", c["measurement_usable"]
      and c["golden_window_ok"])
check("cfg write path ok", c["cfg_write_path_ok"])

# Case-C shape: explicit zero write. The write PATH is proven fine while the
# configuration itself still means "never start" -- two different facts.
c = rp.classify_pmu_diag(rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0))))
check("C: cfg_write_path_ok=1", c["cfg_write_path_ok"])
check("C: cfg_programmed=0", not c["cfg_programmed"])

print("=== classification: the four defect classes ===")
# NC1 -- CFG write omitted: cfg reads back 0, armed, no progress
r = rp.parse_pmu_diag_payload(build(
    nc=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
c = rp.classify_pmu_diag(r)
check("NC1 cfg_programmed=0", not c["cfg_programmed"])
check("NC1 progress=0", not c["progress_observed"])
check("NC1 usable=0", not c["measurement_usable"])

# NC2 -- START=NO_EVENT written: same observable CFG facts, write performed
r = rp.parse_pmu_diag_payload(build(
    nc=2, cfg_written=1, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
c = rp.classify_pmu_diag(r)
check("NC2 cfg_programmed=0", not c["cfg_programmed"])
check("NC2 usable=0", not c["measurement_usable"])

# NC3 -- arm omitted: armed=0 kills cycle_read_valid
r = rp.parse_pmu_diag_payload(build(
    nc=3, pre=snap(cnten=0), post=snap(cnten=0, cyc=0)))
c = rp.classify_pmu_diag(r)
check("NC3 armed=0", not c["cycle_counter_armed"])
check("NC3 cycle_read_valid=0", not c["cycle_read_valid"])
check("NC3 usable=0", not c["measurement_usable"])

# NC4 -- forced overflow: sticky bit invalidates, raw preserved, metric None
r = rp.parse_pmu_diag_payload(build(
    nc=4, pre=snap(ovs=OVF), post=snap(ovs=OVF, cyc=5000)))
c = rp.classify_pmu_diag(r)
check("NC4 overflow", c["cycle_overflow"])
check("NC4 cycle_read_valid=0", not c["cycle_read_valid"])
check("NC4 raw delta preserved", c["raw_delta_diagnostic"] == 5000)
check("NC4 usable delta is None", c["usable_diagnostic_delta"] is None)

print("=== unstable read ===")
r = rp.parse_pmu_diag_payload(build(post=snap(cyc=1000, stable=0, retries=4)))
c = rp.classify_pmu_diag(r)
check("unstable -> progress=0", not c["progress_observed"])
check("unstable -> usable delta None", c["usable_diagnostic_delta"] is None)

print("=== B proof conjunction ===")
ok, checks = rp.pmu_diag_b_proof(rp.parse_pmu_diag_payload(build()))
check("B proof passes on the clean case", ok, str([k for k, v in checks.items() if not v]))

# The whole-region CRC must gate NOTHING: a wildly different region value
# with a correct exact window still passes the full proof.
ok, _ = rp.pmu_diag_b_proof(rp.parse_pmu_diag_payload(build(region_crc=0xDEADBEEF)))
check("B proof unaffected by whole-region crc", ok)

failing = [
    ("cfg drift post != pre", build(post=snap(cfg=0, cyc=1000))),
    ("arm lost", build(post=snap(cnten=0, cyc=1000))),
    ("global lost", build(post=snap(pmcr=0, cyc=1000))),
    ("overflow", build(post=snap(cyc=1000, ovs=OVF))),
    ("no progress", build(post=snap(cyc=0))),
    ("golden WINDOW crc mismatch", build(gw_crc=0x1234)),
    ("golden window base wrong", build(gw_base=0x90020000)),
    ("golden window len wrong", build(gw_len=0x80)),
    ("wrong start sequence", build(sequence_id=0)),
    ("power guard wrong", build(power_guard=0)),
    ("power request not held", build(cmd_after_request=0xC)),
    ("NPU still in reset", build(status_after_request=0x8)),
    ("power release not restored", build(cmd_after_release=0)),
    ("reset guard wrong", build(reset_guard=0)),
    ("global enable missing after program", build(pmcr_program=0x4000)),
    ("arm missing after program", build(arm_program=0)),
    ("stability read count short", build(stability_reads=7)),
    ("program not stable", build(program_stable=0)),
    ("cfg never written", build(cfg_written=0, cfg_value=0, cfg_readback=0,
                                pre=snap(cfg=0), post=snap(cfg=0, cyc=1000))),
    ("wrong case", build(diag_case=1, cfg_written=0, cfg_value=0,
                         cfg_readback=0, pre=snap(cfg=0),
                         post=snap(cfg=0, cyc=1000))),
    ("negative-control build", build(nc=4, post=snap(cyc=1000))),
    ("readback disagrees with write", build(cfg_readback=0)),
    ("inference rc nonzero", build(rc=5)),
    ("required flags missing", build(flags=0x01)),
    ("wrong build_id", build(build_id=0x11111111)),
    ("PDN1 build_id posing as B", build(build_id=0x314E4450)),
]
for name, payload in failing:
    ok, _ = rp.pmu_diag_b_proof(rp.parse_pmu_diag_payload(payload))
    check("B proof fails: %s" % name, not ok)

print("=== verdict table (observed values only) ===")
res_a = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
res_c = rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
res_b = rp.parse_pmu_diag_payload(build())

v, _ = rp.pmu_diag_verdict(res_a, res_b, res_c)
check("root-cause row", v.startswith("cfg-missing-root-cause"), v)

res_b_cfglost = rp.parse_pmu_diag_payload(build(post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_cfglost, res_c)
check("cfg lost in call", v.startswith("cfg-lost-in-call"), v)

res_b_armlost = rp.parse_pmu_diag_payload(build(post=snap(cnten=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_armlost, res_c)
check("arm lost in call", v.startswith("arm-lost-in-call"), v)

res_b_globlost = rp.parse_pmu_diag_payload(build(post=snap(pmcr=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_globlost, res_c)
check("global enable lost", v.startswith("global-enable-lost"), v)

res_b_held = rp.parse_pmu_diag_payload(build(post=snap(cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_held, res_c)
check("all held, no progress", v.startswith("b-no-progress-all-held"), v)

# A moved but C did not -> the explicit zero write has a separate effect.
res_a_moved = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=77)))
v, _ = rp.pmu_diag_verdict(res_a_moved, res_b, res_c)
check("A and C differ", v.startswith("A-and-C-differ"), v)

res_a_bad = rp.parse_pmu_diag_payload(build(
    diag_case=1, pre=snap(cfg=0), post=snap(cfg=0, cyc=0, stable=0)))
v, _ = rp.pmu_diag_verdict(res_a_bad, res_b, res_c)
check("unstable sample invalidates the row", v.startswith("invalid-sample"), v)

# Identity gate: a negative-control record can never feed the table.
res_b_nc = rp.parse_pmu_diag_payload(build(nc=1, cfg_written=0, cfg_value=0,
                                           cfg_readback=0, pre=snap(cfg=0),
                                           post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_nc, res_c)
check("nc build invalidates the row", v.startswith("invalid-sample"), v)

# Golden gate: a drifted EXACT WINDOW invalidates the whole row.
res_c_drift = rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=0,
    gw_crc=0xBAD, pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b, res_c_drift)
check("golden window drift invalidates the row", v.startswith("invalid-sample"), v)

# Wrong start-sequence identity invalidates the row before interpretation.
res_b_badseq = rp.parse_pmu_diag_payload(build(sequence_id=0))
v, _ = rp.pmu_diag_verdict(res_a, res_b_badseq, res_c)
check("wrong start sequence invalidates the row", v.startswith("invalid-sample"), v)

# Cross-case output drift invalidates; whole-region drift does not.
res_b_outdrift = rp.parse_pmu_diag_payload(build(output_crc=0x9999))
v, _ = rp.pmu_diag_verdict(res_a, res_b_outdrift, res_c)
check("output_crc disagreement across cases invalidates",
      v.startswith("invalid-sample"), v)

# Whole-region CRCs differing across all three cases must NOT invalidate as
# long as every exact window is golden -- the boot1/2 lesson, codified.
res_a_r = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    build_id=rp.PMU_DIAG_BUILD_IDS["A"], region_crc=0xA1A1A1A1,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
res_b_r = rp.parse_pmu_diag_payload(build(region_crc=0xB2B2B2B2))
res_c_r = rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=0,
    build_id=rp.PMU_DIAG_BUILD_IDS["C"], region_crc=0xC3C3C3C3,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a_r, res_b_r, res_c_r)
check("differing region CRCs alone do not invalidate (window golden)",
      v.startswith("cfg-missing-root-cause"), v)

# Actual v6 shape: both zero-config context rows progress too. This disproves
# the CFG-missing hypothesis; combined with v5 failing before inference under
# CMD=0xC, it localizes the historical zero to the NPU power lifecycle.
res_a_progress = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    build_id=rp.PMU_DIAG_BUILD_IDS["A"],
    pre=snap(cfg=0, cyc=100), post=snap(cfg=0, cyc=200)))
res_c_progress = rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=0,
    build_id=rp.PMU_DIAG_BUILD_IDS["C"],
    pre=snap(cfg=0, cyc=100), post=snap(cfg=0, cyc=200)))
v, _ = rp.pmu_diag_verdict(res_a_progress, res_b, res_c_progress)
check("all A/B/C progress -> CFG is not required",
      v.startswith("cfg-not-required"), v)

print("=== old schema rejection ===")
v1_body = [1, rp.PMU_DIAG_BUILD_IDS["B"], 2, 0, 7, 1, CFG_B, CFG_B, 0, 0x1F,
           0x1111, 0x2222, 0xAAAA, 1, 100, 200, 300, 0, 20, 8]
v1_body += list(snap()) + list(snap(cyc=1000)) + list(snap(pmcr=0, cyc=1000))
v1_total = rp.PMU_DIAG_HEADER_WORDS + len(v1_body)
v1_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 1, v1_total,
                      rp.PMU_DIAG_HEADER_WORDS, 7, 0x1F, 0, 0)
v1 = bytearray(v1_head + b"".join(struct.pack("<I", w) for w in v1_body))
struct.pack_into("<I", v1, 28,
                 zlib.crc32(bytes(v1[16:28]) + bytes(v1[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v1))
    check("v1 payload rejected (boot1/2 evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v1 payload rejected (boot1/2 evidence quarantined)",
          "schema version 1" in str(exc))

# v2 boot3 is also quarantined: reset bits read clear, then arm/global were
# wiped before the pre snapshot, proving the settle-poll evidence was invalid.
v2_body = [2, rp.PMU_DIAG_BUILD_IDS["A"], 1, 0, 1, 0, 0, 0, 0, 0x0F,
           0x1111, 0x432CD283, 0x4CEEFCE7, 1, 100, 200, 300, 0, 28, 8,
           1, 1, 0x4000, 1, GW_BASE, GW_LEN, GOLDEN_W]
v2_body += list(snap(pmcr=0x4000, cnten=0, cfg=0)) * 3
v2_total = rp.PMU_DIAG_HEADER_WORDS + len(v2_body)
v2_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 2, v2_total,
                      rp.PMU_DIAG_HEADER_WORDS, 1, 0x0F, 0, 0)
v2 = bytearray(v2_head + b"".join(struct.pack("<I", w) for w in v2_body))
struct.pack_into("<I", v2, 28,
                 zlib.crc32(bytes(v2[16:28]) + bytes(v2[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v2))
    check("v2 payload rejected (boot3 evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v2 payload rejected (boot3 evidence quarantined)",
          "schema version 2" in str(exc))

# v3 boot4 isolated the final reset pulse: CNT_EN survived but the cycle arm
# was cleared immediately. v4 added an immediate re-arm, which boot5 showed
# could still precede the asynchronous reset effect.
v3_body = [3, rp.PMU_DIAG_BUILD_IDS["A"], 1, 0, 1, 0, 0, 0, 0, 0x0F,
           0x1111, 0x432CD283, 0x76211A0D, 1, 100, 200, 300, 0, 30, 10,
           1, 0x4001, 1, 0x4001, 0, GW_BASE, GW_LEN, GOLDEN_W]
v3_body += list(snap(pmcr=0x4000, cnten=0, cfg=0)) * 3
v3_total = rp.PMU_DIAG_HEADER_WORDS + len(v3_body)
v3_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 3, v3_total,
                      rp.PMU_DIAG_HEADER_WORDS, 1, 0x0F, 0, 0)
v3 = bytearray(v3_head + b"".join(struct.pack("<I", w) for w in v3_body))
struct.pack_into("<I", v3, 28,
                 zlib.crc32(bytes(v3[16:28]) + bytes(v3[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v3))
    check("v3 payload rejected (boot4 evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v3 payload rejected (boot4 evidence quarantined)",
          "schema version 3" in str(exc))

# v4 boot5 read back the re-arm immediately, then lost both CNT_EN and arm
# before the pre snapshot. It is the direct reason v5 guards before final
# programming and requires spaced persistence observations.
v4_body = [4, rp.PMU_DIAG_BUILD_IDS["A"], 1, 0, 1, 0, 0, 0, 0, 0x0F,
           0x1111, 0x432CD283, 0x76211A0D, 1, 100, 200, 300, 0, 34, 12,
           2, 0x4001, 1, 0x4001, 0, 1, GW_BASE, GW_LEN, GOLDEN_W]
v4_body += list(snap(pmcr=0x4000, cnten=0, cfg=0)) * 3
v4_total = rp.PMU_DIAG_HEADER_WORDS + len(v4_body)
v4_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 4, v4_total,
                      rp.PMU_DIAG_HEADER_WORDS, 1, 0x0F, 0, 0)
v4 = bytearray(v4_head + b"".join(struct.pack("<I", w) for w in v4_body))
struct.pack_into("<I", v4, 28,
                 zlib.crc32(bytes(v4[16:28]) + bytes(v4[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v4))
    check("v4 payload rejected (boot5 evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v4 payload rejected (boot5 evidence quarantined)",
          "schema version 4" in str(exc))

# v5 boot6 guarded reset for 65,536 cycles, but it programmed the PMU while
# the selftest driver still requested clock/power shutdown. Immediate reads
# passed and the very first spaced stability observation failed.
v5_body = [5, rp.PMU_DIAG_BUILD_IDS["A"], 1, 0, 1, 0, 0, 0, 0, 0x0F,
           0x783388D1, 0x432CD283, 0x4CEEFCE7, 1, 100, 200, 300, 0, 28, 8,
           3, 65536, 0x4000, 0x4001, 1, 1, 0,
           GW_BASE, GW_LEN, GOLDEN_W]
v5_body += list(snap(pmcr=0x4000, cnten=0, cfg=0)) * 3
v5_total = rp.PMU_DIAG_HEADER_WORDS + len(v5_body)
v5_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 5, v5_total,
                      rp.PMU_DIAG_HEADER_WORDS, 1, 0x0F, 0, 0)
v5 = bytearray(v5_head + b"".join(struct.pack("<I", w) for w in v5_body))
struct.pack_into("<I", v5, 28,
                 zlib.crc32(bytes(v5[16:28]) + bytes(v5[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v5))
    check("v5 payload rejected (boot6 evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v5 payload rejected (boot6 evidence quarantined)",
          "schema version 5" in str(exc))

# Progress without the FULL B proof must stay inconclusive, never root-cause.
res_b_readback_bad = rp.parse_pmu_diag_payload(build(cfg_readback=0))
v, _ = rp.pmu_diag_verdict(res_a, res_b_readback_bad, res_c)
check("progress without full B proof is inconclusive",
      v.startswith("inconclusive"), v)

print("=== context-row and precondition gates ===")
# A/C must hold arm+global to be comparison rows at all.
res_a_noarm = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0, cnten=0), post=snap(cfg=0, cnten=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a_noarm, res_b, res_c)
check("A without arm is invalid", v.startswith("invalid-sample"), v)

res_a_noglob = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0, pmcr=0), post=snap(cfg=0, pmcr=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a_noglob, res_b, res_c)
check("A without global enable is invalid", v.startswith("invalid-sample"), v)

# A that WROTE cfg violates the A contract even if everything else is clean.
res_a_wrote = rp.parse_pmu_diag_payload(build(
    diag_case=1, cfg_written=1, cfg_value=0, cfg_readback=0,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a_wrote, res_b, res_c)
check("A with a cfg write is invalid", v.startswith("invalid-sample"), v)

# C whose write/readback path failed is not a zero-write control.
res_c_badpath = rp.parse_pmu_diag_payload(build(
    diag_case=3, cfg_written=1, cfg_value=0, cfg_readback=5,
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b, res_c_badpath)
check("C with a broken write path is invalid", v.startswith("invalid-sample"), v)

# B whose PREconditions never held is a programming failure, never
# "all held" and never an in-call loss.
res_b_nopre_cfg = rp.parse_pmu_diag_payload(build(
    pre=snap(cfg=0), post=snap(cfg=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_nopre_cfg, res_c)
check("B pre-CFG never held -> precondition verdict",
      v.startswith("b-precondition-not-established"), v)

res_b_nopre_arm = rp.parse_pmu_diag_payload(build(
    pre=snap(cnten=0), post=snap(cnten=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_nopre_arm, res_c)
check("B pre-arm never held -> precondition verdict",
      v.startswith("b-precondition-not-established"), v)

res_b_nopre_glob = rp.parse_pmu_diag_payload(build(
    pre=snap(pmcr=0), post=snap(pmcr=0, cyc=0)))
v, _ = rp.pmu_diag_verdict(res_a, res_b_nopre_glob, res_c)
check("B pre-global never held -> precondition verdict",
      v.startswith("b-precondition-not-established"), v)

print("=== link freshness (no serial port needed) ===")


def make_link(frames):
    """A RunnerLink shell without opening a port: __new__ skips __init__ and
    the transport methods are replaced with a scripted frame source."""
    link = rp.RunnerLink.__new__(rp.RunnerLink)
    link.late_frames = 0
    link._seq = 100
    link.send_raw = lambda blob: None
    queue = list(frames)

    def read_frame(timeout=5.0):
        if not queue:
            raise rp.ProtocolError("script exhausted")
        return queue.pop(0)

    link.read_frame = read_frame
    return link


good = build(seq=7)
stale = build(seq=6, header_seq=None)
ACK = rp.CMD_RUN_PMU_DIAG | 0x80

# A stale COMPLETE from an earlier exchange (outer sequence 100 vs 101) must
# be dropped as a late frame, and the matching one adopted.
link = make_link([
    rp.Frame(1, ACK, 0, 101, b"\x00" * 4),
    rp.Frame(1, rp.CMD_PMU_DIAG_COMPLETE, 0, 100, stale),
    rp.Frame(1, rp.CMD_PMU_DIAG_COMPLETE, 0, 101, good),
])
res = link.run_pmu_diag(timeout=5.0)
check("stale COMPLETE dropped, fresh one adopted", res.run_sequence == 7)
check("stale COMPLETE counted as late", link.late_frames == 1)
check("raw evidence is the fresh payload", link.last_pmu_diag_raw == good)

# A run that never completes must not leave previous raw evidence behind.
link = make_link([
    rp.Frame(1, ACK, 0, 101, b"\x00" * 4),
])
link.last_pmu_diag_raw = b"previous-run-bytes"
link.last_pmu_diag_reread_raw = b"previous-reread-bytes"
try:
    link.run_pmu_diag(timeout=1.0)
    check("incomplete run raises", False)
except rp.RunSequenceError:
    check("incomplete run raises", True)
check("previous raw evidence cleared on failure", link.last_pmu_diag_raw is None)
check("previous reread evidence cleared on failure",
      link.last_pmu_diag_reread_raw is None)

# A COMPLETE that arrives before any ACK is a protocol violation, not data.
link = make_link([
    rp.Frame(1, rp.CMD_PMU_DIAG_COMPLETE, 0, 101, good),
])
try:
    link.run_pmu_diag(timeout=1.0)
    check("COMPLETE before ACK rejected", False)
except rp.RunSequenceError:
    check("COMPLETE before ACK rejected", True)

print("=== analyzer loader gates (temp JSON files) ===")
import hashlib
import json
import tempfile

import analyze_pmu_diag as az


def write_doc(tmpdir, name, raw, case="B", boot=2, seam=None,
              raw_overrides=None):
    doc = {
        "host": {
            "host_boot_index": boot,
            "deployed_case": case,
            "app_bin_sha256": "a" * 64,
            "vectors_bin_sha256": "b" * 64,
            "ddr_bin_sha256": "c" * 64,
        },
        "raw": {
            "payload_hex": raw.hex(),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "reread_matches_run_payload": True,
        },
    }
    if seam is not None:
        doc["host"]["deployed_seam"] = seam
    if raw_overrides:
        for k, v in raw_overrides.items():
            if v is None:
                doc["raw"].pop(k, None)
            else:
                doc["raw"][k] = v
    path = os.path.join(tmpdir, name)
    with open(path, "w") as f:
        json.dump(doc, f)
    return path


with tempfile.TemporaryDirectory() as td:
    good_raw = build()
    res_ok, host_ok = az.load(write_doc(td, "ok.json", good_raw), "B")
    check("analyzer accepts a clean B file", res_ok.diag_case == 2)

    try:
        az.load(write_doc(td, "wrongid.json", build(build_id=0x11111111)), "B")
        check("analyzer rejects build_id mismatch", False)
    except SystemExit:
        check("analyzer rejects build_id mismatch", True)

    # An A-case file must carry the PDGA id, not PDGB.
    a_raw = build(diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
                  pre=snap(cfg=0), post=snap(cfg=0, cyc=0))
    try:
        az.load(write_doc(td, "a_pdgb.json", a_raw, case="A", boot=1), "A")
        check("analyzer rejects A file carrying the PDGB id", False)
    except SystemExit:
        check("analyzer rejects A file carrying the PDGB id", True)
    a_raw_ok = build(diag_case=1, cfg_written=0, cfg_value=0, cfg_readback=0,
                     build_id=rp.PMU_DIAG_BUILD_IDS["A"],
                     pre=snap(cfg=0), post=snap(cfg=0, cyc=0))
    res_a_ok, _ = az.load(write_doc(td, "a_ok.json", a_raw_ok, case="A", boot=1), "A")
    check("analyzer accepts a clean A file", res_a_ok.diag_case == 1)

    try:
        az.load(write_doc(td, "noflag.json", good_raw,
                          raw_overrides={"reread_matches_run_payload": None}), "B")
        check("analyzer rejects missing reread flag", False)
    except SystemExit:
        check("analyzer rejects missing reread flag", True)

    try:
        az.load(write_doc(td, "flagfalse.json", good_raw,
                          raw_overrides={"reread_matches_run_payload": False}), "B")
        check("analyzer rejects reread flag == false", False)
    except SystemExit:
        check("analyzer rejects reread flag == false", True)

print("=== v7 power seam (S1/S2/S3) ===")


def seam_build(seam, **kw):
    """A seam row. All three carry the SAME case-B cycle config on purpose --
    power_seam_id is the only variable in this experiment."""
    d = dict(build_id=rp.PMU_DIAG_SEAM_BUILD_IDS[seam],
             seam_id=rp.PMU_DIAG_SEAM_IDS[seam],
             diag_case=2, cfg_written=1, cfg_value=CFG_B, cfg_readback=CFG_B)
    # Every seam ends with the board back in its terminal state (0xC): S2/S3
    # restore it with a runner write, S1 only reads back the driver's own.
    # The AFTER-SEAM read is what distinguishes them at runtime: S1 must
    # already show the vendor release, S2/S3 must still be holding power.
    if seam == "S2":
        d.update(rehold_performed=1,
                 rehold_guard=rp.PMU_DIAG_REHOLD_GUARD_CYCLES,
                 cmd_after_release=0xC, cmd_after_seam=0, status_after_seam=0)
    elif seam == "S1":
        d.update(rehold_performed=0, rehold_guard=0,
                 cmd_after_release=0xC, cmd_after_seam=0xC, status_after_seam=0)
    else:
        d.update(rehold_performed=0, rehold_guard=0,
                 cmd_after_release=0xC, cmd_after_seam=0, status_after_seam=0)
    d.update(kw)
    return build(**d)


with tempfile.TemporaryDirectory() as td:
    for index, seam in enumerate(("S1", "S2", "S3"), start=10):
        res, _ = az.load_seam(
            write_doc(td, "%s.json" % seam, seam_build(seam), boot=index,
                      seam=seam),
            seam)
        check("analyzer accepts %s seam build id" % seam,
              res.build_id == rp.PMU_DIAG_SEAM_BUILD_IDS[seam])

    try:
        az.load_seam(
            write_doc(td, "s1_wrong_build.json",
                      seam_build("S1", build_id=rp.PMU_DIAG_SEAM_BUILD_IDS["S2"]),
                      boot=13, seam="S1"),
            "S1")
        check("analyzer rejects another seam's build id", False)
    except SystemExit:
        check("analyzer rejects another seam's build id", True)


# A post snapshot in which the power transition took the PMU with it.
WIPED = snap(pmcr=0, cnten=0, cfg=0, cyc=0)

for seam in ("S1", "S2", "S3"):
    res = rp.parse_pmu_diag_payload(seam_build(seam))
    ok, checks = rp.pmu_diag_seam_row_ok(res, seam)
    check("%s row valid" % seam, ok,
          str([k for k, v in checks.items() if not v]))
    check("%s post held" % seam, rp.pmu_diag_seam_post_held(res))

# Parser-level seam invariants.
for name, kw in (("seam id 0 rejected", dict(seam_id=0)),
                 ("seam id 4 rejected", dict(seam_id=4))):
    try:
        rp.parse_pmu_diag_payload(build(**kw))
        check(name, False)
    except rp.ProtocolError:
        check(name, True)
for name, kw in (
        ("S1 claiming a re-hold rejected",
         dict(seam_id=1, rehold_performed=1)),
        ("S2 without a re-hold rejected",
         dict(seam_id=2, rehold_performed=0)),
        ("S3 claiming a re-hold rejected",
         dict(seam_id=3, rehold_performed=1))):
    try:
        rp.parse_pmu_diag_payload(build(**kw))
        check(name, False)
    except rp.ProtocolError:
        check(name, True)

# Row-level identity and contract gates.
seam_failing = [
    ("build id from another seam", "S1",
     seam_build("S1", build_id=rp.PMU_DIAG_SEAM_BUILD_IDS["S2"])),
    ("negative-control build", "S3", seam_build("S3", nc=4)),
    # Who WRITES the release is a static-gate question; what every seam must
    # show at the record level is that the terminal state came back.
    ("S1 left the board un-released", "S1",
     seam_build("S1", cmd_after_release=0)),
    ("S2 left the board un-released", "S2",
     seam_build("S2", cmd_after_release=0)),
    ("S3 left the board un-released", "S3",
     seam_build("S3", cmd_after_release=0)),
    ("S2 with the wrong re-hold guard", "S2",
     seam_build("S2", rehold_guard=1024)),
    # Pre-inference state read from the PRE SNAPSHOT, not from the
    # post-programming fields: a loss between programming and the inference
    # must not be blamed on the terminal release.
    ("pre snapshot not armed", "S3", seam_build("S3", pre=snap(cnten=0)),
     "pre_armed"),
    ("pre snapshot not globally enabled", "S3",
     seam_build("S3", pre=snap(pmcr=0)), "pre_global_enable"),
    ("pre snapshot cfg does not match the write", "S3",
     seam_build("S3", pre=snap(cfg=0)), "cfg_programmed_pre"),
    # Runtime seam telemetry: the record must show the seam it claims.
    ("S1 still holding power after the seam", "S1",
     seam_build("S1", cmd_after_seam=0), "seam_runtime_cmd_ok"),
    ("S2 released power at the seam", "S2",
     seam_build("S2", cmd_after_seam=0xC), "seam_runtime_cmd_ok"),
    ("S3 released power at the seam", "S3",
     seam_build("S3", cmd_after_seam=0xC), "seam_runtime_cmd_ok"),
    ("S2 status reset bit set after the seam", "S2",
     seam_build("S2", status_after_seam=0x8), "seam_runtime_status_ok"),
    ("S3 status reset bit set after the seam", "S3",
     seam_build("S3", status_after_seam=0x8), "seam_runtime_status_ok"),
    ("wrong golden window", "S3", seam_build("S3", gw_crc=0xDEAD)),
    ("inference rc nonzero", "S3", seam_build("S3", rc=5)),
    ("unstable read", "S3", seam_build("S3", post=snap(cyc=1000, stable=0))),
    ("overflow", "S3", seam_build("S3", post=snap(cyc=1000, ovs=OVF))),
]
for entry in seam_failing:
    name, seam, payload = entry[0], entry[1], entry[2]
    want = entry[3] if len(entry) > 3 else None
    ok, checks = rp.pmu_diag_seam_row_ok(rp.parse_pmu_diag_payload(payload),
                                         seam)
    failed_checks = [k for k, v in checks.items() if not v]
    if want is None:
        check("seam row rejects: %s" % name, not ok, str(failed_checks))
    else:
        # Naming the exact check keeps the gate diagnostic: a row that fails
        # for an unrelated reason would otherwise look like proof.
        check("seam row rejects: %s" % name, failed_checks == [want],
              str(failed_checks))

# A row whose seam id disagrees with the seam it is presented as.
ok, _ = rp.pmu_diag_seam_row_ok(rp.parse_pmu_diag_payload(seam_build("S1")), "S2")
check("seam row rejects: S1 record presented as S2", not ok)

# S1 is sampled mid-transition, so its status bit carries no settled meaning
# and must NOT gate the row -- otherwise a legitimate S1 looks broken.
ok, checks = rp.pmu_diag_seam_row_ok(
    rp.parse_pmu_diag_payload(seam_build("S1", status_after_seam=0x8)), "S1")
check("S1 after-seam status is deliberately not gated", ok,
      str([k for k, v in checks.items() if not v]))

print("=== v7 seam verdict table ===")
s1_ok = rp.parse_pmu_diag_payload(seam_build("S1"))
s2_ok = rp.parse_pmu_diag_payload(seam_build("S2"))
s3_ok = rp.parse_pmu_diag_payload(seam_build("S3"))
s1_lost = rp.parse_pmu_diag_payload(seam_build("S1", post=WIPED))
s2_lost = rp.parse_pmu_diag_payload(seam_build("S2", post=WIPED))
s3_lost = rp.parse_pmu_diag_payload(seam_build("S3", post=WIPED))

for seam, lost in (("S1", s1_lost), ("S2", s2_lost), ("S3", s3_lost)):
    cls = rp.classify_pmu_diag(lost)
    check("%s reset-to-zero is not progress" % seam,
          cls["progress_observed"] is False)
    check("%s reset-to-zero has no usable diagnostic delta" % seam,
          cls["usable_diagnostic_delta"] is None)

v, _ = rp.pmu_diag_seam_verdict(s1_ok, s2_ok, s3_ok)
check("S1+S2 hold -> terminal release harmless",
      v.startswith("terminal-release-harmless"), v)

v, _ = rp.pmu_diag_seam_verdict(s1_lost, s2_ok, s3_ok)
check("S1 lost, S2 recovered -> viable-for-repeat only",
      v.startswith("rehold workaround viable-for-repeat"), v)
check("that verdict refuses to say production GO",
      "NOT a production GO" in v)

v, _ = rp.pmu_diag_seam_verdict(s1_lost, s2_lost, s3_ok)
check("S1 and S2 lost -> internal pre-release seam required",
      v.startswith("internal-pre-release-seam-required"), v)

v, _ = rp.pmu_diag_seam_verdict(s1_ok, s2_lost, s3_ok)
check("S1 held but S2 lost -> inconclusive", v.startswith("inconclusive"), v)

v, _ = rp.pmu_diag_seam_verdict(s1_lost, s2_ok, s3_lost)
check("control failure blocks interpretation",
      v.startswith("control-failed"), v)

v, _ = rp.pmu_diag_seam_verdict(s1_ok, s2_ok,
                                rp.parse_pmu_diag_payload(seam_build("S3", rc=9)))
check("invalid row blocks the table", v.startswith("invalid-sample"), v)

# Cross-seam drift corroboration: every row can pass its own exact golden
# window and still not be comparable if the inferences differed.
s2_drift = rp.parse_pmu_diag_payload(seam_build("S2", output_crc=0x9999))
ok, _ = rp.pmu_diag_seam_row_ok(s2_drift, "S2")
check("output_crc drift leaves the individual row valid", ok)
v, _ = rp.pmu_diag_seam_verdict(s1_ok, s2_drift, s3_ok)
check("cross-seam output_crc mismatch blocks the table",
      v.startswith("invalid-sample") and "output_crc disagrees" in v, v)

print("=== old schema rejection (v6) ===")
v6_body = [6, rp.PMU_DIAG_SEAM_BUILD_IDS["S3"], 2, 0, 7, 1, CFG_B, CFG_B, 0,
           0x1F, 0x1111, 0x2222, 0xAAAA, 1, 100, 200, 300, 0, 20, 8,
           4, 65536, 0xC, 0, 0, 65536, 0x4000, 0x4001, 1, 8, 1, 0xC,
           GW_BASE, GW_LEN, GOLDEN_W]
v6_body += list(snap()) + list(snap(cyc=1000)) + list(snap(pmcr=0, cyc=1000))
v6_total = rp.PMU_DIAG_HEADER_WORDS + len(v6_body)
v6_head = struct.pack("<8I", rp.PMU_DIAG_MAGIC, 6, v6_total,
                      rp.PMU_DIAG_HEADER_WORDS, 7, 0x1F, 0, 0)
v6 = bytearray(v6_head + b"".join(struct.pack("<I", w) for w in v6_body))
struct.pack_into("<I", v6, 28,
                 zlib.crc32(bytes(v6[16:28]) + bytes(v6[32:])) & 0xFFFFFFFF)
try:
    rp.parse_pmu_diag_payload(bytes(v6))
    check("v6 payload rejected (pre-seam evidence quarantined)", False)
except rp.ProtocolError as exc:
    check("v6 payload rejected (pre-seam evidence quarantined)",
          "schema version 6" in str(exc))

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
