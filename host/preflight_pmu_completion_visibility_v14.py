#!/usr/bin/env python3
"""The board preflight contract, as a state machine that refuses rather than warns.

V14 does not write a new board safety policy. The operational contract that
V11-A, V12 and V13 each ran against a real board already exists and already
qualified; what did not exist was an executable form of it. This is that form:
the same thresholds, cited to the documents that set them, arranged so that the
authorisation to deploy cannot be reached except through them.

Three things about the shape are deliberate.

**Three values, not two.** A gate answers PASS, FAIL or UNPROVEN. The third is
not decoration: this project has already stopped once at exactly that state --
no user-visible UART holder, but root ownership unprovable because sudo was not
available. A boolean would have had to call that True or False, and either
answer is a lie. ``GO`` requires every mandatory gate to be PASS, so UNPROVEN
stops the run without pretending to know why.

**Storage before liveness, liveness before deployment.** The order is the point.
The storage gate runs before anything changes on the board, so a mounted card or
a held UART stops the run while it is still reversible. The baseline gate proves
the known-good image is alive *before* V14 is deployed, so that a failure
afterwards can be attributed: a board that was already dead admits no
attribution at all.

**Two layers, kept apart.** The inherited gates are board policy and V14 may not
redefine them. The V14 gates are about this candidate -- its variant, its
manifest, the bytes about to be written -- and belong to this contract. Mixing
them would let a diagnostic quietly relax a safety threshold.

Nothing here touches a board. It decides, from readings someone else collected,
whether a board may be touched at all.
"""

from __future__ import annotations

import json
import sys


PASS = "PASS"
FAIL = "FAIL"
UNPROVEN = "UNPROVEN"
VERDICTS = (PASS, FAIL, UNPROVEN)


# ---------------------------------------------------------------------------
# Where the thresholds come from
#
# Pinned by commit and by blob hash rather than by line number: these documents
# are edited, and a threshold whose source is "the current version of a file"
# drifts silently. The blob hash is what the reader checks; the commit is where
# to find it.
# ---------------------------------------------------------------------------

QUAL_PROCEDURE = {
    "document": "firmware/Selftest_pmu_diag/PMU_QUAL_PROCEDURE.md",
    "section": "복구 후 REBOOT / USB_OFF 종료 상태",
    "commit": "82f931102199",
    "blob": "fe6805acd5a5",
}
V11A_BOARD_RESULT = {
    "document": "firmware/Selftest_pmu_diag/PMU_INTERVAL_ENTRY_DIAG_V11A_BOARD_RESULT.md",
    "section": "preflight: three PINGs in IDLE, root-inclusive UART holder checks",
    "commit": "f1948bcda523",
    "blob": "7355f473b060",
}
V12_BOARD_RESULT = {
    "document": "firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_BOARD_RESULT.md",
    "section": "boot50: DDR/CPUWAIT, PING 3/3 IDLE, zero mounts, zero holders",
    "commit": "f7da7e85bb50",
    "blob": "61bcc6c1ae37",
}
V13_BOARD_RESULT = {
    "document": "firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_BOARD_RESULT.md",
    "section": "runner PING 3/3 IDLE, seven protocol counters zero, four FTDI ports free",
    "commit": "d49fa5fe5b3a",
    "blob": "6c98a08221d2",
}

# The seven counters, spelled as the procedure spells them. A reading that
# carries six of them proves nothing about the seventh.
PROTOCOL_ERROR_COUNTERS = (
    "rx_overrun",
    "bad_magic",
    "bad_version",
    "bad_crc",
    "length_error",
    "sequence_error",
    "parser_resync",
)
FTDI_PORTS = ("ttyUSB0", "ttyUSB1", "ttyUSB2", "ttyUSB3")
REQUIRED_PINGS = 3
IDLE_STATE = 1


class PreflightError(Exception):
    """An illegal transition, or an authorisation asked for out of order."""


def _reading(readings, field):
    """The value of one field, or ``None`` when it was not established.

    A field that is absent and a field that is explicitly ``None`` mean the same
    thing here: nobody measured it. Both become UNPROVEN rather than a default.
    """

    return readings.get(field)


# ---------------------------------------------------------------------------
# The gates
#
# Each one is a pure function from a reading to a verdict. None of them consults
# anything but the reading it is handed, so a gate cannot pass by reaching for a
# second source when the first is silent.
# ---------------------------------------------------------------------------


def _zero_count(readings, field):
    value = _reading(readings, field)
    if value is None:
        return UNPROVEN, "%s was not established" % field
    if not isinstance(value, int) or isinstance(value, bool):
        return UNPROVEN, "%s is %r, which is not a count" % (field, value)
    if value != 0:
        return FAIL, "%s is %d, and the contract requires 0" % (field, value)
    return PASS, "%s is 0" % field


def gate_mount_count(readings):
    return _zero_count(readings, "mount_count")


def gate_block_write_holders(readings):
    return _zero_count(readings, "block_device_write_holders")


def gate_uart_holders(readings):
    """Zero userspace holders on all four FTDI ports, root included.

    The reading has to say, per port, that a root-inclusive check ran. A count
    of zero from a check that could not see root-owned processes is the state
    this project stopped at once already, and it is UNPROVEN, not PASS.
    """

    holders = _reading(readings, "uart_holders")
    if holders is None:
        return UNPROVEN, "no UART holder reading"
    if not isinstance(holders, dict):
        return UNPROVEN, "UART holder reading is %r" % type(holders).__name__
    missing = [port for port in FTDI_PORTS if port not in holders]
    if missing:
        return UNPROVEN, "no reading for %s" % ", ".join(missing)
    for port in FTDI_PORTS:
        entry = holders[port]
        if not isinstance(entry, dict):
            return UNPROVEN, "%s reading is %r" % (port, type(entry).__name__)
        if entry.get("root_inclusive") is not True:
            return UNPROVEN, "%s was not checked for root-owned holders" % port
        count = entry.get("holders")
        if count is None:
            return UNPROVEN, "%s carries no holder count" % port
        if not isinstance(count, int) or isinstance(count, bool):
            return UNPROVEN, "%s holder count is %r" % (port, count)
        if count != 0:
            return FAIL, "%s has %d userspace holder(s)" % (port, count)
    return PASS, "all four FTDI ports free, root-inclusive"


def gate_usb_off(readings):
    """After USB_OFF: the card is gone and nothing is mounted."""

    confirmed = _reading(readings, "usb_off_confirmed")
    if confirmed is None:
        return UNPROVEN, "USB_OFF was not confirmed either way"
    if confirmed is not True:
        return FAIL, "USB_OFF was not confirmed"
    present = _reading(readings, "block_device_present")
    if present is None:
        return UNPROVEN, "no reading for the block device"
    if present is not False:
        return FAIL, "/dev/sdb is still present after USB_OFF"
    return PASS, "USB_OFF confirmed and /dev/sdb absent"


def gate_ddr_selftest(readings):
    value = _reading(readings, "ddr_selftest_passed")
    if value is None:
        return UNPROVEN, "no DDR self-test reading"
    if value is not True:
        return FAIL, "DDR self-test did not report PASSED"
    return PASS, "DDR self-test PASSED"


def gate_cpuwait(readings):
    value = _reading(readings, "cpuwait_cleared")
    if value is None:
        return UNPROVEN, "no CPUWAIT reading"
    if value is not True:
        return FAIL, "CPUWAIT is not cleared"
    return PASS, "CPUWAIT cleared"


def gate_ping_liveness(readings):
    """Three PINGs, every one of them answered from IDLE."""

    pings = _reading(readings, "pings")
    if pings is None:
        return UNPROVEN, "no PING reading"
    if not isinstance(pings, (list, tuple)):
        return UNPROVEN, "PING reading is %r" % type(pings).__name__
    if len(pings) != REQUIRED_PINGS:
        return FAIL, "%d PING(s) recorded, the contract requires %d" % (
            len(pings),
            REQUIRED_PINGS,
        )
    for index, entry in enumerate(pings):
        if not isinstance(entry, dict):
            return UNPROVEN, "PING %d is %r" % (index, type(entry).__name__)
        answered = entry.get("answered")
        if answered is None:
            return UNPROVEN, "PING %d does not say whether it was answered" % index
        if answered is not True:
            return FAIL, "PING %d was not answered" % index
        state = entry.get("state")
        if state is None:
            return UNPROVEN, "PING %d carries no state" % index
        if state != IDLE_STATE:
            return FAIL, "PING %d answered from state %r, not IDLE" % (index, state)
    return PASS, "%d/%d PINGs answered from IDLE" % (REQUIRED_PINGS, REQUIRED_PINGS)


def gate_protocol_errors(readings):
    """All seven counters zero, and all seven of them present."""

    counters = _reading(readings, "protocol_errors")
    if counters is None:
        return UNPROVEN, "no protocol error reading"
    if not isinstance(counters, dict):
        return UNPROVEN, "protocol error reading is %r" % type(counters).__name__
    missing = [name for name in PROTOCOL_ERROR_COUNTERS if name not in counters]
    if missing:
        return UNPROVEN, "no reading for %s" % ", ".join(missing)
    nonzero = [
        "%s=%r" % (name, counters[name])
        for name in PROTOCOL_ERROR_COUNTERS
        if counters[name] != 0
    ]
    if nonzero:
        return FAIL, "protocol error counters not zero: %s" % ", ".join(nonzero)
    return PASS, "all seven protocol error counters zero"


def gate_candidate_identity(readings):
    """The bytes about to be deployed are the bytes that were qualified."""

    declared = _reading(readings, "candidate_digests")
    qualified = _reading(readings, "qualified_digests")
    if declared is None or qualified is None:
        return UNPROVEN, "the candidate or the qualified digest table is missing"
    if not isinstance(declared, dict) or not isinstance(qualified, dict):
        return UNPROVEN, "a digest table is not a table"
    if not qualified:
        return UNPROVEN, "the qualified digest table is empty"
    missing = sorted(set(qualified) - set(declared))
    if missing:
        return FAIL, "the candidate declares no %s" % ", ".join(missing)
    extra = sorted(set(declared) - set(qualified))
    if extra:
        return FAIL, "the candidate carries undeclared %s" % ", ".join(extra)
    differing = sorted(name for name in qualified if declared[name] != qualified[name])
    if differing:
        return FAIL, "the candidate's %s does not match what was qualified" % ", ".join(
            differing
        )
    return PASS, "every deployed artifact matches the qualified digest"


def gate_variant_identity(readings):
    """The candidate is one of this contract's three variants, and says so."""

    variant = _reading(readings, "candidate_variant")
    manifest_variant = _reading(readings, "manifest_variant")
    if variant is None or manifest_variant is None:
        return UNPROVEN, "the candidate or manifest variant is missing"
    if variant not in ("Q", "QS", "SQ"):
        return FAIL, "%r is not a variant this contract defines" % variant
    if variant != manifest_variant:
        return FAIL, "the candidate is %r and its manifest declares %r" % (
            variant,
            manifest_variant,
        )
    return PASS, "candidate and manifest agree on %s" % variant


def gate_manifest_replay(readings):
    """The manifest verified against the bundle it describes, here, now."""

    verified = _reading(readings, "manifest_verified")
    if verified is None:
        return UNPROVEN, "the manifest was not replayed"
    if verified is not True:
        return FAIL, "the manifest did not verify against its bundle"
    return PASS, "manifest replayed and verified"


def gate_gate_evidence(readings):
    """The static gates passed on this candidate, not on some earlier one."""

    for field, label in (
        ("real_elf_pass", "REAL_ELF"),
        ("read_order_equivalent", "read-order equivalence"),
        ("common_tail_shared", "the shared convergence tail"),
    ):
        value = _reading(readings, field)
        if value is None:
            return UNPROVEN, "no evidence for %s" % label
        if value is not True:
            return FAIL, "%s did not pass for this candidate" % label
    return PASS, "REAL_ELF, read-order and common-tail evidence present"


# ---------------------------------------------------------------------------
# The registry
#
# Two layers, kept apart on purpose. The inherited layer is board policy: its
# thresholds are cited, not chosen, and a diagnostic has no business moving
# them. The V14 layer is about this candidate and belongs to this contract.
# ---------------------------------------------------------------------------

INHERITED = "inherited"
V14_SPECIFIC = "v14"

STORAGE = "STORAGE"
BASELINE = "BASELINE"
CANDIDATE = "CANDIDATE"

GATES = (
    {
        "id": "MOUNT_COUNT",
        "stage": STORAGE,
        "layer": INHERITED,
        "meaning": "nothing has the card mounted before the board state is changed",
        "threshold": "mount_count == 0",
        "source": QUAL_PROCEDURE,
        "evidence_field": "mount_count",
        "evaluate": gate_mount_count,
    },
    {
        "id": "BLOCK_WRITE_HOLDERS",
        "stage": STORAGE,
        "layer": INHERITED,
        "meaning": "no process holds the block device open for writing",
        "threshold": "block_device_write_holders == 0",
        "source": V12_BOARD_RESULT,
        "evidence_field": "block_device_write_holders",
        "evaluate": gate_block_write_holders,
    },
    {
        "id": "UART_OWNERSHIP",
        "stage": STORAGE,
        "layer": INHERITED,
        "meaning": "no userspace holder on any FTDI port, root-owned processes included",
        "threshold": "root-inclusive holders == 0 on ttyUSB0..3",
        "source": V11A_BOARD_RESULT,
        "evidence_field": "uart_holders",
        "evaluate": gate_uart_holders,
    },
    {
        "id": "USB_OFF",
        "stage": STORAGE,
        "layer": INHERITED,
        "meaning": "the run starts from USB off with the card gone",
        "threshold": "USB_OFF confirmed and /dev/sdb absent",
        "source": QUAL_PROCEDURE,
        "evidence_field": "usb_off_confirmed",
        "evaluate": gate_usb_off,
    },
    {
        "id": "DDR_SELFTEST",
        "stage": BASELINE,
        "layer": INHERITED,
        "meaning": "the known-good image boots and its DDR self-test passes",
        "threshold": "DDR self-test PASSED == True",
        "source": QUAL_PROCEDURE,
        "evidence_field": "ddr_selftest_passed",
        "evaluate": gate_ddr_selftest,
    },
    {
        "id": "CPUWAIT",
        "stage": BASELINE,
        "layer": INHERITED,
        "meaning": "the core is running rather than held",
        "threshold": "CPUWAIT cleared == True",
        "source": QUAL_PROCEDURE,
        "evidence_field": "cpuwait_cleared",
        "evaluate": gate_cpuwait,
    },
    {
        "id": "PING_LIVENESS",
        "stage": BASELINE,
        "layer": INHERITED,
        "meaning": "the runner answers, three times, from IDLE",
        "threshold": "3/3 answered with state == IDLE",
        "source": V13_BOARD_RESULT,
        "evidence_field": "pings",
        "evaluate": gate_ping_liveness,
    },
    {
        "id": "PROTOCOL_ERRORS",
        "stage": BASELINE,
        "layer": INHERITED,
        "meaning": "the transport carried those PINGs without a single error",
        "threshold": "all seven counters == 0",
        "source": QUAL_PROCEDURE,
        "evidence_field": "protocol_errors",
        "evaluate": gate_protocol_errors,
    },
    {
        "id": "CANDIDATE_IDENTITY",
        "stage": CANDIDATE,
        "layer": V14_SPECIFIC,
        "meaning": "the bytes about to be written are the bytes that were qualified",
        "threshold": "every deployed artifact digest equals the qualified digest",
        "source": None,
        "evidence_field": "candidate_digests",
        "evaluate": gate_candidate_identity,
    },
    {
        "id": "VARIANT_IDENTITY",
        "stage": CANDIDATE,
        "layer": V14_SPECIFIC,
        "meaning": "the candidate is one of Q/QS/SQ and its manifest agrees",
        "threshold": "candidate variant == manifest variant, in Q/QS/SQ",
        "source": None,
        "evidence_field": "candidate_variant",
        "evaluate": gate_variant_identity,
    },
    {
        "id": "MANIFEST_REPLAY",
        "stage": CANDIDATE,
        "layer": V14_SPECIFIC,
        "meaning": "the manifest verifies against the bundle being deployed",
        "threshold": "manifest replay == PASS",
        "source": None,
        "evidence_field": "manifest_verified",
        "evaluate": gate_manifest_replay,
    },
    {
        "id": "STATIC_GATE_EVIDENCE",
        "stage": CANDIDATE,
        "layer": V14_SPECIFIC,
        "meaning": "REAL_ELF, read-order equivalence and the shared tail passed on this candidate",
        "threshold": "all three present and true",
        "source": None,
        "evidence_field": "real_elf_pass",
        "evaluate": gate_gate_evidence,
    },
)

STAGE_ORDER = (STORAGE, BASELINE, CANDIDATE)


def gates_for(stage):
    return tuple(gate for gate in GATES if gate["stage"] == stage)


def evaluate_stage(stage, readings):
    """``(verdict, [per-gate result])`` for one stage.

    The stage is PASS only when every gate in it is PASS. FAIL beats UNPROVEN in
    the report -- a refusal with a reason is more useful than a refusal without
    one -- but neither authorises anything.
    """

    results = []
    for gate in gates_for(stage):
        verdict, detail = gate["evaluate"](readings)
        if verdict not in VERDICTS:
            raise PreflightError("%s returned %r" % (gate["id"], verdict))
        results.append(
            {
                "gate": gate["id"],
                "layer": gate["layer"],
                "verdict": verdict,
                "detail": detail,
                "threshold": gate["threshold"],
            }
        )
    if any(result["verdict"] == FAIL for result in results):
        return FAIL, results
    if any(result["verdict"] == UNPROVEN for result in results):
        return UNPROVEN, results
    return PASS, results


# ---------------------------------------------------------------------------
# The state machine
#
# The states exist so that the authorisation is not a boolean somebody can set.
# Deployment is reachable only from DEPLOYMENT_AUTHORIZED, and that state is
# reachable only by passing storage and then baseline, in that order.
# ---------------------------------------------------------------------------

INITIAL = "INITIAL"
STORAGE_SAFE = "STORAGE_SAFE"
BASELINE_LIVE = "BASELINE_LIVE"
DEPLOYMENT_AUTHORIZED = "DEPLOYMENT_AUTHORIZED"
STOPPED = "STOPPED"

LEGAL_TRANSITIONS = {
    INITIAL: (STORAGE_SAFE, STOPPED),
    STORAGE_SAFE: (BASELINE_LIVE, STOPPED),
    BASELINE_LIVE: (DEPLOYMENT_AUTHORIZED, STOPPED),
    DEPLOYMENT_AUTHORIZED: (STOPPED,),
    STOPPED: (),
}

STAGE_ENTERS = {
    STORAGE: STORAGE_SAFE,
    BASELINE: BASELINE_LIVE,
    CANDIDATE: DEPLOYMENT_AUTHORIZED,
}


class Preflight:
    """One run of the contract. A stopped run does not restart.

    The stage methods are the only way to move, and each one refuses to run out
    of order rather than evaluating its gates and hoping the caller checked.
    """

    def __init__(self):
        self._state = INITIAL
        self._history = ()
        self._results = {}

    @property
    def state(self):
        return self._state

    @property
    def history(self):
        return self._history

    @property
    def results(self):
        return dict(self._results)

    def _move(self, target, reason):
        if target not in LEGAL_TRANSITIONS[self._state]:
            raise PreflightError(
                "%s -> %s is not a transition this contract allows" % (self._state, target)
            )
        self._history = self._history + ((self._state, target, reason),)
        self._state = target

    def run_stage(self, stage, readings):
        """Evaluate one stage and move, or stop.

        Stopping is a transition too, and it is recorded: a run that stopped at
        the storage gate and a run that never started are different things.
        """

        if stage not in STAGE_ORDER:
            raise PreflightError("%r is not a stage of this contract" % stage)
        expected = STAGE_ORDER[len(self._results)] if len(self._results) < len(STAGE_ORDER) else None
        if stage != expected:
            raise PreflightError(
                "%s cannot run here: this contract runs %s"
                % (stage, " then ".join(STAGE_ORDER))
            )
        verdict, results = evaluate_stage(stage, readings)
        self._results[stage] = results
        if verdict != PASS:
            self._move(STOPPED, "%s stage is %s" % (stage, verdict))
            return verdict, results
        self._move(STAGE_ENTERS[stage], "%s stage passed" % stage)
        return verdict, results

    def authorized(self):
        return self._state == DEPLOYMENT_AUTHORIZED

    def require_authorization(self):
        """The call a deployment makes before it writes anything.

        It raises rather than returning False so that a caller who forgets to
        look at the answer still cannot deploy.
        """

        if self._state != DEPLOYMENT_AUTHORIZED:
            raise PreflightError(
                "deployment is not authorised: the contract is in %s" % self._state
            )
        return True

    def report(self):
        mandatory_unproven = [
            result["gate"]
            for results in self._results.values()
            for result in results
            if result["verdict"] == UNPROVEN
        ]
        return {
            "state": self._state,
            "authorized": self.authorized(),
            "stages": {stage: self._results.get(stage, []) for stage in STAGE_ORDER},
            "mandatory_unproven": sorted(mandatory_unproven),
            "transitions": [
                {"from": source, "to": target, "reason": reason}
                for source, target, reason in self._history
            ],
        }


def run_preflight(storage, baseline, candidate):
    """The whole contract, in order, stopping at the first stage that is not PASS."""

    preflight = Preflight()
    for stage, readings in (
        (STORAGE, storage),
        (BASELINE, baseline),
        (CANDIDATE, candidate),
    ):
        verdict, _results = preflight.run_stage(stage, readings)
        if verdict != PASS:
            break
    return preflight


def main(argv=None):
    """Decide from a readings file. It reads JSON; it does not read a board."""

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: preflight_pmu_completion_visibility_v14.py <readings.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[0], "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        print("readings unreadable: %s" % exc, file=sys.stderr)
        return 2
    missing = [key for key in ("storage", "baseline", "candidate") if key not in document]
    if missing:
        print("readings carry no %s section" % ", ".join(missing), file=sys.stderr)
        return 2
    preflight = run_preflight(
        document["storage"], document["baseline"], document["candidate"]
    )
    report = preflight.report()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["authorized"]:
        print("PREBOARD_GATE GO")
        return 0
    print("PREBOARD_GATE STOP: %s" % report["state"], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
