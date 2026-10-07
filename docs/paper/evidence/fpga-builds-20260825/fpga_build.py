"""Seven FPGA-specific U85@1024 builds. Provenance only - no board run.

FVP and FPGA binaries are target-specific by MLEK's own contract, so nothing
here is carried over from the FVP artifacts.
"""
import json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, "/tmp/xqbin")
import ccident

KIT = "/opt/arm/ml-embedded-evaluation-kit"
ROOT = "/tmp/fpga"
EPOCH = 1776763519
ARENA = 0x00200000
MODEL_SRC = {
 "rnnoise_INT8": "noise_reduction/rnnoise_INT8.tflite",
 "kws_micronet_m": "kws/kws_micronet_m.tflite",
 "ad_medium_int8": "ad/ad_medium_int8.tflite",
 "vww4_128_128_INT8": "vww/vww4_128_128_INT8.tflite",
 "yolo-fastest_192_face_v4": "object_detection/yolo-fastest_192_face_v4.tflite",
 "mobilenet_v2_1.0_224_INT8": "img_class/mobilenet_v2_1.0_224_INT8.tflite",
 "wav2letter_pruned_int8": "asr/wav2letter_pruned_int8.tflite",
}
ORDER = ["rnnoise_INT8", "kws_micronet_m", "ad_medium_int8", "vww4_128_128_INT8",
         "yolo-fastest_192_face_v4", "mobilenet_v2_1.0_224_INT8", "wav2letter_pruned_int8"]


def env():
    e = dict(os.environ); e["SOURCE_DATE_EPOCH"] = str(EPOCH); return e


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True, env=env())


def sha(p):
    return sh("sha256sum %s" % p).stdout.split()[0] if os.path.exists(p) else None


def build(model, outdir):
    ws = os.path.join(ROOT, model)
    shutil.rmtree(ws, ignore_errors=True)
    vdir = os.path.join(ws, "vela"); os.makedirs(vdir, exist_ok=True)
    src = os.path.join(KIT, "resources_downloaded", MODEL_SRC[model])
    vargs = ("vela --accelerator-config ethos-u85-1024 "
             "--config %s/scripts/vela/default_vela.ini "
             "--system-config Ethos_U85_SYS_DRAM_Mid_1024 --memory-mode Dedicated_Sram "
             "--optimise Performance --output-dir %s %s" % (KIT, vdir, src))
    rv = sh(vargs)
    art = os.path.join(vdir, "%s_vela.tflite" % model)
    if not os.path.exists(art):
        return {"ok": False, "stage": "vela", "log": (rv.stdout + rv.stderr)[-1200:], "ws": ws}
    # CPU fallback must be zero: count operators vela left on the CPU
    summary = rv.stdout + rv.stderr
    cpu_ops = re.search(r"CPU operators\s*=\s*(\d+)", summary)
    bdir = os.path.join(ws, "build-fpga")
    cargs = ("cmake -B %s -S %s "
             "-DCMAKE_TOOLCHAIN_FILE=%s/scripts/cmake/toolchains/bare-metal-gcc.cmake "
             "-DTARGET_PLATFORM=mps4 -DTARGET_SUBSYSTEM=sse-320 "
             "-DFPGA_PLATFORM_SSE_320=ON "                     # required for FPGA
             "-DETHOS_U_NPU_ID=U85 -DETHOS_U_NPU_CONFIG_ID=Z1024 "
             "-DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram -DETHOS_U_NPU_ENABLED=ON "
             "-DUSE_CASE_BUILD=inference_runner "
             "-Dinference_runner_ACTIVATION_BUF_SZ=0x%08X "
             "-Dinference_runner_MODEL_PATH=%s" % (bdir, KIT, KIT, ARENA, art))
    rc = sh(cargs)
    if rc.returncode != 0:
        return {"ok": False, "stage": "configure", "log": (rc.stdout + rc.stderr)[-1500:], "ws": ws}
    rb = sh("cmake --build %s -j $(nproc)" % bdir)
    axf = os.path.join(bdir, "bin", "mlek_inference_runner.axf")
    if rb.returncode != 0 or not os.path.exists(axf):
        return {"ok": False, "stage": "build", "log": (rb.stdout + rb.stderr)[-1500:], "ws": ws}
    gen = sh("ls %s/generated/inference_runner/src/*_vela.tflite.cc" % bdir).stdout.strip().splitlines()
    gen = gen[0] if gen else None
    fpga_flag = sh("grep -E '^FPGA_PLATFORM_SSE_320' %s/CMakeCache.txt" % bdir).stdout.strip()
    cfgid = sh("grep -E '^ETHOS_U_NPU_CONFIG_ID' %s/CMakeCache.txt" % bdir).stdout.strip()
    ta = sh("grep -E '^ETHOS_U_NPU_TIMING_ADAPTER_ENABLED' %s/CMakeCache.txt" % bdir).stdout.strip()
    stamp = sh("arm-none-eabi-strings %s | grep -m1 'Build date:'" % axf).stdout.strip()
    # keep the deployable artifacts
    keep = os.path.join(outdir, "artifacts", model)
    shutil.rmtree(keep, ignore_errors=True)
    shutil.copytree(os.path.join(bdir, "bin"), keep)   # includes the FPGA sectors/ layout
    rec = {"workload": model, "target": "FPGA / Corstone-320 / Ethos-U85 / 1024 MAC",
           "model_src": src, "model_sha256": sha(src),
           "vela_args": vargs, "vela_artifact": os.path.basename(art),
           "vela_sha256": sha(art),
           "vela_cpu_operators": int(cpu_ops.group(1)) if cpu_ops else None,
           "generated_cc_raw_sha256": sha(gen),
           "generated_cc_body_sha256": ccident.body_sha256(open(gen, "rb").read()) if gen else None,
           "axf_sha256": sha(axf), "axf_bytes": os.path.getsize(axf),
           "build_args": cargs, "arena": ARENA,
           "fpga_flag": fpga_flag, "npu_config_id_resolved": cfgid,
           "timing_adapter_cache": ta, "embedded_build_stamp": stamp,
           "source_date_epoch": EPOCH,
           "mlek_commit": "b2c0bb2884698b7328f65c41b7c8c51ca9bec386",
           "kept_artifacts": sorted(os.listdir(keep)),
           "sectors_manifest": sorted(os.listdir(os.path.join(keep, "sectors")))
               if os.path.isdir(os.path.join(keep, "sectors")) else None,
           "ok": True, "ws": ws}
    return rec


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(ROOT, exist_ok=True)
    out = []
    for i, model in enumerate(ORDER, 1):
        t0 = time.monotonic()
        r = build(model, outdir)
        ws = r.pop("ws", None)
        if ws: shutil.rmtree(ws, ignore_errors=True)
        r["elapsed_s"] = round(time.monotonic() - t0, 1)
        out.append(r)
        if not r.get("ok"):
            print("[%d/7] %-28s BUILD_FAILED stage=%s" % (i, model, r.get("stage")), flush=True)
        else:
            print("[%d/7] %-28s axf=%s cpu_ops=%s %s %4.0fs" %
                  (i, model, r["axf_sha256"][:16], r["vela_cpu_operators"],
                   r["fpga_flag"], r["elapsed_s"]), flush=True)
        json.dump(out, open(os.path.join(outdir, "fpga_builds.json"), "w"), indent=1)
    print("FPGA_BUILDS_DONE %d/%d ok" % (sum(1 for r in out if r.get("ok")), len(out)), flush=True)


if __name__ == "__main__":
    main()
