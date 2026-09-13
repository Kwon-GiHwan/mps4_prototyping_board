"""S4 -- U85 stall counters via the core-driver patch (plan 2026-09-14 section 11).

Runs on the build server inside benchmark-runner AFTER the X4 sweep has finished (the patch
touches the shared MLEK tree, so no other build may run concurrently). Applies the driver patch,
builds each frozen cell with the stock cmake command (no -D overrides), runs REPS times, keeps
the raw UART, records the four extra counters, and reverts the patch in a finally block.

Usage:  python3 s4_stall_counters.py
Needs:  /tmp/s4/expected.json  {cell_id: {npu_total_cycles, npu_active_cycles, sram_rd_beats, ...}}
Output: /tmp/s4/results.jsonl, /tmp/s4/uart/<cell>__R<n>.txt
"""
import json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, "/tmp/xqbin"); sys.path.insert(0, "/tmp/x4")
import stage1                      # noqa: E402
from x4_ta_sweep import build_with_ta, parse_uart  # noqa: E402  (defines={} -> stock cmake command)

OUT = "/tmp/s4"
ANCHOR = "/tmp/xqbin/anchor.json"
REPS = 3
CELLS = ["rnnoise_INT8__SSE-320__ethos-u85-256", "rnnoise_INT8__SSE-320__ethos-u85-512",
         "kws_micronet_m__SSE-320__ethos-u85-256", "kws_micronet_m__SSE-320__ethos-u85-512",
         "wav2letter_pruned_int8__SSE-320__ethos-u85-256", "wav2letter_pruned_int8__SSE-320__ethos-u85-512"]
S4_RE = {k: r"NPU S4 %s:\s*(\d+)" % k for k in ("MAC_ACTIVE", "MAC_STALLED_BY_W", "MAC_STALLED_BY_IB", "AO_STALLED_BY_OB", "NPU_IDLE")}
STOCK_KEYS = ("npu_total_cycles", "npu_active_cycles", "sram_rd_beats", "sram_wr_beats", "ext_rd_beats", "ext_wr_beats")


def parse_s4(txt):
    out = {}
    for k, pat in S4_RE.items():
        m = re.search(pat, txt); out[k] = int(m.group(1)) if m else None
    return out


def patch(cmd, pass_id=None):
    args = [sys.executable, OUT + "/patch_driver.py", cmd] + ([pass_id] if pass_id else [])
    r = subprocess.run(args, capture_output=True, text=True)
    print("patch", cmd, r.stdout.strip(), r.stderr.strip(), flush=True)
    if r.returncode != 0:
        raise SystemExit("patch %s failed" % cmd)


def main():
    os.makedirs(OUT + "/uart", exist_ok=True)
    cells = {c["cell_id"]: c for c in json.load(open(ANCHOR))["canonical_order"]}
    expected = json.load(open(OUT + "/expected.json"))
    results = OUT + "/results.jsonl"
    for pass_id in ("A", "B"):
      patch("apply", pass_id)
      try:
          for cid in CELLS:
              cell = cells[cid]
              if stage1.free_bytes() < stage1.FREE_GATE:
                  print("STOP free-space gate", flush=True); return 2
              t0 = time.monotonic()
              b = build_with_ta(cell, {})
              if not b.get("ok"):
                  open(results, "a").write(json.dumps({"cell_id": cid, "status": "BUILD_FAILED:" + b.get("stage", "?"), "log": b.get("log", "")}) + "\n")
                  shutil.rmtree(b.get("ws", "/nonexistent"), ignore_errors=True); print("BUILD_FAILED", cid, flush=True); continue
              for rep in range(1, REPS + 1):
                  uart = os.path.join(b["ws"], "uart_%d.txt" % rep); log = os.path.join(b["ws"], "fvp_%d.log" % rep)
                  r = stage1.run_once(cell, b["axf"], uart, log)
                  txt = open(uart).read() if os.path.exists(uart) else ""
                  keep = os.path.join(OUT, "uart", "%s__pass%s__R%d.txt" % (cid, pass_id, rep)); open(keep, "w").write(txt)
                  stock = parse_uart(txt); exp = expected.get(cid, {})
                  g2 = {k: (stock.get(k) == exp.get(k)) for k in STOCK_KEYS if k in exp}
                  rec = {"cell_id": cid, "pass": pass_id, "rep": rep, "status": r["status"], "wall_clock_s": r["wall_clock_s"],
                         "survivors": r["survivors_after_cleanup"], "stock_counters": stock, "expected_stock": exp,
                         "G2_stock_counters_match": g2, "s4_counters": parse_s4(txt), "uart_file": keep,
                         "artifact": {"vela_sha256": b["vela_sha256"], "frozen_vela_sha256": cell["formal_vela_sha256"],
                                      "cc_body_sha256": b["cc_body_sha256"], "frozen_cc_body_sha256": cell["FORMAL_GENERATED_CC_BODY_SHA256"],
                                      "axf_sha256": b["axf_sha256"], "frozen_axf_sha256": cell["FORMAL_REFERENCE_AXF_SHA256"]},
                         "embedded_build_stamp": b["embedded_build_stamp"], "elapsed_s": round(time.monotonic() - t0, 1)}
                  open(results, "a").write(json.dumps(rec) + "\n")
                  print("pass%s %-46s R%d %s total=%s G2=%s s4=%s wall=%.1fs" % (pass_id, cid[:46], rep, r["status"], stock["npu_total_cycles"],
                        all(g2.values()) if g2 else None, rec["s4_counters"], r["wall_clock_s"]), flush=True)
                  if r["status"] != "SUCCESS":
                      break
              shutil.rmtree(b["ws"], ignore_errors=True)
      finally:
        patch("revert")
    print("S4_DONE", flush=True); return 0


if __name__ == "__main__":
    sys.exit(main())
