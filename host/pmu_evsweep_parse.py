"""Parse and refuse a Tier A EV_TYPE sweep UART capture.

Contract: docs/superpowers/specs/2026-09-23-pmu-evsweep-contract.md.
Pure functions, no serial here. Every refusal carries its rule id.
"""
import re, zlib
from dataclasses import dataclass

BUILD_ID_EVSW = 0x45565357
EXPECTED_LINES = 1024 + 8 * 1024
VERDICTS = ("ACCEPTED", "COERCED_TO_ZERO", "COERCED_OTHER", "UPPER_BITS_SET")
RULES = ("RULE_HDR_MISSING", "RULE_END_MISSING", "RULE_LINE_COUNT", "RULE_CRC",
         "RULE_DUP_CELL", "RULE_BUILD_ID",
         "RULE_NUM_EVENT_CNT")

_HDR = re.compile(r"^EVSWEEP-HDR,([0-9a-f]{8}),([0-9a-f]{8}),([0-9a-f]{8}),(\d+)$")
_EV  = re.compile(r"^EV,([01]),([0-7]),(\d{1,4}),([0-9a-f]{8})$")
_END = re.compile(r"^EVSWEEP-END,(\d+),([0-9a-f]{8})$")


class Refusal(Exception):
    def __init__(self, rule, msg):
        assert rule in RULES; super().__init__(f"{rule}: {msg}"); self.rule = rule


def fail_rule(rule, msg): return Refusal(rule, msg)
def refusal_rule(exc): return exc.rule


@dataclass(frozen=True)
class Header: build_id: int; pmcr: int; config: int; num_event_cnt: int
@dataclass(frozen=True)
class Cell: pass_: int; slot: int; ev: int; readback: int; verdict: str


def verdict(ev, rb):
    lo, hi = rb & 0x3FF, rb >> 10
    if lo == ev and hi == 0: return "ACCEPTED"
    if lo == ev and hi != 0: return "UPPER_BITS_SET"
    if lo == 0 and ev != 0:  return "COERCED_TO_ZERO"
    return "COERCED_OTHER"   # lo != ev and lo != 0: the four verdicts are exhaustive


def parse(text):
    """text: the raw capture. Returns (Header, [Cell]) or raises Refusal."""
    lines = [l.rstrip("\r") for l in text.split("\n")]
    hdr = None; cells = []; seen = set(); crc = 0; end = None
    for l in lines:
        m = _HDR.match(l)
        if m and hdr is None:
            hdr = Header(*(int(x, 16) for x in m.groups()[:3]), int(m.group(4)))
            continue
        m = _EV.match(l)
        if m:
            if hdr is None: raise fail_rule("RULE_HDR_MISSING", "EV line before header")
            p, s, ev, rb = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4), 16)
            key = (p, s, ev)
            if key in seen: raise fail_rule("RULE_DUP_CELL", str(key))
            seen.add(key)
            crc = zlib.crc32((l + "\n").encode("ascii"), crc)
            cells.append(Cell(p, s, ev, rb, verdict(ev, rb)))
            continue
        m = _END.match(l)
        if m and end is None:
            end = (int(m.group(1)), int(m.group(2), 16))
    if hdr is None: raise fail_rule("RULE_HDR_MISSING", "no EVSWEEP-HDR")
    if end is None: raise fail_rule("RULE_END_MISSING", "no EVSWEEP-END")
    if hdr.build_id != BUILD_ID_EVSW:
        raise fail_rule("RULE_BUILD_ID", f"0x{hdr.build_id:08x}")
    if hdr.num_event_cnt != 8:
        raise fail_rule("RULE_NUM_EVENT_CNT", str(hdr.num_event_cnt))
    if len(cells) != end[0] or len(cells) != EXPECTED_LINES:
        raise fail_rule("RULE_LINE_COUNT", f"parsed={len(cells)} footer={end[0]} expected={EXPECTED_LINES}")
    if (crc & 0xFFFFFFFF) != end[1]:
        raise fail_rule("RULE_CRC", f"computed=0x{crc & 0xFFFFFFFF:08x} footer=0x{end[1]:08x}")
    return hdr, cells


def summarize(cells):
    """Preregistered P1 summaries only."""
    p1 = [c for c in cells if c.pass_ == 1]
    per_slot = {s: frozenset(c.ev for c in p1 if c.slot == s and c.verdict == "ACCEPTED") for s in range(8)}
    slot_sets = set(per_slot.values())
    p0 = frozenset(c.ev for c in cells if c.pass_ == 0 and c.verdict == "ACCEPTED")
    p1s = per_slot[0]
    p0_vs_p1 = "EQUAL" if p0 == p1s else ("P0_SUBSET" if p0 < p1s else "DIFFERENT")
    return {"slot_agreement": "AGREE" if len(slot_sets) == 1 else "SLOT_DISAGREEMENT",
            "accepted_p1_slot0": sorted(p1s), "p0_vs_p1": p0_vs_p1}
