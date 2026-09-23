"""Join Tier A (readback) and Tier B (count) per-event tables into one 171-row record.

  python3 pmu_tiers_join.py evidence/pmu_evsweep/boot1/per_event.csv \
                            evidence/pmu_events/boot2/per_event.csv  out.csv
Pure: no interpretation. Columns are exactly the two tiers' facts side by side.
"""
import csv, sys

COLS = ["ev_type", "name", "in_trm110", "in_driver171",
        "tierA_verdict", "tierA_readback_hex", "tierA_slots_accepted", "tierA_boot", "tierA_app_sha256",
        "tierB_verdict", "tierB_values", "tierB_boot", "tierB_app_sha256",
        "where", "how_tierA", "how_tierB", "board_serial", "fpga_image", "authorization"]


def join(rows_a, rows_b):
    a = {int(r["ev_type"]): r for r in rows_a}
    b = {int(r["ev_type"]): r for r in rows_b}
    if set(a) != set(b):
        raise SystemExit(f"tier tables cover different ids: A-only={sorted(set(a)-set(b))[:5]} B-only={sorted(set(b)-set(a))[:5]}")
    out = []
    for ev in sorted(a):
        ra, rb = a[ev], b[ev]
        if ra["name"] != rb["name"]:
            raise SystemExit(f"name mismatch at {ev}: {ra['name']} vs {rb['name']}")
        out.append({
            "ev_type": ev, "name": ra["name"], "in_trm110": ra["in_trm110"], "in_driver171": ra.get("in_driver171", "True"),
            "tierA_verdict": ra["verdict_p1_slot0"], "tierA_readback_hex": ra["readback_p1_slot0"],
            "tierA_slots_accepted": ra["slots_accepted_p1"], "tierA_boot": ra["boot"], "tierA_app_sha256": ra["app_sha256"],
            "tierB_verdict": rb["verdict"], "tierB_values": rb["values"], "tierB_boot": rb["boot"], "tierB_app_sha256": rb["app_sha256"],
            "where": ra["where"].split(" / NPU")[0] + " / NPU APB 0x50004000",
            "how_tierA": ra["how"], "how_tierB": rb["how"],
            "board_serial": ra["where"].split(" / ")[0], "fpga_image": ra["where"].split(" / ")[1],
            "authorization": ra["authorization"],
        })
    return out


def main(argv):
    ra = list(csv.DictReader(open(argv[1]))); rb = list(csv.DictReader(open(argv[2])))
    rows = join(ra, rb)
    with open(argv[3], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} rows -> {argv[3]}")
    print("tierB verdicts:", dict(Counter(r["tierB_verdict"] for r in rows)))
    print("tierB by TRM membership:", {k: dict(Counter(r["tierB_verdict"] for r in rows if r["in_trm110"] == k)) for k in ("True", "False")})


if __name__ == "__main__":
    main(sys.argv)
