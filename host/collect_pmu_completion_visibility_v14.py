"""Campaign collection for PMU_COMPLETION_VISIBILITY_DIAG_V14.

The board's part -- opening a port, sending a command, reading a frame -- is
not here. What is here is the bookkeeping that decides whether a run counts,
because that is where nine good runs and one bad one quietly become a ten-run
cell.

The rules it enforces are the campaign's, not this module's convenience:

  * a cell is ten consecutive valid runs numbered 1..10 on one unchanged boot;
  * a failure anywhere in an attempt quarantines that whole attempt, including
    the runs that had already succeeded, and stops the campaign;
  * a retry needs an explicit disposition and a restored board, and starts over
    at run 1 in a new attempt;
  * completed cells survive a reopen only while every identity input -- source,
    image, classifier, manifest, contract -- is byte-identical.

Nothing here deletes. Quarantine is a move, so a failed attempt stays readable
as the evidence it is.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil

try:
    from host import runner_proto_pmu_completion_visibility_v14 as v14
except ModuleNotFoundError:  # pragma: no cover - direct script fallback
    import runner_proto_pmu_completion_visibility_v14 as v14

VARIANTS = ("Q", "QS", "SQ")
RUNS_PER_CELL = 10
IDENTITY_KEYS = (
    "source_sha256",
    "image_sha256",
    "classifier_sha256",
    "manifest_sha256",
    "contract_sha256",
)


class CollectorError(RuntimeError):
    """A refusal with a reason. Never raised for something the board did."""


def payload_digest(payload: bytes) -> str:
    """The digest the campaign records for a frame, over the bytes as received."""

    return hashlib.sha256(payload).hexdigest()


class Cell:
    """One matrix cell: a round, a position in the order, and a variant."""

    def __init__(self, campaign: "Campaign", round_index: int, position: int, variant: str,
                 attempt: int):
        self.campaign = campaign
        self.round_index = round_index
        self.position = position
        self.variant = variant
        self.attempt = attempt
        self.samples: list[dict] = []
        self.boot_id: str | None = None
        self.dead: str | None = None
        os.makedirs(self.attempt_path(attempt), exist_ok=True)

    @property
    def name(self) -> str:
        return "%d-%d-%s" % (self.round_index, self.position, self.variant)

    def attempt_path(self, attempt: int) -> str:
        return os.path.join(self.campaign.root, "cells", self.name, "attempt-%d" % attempt)

    @property
    def complete(self) -> bool:
        return len(self.samples) == RUNS_PER_CELL

    def record(self, sample: dict) -> None:
        """Accept one run, or end the attempt.

        Every refusal here quarantines the attempt and stops the campaign before
        it raises. Raising alone was the defect: the caller could catch the
        error, offer the run again, and turn nine good runs and one bad one into
        a ten-run cell -- the exact thing this module's docstring says it
        prevents. A run that is not acceptable is not a run to be retried; it is
        the end of the attempt.
        """

        if self.campaign.stopped:
            raise CollectorError("the campaign is stopped: %s" % self.campaign.stop_reason)
        if self.dead:
            raise CollectorError("cell %s is over: %s" % (self.name, self.dead))
        if self.complete:
            raise CollectorError(
                "cell %s already carries its %d runs" % (self.name, RUNS_PER_CELL)
            )
        if not sample.get("sample_valid"):
            self._end("run %s is not a valid sample" % sample.get("run_id"))
        variant = sample.get("variant")
        if variant is not None and variant != self.variant:
            self._end(
                "run %s carries variant %s in a %s cell" % (sample.get("run_id"), variant, self.variant)
            )
        expected = len(self.samples) + 1
        if sample.get("run_id") != expected:
            self._end(
                "cell %s expected run %d, was offered %s"
                % (self.name, expected, sample.get("run_id"))
            )
        boot = sample.get("boot_id")
        if self.boot_id is not None and boot != self.boot_id:
            self._end(
                "cell %s changed boot mid-cell: %s then %s" % (self.name, self.boot_id, boot)
            )
        if self.boot_id is None:
            self.boot_id = boot
        self.samples.append(dict(sample))
        self._write()
        if self.complete:
            self.campaign._cell_completed(self)

    def record_frame(self, payload: bytes, *, boot_id: str, reread: bytes | None = None) -> dict:
        """Parse, classify and record one frame. The only honest entry point.

        `record()` takes a dict and believes its `sample_valid`. That is the
        right shape for testing the bookkeeping and the wrong one for a
        campaign: it lets a run be declared good by whoever offers it. Here the
        verdict is derived from the bytes -- the parser decides whether it is a
        V14 frame at all, and the phase classifier decides whether it is a
        sample -- and the caller supplies only what it alone knows, the boot it
        came from and the optional second read.
        """

        digest = payload_digest(payload)
        if reread is not None and payload_digest(reread) != digest:
            self._end(
                "the frame and its re-read differ: %s against %s"
                % (digest[:16], payload_digest(reread)[:16])
            )
        try:
            result = v14.parse_payload(payload)
        except v14.ProtocolError as exc:
            self._end("the frame is not a V14 record: %s" % exc)
        document = v14.classify_payload(result)
        if document["variant"] != self.variant:
            self._end(
                "the frame carries variant %s in a %s cell" % (document["variant"], self.variant)
            )
        if not document["sample_valid"]:
            self._end(
                "the frame is not a valid sample: %s"
                % (document["problems"][0] if document["problems"]
                   else "phase %d reason %d" % (result.failure_phase, result.failure_reason))
            )
        sample = {
            # The firmware's own run counter, not the caller's idea of one.
            "run_id": result.run_sequence,
            "boot_id": boot_id,
            "variant": document["variant"],
            "sample_valid": True,
            "payload_sha256": digest,
            "reread_matched": reread is not None,
            "category": document["category"],
            "primary_iterations": result.primary_iterations,
            "convergence_iterations": result.convergence_iterations,
            "convergence_timeout": result.convergence_timeout,
            "first_q_done": result.first_q_done,
            "first_cmd_end_reached": result.first_cmd_end_reached,
            # The words those two flags were derived from, carried so that the
            # analyzer can re-derive the read-order category rather than trust a
            # field this collector computed. A verdict that reads a derived
            # field is a verdict about that field.
            "first_qread": result.first_qread,
            "qsize_expected": result.qsize_expected,
            "first_status": result.first_status,
            "q_observation_cycles": (result.t_first_observation - result.t_primary_entry) & 0xFFFFFFFF,
        }
        self.record(sample)
        return sample

    def _end(self, reason: str):
        """Quarantine, stop, then raise. Never raise without the first two."""

        self.fail(reason)
        raise CollectorError(reason)

    def fail(self, reason: str) -> None:
        """Quarantine this whole attempt and stop the campaign."""

        self.campaign._quarantine(self, reason)
        self.samples = []
        self.boot_id = None
        self.dead = reason

    def _write(self) -> None:
        path = os.path.join(self.attempt_path(self.attempt), "samples.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {"cell": self.name, "attempt": self.attempt, "boot_id": self.boot_id,
                 "samples": self.samples},
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")


class Campaign:
    """The whole matrix, and the one stop flag that governs it."""

    def __init__(self, root: str, identity: dict):
        self.root = os.path.abspath(root)
        missing = [key for key in IDENTITY_KEYS if key not in identity]
        if missing:
            raise CollectorError("campaign identity is missing %s" % ", ".join(missing))
        self.identity = {key: identity[key] for key in IDENTITY_KEYS}
        os.makedirs(self.root, exist_ok=True)
        self._identity_path = os.path.join(self.root, "campaign_identity.json")
        self._state_path = os.path.join(self.root, "campaign_state.json")
        self._check_identity()
        self._load_state()

    # --- identity ----------------------------------------------------------
    def _check_identity(self) -> None:
        if os.path.isfile(self._identity_path):
            with open(self._identity_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            drift = [key for key in IDENTITY_KEYS if stored.get(key) != self.identity[key]]
            if drift:
                # Not a warning. A campaign whose inputs changed halfway is two
                # campaigns wearing one name, and its cells cannot be pooled.
                raise CollectorError(
                    "campaign inputs changed (%s): the campaign restarts from round one"
                    % ", ".join(sorted(drift))
                )
            return
        with open(self._identity_path, "w", encoding="utf-8") as handle:
            json.dump(self.identity, handle, indent=2, sort_keys=True)
            handle.write("\n")

    # --- state -------------------------------------------------------------
    def _load_state(self) -> None:
        self.stopped = False
        self.stop_reason = None
        self._attempts: dict[str, int] = {}
        self._completed: list[str] = []
        self._disposed: dict[str, bool] = {}
        if not os.path.isfile(self._state_path):
            return
        with open(self._state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        self.stopped = bool(state.get("stopped"))
        self.stop_reason = state.get("stop_reason")
        self._attempts = dict(state.get("attempts", {}))
        self._completed = list(state.get("completed", []))
        self._disposed = dict(state.get("disposed", {}))

    def _save_state(self) -> None:
        with open(self._state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {"stopped": self.stopped, "stop_reason": self.stop_reason,
                 "attempts": self._attempts, "completed": sorted(self._completed),
                 "disposed": self._disposed},
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")

    # --- cells -------------------------------------------------------------
    def cell(self, round_index: int, position: int, variant: str) -> Cell:
        if variant not in VARIANTS:
            raise CollectorError("variant %r is not one of %s" % (variant, ", ".join(VARIANTS)))
        if self.stopped:
            raise CollectorError(
                "the campaign is stopped and needs a disposition: %s" % self.stop_reason
            )
        name = "%d-%d-%s" % (round_index, position, variant)
        if name in self._completed:
            raise CollectorError("cell %s is already complete" % name)
        # Attempts advance only after a failure was disposed of. Handing out a
        # fresh attempt on request is retry-until-clean: a cell could be run
        # until it happened to yield ten good samples, with the abandoned
        # attempts sitting in cells/ rather than quarantine/.
        attempt = self._attempts.get(name, 0)
        if attempt and not self._disposed.get(name):
            raise CollectorError(
                "cell %s already has attempt %d and no disposition released it" % (name, attempt)
            )
        attempt += 1
        self._attempts[name] = attempt
        self._disposed.pop(name, None)
        self._save_state()
        return Cell(self, round_index, position, variant, attempt)

    def _cell_completed(self, cell: Cell) -> None:
        if cell.name not in self._completed:
            self._completed.append(cell.name)
        self._save_state()

    def completed_cells(self) -> list[str]:
        return sorted(self._completed)

    def formal_samples(self) -> list[str]:
        formal = os.path.join(self.root, "samples")
        if not os.path.isdir(formal):
            return []
        return sorted(os.listdir(formal))

    # --- failure -----------------------------------------------------------
    def _quarantine(self, cell: Cell, reason: str) -> None:
        source = cell.attempt_path(cell.attempt)
        target = os.path.join(self.root, "quarantine", "%s-attempt-%d" % (cell.name, cell.attempt))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.isdir(source):
            shutil.move(source, target)
        else:
            os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "STOP.json"), "w", encoding="utf-8") as handle:
            json.dump(
                {"cell": cell.name, "attempt": cell.attempt, "reason": reason,
                 "runs_discarded": len(cell.samples), "disposition": None},
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
        self.stopped = True
        self.stop_reason = "%s: %s" % (cell.name, reason)
        self._save_state()

    def quarantined(self) -> list[str]:
        root = os.path.join(self.root, "quarantine")
        if not os.path.isdir(root):
            return []
        return sorted(os.path.join(root, name) for name in os.listdir(root))

    def dispose(self, disposition: str, *, board_restored: bool) -> None:
        """Clear the stop, once somebody has said what happened and restored the board."""

        if not self.stopped:
            raise CollectorError("there is no stop to dispose of")
        if not board_restored:
            raise CollectorError(
                "a disposition without a restored board is not a disposition: the next attempt "
                "would start from the state that failed"
            )
        if not disposition or not disposition.strip():
            raise CollectorError("a disposition needs a reason somebody wrote down")
        for path in self.quarantined():
            stop_file = os.path.join(path, "STOP.json")
            if not os.path.isfile(stop_file):
                continue
            with open(stop_file, "r", encoding="utf-8") as handle:
                record = json.load(handle)
            if record.get("disposition") is None:
                record["disposition"] = disposition
                record["board_restored"] = True
                with open(stop_file, "w", encoding="utf-8") as handle:
                    json.dump(record, handle, indent=2, sort_keys=True)
                    handle.write("\n")
        # The cell that failed is the one a retry is released for, and only it.
        for path in self.quarantined():
            name = os.path.basename(path).rsplit("-attempt-", 1)[0]
            self._disposed[name] = True
        self.stopped = False
        self.stop_reason = None
        self._save_state()
