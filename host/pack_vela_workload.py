#!/usr/bin/env python3
"""Pack a Vela-compiled model into a PMWL workload blob for the Tier C runner.

Runs where vela, tflite and tflite_runtime exist (the benchmark-runner container).

  python3 pack_vela_workload.py --model kws_micronet_m.tflite --out kws.pmwl --seed 1

Steps: vela (ethos-u85-1024) -> the single ethos-u op's inputs (COP1 payload, read_only,
scratch/scratch_fast sizes) + OfflineMemoryAllocation (IFM/OFM offsets in the arena) ->
deterministic int8 IFM -> reference OFM from tflite_runtime on the ORIGINAL model -> blob.

Blob (little-endian, 16 u32 header):
  0 magic 'PMWL'  1 version  2 cms_off 3 cms_len 4 const_off 5 const_len
  6 arena_size 7 fast_size 8 ifm_arena_off 9 ifm_len 10 ifm_data_off
  11 ofm_arena_off 12 ofm_len 13 golden_off 14 irq_mask 15 total_len
"""
import argparse, glob, hashlib, json, os, struct, subprocess, sys, tempfile

MAGIC = 0x4C574D50  # 'PMWL'
VERSION = 1
OFF = 0xFFFFFFFF
AXI_CHANNELS = {"rd_cmd": 0, "rd_ifm": 1, "rd_weights": 2, "rd_scale_bias": 3, "rd_mem2mem": 4,
                "rd_ifm_stream": 5, "rd_mem2mem_idx": 6, "wr_ofm": 8, "wr_mem2mem": 9}  # TRM PMCAXI_CHAN.CH_SEL
ATTR_SRAM, ATTR_EXT = 0, 2      # MEM_ATTR indices used for the two ports
MEM_ATTR_SRAM, MEM_ATTR_EXT = 0x0, 0x4   # bit 2 = EXT AXI port


def knobs(axi=None, ports=None):
    """Header v2 words 16..23. axi='ext:rd_weights'; ports={'cmd':'ext','const':'ext','arena':'sram','fast':'sram'}.
    Anything not given is OFF (0xFFFFFFFF) = vendor default (all EXT under USE_AXI_EXT)."""
    k = [OFF] * 8
    if axi:
        port, chan = axi.split(":")
        k[0] = (1 << 8 if port == "ext" else 0) | AXI_CHANNELS[chan]
    if ports:
        idx = lambda r: ATTR_EXT if ports[r] == "ext" else ATTR_SRAM
        k[1] = idx("const") | idx("arena") << 2 | idx("fast") << 4 | ATTR_SRAM << 6   # REGIONCFG, region 3 unused
        k[2] = idx("cmd")                                                              # QCONFIG
        k[3], k[4], k[5], k[6] = MEM_ATTR_SRAM, MEM_ATTR_SRAM, MEM_ATTR_EXT, MEM_ATTR_EXT
    return k
COP1 = b"COP1"
DA_OPTIMIZER_CONFIG, DA_COMMAND_STREAM, DA_NOP = 1, 2, 5


def align(n, a=16): return (n + a - 1) // a * a


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
    if op.InputsLength() != 5 or op.OutputsLength() != 1:
        raise SystemExit(f"expected 5 inputs / 1 output, got {op.InputsLength()}/{op.OutputsLength()}")
    offs = {}
    for i in range(m.MetadataLength()):
        md = m.Metadata(i)
        if md.Name().decode() == "OfflineMemoryAllocation":
            raw = m.Buffers(md.Buffer()).DataAsNumpy().tobytes()
            w = struct.unpack("<%di" % (len(raw) // 4), raw)
            offs = {ti: o for ti, o in enumerate(w[3:]) if o >= 0}
    ifm_t, ofm_t = op.Inputs(4), op.Outputs(0)
    if ifm_t not in offs or ofm_t not in offs:
        raise SystemExit("OfflineMemoryAllocation lacks IFM/OFM offsets")
    return dict(cms=extract_cms(data(0)), const=data(1), arena_size=size(t(2)), fast_size=size(t(3)),
                ifm_off=offs[ifm_t], ifm_len=size(sg.Tensors(ifm_t)),
                ofm_off=offs[ofm_t], ofm_len=size(sg.Tensors(ofm_t)))


def reference(model, seed):
    import numpy as np
    from tflite_runtime.interpreter import Interpreter
    it = Interpreter(model_path=model); it.allocate_tensors()
    ins, outs = it.get_input_details(), it.get_output_details()
    if len(ins) != 1 or len(outs) != 1:
        raise SystemExit(f"original model has {len(ins)} inputs / {len(outs)} outputs -- step 1 needs 1/1")
    rng = np.random.default_rng(seed)
    x = rng.integers(np.iinfo(ins[0]["dtype"]).min, np.iinfo(ins[0]["dtype"]).max + 1,
                     size=ins[0]["shape"], dtype=ins[0]["dtype"])
    it.set_tensor(ins[0]["index"], x); it.invoke()
    return x.tobytes(), it.get_tensor(outs[0]["index"]).tobytes()


def pack(info, ifm, golden, knob_words=None):
    if len(ifm) != info["ifm_len"] or len(golden) != info["ofm_len"]:
        raise SystemExit(f"IFM/OFM size mismatch: {len(ifm)}/{info['ifm_len']}, {len(golden)}/{info['ofm_len']}")
    v2 = knob_words is not None and any(w != OFF for w in knob_words)
    cms_off = 96 if v2 else 64
    const_off = align(cms_off + len(info["cms"]))
    ifm_data_off = align(const_off + len(info["const"]))
    golden_off = align(ifm_data_off + len(ifm))
    total = align(golden_off + len(golden))
    hdr = struct.pack("<16I", MAGIC, 2 if v2 else VERSION, cms_off, len(info["cms"]), const_off, len(info["const"]),
                      info["arena_size"], info["fast_size"], info["ifm_off"], len(ifm), ifm_data_off,
                      info["ofm_off"], len(golden), golden_off, 0xFFFF, total)
    blob = bytearray(total); blob[0:64] = hdr
    if v2:
        blob[64:96] = struct.pack("<8I", *knob_words)
    for off, b in ((cms_off, info["cms"]), (const_off, info["const"]), (ifm_data_off, ifm), (golden_off, golden)):
        blob[off:off + len(b)] = b
    stop = struct.unpack("<I", info["cms"][-4:])[0]
    if stop != 0xFFFF0000:
        raise SystemExit(f"command stream does not end in NPU_OP_STOP mask 0xFFFF (last word 0x{stop:08x})")
    return bytes(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--memory-mode", default="Dedicated_Sram")
    ap.add_argument("--axi", help="PMCAXI_CHAN knob, e.g. ext:rd_weights (default OFF)")
    ap.add_argument("--ports", help="region ports, e.g. cmd=ext,const=ext,arena=sram,fast=sram (default OFF)")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["vela", a.model, "--accelerator-config", "ethos-u85-1024",
                        "--system-config", "Ethos_U85_SYS_DRAM_Low", "--memory-mode", a.memory_mode,
                        "--output-dir", d], check=True, capture_output=True)
        vela_out = glob.glob(os.path.join(d, "*_vela.tflite"))[0]
        info = inspect_vela(vela_out)
        vela_sha = hashlib.sha256(open(vela_out, "rb").read()).hexdigest()
    ifm, golden = reference(a.model, a.seed)
    ports = dict(kv.split("=") for kv in a.ports.split(",")) if a.ports else None
    kw = knobs(a.axi, ports)
    blob = pack(info, ifm, golden, kw)
    open(a.out, "wb").write(blob)
    meta = dict(model=a.model, model_sha256=hashlib.sha256(open(a.model, "rb").read()).hexdigest(),
                vela_sha256=vela_sha, accelerator="ethos-u85-1024", system_config="Ethos_U85_SYS_DRAM_Low",
                memory_mode=a.memory_mode, seed=a.seed, blob_sha256=hashlib.sha256(blob).hexdigest(),
                cms_len=len(info["cms"]), const_len=len(info["const"]), arena_size=info["arena_size"],
                fast_size=info["fast_size"], ifm_off=info["ifm_off"], ifm_len=len(ifm),
                ofm_off=info["ofm_off"], ofm_len=len(golden), total=len(blob),
                header_version=struct.unpack("<I", blob[4:8])[0], knobs=[f"0x{w:08x}" for w in kw],
                axi=a.axi, ports=a.ports)
    open(a.out + ".json", "w").write(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
