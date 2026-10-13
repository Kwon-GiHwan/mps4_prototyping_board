#!/usr/bin/env python3
"""P0-E2: run the ten gates over the campaign's actual evidence.

The unit tests prove each gate can fail. This proves what the gates say about
the six cells that were measured. Every outcome is PASS, FAIL or UNPROVEN; a
gate whose evidence is absent is UNPROVEN, never a pass.
"""
import csv, json, os, sys, collections

REPO = "/Users/gihwan/Documents/Projects/mps4_prototyping_board"
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
from host.experiments.p0e2 import gates  # noqa: E402

MECH = os.path.join(REPO, "docs/paper/mechanism")
VIEW = os.path.join(SP, "viewE2")
PAIRS = [("B-frozen", "256_Low", "512_Mid512"), ("B-held", "256_Low", "512_Low")]
MODELS = ["wav2letter_pruned_int8", "mobilenet_v2_1.0_224_INT8"]

results = []


def record(rule, subject, fn):
    try:
        fn()
        results.append((rule, subject, "PASS", ""))
    except gates.GateError as exc:
        tripped = gates.refusal_rule(exc)
        verdict = "FAIL" if tripped == rule else "FAIL(OTHER_RULE:%s)" % tripped
        results.append((rule, subject, verdict, "%s" % exc))


def main():
    summary = json.load(open(os.path.join(SP, "summary.json")))
    by_cell = {s["cell"]: s for s in summary}
    env = json.load(open(os.path.join(SP, "environment.json")))

    record(gates.RULE_P0E2_MODEL_SHA, "both workloads",
           lambda: gates.check_model_sha(env["model_sha"]))
    record(gates.RULE_P0E2_TOOLCHAIN, "vela/mlek/core-driver/fvp",
           lambda: gates.check_toolchain(env["toolchain"]))
    record(gates.RULE_P0E2_PATCH_IDENTITY, "september patch digests",
           lambda: gates.check_patch_identity(env["patch_sha"]))

    for cell in sorted(by_cell):
        s = by_cell[cell]
        launches = json.load(open(os.path.join(VIEW, cell, "launches.json")))
        prof = s["runs"]["prof"][0]
        recs = [l for l in prof["plprof"].splitlines() if l.startswith("PLPROF,")]
        # launches accounted for by the decoded history windows, tail included
        serviced = 0
        seq = 0
        contiguous = True
        for r in recs:
            hist = int(r.split(",")[8], 16)
            n = bin(hist).count("1")
            expect = 0
            for k in range(n):
                expect |= 1 << ((seq + k) % 16)
            if expect != hist:
                contiguous = False
            seq += n
        serviced = seq + max(0, len(launches) - seq)  # tail window covers the rest
        cellrec = {"cell": cell, "irq_count": s["irq_count"],
                   "stream_irq_count": s["stream_irq_count_instr"],
                   "serviced_launches": serviced,
                   "contiguous_windows": contiguous}
        record(gates.RULE_P0E2_IRQ_VALID, cell,
               lambda c=cellrec: gates.check_irq_valid(c))
        record(gates.RULE_P0E2_LAYER_CAP, cell,
               lambda c=cellrec: gates.check_layer_cap(c))
        for arm in ("clean", "prof"):
            record(gates.RULE_P0E2_REPS_EXACT, "%s/%s" % (cell, arm),
                   lambda a=arm, ss=s: gates.check_reps_exact(ss["runs"][a]))
        record(gates.RULE_P0E2_OUTPUT_CRC, cell,
               lambda ss=s: gates.check_output_crc(
                   {"cell": ss["cell"], "clean_crc": ss["runs"]["clean"][0]["crc"],
                    "prof_crc": ss["runs"]["prof"][0]["crc"]}))

    units = collections.defaultdict(int)
    for u in csv.DictReader(open(os.path.join(MECH, "U85_ATTRIBUTION_UNITS.csv"))):
        units[(u["workload"], u["binding"])] += int(u["ccnt"])
    for cell in sorted(by_cell):
        s = by_cell[cell]
        key = (s["model"], s["binding"])
        rec = {"cell": cell, "unit_ccnt_sum": units.get(key),
               "clean_total": s["runs"]["clean"][0]["total"]}
        record(gates.RULE_P0E2_SUM_COHERENT, cell,
               lambda r=rec: gates.check_sum_coherent(r))

    diff = list(csv.DictReader(open(os.path.join(MECH, "U85_256_512_DIFFERENTIAL.csv"))))
    srcs = {}
    for cell in sorted(by_cell):
        s = by_cell[cell]
        q, o, source = __import__("pd_analyzer").parse_db(
            os.path.join(VIEW, cell, "debug.xml"))
        srcs[(s["model"], s["binding"])] = source
    for model in MODELS:
        for pair, a_lbl, b_lbl in PAIRS:
            sa, sb = srcs[(model, a_lbl)], srcs[(model, b_lbl)]
            rows = [r for r in diff
                    if r["workload"] == model and r["binding_pair"] == pair]
            sids = [int(r["source_id"]) for r in rows]

            def side(table, ids):
                return [{"workload": model, "op_index": i,
                         "op_type": table[i]["operator"],
                         "ifm_shape": table[i]["kernel"],
                         "ofm_shape": table[i]["ofm"]} for i in ids]

            record(gates.RULE_P0E2_IDENTITY_JOIN, "%s %s" % (model, pair),
                   lambda ta=sa, tb=sb, ids=sids: gates.check_identity_join(
                       {"key": gates.IDENTITY_JOIN_KEY,
                        "left": side(ta, ids), "right": side(tb, ids)}))

    post = os.path.join(SP, "POSTSTATE.sha256")
    if os.path.exists(post):
        def load(p):
            return {l.split()[1]: l.split()[0] for l in open(p) if l.strip()}
        record(gates.RULE_P0E2_RESTORE, "patch targets",
               lambda: gates.check_restore(load(os.path.join(SP, "PRESTATE.sha256")),
                                           load(post)))
    else:
        results.append((gates.RULE_P0E2_RESTORE, "patch targets", "UNPROVEN",
                        "POSTSTATE.sha256 not captured yet"))

    out = []
    out.append("%-28s %-46s %s" % ("RULE", "SUBJECT", "VERDICT"))
    out.append("-" * 96)
    for rule, subject, verdict, msg in results:
        out.append("%-28s %-46s %s" % (rule, subject, verdict))
        if msg:
            out.append("    %s" % msg)
    counts = collections.Counter(v.split("(")[0] for _, _, v, _ in results)
    out.append("-" * 96)
    out.append("checks: %d  " % len(results) +
               "  ".join("%s=%d" % kv for kv in sorted(counts.items())))
    covered = {r for r, _, _, _ in results}
    missing = {getattr(gates, n) for n in gates.RULES} - covered
    out.append("rules evaluated: %d/%d%s" % (
        len(covered), len(gates.RULES),
        "  NOT EVALUATED: %s" % sorted(missing) if missing else ""))
    text = "\n".join(out)
    print(text)
    open(os.path.join(SP, "gate_report.txt"), "w").write(text + "\n")
    return 0 if counts.get("FAIL", 0) == 0 and not missing else 1


if __name__ == "__main__":
    sys.path.insert(0, MECH)
    sys.exit(main())
