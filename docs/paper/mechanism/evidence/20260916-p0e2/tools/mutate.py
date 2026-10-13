#!/usr/bin/env python3
"""Mutation harness for the P0-E2 gates.

Neuter one check, require the suite to go RED, restore by digest. A mutation
that survives means the branch has no reaching fixture; the fixture gets added,
the mutation does not get deleted.
"""
import hashlib, shutil, subprocess, sys, pathlib

REPO = pathlib.Path("/Users/gihwan/Documents/Projects/mps4_prototyping_board")
TARGET = REPO / "host/experiments/p0e2/gates.py"
SAVED = pathlib.Path(__file__).with_name("gates.py.pristine")

# (rule id, description, old text, new text)
MUTATIONS = [
 ("RULE_P0E2_MODEL_SHA", "accept any model digest",
  "        if observed[model] != frozen:\n            raise fail_rule(\n                RULE_P0E2_MODEL_SHA,",
  "        if False:\n            raise fail_rule(\n                RULE_P0E2_MODEL_SHA,"),
 ("RULE_P0E2_MODEL_SHA", "accept a workload outside the closed set",
  "        if model not in FROZEN_MODEL_SHA:\n            raise fail_rule(RULE_P0E2_MODEL_SHA,",
  "        if False:\n            raise fail_rule(RULE_P0E2_MODEL_SHA,"),
 ("RULE_P0E2_TOOLCHAIN", "accept any toolchain version",
  "        if observed[name] != frozen:\n            raise fail_rule(\n                RULE_P0E2_TOOLCHAIN,",
  "        if False:\n            raise fail_rule(\n                RULE_P0E2_TOOLCHAIN,"),
 ("RULE_P0E2_PATCH_IDENTITY", "accept any patch digest",
  "        if observed[name] != frozen:\n            raise fail_rule(\n                RULE_P0E2_PATCH_IDENTITY,",
  "        if False:\n            raise fail_rule(\n                RULE_P0E2_PATCH_IDENTITY,"),
 ("RULE_P0E2_PATCH_IDENTITY", "accept a missing campaign tool",
  "        if name not in observed:\n            raise fail_rule(RULE_P0E2_PATCH_IDENTITY, \"tool absent: %s\" % name)",
  "        if False:\n            raise fail_rule(RULE_P0E2_PATCH_IDENTITY, \"tool absent: %s\" % name)"),
 ("RULE_P0E2_IRQ_VALID", "accept a command stream missing IRQs",
  "    if in_stream != inserted:", "    if False:"),
 ("RULE_P0E2_IRQ_VALID", "accept fewer serviced launches than inserted",
  "    if serviced != inserted:", "    if False:"),
 ("RULE_P0E2_IRQ_VALID", "accept a cell with zero IRQ as a vacuous pass",
  "    if inserted <= 0:", "    if False:"),
 ("RULE_P0E2_LAYER_CAP", "accept an operation count over the cap",
  "    if n > cap:", "    if False:"),
 ("RULE_P0E2_LAYER_CAP", "accept a batch split around the cap",
  "    if cell.get(\"batches\", 1) != 1:", "    if False:"),
 ("RULE_P0E2_LAYER_CAP", "widen the cap to the looser of the two constants",
  "    cap = min(PROFILING_MAX_LAYERS, CONTRACT_CITED_MAX_LAYERS)",
  "    cap = max(PROFILING_MAX_LAYERS, CONTRACT_CITED_MAX_LAYERS)"),
 ("RULE_P0E2_REPS_EXACT", "accept disagreeing replicates",
  "        if not (seen[0] == seen[1] == seen[2]):", "        if False:"),
 ("RULE_P0E2_REPS_EXACT", "accept two replicates as three",
  "    if len(runs) != 3:", "    if False:"),
 ("RULE_P0E2_REPS_EXACT", "accept a replicate with a field dropped",
  "            if field not in run:", "            if False:"),
 ("RULE_P0E2_REPS_EXACT", "narrow the replicate vector to cycles only",
  "REPLICATE_FIELDS = (\"total\", \"active\", \"idle\", \"crc\", \"plprof\", \"pl_count\")",
  "REPLICATE_FIELDS = (\"total\",)"),
 ("RULE_P0E2_SUM_COHERENT", "drop the absolute residual bound",
  "    if abs(residual) > SUM_COHERENCE_MAX_ABS_CYCLES:", "    if False:"),
 ("RULE_P0E2_SUM_COHERENT", "drop the ratio bound",
  "    if ratio > SUM_COHERENCE_MAX_RATIO:", "    if False:"),
 ("RULE_P0E2_SUM_COHERENT", "divide by a zero clean total instead of refusing",
  "    if clean_total <= 0:", "    if False:"),
 ("RULE_P0E2_OUTPUT_CRC", "accept differing output CRC",
  "    if clean != prof:", "    if False:"),
 ("RULE_P0E2_OUTPUT_CRC", "accept two absent outputs as a match",
  "    if not clean or not prof:", "    if False:"),
 ("RULE_P0E2_IDENTITY_JOIN", "accept a positional join key",
  "    if key != IDENTITY_JOIN_KEY:", "    if False:"),
 ("RULE_P0E2_IDENTITY_JOIN", "accept identity sets that differ",
  "    if set(li) != set(ri):", "    if False:"),
 ("RULE_P0E2_IDENTITY_JOIN", "accept a row lacking a key field",
  "            if missing:", "            if False:"),
 ("RULE_P0E2_IDENTITY_JOIN", "accept duplicate identities on the 256 side",
  "    if len(set(li)) != len(li):", "    if False:"),
 ("RULE_P0E2_IDENTITY_JOIN", "accept duplicate identities on the 512 side",
  "    if len(set(ri)) != len(ri):", "    if False:"),
 ("RULE_P0E2_RESTORE", "accept a file that is still patched",
  "        if poststate[path] != prestate[path]:", "        if False:"),
 ("RULE_P0E2_RESTORE", "accept a file that vanished",
  "        if path not in poststate:\n            raise fail_rule(RULE_P0E2_RESTORE, \"absent after restore: %s\" % path)",
  "        if False:\n            raise fail_rule(RULE_P0E2_RESTORE, \"absent after restore: %s\" % path)"),
 ("RULE_P0E2_RESTORE", "accept a leftover patched copy",
  "        if path not in prestate:\n            raise fail_rule(RULE_P0E2_RESTORE,",
  "        if False:\n            raise fail_rule(RULE_P0E2_RESTORE,"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def clear_pyc():
    subprocess.run("find %s -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null" % REPO,
                   shell=True)


def suite():
    clear_pyc()
    r = subprocess.run([sys.executable, "-m", "unittest",
                        "host.tests.p0e2.test_gates"],
                       cwd=REPO, capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def main():
    shutil.copy2(TARGET, SAVED)
    pristine = digest(TARGET)
    print("pristine gates.py sha256:", pristine)
    green, _ = suite()
    if not green:
        print("BASELINE NOT GREEN — aborting"); sys.exit(2)
    print("baseline: GREEN\n")

    survivors, red = [], 0
    for i, (rule, what, old, new) in enumerate(MUTATIONS, 1):
        text = SAVED.read_text()
        if text.count(old) != 1:
            print("%2d. %-26s %-52s MUTATION-NOT-APPLICABLE (%d matches)"
                  % (i, rule, what, text.count(old)))
            survivors.append((rule, what, "not applicable"))
            continue
        TARGET.write_text(text.replace(old, new, 1))
        ok, err = suite()
        if ok:
            print("%2d. %-26s %-52s SURVIVED" % (i, rule, what))
            survivors.append((rule, what, "survived"))
        else:
            fails = [l for l in err.splitlines() if l.startswith("FAIL:") or l.startswith("ERROR:")]
            print("%2d. %-26s %-52s RED (%d failing)" % (i, rule, what, len(fails)))
            red += 1
        shutil.copy2(SAVED, TARGET)
        if digest(TARGET) != pristine:
            print("RESTORE FAILED after mutation %d" % i); sys.exit(2)

    clear_pyc()
    print("\nrestored digest:", digest(TARGET), "==", pristine,
          "->", digest(TARGET) == pristine)
    final_green, _ = suite()
    print("post-restore suite:", "GREEN" if final_green else "RED")
    print("\nmutations: %d, RED: %d, survivors: %d" % (len(MUTATIONS), red, len(survivors)))
    for s in survivors:
        print("  SURVIVOR:", s)
    sys.exit(0 if (not survivors and final_green) else 1)


if __name__ == "__main__":
    main()
