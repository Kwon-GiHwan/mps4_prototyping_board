"""fi101_s013 amendment 2: a measured blob with only its PMCAXI_CHAN knob (header word 16) set, so the AXI bandwidth
events (beats, transactions) count one AXI channel instead of all (TRM PMCAXI_CHAN: CH_SEL[3:0], BW_CH_SEL_EN[10]).

  python3 make_chan_blob.py <in.pmwl> <out.pmwl> <channel name>
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import pmwl  # noqa: E402

BW_CH_SEL_EN = 1 << 10
CHANNELS = {"rd_cmd": 0x0, "rd_ifm": 0x1, "rd_weights": 0x2, "rd_scale_bias": 0x3, "rd_mem2mem": 0x4,
            "rd_ifm_stream": 0x5, "rd_mem2mem_idx": 0x6, "wr_ofm": 0x8, "wr_mem2mem": 0x9}
AXI_CHAN_WORD = pmwl.HEADER_WORDS + pmwl.KNOB_FIELDS.index("axi_chan")


def main(src, dst, channel):
    blob = pathlib.Path(src).read_bytes()
    h = pmwl.parse_header(blob)
    if h["version"] < 2 or h["knobs"][0] != pmwl.OFF:
        raise SystemExit(f"need a v2+ blob with PMCAXI_CHAN off, got version {h['version']} knob 0x{h['knobs'][0]:08x}")
    out = bytearray(blob)
    struct.pack_into("<I", out, 4 * AXI_CHAN_WORD, BW_CH_SEL_EN | CHANNELS[channel])
    assert pmwl.parse_header(bytes(out))["knobs"][0] == BW_CH_SEL_EN | CHANNELS[channel]
    diff = [i for i in range(len(blob)) if blob[i] != out[i]]
    assert diff and all(4 * AXI_CHAN_WORD <= i < 4 * AXI_CHAN_WORD + 4 for i in diff), diff
    pathlib.Path(dst).write_bytes(out)
    print(f"{channel}: word {AXI_CHAN_WORD} = 0x{BW_CH_SEL_EN | CHANNELS[channel]:08x}, {len(diff)} bytes differ")


if __name__ == "__main__":
    main(*sys.argv[1:4])
