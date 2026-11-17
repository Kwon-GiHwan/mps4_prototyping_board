#!/usr/bin/env python3
"""Compare two regression.py outputs (before / after). Every identity result must be identical except the expected
change: a folder whose RUNs carry placement 1 under a manifest entry that expects placement 1 (only the `placement`
term may flip, False -> True). Exit 1 on any other difference.

  compare.py <before.json> <after.json> <out.json>
"""
import json
import sys

a, b = (json.load(open(p)) for p in sys.argv[1:3])
fa, fb = a["folders"], b["folders"]
res = dict(folders=len(fa), reference_folders_not_on_identity_path=len(a["reference_folders"]),
           identity_results=sum(len([k for k in v if k.startswith(("k_", "identity"))]) for v in fa.values()),
           same=0, expected_changes=[], unexpected=[], errors=[])
if fa.keys() != fb.keys() or a["reference_folders"] != b["reference_folders"]:
    res["unexpected"].append("folder sets differ")
for folder in sorted(fa.keys() & fb.keys()):
    for fn in sorted(set(fa[folder]) | set(fb[folder])):
        x, y = fa[folder].get(fn), fb[folder].get(fn)
        if isinstance(y, dict) and "error" in y:
            res["errors"].append([folder, fn, y["error"]])
        if x == y:
            res["same"] += 1 if fn.startswith(("k_", "identity")) else 0
            continue
        flips = {c: [x["checks"][c], y["checks"][c]] for c in x.get("checks", {}) if x["checks"][c] != y["checks"].get(c)}
        rest_same = {k: v for k, v in x.items() if k not in ("checks", "ok")} == \
                    {k: v for k, v in y.items() if k not in ("checks", "ok")}
        expected = fn.startswith("identity_of[") and flips == {"placement": [False, True]} and rest_same
        (res["expected_changes"] if expected else res["unexpected"]).append(
            dict(folder=folder, function=fn, ok=[x.get("ok"), y.get("ok")], flips=flips))
res["verdict"] = "REGRESSION_PASS" if not res["unexpected"] else "REGRESSION_FAIL"
open(sys.argv[3], "w").write(json.dumps(res, indent=1, sort_keys=True))
print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()}))
sys.exit(0 if res["verdict"] == "REGRESSION_PASS" else 1)
