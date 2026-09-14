"""H13 -- verification campaign for hypotheses H1'/H2'/H3' (plan: docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md).

Runs on the build server inside the benchmark-runner container. Reuses the frozen stage1 harness
(/tmp/xqbin) for Vela, cmake, the FVP launch and the record layout. Differences from X4:
  * every build receives the FULL timing-adapter parameter set (16 values, SRAM + EXT) as -D flags,
    so nothing is left to MLEK's automatic profile selection (plan section 0);
  * every arm gets a second build with -DVERIFY_TEST_OUTPUT=1 (stock MLEK option, no code patch)
    that dumps input/output tensors on the UART; run once, kept under /tmp/h13/verify/ (gate G6);
  * cells may be synthetic (S3): /tmp/h13/synthetic_cells.json supplies model_path etc.

Usage:  python3 h13_sweep.py <stage: S1|S2|S3|S4|all>
Output: /tmp/h13/results.jsonl (one line per stock run, with the verify block attached to rep 1),
        /tmp/h13/uart/<cell>__<arm>__R<n>.txt, /tmp/h13/verify/<cell>__<arm>.txt
Resumable: arms with REPS stock runs recorded are skipped.
"""
import csv, hashlib, json, os, re, shutil, sys, time

sys.path.insert(0, "/tmp/xqbin")
import stage1  # noqa: E402  (frozen harness; run_once(), sh(), sha256(), ccident, KIT, ROOT, ARENA)

OUT = "/tmp/h13"
ANCHOR = "/tmp/xqbin/anchor.json"
SYNTH = OUT + "/synthetic_cells.json"
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
    gen = stage1.sh("ls %s/generated/inference_runner/src/*_vela.tflite.cc" % bdir).stdout.strip().splitlines()
    gen = gen[0] if gen else None
    body = stage1.ccident.body_sha256(open(gen, "rb").read()) if gen else None
    return {"ok": True, "axf": axf, "axf_sha256": stage1.sha256(axf), "cc_body_sha256": body,
            "ta_header": ta, "ta_header_path": hdr, "cmd": cfg,
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


# ------------------------------------------------------------------ experiment matrix (plan sections 1-7)
RN = "rnnoise_INT8__SSE-320__ethos-u85-%d"
KWS, AD, W2L = "kws_micronet_m__SSE-320__ethos-u85-%d", "ad_medium_int8__SSE-320__ethos-u85-%d", "wav2letter_pruned_int8__SSE-320__ethos-u85-%d"


def lat(r, w):
    return "r%d_w%d" % (r, w), {"EXT_RLATENCY": r, "EXT_WLATENCY": w}


def arms_S1():
    for mac in (256, 512, 1024, 2048):                              # H1-A
        yield "H1A", RN % mac, lat(*((250, 125) if mac == 256 else (500, 250)))
        for r in (0, 125, 250, 500, 1000):
            yield "H1A", RN % mac, lat(r, 250)
        for w in (0, 125, 250, 500):
            yield "H1A", RN % mac, lat(500, w)
        yield "H1A", RN % mac, lat(0, 0)
    for mac in (256, 512):                                          # H1-B
        wbase = 125 if mac == 256 else 250
        for m in (1, 4, 16, 63, 64, 0):
            for r in (250, 1000):
                yield "H1B", RN % mac, ("maxr%d_r%d_w%d" % (m, r, wbase), {"EXT_MAXR": m, "EXT_RLATENCY": r, "EXT_WLATENCY": wbase})
        for m in (1, 63):                                           # plan A3: does C(0,0) respond to MAXR? (factor 6)
            yield "H1B", RN % mac, ("maxr%d_r0_w0" % m, {"EXT_MAXR": m, "EXT_RLATENCY": 0, "EXT_WLATENCY": 0})
    for mac in (256, 512, 1024, 2048):                              # H1-C(a)
        for r in (375, 750):
            yield "H1Ca", RN % mac, lat(r, r // 2)
    for tmpl in (KWS, AD):                                          # H1-C(b)
        for mac in (256, 512):
            yield "H1Cb", tmpl % mac, lat(*((250, 125) if mac == 256 else (500, 250)))
            for r in (0, 250, 500, 1000):
                yield "H1Cb", tmpl % mac, lat(r, 250)


def arms_S2():
    for mac, caps, base in ((512, (1875, 3750, 7500, 0), (500, 250)), (256, (1172, 2344, 4688, 0), (250, 125))):
        for cap in caps:
            for r, w in (base, (0, 0)):
                yield "H2A", W2L % mac, ("bw%d_r%d_w%d" % (cap, r, w), {"EXT_BWCAP": cap, "EXT_RLATENCY": r, "EXT_WLATENCY": w})
    for cid in ("kws_micronet_m__SSE-300__ethos-u55-256", "ad_medium_int8__SSE-300__ethos-u55-256",
                "kws_micronet_m__SSE-300__ethos-u65-512", "ad_medium_int8__SSE-300__ethos-u65-512"):
        for cap in (4000, 2000, 8000, 0):
            yield "SRAMCAP", cid, ("sbw%d" % cap, {"SRAM_BWCAP": cap})


def arms_S3():
    """Synthetic shape cells: each entry in synthetic_cells.json carries its own arm list."""
    if not os.path.exists(SYNTH):
        return
    for c in json.load(open(SYNTH)):
        if c.get("experiment") == "H2BX":
            continue
        for arm, defs in c["arms"]:
            yield c.get("experiment", "H3"), c["cell_id"], (arm, defs)


def arms_S4():
    if not os.path.exists(SYNTH):
        return
    for c in json.load(open(SYNTH)):
        if c.get("experiment") == "H2BX":
            for arm, defs in c["arms"]:
                yield "H2BX", c["cell_id"], (arm, defs)


STAGES = {"S1": arms_S1, "S2": arms_S2, "S3": arms_S3, "S4": arms_S4}


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
    cells = {c["cell_id"]: c for c in json.load(open(ANCHOR))["canonical_order"]}
    if os.path.exists(SYNTH):
        for c in json.load(open(SYNTH)):
            cells[c["cell_id"]] = c
    return cells


def run_arm(exp, cell, arm, overrides, results):
    defines = full_defines(cell, overrides)
    is_base = defines == PROFILES[profile_of(cell)]
    ws = os.path.join(stage1.ROOT, "h13_" + cell["cell_id"]); shutil.rmtree(ws, ignore_errors=True)
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


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for d in ("uart", "verify", "vela"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    cells = load_cells()
    path = OUT + "/results.jsonl"; have = done_runs(path)
    limit = 1 if which == "smoke" else None
    stages = list(STAGES) if which == "all" else (["S1"] if which == "smoke" else [which])
    seen = set(); started = 0
    with open(path, "a") as results:
        for st in stages:
            for exp, cid, (arm, overrides) in STAGES[st]():
                if (cid, arm) in seen:
                    continue
                seen.add((cid, arm))
                if have.get((cid, arm), 0) >= REPS:
                    continue
                if stage1.free_bytes() < stage1.FREE_GATE:
                    print("STOP free-space gate", flush=True); return 2
                run_arm(exp, cells[cid], arm, overrides, results); started += 1
                if limit and started >= limit:
                    print("H13_SMOKE_DONE", flush=True); return 0
    print("H13_DONE", which, flush=True); return 0


if __name__ == "__main__":
    sys.exit(main())
