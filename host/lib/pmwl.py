"""PMWL workload blob format: header and knob word layout, knob encoding, packing, header parsing.

The runner firmware declares the same layout independently (firmware/patches/patch_pmu_events_source.py);
host/tests/test_pmwl_firmware_contract.py asserts the two agree. Neither imports the other.

Blob (little-endian u32 words):
  words  0..15  header (HEADER_FIELDS)
  words 16..31  knobs  (KNOB_FIELDS; OFF = leave the vendor/reset state). Present from header version 2
                (words 16..23) / 3 (words 16..31); the packer picks the smallest version that holds the knobs.
  words 32..63  IO table, version 4 only (a model with more than one IFM or OFM): n_in, n_out, then
                (arena_off, len, data_off) per IFM and (arena_off, len, golden_off) per OFM, unused words 0.
                Entry 0 of each list repeats the header's IFM / OFM words. Versions 1-3 hold one IFM and one OFM.
  then cms, const, IFM data, reference OFM, each 16-byte aligned (version 4: every IFM, then every OFM).
"""
from __future__ import annotations

import struct

MAGIC = 0x4C574D50  # 'PMWL'
OFF = 0xFFFFFFFF
HEADER_WORDS = 16
KNOB_WORDS = 16

HEADER_FIELDS = ("magic", "version", "cms_off", "cms_len", "const_off", "const_len", "arena_size", "fast_size",
                 "ifm_arena_off", "ifm_len", "ifm_data_off", "ofm_arena_off", "ofm_len", "golden_off",
                 "irq_mask", "total_len")
KNOB_FIELDS = ("axi_chan", "regioncfg", "qconfig", "mem_attr0", "mem_attr1", "mem_attr2", "mem_attr3",
               "axi_sram", "axi_ext", "power_ctrl", "fast_base", "ta_profile")   # words 16.., rest reserved
V2_KNOBS = 7   # version 2 carries knob words 16..23 (axi_chan..mem_attr3 + word 23 reserved in v2)
IO_WORD = HEADER_WORDS + KNOB_WORDS   # version 4 IO table starts here
IO_MAX = 10                           # IFMs + OFMs per blob
IO_WORDS = 2 + 3 * IO_MAX


def word(name: str) -> int:
    """Absolute header word index of a header or knob field."""
    if name in HEADER_FIELDS:
        return HEADER_FIELDS.index(name)
    return HEADER_WORDS + KNOB_FIELDS.index(name)


# TRM PMCAXI_CHAN.CH_SEL
AXI_CHANNELS = {"rd_cmd": 0, "rd_ifm": 1, "rd_weights": 2, "rd_scale_bias": 3, "rd_mem2mem": 4,
                "rd_ifm_stream": 5, "rd_mem2mem_idx": 6, "wr_ofm": 8, "wr_mem2mem": 9}
ATTR_SRAM, ATTR_EXT = 0, 2                 # MEM_ATTR indices used for the two ports
MEM_ATTR_SRAM, MEM_ATTR_EXT = 0x0, 0x4     # bit 2 = EXT AXI port
AXI_LIMIT_FIELDS = 0x31F3F                 # TRM AXI_SRAM / AXI_EXT writable bits
POWER_CTRL_MASK = 0x3F                     # POWER_CTRL.mac_step_cycles
ONCHIP_SRAM = (0x31000000, 0x31400000)     # runner lnk.ld SRAM ORIGIN, ORIGIN + LENGTH

# NPU timing adapters (FI101; MLEK platform mps4: TA_SRAM_BASE / TA_EXT_BASE; core-platform timing_adapter.c).
TA_BASE = {"sram": 0x51102000, "ext": 0x51102400}
TA_VERSION = 0x1117
TA_REGS = (("maxr", 0x00), ("maxw", 0x04), ("maxrw", 0x08), ("rlatency", 0x0C), ("wlatency", 0x10),
           ("pulse_on", 0x14), ("pulse_off", 0x18), ("bwcap", 0x1C), ("perfctrl", 0x20), ("mode", 0x28),
           ("histbin", 0x30))   # written by profile, in this order; values pre-masked
TA_PROFILES = {
    1: {  # MLEK ta_config_u85_sys_dram_mid, Dedicated_Sram branch (EXT MAXR 64 & 0x3F = 0)
        "sram": dict(maxr=8, maxw=8, maxrw=0, rlatency=32, wlatency=32, pulse_on=3999, pulse_off=1, bwcap=4000,
                     perfctrl=0, mode=1, histbin=0),
        "ext": dict(maxr=0, maxw=32, maxrw=0, rlatency=500, wlatency=250, pulse_on=4000, pulse_off=1000,
                    bwcap=3750, perfctrl=0, mode=1, histbin=0)},
    2: {  # pass-through: no limits, no added latency, full speed
        "sram": dict(maxr=0, maxw=0, maxrw=0, rlatency=0, wlatency=0, pulse_on=0xFFFF, pulse_off=0, bwcap=0,
                     perfctrl=0, mode=1, histbin=0),
        "ext": dict(maxr=0, maxw=0, maxrw=0, rlatency=0, wlatency=0, pulse_on=0xFFFF, pulse_off=0, bwcap=0,
                    perfctrl=0, mode=1, histbin=0)},
}


def knobs(axi=None, ports=None, axi_limit=None, power_ctrl=None, fast_base=None, ta_profile=None) -> list[int]:
    """Knob words 16..31. axi='ext:rd_weights'; ports={'cmd':'ext','const':'ext','arena':'sram','fast':'sram'};
    axi_limit={'sram': 0x20F0B, 'ext': 0x21F3F}. Anything not given is OFF."""
    k = [OFF] * KNOB_WORDS
    at = lambda name: KNOB_FIELDS.index(name)
    if axi:
        port, chan = axi.split(":")
        k[at("axi_chan")] = (1 << 8 if port == "ext" else 0) | AXI_CHANNELS[chan]
    if ports:
        idx = lambda r: ATTR_EXT if ports[r] == "ext" else ATTR_SRAM
        k[at("regioncfg")] = idx("const") | idx("arena") << 2 | idx("fast") << 4 | ATTR_SRAM << 6  # region 3 unused
        k[at("qconfig")] = idx("cmd")
        for i, v in enumerate((MEM_ATTR_SRAM, MEM_ATTR_SRAM, MEM_ATTR_EXT, MEM_ATTR_EXT)):
            k[at(f"mem_attr{i}")] = v
    if axi_limit:
        for port in ("sram", "ext"):
            if port in axi_limit:
                v = axi_limit[port]
                if v & ~AXI_LIMIT_FIELDS:
                    raise SystemExit(f"AXI_{port.upper()} 0x{v:x} sets reserved bits")
                k[at(f"axi_{port}")] = v
    if power_ctrl is not None:   # runner hook; read back at the CPM seam
        if not 0 <= power_ctrl <= POWER_CTRL_MASK:
            raise SystemExit(f"POWER_CTRL 0x{power_ctrl:x} outside the 6-bit mac_step_cycles field")
        k[at("power_ctrl")] = power_ctrl
    if fast_base is not None:    # fast scratch base in on-chip SRAM; the runner also checks range/port
        if fast_base & 0xFF or not ONCHIP_SRAM[0] <= fast_base < ONCHIP_SRAM[1]:
            raise SystemExit(f"fast base 0x{fast_base:x}: must be 256-aligned inside on-chip SRAM "
                             f"0x{ONCHIP_SRAM[0]:08X}-0x{ONCHIP_SRAM[1] - 1:08X}")
        if ports is None or ports.get("fast") != "sram":
            raise SystemExit("--fast-base needs --ports with fast=sram (on-chip SRAM is behind the SRAM port)")
        k[at("fast_base")] = fast_base
    if ta_profile is not None:
        if ta_profile not in TA_PROFILES:
            raise SystemExit(f"TA profile {ta_profile}: one of {sorted(TA_PROFILES)}")
        k[at("ta_profile")] = ta_profile
    return k


def align(n: int, a: int = 16) -> int:
    return (n + a - 1) // a * a


def pack(info: dict, ifm, golden, knob_words: list[int] | None = None) -> bytes:
    """info: cms, const, arena_size, fast_size and either ifm_off/ofm_off (one IFM, one OFM; ifm and golden are
    bytes) or inputs/outputs = [(arena_off, len)] (ifm and golden are lists of bytes, one per entry).
    One IFM and one OFM give header version 1-3, byte for byte as before; more give version 4."""
    ins = info.get("inputs") or [(info["ifm_off"], info["ifm_len"])]
    outs = info.get("outputs") or [(info["ofm_off"], info["ofm_len"])]
    ifms = [ifm] if isinstance(ifm, (bytes, bytearray)) else list(ifm)
    golds = [golden] if isinstance(golden, (bytes, bytearray)) else list(golden)
    if len(ifms) != len(ins) or len(golds) != len(outs):
        raise SystemExit(f"IFM/OFM count mismatch: {len(ifms)}/{len(ins)}, {len(golds)}/{len(outs)}")
    if len(ins) + len(outs) > IO_MAX:
        raise SystemExit(f"{len(ins)} IFMs + {len(outs)} OFMs > {IO_MAX}")
    for (off, n), b in zip(ins + outs, ifms + golds):
        if len(b) != n:
            raise SystemExit(f"IFM/OFM size mismatch: {len(b)} bytes for a {n}-byte tensor")
        if off + n > info["arena_size"]:
            raise SystemExit(f"tensor at arena offset {off} + {n} outside the {info['arena_size']}-byte arena")
    kw = list(knob_words or [OFF] * KNOB_WORDS) + [OFF] * (KNOB_WORDS - len(knob_words or []))
    v4 = len(ins) + len(outs) > 2
    v3 = v4 or any(w != OFF for w in kw[V2_KNOBS:KNOB_WORDS])
    v2 = v3 or any(w != OFF for w in kw[0:V2_KNOBS])
    knob_bytes = 4 * KNOB_WORDS if v3 else (32 if v2 else 0)
    cms_off = 4 * HEADER_WORDS + knob_bytes + (4 * IO_WORDS if v4 else 0)
    const_off = align(cms_off + len(info["cms"]))
    data_offs, off = [], align(const_off + len(info["const"]))
    for b in ifms + golds:
        data_offs.append(off); off = align(off + len(b))
    total = off
    ents = [(a, n, d) for (a, n), d in zip(ins + outs, data_offs)]
    fi, fo = ents[0], ents[len(ins)]
    fields = dict(magic=MAGIC, version=4 if v4 else (3 if v3 else (2 if v2 else 1)), cms_off=cms_off,
                  cms_len=len(info["cms"]), const_off=const_off, const_len=len(info["const"]),
                  arena_size=info["arena_size"], fast_size=info["fast_size"],
                  ifm_arena_off=fi[0], ifm_len=fi[1], ifm_data_off=fi[2], ofm_arena_off=fo[0], ofm_len=fo[1],
                  golden_off=fo[2], irq_mask=0xFFFF, total_len=total)
    blob = bytearray(total)
    blob[0:4 * HEADER_WORDS] = struct.pack(f"<{HEADER_WORDS}I", *(fields[f] for f in HEADER_FIELDS))
    if knob_bytes:
        blob[4 * HEADER_WORDS:4 * HEADER_WORDS + knob_bytes] = struct.pack("<%dI" % (knob_bytes // 4),
                                                                        *kw[:knob_bytes // 4])
    if v4:
        table = [len(ins), len(outs)] + [w for e in ents for w in e]
        struct.pack_into(f"<{IO_WORDS}I", blob, 4 * IO_WORD, *(table + [0] * (IO_WORDS - len(table))))
    for off, b in [(cms_off, info["cms"]), (const_off, info["const"])] + list(zip(data_offs, ifms + golds)):
        blob[off:off + len(b)] = b
    stop = struct.unpack("<I", info["cms"][-4:])[0]
    if stop != 0xFFFF0000:
        raise SystemExit(f"command stream does not end in NPU_OP_STOP mask 0xFFFF (last word 0x{stop:08x})")
    return bytes(blob)


def parse_header(blob: bytes) -> dict:
    """Header fields by name, plus 'knobs' (16 words, OFF where the version does not carry them) and 'inputs' /
    'outputs' (one entry each before version 4). Refuses an IO table the runner would refuse."""
    if len(blob) < 4 * HEADER_WORDS:
        raise ValueError("blob shorter than the PMWL header")
    h = dict(zip(HEADER_FIELDS, struct.unpack_from(f"<{HEADER_WORDS}I", blob, 0)))
    if h["magic"] != MAGIC:
        raise ValueError(f"not a PMWL blob (magic 0x{h['magic']:08x})")
    n = {1: 0, 2: 8, 3: KNOB_WORDS, 4: KNOB_WORDS}.get(h["version"])
    if n is None:
        raise ValueError(f"unknown PMWL version {h['version']}")
    k = list(struct.unpack_from(f"<{n}I", blob, 4 * HEADER_WORDS)) + [OFF] * (KNOB_WORDS - n)
    if h["version"] == 2:
        k[V2_KNOBS] = OFF   # v2 word 23 was reserved (firmware does the same)
    h["knobs"] = k
    first_in = (h["ifm_arena_off"], h["ifm_len"], h["ifm_data_off"])
    first_out = (h["ofm_arena_off"], h["ofm_len"], h["golden_off"])
    if h["version"] == 4:
        t = struct.unpack_from(f"<{IO_WORDS}I", blob, 4 * IO_WORD)
        n_in, n_out = t[0], t[1]
        if n_in < 1 or n_out < 1 or n_in + n_out > IO_MAX:
            raise ValueError(f"IO table: {n_in} IFMs, {n_out} OFMs")
        ents = [t[2 + 3 * i:5 + 3 * i] for i in range(n_in + n_out)]
        if ents[0] != first_in or ents[n_in] != first_out:
            raise ValueError("IO table entry 0 differs from the header's IFM/OFM words")
    else:
        n_in, ents = 1, [first_in, first_out]
    for a, ln, d in ents:
        if a + ln > h["arena_size"] or d + ln > h["total_len"]:
            raise ValueError(f"IO entry ({a}, {ln}, {d}) outside the arena or the blob")
    h["inputs"] = [dict(arena_off=a, len=ln, data_off=d) for a, ln, d in ents[:n_in]]
    h["outputs"] = [dict(arena_off=a, len=ln, golden_off=d) for a, ln, d in ents[n_in:]]
    return h
