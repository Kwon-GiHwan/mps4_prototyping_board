"""s2_groups blobs from the fi101_s013 blobs (TA profile 1, words 29-30 OFF). Arms:
  m_all       word 30 = 1, PMU_MASK(1) before everything (as 2B-0)
  g_<TYPE>    word 30 = 1, only the kernel ops of that type counted (host/lib/cms.py gate_ops), one arm per type present

  python3 make_group_blobs.py <in.pmwl> <out dir> <model>
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import cms  # noqa: E402
import pmwl  # noqa: E402

LUT_WORD, MASK_WORD = pmwl.word("pmclut"), pmwl.word("pmu_mask_en")


def arms(blob):
    h = pmwl.parse_header(blob)
    k = h["knobs"]
    if k[pmwl.word("ta_profile") - 16] != 1 or k[LUT_WORD - 16] != pmwl.OFF or k[MASK_WORD - 16] != pmwl.OFF:
        raise SystemExit("need a TA profile 1 blob with words 29-30 OFF")
    stream = blob[h["cms_off"]:h["cms_off"] + h["cms_len"]]
    masked = bytearray(blob)
    struct.pack_into("<I", masked, 4 * MASK_WORD, 1)
    types = cms.kernel_types(stream)
    out = {"m_all": cms.with_cms(bytes(masked), cms.insert(stream, {0: [cms.pmu_mask(1)]}))}
    for t in sorted(set(types)):
        ops = {i for i, x in enumerate(types) if x == t}
        out[f"g_{t}"] = cms.with_cms(bytes(masked), cms.gate_ops(stream, ops))
    return out, types


def main(src, out, model):
    blob = pathlib.Path(src).read_bytes()
    made, types = arms(blob)
    for arm, b in made.items():
        pathlib.Path(out, f"{model}.{arm}.pmwl").write_bytes(b)
        n = sum(1 for x in types if f"g_{x}" == arm) if arm != "m_all" else len(types)
        print(f"{model}.{arm}: {n} kernel ops, cms {pmwl.parse_header(b)['cms_len']} B")


if __name__ == "__main__":
    main(*sys.argv[1:4])
