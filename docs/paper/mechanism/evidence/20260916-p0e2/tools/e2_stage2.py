#!/usr/bin/env python3
"""P0-E2 stage 2: clean + profiled builds and 3x FVP runs per arm.
Verbatim reuse of the P0-D/P0-D2 build+run recipe. Fail-closed."""
import hashlib, json, os, re, shutil, signal, subprocess, sys, time

KIT = "/opt/arm/ml-embedded-evaluation-kit"
OUT = "/work/u85e2"
PD  = OUT + "/pd"
FVP = "/opt/arm/fvp_installed_320/models/Linux64_GCC-9.3/FVP_Corstone_SSE-320"
EPOCH = "1776763519"
cells = json.load(open(OUT + "/cells.json"))

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          env=dict(os.environ, SOURCE_DATE_EPOCH=EPOCH))
def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()
def stop(m): print("STOP:", m, flush=True); sys.exit(2)
def log(*a): print(*a, flush=True)

def build(c, arm, model_path):
    d = os.path.join(PD, c["cell"])
    axf_out = os.path.join(d, "%s.axf" % arm)
    meta_out = os.path.join(d, "%s.build.json" % arm)
    if os.path.exists(meta_out): return
    bdir = os.path.join(d, "build-" + arm)
    shutil.rmtree(bdir, ignore_errors=True)
    r = sh("cmake -B %s -S %s -DCMAKE_TOOLCHAIN_FILE=%s/scripts/cmake/toolchains/bare-metal-gcc.cmake "
           "-DTARGET_PLATFORM=mps4 -DTARGET_SUBSYSTEM=sse-320 -DETHOS_U_NPU_ID=U85 "
           "-DETHOS_U_NPU_CONFIG_ID=Z%d -DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram "
           "-DETHOS_U_NPU_ENABLED=ON -DUSE_CASE_BUILD=inference_runner "
           "-Dinference_runner_ACTIVATION_BUF_SZ=0x00200000 -Dinference_runner_MODEL_PATH=%s"
           % (bdir, KIT, KIT, c["macs"], model_path))
    if r.returncode != 0: stop("configure %s/%s: %s" % (c["cell"], arm, r.stderr[-400:]))
    r = sh("cmake --build %s -j $(nproc)" % bdir)
    axf = os.path.join(bdir, "bin", "mlek_inference_runner.axf")
    if r.returncode != 0 or not os.path.exists(axf):
        stop("build %s/%s: %s" % (c["cell"], arm, (r.stdout + r.stderr)[-500:]))
    ta = sh("grep -E '^ETHOS_U_NPU_TIMING_ADAPTER_ENABLED' %s/CMakeCache.txt" % bdir).stdout.strip()
    shutil.copy2(axf, axf_out)
    json.dump({"axf_sha256": sha256(axf_out), "timing_adapter": ta}, open(meta_out, "w"))
    shutil.rmtree(bdir, ignore_errors=True)
    log("[build] %-44s %s %s" % (c["cell"], arm, sha256(axf_out)[:12]))

def patches(*names):
    for n in names:
        r = sh("python3 /tmp/%s" % n)
        if r.returncode != 0: stop("patch %s: %s" % (n, r.stdout + r.stderr))
        log("[patch]", n, r.stdout.strip()[:70])

REVERT_PAIRS = [("dependencies/core-driver/src/ethosu_driver.c",
                 "dependencies/core-driver/src/ethosu_driver.c.bak"),
                ("dependencies/core-driver/src/ethosu_device_u85.c",
                 "dependencies/core-driver/src/ethosu_device_u85.c.bak.v3"),
                ("source/app/use_case/inference_runner/src/UseCaseHandler.cc",
                 "source/app/use_case/inference_runner/src/UseCaseHandler.cc.bak.cgroup")]

def reverts(*names):
    for n in names: sh("python3 /tmp/%s --revert" % n)
    for a, b in REVERT_PAIRS:
        if not os.path.exists(os.path.join(KIT, b)): continue
        if sh("diff %s/%s %s/%s" % (KIT, a, KIT, b)).returncode != 0:
            stop("revert verification failed " + a)
    log("[revert] verified clean")

log("== phase A: clean builds ==")
patches("patch_app.py")
for c in cells: build(c, "clean", c["art"])
reverts("patch_app.py")

log("== phase B: profiled builds ==")
patches("patch_app.py", "patch_driver_u85_v3.py")
for c in cells: build(c, "prof", c["instr"])
reverts("patch_driver_u85_v3.py", "patch_app.py")

# ---------------- runs -------------------------------------------------
CRC_RE = re.compile(r"C04_OUTPUT_CRC\[(\d+)\]: bytes=(\d+) crc32=(0x[0-9A-F]+)")
TOT_RE = re.compile(r"NPU TOTAL: (\d+) cycles")
ACT_RE = re.compile(r"NPU ACTIVE: (\d+) cycles")
IDL_RE = re.compile(r"NPU IDLE: (\d+) cycles")
CNT_RE = re.compile(r"Total number of inferences:\s*(\d+)")

def run_fvp(axf, uart, macs, timeout=1800):
    try: os.remove(uart)
    except OSError: pass
    p = subprocess.Popen([FVP, "-a", axf,
        "-C", "mps4_board.subsystem.ethosu.num_macs=%d" % macs,
        "-C", "mps4_board.visualisation.disable-visualisation=1",
        "-C", "mps4_board.telnetterminal0.start_telnet=0",
        "-C", "mps4_board.uart0.out_file=" + uart,
        "-C", "mps4_board.uart0.unbuffered_output=1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    t0 = time.monotonic(); txt = ""
    while time.monotonic() - t0 < timeout:
        try: txt = open(uart).read()
        except OSError: txt = ""
        if CNT_RE.search(txt) or "Inference failed" in txt: break
        time.sleep(1)
    time.sleep(3)
    try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception: pass
    return (open(uart).read() if os.path.exists(uart) else "",
            round(time.monotonic() - t0, 1))

def extract(txt):
    v = {}
    for name, rx in (("total", TOT_RE), ("active", ACT_RE), ("idle", IDL_RE), ("count", CNT_RE)):
        m = rx.search(txt); v[name] = int(m.group(1)) if m else None
    v["crc"] = ";".join("%s:%s:%s" % g for g in CRC_RE.findall(txt))
    v["plprof"] = "\n".join(l for l in txt.replace("\x00", "").splitlines() if l.startswith("PLPROF"))
    m = re.search(r"PLPROF_BEGIN,(\d+)", txt)
    v["pl_count"] = int(m.group(1)) if m else None
    return v

log("== runs ==")
for c in cells:
    d = os.path.join(PD, c["cell"])
    for arm in ("clean", "prof"):
        vecs = []
        for rn in (1, 2, 3):
            done = os.path.join(d, "%s.run%d.json" % (arm, rn))
            uart = os.path.join(d, "%s.run%d.uart.log" % (arm, rn))
            if os.path.exists(done):
                vecs.append(json.load(open(done))); continue
            txt, secs = run_fvp(os.path.join(d, "%s.axf" % arm), uart, c["macs"])
            v = extract(txt); v["wall_s"] = secs
            if v["count"] != 1 or (arm == "clean" and v["total"] is None):
                stop("run invalid %s/%s/r%d count=%s total=%s" % (c["cell"], arm, rn, v["count"], v["total"]))
            json.dump(v, open(done, "w")); vecs.append(v)
            log("   [r%d] %s/%s %.0fs" % (rn, c["cell"], arm, secs))
        # RULE_P0E2_REPS_EXACT
        for k in ("total", "active", "idle", "crc", "plprof", "pl_count"):
            if not (vecs[0][k] == vecs[1][k] == vecs[2][k]):
                stop("RULE_P0E2_REPS_EXACT %s/%s field=%s" % (c["cell"], arm, k))
        log("[run] %-44s %-5s x3 exact-equal total=%s pl=%s" %
            (c["cell"], arm, vecs[0]["total"], vecs[0]["pl_count"]))
log("STAGE2_DONE")
