"""Stage 2B-3 Phase 3a pilot blobs from the 2B-0b `ctl` blob of a model (= the fi101_s013 blob, TA profile 1, words
29-30 OFF). A and B = host/analysis/s2b3_select.py on the model's timeline (B = A + 1). Arms:
  ctl, ctl2   unchanged (byte copies)
  w_prev, w_A, w_B, w_next   word 30 = 1, cms.gate(stream, k, k + 1) for k = A-1, A, A+1, A+2
  u           word 30 = 1, cms.gate(stream, A-1, A+3): the four windows as one
  w_A_wait / w_B_wait   only for the first of A, B whose setup (after the previous kernel instruction) holds a
              DMA_WAIT or KERNEL_WAIT: as w_A / w_B with PMU_MASK(1) moved to right after the last such wait

  python3 make_window_blobs.py <ctl.pmwl> <timeline.csv> <out dir> <model>
"""
import csv, pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host" / "lib")); sys.path.insert(0, str(ROOT / "host" / "analysis"))
import cms  # noqa: E402
import pmwl  # noqa: E402
import s2b3_select  # noqa: E402

MASK_WORD = pmwl.word("pmu_mask_en")
WAITS = (17, 18)                    # NPU_OP_DMA_WAIT, NPU_OP_KERNEL_WAIT


def last_wait(stream, k):
    """Byte offset right after the last DMA_WAIT/KERNEL_WAIT between kernel op k-1 and kernel op k, or None."""
    lo, hi = cms.boundaries(stream)[k], cms.kernel_offsets(stream)[k]
    waits = [o for o, _, c, op in cms.instructions(stream) if c == 0 and op in WAITS and lo <= o < hi]
    return waits[-1] + 4 if waits else None


def after_wait(stream, k):
    at = {last_wait(stream, k): [cms.pmu_mask(1)], cms.boundaries(stream)[k + 1]: [cms.pmu_mask(0)], 0: [cms.pmu_mask(0)]}
    return cms.insert(stream, at)


def arms(blob, a):
    h = pmwl.parse_header(blob)
    k = h["knobs"]
    if k[pmwl.word("ta_profile") - 16] != 1 or k[pmwl.word("pmclut") - 16] != pmwl.OFF or k[MASK_WORD - 16] != pmwl.OFF:
        raise SystemExit("need a TA profile 1 blob with words 29-30 OFF")
    stream = blob[h["cms_off"]:h["cms_off"] + h["cms_len"]]
    masked = bytearray(blob)
    struct.pack_into("<I", masked, 4 * MASK_WORD, 1)
    put = lambda s: cms.with_cms(bytes(masked), s)
    out = dict(ctl=blob, ctl2=blob, u=put(cms.gate(stream, a - 1, a + 3)))
    out.update({name: put(cms.gate(stream, a + d, a + d + 1))
                for name, d in (("w_prev", -1), ("w_A", 0), ("w_B", 1), ("w_next", 2))})
    for name, op in (("w_A_wait", a), ("w_B_wait", a + 1)):
        if last_wait(stream, op) is not None:
            out[name] = put(after_wait(stream, op))
            break
    return out


def main(src, timeline, out, model):
    a, b, c = s2b3_select.select([int(r["macs"]) for r in csv.DictReader(open(timeline))])
    for arm, blob in arms(pathlib.Path(src).read_bytes(), a).items():
        pathlib.Path(out, f"{model}.{arm}.pmwl").write_bytes(blob)
        print(f"{model}.{arm}: A={a} B={b} cms {pmwl.parse_header(blob)['cms_len']} B")


if __name__ == "__main__":
    main(*sys.argv[1:5])
