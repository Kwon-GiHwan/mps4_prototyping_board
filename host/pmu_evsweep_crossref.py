"""Cross-reference a Tier A cells.csv against the TRM-110 and driver-171 tables.

Emits only what the contract preregistered, plus the per-event provenance
table (where / how each event was measured). Nothing is interpreted here.
"""
import csv, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "ethos_u85_pmu_sources"


def load_tables():
    trm = {int(v): n for v, n, _ in json.loads((SRC / "trm_events_110.json").read_text())}
    drv = {int(v): n for v, n in json.loads((SRC / "driver_events_171.json").read_text())}
    return trm, drv


def accepted_p1(cells):
    """P1, all 8 slots must agree (contract); returns the slot-0 set and agreement."""
    per = {s: frozenset(int(c["ev"]) for c in cells if c["pass"] == "1" and int(c["slot"]) == s
                        and c["verdict"] == "ACCEPTED") for s in range(8)}
    return per[0], ("AGREE" if len(set(per.values())) == 1 else "SLOT_DISAGREEMENT")


def crossref(cells):
    trm, drv = load_tables()
    acc, agree = accepted_p1(cells)
    p0 = frozenset(int(c["ev"]) for c in cells if c["pass"] == "0" and c["verdict"] == "ACCEPTED")
    reserved61 = {v for v in drv if v not in trm}
    all1024 = frozenset(range(1024))
    return {
        "slot_agreement": agree,
        "accepted_count": len(acc),
        "accepted_in_trm110": sorted(acc & set(trm)),
        "trm110_not_accepted": sorted(set(trm) - acc),
        "accepted_in_driver_reserved61": sorted(acc & reserved61),
        "driver_reserved61_not_accepted": sorted(reserved61 - acc),
        "accepted_outside_driver171": sorted(acc - set(drv)),
        "rejected_count": len(all1024 - acc),
        "p0_vs_p1": "EQUAL" if p0 == acc else ("P0_SUBSET" if p0 < acc else "DIFFERENT"),
    }


def per_event_table(cells, prov):
    """One row per named event (TRM or driver): where / how it was measured."""
    trm, drv = load_tables()
    by = {(c["pass"], int(c["slot"]), int(c["ev"])): c for c in cells}
    rows = []
    for ev in sorted(set(trm) | set(drv)):
        c1 = by[("1", 0, ev)]
        rows.append({
            "ev_type": ev, "name": drv.get(ev, trm.get(ev)),
            "in_trm110": ev in trm, "in_driver171": ev in drv,
            "tier": "A-readback",
            "verdict_p1_slot0": c1["verdict"], "readback_p1_slot0": c1["readback_hex"],
            "verdict_p0_slot0": by[("0", 0, ev)]["verdict"],
            "slots_accepted_p1": sum(1 for s in range(8) if by[("1", s, ev)]["verdict"] == "ACCEPTED"),
            "where": f"{prov['board_serial']} / {prov['fpga_image']} / NPU APB 0x50004000 PMEVTYPER[slot]",
            "how": "write EV_TYPE, DSB, read back; PMCR.cnt_en=1 (P1) / =0 (P0); no inference",
            "boot": prov.get("boot", ""), "uart_log_sha256": prov["uart_log_sha256"],
            "app_sha256": prov["app_sha256"], "captured_at_utc": prov["captured_at_utc"],
            "authorization": prov["authorization"],
        })
    return rows


def main(argv):
    ev_dir = pathlib.Path(argv[1])
    cells = list(csv.DictReader((ev_dir / "cells.csv").open()))
    summ = json.loads((ev_dir / "summary.json").read_text())
    prov = dict(summ["provenance"], boot=ev_dir.name)
    x = crossref(cells)
    (ev_dir / "crossref.json").write_text(json.dumps(x, indent=2))
    rows = per_event_table(cells, prov)
    with (ev_dir / "per_event.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(json.dumps({k: (v if not isinstance(v, list) else f"[{len(v)} ids]") for k, v in x.items()}, indent=2))
    print(f"per_event.csv: {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv)
