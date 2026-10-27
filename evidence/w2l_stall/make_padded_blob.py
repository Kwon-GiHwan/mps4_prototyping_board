"""Test C1 of the wav2letter stall: a working blob whose S DRAM footprint is stretched to wav2letter's.

Zero padding is appended to the blob and const_len grows to the new end, so the runner's const copy spans
14.5 MB and the arena lands where wav2letter's did (0x70ED2C00). The command stream, constants, IFM and golden
bytes are unchanged and the NPU reads constants only at their original offsets; what moves is the arena (NPU
reads and writes) and the CPU copy range.

  python3 make_padded_blob.py <in.pmwl> <out.pmwl>
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "host" / "lib"))
import pmwl  # noqa: E402

EXT_DRAM_BASE = 0x70100000
W2L_CMS_LEN, W2L_CONST_LEN = 5632, 14488640   # evidence/x1_mlek_models/manifest.x1.json


def al256(n):
    return (n + 255) & ~255


def main(src, dst):
    blob = pathlib.Path(src).read_bytes()
    h = pmwl.parse_header(blob)
    arena_base = EXT_DRAM_BASE + al256(W2L_CMS_LEN) + al256(W2L_CONST_LEN)
    const_len = arena_base - EXT_DRAM_BASE - al256(h["cms_len"])
    total = h["const_off"] + const_len
    if total < len(blob) or total > 0x01000000:
        raise SystemExit(f"new total {total} outside [{len(blob)}, 16 MiB]")
    out = bytearray(blob) + bytes(total - len(blob))
    struct.pack_into("<I", out, 4 * pmwl.HEADER_FIELDS.index("const_len"), const_len)
    struct.pack_into("<I", out, 4 * pmwl.HEADER_FIELDS.index("total_len"), total)
    g = pmwl.parse_header(bytes(out))
    assert out[:len(blob)][64:] == blob[64:], "only header words may change in the original bytes"
    placed = EXT_DRAM_BASE + al256(g["cms_len"]) + al256(g["const_len"])
    assert placed == arena_base, hex(placed)
    pathlib.Path(dst).write_bytes(out)
    print(f"const_len {h['const_len']} -> {const_len}, total {len(blob)} -> {total}, arena at 0x{placed:08X}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
