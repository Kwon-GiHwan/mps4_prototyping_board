"""Negative gates for the two-class manifest verifier.

The whole point of the split is that two superficially similar changes must
land on OPPOSITE sides of the pass/fail line:

  a live working file edited        -> informational, exit 0   (development)
  an archived snapshot file edited  -> failure,       exit 1   (corruption)

Before the split both produced the same 74/75 "failure", which made an ordinary
host-script edit indistinguishable from a damaged archive.
"""
import os, shutil, subprocess, sys, tempfile

SRC = "/home/gihwan/mps4/FI101_RUNNER_V1_MEASURE_SEQ"
WT = "/home/gihwan/mps4"


def run(img, wt):
    env = dict(os.environ, IMG=img, MANIFEST=os.path.join(img, "MANIFEST.yaml"))
    r = subprocess.run([sys.executable, os.path.join(img, "verify_manifest.py")],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def stage():
    d = tempfile.mkdtemp(prefix="ncm_")
    img = os.path.join(d, "IMG")
    shutil.copytree(SRC, img, symlinks=True)
    return d, img


cases, bad = [], 0

# 1. untouched -> pass
d, img = stage()
rc, out = run(img, WT)
cases.append(("untouched archive", rc == 0, "exit=%d" % rc))
shutil.rmtree(d)

# 2. archived SNAPSHOT altered -> must FAIL
d, img = stage()
p = os.path.join(img, "working_snapshot", "runner_proto.py")
open(p, "a").write("\n# tampered\n")
rc, out = run(img, WT)
cases.append(("archived snapshot altered -> FAIL",
              rc != 0 and "snapshot ALTERED" in out, "exit=%d" % rc))
shutil.rmtree(d)

# 3. QUALIFICATION evidence altered -> must FAIL
d, img = stage()
p = os.path.join(img, "qualification", "measure_acceptance.py")
open(p, "a").write("\n# tampered\n")
rc, out = run(img, WT)
cases.append(("qualification evidence altered -> FAIL", rc != 0, "exit=%d" % rc))
shutil.rmtree(d)

# 4. raw log altered -> must FAIL
d, img = stage()
lg = [f for f in os.listdir(os.path.join(img, "qualification", "raw_logs"))
      if f.startswith("runner_gate")][0]
open(os.path.join(img, "qualification", "raw_logs", lg), "a").write("forged\n")
rc, out = run(img, WT)
cases.append(("raw log altered -> FAIL", rc != 0, "exit=%d" % rc))
shutil.rmtree(d)

# 5. live WORKTREE differs -> informational, must still PASS
d, img = stage()
fake_wt = os.path.join(d, "wt")
shutil.copytree(WT, fake_wt, symlinks=True, ignore=shutil.ignore_patterns(
    "FI101_*", "boot-capture-logs", "runner", "sd-backup", "venv", "__pycache__", "logs"))
open(os.path.join(fake_wt, "runner_proto.py"), "a").write("\n# ongoing development\n")
mp = os.path.join(img, "MANIFEST.yaml")
t = open(mp).read().replace("worktree_root: /home/gihwan/mps4",
                            "worktree_root: " + fake_wt)
open(mp, "w").write(t)
rc, out = run(img, WT)
ok = rc == 0 and "current worktree differs: 1" in out
cases.append(("live worktree differs -> informational, PASS", ok,
              "exit=%d" % rc))
shutil.rmtree(d)

print("=== manifest two-class negative gates ===")
for name, ok, det in cases:
    print("  %-5s %-46s %s" % ("PASS" if ok else "FAIL", name, det))
    if not ok:
        bad += 1
print("\n%d/%d" % (len(cases) - bad, len(cases)))
sys.exit(1 if bad else 0)
