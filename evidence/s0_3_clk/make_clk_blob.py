"""s0_3_clk: a fi101_s013 blob (TA profile 1, word 28 OFF) with the TA counter select (word 28) and optionally the TA
profile (word 27) changed, everything else byte-identical.

  python3 make_clk_blob.py <in.pmwl> <out.pmwl> <sram event> <ext event> [profile]
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import pmwl  # noqa: E402

TA_WORD, SEL_WORD = pmwl.word("ta_profile"), pmwl.word("ta_perfctrl")


def main(src, dst, sram, ext, profile="1"):
    blob = pathlib.Path(src).read_bytes()
    k = pmwl.parse_header(blob)["knobs"]
    if k[TA_WORD - pmwl.HEADER_WORDS] != 1 or k[SEL_WORD - pmwl.HEADER_WORDS] != pmwl.OFF:
        raise SystemExit(f"need a TA profile 1 blob with word {SEL_WORD} OFF")
    ev = pmwl.TA_PERFCTRL_EVENTS
    sel, profile = pmwl.ta_perfctrl_word(ev[sram], ev[ext]), int(profile)
    if profile not in pmwl.TA_PROFILES:
        raise SystemExit(f"profile {profile}: one of {sorted(pmwl.TA_PROFILES)}")
    out = bytearray(blob)
    struct.pack_into("<I", out, 4 * SEL_WORD, sel)
    struct.pack_into("<I", out, 4 * TA_WORD, profile)
    k2 = pmwl.parse_header(bytes(out))["knobs"]
    assert (k2[TA_WORD - pmwl.HEADER_WORDS], k2[SEL_WORD - pmwl.HEADER_WORDS]) == (profile, sel)
    diff = [i for i in range(len(blob)) if blob[i] != out[i]]
    assert diff and all(4 * TA_WORD <= i < 4 * SEL_WORD + 4 for i in diff), diff
    pathlib.Path(dst).write_bytes(out)
    print(f"word {SEL_WORD} = 0x{sel:04X}, word {TA_WORD} = {profile}, {len(diff)} bytes differ")


if __name__ == "__main__":
    main(*sys.argv[1:6])
