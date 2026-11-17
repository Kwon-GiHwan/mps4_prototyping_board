"""Container cross-check of the X3 variant models with the tflite package and the packer's extract_cms (independent of
host/lib/tflite_cop1.py): one ethos-u op, its input-0 buffer = a COP1 whose command stream = <key>.cms.bin, every other
buffer byte-identical to the m7 model, tensors and operator I/O unchanged, and the first len(m7 model) bytes differ only
in the 4-byte Buffer.data offset.
  python3 check_models_container.py <workloads dir> <m7 DRWL dir>"""
import hashlib, json, pathlib, struct, sys
sys.path.insert(0, "/work/s6ex3_src/host/container"); sys.path.insert(0, "/work/s6ex3_src/host/lib")
import tflite
from pack_vela_workload import extract_cms
import drwl

def model_of(b):
    h = drwl.parse(b); return b[h["model_off"]:h["model_off"] + h["model_len"]], h

def info(model):
    m = tflite.Model.GetRootAsModel(model, 0); sg = m.Subgraphs(0)
    assert sg.OperatorsLength() == 1
    op = sg.Operators(0); assert m.OperatorCodes(op.OpcodeIndex()).CustomCode().decode() == "ethos-u"
    bi = sg.Tensors(op.Inputs(0)).Buffer()
    bufs = [m.Buffers(i).DataAsNumpy().tobytes() if m.Buffers(i).DataLength() else b"" for i in range(m.BuffersLength())]
    tens = [(sg.Tensors(i).Name(), sg.Tensors(i).Buffer(), sg.Tensors(i).Type(), sg.Tensors(i).ShapeAsNumpy().tobytes()) for i in range(sg.TensorsLength())]
    io = ([op.Inputs(k) for k in range(op.InputsLength())], [op.Outputs(k) for k in range(op.OutputsLength())])
    return bi, bufs, tens, io

wd, src = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
man = json.loads((wd / "x3_manifest.json").read_text()); bad = 0
for key, v in sorted(man.items()):
    blob = (wd / f"{key}.drwl").read_bytes(); orig_blob = (src / f"{v['model']}.drwl").read_bytes()
    mod, h = model_of(blob); om, oh = model_of(orig_blob)
    bi, bufs, tens, io = info(mod); obi, obufs, otens, oio = info(om)
    cms = extract_cms(bufs[bi]); want = (wd / f"{key}.cms.bin").read_bytes()
    others = all(bufs[i] == obufs[i] for i in range(len(bufs)) if i != bi) and len(bufs) == len(obufs)
    diff = [i for i in range(len(om)) if mod[i] != om[i]]
    ok = (bi == obi and cms == want and hashlib.sha256(cms).hexdigest() == v["cms_sha256"] and others and tens == otens
          and io == oio and h["inputs"] and [blob[o:o+n] for o, n in h["inputs"]] == [orig_blob[o:o+n] for o, n in oh["inputs"]]
          and [blob[o:o+n] for o, n in h["outputs"]] == [orig_blob[o:o+n] for o, n in oh["outputs"]]
          and h["pmu_flags"] == v["pmu_flags"] and h["placement"] == oh["placement"]
          and (v["cond"] == "B0" and diff == [] or v["cond"] != "B0" and len(diff) <= 4 and max(diff) - min(diff) < 4))
    bad += not ok
    print(f"{key}: {'OK' if ok else 'FAIL'} cop1_buffer={bi} other_buffers_equal={others} tensors_equal={tens == otens} "
          f"io_equal={io == oio} changed_bytes_in_original_span={diff} model_len {len(om)}->{len(mod)}")
print("ALL OK" if not bad else f"{bad} FAILED")
