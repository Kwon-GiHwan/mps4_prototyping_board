"""POST_HOC_DESCRIPTIVE (not a verdict input; written after the Stage 6-M result): TFLite N_MAC per operator family and
model, with Vela's own per-op MAC-cycle estimate beside it, from results/fi101_stage6m/operator_mapping.csv.

    python3 evidence/stage6m/family_breakdown.py results/fi101_stage6m
"""
import collections
import csv
import pathlib
import sys


def family(o: dict) -> str:
    if o["is_target"] == "True":
        return f"1x1 DepthFirst Conv ({o['category']})"
    if o["exec_on"] != "NPU":
        return f"{o['tflite_op']} ({o['exec_on']})"
    return f"{o['tflite_op']} {o['kernel']} {o['traversal']}"


def main(d: str) -> None:
    p = pathlib.Path(d)
    ops = [o for o in csv.DictReader(open(p / "operator_mapping.csv")) if o["n_mac_tflite"]]
    tot = collections.Counter()
    n, vm, k = collections.Counter(), collections.Counter(), collections.Counter()
    for o in ops:
        key = (o["model"], family(o))
        tot[o["model"]] += int(o["n_mac_tflite"])
        n[key] += int(o["n_mac_tflite"]); k[key] += 1
        vm[key] += float(o["vela_mac_cycles"] or 0)
    rows = [dict(model=m, family=f, n_ops=k[(m, f)], n_mac_tflite=v, share=v / tot[m], ideal_cycles=v / 1024,
                 vela_mac_cycles=vm[(m, f)], label="POST_HOC_DESCRIPTIVE")
            for (m, f), v in sorted(n.items(), key=lambda x: (x[0][0], -x[1]))]
    with open(p / "mac_family_breakdown.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1])
