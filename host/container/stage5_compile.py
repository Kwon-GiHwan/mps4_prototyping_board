#!/usr/bin/env python3
"""Stage 5-0 (evidence/stage5/contract.md): compile-only classification of the SRAM workspace budget and strategy
variants, Dedicated_Sram, Vela 5.0.0 (VELA_OPTIONS + one variant's extra options). Runs in the benchmark-runner
container. No board.

  python3 stage5_compile.py <out dir> <name>=<model.tflite>...

Per workload and variant: the Vela summary (applied arena_cache_size, SRAM / DRAM memory used, cycles, MACs), the
Vela output's execution payload (command stream, constant data, fast-scratch and arena sizes, IO offsets: the same
fields the packer and the runner use), CPU-fallback operators, and per kernel the decoded register state. Against the
workload's base variant:
  EXEC_IDENTICAL   command stream, constant data, fast-scratch size, arena size and IO offsets all equal
  MEMORY_ONLY      every kernel's compute signature equal (kind, IFM/OFM shape and depth, OFM block, microblock,
                   kernel size/stride/weight order), only memory placement / data movement differ
  SCHEDULE_CHANGED otherwise (reported as a whole-configuration effect)
"""
import csv, glob, hashlib, json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
import cms_regs  # noqa: E402
from pack_vela_workload import VELA_OPTIONS, inspect_vela  # noqa: E402
from stage4_inventory import tflite_ops  # noqa: E402

VARIANTS = {"base": [], "cache64k": ["--arena-cache-size", "65536"], "cache0": ["--arena-cache-size", "0"],
            "size": ["--optimise", "Size"], "size_cache0": ["--optimise", "Size", "--arena-cache-size", "0"]}
COMPUTE = ("kind", "ifm_depth_m1", "ifm_width0_m1", "ifm_height0_m1", "ofm_width_m1", "ofm_height_m1", "ofm_depth_m1",
           "blk_width_m1", "blk_height_m1", "blk_depth_m1", "acc_format", "kernel_width_m1", "kernel_height_m1",
           "kernel_stride")
MEMORY = ("ifm_region", "ofm_region", "weight_region", "ifm_base0", "ofm_base0", "ifm_stride_x", "ifm_stride_y",
          "ofm_stride_x", "ofm_stride_y", "ifm_precision", "ofm_precision", "weight_length", "weight1_length",
          "weight2_length", "weight3_length", "dma_before")
sha = lambda b: hashlib.sha256(b).hexdigest()


def compile_one(model: str, extra: list) -> dict:
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["vela", model, *VELA_OPTIONS, *extra, "--output-dir", d], capture_output=True, text=True)
        if r.returncode != 0:
            return dict(rc=r.returncode, error=r.stderr[-400:])
        out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        summ = next(csv.DictReader(open(glob.glob(os.path.join(d, "*_summary_*.csv"))[0])))
        info = inspect_vela(out)
        ops = [o[1] for o in tflite_ops(out)]
        ks = cms_regs.kernels(info["cms"])
        vela_sha = sha(open(out, "rb").read())
    return dict(rc=0, arena_cache_size_kib=float(summ["arena_cache_size"]), sram_used_kib=float(summ["sram_memory_used"]),
                dram_used_kib=float(summ["dram_memory_used"]), cycles_npu=int(float(summ["cycles_npu"])),
                cycles_total=int(float(summ["cycles_total"])), nn_macs=int(float(summ["nn_macs"])),
                sram_total_bytes=int(float(summ["sram_total_bytes"])), dram_total_bytes=int(float(summ["dram_total_bytes"])),
                cpu_ops=[o for o in ops if not o.startswith("CUSTOM:ethos-u")], npu_ops=sum(o.startswith("CUSTOM:ethos-u") for o in ops),
                cms_sha256=sha(info["cms"]), const_sha256=sha(info["const"]), fast_size=info["fast_size"],
                arena_size=info["arena_size"], io=dict(ifms=[(e["off"], e["len"]) for e in info["ifms"]],
                                                       ofms=[(e["off"], e["len"]) for e in info["ofms"]]),
                kernels=len(ks), kernel_kinds=sorted({k["kind"] for k in ks}),
                compute_sig=sha(json.dumps([[k[f] for f in COMPUTE] for k in ks]).encode()),
                memory_sig=sha(json.dumps([[k[f] for f in MEMORY] for k in ks]).encode()),
                weight_bytes=sum(sum(k[f] or 0 for f in ("weight_length", "weight1_length", "weight2_length",
                                                         "weight3_length")) for k in ks),
                dma_bytes=sum(sum(x or 0 for x in k["dma_before"]) for k in ks),
                vela_sha256=vela_sha)


def classify(b: dict, v: dict) -> str:
    if v["rc"] != 0 or b["rc"] != 0:
        return "COMPILE_FAILED"
    same = all(b[k] == v[k] for k in ("cms_sha256", "const_sha256", "fast_size", "arena_size", "io"))
    if same:
        return "EXEC_IDENTICAL"
    return "MEMORY_ONLY" if b["compute_sig"] == v["compute_sig"] else "SCHEDULE_CHANGED"


def main(out, *specs):
    o = pathlib.Path(out); o.mkdir(parents=True, exist_ok=True)
    res = {}
    for spec in specs:
        name, model = spec.split("=", 1)
        res[name] = {v: compile_one(model, extra) for v, extra in VARIANTS.items()}
        for v in VARIANTS:
            res[name][v]["class"] = "BASE" if v == "base" else classify(res[name]["base"], res[name][v])
            r = res[name][v]
            print(name, v, r.get("class"), r.get("arena_cache_size_kib"), r.get("sram_used_kib"), r.get("fast_size"),
                  r.get("arena_size"), r.get("kernels"), r.get("cycles_npu"), r.get("nn_macs"), r.get("cpu_ops"), flush=True)
    (o / "stage5_0.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
