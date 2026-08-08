"""Milestone 1 board gates for FI101_RUNNER_V1_PMU_CANDIDATE (clean image).

OFF is not "cycles came back 0". It is: the RUN path made zero PMU MMIO
accesses, every PMU validity flag is clear, and the existing functional
guarantees are unchanged. END_ONLY asserts the mirror image, plus a cycle
value that is valid and non-zero.

The cycle number is npu_pmu_window_cycles throughout. It is not T_npu.
"""

import os
import sys
import zlib

import runner_proto as rp
from runner_proto import (INSTRUMENTATION_OFF, INSTRUMENTATION_END_ONLY,
                          COMPLETION_WAIT_MODE_BUSY_POLL, Nack, RunnerLink)

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
RESULT_BASE = int(os.environ.get("RESULT_BASE", "0x90020cc0"), 16)
RESULT_LEN = int(os.environ.get("RESULT_LEN", "0x100"), 16)
GOLDEN = 0x27084C4C

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print("  %-4s %-46s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    if ok:
        passed += 1
    else:
        failed += 1


def prime(link):
    link.reset_runner()
    blob = b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")


def do_run(link, mode):
    """RESET -> set mode -> load -> RUN.

    Order is forced by two contracts working together: RESET_RUNNER returns the
    mode to OFF (deliberately, so nothing is inherited), and the mode may only
    be set in IDLE. So the mode is set immediately after the reset and the load
    sequence must NOT reset again -- which is why this does not call prime().
    """
    link.reset_runner()
    link.set_instrumentation_mode(mode)
    blob = b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")
    rc = link.run()
    m = link.last_measurement
    _, _, _, crc = link.get_result(RESULT_BASE, RESULT_LEN,
                                   run_sequence=m.run_sequence)
    return rc, m, crc


link = RunnerLink(PORT, protocol=rp.PROTO_MEASURE_V2)

print("=== capabilities: what the device actually reports ===", flush=True)
st = link.ping()
check("runner answers PING", st.state == 1, "state=%d" % st.state)

print("\n=== OFF: zero PMU MMIO on the RUN path ===", flush=True)
rc, m, crc = do_run(link, INSTRUMENTATION_OFF)
p = m.pmu
if p is None:
    check("PMU block present in the ABI", False, "pmu is None -- wrong image?")
    print("\n### not the PMU candidate image. Stopping. ###")
    link.close()
    sys.exit(1)
check("PMU block present in the ABI", True, "trailing=%d" % m.trailing_words)
check("requested/applied both OFF",
      p["instrumentation_mode_requested"] == INSTRUMENTATION_OFF
      and p["instrumentation_mode_applied"] == INSTRUMENTATION_OFF)
check("PMU MMIO read delta == 0", p["pmu_mmio_read_count_delta"] == 0,
      "delta=%d total=%d" % (p["pmu_mmio_read_count_delta"],
                             p["pmu_mmio_read_count_total"]))
check("PMU MMIO write delta == 0", p["pmu_mmio_write_count_delta"] == 0,
      "delta=%d total=%d" % (p["pmu_mmio_write_count_delta"],
                             p["pmu_mmio_write_count_total"]))
check("every PMU validity flag clear",
      p["pmu_sample_valid"] == 0 and p["npu_pmu_cycle_valid"] == 0
      and p["npu_pmu_cycle_overflow"] == 0 and p["event_valid_mask"] == 0
      and p["event_overflow_mask"] == 0)
check("window cycles absent, not zero",
      p["npu_pmu_window_cycles"] is None and p["npu_pmu_window_cycles_raw"] == 0)
check("functional non-regression: golden CRC", crc == GOLDEN, "0x%08X" % crc)
check("RUN rc == 0", rc == 0, "rc=%d" % rc)

print("\n=== OFF repeated, and OFF after END_ONLY ===", flush=True)
_, m2, crc2 = do_run(link, INSTRUMENTATION_OFF)
check("OFF -> OFF still zero delta",
      m2.pmu["pmu_mmio_read_count_delta"] == 0
      and m2.pmu["pmu_mmio_write_count_delta"] == 0 and crc2 == GOLDEN)

print("\n=== END_ONLY: cycle-only ===", flush=True)
rc, me, crce = do_run(link, INSTRUMENTATION_END_ONLY)
q = me.pmu
check("applied mode is END_ONLY",
      q["instrumentation_mode_applied"] == INSTRUMENTATION_END_ONLY)
check("PMU was probed", q["pmu_probe_performed"] == 1)
check("hardware counter count reported",
      q["hw_event_counter_count"] > 0,
      "hw=%d abi=%d effective=%d (header claims %d)"
      % (q["hw_event_counter_count"], q["abi_event_slot_count"],
         q["effective_event_slot_count"], q["expected_hw_event_counter_count"]))
check("MMIO deltas non-zero",
      q["pmu_mmio_read_count_delta"] > 0 and q["pmu_mmio_write_count_delta"] > 0,
      "r=%d w=%d" % (q["pmu_mmio_read_count_delta"],
                     q["pmu_mmio_write_count_delta"]))
check("PMCR enable bit cleared at disable",
      (q["pmcr_at_disable"] & 0x1) == 0, "PMCR=0x%08X" % q["pmcr_at_disable"])
check("cycle counter ARMED (PMCNTENSET readback)", q["cycle_counter_armed"] == 1)
check("global enable VERIFIED (PMCR readback)",
      q["cycle_global_enable_verified"] == 1)
check("stable read, progress observed, no overflow",
      q["cycle_read_stable"] == 1 and q["cycle_progress_observed"] == 1
      and q["npu_pmu_cycle_overflow"] == 0,
      "retries=%d" % q["npu_pmu_cycle_read_retry_count"])
check("sample valid and cycle valid",
      q["pmu_sample_valid"] == 1 and q["npu_pmu_cycle_valid"] == 1)
wc = q["npu_pmu_window_cycles"]
check("npu_pmu_window_cycles > 0 and < 2^48",
      wc is not None and 0 < wc < (1 << 48), "%s" % wc)
check("bits above 48 are zero", (q["npu_pmu_window_cycles_hi"] >> 16) == 0,
      "hi=0x%08X" % q["npu_pmu_window_cycles_hi"])
check("no event slots armed",
      q["event_valid_mask"] == 0 and q["event_overflow_mask"] == 0
      and q["applied_event_count"] == 0)
check("completion wait mode is BUSY_POLL",
      q["completion_wait_mode"] == COMPLETION_WAIT_MODE_BUSY_POLL)
check("golden CRC unchanged by PMU", crce == GOLDEN, "0x%08X" % crce)

print("\n=== END_ONLY x10: consistency, not accuracy ===", flush=True)
cycles, deltas, crcs, bad = [], set(), set(), []
for i in range(10):
    rc, mm, cc = do_run(link, INSTRUMENTATION_END_ONLY)
    d = mm.pmu
    cycles.append(d["npu_pmu_window_cycles"])
    deltas.add((d["pmu_mmio_read_count_delta"], d["pmu_mmio_write_count_delta"]))
    crcs.add(cc)
    if not (d["npu_pmu_cycle_valid"] == 1 and d["npu_pmu_cycle_overflow"] == 0
            and d["cycle_counter_armed"] == 1
            and d["cycle_global_enable_verified"] == 1
            and d["cycle_progress_observed"] == 1
            and cc == GOLDEN and rc == 0):
        bad.append(i + 1)
    print("    run %2d: window_cycles=%-12s valid=%d ovf=%d crc=0x%08X r/w=%d/%d"
          % (i + 1, d["npu_pmu_window_cycles"], d["npu_pmu_cycle_valid"],
             d["npu_pmu_cycle_overflow"], cc,
             d["pmu_mmio_read_count_delta"], d["pmu_mmio_write_count_delta"]),
          flush=True)
check("10/10 valid, no overflow, golden CRC", not bad, "bad=%r" % bad)
check("MMIO access count identical every run", len(deltas) == 1, "%r" % deltas)
if all(c is not None for c in cycles):
    srt = sorted(cycles)
    check("window_cycles min/median/max recorded", True,
          "%d / %d / %d" % (srt[0], srt[len(srt) // 2], srt[-1]))

print("\n=== configuration command: negative tests ===", flush=True)
link.reset_runner()
for name, args, expect in (
        ("PER_LAYER rejected", (2,), rp.ERR_UNSUPPORTED),
        ("unknown mode rejected", (99,), rp.ERR_UNSUPPORTED),
        ("END_ONLY + 1 event rejected (milestone 1)",
         (INSTRUMENTATION_END_ONLY, (0x10,)), rp.ERR_UNSUPPORTED)):
    try:
        link.set_instrumentation_mode(*args)
        check(name, False, "accepted")
    except Nack as e:
        check(name, e.code == expect, "code=0x%04X" % e.code)

st = link.ping()
check("a rejected request left the state alone", st.state == 1, "state=%d" % st.state)

print("\n=== RESET_RUNNER returns to the defined default ===", flush=True)
link.reset_runner()
link.set_instrumentation_mode(INSTRUMENTATION_END_ONLY)
link.reset_runner()          # must wipe the END_ONLY setting
rc, mr, crcr = do_run(link, INSTRUMENTATION_OFF)
check("after RESET the mode default is OFF, no PMU access",
      mr.pmu["instrumentation_mode_applied"] == INSTRUMENTATION_OFF
      and mr.pmu["pmu_mmio_read_count_delta"] == 0
      and mr.pmu["pmu_mmio_write_count_delta"] == 0 and crcr == GOLDEN)

print("\n=== SUMMARY ===", flush=True)
print("passed: %d   failed: %d" % (passed, failed), flush=True)
link.close()
sys.exit(1 if failed else 0)
