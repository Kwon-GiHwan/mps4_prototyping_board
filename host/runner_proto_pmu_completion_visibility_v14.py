"""Schema-14 PMU completion-visibility frame.

The frame is the 85-word body every PMU diagnostic has carried since v8, with a
34-word appendix after it. This module parses that appendix explicitly, word by
word, and refuses anything that is not a complete V14 frame.

It does not coerce. Earlier parsers reject schema 14, and the temptation is to
hand them a frame wearing an older schema number so they will read the prefix
they understand -- which publishes a V14 run as a v8 measurement. An older view
is available here, but only from a frame that has already passed every check
below, and only over the prefix this module has verified is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field

try:
    from host import runner_proto as v8
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto as v8

ProtocolError = v8.ProtocolError

NAME = "PMU_COMPLETION_VISIBILITY_DIAG_V14"
SCHEMA_VERSION = 14
BUILD_ID = 0x34314950
MAGIC = v8.PMU_DIAG_MAGIC
MAILBOX_VALID = 0x5631344D

HEADER_WORDS = v8.PMU_QUAL_HEADER_WORDS                 # 8
BASE_WORDS = v8.PMU_QUAL_KNOWN_FIELDS                   # 85
APPENDIX_WORDS = 34
BODY_WORDS = BASE_WORDS + APPENDIX_WORDS                # 119
TOTAL_WORDS = HEADER_WORDS + BODY_WORDS                 # 127
PAYLOAD_BYTES = TOTAL_WORDS * 4                         # 508

QSIZE_EXPECTED = 0x110

# The appendix, in wire order. Position is the contract; this table is this
# module's own and is never read back from a test.
APPENDIX_FIELDS = (
    "variant_id",
    "qsize_expected",
    "pre_program_status",
    "pre_submit_status",
    "t_submit_after_cmd",
    "t_primary_entry",
    "t_first_observation",
    "primary_result",
    "primary_iterations",
    "first_qread",
    "first_status",
    "first_q_done",
    "first_cmd_end_reached",
    "first_irq_raised",
    "first_state",
    "convergence_result",
    "convergence_iterations",
    "convergence_final_qread",
    "convergence_final_status",
    "convergence_timeout",
    "failure_phase",
    "failure_reason",
    "failure_qread",
    "failure_status",
    "installed_vector",
    "nvic_enabled_before_submit",
    "nvic_pending_after_initial_clear",
    "nvic_active_before_submit",
    "irq_triggered_before_submit",
    "nvic_pending_before_final_clear",
    "nvic_pending_after_final_clear",
    "nvic_active_after_cleanup",
    "irq_triggered_after_cleanup",
    "mailbox_valid",
)

VARIANT_BY_ID = {1: "Q", 2: "QS", 3: "SQ"}

# STATUS bits, named where they are read rather than where they are decoded.
STATUS_STATE = 0x001
STATUS_IRQ_RAISED = 0x002
STATUS_RESET = 0x008
STATUS_CMD_END = 0x020
STATUS_FAULT_MASK = 0x314

U32_INVALID = 0xFFFFFFFF


@dataclass(frozen=True)
class PmuCompletionVisibilityV14Result:
    """One decoded frame. Every appendix word is a field, none is derived."""

    schema_version: int
    total_words: int
    run_sequence: int
    run_rc: int
    base_words: tuple = field(repr=False)

    variant_id: int = 0
    qsize_expected: int = 0
    pre_program_status: int = 0
    pre_submit_status: int = 0
    t_submit_after_cmd: int = 0
    t_primary_entry: int = 0
    t_first_observation: int = 0
    primary_result: int = 0
    primary_iterations: int = 0
    first_qread: int = 0
    first_status: int = 0
    first_q_done: int = 0
    first_cmd_end_reached: int = 0
    first_irq_raised: int = 0
    first_state: int = 0
    convergence_result: int = 0
    convergence_iterations: int = 0
    convergence_final_qread: int = 0
    convergence_final_status: int = 0
    convergence_timeout: int = 0
    failure_phase: int = 0
    failure_reason: int = 0
    failure_qread: int = 0
    failure_status: int = 0
    installed_vector: int = 0
    nvic_enabled_before_submit: int = 0
    nvic_pending_after_initial_clear: int = 0
    nvic_active_before_submit: int = 0
    irq_triggered_before_submit: int = 0
    nvic_pending_before_final_clear: int = 0
    nvic_pending_after_final_clear: int = 0
    nvic_active_after_cleanup: int = 0
    irq_triggered_after_cleanup: int = 0
    mailbox_valid: int = 0

    @property
    def variant(self) -> str:
        return VARIANT_BY_ID[self.variant_id]


def parse_payload(payload: bytes) -> PmuCompletionVisibilityV14Result:
    """Decode a schema-14 frame, or refuse it by name."""

    if len(payload) < HEADER_WORDS * 4:
        raise ProtocolError("V14 payload too short for the ABI header")
    magic, version, total_words, header_words, seq, _flags, rc, crc = struct.unpack_from(
        "<8I", payload
    )
    if magic != MAGIC:
        raise ProtocolError("bad PMU diagnostic magic 0x%08X" % magic)
    if version != SCHEMA_VERSION:
        # Deliberately not a fallback. A frame that is not schema 14 is not a
        # completion-visibility record, and reading its prefix anyway is how a
        # diagnostic becomes a measurement.
        raise ProtocolError(
            "unsupported schema %d: %s reads schema %d only" % (version, NAME, SCHEMA_VERSION)
        )
    if header_words != HEADER_WORDS:
        raise ProtocolError("unexpected V14 header_words %d" % header_words)
    if total_words != TOTAL_WORDS:
        raise ProtocolError(
            "declared %d payload words: the V14 frame is %d" % (total_words, TOTAL_WORDS)
        )
    if len(payload) != PAYLOAD_BYTES:
        raise ProtocolError(
            "V14 frame carried %d bytes, the contract is %d" % (len(payload), PAYLOAD_BYTES)
        )
    if v8.measurement_payload_crc(payload, total_words) != crc:
        raise ProtocolError("V14 payload CRC mismatch")

    body = struct.unpack_from("<%dI" % BODY_WORDS, payload, HEADER_WORDS * 4)
    base = body[:BASE_WORDS]
    appendix = dict(zip(APPENDIX_FIELDS, body[BASE_WORDS:]))

    # The magic is the firmware's statement that the appendix was filled in.
    # It is checked before any appendix word is believed, not after.
    if appendix["mailbox_valid"] != MAILBOX_VALID:
        raise ProtocolError(
            "V14 appendix carries no mailbox magic: 0x%08X" % appendix["mailbox_valid"]
        )
    if appendix["variant_id"] not in VARIANT_BY_ID:
        raise ProtocolError("V14 variant_id %d is not Q, QS or SQ" % appendix["variant_id"])
    if appendix["qsize_expected"] != QSIZE_EXPECTED:
        raise ProtocolError(
            "V14 qsize_expected 0x%X is not the frozen workload 0x%X"
            % (appendix["qsize_expected"], QSIZE_EXPECTED)
        )

    return PmuCompletionVisibilityV14Result(
        schema_version=version,
        total_words=total_words,
        run_sequence=seq,
        run_rc=rc,
        base_words=base,
        **appendix,
    )


def v8_prefix_view(result: PmuCompletionVisibilityV14Result) -> tuple:
    """The frozen 85-word prefix, for readers that predate the appendix.

    Available only from an already-validated V14 result, and only as the words
    themselves: handing back a re-headered frame would let an older parser
    publish this run under a schema it never carried.
    """

    if result.schema_version != SCHEMA_VERSION:
        raise ProtocolError("prefix view requires a validated V14 result")
    if len(result.base_words) != BASE_WORDS:
        raise ProtocolError(
            "prefix view requires the %d-word frozen body, found %d"
            % (BASE_WORDS, len(result.base_words))
        )
    return result.base_words


# ---------------------------------------------------------------------------
# Phase validity
#
# A frame carries words for every stage whether or not that stage ran, so the
# question a reader actually has is which of them mean anything. That is decided
# here, once, from the results the firmware published -- not by each consumer
# noticing that a timestamp looks like 0xFFFFFFFF.
#
# The rule throughout: a word is valid when the stage that writes it reached the
# point of writing it. Everything downstream of a failure is invalid even when
# the frame happens to carry a plausible number there.
# ---------------------------------------------------------------------------

PRIMARY_NOT_RUN = 0
PRIMARY_OBSERVED = 1
PRIMARY_TIMEOUT = 2
PRIMARY_RESET = 3
PRIMARY_FAULT = 4

CONVERGENCE_NOT_RUN = 0
CONVERGENCE_SUCCESS = 1
CONVERGENCE_TIMEOUT = 2
CONVERGENCE_RESET = 3
CONVERGENCE_FAULT = 4

PHASE_NONE = 0
PHASE_PRE_PROGRAM = 1
PHASE_PRE_SUBMIT = 2
PHASE_PRIMARY = 3
PHASE_CONVERGENCE = 4
PHASE_CLEANUP = 5

REASON_NONE = 0

ITERATION_BOUND = 10000

CATEGORY_Q_FIRST = "Q_FIRST"
CATEGORY_S5_FIRST = "S5_FIRST"
CATEGORY_SAME_ITERATION = "SAME_ITERATION"

PRIMARY_FAILURES = (PRIMARY_TIMEOUT, PRIMARY_RESET, PRIMARY_FAULT)
CONVERGENCE_FAILURES = (CONVERGENCE_TIMEOUT, CONVERGENCE_RESET, CONVERGENCE_FAULT)


def _iteration_is_well_formed(count: int, succeeded: bool) -> bool:
    """A stage that ran counts from one; a stage that did not counts zero."""

    return 1 <= count <= ITERATION_BOUND if succeeded else count == 0


def classify_payload(result: PmuCompletionVisibilityV14Result) -> dict:
    """Which phases of one frame mean anything, and what may be published.

    Returns a document rather than a verdict: a consumer that wants the first
    tuple has to read whether the first tuple is valid, and a consumer that
    wants a category gets one only where the contract allows a category at all.
    """

    primary_ok = result.primary_result == PRIMARY_OBSERVED
    convergence_ok = result.convergence_result == CONVERGENCE_SUCCESS
    pre_run_failed = result.failure_phase in (PHASE_PRE_PROGRAM, PHASE_PRE_SUBMIT)
    cleanup_failed = result.failure_phase == PHASE_CLEANUP
    submitted = not pre_run_failed

    problems = []

    # The stage results and the failure phase are two accounts of the same run,
    # and they have to agree. Disagreement is not a phase to be classified; it
    # is a frame nobody should read.
    if result.primary_result in PRIMARY_FAILURES and result.failure_phase != PHASE_PRIMARY:
        problems.append("primary failed but the failure phase is %d" % result.failure_phase)
    if (
        result.convergence_result in CONVERGENCE_FAILURES
        and result.failure_phase != PHASE_CONVERGENCE
    ):
        problems.append("convergence failed but the failure phase is %d" % result.failure_phase)
    if result.failure_phase == PHASE_NONE and result.failure_reason != REASON_NONE:
        problems.append("a failure reason without a failure phase")
    if pre_run_failed and result.primary_result != PRIMARY_NOT_RUN:
        problems.append("the primary loop ran after a pre-run failure")

    if not _iteration_is_well_formed(result.primary_iterations, primary_ok):
        problems.append(
            "primary_iterations %d does not match primary_result %d"
            % (result.primary_iterations, result.primary_result)
        )
    if not _iteration_is_well_formed(result.convergence_iterations, convergence_ok):
        problems.append(
            "convergence_iterations %d does not match convergence_result %d"
            % (result.convergence_iterations, result.convergence_result)
        )
    expected_timeout = 1 if result.convergence_result == CONVERGENCE_TIMEOUT else 0
    if result.convergence_timeout != expected_timeout:
        problems.append(
            "convergence_timeout %d does not match convergence_result %d"
            % (result.convergence_timeout, result.convergence_result)
        )

    q_only = result.variant == "Q"

    # --- the words themselves -------------------------------------------
    #
    # Everything above reads results and counts. These read the STATUS values
    # the firmware published, which is where a frame can satisfy every count
    # and still describe a run the contract says failed closed. The classifier
    # read none of them until the canonical fixture turned out to be such a
    # frame: pre-submit said running with a stale interrupt, the first tuple
    # carried reset_status, and the convergence tuple had a parse fault and no
    # cmd_end -- and it was classified valid.

    if submitted:
        for label, status in (
            ("pre_program_status", result.pre_program_status),
            ("pre_submit_status", result.pre_submit_status),
        ):
            if status & (STATUS_STATE | STATUS_RESET | STATUS_FAULT_MASK):
                problems.append("%s is not a stopped, unfaulted baseline: 0x%03X" % (label, status))
        # The submit-side baseline additionally has to be free of the two stale
        # bits, because a run that starts on them measures the previous one.
        if result.pre_submit_status & (STATUS_IRQ_RAISED | STATUS_CMD_END):
            problems.append(
                "pre_submit_status carries a stale irq or cmd_end: 0x%03X" % result.pre_submit_status
            )

    if primary_ok:
        if q_only:
            # Q read one register. Anything else in its tuple is a number
            # nobody measured, so the sentinel is what belongs there.
            for label, value in (
                ("first_status", result.first_status),
                ("first_cmd_end_reached", result.first_cmd_end_reached),
                ("first_irq_raised", result.first_irq_raised),
                ("first_state", result.first_state),
            ):
                if value != U32_INVALID:
                    problems.append("Q published %s=0x%X for a register it never read" % (label, value))
            if result.first_q_done != 1 or result.first_qread != QSIZE_EXPECTED:
                problems.append("Q observed completion without a complete queue cursor")
        else:
            status = result.first_status
            if status & (STATUS_RESET | STATUS_FAULT_MASK):
                problems.append("the first tuple carries reset or fault: 0x%03X" % status)
            # The flags and the STATUS are the same load and cannot disagree.
            if bool(status & STATUS_CMD_END) != bool(result.first_cmd_end_reached):
                problems.append("first_cmd_end_reached disagrees with the STATUS it came from")
            if bool(status & STATUS_IRQ_RAISED) != bool(result.first_irq_raised):
                problems.append("first_irq_raised disagrees with the STATUS it came from")
            if (status & STATUS_STATE) != result.first_state:
                problems.append("first_state disagrees with the STATUS it came from")
            if bool(result.first_q_done) != (result.first_qread == QSIZE_EXPECTED):
                problems.append("first_q_done disagrees with the queue cursor it came from")
            if not result.first_q_done and not result.first_cmd_end_reached:
                problems.append("the primary loop observed neither register and stopped anyway")
        # A run cannot observe before it entered, nor enter before it submitted.
        if not (result.t_submit_after_cmd <= result.t_primary_entry <= result.t_first_observation):
            problems.append("the run's timestamps do not advance through it")

    if convergence_ok:
        status = result.convergence_final_status
        required = STATUS_CMD_END | STATUS_IRQ_RAISED
        if status & required != required:
            problems.append("the convergence tuple does not carry cmd_end and irq: 0x%03X" % status)
        if status & (STATUS_STATE | STATUS_RESET | STATUS_FAULT_MASK):
            problems.append("the convergence tuple is running, resetting or faulted: 0x%03X" % status)
        if result.convergence_final_qread != QSIZE_EXPECTED:
            problems.append(
                "the convergence tuple's queue cursor is 0x%X, not the workload's 0x%X"
                % (result.convergence_final_qread, QSIZE_EXPECTED)
            )

    # The V12 hard bypass, as the frame reports it.
    if submitted and result.nvic_enabled_before_submit:
        problems.append("the NPU interrupt was enabled before submit")
    for label, value in (
        ("nvic_pending_after_initial_clear", result.nvic_pending_after_initial_clear),
        ("nvic_active_before_submit", result.nvic_active_before_submit),
        ("irq_triggered_before_submit", result.irq_triggered_before_submit),
    ):
        if submitted and value:
            problems.append("%s is set: the run did not start from a clean interrupt state" % label)

    succeeded = (
        not problems
        and result.failure_phase == PHASE_NONE
        and result.failure_reason == REASON_NONE
        and primary_ok
        and convergence_ok
    )

    phases = {
        # Submit-side timing exists once the run was allowed to start.
        "t_submit_after_cmd": submitted,
        "t_primary_entry": submitted,
        # The first-observation timestamp is written by the primary loop when it
        # observed something, so a timeout has no P1.
        "t_first_observation": primary_ok,
        "first_tuple": primary_ok,
        "convergence": convergence_ok,
        # The failure tuple is the one thing a failure does publish.
        "failure_tuple": result.failure_phase != PHASE_NONE,
        "cleanup_readbacks": submitted,
    }

    # Q observes one register, so its first tuple has no STATUS-derived words to
    # believe even when the tuple itself is valid.
    tuple_fields = {
        "first_qread": phases["first_tuple"],
        "first_q_done": phases["first_tuple"],
        "first_status": phases["first_tuple"] and not q_only,
        "first_cmd_end_reached": phases["first_tuple"] and not q_only,
        "first_irq_raised": phases["first_tuple"] and not q_only,
        "first_state": phases["first_tuple"] and not q_only,
    }

    category = None
    if succeeded and not q_only:
        q_done = result.first_q_done == 1
        cmd_end = result.first_cmd_end_reached == 1
        if q_done and cmd_end:
            category = CATEGORY_SAME_ITERATION
        elif q_done:
            category = CATEGORY_Q_FIRST
        elif cmd_end:
            category = CATEGORY_S5_FIRST
        else:
            problems.append("a successful primary observation that observed neither register")
            succeeded = False

    return {
        "variant": result.variant,
        "sample_valid": succeeded,
        "phases": phases,
        "first_tuple_fields": tuple_fields,
        "primary_result": result.primary_result,
        "convergence_result": result.convergence_result,
        "failure_phase": result.failure_phase,
        "failure_reason": result.failure_reason,
        # Q is a single-register variant: it has no read order to categorise, so
        # it never carries a category rather than carrying an empty one.
        "category": category,
        "category_scope": (
            "Q observes one register and has no read order to categorise"
            if q_only
            else "read order category, published only for a fully successful sample"
        ),
        # Nothing derived from an invalid phase may be published, and that
        # includes anything that would read like a performance number.
        "may_publish_distribution": succeeded,
        "may_publish_pmu_metric": False,
        "perturbed_by_convergence_tail": True,
        "not_comparable_to_v13": True,
        "not_performance_metric": True,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# The build manifest
#
# The manifest says which artifacts a build declared and what they hashed to.
# Verifying it means recomputing, not reading: a stored boolean is the build's
# opinion of itself, and a stored digest is only evidence once the bytes it
# claims to describe have been hashed again.
# ---------------------------------------------------------------------------

CANONICAL_JSON = "v14-canonical-json-v1"
MANIFEST_SELF_HASH_KEY = "manifest_self_hash"


def canonical_json_bytes(document: dict) -> bytes:
    """The one serialisation both sides hash.

    Sorted keys, no incidental whitespace, no NaN, one trailing newline. Two
    parties that disagree about any of these disagree about every digest they
    exchange, so the rule is named and written once.
    """

    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def manifest_self_hash(document: dict) -> str:
    """The digest of the manifest with its own hash key removed."""

    preimage = {key: value for key, value in document.items() if key != MANIFEST_SELF_HASH_KEY}
    return hashlib.sha256(canonical_json_bytes(preimage)).hexdigest()


def verify_manifest(document: dict, artifact_root: str, *, allow_undeclared: bool = False) -> dict:
    """Recompute everything the manifest asserts, or refuse it by name."""

    for key in ("variant", "schema_version", "build_id", "declared_artifacts"):
        if key not in document:
            raise ProtocolError("manifest carries no %s" % key)
    if document.get("canonical_json") != CANONICAL_JSON:
        raise ProtocolError(
            "manifest declares canonical form %r, this reader implements %r"
            % (document.get("canonical_json"), CANONICAL_JSON)
        )
    if document["schema_version"] != SCHEMA_VERSION:
        raise ProtocolError(
            "manifest declares schema %r, not %d" % (document["schema_version"], SCHEMA_VERSION)
        )
    if int(str(document["build_id"]), 16) != BUILD_ID:
        raise ProtocolError("manifest declares build %r" % (document["build_id"],))
    if document["variant"] not in VARIANT_BY_ID.values():
        raise ProtocolError("manifest declares variant %r" % (document["variant"],))

    stored = document.get(MANIFEST_SELF_HASH_KEY)
    if not isinstance(stored, str) or len(stored) != 64:
        raise ProtocolError("manifest carries no usable %s" % MANIFEST_SELF_HASH_KEY)
    recomputed = manifest_self_hash(document)
    if recomputed != stored:
        raise ProtocolError(
            "manifest self-hash mismatch: stored %s, recomputed %s" % (stored, recomputed)
        )

    table = document["declared_artifacts"]
    if not isinstance(table, dict) or not table:
        raise ProtocolError("manifest declares no artifacts")
    root = os.path.abspath(artifact_root)
    checked = {}
    for name in sorted(table):
        entry = table[name]
        if not isinstance(entry, dict) or "sha256" not in entry or "bytes" not in entry:
            raise ProtocolError("artifact %s is not declared with a digest and a size" % name)
        if os.path.isabs(name) or ".." in name.split("/"):
            raise ProtocolError("artifact %s is not a path inside the build" % name)
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            raise ProtocolError("artifact %s is declared and absent" % name)
        # A declared artifact has to be the build's own file. A symlink out of
        # the tree hashes clean and means the manifest stopped certifying what
        # was actually built -- the digest describes a file somewhere else.
        if os.path.islink(path):
            raise ProtocolError("artifact %s is a symlink, not a build output" % name)
        if os.path.realpath(path) != os.path.join(os.path.realpath(root), *name.split("/")):
            raise ProtocolError("artifact %s resolves outside the build root" % name)
        with open(path, "rb") as handle:
            payload = handle.read()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry["sha256"]:
            raise ProtocolError(
                "artifact %s hashes to %s, the manifest declares %s"
                % (name, digest, entry["sha256"])
            )
        if len(payload) != entry["bytes"]:
            raise ProtocolError(
                "artifact %s is %d bytes, the manifest declares %s"
                % (name, len(payload), entry["bytes"])
            )
        checked[name] = digest

    # Files the build left behind that the manifest never declared are not a
    # digest mismatch and are not silence either: a reader that hashes only what
    # it was told about cannot notice a second image sitting beside the first.
    present = set()
    for directory, _subdirectories, files in os.walk(root):
        for filename in files:
            relative = os.path.relpath(os.path.join(directory, filename), root)
            present.add(relative.replace(os.sep, "/"))
    undeclared = sorted(present - set(table))
    if undeclared and not allow_undeclared:
        # Reporting was not enough. A reader that hashes only what it was told
        # about cannot notice a second image sitting beside the first, and the
        # contract says an extra artifact is a mismatch rather than a note.
        raise ProtocolError(
            "the build root carries %d files the manifest does not declare, first %s"
            % (len(undeclared), undeclared[0])
        )

    bundle = hashlib.sha256(
        canonical_json_bytes({name: checked[name] for name in sorted(checked)})
    ).hexdigest()
    stored_bundle = document.get("artifact_bundle_sha256")
    if stored_bundle is not None and stored_bundle != bundle:
        raise ProtocolError(
            "artifact bundle hash mismatch: stored %s, recomputed %s" % (stored_bundle, bundle)
        )

    return {
        "variant": document["variant"],
        "artifacts_verified": len(checked),
        "manifest_self_hash_recomputed": recomputed,
        "undeclared_files_present": undeclared,
        # Which question was actually answered. A tree verified with
        # undeclared files allowed is a tree where "these artifacts are what
        # the manifest says" was checked and "these are the only artifacts"
        # was not, and the difference is the second image nobody looked for.
        "containment": "declared artifacts only" if not allow_undeclared else "declared artifacts verified; the tree was not required to hold only them",
        "artifact_bundle_sha256": bundle,
    }


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog=NAME, description="Schema-14 frame and manifest reader.")
    sub = parser.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("verify-manifest", help="recompute a build manifest's claims")
    manifest.add_argument("--manifest", required=True)
    manifest.add_argument("--artifact-root", required=True)
    manifest.add_argument(
        "--allow-undeclared",
        action="store_true",
        help="verify a raw build tree, which carries intermediates the manifest never declares",
    )
    args = parser.parse_args(argv)
    if args.command == "verify-manifest":
        try:
            with open(args.manifest, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            report = verify_manifest(
                document, args.artifact_root, allow_undeclared=args.allow_undeclared
            )
        except (ProtocolError, OSError, ValueError) as exc:
            print("MANIFEST FAIL %s" % exc)
            return 1
        print(
            "MANIFEST PASS variant=%s artifacts=%d bundle=%s"
            % (report["variant"], report["artifacts_verified"], report["artifact_bundle_sha256"][:16])
        )
        if report["undeclared_files_present"]:
            print(
                "  note: %d undeclared files present; containment was not checked"
                % len(report["undeclared_files_present"])
            )
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
