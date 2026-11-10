"""POST_HOC_DESCRIPTIVE (owner request 2026-11-10): output-write beat count under a stated access rule, from the measured
OFM address, shape and strides (Vela register stream, record base addresses). No board run, no fitted factor.

Rule A (the owner's candidate): every pixel's channels are split into chunks of at most 16 bytes starting at channel 0;
each chunk is an independent access; it costs the number of 16-byte-aligned segments it touches; no merging across
chunks. Comparison rules: B = each pixel's whole channel vector is one access; C = the kernel's channel slices
(16 + rest) as accesses; D = the whole tensor as one contiguous stream (bytes / 16, rounded up).

  python3 evidence/stage4/beat_model.py
"""
import json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
# config: (OFM region-1 offset from the register stream, H, W, C, OFM stride X, OFM stride Y, kernel channel slices)
CFG = {"conv_base": (0x0, 24, 24, 96, 0x60, 0x900, (16, 80)), "conv_cout95": (0x0, 24, 24, 95, 0x5F, 0x8E8, (16, 79)),
       "dw_base": (0x0, 56, 56, 144, 0x90, 0x1F80, (16, 128)), "dw_c143": (0x0, 56, 56, 143, 0x8F, 0x1F48, (16, 127))}
MEASURED = {"conv_base": 3456, "conv_cout95": 6660, "dw_base": 28224, "dw_c143": 54488}   # pass B median, event 391


def segs(a, n):
    """16-byte-aligned segments touched by n bytes at address a."""
    return (a + n - 1) // 16 - a // 16 + 1


def region1(cfg):
    raw = json.loads((HERE / "raw" / "conds" / f"s4_{cfg}" / "wfe" / "raw_runs.json").read_text())[1:]
    bases = {x["record"]["base1"] for x in raw}
    assert len(bases) == 1
    return bases.pop()


def count_at(base, h, w, c, sx, sy, chunks_of):
    """The rule's count for an OFM at base with the given shape and strides (no reference to any measurement)."""
    return sum(segs(base + y * sy + x * sx + s, n) for y in range(h) for x in range(w) for s, n in chunks_of(c))


def count(cfg, chunks_of):
    off, h, w, c, sx, sy, _ = CFG[cfg]
    return count_at(region1(cfg) + off, h, w, c, sx, sy, chunks_of)


def rule_a(c):
    return [(s, min(16, c - s)) for s in range(0, c, 16)]


def main():
    out = {}
    for cfg in CFG:
        off, h, w, c, sx, sy, sl = CFG[cfg]
        assert sx == c and sy == w * c, cfg                      # dense NHWC as the strides state
        rule_c = lambda cc, sl=sl: [(0, sl[0]), (sl[0], sl[1])]
        out[cfg] = dict(ofm_address=hex(region1(cfg) + off), A_16B_chunks=count(cfg, rule_a),
                        B_whole_pixel=count(cfg, lambda cc: [(0, cc)]), C_kernel_slices=count(cfg, rule_c),
                        D_contiguous=-(-h * w * c // 16), measured=MEASURED[cfg])
        print(cfg, out[cfg])
    (HERE / "beat_model.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
