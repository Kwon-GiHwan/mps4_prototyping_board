#!/usr/bin/env python3
"""P0-E2 stage 4: analysis over the extended view.

pd_analyzer.py and pd_groups.py are run UNMODIFIED. The only thing this driver
changes is the analyzer's workload list, which it sets on the imported module
rather than editing the file, so the frozen tool's digest is unchanged and the
widening is visible in one place. No new aggregation rule is introduced.

Regression: the five existing workloads' rows must come back unchanged. For
three of the four CSVs that is a byte comparison. U85_GROUP_DIFFERENTIAL.csv is
compared row-wise instead, because pd_groups.py orders its rows through a set
of strings and therefore emits a different byte sequence on every interpreter
run; see P0E2_LIMITATIONS.md.
"""
import csv, hashlib, io, json, os, shutil, subprocess, sys

REPO = "/Users/gihwan/Documents/Projects/mps4_prototyping_board"
MECH = os.path.join(REPO, "docs/paper/mechanism")
SP = os.path.dirname(os.path.abspath(__file__))
FROZEN_VIEW = os.path.join(SP, "view5")      # 6 September workloads
NEW_VIEW = os.path.join(SP, "viewE2")        # 2 P0-E2 workloads
ROOT = os.path.join(SP, "view8")             # the union the analyzer sees

NEW_WORKLOADS = ["wav2letter_pruned_int8", "mobilenet_v2_1.0_224_INT8"]
EXISTING = ["ad_medium_int8", "kws_micronet_m", "rnnoise_INT8",
            "vww4_128_128_INT8", "yolo-fastest_192_face_v4"]
BINDINGS = [("256_Low", "Ethos_U85_SYS_DRAM_Low", 256),
            ("512_Mid512", "Ethos_U85_SYS_DRAM_Mid_512", 512),
            ("512_Low", "Ethos_U85_SYS_DRAM_Low", 512)]


def sha(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def rows_of(path, workload_col="workload"):
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        idx = header.index(workload_col)
        return header, [r for r in reader], idx


def main():
    # ---- build the union view ------------------------------------------
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT)
    for src in (FROZEN_VIEW, NEW_VIEW):
        for cell in sorted(os.listdir(src)):
            if os.path.isdir(os.path.join(src, cell)):
                shutil.copytree(os.path.join(src, cell), os.path.join(ROOT, cell))
    print("view cells:", len(os.listdir(ROOT)))

    # ---- run the frozen analyzer with a widened workload list -----------
    sys.path.insert(0, MECH)
    import pd_analyzer
    import pd_groups
    before = sha(open(os.path.join(MECH, "pd_analyzer.py"), "rb").read())
    pd_analyzer.WORKLOADS = pd_analyzer.WORKLOADS + NEW_WORKLOADS
    print("analyzer workloads:", pd_analyzer.WORKLOADS)
    pd_analyzer.main(ROOT)
    pd_groups.main(ROOT)
    after = sha(open(os.path.join(MECH, "pd_analyzer.py"), "rb").read())
    assert before == after, "pd_analyzer.py changed on disk"
    print("pd_analyzer.py unchanged:", before[:16])

    # ---- regression over the existing five ------------------------------
    print("\n== regression: existing five workloads ==")
    ok = True
    for name in ("U85_256_512_DIFFERENTIAL.csv", "U85_OPERATOR_MATCH.csv",
                 "U85_ATTRIBUTION_UNITS.csv", "U85_GROUP_DIFFERENTIAL.csv"):
        new_h, new_r, ni = rows_of(os.path.join(ROOT, name))
        old_h, old_r, oi = rows_of(os.path.join(MECH, name))
        if new_h != old_h:
            print("  HEADER CHANGED %s" % name); ok = False; continue
        new_keep = [r for r in new_r if r[ni] in EXISTING]
        old_keep = [r for r in old_r if r[oi] in EXISTING]
        if name == "U85_GROUP_DIFFERENTIAL.csv":
            same = sorted(map(tuple, new_keep)) == sorted(map(tuple, old_keep))
            how = "row-multiset"
        else:
            same = new_keep == old_keep
            how = "byte-order"
        print("  %-32s %-13s %s  (%d rows)"
              % (name, how, "UNCHANGED" if same else "CHANGED", len(old_keep)))
        ok = ok and same
        added = [r for r in new_r if r[ni] in NEW_WORKLOADS]
        print("  %-32s %-13s +%d new rows" % ("", "", len(added)))
    print("regression:", "PASS" if ok else "FAIL")

    # ---- formal matrix append -------------------------------------------
    summary = json.load(open(os.path.join(SP, "summary.json")))
    by_cell = {s["cell"]: s for s in summary}
    mpath = os.path.join(MECH, "U85_FORMAL_MATRIX.csv")
    original = open(mpath, "rb").read()
    with open(mpath) as f:
        header = next(csv.reader(f))
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    for model in NEW_WORKLOADS:
        for label, syscfg, macs in BINDINGS:
            s = by_cell["%s__%s" % (model, label)]
            cl, pr = s["runs"]["clean"][0], s["runs"]["prof"][0]
            w.writerow([s["cell"], model, label, macs, syscfg, s["vela_sha256"],
                        s["instr_status"], s["irq_count"], s["instr_sha256"],
                        s["clean_build"]["axf_sha256"], s["prof_build"]["axf_sha256"],
                        s["clean_build"]["timing_adapter"],
                        cl["total"], cl["active"], cl["idle"],
                        pr["pl_count"], pr["total"], cl["crc"], "3/3"])
    appended = out.getvalue()
    with open(mpath, "wb") as f:
        f.write(original + appended.encode())
    # the existing bytes must be a prefix of the new file
    check = open(mpath, "rb").read()
    print("\nformal matrix: existing %d bytes preserved as prefix: %s"
          % (len(original), check.startswith(original)))
    print("formal matrix rows now:", sum(1 for _ in open(mpath)) - 1)

    # ---- publish the four analysis CSVs ---------------------------------
    for name in ("U85_256_512_DIFFERENTIAL.csv", "U85_OPERATOR_MATCH.csv",
                 "U85_ATTRIBUTION_UNITS.csv", "U85_GROUP_DIFFERENTIAL.csv"):
        shutil.copy2(os.path.join(ROOT, name), os.path.join(MECH, name))
    print("published 4 CSVs to", MECH)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
