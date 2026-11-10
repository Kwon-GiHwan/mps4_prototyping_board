"""Effective-MAC correction (2026-11-11): every verdict of Stage 5-1 and 5-2 must be unchanged.

Compares the summaries at a git revision (before the correction) with the files in the working tree: config verdicts,
output verdicts, base reproduction, pair verdicts (pass A verdict, opposite-direction flag) and the NPU_ACTIVE /
MAC / traffic values. Only MAC-derived fields may differ. Exit 1 on any difference.

    python3 evidence/stage5_2/verdicts_unchanged.py <git revision>
"""
import json, pathlib, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FILES = ("results/fi101_stage5/summary.json", "results/fi101_stage5_2/summary.json")
MAC_DERIVED = {"expected_by_macs", "mac_change_pct", "cycles_per_mac_change_pct", "macs_per_npu_active",
               "cycles_per_mac", "macs_per_1024_mac_active", "comp", "vela_macs", "metrics"}


def kept(s):
    out = {"base_check": s["base_check"]}
    for c, r in s["configs"].items():
        out[f"config {c}"] = (r.get("verdict"), (r.get("output") or {}).get("verdict"), r.get("same_output_as_base"))
        m = r.get("metrics") or {}
        out[f"counters {c}"] = {k: v for k, v in m.items() if k.startswith(("A_", "B_"))}
    for k, p in s["pairs"].items():
        a = p.get("pass_a", {})
        out[f"pair {k}"] = (p["verdict"], p.get("directions_opposite"), p.get("mac_dpu_exact"),
                            {x: y for x, y in a.items() if x not in MAC_DERIVED})
    return out


def main(rev):
    bad = 0
    for f in FILES:
        old = json.loads(subprocess.run(["git", "show", f"{rev}:{f}"], cwd=REPO, capture_output=True, text=True,
                                        check=True).stdout)
        new = json.loads((REPO / f).read_text())
        a, b = kept(old), kept(new)
        diff = sorted(k for k in a.keys() | b.keys() if json.dumps(a.get(k), sort_keys=True, default=str)
                      != json.dumps(b.get(k), sort_keys=True, default=str))
        print(f, "verdicts and counters unchanged" if not diff else f"DIFFERS: {diff}")
        bad += bool(diff)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1]) else 0)
