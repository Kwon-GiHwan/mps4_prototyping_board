#!/usr/bin/env python3
"""Stage 4 Phase 2 (evidence/stage4/contract.md): build each isolated operator, check from the compile record that it
runs as intended on the NPU, and pack the DRWL for the driver runner. Runs in the benchmark-runner container.

  python3 stage4_compile.py <out dir> <config>...      config: make_op_model.OPS name (s4_*)

Per config: <cfg>.tflite / .json (make_op_model), <cfg>.drwl (+ .json, .tflite_ofm.bin = the CPU reference OFM,
.cms.bin) by pack_vela_workload.py --profile config/fi101_s013.json --format drwl, and <cfg>.compile.json:
  placement  the Vela output holds exactly one operator, the Ethos-U custom op (no CPU fallback)
  schedule   exactly one scheduled operation with cycles, of the expected type; any other scheduled row is a fused
             activation with zero cycles and no command (the debug database)
  kernels    every kernel instruction of the command stream is of the expected NPU kind
  macs       the scheduled MACs = the generator's N_MAC
  same_vela  the debug-db compile and the packer's compile give the same Vela output
plus Vela's block / ublock, estimated cycles (op, NPU, MAC, AO, command), memory areas, weight bytes, cascade.
gate_b = all five checks.
"""
import glob, hashlib, json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib")); sys.path.insert(0, str(HERE.parents[0] / "analysis"))
import cms_timeline  # noqa: E402
import make_op_model as M  # noqa: E402
from pack_vela_workload import VELA_OPTIONS, inspect_vela  # noqa: E402
from stage4_inventory import tables, tflite_ops  # noqa: E402

PROFILE = HERE.parents[1] / "config" / "fi101_s013.json"
EXPECT = {"conv": ("Conv2D", {"CONV"}), "dw": ("DepthwiseConv2D", {"DEPTHWISE"}), "fc": ("FullyConnected", None)}


def check(cfg: str, out: pathlib.Path) -> dict:
    model, meta = M.build(cfg)
    (out / f"{cfg}.tflite").write_bytes(model)
    (out / f"{cfg}.json").write_text(json.dumps(meta, indent=1))
    kind = M.OPS[cfg]["kind"]
    npu_op, kernel_kinds = EXPECT[kind]
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", str(out / f"{cfg}.tflite"), *VELA_OPTIONS, "--output-dir", d, "--enable-debug-db"],
                       check=True, capture_output=True)
        t = tables(glob.glob(os.path.join(d, "*_debug.xml"))[0])
        vela_out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        vops = tflite_ops(vela_out)
        vela_bytes = open(vela_out, "rb").read()
        stream = inspect_vela(vela_out)["cms"]
    working = [p for p in t["perf"] if int(p["npu_cycles"] or 0) > 0 or int(p["mac_count"] or 0) > 0]
    others = [p for p in t["perf"] if p not in working]
    q_ids = {q["scheduled_id"] for q in t["queue"]}
    kinds = [r["type"] for r in cms_timeline.timeline(stream)]
    w = working[0] if len(working) == 1 else {}
    dq = next((r for r in t["perf_debug"] if r["id"] == w.get("id")), {})
    mq = next((r for r in t["perf_debug_main"] if r["id"] == w.get("id")), {})
    subprocess.run([sys.executable, str(HERE / "pack_vela_workload.py"), "--model", str(out / f"{cfg}.tflite"),
                    "--profile", str(PROFILE), "--format", "drwl", "--out", str(out / f"{cfg}.drwl")],
                   check=True, capture_output=True)
    packed = json.loads((out / f"{cfg}.drwl.json").read_text())
    checks = dict(
        placement=len(vops) == 1 and vops[0][1].startswith("CUSTOM:ethos-u"),
        schedule=len(working) == 1 and w["operator"] == npu_op
        and all(int(p["npu_cycles"] or 0) == 0 and p["id"] not in q_ids for p in others),
        kernels=bool(kinds) and (kernel_kinds is None or set(kinds) <= kernel_kinds) and len(set(kinds)) == 1,
        macs=len(working) == 1 and int(w["mac_count"]) == meta["n_mac"],
        same_vela=packed["vela_sha256"] == hashlib.sha256(vela_bytes).hexdigest(),
    )
    hwc = lambda pre, src: "x".join(src.get(f"{pre}_{a}", "") for a in "hwc")
    res = dict(config=cfg, checks=checks, gate_b=all(checks.values()), n_mac=meta["n_mac"],
               vela_ops=[o[1] for o in vops], scheduled=[(p["operator"], p["npu_cycles"]) for p in t["perf"]],
               kernel_kinds=kinds, n_kernels=len(kinds),
               vela_op_cycles=w.get("op_cycles"), vela_npu_cycles=w.get("npu_cycles"),
               vela_mac_cycles=mq.get("mac_cycles"), vela_ao_cycles=mq.get("ao_cycles"),
               vela_cmd_cycles=mq.get("cmd_cycles"), ofm_block=hwc("ofm_block", mq), ifm_block=hwc("ifm_block", mq),
               ofm_ublock=hwc("ofm_ublock", mq), traversal=mq.get("traversal"),
               ifm_memory=dq.get("ifm_memory"), ofm_memory=dq.get("ofm_memory"), ifm_format=dq.get("ifm_format"),
               ofm_format=dq.get("ofm_format"), weight_bytes=dq.get("weight_total_bytes"), cascade=dq.get("cascade"),
               sram_ac=w.get("Sram_ac"), dram_ac=w.get("Dram_ac"), staging_usage=w.get("staging_usage"),
               model_sha256=meta["model_sha256"], vela_sha256=packed["vela_sha256"], cms_sha256=packed["cms_sha256"],
               cms_len=packed["cms_len"], drwl_sha256=packed["blob_sha256"], ifm_sha256=packed["ifm_sha256"],
               cpu_ofm_sha256=packed["golden_sha256"], arena_size=packed["arena_size"],
               vela_version=subprocess.run(["vela", "--version"], capture_output=True, text=True).stdout.strip(),
               vela_options=VELA_OPTIONS, quant=meta["quant"], activation=meta["activation"],
               ifm_shape=meta["input_shape"], ofm_shape=meta["output_shape"], weight_shape=meta["weight_shape"])
    (out / f"{cfg}.compile.json").write_text(json.dumps(res, indent=1))
    return res


def main(out, *cfgs):
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    for c in cfgs:
        r = check(c, o)
        print(c, "GATE_B", "PASS" if r["gate_b"] else "FAIL", r["checks"], r["kernel_kinds"][:3], r["n_kernels"],
              r["vela_npu_cycles"], r["ofm_block"], r["ofm_ublock"], r["ifm_memory"], r["ofm_memory"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
