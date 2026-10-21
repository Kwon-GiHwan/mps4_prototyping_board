#!/usr/bin/env python3
"""Pack a Vela-compiled model into a PMWL workload blob for the runner.

Runs where vela, tflite and tflite_runtime exist (the benchmark-runner container).

  python3 pack_vela_workload.py --model kws_micronet_m.tflite --out kws.pmwl --seed 1

Steps: vela (ethos-u85-1024) -> the single ethos-u op's inputs (COP1 payload, read_only,
scratch/scratch_fast sizes) + OfflineMemoryAllocation (IFM/OFM offsets in the arena) ->
deterministic int8 IFM -> reference OFM from tflite_runtime on the ORIGINAL model -> blob.

Blob layout, knob encoding and packing: host/lib/pmwl.py; profile -> knobs: host/lib/mlek_profile.py.
"""
import argparse, glob, hashlib, json, os, pathlib, struct, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import pmwl
from mlek_profile import knob_args, parse_axi_limit, parse_ports

MLEK_INI = "/opt/arm/ml-embedded-evaluation-kit/scripts/vela/default_vela.ini"
# Vela options after the model path = MLEK resources.py run_vela() for ethos-u85-1024 (npu_config.py:
# Dedicated_Sram, Ethos_U85_SYS_DRAM_Mid_1024; arena_cache_size 393216 from the ini). Reproduces MLEK's
# shipped *_vela_Z256.tflite byte for byte when built for ethos-u85-256 / SYS_DRAM_Low.
VELA_OPTIONS = ["--accelerator-config", "ethos-u85-1024", "--optimise", "Performance", "--config", MLEK_INI,
                "--memory-mode", "Dedicated_Sram", "--system-config", "Ethos_U85_SYS_DRAM_Mid_1024"]


COP1 = b"COP1"
DA_OPTIMIZER_CONFIG, DA_COMMAND_STREAM, DA_NOP = 1, 2, 5


def extract_cms(cop):
    """Return the raw NPU command stream from a COP1 driver payload (core-driver semantics)."""
    if cop[:4] != COP1:
        raise ValueError("custom op data does not start with COP1")
    words = struct.unpack("<%dI" % (len(cop) // 4), cop)
    i, cms = 1, None  # word 0 = 'COP1' header (driver action with version fields)
    while i < len(words):
        w = words[i]; cmd = w & 0xFF; length = ((w >> 8) & 0xFF) << 16 | (w >> 16)
        if cmd == DA_OPTIMIZER_CONFIG: i += 1 + 2
        elif cmd == DA_COMMAND_STREAM:
            # core-driver: cms_length = (reserved << 16) | length  (reserved = byte 1, length = upper u16)
            n = ((w >> 8) & 0xFF) << 16 | (w >> 16)
            if cms is not None: raise ValueError("more than one COMMAND_STREAM")
            cms = cop[(i + 1) * 4:(i + 1 + n) * 4]; i += 1 + n
        elif cmd == DA_NOP: i += 1
        else: raise ValueError(f"unknown driver action {cmd} at word {i}")
    if cms is None: raise ValueError("no COMMAND_STREAM in COP1 payload")
    return cms


def inspect_vela(path):
    import tflite
    buf = open(path, "rb").read()
    m = tflite.Model.GetRootAsModel(buf, 0); sg = m.Subgraphs(0)
    if sg.OperatorsLength() != 1:
        raise SystemExit(f"{path}: {sg.OperatorsLength()} ops -- needs exactly one ethos-u op")
    op = sg.Operators(0); oc = m.OperatorCodes(op.OpcodeIndex())
    if not oc.CustomCode() or oc.CustomCode().decode() != "ethos-u":
        raise SystemExit("the single op is not ethos-u")
    t = lambda k: sg.Tensors(op.Inputs(k))
    data = lambda k: m.Buffers(t(k).Buffer()).DataAsNumpy().tobytes() if m.Buffers(t(k).Buffer()).DataLength() else b""
    size = lambda tt: int(__import__("numpy").prod([tt.Shape(j) for j in range(tt.ShapeLength())]))
    # inputs 0-3: command stream, read_only, scratch (arena), scratch_fast; then the IFMs. Outputs: the OFMs.
    if op.InputsLength() < 5 or op.OutputsLength() < 1 or op.InputsLength() - 4 + op.OutputsLength() > pmwl.IO_MAX:
        raise SystemExit(f"expected 5..{4 + pmwl.IO_MAX - 1} inputs / 1.. outputs ({pmwl.IO_MAX} IFMs + OFMs at most), "
                         f"got {op.InputsLength()}/{op.OutputsLength()}")
    offs = {}
    for i in range(m.MetadataLength()):
        md = m.Metadata(i)
        if md.Name().decode() == "OfflineMemoryAllocation":
            raw = m.Buffers(md.Buffer()).DataAsNumpy().tobytes()
            w = struct.unpack("<%di" % (len(raw) // 4), raw)
            offs = {ti: o for ti, o in enumerate(w[3:]) if o >= 0}
    ifm_ts = [op.Inputs(k) for k in range(4, op.InputsLength())]
    ofm_ts = [op.Outputs(k) for k in range(op.OutputsLength())]
    if any(ti not in offs for ti in ifm_ts + ofm_ts):
        raise SystemExit("OfflineMemoryAllocation lacks IFM/OFM offsets")
    io = lambda tis: [dict(name=sg.Tensors(ti).Name().decode(), off=offs[ti], len=size(sg.Tensors(ti))) for ti in tis]
    ins, outs = io(ifm_ts), io(ofm_ts)
    return dict(cms=extract_cms(data(0)), const=data(1), arena_size=size(t(2)), fast_size=size(t(3)),
                ifm_off=ins[0]["off"], ifm_len=ins[0]["len"], ofm_off=outs[0]["off"], ofm_len=outs[0]["len"],
                ifms=ins, ofms=outs, inputs=[(e["off"], e["len"]) for e in ins],
                outputs=[(e["off"], e["len"]) for e in outs])


def reference(model, seed, ifm=None, in_names=None, out_names=None):
    """IFMs (seeded, or the given raw bytes for a one-IFM model) and the tflite_runtime OFMs of the original model
    on them, as lists in the order of in_names / out_names (the Vela op's order; matched by tensor name). The seeded
    IFMs are drawn from one generator in that order, so a one-IFM model gets the same bytes as before."""
    import numpy as np
    from tflite_runtime.interpreter import Interpreter
    it = Interpreter(model_path=model); it.allocate_tensors()
    ins, outs = it.get_input_details(), it.get_output_details()
    by_name = lambda ds, names: [next(d for d in ds if d["name"] == n) for n in names] if names else ds
    try:
        ins, outs = by_name(ins, in_names), by_name(outs, out_names)
    except StopIteration:
        raise SystemExit(f"Vela IFM/OFM names {in_names}/{out_names} not all in the original model") from None
    if ifm is not None and len(ins) != 1:
        raise SystemExit(f"--ifm gives one IFM; the model has {len(ins)}")
    rng = np.random.default_rng(seed)
    xs = []
    for d in ins:
        if ifm is not None:
            x = np.frombuffer(ifm, dtype=d["dtype"]).reshape(d["shape"])
        else:
            x = rng.integers(np.iinfo(d["dtype"]).min, np.iinfo(d["dtype"]).max + 1, size=d["shape"], dtype=d["dtype"])
        it.set_tensor(d["index"], x); xs.append(x.tobytes())
    it.invoke()
    return xs, [it.get_tensor(d["index"]).tobytes() for d in outs]


def check_vela(prof, vela_version):
    """Refuse to pack under a profile whose Vela version or options differ from this packer's."""
    if vela_version != prof["vela"]["version"] or VELA_OPTIONS != prof["vela"]["options"]:
        raise SystemExit(f"Vela {vela_version} {VELA_OPTIONS} != profile {prof['vela']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--axi", help="PMCAXI_CHAN knob, e.g. ext:rd_weights (default OFF)")
    ap.add_argument("--axi-limit", help="AXI outstanding-limit knob, e.g. sram=0x20000,ext=0x20000 (default OFF)")
    ap.add_argument("--power-ctrl", type=lambda x: int(x, 0), help="POWER_CTRL value, e.g. 0 = MLEK driver (default OFF = vendor 2)")
    ap.add_argument("--fast-base", type=lambda x: int(x, 0), help="fast scratch in on-chip SRAM at this address (default OFF = staging)")
    ap.add_argument("--ta-profile", type=int, help="timing adapters: 1 = MLEK sys_dram_mid, 2 = pass-through (default OFF = untouched)")
    ap.add_argument("--ports", help="region ports, e.g. cmd=ext,const=ext,arena=sram,fast=sram (default OFF)")
    ap.add_argument("--profile", help="frozen profile JSON: knobs, seed and Vela from it; no other knob flags")
    ap.add_argument("--ifm", help="raw IFM bytes to use instead of the seeded input (output verification only)")
    ap.add_argument("--golden", help="raw OFM bytes the runner compares against instead of tflite_runtime's")
    a = ap.parse_args()
    profile_sha = None
    if a.profile:
        if any(v is not None for v in (a.axi, a.axi_limit, a.power_ctrl, a.fast_base, a.ta_profile, a.ports)):
            raise SystemExit("--profile fixes every knob; drop the other knob flags")
        raw = open(a.profile, "rb").read(); profile_sha = hashlib.sha256(raw).hexdigest()
        ver = subprocess.run(["vela", "--version"], check=True, capture_output=True, text=True).stdout.strip()
        prof = json.loads(raw); check_vela(prof, ver)
        kargs, a.seed = knob_args(prof), prof["seed"]
    else:
        kargs = dict(axi=a.axi, ports=parse_ports(a.ports), axi_limit=parse_axi_limit(a.axi_limit),
                     power_ctrl=a.power_ctrl, fast_base=a.fast_base, ta_profile=a.ta_profile)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", a.model, *VELA_OPTIONS, "--output-dir", d], check=True, capture_output=True)
        vela_out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        info = inspect_vela(vela_out)
        vela_sha = hashlib.sha256(open(vela_out, "rb").read()).hexdigest()
    ifms, golds = reference(a.model, a.seed, open(a.ifm, "rb").read() if a.ifm else None,
                            [e["name"] for e in info["ifms"]], [e["name"] for e in info["ofms"]])
    tflite_sha = hashlib.sha256(b"".join(golds)).hexdigest()
    if a.golden:
        if len(golds) != 1:
            raise SystemExit(f"--golden gives one OFM; the model has {len(golds)}")
        golds = [open(a.golden, "rb").read()]
    ifm, golden = b"".join(ifms), b"".join(golds)   # hashes below cover every IFM / OFM in IO-table order
    kw = pmwl.knobs(**kargs)
    blob = pmwl.pack(info, ifms, golds, kw)
    open(a.out, "wb").write(blob)
    meta = dict(model=a.model, model_sha256=hashlib.sha256(open(a.model, "rb").read()).hexdigest(),
                vela_sha256=vela_sha, accelerator="ethos-u85-1024",
                system_config="Ethos_U85_SYS_DRAM_Mid_1024", memory_mode="Dedicated_Sram",
                vela_options=VELA_OPTIONS, seed=a.seed, blob_sha256=hashlib.sha256(blob).hexdigest(),
                cms_len=len(info["cms"]), const_len=len(info["const"]), arena_size=info["arena_size"],
                fast_size=info["fast_size"], ifm_off=info["ifm_off"], ifm_len=len(ifm),
                ofm_off=info["ofm_off"], ofm_len=len(golden), total=len(blob),
                **({} if len(ifms) == 1 and len(golds) == 1 else dict(
                    ifms=[dict(e, sha256=hashlib.sha256(x).hexdigest()) for e, x in zip(info["ifms"], ifms)],
                    ofms=[dict(e, sha256=hashlib.sha256(x).hexdigest()) for e, x in zip(info["ofms"], golds)])),
                header_version=pmwl.parse_header(blob)["version"], knobs=[f"0x{w:08x}" for w in kw],
                cms_sha256=hashlib.sha256(info["cms"]).hexdigest(), profile=a.profile, profile_sha256=profile_sha,
                ifm_file=a.ifm, ifm_sha256=hashlib.sha256(ifm).hexdigest(), tflite_ofm_sha256=tflite_sha,
                golden_file=a.golden, golden_sha256=hashlib.sha256(golden).hexdigest(),
                axi=kargs["axi"], ports=kargs["ports"], axi_limit=kargs["axi_limit"], power_ctrl=kargs["power_ctrl"],
                fast_base=kargs["fast_base"], ta_profile=kargs["ta_profile"])
    open(a.out + ".json", "w").write(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
