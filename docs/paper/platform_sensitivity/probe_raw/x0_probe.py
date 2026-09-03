#!/usr/bin/env python3
"""X0 stage A/B/C probes: FVP inventory, MAC acceptance, Vela option matrix."""
import glob, hashlib, json, os, re, shutil, subprocess, sys, time

KIT = "/opt/arm/ml-embedded-evaluation-kit"
OUT = "/work/u85mech/x0"
os.makedirs(OUT, exist_ok=True)

def sh(c, t=180):
    try:
        return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    except subprocess.TimeoutExpired:
        class R: returncode, stdout, stderr = 124, "", "TIMEOUT"
        return R()

def log(*a): print(*a, flush=True)

# ---------- A. FVP inventory ----------
fvps = {}
cands = sorted(set(glob.glob("/opt/arm/fvp*/models/Linux64*/FVP_Corstone*") +
                   glob.glob("/opt/arm/fvp*/bin/FVP_Corstone*")))
for f in cands:
    name = os.path.basename(f)
    v = sh("%s --version" % f, 60)
    txt = (v.stdout + v.stderr)
    fm = re.search(r"Fast Models\s*\[?([0-9.]+)", txt)
    rt = re.search(r"(?:Model Shell|Simulation) [Vv]ersion\s*([0-9.]+)", txt)
    p = sh("%s --list-params" % f, 120)
    params = p.stdout
    macs = [l.strip() for l in params.splitlines() if "num_macs" in l]
    ta = [l.strip() for l in params.splitlines() if re.search(r"timing|adapter", l, re.I)]
    board = "mps4_board" if "mps4_board" in params else ("mps3_board" if "mps3_board" in params else "?")
    fvps[name] = {"path": f, "fm_version": fm.group(1) if fm else None,
                  "version_banner": txt.strip().splitlines()[:3],
                  "board_ns": board, "num_macs_params": macs,
                  "ta_params": ta, "param_count": len(params.splitlines())}
    log("[FVP]", name, "FM", fvps[name]["fm_version"], "| board", board,
        "| num_macs param:", bool(macs), "| TA params:", len(ta))
json.dump(fvps, open(OUT + "/fvp_inventory.json", "w"), indent=1)

# ---------- B. num_macs acceptance probe ----------
CAND = [32, 64, 100, 128, 256, 512, 1024, 2048]
acc = {}
for name, info in fvps.items():
    mp = None
    for l in info["num_macs_params"]:
        mp = l.split("=")[0].strip()
        break
    if not mp:
        acc[name] = {"param": None, "note": "no num_macs parameter exposed"}
        log("[MAC]", name, "no num_macs param"); continue
    res = {}
    for m in CAND:
        r = sh('%s -C %s=%d --cyclelimit 1 2>&1 | head -20' % (info["path"], mp, m), 90)
        o = r.stdout + r.stderr
        bad = re.search(r"(not a valid|Invalid|out of range|Unsupported|failed to set|Error:)", o, re.I)
        res[m] = "REJECTED" if bad else "ACCEPTED"
    acc[name] = {"param": mp, "results": res}
    log("[MAC]", name, mp, res)
json.dump(acc, open(OUT + "/mac_acceptance.json", "w"), indent=1)

# ---------- C. Vela option enumeration ----------
h = sh("vela --help", 60).stdout
accel = re.search(r"--accelerator-config\s*\{([^}]*)\}", h, re.S)
accels = [x.strip() for x in accel.group(1).split(",")] if accel else []
ini = KIT + "/scripts/vela/default_vela.ini"
secs = [l.strip()[1:-1] for l in open(ini) if l.strip().startswith("[")]
sysc = [s.split(".", 1)[1] for s in secs if s.startswith("System_Config.")]
memm = [s.split(".", 1)[1] for s in secs if s.startswith("Memory_Mode.")]
vela_ver = sh("vela --version", 30).stdout.strip()
json.dump({"vela_version": vela_ver, "accelerator_configs": accels,
           "system_configs": sysc, "memory_modes": memm},
          open(OUT + "/vela_options.json", "w"), indent=1)
log("[VELA]", vela_ver, "| accels", len(accels), "| syscfg", sysc, "| memmodes", memm)

# ---------- D. memory-mode x system-config compile probe ----------
MODEL = KIT + "/resources_downloaded/kws/kws_micronet_m.tflite"
GEN = {"ethos-u55-256": [s for s in sysc if "U55" in s],
       "ethos-u65-256": [s for s in sysc if "U65" in s],
       "ethos-u85-256": [s for s in sysc if "U85" in s and "Low" in s]}
rows = []
for accel_cfg, scs in GEN.items():
    for sc in scs:
        for mm in memm:
            tag = "%s__%s__%s" % (accel_cfg, sc, mm)
            d = os.path.join(OUT, "cmp", tag)
            shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
            r = sh("vela --accelerator-config %s --config %s --system-config %s "
                   "--memory-mode %s --optimise Performance --output-dir %s %s"
                   % (accel_cfg, ini, sc, mm, d, MODEL), 300)
            art = os.path.join(d, "kws_micronet_m_vela.tflite")
            if os.path.exists(art):
                sha = hashlib.sha256(open(art, "rb").read()).hexdigest()
                rows.append({"accelerator_config": accel_cfg, "system_config": sc,
                             "memory_mode": mm, "compile": "OK", "artifact_sha256": sha,
                             "bytes": os.path.getsize(art)})
            else:
                err = (r.stdout + r.stderr)[-200:].replace("\n", " ")
                rows.append({"accelerator_config": accel_cfg, "system_config": sc,
                             "memory_mode": mm, "compile": "FAILED",
                             "artifact_sha256": "", "bytes": 0, "error": err})
            log("[CMP]", tag, rows[-1]["compile"], rows[-1]["artifact_sha256"][:12])
            shutil.rmtree(d, ignore_errors=True)
json.dump(rows, open(OUT + "/vela_memory_matrix.json", "w"), indent=1)
log("DONE_X0_PROBE")
