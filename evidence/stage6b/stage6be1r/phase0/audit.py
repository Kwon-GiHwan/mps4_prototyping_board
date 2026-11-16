#!/usr/bin/env python3
"""Stage 6B-E1-R Phase 0: identity audit of the committed E1 record (5537c11). Reads files only; deliberately does not
import host/analysis/stage6be1.py, so the mapping is re-derived from the raw files and the committed digests.

  audit.py <repo root> <out.json>
"""
import csv, hashlib, json, pathlib, re, sys

R = pathlib.Path(sys.argv[1])
E1 = R / "evidence/stage6b/stage6be1"
W = E1 / "workloads"
RAW = E1 / "raw/evsweep_s6be1_run/conds"
SUM = R / "results/fi101_stage6b/stage6be1/stage6be1_summary.json"
README = R / "results/fi101_stage6b/stage6be1/README.md"

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
pred = json.loads((W / "predictions.json").read_text())
man = json.loads((W / "stage6bb_manifest.json").read_text())
summ = {s["config"]: s for s in json.loads(SUM.read_text())["shapes"]}

plans = {}
for f in sorted((E1 / "board").glob("plan_b0*.txt")):
    for line in f.read_text().splitlines():
        if line and not line.startswith("#"):
            b, name = line.split()[:2]
            plans[name] = int(b)

def raw_rows(name):
    return list(csv.DictReader(open(RAW / name / "wfe/runs.csv")))

rows, issues = [], []
for name in sorted(man, key=lambda n: man[n]["order"]):
    rr = raw_rows(name)
    boots = {r["host_boot_index"] for r in rr}
    wl = {r["workload_sha256"] for r in rr}
    model = {r["model_sha256"] for r in rr}
    drwl_file = sha(W / f"{name}.drwl")
    meas = [r for r in rr if int(r["rep"]) >= 2]           # rep 1 of each set = warm-up
    mac = sorted({int(r["event_value"]) for r in meas if r["name"] == "mac_active"})
    n_mac_runs = len({(r["set_id"], r["rep"]) for r in meas if r["name"] == "mac_active"})
    row = dict(name=name, plan_boot=plans.get(name), manifest_boot=man[name]["boot"], raw_boots=sorted(boots),
               drwl_file_sha=drwl_file, manifest_drwl=man[name]["drwl_sha256"], raw_workload=sorted(wl),
               raw_model=sorted(model), mac_measured=mac, mac_measured_runs=n_mac_runs)
    ok = (row["plan_boot"] == row["manifest_boot"] and boots == {str(row["plan_boot"])}
          and wl == {drwl_file} and drwl_file == row["manifest_drwl"] and len(mac) == 1)
    if name in pred:
        p = pred[name]
        h1 = p["mac"]["H1-UC"]
        comp = {k: v for k, v in p["mac"].items() if k != "H1-UC"}
        row.update(pred_drwl=p["drwl_sha256"], pred_vela=p["vela_sha256"], h1_uc=h1,
                   h1_uc_match=bool(mac) and mac[0] == h1,
                   competitors_differing=sorted(k for k, v in comp.items() if v != h1),
                   competitors_matching_measured=sorted(k for k, v in comp.items() if mac and v == mac[0]),
                   kernels=p["kernels"], ublock=p["ublock"], ofm_block=p["ofm_block"], cin_chunks=p["cin_chunks"],
                   summary_mac=summ[name]["measured_mac"], summary_pred=summ[name]["predicted_mac"],
                   summary_status=summ[name]["status"])
        ok = ok and p["drwl_sha256"] == drwl_file and model == {p["vela_sha256"]} and \
            summ[name]["measured_mac"] == mac[0] and summ[name]["predicted_mac"] == h1
    row["consistent"] = ok
    if not ok:
        issues.append(name)
    rows.append(row)

new = [r for r in rows if r["name"] in pred]
dims = [tuple(int(x) for x in re.findall(r"\d+", r["name"])[1:]) for r in new]
readme_rows = [l for l in README.read_text().splitlines() if l.startswith("| ") and re.search(r"Cin\d+ \d+×\d+ o\d+", l)]
out = dict(
    n_new_shapes=len(pred), n_unique_names=len({r["name"] for r in new}),
    n_unique_drwl=len({r["drwl_file_sha"] for r in new}), n_unique_dims=len(set(dims)),
    n_unique_exec=len({(json.dumps(r["kernels"]), json.dumps(r["ublock"]), r["ofm_block"]) for r in new}),
    boots=sorted(b for r in rows for b in r["raw_boots"]), n_conditions=len(rows),
    h1_uc_matches=sum(r["h1_uc_match"] for r in new),
    all_competitors_split=sum(not r["competitors_matching_measured"] for r in new),
    readme_measured_table_rows=[re.search(r"Cin\d+ \d+×\d+ o\d+", l).group(0) for l in readme_rows],
    n_tests_test_stage6be1=len(re.findall(r"^\s+def test_", (R / "host/tests/test_stage6be1.py").read_text(), re.M)),
    commit_message_claim_tests=19, issues=issues, rows=rows)
pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
for r in rows:
    print(r["name"], r["raw_boots"], r["mac_measured"], r.get("h1_uc"), r["mac_measured_runs"], r["consistent"],
          len(r.get("competitors_differing", [])), r.get("competitors_matching_measured"))
