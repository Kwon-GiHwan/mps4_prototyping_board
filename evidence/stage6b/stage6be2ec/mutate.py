"""Mutation test of the Stage 6B-E2E-C rules (host/analysis/stage6be2ec.py). Each mutation neuters one rule, runs
test_stage6be2ec, requires RED, and restores the file by sha256.

    python3 evidence/stage6b/stage6be2ec/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
A = "host/analysis/stage6be2ec.py"
T = ["test_stage6be2ec"]

MUTATIONS = [
    ("p0 bytes", A, "c = dict(summary_bytes=same_bytes, verdicts=", "c = dict(summary_bytes=True, verdicts="),
    ("p0 verdicts", A, "verdicts=s[\"verdicts\"] == committed.get(\"verdicts\"))", "verdicts=True)"),
    ("p0 npu", A, "c[f\"{cell}_npu\"] = all(met(cell, L)[\"npu_active\"] == want[L] for L in (500, 1000))", "c[f\"{cell}_npu\"] = True"),
    ("p0 le", A, "c[f\"{cell}_le\"] = met(cell, 1000)[\"npu_active\"] - met(cell, 500)[\"npu_active\"] == want[\"le\"]", "c[f\"{cell}_le\"] = True"),
    ("p0 mac", A, "c[f\"{cell}_mac\"] = all(met(cell, L)[\"mac_active\"] == H1UC for L in (500, 1000))", "c[f\"{cell}_mac\"] = True"),
    ("p0 ext", A, "== (want[\"ext_rd\"], want[\"ext_tr\"])", "== (want[\"ext_rd\"], tr(cell, L)[\"ext_rd_trans\"])"),
    ("p0 removed", A, "tr(\"B0\", L)[\"ext_rd_trans\"] - tr(\"B3\", L)[\"ext_rd_trans\"]) == REMOVED", "REMOVED[1]) == REMOVED"),
    ("p0 conservation wr", A, "(\"sram_wr_beats\", \"ext_wr_beats\")))", "))"),
    ("p0 conservation tr", A, "(\"sram_rd_trans\", \"ext_rd_trans\"),\n", ""),
    ("p0 invariant rel", A, "INVARIANT_REL = 0.01", "INVARIANT_REL = 0.05"),
    ("p0 invariant wd", A, "for x in (\"ao_active\", \"wd_active\"))", "for x in (\"ao_active\",))"),
    ("p0 outputs", A, "c[\"outputs_valid\"] = all(", "c[\"outputs_valid\"] = True or all("),
    ("p0 cms", A, "c[\"command_stream_identical\"] = drwl_diff == [(28, 0, 1)]", "c[\"command_stream_identical\"] = True"),
    ("p0 all", A, "return dict(ok=all(c.values()), checks=c)", "return dict(ok=True, checks=c)"),
    ("ev reserved", A, "    if ev not in trm_ids:\n        return \"RESERVED\"", "    if False:\n        return \"RESERVED\""),
    ("ev inconsistent", A, "    if \"INCONSISTENT\" in v:\n        return \"INCONSISTENT_ON_FI101\"", "    if False:\n        return \"INCONSISTENT_ON_FI101\""),
    ("ev nonzero", A, "    if \"COUNTED_NONZERO\" in v:", "    if v:"),
    ("ch write", A, "    if ch == \"wr_ofm\":\n        return \"WRITE_NOT_INTERPRETABLE\"", "    if False:\n        return \"WRITE_NOT_INTERPRETABLE\""),
    ("ch works", A, "return \"READ_FILTER_VERIFIED\" if ch in filter_works else \"UNVERIFIED\"", "return \"READ_FILTER_VERIFIED\""),
    ("drv grep", A, "drv = any(\"PMCAXI\" in", "drv = True or any(\"PMCAXI\" in"),
    ("row per trans", A, "ext_beats_per_trans=rd / tr if tr else None", "ext_beats_per_trans=rd / (tr + 1) if tr else None"),
    ("row knpu", A, "ext_trans_per_knpu=1000 * tr / npu", "ext_trans_per_knpu=tr / npu"),
    ("pair le", A, "d_le = le(a) - le(b)", "d_le = le(a)"),
    ("pair residual", A, "residual_le_per_trans=le(b) / b[500][\"ext_rd_trans\"]", "residual_le_per_trans=le(b) / a[500][\"ext_rd_trans\"]"),
    ("pair same", A, "same_traffic_both_latencies=all(", "same_traffic_both_latencies=True or all("),
    ("res scale", A, "scale = total - fm - w", "scale = total - fm"),
    ("res cms", A, "ch = dict(rd_weights=w, rd_scale_bias=scale, rd_cmd=cms,", "ch = dict(rd_weights=w, rd_scale_bias=scale, rd_cmd=0,"),
    ("copy align", A, "start = (arena_base + ARENA_LEN + SRAM_ALIGN - 1) & ~(SRAM_ALIGN - 1)", "start = arena_base + ARENA_LEN"),
    ("copy fits", A, "fits=base + region0_size <= SRAM_LIMIT)", "fits=True)"),
    ("copy fits strict", A, "fits=base + region0_size <= SRAM_LIMIT)", "fits=base + region0_size < SRAM_LIMIT)"),
    ("status fails", A, "return \"UNAVAILABLE\" if \"FAILS\" in prereqs.values() else \"AVAILABLE\"", "return \"AVAILABLE\""),
    ("disc equal", A, "and predictions.get(\"H-R1\") != predictions.get(\"H-R2\")", ""),
    ("disc none", A, "return predictions.get(\"H-R1\") is not None and", "return"),
    ("gate 1", A, "\"1 controlled variable\": m[\"controlled_variable\"] is not None,", "\"1 controlled variable\": True,"),
    ("gate 2", A, "\"2 different predictions\": discriminating(m[\"predictions\"]),", "\"2 different predictions\": True,"),
    ("gate 3", A, "\"3 verifiable instrumentation\": instr_ok,", "\"3 verifiable instrumentation\": True,"),
    ("gate 4", A, "\"4 not answerable from existing data\": m[\"needs_new_data\"],", "\"4 not answerable from existing data\": True,"),
    ("gate 5 boots", A, "\"5 small budget\": m[\"budget\"][0] <= BUDGET[0] and", "\"5 small budget\":"),
    ("gate 5 runs", A, "and m[\"budget\"][1] <= BUDGET[1]}", "}"),
    ("gate status", A, "return dict(criteria=g, passed=method_status(m[\"prereqs\"]) == \"AVAILABLE\" and all(g.values()))", "return dict(criteria=g, passed=all(g.values()))"),
    ("A disc", A, "\"H-R2\": \"channel bytes = static (weights 174,752 / scale 5,760 / cmd 628)\"}", "\"H-R2\": \"channel bytes differ\"}"),
    ("B fits wired", A, "\"SRAM capacity\": \"VERIFIED_SOURCE\" if fits[\"fits\"] else \"FAILS\",", "\"SRAM capacity\": \"VERIFIED_SOURCE\","),
    ("A cmd prereq", A, "\"VERIFIED_BOARD\" if ch[\"rd_cmd\"] == \"READ_FILTER_VERIFIED\" else \"BOARD_CHECK_REQUIRED\"", "\"VERIFIED_BOARD\""),
    ("v invalid", A, "    if not phase0_ok:\n        return dict(verdict=\"INVALID\", selected=None)", "    if False:\n        return dict(verdict=\"INVALID\", selected=None)"),
    ("v select", A, "sel = min(passed, key=lambda n: (ms[n][\"board_checks\"], (\"B\", \"A\").index(n)))", "sel = passed[0]"),
    ("v nonid", A, "    if not any(m[\"discriminating\"] for m in ms.values()):", "    if False:"),
    ("v order", A, "    if passed:\n", "    if passed and False:\n"),
    ("rerun cleanup", A, "        shutil.rmtree(tmp, ignore_errors=True)", "        pass"),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def green():
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return all(subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                              capture_output=True).returncode == 0 for m in T)


def main():
    if not green():
        print("baseline not GREEN"); return 1
    lines, bad = [], 0
    for mid, rel, old, new in MUTATIONS:
        p = REPO / rel
        before, text = sha(p), p.read_text()
        if text.count(old) != 1:
            lines.append(f"NOT_APPLIED  {mid}  ({rel}: pattern found {text.count(old)}x)"); bad += 1; print(lines[-1]); continue
        p.write_text(text.replace(old, new))
        try:
            g = green()
        finally:
            p.write_text(text)
        restored = sha(p) == before
        bad += g or not restored
        lines.append(f"{'SURVIVED' if g else 'KILLED':12s} {mid}  ({rel}; restored by sha256: {restored})")
        print(lines[-1], flush=True)
    g = green()
    lines.append(f"after restore: {'GREEN' if g else 'RED'}")
    (pathlib.Path(__file__).parent / "mutation.txt").write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if bad or not g else 0


if __name__ == "__main__":
    sys.exit(main())
