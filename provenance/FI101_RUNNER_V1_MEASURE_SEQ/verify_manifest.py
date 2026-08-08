"""Semantic verification of the frozen manifest.

Deliberately split from byte-integrity checking:

    sha256sum -c SHA256SUMS   -- every archived file is byte-identical
    verify_manifest.py        -- required fields, disallowed nulls, hash
                                 targets, and cross-consistency

This file is itself listed in SHA256SUMS, so a modified verifier cannot quietly
certify itself. Run both.

Parsing is done with yaml.safe_load, not regex. An earlier regex version
silently skipped two hashes -- one of them the frozen linker script -- because
of a trailing comment and an uppercase letter in a key name, and still exited 0.
Every failure mode below therefore exits non-zero, including "declared but not
checked" and "checked but not declared".
"""

import hashlib
import os
import subprocess
import sys

import yaml

IMG = os.environ.get(
    "IMG", "/home/gihwan/mps4/FI101_RUNNER_V1_MEASURE_SEQ")
MANIFEST = os.environ.get("MANIFEST", os.path.join(IMG, "MANIFEST.yaml"))
HOST = "/home/gihwan/mps4"
CONTAINER = "benchmark-runner"
WORK = "/work/selftest"

# Required keys, dotted. A missing key or a null value here is a failure.
REQUIRED = [
    "image_id", "qualification", "protocol", "deployed_variant",
    "performance_data_eligible",
    "image_identity.vectors_sha256", "image_identity.app_sha256",
    "image_identity.ddr_sha256", "image_identity.image_fingerprint",
    "build.build_script_sha256", "build.profile", "build.command",
    "build.reproduced_2026_08_06",
    "build_closure.object_count", "build_closure.dep_file_count",
    "toolchain.gcc_version", "toolchain.ld_version", "toolchain.objcopy_version",
    "abi.measurement_magic", "abi.decoded_fields", "abi.result_request_size",
    "abi.nack_payload_size", "abi.required_valid_flags",
    "error_codes.idle_get_result", "error_codes.result_ready_invalid_result",
    "golden.test19_output_crc32", "golden.result_region_base",
    "golden.result_region_length",
    "qualification_evidence.runner_gate_script.result",
    "qualification_evidence.measure_acceptance_script.result",
    "qualification_evidence.python.version",
    "qualification_evidence.invocation.runner_gate",
    "qualification_evidence.invocation.measure_acceptance",
]

# source_commit is the ONE key allowed to be null: the tree is not under
# version control and inventing a commit would be worse than recording none.
NULL_ALLOWED = {"source.source_commit"}

# dotted hash key -> (location, path).  "host" = this filesystem,
# "container" = inside the build container.
HASH_TARGETS = {
    "artifacts.app_sha256":              ("host", IMG + "/clean/APP.BIN"),
    "artifacts.ddr_sha256":              ("host", IMG + "/clean/DDR.BIN"),
    "artifacts.vectors_sha256":          ("host", IMG + "/clean/VECTORS.BIN"),
    "artifacts.wrapped_app_sha256":      ("host", IMG + "/wrapped/APP.BIN"),
    "artifacts.wrapped_vectors_sha256":  ("host", IMG + "/wrapped/VECTORS.BIN"),
    "image_identity.app_sha256":         ("host", IMG + "/clean/APP.BIN"),
    "image_identity.ddr_sha256":         ("host", IMG + "/clean/DDR.BIN"),
    "image_identity.vectors_sha256":     ("host", IMG + "/clean/VECTORS.BIN"),
    "source.runner_measure_main_c_sha256":
        ("container", WORK + "/Selftest_measure/runner_measure_main.c"),
    "source.check_measure_symbols_py_sha256":
        ("container", WORK + "/Selftest_measure/check_measure_symbols.py"),
    "linker.lnk_ld_S_sha256":            ("container", WORK + "/LinkScripts/lnk.ld.S"),
    "linker.lnk_measure_overlay_ld_sha256":
        ("container", WORK + "/LinkScripts/lnk.measure.overlay.ld"),
    "build.build_script_sha256":         ("container", WORK + "/Makefile.measure"),
    "build_closure.cflags_txt_sha256":   ("host", IMG + "/build_closure/CFLAGS.txt"),
    "build_closure.link_objects_txt_sha256":
        ("host", IMG + "/build_closure/link_objects.txt"),
    "build_closure.all_deps_d_sha256":   ("host", IMG + "/build_closure/all_deps.d"),
    "build_closure.dep_files_tar_gz_sha256":
        ("host", IMG + "/build_closure/dep_files.tar.gz"),
    "build_closure.runner_measure_map_sha256":
        ("host", IMG + "/build_closure/runner_measure.map"),
    "qualification_evidence.runner_gate_script.sha256":
        ("host", IMG + "/qualification/test_runner_gate.py"),
    "qualification_evidence.measure_acceptance_script.sha256":
        ("host", IMG + "/qualification/measure_acceptance.py"),
    "qualification_evidence.stale_demo_script.sha256":
        ("host", IMG + "/qualification/stale_demo.py"),
    "qualification_evidence.protocol_client.sha256":
        ("host", IMG + "/host/protocol_client/runner_proto.py"),
}

# Fingerprints are computed, not read off a single file.
FINGERPRINTS = {
    "image_identity.image_fingerprint":
        [IMG + "/clean/VECTORS.BIN", IMG + "/clean/APP.BIN", IMG + "/clean/DDR.BIN"],
    "sibling_fingerprints.measure_seq_wrapped":
        [IMG + "/wrapped/VECTORS.BIN", IMG + "/wrapped/APP.BIN", IMG + "/wrapped/DDR.BIN"],
    "sibling_fingerprints.test_hooks":
        [HOST + "/FI101_MEASURE_TESTHOOKS/VECTORS.BIN",
         HOST + "/FI101_MEASURE_TESTHOOKS/APP.BIN",
         HOST + "/FI101_MEASURE_TESTHOOKS/DDR.BIN"],
}

MISSING = object()   # never truthy-tested; always compared with "is"

failures = []
checks = 0


def fail(msg):
    failures.append(msg)
    print("  FAIL  %s" % msg)


def ok(msg):
    global checks
    checks += 1
    print("  ok    %s" % msg)


def get(tree, dotted):
    cur = tree
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return MISSING
        cur = cur[part]
    return cur


def file_sha(where, path):
    if where == "host":
        if not os.path.exists(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    r = subprocess.run(["docker", "exec", CONTAINER, "sha256sum", path],
                       capture_output=True, text=True)
    return r.stdout.split()[0] if r.returncode == 0 else None


def concat_sha(paths):
    h = hashlib.sha256()
    for p in paths:
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def looks_like_hash_key(name):
    return name == "sha256" or name.endswith("_sha256") or "fingerprint" in name


def is_hash_string(v):
    return (isinstance(v, str) and len(v) == 64
            and all(c in "0123456789abcdef" for c in v))


def walk_hash_keys(tree, prefix=""):
    """Collect hashes by KEY NAME as well as by value.

    Value-only detection is not enough: YAML parses an all-digit hash as an
    int, so such a value is not a str and would slip past a value-based walk
    entirely -- including past the "declared but unverifiable" check. Anything
    NAMED like a hash is therefore collected whatever its type, and validated
    below. malformed[] holds the ones that are not 64-char lowercase hex.
    """
    found, malformed = {}, {}
    for k, v in tree.items():
        dotted = "%s.%s" % (prefix, k) if prefix else k
        if isinstance(v, dict):
            f2, m2 = walk_hash_keys(v, dotted)
            found.update(f2)
            malformed.update(m2)
        elif looks_like_hash_key(k):
            if is_hash_string(v):
                found[dotted] = v
            else:
                malformed[dotted] = v
        elif is_hash_string(v):
            found[dotted] = v
    return found, malformed


with open(MANIFEST, "rb") as f:
    m = yaml.safe_load(f)

print("=== required fields ===")
for key in REQUIRED:
    val = get(m, key)
    if val is MISSING:
        fail("required key missing: %s" % key)
    elif val is None:
        fail("required key is null: %s" % key)
    else:
        ok("%s = %r" % (key, val if not isinstance(val, str) or len(val) < 46
                        else val[:42] + "..."))

print("\n=== nulls ===")
for dotted, _ in list(HASH_TARGETS.items()):
    v = get(m, dotted)
    if v is None and dotted not in NULL_ALLOWED:
        fail("null not allowed at %s" % dotted)
sc = get(m, "source.source_commit")
if sc is MISSING:
    fail("source.source_commit must be present, even as null")
elif sc is None:
    reason = get(m, "source.source_commit_unavailable_reason")
    if reason is MISSING or reason in (None, ""):
        fail("source_commit is null with no stated reason")
    else:
        ok("source_commit null, reason recorded")
else:
    ok("source_commit = %s" % sc)

print("\n=== declared hashes vs checkable targets ===")
declared, malformed = walk_hash_keys(m)
# The snapshot block is verified by its own pass below, against the ARCHIVED
# copies rather than the live worktree. Excluding it here keeps the
# "declared but unverifiable" check meaningful for qualification evidence.
declared = {k: v for k, v in declared.items()
            if not k.startswith("working_tooling_snapshot.")}
for d in sorted(malformed):
    fail("%s is named like a hash but is %s (%r) -- quote it as a 64-char "
         "lowercase hex string" % (d, type(malformed[d]).__name__,
                                   malformed[d]))
known = set(HASH_TARGETS) | set(FINGERPRINTS)
for d in sorted(set(declared) - known):
    fail("declared hash with no verification target: %s" % d)
for k in sorted(known - set(declared)):
    fail("verification target not declared in manifest: %s" % k)

print("\n=== file hashes ===")
for key in sorted(HASH_TARGETS):
    if key not in declared:
        continue
    where, path = HASH_TARGETS[key]
    actual = file_sha(where, path)
    if actual is None:
        fail("%s -- file unreadable: %s" % (key, path))
    elif actual != declared[key]:
        fail("%s -- declared %s... actual %s...  (%s)"
             % (key, declared[key][:16], actual[:16], path))
    else:
        ok("%-52s %s..." % (key, actual[:16]))

print("\n=== fingerprints recomputed ===")
for key, paths in sorted(FINGERPRINTS.items()):
    if key not in declared:
        continue
    actual = concat_sha(paths)
    if actual is None:
        fail("%s -- a component binary is missing" % key)
    elif actual != declared[key]:
        fail("%s -- declared %s... recomputed %s..."
             % (key, declared[key][:16], actual[:16]))
    else:
        ok("%-52s %s..." % (key, actual[:16]))

print("\n=== cross-consistency ===")
for name in ("app", "ddr", "vectors"):
    a = get(m, "image_identity.%s_sha256" % name)
    b = get(m, "artifacts.%s_sha256" % name)
    if a != b:
        fail("image_identity.%s_sha256 != artifacts.%s_sha256" % (name, name))
    else:
        ok("image_identity.%s matches artifacts" % name)

fp = get(m, "image_identity.image_fingerprint")
for sib, val in (get(m, "sibling_fingerprints") or {}).items():
    if val == fp:
        fail("sibling %s has the same fingerprint as this image" % sib)
    else:
        ok("sibling %s is distinguishable" % sib)

qual = get(m, "qualification")
elig = get(m, "performance_data_eligible")
if qual == "measurement-golden":
    abc = get(m, "qualification_evidence.abc_contamination_gate")
    if abc is MISSING or abc in (None, False, ""):
        fail("qualification is measurement-golden without an A/B/C gate record")
    elif elig is not True:
        fail("measurement-golden but performance_data_eligible is not true")
    else:
        ok("measurement-golden with an A/B/C gate record")
elif elig is not False:
    fail("performance_data_eligible must be false while qualification is %r" % qual)
else:
    ok("qualification=%s with performance_data_eligible=false" % qual)

print("\n=== RESULTS.yaml raw logs ===")
rp = os.path.join(IMG, "qualification", "RESULTS.yaml")
if not os.path.exists(rp):
    fail("qualification/RESULTS.yaml missing")
else:
    with open(rp, "rb") as f:
        res = yaml.safe_load(f)
    if res.get("image_fingerprint") != fp:
        fail("RESULTS.yaml image_fingerprint does not match the manifest")
    else:
        ok("RESULTS.yaml fingerprint matches")
    for run in res.get("runs", []):
        lp = os.path.join(IMG, run.get("raw_log", ""))
        want = run.get("raw_log_sha256")
        got = file_sha("host", lp)
        if got is None:
            fail("raw log missing for %s: %s" % (run.get("name"), lp))
        elif got != want:
            fail("raw log altered for %s" % run.get("name"))
        else:
            ok("raw log intact: %s (%s)" % (run.get("name"), run.get("result")))

print("\n=== WORKING TOOLING SNAPSHOT ===")
snap_root = os.path.join(IMG, (get(m, "working_tooling_snapshot.archived_under")
                               or "working_snapshot/"))
snap_files = get(m, "working_tooling_snapshot.files")
wt_root = get(m, "working_tooling_snapshot.worktree_root")
snap_ok = snap_bad = 0
drifted = []
if snap_files is MISSING or not isinstance(snap_files, dict):
    fail("working_tooling_snapshot.files missing")
else:
    for key, want in sorted(snap_files.items()):
        name = key[:-len("_sha256")].replace("_py", ".py")
        path = os.path.join(snap_root, name)
        got = file_sha("host", path)
        if got is None:
            fail("snapshot file unreadable: %s" % path)
            snap_bad += 1
        elif got != want:
            # The ARCHIVED copy changed. A snapshot, once taken, is frozen --
            # this is real corruption, not development.
            fail("snapshot ALTERED: %s" % name)
            snap_bad += 1
        else:
            snap_ok += 1
        if wt_root is not MISSING:
            live = file_sha("host", os.path.join(wt_root, name))
            if live is not None and live != want:
                drifted.append(name)
    print("  snapshot %d/%d intact" % (snap_ok, snap_ok + snap_bad))
    print("  current worktree differs: %d  (informational only -- the worktree"
          % len(drifted))
    print("   is expected to move on; the snapshot is what is frozen)")
    for d in drifted:
        print("     ~ %s" % d)

print("\n=== SUMMARY ===")
print("QUALIFICATION    %d passed, %d failed" % (checks, len(failures)))
print("WORKING SNAPSHOT %d/%d intact, %d worktree difference(s), informational"
      % (snap_ok, snap_ok + snap_bad, len(drifted)))
if failures:
    print("\nDO NOT record experiment data under this image_id:")
    for f_ in failures:
        print("  - %s" % f_)
sys.exit(1 if failures else 0)
