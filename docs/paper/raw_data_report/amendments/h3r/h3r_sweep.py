"""H3-R -- shape-only INT8 derivatives x {256,512} x {base, equalized, bridge_legacy_relaxed} (plan A8, manager GO 2026-09-15).

Copy of h13_sweep.py (frozen H13 harness) with: OUT=/tmp/h3r, cells from /tmp/h3r/cells.json only, the shared
FetchContent cache of /tmp/h13 (plan A6), CMakeCache read-back of the 16 TA values (ta_cache), the driver mask
excerpt recorded once per run, and two in-run stops: a generated header that does not match the request, or a
verify-build output dump that differs from the first dump seen for the same model (output gate) -> the run stops
so that later arms are not spent on a failed gate (GO section 0). Otherwise identical: every build receives the
full 16-value TA set as -D flags; per arm one verify build (+1 FVP run) and REPS stock FVP runs.

Usage:  python3 h3r_sweep.py qual   # first arm only (h3r_conv1x1_6x6_c128 x 256 base)
        python3 h3r_sweep.py all
Output: /tmp/h3r/results.jsonl, /tmp/h3r/uart/, /tmp/h3r/verify/, /tmp/h3r/vela/. Resumable.
"""
import csv, hashlib, json, os, re, shutil, sys, time

sys.path.insert(0, "/tmp/xqbin")
import stage1  # noqa: E402  (frozen harness; run_once(), sh(), sha256(), ccident, KIT, ROOT, ARENA)

OUT = "/tmp/h3r"
FC_CACHE = "/tmp/h13/fc_cache"
SYNTH = OUT + "/cells.json"
DRIVER = "/opt/arm/ml-embedded-evaluation-kit/dependencies/core-platform/drivers/timing_adapter/src/timing_adapter.c"
TA_CSV = OUT + "/ta_parameters.csv"
REPS = 3
KIT = stage1.KIT
TA_KEYS = ("MAXR", "MAXW", "MAXRW", "RLATENCY", "WLATENCY", "PULSE_ON", "PULSE_OFF", "BWCAP")

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


def profiles():
    """ta_config -> full 16-value define dict (MAXRW is 0 in every MLEK profile file)."""
    p = {}
    for r in csv.DictReader(open(TA_CSV)):
        d = {}
        for side in ("sram", "ext"):
            for k in TA_KEYS:
                d["%s_%s" % (side.upper(), k)] = 0 if k == "MAXRW" else int(r["%s_%s" % (side, k.lower())])
        p[r["ta_config"]] = d
    return p


PROFILES = profiles()


def profile_of(cell):
    npu, mac = cell["npu"], int(cell["mac_config"])
    if npu == "ethos-u55":
        return "u55_high_end"
    if npu == "ethos-u65":
        return "u65_high_end"
    return "u85_sys_dram_low" if mac <= 256 else ("u85_sys_dram_mid" if mac <= 1024 else "u85_sys_dram_high")


def full_defines(cell, overrides):
    d = dict(PROFILES[profile_of(cell)]); d.update(overrides); return d


def dump_sha(txt):
    """sha256 of the output-tensor dump section of a verify-build UART (None if absent)."""
    i = txt.find("output tensors post inference")
    if i < 0:
        return None
    data = re.findall(r"0x[0-9a-f]{2}", txt[i:])      # bytes only: the UART tail after the dump may be cut off
    return hashlib.sha256(",".join(data).encode()).hexdigest() if data else None


def build(cell, defines, verify, ws, art):
    """cmake + build in ws/build-{stock|verify}; returns record with header readback."""
    bdir = os.path.join(ws, "build-verify" if verify else "build-stock")
    extra = " ".join("-D%s=%s" % kv for kv in sorted(defines.items()))
    if verify:
        extra += " -DVERIFY_TEST_OUTPUT=1"
    # plan A6: third-party sources (flatbuffers, ruy, ...) come from a shared local FetchContent cache once populated,
    # instead of a fresh GitHub archive download per configure (intermittent HTTP 504 killed 33 arms). Same versions.
    extra += " -DFETCHCONTENT_BASE_DIR=%s -DFETCHCONTENT_UPDATES_DISCONNECTED=ON" % FC_CACHE
    cfg = ("cmake -B %s -S %s -DCMAKE_TOOLCHAIN_FILE=%s/scripts/cmake/toolchains/bare-metal-gcc.cmake "
           "-DTARGET_PLATFORM=%s -DTARGET_SUBSYSTEM=%s -DETHOS_U_NPU_ID=%s -DETHOS_U_NPU_CONFIG_ID=%s "
           "-DETHOS_U_NPU_MEMORY_MODE=%s -DETHOS_U_NPU_ENABLED=ON -DUSE_CASE_BUILD=inference_runner "
           "-Dinference_runner_ACTIVATION_BUF_SZ=0x%08X -Dinference_runner_MODEL_PATH=%s %s"
           % (bdir, KIT, KIT, cell["target_platform"], cell["target_subsystem"], stage1.NPU_ID[cell["npu"]],
              stage1.CFG[cell["npu"]] + str(cell["mac_config"]), cell["memory_mode"], stage1.ARENA, art, extra))
    rc = stage1.sh(cfg)
    if rc.returncode != 0:
        return {"ok": False, "stage": "configure", "log": (rc.stdout + rc.stderr)[-1500:], "cmd": cfg}
    rb = stage1.sh("cmake --build %s -j $(nproc)" % bdir)
    axf = os.path.join(bdir, "bin", "mlek_inference_runner.axf")
    if rb.returncode != 0 or not os.path.exists(axf):
        return {"ok": False, "stage": "build", "log": (rb.stdout + rb.stderr)[-1500:], "cmd": cfg}
    hdr = stage1.sh("find %s -name timing_adapter_settings.h | head -1" % bdir).stdout.strip()
    ta = {}
    if hdr:
        for line in open(hdr):
            m = re.match(r"#define ((?:EXT|SRAM)_\w+)\s+\((\d+)\)", line)
            if m:
                ta[m.group(1)] = int(m.group(2))
    cache = {}
    for line in open(os.path.join(bdir, "CMakeCache.txt")):
        m = re.match(r"((?:EXT|SRAM)_(?:MAXR|MAXW|MAXRW|RLATENCY|WLATENCY|PULSE_ON|PULSE_OFF|BWCAP)):[A-Z]*=(-?\d+)\s*$", line)
        if m:
            cache[m.group(1)] = int(m.group(2))
    gen = stage1.sh("ls %s/generated/inference_runner/src/*_vela.tflite.cc" % bdir).stdout.strip().splitlines()
    gen = gen[0] if gen else None
    body = stage1.ccident.body_sha256(open(gen, "rb").read()) if gen else None
    return {"ok": True, "axf": axf, "axf_sha256": stage1.sha256(axf), "cc_body_sha256": body,
            "ta_header": ta, "ta_header_path": hdr, "ta_cache": cache, "cmd": cfg,
            "header_matches_request": all(ta.get(k) == v for k, v in defines.items()),
            "timing_adapter_cache": stage1.sh("grep -E '^ETHOS_U_NPU_TIMING_ADAPTER_ENABLED' %s/CMakeCache.txt" % bdir).stdout.strip(),
            "embedded_build_stamp": stage1.sh("arm-none-eabi-strings %s | grep -m1 'Build date:'" % axf).stdout.strip()}


def vela(cell, ws):
    vdir = os.path.join(ws, "vela"); os.makedirs(vdir, exist_ok=True)
    src = cell.get("model_path") or os.path.join(KIT, "resources_downloaded", stage1.MODEL_SRC[cell["model"]])
    cmd = ("vela --accelerator-config %s --config %s/scripts/vela/default_vela.ini --system-config %s "
           "--memory-mode %s --optimise Performance --output-dir %s %s"
           % (cell["accelerator_config"], KIT, cell["system_config"], cell["memory_mode"], vdir, src))
    if cell.get("verbose"):
        cmd += " --verbose-schedule --verbose-performance"
    if cell.get("vela_extra"):
        cmd += " " + cell["vela_extra"]
    r = stage1.sh(cmd)
    art = os.path.join(vdir, "%s_vela.tflite" % cell["model"])
    if cell.get("verbose"):
        open(os.path.join(vdir, "vela_verbose.txt"), "w").write(r.stdout + r.stderr)
    return (art if os.path.exists(art) else None), cmd, vdir


# ------------------------------------------------------------------ experiment matrix: /tmp/h3r/cells.json (plan A8)
def arms_all():
    for c in json.load(open(SYNTH)):
        for arm, defs in c["arms"]:
            yield c.get("experiment", "H3R"), c["cell_id"], (arm, defs)


def arms_qual():
    for x in arms_all():
        yield x; return


STAGES = {"qual": arms_qual, "all": arms_all}


def done_runs(path):
    n = {}
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
                if "measurement" in r:
                    n[(r["cell_id"], r["arm"])] = n.get((r["cell_id"], r["arm"]), 0) + 1
            except Exception:
                pass
    return n


def load_cells():
    return {c["cell_id"]: c for c in json.load(open(SYNTH))}


def first_dumps(path):
    """model -> verify dump sha256 of the first recorded arm (in-run output gate reference)."""
    d = {}
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            v = r.get("verify") or {}
            if v.get("dump_sha256"):
                d.setdefault(r["cell_id"].split("__")[0], v["dump_sha256"])
    return d


def run_arm(exp, cell, arm, overrides, results, dumps):
    defines = full_defines(cell, overrides)
    is_base = defines == PROFILES[profile_of(cell)]
    ws = os.path.join(stage1.ROOT, "h3r_" + cell["cell_id"]); shutil.rmtree(ws, ignore_errors=True)
    t0 = time.monotonic()
    art, vcmd, vdir = vela(cell, ws)
    base_rec = {"experiment": exp, "cell_id": cell["cell_id"], "arm": arm, "overrides": overrides, "defines": defines,
                "is_base": is_base, "profile": profile_of(cell), "vela_cmd": vcmd}
    if not art:
        results.write(json.dumps(dict(base_rec, status="BUILD_FAILED:vela")) + "\n"); results.flush()
        shutil.rmtree(ws, ignore_errors=True); print("VELA_FAILED", cell["cell_id"], arm, flush=True); return
    vsha = stage1.sha256(art)
    if cell.get("verbose"):
        keep_v = os.path.join(OUT, "vela", "%s__%s" % (cell["cell_id"], arm)); os.makedirs(keep_v, exist_ok=True)
        for f in os.listdir(vdir):
            if f.endswith((".txt", ".csv")):
                shutil.copy(os.path.join(vdir, f), keep_v)
    b = build(cell, defines, False, ws, art)
    if not b["ok"]:
        results.write(json.dumps(dict(base_rec, status="BUILD_FAILED:" + b["stage"], log=b["log"], cmd=b["cmd"])) + "\n"); results.flush()
        shutil.rmtree(ws, ignore_errors=True); print("BUILD_FAILED", cell["cell_id"], arm, b["stage"], flush=True); return
    # verify build (stock source + -DVERIFY_TEST_OUTPUT=1), one run
    v = build(cell, defines, True, ws, art)
    verify = {"build_ok": v["ok"]}
    if v["ok"]:
        vu = os.path.join(ws, "uart_verify.txt"); vl = os.path.join(ws, "fvp_verify.log")
        r = stage1.run_once(cell, v["axf"], vu, vl)
        txt = open(vu).read() if os.path.exists(vu) else ""
        keep = os.path.join(OUT, "verify", "%s__%s.txt" % (cell["cell_id"], arm)); open(keep, "w").write(txt)
        verify.update({"status": r["status"], "measurement": parse_uart(txt), "dump_sha256": dump_sha(txt),
                       "uart_file": keep, "axf_sha256": v["axf_sha256"], "header_matches_request": v["header_matches_request"]})
    else:
        verify.update({"stage": v["stage"], "log": v["log"]})
    for rep in range(1, REPS + 1):
        uart = os.path.join(ws, "uart_%d.txt" % rep); log = os.path.join(ws, "fvp_%d.log" % rep)
        r = stage1.run_once(cell, b["axf"], uart, log)
        txt = open(uart).read() if os.path.exists(uart) else ""
        keep = os.path.join(OUT, "uart", "%s__%s__R%d.txt" % (cell["cell_id"], arm, rep)); open(keep, "w").write(txt)
        rec = dict(base_rec, rep=rep, status=r["status"], wall_clock_s=r["wall_clock_s"], survivors=r["survivors_after_cleanup"],
                   measurement=parse_uart(txt), uart_file=keep, fvp_cmd_axf=b["axf"],
                   artifact={"vela_sha256": vsha, "frozen_vela_sha256": cell.get("formal_vela_sha256"),
                             "cc_body_sha256": b["cc_body_sha256"], "frozen_cc_body_sha256": cell.get("FORMAL_GENERATED_CC_BODY_SHA256"),
                             "axf_sha256": b["axf_sha256"], "frozen_axf_sha256": cell.get("FORMAL_REFERENCE_AXF_SHA256")},
                   ta_header=b["ta_header"], header_matches_request=b["header_matches_request"],
                   timing_adapter_cache=b["timing_adapter_cache"], embedded_build_stamp=b["embedded_build_stamp"],
                   cmake_cmd=b["cmd"], elapsed_s=round(time.monotonic() - t0, 1))
        if rep == 1:
            rec["verify"] = verify
        results.write(json.dumps(rec) + "\n"); results.flush()
        print("%s %-46s %-22s R%d %s total=%s hdr=%s vfy=%s" % (exp, cell["cell_id"][:46], arm, rep, r["status"],
              rec["measurement"]["npu_total_cycles"], b["header_matches_request"], verify.get("dump_sha256", "-")[:8] if verify.get("dump_sha256") else verify.get("status", "-")), flush=True)
        if r["status"] != "SUCCESS":
            break
    shutil.rmtree(ws, ignore_errors=True)
    # in-run gates (GO section 0: preserve the evidence, stop the runs affected)
    if not b["header_matches_request"] or (v["ok"] and not v["header_matches_request"]):
        print("STOP header != request", cell["cell_id"], arm, flush=True); return "STOP_HEADER"
    model = cell["cell_id"].split("__")[0]; ds = verify.get("dump_sha256")
    if ds is None:
        print("STOP no verify dump", cell["cell_id"], arm, verify, flush=True); return "STOP_NO_DUMP"
    if model in dumps and dumps[model] != ds:
        print("STOP output dump differs for model", model, cell["cell_id"], arm, ds, "!=", dumps[model], flush=True); return "STOP_OUTPUT"
    dumps.setdefault(model, ds)
    return None


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for d in ("uart", "verify", "vela"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    open(os.path.join(OUT, "driver_masks.txt"), "w").write(
        stage1.sh("sha256sum %s; grep -n 'MASK\\|ta_set_\\|& TA_' %s" % (DRIVER, DRIVER)).stdout)
    cells = load_cells()
    path = os.environ.get("H3R_RESULTS", OUT + "/results.jsonl"); have = done_runs(path); dumps = first_dumps(path)
    seen = set()
    with open(path, "a") as results:
        for exp, cid, (arm, overrides) in STAGES[which]():
            if (cid, arm) in seen:
                continue
            seen.add((cid, arm))
            if have.get((cid, arm), 0) >= REPS:
                continue
            if stage1.free_bytes() < stage1.FREE_GATE:
                print("STOP free-space gate", flush=True); return 2
            stop = run_arm(exp, cells[cid], arm, overrides, results, dumps)
            if stop:
                print("H3R_STOPPED", stop, flush=True); return 3
    print("H3R_DONE", which, flush=True); return 0


if __name__ == "__main__":
    sys.exit(main())
