#!/usr/bin/env python3
"""Shared identity regression (maintenance, 2026-11-17): every raw_runs.json folder on a stage4k.identity path, judged by
the identity functions of the code tree given (before / after the expected-placement change), with the defaults the
historical judges used (no expected placement passed), plus the manifest-driven stage6bb.identity_of for the frozen
manifest entry that names this config and this boot. A config judged from several workload dirs gets them merged
(first dir wins), as its judge did. reproduction-reference folders (ref/wfe) are not on the identity path and are only
counted. E2D's original session (boots 440-442) is also judged with the Amendment A manifest entry of the same config
and latency (the corrected expectation). Output: one JSON per code tree; the report compares them.

  regression.py <code root> <repo root (data)> <out.json>
"""
import atexit
import csv
import json
import pathlib
import shutil
import sys
import tempfile

code, data, out = (pathlib.Path(a).resolve() for a in sys.argv[1:4])
sys.path[:0] = [str(code / "host/analysis"), str(code / "host/lib")]
import stage4k as K          # noqa: E402
import stage4aoe as AOE      # noqa: E402
import stage6bb as BB        # noqa: E402

EXPERIMENTS = {              # experiment raw root -> workload dirs (data repo)
    "evidence/stage4k": ["evidence/stage4k/workloads"],
    "evidence/stage4ao": ["evidence/stage4ao/workloads"],
    "evidence/stage4aoe": ["evidence/stage4aoe/workloads", "evidence/stage4ao/workloads"],
    "evidence/stage4wd": ["evidence/stage4wd/workloads", "evidence/stage4ao/workloads", "evidence/stage4wd/board"],
    "evidence/stage6b/stage6bb": ["evidence/stage6b/stage6bb/workloads"],
    "evidence/stage6b/stage6be1": ["evidence/stage6b/stage6be1/workloads"],
    "evidence/stage6b/stage6be1r": ["evidence/stage6b/stage6be1r/workloads"],
    "evidence/stage6b/stage6be2b": ["evidence/stage6b/stage6be2b/workloads"],
    "evidence/stage6b/stage6be2d": ["evidence/stage6b/stage6be2d/workloads"],
}


def safe(f, *a):
    try:
        return f(*a)
    except Exception as e:  # a folder the function cannot judge is recorded, not skipped
        return dict(error=type(e).__name__ + ": " + str(e)[:120])


def manifests(wl: pathlib.Path) -> list[tuple[str, str, dict]]:
    res = []
    for p in sorted(wl.glob("*manifest*.json")):
        d = json.loads(p.read_text())
        res += [(p.name, k, v) for k, v in d.items() if isinstance(v, dict) and "kind" in v and "config" in v]
    return res


def merged(dirs: list[pathlib.Path]) -> pathlib.Path:
    if len(dirs) == 1:
        return dirs[0]
    tmp = pathlib.Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, tmp, True)
    for d in dirs:
        for f in d.iterdir():
            if f.is_file() and not (tmp / f.name).exists():
                shutil.copy(f, tmp / f.name)
    return tmp


def boot_of(folder: pathlib.Path) -> int | None:
    with open(folder / "runs.csv") as f:
        b = {r["host_boot_index"] for r in csv.DictReader(f)}
    return int(b.pop()) if len(b) == 1 else None


E2D_ORIG = "evidence/stage6b/stage6be2d/raw/"
rows, refs = {}, sorted(str(p.parent.relative_to(data)) for e in EXPERIMENTS
                        for p in (data / e).glob("**/raw_runs.json") if "/conds/" not in str(p))
for exp, wls in EXPERIMENTS.items():
    wlm = merged([data / w for w in wls])
    for raw in sorted((data / exp).glob("**/conds/*/wfe/raw_runs.json")):
        folder, cfg = raw.parent, raw.parent.parent.name
        wl = wlm if (wlm / f"{cfg}.drwl").exists() else None
        rel = str(folder.relative_to(data))
        boot = boot_of(folder)
        r = dict(experiment=exp, cfg=cfg, boot=boot, wl=wls if wl else None)
        if wl is None:
            r["k_identity"] = dict(error="no DRWL for this config in the experiment's workload dirs")
        else:
            r["k_identity"] = safe(K.identity, folder, wl, cfg)
            if (wl / AOE.MANIFEST).exists() and cfg in json.loads((wl / AOE.MANIFEST).read_text()):
                r["identity_a1"] = safe(AOE.identity_a1, folder, wl, cfg)
            for name, key, m in manifests(wl):
                caps = str(wl / m["caps_ref"]) if "caps_ref" in m else None
                lat = "L1000" if "l1000" in rel else "L500"
                rejudge = rel.startswith(E2D_ORIG) and name == "e2d_manifest_a.json" and key.endswith(lat)
                if m["config"] == cfg and (m.get("boot") == boot or rejudge):
                    r[f"identity_of[{name}:{key}]"] = safe(BB.identity_of, folder, wl, cfg, m, caps)
        rows[rel] = r
pathlib.Path(out).write_text(json.dumps(dict(folders=rows, reference_folders=refs), indent=1, sort_keys=True,
                                        default=str))
print(out, len(rows), len(refs))
