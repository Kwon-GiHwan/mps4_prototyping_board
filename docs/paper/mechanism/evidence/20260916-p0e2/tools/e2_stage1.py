#!/usr/bin/env python3
"""P0-E2 stage 1: vela artifacts + debug.xml + verbose log + IRQ instrumentation
for wav2letter_pruned_int8 and mobilenet_v2_1.0_224_INT8, U85 256/512 bindings.
Reuses the frozen P0-D/P0-D2 recipe verbatim. Fail-closed."""
import hashlib, json, os, re, shutil, subprocess, sys

KIT = "/opt/arm/ml-embedded-evaluation-kit"
OUT = "/work/u85e2"
ART = OUT + "/artifacts"
PD  = OUT + "/pd"
EPOCH = "1776763519"

FROZEN_MODEL_SHA = {
    "wav2letter_pruned_int8": "e0814a0e586f2f2881f7fe96e6bc0b8e4cfecc8d64ced56d8f7ca85b9b7ab257",
    "mobilenet_v2_1.0_224_INT8": "bd8d56b80557a5fca7acf14f61e5339285c02810f7d7afa714b9763fc4b86e95",
}
MODEL_SRC = {
    "wav2letter_pruned_int8": "asr/wav2letter_pruned_int8.tflite",
    "mobilenet_v2_1.0_224_INT8": "img_class/mobilenet_v2_1.0_224_INT8.tflite",
}
BINDINGS = [("256_Low", "ethos-u85-256", "Ethos_U85_SYS_DRAM_Low", 256),
            ("512_Mid512", "ethos-u85-512", "Ethos_U85_SYS_DRAM_Mid_512", 512),
            ("512_Low", "ethos-u85-512", "Ethos_U85_SYS_DRAM_Low", 512)]

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          env=dict(os.environ, SOURCE_DATE_EPOCH=EPOCH))

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def stop(m):
    print("STOP:", m, flush=True); sys.exit(2)

def log(*a): print(*a, flush=True)

# --- RULE_P0E2_MODEL_SHA -------------------------------------------------
for model, rel in MODEL_SRC.items():
    src = os.path.join(KIT, "resources_downloaded", rel)
    s = sha256(src)
    if s != FROZEN_MODEL_SHA[model]:
        stop("RULE_P0E2_MODEL_SHA %s: %s" % (model, s))
    log("[sha] %s OK %s" % (model, s[:12]))

os.makedirs(ART, exist_ok=True); os.makedirs(PD, exist_ok=True)
cells = []
for model, rel in MODEL_SRC.items():
    src = os.path.join(KIT, "resources_downloaded", rel)
    for label, acc, syscfg, macs in BINDINGS:
        cell = "%s__%s" % (model, label)
        c = {"cell": cell, "model": model, "label": label, "acc": acc,
             "syscfg": syscfg, "macs": macs, "src": src}
        vdir = os.path.join(ART, cell); os.makedirs(vdir, exist_ok=True)
        art = os.path.join(vdir, "%s_vela.tflite" % model)
        base = ("vela --accelerator-config %s --config %s/scripts/vela/default_vela.ini "
                "--system-config %s --memory-mode Dedicated_Sram --optimise Performance"
                % (acc, KIT, syscfg))
        if not os.path.exists(art):
            r = sh("%s --output-dir %s %s" % (base, vdir, src))
            if r.returncode != 0 or not os.path.exists(art):
                stop("vela failed %s: %s" % (cell, (r.stdout + r.stderr)[-500:]))
        c["art"] = art; c["vela_sha"] = sha256(art)

        d = os.path.join(PD, cell); os.makedirs(d, exist_ok=True)
        # debug db (hash-gated: artifact must be byte-identical)
        dbg = os.path.join(d, "debug.xml")
        if not os.path.exists(dbg):
            td = os.path.join(d, "_db"); shutil.rmtree(td, ignore_errors=True); os.makedirs(td)
            r = sh("%s --enable-debug-db --output-dir %s %s" % (base, td, src))
            a2 = os.path.join(td, "%s_vela.tflite" % model)
            if r.returncode != 0 or not os.path.exists(a2):
                stop("debug-db vela failed %s: %s" % (cell, (r.stdout + r.stderr)[-400:]))
            if sha256(a2) != c["vela_sha"]:
                stop("debug-db artifact mismatch %s" % cell)
            xs = [f for f in os.listdir(td) if f.endswith("_debug.xml")]
            if len(xs) != 1: stop("debug xml count %d %s" % (len(xs), cell))
            os.rename(os.path.join(td, xs[0]), dbg); shutil.rmtree(td, ignore_errors=True)
        # verbose schedule/performance (hash-gated identically)
        vv = os.path.join(d, "vela_verbose"); vlog = os.path.join(vv, "verbose.log")
        if not os.path.exists(vlog):
            shutil.rmtree(vv, ignore_errors=True); os.makedirs(vv)
            r = sh("%s --verbose-schedule --verbose-performance --output-dir %s %s > %s 2>&1"
                   % (base, vv, src, vlog))
            va = os.path.join(vv, "%s_vela.tflite" % model)
            if not os.path.exists(va) or sha256(va) != c["vela_sha"]:
                stop("verbose artifact mismatch %s" % cell)
        # one-hot IRQ instrumentation (P0-D2 path)
        instr = os.path.join(d, "instr_oh.tflite")
        meta_p = os.path.join(d, "instr.meta.json")
        if not os.path.exists(meta_p):
            r = sh("python3 /tmp/insert_irq.py %s %s --all --onehot" % (art, instr))
            if r.returncode != 0:
                stop("insert_irq failed %s: %s" % (cell, (r.stdout + r.stderr)[-400:]))
            m = re.search(r"IRQ-ALL x(\d+)", r.stdout)
            if not m: stop("no IRQ-ALL count %s" % cell)
            json.dump({"profiled": "OK", "irq_count": int(m.group(1)),
                       "instr_sha256": sha256(instr), "encoding": "onehot"},
                      open(meta_p, "w"))
        c["meta"] = json.load(open(meta_p)); c["instr"] = instr
        c["cfg"] = {"acc": acc, "syscfg": syscfg, "macs": macs}
        log("[cell] %-44s vela=%s IRQs=%d" % (cell, c["vela_sha"][:12], c["meta"]["irq_count"]))
        cells.append({k: v for k, v in c.items()})

json.dump(cells, open(OUT + "/cells.json", "w"), indent=1)
log("STAGE1_DONE cells=%d" % len(cells))
