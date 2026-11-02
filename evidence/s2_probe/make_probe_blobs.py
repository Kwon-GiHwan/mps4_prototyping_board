"""s2_probe blobs from the fi101_s013 blobs (TA profile 1, words 29-30 OFF). Arms:
  lut_id  word 29 = PMCLUT 0xCCCC (counter 0 = event 1)        lut   word 29 = PMCLUT 0x8888 (event 0 AND event 1)
  ctl     unchanged                                             m_none word 30 = 1 (mask_en), command stream unchanged
  m_all   word 30 = 1, PMU_MASK(1) before everything            m_a / m_b  word 30 = 1, kernel ops [0, k) / [k, n)
k = n // 2 (n kernel operations in the command stream).

  python3 make_probe_blobs.py <in.pmwl> <out dir> <model> <arm>...
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import cms  # noqa: E402
import pmwl  # noqa: E402

LUT_WORD, MASK_WORD = pmwl.word("pmclut"), pmwl.word("pmu_mask_en")


def knob(blob, word, value):
    out = bytearray(blob)
    struct.pack_into("<I", out, 4 * word, value)
    return bytes(out)


def make(blob, arm):
    h = pmwl.parse_header(blob)
    k = h["knobs"]
    if k[pmwl.word("ta_profile") - 16] != 1 or k[LUT_WORD - 16] != pmwl.OFF or k[MASK_WORD - 16] != pmwl.OFF:
        raise SystemExit("need a TA profile 1 blob with words 29-30 OFF")
    stream = blob[h["cms_off"]:h["cms_off"] + h["cms_len"]]
    n = len(cms.kernel_offsets(stream))
    if arm == "ctl":
        return blob
    if arm in ("lut_id", "lut"):
        return knob(blob, LUT_WORD, pmwl.pmclut_word(0xCCCC if arm == "lut_id" else 0x8888))
    masked = knob(blob, MASK_WORD, 1)
    new = {"m_none": stream, "m_all": cms.insert(stream, {0: [cms.pmu_mask(1)]}),
           "m_a": cms.gate(stream, 0, n // 2), "m_b": cms.gate(stream, n // 2, n)}[arm]
    return cms.with_cms(masked, new)


def main(src, out, model, *arms):
    blob = pathlib.Path(src).read_bytes()
    for arm in arms:
        b = make(blob, arm)
        h, h0 = pmwl.parse_header(b), pmwl.parse_header(blob)
        changed = [i for i, (x, y) in enumerate(zip(h["knobs"], h0["knobs"])) if x != y]
        pathlib.Path(out, f"{model}.{arm}.pmwl").write_bytes(b)
        print(f"{model}.{arm}: knob words changed {[16 + i for i in changed]}, cms {h0['cms_len']} -> {h['cms_len']} B")


if __name__ == "__main__":
    main(*sys.argv[1:])
