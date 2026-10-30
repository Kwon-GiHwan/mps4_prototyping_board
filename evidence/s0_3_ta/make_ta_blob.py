"""s0_3_ta: a measured blob with only its TA profile knob (header word 27) changed, everything else byte-identical.

  python3 make_ta_blob.py <in.pmwl> <out.pmwl> <profile>
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import pmwl  # noqa: E402

TA_WORD = pmwl.word("ta_profile")


def main(src, dst, profile):
    profile = int(profile)
    if profile not in pmwl.TA_PROFILES:
        raise SystemExit(f"profile {profile}: one of {sorted(pmwl.TA_PROFILES)}")
    blob = pathlib.Path(src).read_bytes()
    k = TA_WORD - pmwl.HEADER_WORDS
    if pmwl.parse_header(blob)["knobs"][k] != 1:
        raise SystemExit(f"need a TA profile 1 blob, got word {TA_WORD} = {pmwl.parse_header(blob)['knobs'][k]}")
    out = bytearray(blob)
    struct.pack_into("<I", out, 4 * TA_WORD, profile)
    assert pmwl.parse_header(bytes(out))["knobs"][k] == profile
    diff = [i for i in range(len(blob)) if blob[i] != out[i]]
    assert diff and all(4 * TA_WORD <= i < 4 * TA_WORD + 4 for i in diff), diff
    pathlib.Path(dst).write_bytes(out)
    print(f"word {TA_WORD} = {profile}, {len(diff)} bytes differ")


if __name__ == "__main__":
    main(*sys.argv[1:4])
