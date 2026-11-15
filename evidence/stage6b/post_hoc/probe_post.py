# POST_HOC probe (not part of the Stage 6B classification): which zero-MAC consumer after the Conv keeps the Conv OFM in Sram?
import json, pathlib, sys, tempfile
sys.path.insert(0, "/work/s6b_host/host/container"); sys.path.insert(0, "/work/s6b_host/host/lib"); sys.path.insert(0, "/work/s6b_host/host/analysis")
import stage6b_models as B, stage4ao_models as AO
cands = {c["group"]: c for c in json.load(open("/work/s6b_host/evidence/stage6b/candidates.json"))["candidates"]}
out = []
for gname in sys.argv[1:]:
    c = cands[gname]; src = B.source_conv(c["rep"]["model"], int(c["rep"]["tflite_op_index"]))
    i, w, b, o = src["ifm"], src["w"], src["b"], src["ofm"]
    t = lambda name, x, data=None, **kw: dict(dict(name=name, shape=x["shape"], type=x["type"], data=data, scale=x["scale"], zp=x["zp"], qdim=x["qdim"]), **kw)
    act = B.ACTS[src["activation"]]
    pre = [t("a", i), t("b", i), t("ifm", i), t("weights", w, w["data"]), t("bias", b, b["data"]), t("conv_out", o)]
    preops = [dict(kind="add", ins=[0, 1], outs=[2]), dict(kind="conv", arg=act, ins=[2, 3, 4], outs=[5])]
    variants = {
        "add_self": (pre + [t("ofm", o, scale=[2 * o["scale"][0]])], preops + [dict(kind="add", ins=[5, 5], outs=[6])]),
        "abs": (pre + [t("ofm", o)], preops + [dict(kind="abs", ins=[5], outs=[6])]),
        "add_add": (pre + [t("c", o), t("t", o, scale=[2 * o["scale"][0]]), t("d", o, scale=[2 * o["scale"][0]]), t("ofm", o, scale=[4 * o["scale"][0]])],
                    preops + [dict(kind="add", ins=[5, 6], outs=[7]), dict(kind="add", ins=[7, 8], outs=[9])]),
    }
    for v, (ts, ops) in variants.items():
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / f"{gname}_{v}.tflite"; p.write_bytes(AO.graph(p.stem, ts, ops))
            rows = B.inventory_rows(p)
        conv = [r for r in rows if r.get("npu_op") == "Conv2D"][0]
        out.append(dict(group=gname, variant=v, orig_ofm=c["key"]["ofm_memory"], ofm_memory=conv["ofm_memory"], ofm_format=conv["ofm_format"],
                        ifm_memory=conv["ifm_memory"], ofm_block=conv["ofm_block"], weight_bytes=conv["weight_bytes"], staging=conv["staging_usage"],
                        ops=[(r.get("npu_op"), r.get("cpu")) for r in rows]))
        print(out[-1], flush=True)
json.dump(out, open("/work/s6b_probe_post.json", "w"), indent=1)
