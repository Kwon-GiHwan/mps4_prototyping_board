#!/usr/bin/env python3
"""P0-E2 stage 5: build the evidence tree and its manifest.

Mirrors the layout of the two frozen September trees so the same reader works:
run-vectors/, uart-logs/, vela-debug/, misc/, reports/, tools/, manifests/.
"""
import hashlib, json, os, shutil, sys

REPO = "/Users/gihwan/Documents/Projects/mps4_prototyping_board"
SP = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(REPO, "docs/paper/mechanism/evidence/20260916-p0e2")
SRC = os.path.join(SP, "raw")          # unpacked bundle: pd/ per-cell files
VIEW = os.path.join(SP, "viewE2")
MECH = os.path.join(REPO, "docs/paper/mechanism")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    shutil.rmtree(EV, ignore_errors=True)
    for sub in ("run-vectors", "uart-logs", "vela-debug", "misc", "reports",
                "tools", "manifests"):
        os.makedirs(os.path.join(EV, sub))

    cells = sorted(os.listdir(VIEW))
    for cell in cells:
        v = os.path.join(VIEW, cell)
        r = os.path.join(SRC, cell)
        os.makedirs(os.path.join(EV, "run-vectors", cell))
        for arm in ("clean", "prof"):
            for i in (1, 2, 3):
                f = "%s.run%d.json" % (arm, i)
                if os.path.exists(os.path.join(r, f)):
                    shutil.copy2(os.path.join(r, f),
                                 os.path.join(EV, "run-vectors", cell, f))
        shutil.copy2(os.path.join(v, "instr.meta.json"),
                     os.path.join(EV, "run-vectors", cell, "instr.meta.json"))
        os.makedirs(os.path.join(EV, "uart-logs", cell))
        for arm in ("clean", "prof"):
            for i in (1, 2, 3):
                f = "%s.run%d.uart.log" % (arm, i)
                if os.path.exists(os.path.join(r, f)):
                    shutil.copy2(os.path.join(r, f),
                                 os.path.join(EV, "uart-logs", cell, f))
        os.makedirs(os.path.join(EV, "vela-debug", cell, "vela_verbose"))
        shutil.copy2(os.path.join(v, "debug.xml"),
                     os.path.join(EV, "vela-debug", cell, "debug.xml"))
        shutil.copy2(os.path.join(v, "vela_verbose", "verbose.log"),
                     os.path.join(EV, "vela-debug", cell, "vela_verbose", "verbose.log"))
        os.makedirs(os.path.join(EV, "misc", cell))
        shutil.copy2(os.path.join(v, "launches.json"),
                     os.path.join(EV, "misc", cell, "launches.json"))

    for f in ("summary.json", "cells.json", "PRESTATE.sha256", "POSTSTATE.sha256",
              "stage2.log", "gate_report.txt", "mutation_report.txt"):
        p = os.path.join(SP, f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(EV, "reports", f))

    # the orchestrators this campaign ran, plus the September tools it reused
    for f in ("e2_stage1.py", "e2_stage2.py", "e2_stage3.py", "e2_analyze.py",
              "e2_gate_run.py", "mutate.py", "e2_evidence.py"):
        p = os.path.join(SP, f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(EV, "tools", f))
    sep = os.path.join(REPO, "docs/paper/mechanism/evidence")
    for src, name in (
        ("20260902-p0d2-profiled-irqhistory/tools/insert_irq.py", "insert_irq.py"),
        ("20260902-p0d2-profiled-irqhistory/tools/patch_driver_u85_v3.py",
         "patch_driver_u85_v3.py"),
        ("20260902-p0d-formal-clean/tools/patch_app.py", "patch_app.py"),
    ):
        shutil.copy2(os.path.join(sep, src),
                     os.path.join(EV, "tools", "september-" + name))

    lines = []
    for root, dirs, files in os.walk(EV):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            lines.append("%s  ./%s" % (sha256(p), os.path.relpath(p, EV)))
    man = os.path.join(EV, "manifests", "EVIDENCE.sha256")
    open(man, "w").write("\n".join(lines) + "\n")

    derived = {name: sha256(os.path.join(MECH, name)) for name in (
        "U85_FORMAL_MATRIX.csv", "U85_256_512_DIFFERENTIAL.csv",
        "U85_ATTRIBUTION_UNITS.csv", "U85_GROUP_DIFFERENTIAL.csv",
        "U85_OPERATOR_MATCH.csv", "P0E2_RESULTS.md", "P0E2_LIMITATIONS.md")
        if os.path.exists(os.path.join(MECH, name))}
    derived["EVIDENCE.sha256"] = sha256(man)
    json.dump({"campaign": "P0-E2", "date": "2026-09-16",
               "contract": "docs/superpowers/plans/"
                           "2026-09-16-p0e2-two-workload-extension-plan.md",
               "approval": "operator instruction; no manager GO (contract S9)",
               "cells": cells, "derived_sha256": derived},
              open(os.path.join(EV, "manifests", "P0E2_META.json"), "w"), indent=1)
    print("evidence tree:", EV)
    print("manifest entries:", len(lines))
    for k, v in sorted(derived.items()):
        print("  %-32s %s" % (k, v))


if __name__ == "__main__":
    sys.exit(main())
