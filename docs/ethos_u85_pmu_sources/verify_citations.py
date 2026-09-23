#!/usr/bin/env python3
"""Re-check every per-row citation in docs/ETHOS_U85_PMU_REFERENCE.md.

Each event row carries `S1`§`<id>`[=Reserved] · `S8e`:L<n> · `S8x`:L<n>.
This walks those back to the primary sources and fails on any mismatch.

  S1  -> trm_events_110.json   (parsed from 102685_0000_PMEVTYPER0.response.json)
  S8e -> ethosu_interface_u85.h `enum pmu_event`, line n
  S8x -> ethosu_interface_u85.h `EXPAND_PMU_EVENT`, line n

The header is 763KB and is not committed; fetch it first:

  curl -sLO https://gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver/-/raw/\
5f0b9d1e17b245aefc308ee0d5a4543833b96b11/src/ethosu_interface_u85.h

Usage: python3 verify_citations.py <ethosu_interface_u85.h>
Exit 0 = all citations resolve. Exit 1 = at least one does not.
"""
import json, pathlib, re, sys

HEADER_SHA256 = "79aa695a7a35cabfdda83856661ceabb1169d2ece1e08b86c48d2fadd0f09ece"
CITE = re.compile(r"`S1`§`(\d+)`(=Reserved)? · `S8e`:L(\d+) · `S8x`:L(\d+)")


def main(header_path):
    here = pathlib.Path(__file__).parent
    doc = (here.parent / "ETHOS_U85_PMU_REFERENCE.md").read_text().split("\n")
    trm = {v: n for v, n, _ in json.loads((here / "trm_events_110.json").read_text())}
    drv = dict(json.loads((here / "driver_events_171.json").read_text()))
    hdr = pathlib.Path(header_path).read_text().split("\n")

    cited, failures = [], []
    for line in doc:
        m = CITE.search(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        names = [c.strip("`") for c in cells if re.fullmatch(r"`[a-z0-9_]+`", c)]
        ids = [c for c in cells if re.fullmatch(r"\d+", c)]
        if len(names) != 1 or len(ids) != 1:
            failures.append((line[:60], "row does not parse"))
            continue
        name, value = names[0], int(ids[0])
        sid, reserved, le, lx = int(m[1]), bool(m[2]), int(m[3]), int(m[4])
        cited.append(name)

        if sid != value:
            failures.append((name, f"S1 id {sid} != row id {value}"))
        if reserved and value in trm:
            failures.append((name, f"claimed Reserved but TRM documents {value}"))
        if not reserved and trm.get(value) != name:
            failures.append((name, f"TRM {value} is {trm.get(value)!r}, not {name!r}"))
        if drv.get(str(value), drv.get(value)) not in (name, None):
            failures.append((name, f"driver id {value} is {drv.get(value)!r}"))
        if f"PMU_EVENT_{name.upper()} = {value}," not in hdr[le - 1]:
            failures.append((name, f"S8e L{le} -> {hdr[le - 1].strip()!r}"))
        if f"FUNC(pmu_event, {name.upper()})" not in hdr[lx - 1]:
            failures.append((name, f"S8x L{lx} -> {hdr[lx - 1].strip()!r}"))

    uncited = sorted(set(drv.values()) - set(cited))
    if uncited:
        failures.append(("<coverage>", f"{len(uncited)} driver events uncited: {uncited[:5]}"))

    print(f"rows checked   : {len(cited)}")
    print(f"distinct events: {len(set(cited))} / {len(drv)}")
    print(f"failures       : {len(failures)}")
    for name, why in failures:
        print(f"  FAIL {name}: {why}")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
