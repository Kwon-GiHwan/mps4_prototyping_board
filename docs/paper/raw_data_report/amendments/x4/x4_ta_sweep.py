"""X4 -- Timing Adapter memory-service sweep with the compiled artifact fixed.

Contract: docs/superpowers/plans/2026-09-14-unresolved-items-evaluation-plan.md section 10.
Runs on the build server inside the benchmark-runner container. Reuses stage1 (frozen harness
at /tmp/xqbin) for the FVP launch and cell records; only the cmake command gains -D overrides
for the EXT timing-adapter parameters. Nothing else differs from the formal build.

Usage:  python3 x4_ta_sweep.py <campaign: A|B|all>
Output: /tmp/x4/results.jsonl (one line per run), /tmp/x4/uart/<cell>__<arm>__R<n>.txt (raw UART)
Resumable: arms with 3 recorded runs are skipped.
"""
import json, os, re, shutil, sys, time

sys.path.insert(0, "/tmp/xqbin")
import stage1  # noqa: E402  (frozen harness; build(), run_once(), sh(), sha256())

OUT = "/tmp/x4"
ANCHOR = "/tmp/xqbin/anchor.json"
REPS = 3
KIT = stage1.KIT

CAMPAIGN_A = {  # cell_id -> base read latency; write latency = read / 2
    "rnnoise_INT8__SSE-320__ethos-u85-256": 250,
    "rnnoise_INT8__SSE-320__ethos-u85-512": 500,
    "wav2letter_pruned_int8__SSE-320__ethos-u85-256": 250,
    "wav2letter_pruned_int8__SSE-320__ethos-u85-512": 500,
}
A_FACTORS = (1.0, 0.0, 0.5, 2.0, 4.0)  # base first: it is the reproduction gate
CAMPAIGN_B = {"rnnoise_INT8__SSE-300__ethos-u55-256": 50}
B_LEVELS = (50, 25, 100, 200, 0)

PMU_RE = {
    "npu_total_cycles": r"NPU TOTAL:\s*(\d+)", "npu_active_cycles": r"NPU ACTIVE:\s*(\d+)",
    "npu_idle_cycles": r"NPU IDLE:\s*(\d+)",
    "axi0_rd_beats": r"AXI0_RD_DATA_BEAT_RECEIVED:\s*(\d+)", "axi0_wr_beats": r"AXI0_WR_DATA_BEAT_WRITTEN:\s*(\d+)",
    "axi1_rd_beats": r"AXI1_RD_DATA_BEAT_RECEIVED:\s*(\d+)",
    "sram_rd_beats": r"SRAM_RD_DATA_BEAT_RECEIVED:\s*(\d+)", "sram_wr_beats": r"SRAM_WR_DATA_BEAT_WRITTEN:\s*(\d+)",
    "ext_rd_beats": r"EXT_RD_DATA_BEAT_RECEIVED:\s*(\d+)", "ext_wr_beats": r"EXT_WR_DATA_BEAT_WRITTEN:\s*(\d+)",
}


def parse_uart(txt):
    out = {}
    for k, pat in PMU_RE.items():
        m = re.search(pat, txt); out[k] = int(m.group(1)) if m else None
    return out


def build_with_ta(cell, defines):
    """stage1.build with extra -D flags; returns stage1's record plus the generated TA header values."""
    ws = os.path.join(stage1.ROOT, cell["cell_id"])
    shutil.rmtree(ws, ignore_errors=True)
    vdir = os.path.join(ws, "vela"); os.makedirs(vdir, exist_ok=True)
    src = os.path.join(KIT, "resources_downloaded", stage1.MODEL_SRC[cell["model"]])
    stage1.sh("vela --accelerator-config %s --config %s/scripts/vela/default_vela.ini "
              "--system-config %s --memory-mode %s --optimise Performance --output-dir %s %s"
              % (cell["accelerator_config"], KIT, cell["system_config"], cell["memory_mode"], vdir, src))
    art = os.path.join(vdir, "%s_vela.tflite" % cell["model"])
    if not os.path.exists(art):
        return {"ok": False, "stage": "vela", "ws": ws}
    bdir = os.path.join(ws, "build-a1")
    extra = " ".join("-D%s=%s" % kv for kv in defines.items())
    rc = stage1.sh("cmake -B %s -S %s "
                   "-DCMAKE_TOOLCHAIN_FILE=%s/scripts/cmake/toolchains/bare-metal-gcc.cmake "
                   "-DTARGET_PLATFORM=%s -DTARGET_SUBSYSTEM=%s -DETHOS_U_NPU_ID=%s "
                   "-DETHOS_U_NPU_CONFIG_ID=%s -DETHOS_U_NPU_MEMORY_MODE=%s -DETHOS_U_NPU_ENABLED=ON "
                   "-DUSE_CASE_BUILD=inference_runner -Dinference_runner_ACTIVATION_BUF_SZ=0x%08X "
                   "-Dinference_runner_MODEL_PATH=%s %s"
                   % (bdir, KIT, KIT, cell["target_platform"], cell["target_subsystem"],
                      stage1.NPU_ID[cell["npu"]], stage1.CFG[cell["npu"]] + str(cell["mac_config"]),
                      cell["memory_mode"], stage1.ARENA, art, extra))
    if rc.returncode != 0:
        return {"ok": False, "stage": "configure", "ws": ws, "log": (rc.stdout + rc.stderr)[-1200:]}
    rb = stage1.sh("cmake --build %s -j $(nproc)" % bdir)
    axf = os.path.join(bdir, "bin", "mlek_inference_runner.axf")
    if rb.returncode != 0 or not os.path.exists(axf):
        return {"ok": False, "stage": "build", "ws": ws, "log": (rb.stdout + rb.stderr)[-1200:]}
    hdr = stage1.sh("find %s -name timing_adapter_settings.h | head -1" % bdir).stdout.strip()
    ta = {}
    if hdr:
        for line in open(hdr):
            m = re.match(r"#define (EXT_\w+|SRAM_\w+)\s+\((\d+)\)", line)
            if m: ta[m.group(1)] = int(m.group(2))
    gen = stage1.sh("ls %s/generated/inference_runner/src/*_vela.tflite.cc" % bdir).stdout.strip().splitlines()
    gen = gen[0] if gen else None
    body = stage1.ccident.body_sha256(open(gen, "rb").read()) if gen else None
    return {"ok": True, "ws": ws, "axf": axf, "axf_sha256": stage1.sha256(axf), "vela_sha256": stage1.sha256(art),
            "cc_body_sha256": body, "ta_header": ta, "ta_header_path": hdr,
            "timing_adapter_cache": stage1.sh("grep -E '^ETHOS_U_NPU_TIMING_ADAPTER_ENABLED' %s/CMakeCache.txt" % bdir).stdout.strip(),
            "embedded_build_stamp": stage1.sh("arm-none-eabi-strings %s | grep -m1 'Build date:'" % axf).stdout.strip()}


def arms():
    for cid, base in CAMPAIGN_A.items():
        for f in A_FACTORS:
            r = int(base * f)
            yield "A", cid, "rlat%d_wlat%d" % (r, r // 2), {"EXT_RLATENCY": r, "EXT_WLATENCY": r // 2}, f == 1.0
    for cid, base in CAMPAIGN_B.items():
        for lvl in B_LEVELS:
            yield "B", cid, "bwcap%d" % lvl, {"EXT_BWCAP": lvl}, lvl == base


def done_runs(path):
    n = {}
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line); n[(r["cell_id"], r["arm"])] = n.get((r["cell_id"], r["arm"]), 0) + 1
            except Exception:
                pass
    return n


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    os.makedirs(OUT + "/uart", exist_ok=True)
    cells = {c["cell_id"]: c for c in json.load(open(ANCHOR))["canonical_order"]}
    results = OUT + "/results.jsonl"; have = done_runs(results)
    for camp, cid, arm, defines, is_base in arms():
        if which != "all" and camp != which:
            continue
        if have.get((cid, arm), 0) >= REPS:
            continue
        cell = cells[cid]
        if stage1.free_bytes() < stage1.FREE_GATE:
            print("STOP free-space gate", flush=True); return 2
        t0 = time.monotonic()
        b = build_with_ta(cell, defines)
        if not b.get("ok"):
            rec = {"campaign": camp, "cell_id": cid, "arm": arm, "defines": defines, "status": "BUILD_FAILED:" + b.get("stage", "?"),
                   "log": b.get("log", "")}
            open(results, "a").write(json.dumps(rec) + "\n"); shutil.rmtree(b.get("ws", "/nonexistent"), ignore_errors=True)
            print("BUILD_FAILED", cid, arm, flush=True); continue
        for rep in range(1, REPS + 1):
            uart = os.path.join(b["ws"], "uart_%d.txt" % rep); log = os.path.join(b["ws"], "fvp_%d.log" % rep)
            r = stage1.run_once(cell, b["axf"], uart, log)
            txt = open(uart).read() if os.path.exists(uart) else ""
            keep = os.path.join(OUT, "uart", "%s__%s__R%d.txt" % (cid, arm, rep)); open(keep, "w").write(txt)
            rec = {"campaign": camp, "cell_id": cid, "arm": arm, "defines": defines, "is_base": is_base, "rep": rep,
                   "status": r["status"], "wall_clock_s": r["wall_clock_s"], "survivors": r["survivors_after_cleanup"],
                   "measurement": parse_uart(txt), "uart_file": keep,
                   "artifact": {"vela_sha256": b["vela_sha256"], "frozen_vela_sha256": cell["formal_vela_sha256"],
                                "cc_body_sha256": b["cc_body_sha256"], "frozen_cc_body_sha256": cell["FORMAL_GENERATED_CC_BODY_SHA256"],
                                "axf_sha256": b["axf_sha256"], "frozen_axf_sha256": cell["FORMAL_REFERENCE_AXF_SHA256"]},
                   "ta_header": b["ta_header"], "timing_adapter_cache": b["timing_adapter_cache"],
                   "embedded_build_stamp": b["embedded_build_stamp"], "elapsed_s": round(time.monotonic() - t0, 1)}
            open(results, "a").write(json.dumps(rec) + "\n")
            print("%s %-46s %-18s R%d %s total=%s wall=%.1fs" % (camp, cid[:46], arm, rep, r["status"],
                  rec["measurement"]["npu_total_cycles"], r["wall_clock_s"]), flush=True)
            if r["status"] != "SUCCESS":
                break
        shutil.rmtree(b["ws"], ignore_errors=True)
    print("X4_DONE", flush=True); return 0


if __name__ == "__main__":
    sys.exit(main())
