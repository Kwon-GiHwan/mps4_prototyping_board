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

import json
import os
import shutil

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
        """Accept one run, or refuse it for a named reason."""

        if self.campaign.stopped:
            raise CollectorError("the campaign is stopped: %s" % self.campaign.stop_reason)
        if self.complete:
            raise CollectorError(
                "cell %s already carries its %d runs" % (self.name, RUNS_PER_CELL)
            )
        if not sample.get("sample_valid"):
            # An invalid sample is not a run that can be repeated quietly. The
            # campaign's own rule is that the cell fails.
            raise CollectorError("run %s is not a valid sample" % sample.get("run_id"))
        expected = len(self.samples) + 1
        if sample.get("run_id") != expected:
            raise CollectorError(
                "cell %s expected run %d, was offered %s"
                % (self.name, expected, sample.get("run_id"))
            )
        boot = sample.get("boot_id")
        if self.boot_id is None:
            self.boot_id = boot
        elif boot != self.boot_id:
            raise CollectorError(
                "cell %s changed boot mid-cell: %s then %s" % (self.name, self.boot_id, boot)
            )
        self.samples.append(dict(sample))
        self._write()
        if self.complete:
            self.campaign._cell_completed(self)

    def fail(self, reason: str) -> None:
        """Quarantine this whole attempt and stop the campaign."""

        self.campaign._quarantine(self, reason)
        self.samples = []
        self.boot_id = None

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
        if not os.path.isfile(self._state_path):
            return
        with open(self._state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        self.stopped = bool(state.get("stopped"))
        self.stop_reason = state.get("stop_reason")
        self._attempts = dict(state.get("attempts", {}))
        self._completed = list(state.get("completed", []))

    def _save_state(self) -> None:
        with open(self._state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {"stopped": self.stopped, "stop_reason": self.stop_reason,
                 "attempts": self._attempts, "completed": sorted(self._completed)},
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
        attempt = self._attempts.get(name, 0) + 1
        self._attempts[name] = attempt
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
        self.stopped = False
        self.stop_reason = None
        self._save_state()
