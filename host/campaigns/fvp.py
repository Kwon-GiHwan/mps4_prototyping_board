"""Run one fresh FVP process and retain raw output before classification."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from .build import MEMORY_ERROR, command, digest, executable_identity
from .errors import CellFailure
from .options import validate_options
from .measurement import EXECUTION_ERRORS, MEMORY_ERRORS


def run_fvp(cell, config, artifacts, run_dir: Path):
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    target, options = cell["target"], cell["options"]
    validate_options(target, options)
    identity = executable_identity(target["executable"])
    for probe in ("--version", "--list-params"):
        name = probe.removeprefix("--")
        try:
            command([target["executable"], probe], run_dir, name, 10)
            identity[name + "_returncode"] = 0
        except CellFailure as exc:
            if exc.status == "ENVIRONMENT_UNAVAILABLE":
                raise
            identity[name + "_probe_failure"] = exc.status
    axf = Path(artifacts["axf"])
    if not axf.is_file() or digest(axf) != artifacts["hashes"]["axf"]:
        raise CellFailure("IDENTITY_MISMATCH", "identity", "AXF changed since build")
    uart, log_path = run_dir / "uart.txt", run_dir / "fvp.log"
    if uart.exists() or log_path.exists():
        raise CellFailure("EXECUTION_ERROR", "preflight", "Run directory must be fresh")
    board = target["board_prefix"]
    parameters = {
        target["mac_parameter"]: options["mac"],
        f"{board}.visualisation.disable-visualisation": 1,
        f"{board}.telnetterminal0.start_telnet": 0,
        f"{board}.uart0.out_file": str(uart),
        f"{board}.uart0.unbuffered_output": 1,
    }
    for key, value in options.get("fvp_parameters", {}).items():
        if key in parameters:
            raise CellFailure("EXECUTION_ERROR", "configuration", f"Reserved FVP override: {key}")
        parameters[key] = value
    argv = [target["executable"], "-a", str(axf)]
    for key, value in parameters.items():
        argv.extend(["-C", f"{key}={value}"])
    (run_dir / "command.json").write_text(json.dumps(argv, indent=2))
    start = time.monotonic()
    failure = None
    with log_path.open("w") as log:
        try:
            process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            raise CellFailure("ENVIRONMENT_UNAVAILABLE", "fvp", str(exc)) from exc
        try:
            while True:
                text = uart.read_text(errors="replace") if uart.exists() else ""
                combined = text + "\n" + log_path.read_text(errors="replace")
                code = process.poll()
                if MEMORY_ERROR.search(combined) or any(message in combined.lower() for message in MEMORY_ERRORS):
                    failure = ("MEMORY_ERROR", "Memory allocation failure")
                    break
                if any(message in combined.lower() for message in EXECUTION_ERRORS):
                    failure = ("EXECUTION_ERROR", "Fatal runtime diagnostic")
                    break
                if code is not None and code != 0:
                    failure = ("EXECUTION_ERROR", f"FVP exited with {code}")
                    break
                if "Inference completed." in text:
                    # Let a just-finished process report its natural failure code
                    # before intentionally terminating the usual idle FVP loop.
                    try:
                        code = process.wait(timeout=0.05)
                    except subprocess.TimeoutExpired:
                        code = None
                    if code is not None and code != 0:
                        failure = ("EXECUTION_ERROR", f"FVP exited with {code}")
                        break
                    text = uart.read_text(errors="replace")
                    combined = text + "\n" + log_path.read_text(errors="replace")
                    if MEMORY_ERROR.search(combined) or any(message in combined.lower() for message in MEMORY_ERRORS):
                        failure = ("MEMORY_ERROR", "Memory allocation failure")
                        break
                    if any(message in combined.lower() for message in EXECUTION_ERRORS):
                        failure = ("EXECUTION_ERROR", "Fatal runtime diagnostic")
                        break
                    counts = re.findall(r"Total number of inferences:\s*(\d+)", text)
                    if counts != ["1"]:
                        failure = ("INVALID_MEASUREMENT", "Expected exactly one inference")
                    break
                if code is not None:
                    failure = ("EXECUTION_ERROR", "FVP exited without completion")
                    break
                if time.monotonic() - start >= config["measurement"]["timeout_seconds"]:
                    failure = ("TIMEOUT", "FVP inference timed out")
                    break
                time.sleep(0.02)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    if failure:
        raise CellFailure(failure[0], "fvp", f"{failure[1]}; see {uart} and {log_path}")
    if executable_identity(target["executable"]) != {key: identity[key] for key in ("path", "sha256")}:
        raise CellFailure("IDENTITY_MISMATCH", "identity", "FVP executable changed during execution")
    return {"uart": uart.read_text(errors="replace"), "uart_path": str(uart),
            "uart_sha256": digest(uart), "log_path": str(log_path),
            "wall_clock_seconds": time.monotonic() - start, "command": argv, "executable_identity": identity}
