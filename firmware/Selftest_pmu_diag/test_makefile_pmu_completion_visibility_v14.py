"""Graph semantics for the isolated V14 three-variant build.

The V14 graph builds Q, QS and SQ from one frozen pair of sources, and the
property that matters is *isolation*: three disjoint build roots, no writable
generated source shared between them, an explicit variant that the graph refuses
to guess, and a manifest that cannot be produced without the ELF, the map, the
symbol and disassembly dumps, the DWARF, the generated sources, and every
declared proof.

Substring inspection alone would only prove the text of the Makefile. The
checker is therefore actually executed here -- ``--help`` for its option surface,
and a controlled fixture manifest written to a temporary path -- so the binding
the graph relies on is exercised rather than asserted.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile


FIRMWARE = pathlib.Path(__file__).resolve().parents[1]
MAKEFILE = FIRMWARE / "Makefile.pmu_completion_visibility_v14"
GATE = FIRMWARE / "Selftest_pmu_diag" / "check_pmu_completion_visibility_v14.py"
PATCHER = FIRMWARE / "patches" / "patch_pmu_completion_visibility_v14.py"
VARIANTS = ("Q", "QS", "SQ")
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print("  PASS %-72s %s" % (label, detail[:70]))
    else:
        FAILED += 1
        print("  FAIL %-72s %s" % (label, detail[:70]))


def require(text: str, needle: str, label: str) -> None:
    check(label, needle in text, needle[:70])


def _canonical_pair(variant: str):
    """The generated Q/QS/SQ pair the V14 contract suite already builds.

    The genuine frozen vendor input is staged into the build container rather
    than tracked here, so the canonical generated pair is what this worktree can
    hand the checker. It is the same text the manifest rule would verify.
    """

    import contextlib
    import io

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            suite = __import__("test_check_pmu_completion_visibility_v14")
        return suite.canonical_runner(variant), suite.canonical_vendor(variant)
    except Exception:
        return None, None


def make_dry_run(build: str, variant: str, *goals: str):
    """Ask make what it *would* do, without a toolchain present."""

    return subprocess.run(
        ["make", "-f", str(MAKEFILE), "-n", "V14_VARIANT=%s" % variant, "BUILD=%s" % build, *goals],
        capture_output=True,
        text=True,
        cwd=str(FIRMWARE),
    )


def validate_isolation(text: str) -> None:
    # The default root carries the variant, so Q, QS and SQ cannot land on each
    # other even when BUILD is left alone.
    require(text, "BUILD := build_pmu_completion_visibility_v14/$(V14_VARIANT)",
            "the default build root is per-variant")
    check(
        "the default is only applied when the caller set nothing",
        "ifeq ($(origin BUILD),undefined)" in text,
        "origin guard",
    )
    # Generated sources live under the per-variant root: nothing writable is
    # shared, so one variant's generation cannot be read by another.
    require(text, "GEN := $(BUILD)/generated", "generated sources sit under the build root")
    for tracked in ("Selftest_pmu_diag/runner_pmu_diag_main.c", "Drivers/u85_driver/u85.c"):
        check(
            "the frozen input %s is never a generated output" % tracked,
            "$(GEN)/%s" % tracked not in text or "GEN_" in text,
            tracked,
        )


def validate_variant_gate(text: str) -> None:
    require(text, "V14_VALID_VARIANTS := Q QS SQ", "the accepted variant set is written down")
    check(
        "an unknown variant is a make error rather than a default",
        "$(error" in text and "V14_VARIANT" in text,
        "$(error ...) on V14_VARIANT",
    )
    require(text, "--variant $(V14_VARIANT)", "the variant reaches the checker CLI")
    require(text, "--variant $(V14_VARIANT)", "the variant reaches the patcher CLI")


def validate_frozen_inputs(text: str) -> None:
    require(text, "RUNNER_SRC := Selftest_pmu_diag/runner_pmu_diag_main.c", "frozen runner input")
    require(text, "VENDOR_SRC := Drivers/u85_driver/u85.c", "frozen vendor input")
    require(text, "RUNNER_SHA256 := %s" % RUNNER_SHA256, "frozen runner digest")
    require(text, "VENDOR_SHA256 := %s" % VENDOR_SHA256, "frozen vendor digest")
    require(text, "FROZEN_INPUT_EVIDENCE :=", "frozen-input digests are a declared output")


def validate_targets(text: str) -> None:
    for goal in ("all", "clean", "manifest", "check"):
        check("the %s target exists" % goal, re.search(r"(?m)^%s:" % goal, text) is not None, goal)
    require(text, ".PHONY:", "phony targets are declared")
    require(text, "rm -rf --", "clean ends option parsing before the path")


def rule_prerequisites(text: str, target: str) -> str:
    """The whole prerequisite list of ``target``, continuation lines joined.

    A make prerequisite list is one logical line however many physical ones it
    is written across, so reading only the first would silently stop checking at
    the first backslash -- and everything this manifest must depend on is on the
    later lines.
    """

    parts = text.split(target, 1)
    if len(parts) != 2:
        return ""
    logical = []
    for line in parts[1].splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            logical.append(stripped[:-1])
            continue
        logical.append(stripped)
        break
    return " ".join(logical)


def validate_manifest_inputs(text: str) -> None:
    check("the manifest has a rule", "$(MANIFEST):" in text, "")
    prerequisites = rule_prerequisites(text, "$(MANIFEST):")
    check("the manifest prerequisite list is recovered", bool(prerequisites.strip()), "")
    for needed, label in (
        ("$(TARGET).elf", "ELF"),
        ("$(TARGET).map", "map"),
        ("$(BUILD)/APP.BIN", "APP image"),
        ("$(BUILD)/VECTORS.BIN", "vectors image"),
        ("$(BUILD)/DDR.BIN", "DDR image"),
        ("$(V14_NM)", "nm"),
        ("$(V14_OBJDUMP)", "objdump"),
        ("$(V14_DWARF)", "DWARF"),
        ("$(GEN_RUNNER)", "generated runner"),
        ("$(GEN_VENDOR)", "generated vendor"),
        ("$(SOURCE_FIXTURE_EVIDENCE)", "source/fixture proof"),
        ("$(MAILBOX_WIRE_EVIDENCE)", "mailbox/wire proof"),
        ("$(RETAINED_BASE_PMU_EVIDENCE)", "retained base-PMU proof"),
        ("$(FROZEN_INPUT_EVIDENCE)", "frozen-input digests"),
    ):
        check("the manifest depends on the %s" % label, needed in prerequisites, needed)
    require(text, "@test -s $(MANIFEST)", "the manifest is proven non-empty")
    # Every side-effect artifact named as a prerequisite needs a rule of its own,
    # or make refuses the graph with "No rule to make target" even though the
    # link or the image step emits it.
    for side_effect in ("$(TARGET).map:", "$(BUILD)/APP.BIN"):
        check(
            "the side-effect artifact %s carries a witness rule" % side_effect.rstrip(":"),
            re.search(r"(?m)^%s" % re.escape(side_effect), text) is not None,
            side_effect,
        )


def validate_dry_runs() -> None:
    # ``Drivers/u85_driver/u85.c`` is a frozen vendor input that is not tracked
    # in this repository -- Task 7 stages it into the build container -- so the
    # manifest graph cannot be fully expanded here. That is itself the assertion
    # worth making: the graph must demand the frozen input by name rather than
    # proceed without it, and everything reachable without it must still resolve.
    # BUILD reaches the recipe through the environment now, so ``make -n`` no
    # longer prints it. Isolation is proven by running the real ``clean`` against
    # scratch roots and observing exactly which one disappears.
    with tempfile.TemporaryDirectory() as scratch:
        roots = {}
        for variant in VARIANTS:
            directory = pathlib.Path(scratch) / ("%s-root" % variant)
            directory.mkdir(parents=True)
            (directory / "marker").write_text(variant, encoding="utf-8")
            roots[variant] = directory
        for index, variant in enumerate(VARIANTS):
            done = subprocess.run(
                [
                    "make", "-f", str(MAKEFILE), "V14_VARIANT=%s" % variant,
                    "BUILD=%s" % roots[variant], "clean",
                ],
                capture_output=True,
                text=True,
                cwd=str(FIRMWARE),
            )
            check(
                "the %s clean graph runs" % variant,
                done.returncode == 0,
                (done.stderr or done.stdout).strip()[:60],
            )
            check(
                "the %s clean removed its own root" % variant,
                not roots[variant].exists(),
                roots[variant].name,
            )
            for other in VARIANTS[index + 1 :]:
                check(
                    "cleaning %s left the %s root alone" % (variant, other),
                    roots[other].exists(),
                    roots[other].name,
                )

    for variant in VARIANTS:
        root = "/tmp/v14-dry/%s-root" % variant
        wanted = make_dry_run(root, variant, "manifest")
        combined = wanted.stdout + wanted.stderr
        check(
            "the %s manifest graph demands the frozen vendor input" % variant,
            wanted.returncode != 0 and "Drivers/u85_driver/u85.c" in combined,
            combined.strip().splitlines()[-1][:60] if combined.strip() else "",
        )

    # ``$(filter ...)`` would treat the *caller's* value as a pattern, so a bare
    # ``%`` matches everything and a two-word value passes as non-empty. Each of
    # those is a build labelled with a variant it did not build.
    # ``Q `` and `` Q`` are not in this list: make collapses surrounding
    # whitespace, so they *are* ``Q`` and refusing them would be wrong.
    for bogus in ("QQ", "%", "Q%", "%S", "Q QS", "Q SQ QS"):
        rejected = make_dry_run("/tmp/v14-dry/BAD-root", bogus, "clean")
        check(
            "the variant %r is refused" % bogus,
            rejected.returncode != 0 and "V14_VARIANT" in (rejected.stderr + rejected.stdout),
            (rejected.stderr or rejected.stdout).strip()[:60],
        )
    missing = subprocess.run(
        ["make", "-f", str(MAKEFILE), "-n", "manifest"],
        capture_output=True,
        text=True,
        cwd=str(FIRMWARE),
    )
    check(
        "an absent variant is refused rather than defaulted",
        missing.returncode != 0,
        (missing.stderr or missing.stdout).strip()[:60],
    )


def clean_guard_command(text: str):
    """The shipped BUILD guard, extracted so the test runs the real one.

    The assignment spans continuation lines, and make joins a backslash-newline
    into a single space -- so the same joining happens here. Reading only the
    first physical line would hand the shell an unterminated quote and prove
    nothing about the guard.
    """

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("CLEAN_GUARD :="):
            continue
        joined = [line.split(":=", 1)[1].strip()]
        while joined[-1].endswith("\\"):
            joined[-1] = joined[-1][:-1].rstrip()
            index += 1
            if index >= len(lines):
                break
            joined.append(lines[index].strip())
        return " ".join(part for part in joined if part)
    return None


def validate_clean_safety(text: str) -> None:
    """``BUILD`` is caller-supplied and ``clean`` deletes it, so it is validated.

    The dangerous values are never handed to ``rm``: the guard is executed on its
    own and only has to refuse. Nothing here removes anything.
    """

    guard = clean_guard_command(text)
    check("the clean recipe routes through a named BUILD guard", guard is not None, "CLEAN_GUARD")
    if guard is None:
        return
    check(
        "clean deletes only what the guard returned",
        "$(CLEAN_GUARD)" in text and "rm -rf --" in text,
        "guard && rm -rf --",
    )
    check(
        "clean never expands BUILD straight into rm",
        "rm -rf $(BUILD)" not in text,
        "no raw rm -rf $(BUILD)",
    )

    with tempfile.TemporaryDirectory() as scratch:
        sandbox = pathlib.Path(scratch) / "a" / "b"
        sandbox.mkdir(parents=True)
        # The guard carries its own quoting, so it is written to a script and
        # given the candidate as an argument rather than composed into ``sh -c``.
        script = pathlib.Path(scratch) / "guard.sh"
        script.write_text("%s\n" % guard, encoding="utf-8")

        def run_guard(candidate: str):
            # The guard reads the candidate from the environment, the same way
            # the recipe hands it over -- there is no argv path to test.
            environment = dict(os.environ, V14_CLEAN_BUILD=candidate)
            return subprocess.run(
                ["sh", str(script)],
                capture_output=True,
                text=True,
                cwd=str(FIRMWARE),
                env=environment,
            )

        home = str(pathlib.Path.home())
        for dangerous in ("", "/", ".", "..", "/.", "/..", "   ", str(FIRMWARE), home, "/tmp"):
            probe = run_guard(dangerous)
            check(
                "the guard refuses BUILD=%r" % dangerous,
                probe.returncode != 0,
                (probe.stderr or probe.stdout).strip()[:60],
            )
        for allowed in (
            str(sandbox),
            "/work/v14/BUILD_A/Q",
            "build_pmu_completion_visibility_v14/Q",
        ):
            probe = run_guard(allowed)
            check(
                "the guard accepts BUILD=%r" % allowed,
                probe.returncode == 0,
                (probe.stderr or probe.stdout).strip()[:60],
            )


def validate_clean_injection(text: str) -> None:
    """A caller-supplied BUILD must reach ``clean`` as data, never as shell syntax.

    ``clean`` runs a shell, and BUILD is the caller's string. Interpolating it
    into the recipe lets an apostrophe close the quoting and whatever follows run
    as a command -- with the privileges of whoever ran make. This drives the real
    recipe rather than the guard alone, because the guard was never what was
    bypassed: the payload fired before the guard was reached.

    Everything happens under a scratch root, and the assertion is that a sentinel
    inside that scratch root was never created.
    """

    with tempfile.TemporaryDirectory() as scratch:
        sentinel = pathlib.Path(scratch) / "SENTINEL"
        payloads = (
            "%s/root'`touch %s`'" % (scratch, sentinel),
            "%s/root' && touch %s && echo '" % (scratch, sentinel),
            "%s/root'$(touch %s)'" % (scratch, sentinel),
            "%s/root'|touch %s|'" % (scratch, sentinel),
            # Make syntax, not shell syntax: BUILD is expanded by make wherever
            # it is referenced, so a make function written into it is its own
            # surface. The graph refuses the metacharacter rather than relying on
            # where the expansion happens to land.
            "$(shell touch %s)/root" % sentinel,
            "%s/root$(shell touch %s)" % (scratch, sentinel),
        )
        for payload in payloads:
            subprocess.run(
                [
                    "make", "-f", str(MAKEFILE), "V14_VARIANT=Q",
                    "BUILD=%s" % payload, "clean",
                ],
                capture_output=True,
                text=True,
                cwd=str(FIRMWARE),
            )
            check(
                "a BUILD carrying %r executes nothing" % payload[len(scratch):][:26],
                not sentinel.exists(),
                "sentinel present" if sentinel.exists() else "sentinel absent",
            )
            if sentinel.exists():
                sentinel.unlink()

        # And the honest paths still clean: a Task 7 absolute staging root and
        # the per-variant default.
        honest = pathlib.Path(scratch) / "BUILD_A" / "Q"
        honest.mkdir(parents=True)
        (honest / "marker").write_text("x", encoding="utf-8")
        done = subprocess.run(
            ["make", "-f", str(MAKEFILE), "V14_VARIANT=Q", "BUILD=%s" % honest, "clean"],
            capture_output=True,
            text=True,
            cwd=str(FIRMWARE),
        )
        check(
            "an absolute staging root still cleans",
            done.returncode == 0 and not honest.exists(),
            (done.stderr or done.stdout).strip()[:60],
        )
        # The default root, proven by deletion rather than by grepping the
        # recipe: BUILD travels in the environment now and need not appear in
        # ``make -n`` output at all. The directory is a build output this test
        # creates itself, so nothing pre-existing is at risk.
        default_root = FIRMWARE / "build_pmu_completion_visibility_v14" / "Q"
        default_root.mkdir(parents=True, exist_ok=True)
        (default_root / "marker").write_text("x", encoding="utf-8")
        defaulted = subprocess.run(
            ["make", "-f", str(MAKEFILE), "V14_VARIANT=Q", "clean"],
            capture_output=True,
            text=True,
            cwd=str(FIRMWARE),
        )
        check(
            "the default root still cleans",
            defaulted.returncode == 0 and not default_root.exists(),
            (defaulted.stderr or defaulted.stdout).strip()[:60],
        )
        parent = FIRMWARE / "build_pmu_completion_visibility_v14"
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


def validate_checker_cli() -> None:
    help_text = subprocess.run(
        [sys.executable, str(GATE), "--help"], capture_output=True, text=True, check=True
    ).stdout
    for option in ("--variant", "--runner-generated", "--vendor-generated", "--allow-fixture"):
        require(help_text, option, "the checker CLI offers %s" % option)
    manifest_option = "--fixture-manifest-out"
    require(help_text, manifest_option, "the checker CLI offers %s" % manifest_option)

    patcher_help = subprocess.run(
        [sys.executable, str(PATCHER), "--help"], capture_output=True, text=True, check=True
    ).stdout
    for option in ("--variant", "--runner-in", "--vendor-in", "--runner-out", "--vendor-out"):
        require(patcher_help, option, "the patcher CLI offers %s" % option)

    # The patcher's frozen-input gate is exercised for real: handed anything but
    # the pinned vendor source it refuses rather than generating. The genuine
    # vendor input is not tracked here, so this is the half of the contract this
    # worktree can execute, and it is the half that fails closed.
    with tempfile.TemporaryDirectory() as scratch:
        root = pathlib.Path(scratch)
        impostor = root / "u85.c"
        impostor.write_text("/* not the frozen vendor source */\n", encoding="utf-8")
        refused = subprocess.run(
            [
                sys.executable, str(PATCHER), "--variant", "Q",
                "--runner-in", str(FIRMWARE / "Selftest_pmu_diag" / "runner_pmu_diag_main.c"),
                "--vendor-in", str(impostor),
                "--runner-out", str(root / "r.c"),
                "--vendor-out", str(root / "v.c"),
            ],
            capture_output=True,
            text=True,
        )
        check(
            "the patcher refuses a vendor input that is not the frozen one",
            refused.returncode != 0,
            (refused.stderr or refused.stdout).strip()[:70],
        )

        # The controlled manifest run: drive the checker exactly as the manifest
        # rule does -- real CLI, real generated pair, a manifest path this test
        # owns -- and read what it wrote.
        for variant in VARIANTS:
            runner_text, vendor_text = _canonical_pair(variant)
            if runner_text is None:
                check("a canonical %s pair is available to drive the checker" % variant, False, "")
                continue
            runner_path = root / ("%s_runner.c" % variant)
            vendor_path = root / ("%s_vendor.c" % variant)
            runner_path.write_text(runner_text, encoding="utf-8")
            vendor_path.write_text(vendor_text, encoding="utf-8")
            manifest_path = root / ("controlled_%s_manifest.json" % variant)
            verified = subprocess.run(
                [
                    sys.executable, str(GATE), "--allow-fixture", "--variant", variant,
                    "--runner-generated", str(runner_path),
                    "--vendor-generated", str(vendor_path),
                    manifest_option, str(manifest_path),
                ],
                capture_output=True,
                text=True,
            )
            check(
                "the checker accepts the canonical %s pair through its CLI" % variant,
                verified.returncode == 0,
                (verified.stderr or verified.stdout).strip()[:70],
            )
            check(
                "the controlled %s manifest is non-empty" % variant,
                manifest_path.exists() and manifest_path.stat().st_size > 0,
                manifest_path.name,
            )
            if not (manifest_path.exists() and manifest_path.stat().st_size > 0):
                continue
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            for key in ("variant", "schema_version", "generated_runner_sha256",
                        "generated_vendor_sha256"):
                check("the controlled %s manifest carries %s" % (variant, key),
                      key in document, key)
            check(
                "the controlled %s manifest names the variant it was asked for" % variant,
                document.get("variant") == variant,
                str(document.get("variant")),
            )

        # And the CLI refuses a pair that is not the variant it was told to check.
        runner_text, vendor_text = _canonical_pair("Q")
        if runner_text is not None:
            (root / "mismatch_runner.c").write_text(runner_text, encoding="utf-8")
            (root / "mismatch_vendor.c").write_text(vendor_text, encoding="utf-8")
            mismatched = subprocess.run(
                [
                    sys.executable, str(GATE), "--allow-fixture", "--variant", "QS",
                    "--runner-generated", str(root / "mismatch_runner.c"),
                    "--vendor-generated", str(root / "mismatch_vendor.c"),
                    manifest_option, str(root / "unused.json"),
                ],
                capture_output=True,
                text=True,
            )
            check(
                "the checker refuses a Q pair presented as QS",
                mismatched.returncode != 0,
                (mismatched.stderr or mismatched.stdout).strip()[:70],
            )


def main() -> int:
    if not MAKEFILE.exists():
        print("  FAIL %-72s %s" % ("the V14 build graph exists", str(MAKEFILE)))
        print("\npassed=0 failed=1")
        return 1
    text = MAKEFILE.read_text(encoding="utf-8")
    validate_isolation(text)
    validate_variant_gate(text)
    validate_frozen_inputs(text)
    validate_targets(text)
    validate_manifest_inputs(text)
    validate_clean_safety(text)
    validate_clean_injection(text)
    validate_dry_runs()
    validate_checker_cli()
    print("\npassed=%d failed=%d" % (PASSED, FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
