"""Build the selected model with the campaign's explicit MLEK options."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess

from .errors import CellFailure
from .options import validate_options


MEMORY_ERROR = re.compile(
    r"out of memory|cannot allocate memory|failed to allocate tensors|"
    r"tensor allocation failed|failed to resize buffer|"
    r"region .+ overflowed|will not fit in region|arena .+ too small", re.I)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable_identity(executable):
    path = shutil.which(str(executable))
    if path is None:
        raise CellFailure("ENVIRONMENT_UNAVAILABLE", "preflight", f"Executable unavailable: {executable}")
    resolved = Path(path).resolve()
    return {"path": str(resolved), "sha256": digest(resolved)}


def command(argv, directory, stage, timeout, env=None):
    """Retain the command and complete combined output, including failures."""
    directory = Path(directory)
    (directory / f"{stage}.command.json").write_text(json.dumps(argv, indent=2))
    log_path = directory / f"{stage}.log"
    with log_path.open("w") as log:
        try:
            proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, start_new_session=True)
        except OSError as exc:
            raise CellFailure("ENVIRONMENT_UNAVAILABLE", stage, str(exc)) from exc
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise CellFailure("TIMEOUT", stage, f"See {log_path}") from exc
        finally:
            # Also clean up on KeyboardInterrupt, filesystem errors and failed
            # commands that left children behind after the main process exited.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    output = log_path.read_text(errors="replace")
    if code:
        status = "MEMORY_ERROR" if MEMORY_ERROR.search(output) else "BUILD_ERROR"
        raise CellFailure(status, stage, f"Exit {code}; see {log_path}")
    return output


def verify_cache(path, definitions):
    entries = {}
    if Path(path).is_file():
        for line in Path(path).read_text().splitlines():
            match = re.fullmatch(r"([^#/:][^:]*):[^=]+=(.*)", line)
            if match:
                entries[match[1]] = match[2]
    bool_keys = {"ETHOS_U_NPU_ENABLED", "ETHOS_U_NPU_TIMING_ADAPTER_ENABLED", "FPGA_PLATFORM_SSE_320"}
    path_keys = {"CMAKE_TOOLCHAIN_FILE", "inference_runner_MODEL_PATH"}
    for key, expected in definitions.items():
        actual = entries.get(key)
        if actual is None:
            raise CellFailure("IDENTITY_MISMATCH", "identity", f"Resolved CMake value missing: {key}")
        if key in bool_keys:
            actual = {"1": "ON", "TRUE": "ON", "YES": "ON", "0": "OFF", "FALSE": "OFF", "NO": "OFF"}.get(actual.upper(), actual.upper())
        elif key in path_keys:
            actual, expected = str(Path(actual).resolve()), str(Path(expected).resolve())
        elif key == "inference_runner_ACTIVATION_BUF_SZ":
            try:
                actual, expected = int(actual, 0), int(str(expected), 0)
            except ValueError:
                pass
        if actual != expected:
            raise CellFailure("IDENTITY_MISMATCH", "identity", f"Resolved CMake value differs: {key}")
    return entries


def build(cell, config, directory: Path):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    settings, options, target = config["build"], cell["options"], cell["target"]
    validate_options(target, options)
    root = Path(settings["mlek_root"]).resolve()
    model = Path(cell["model"]["path"])
    if not model.is_absolute():
        model = root / model
    if not root.is_dir() or not model.is_file():
        raise CellFailure("ENVIRONMENT_UNAVAILABLE", "preflight", f"Missing MLEK root or model: {model}")
    if digest(model) != cell["model"]["sha256"]:
        raise CellFailure("IDENTITY_MISMATCH", "identity", "Source model SHA256 mismatch")
    inputs = {"model": model}
    for name, setting in (("vela_config", "vela_config"), ("toolchain", "toolchain_file")):
        path = Path(settings[setting])
        inputs[name] = path if path.is_absolute() else root / path
        if not inputs[name].is_file():
            raise CellFailure("ENVIRONMENT_UNAVAILABLE", "preflight", f"Missing input: {inputs[name]}")
    input_hashes = {name: digest(path) for name, path in inputs.items()}
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(settings["epoch"]))
    timeout = settings["timeout_seconds"]
    revision = settings.get("mlek_revision")
    try:
        source_root = command(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                              directory, "mlek-root", timeout).strip()
    except CellFailure as exc:
        raise CellFailure("ENVIRONMENT_UNAVAILABLE", "identity", "MLEK source is not an identifiable Git checkout") from exc
    if Path(source_root).resolve() != root:
        raise CellFailure("ENVIRONMENT_UNAVAILABLE", "identity", "MLEK root is not the Git repository root")
    observed = command(["git", "-C", str(root), "rev-parse", "HEAD"], directory,
                       "mlek-revision", timeout).strip()
    if revision and observed != revision:
        raise CellFailure("IDENTITY_MISMATCH", "identity", "MLEK revision mismatch")
    dirty = command(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                    directory, "mlek-status", timeout)
    if dirty.strip():
        raise CellFailure("IDENTITY_MISMATCH", "identity", "MLEK tracked sources are modified")
    vela_dir, build_dir = directory / "vela", directory / "build"
    # Reusing output can silently pair a new request with a stale executable.
    if vela_dir.exists() or build_dir.exists():
        raise CellFailure("BUILD_ERROR", "preflight", "Build directory must be fresh")
    vela_dir.mkdir()
    vela = str(settings["vela"])
    tools = {name: executable_identity(settings[name]) for name in ("vela", "cmake")}
    versions = {}
    for name, argv in (("vela-version", [vela, "--version"]),
                       ("cmake-version", [str(settings["cmake"]), "--version"])):
        versions[name] = command(argv, directory, name, timeout, env)
    vela_help = command([vela, "--help"], directory, "vela-help", timeout, env)
    accelerator = f'{target["npu"]}-{options["mac"]}'
    enumerated = re.search(r"--accelerator-config\s*\{([^}]+)\}", vela_help, re.S)
    if enumerated and accelerator not in {x.strip() for x in enumerated[1].split(",")}:
        raise CellFailure("UNSUPPORTED_CONFIGURATION", "vela", f"Vela does not enumerate {accelerator}")
    extra = options.get("vela_options", [])
    vela_config, toolchain = inputs["vela_config"], inputs["toolchain"]
    vela_output = command([vela, "--accelerator-config", accelerator, "--config", str(vela_config),
                          "--system-config", options["system_config"], "--memory-mode", options["memory_mode"],
                          "--optimise", options["optimise"], "--output-dir", str(vela_dir),
                          *extra, str(model)], directory, "vela", timeout, env)
    compiled = vela_dir / f"{model.stem}_vela.tflite"
    if not compiled.is_file():
        raise CellFailure("BUILD_ERROR", "vela", "Vela did not produce the requested model")
    compiled_hash = digest(compiled)
    family = target["npu"].removeprefix("ethos-").upper()
    prefix = {"U55": "H", "U65": "Y", "U85": "Z"}[family]
    definitions = {
        "CMAKE_TOOLCHAIN_FILE": str(toolchain), "CMAKE_BUILD_TYPE": "Release",
        "TARGET_PLATFORM": target["platform"],
        "TARGET_SUBSYSTEM": target["subsystem"], "ETHOS_U_NPU_ID": family,
        "ETHOS_U_NPU_CONFIG_ID": prefix + str(options["mac"]),
        "ETHOS_U_NPU_MEMORY_MODE": options["memory_mode"], "ETHOS_U_NPU_ENABLED": "ON",
        "ETHOS_U_NPU_TIMING_ADAPTER_ENABLED": target["timing_adapter"],
        "FPGA_PLATFORM_SSE_320": "ON" if target.get("kind") == "board" else "OFF",
        "USE_CASE_BUILD": "inference_runner",
        "inference_runner_ACTIVATION_BUF_SZ": str(options["activation_bytes"]),
        "inference_runner_MODEL_PATH": str(compiled),
    }
    for additions in (target.get("cmake_options", {}), options.get("cmake_options", {})):
        for key, value in additions.items():
            definitions[key] = str(value)
    cmake = str(settings["cmake"])
    command([cmake, "-B", str(build_dir), "-S", str(root),
             *[f"-D{key}={value}" for key, value in definitions.items()]],
            directory, "configure", timeout, env)
    cache_path = build_dir / "CMakeCache.txt"
    configured_cache = verify_cache(cache_path, definitions)
    for name in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER"):
        if not configured_cache.get(name):
            raise CellFailure("IDENTITY_MISMATCH", "identity", "Compiler missing from CMake cache: " + name)
        tools[name] = executable_identity(configured_cache[name])
    command([cmake, "--build", str(build_dir), "-j", str(settings["jobs"])],
            directory, "build", timeout, env)
    axf = build_dir / "bin" / "mlek_inference_runner.axf"
    if not axf.is_file():
        raise CellFailure("BUILD_ERROR", "build", "Requested inference_runner AXF missing")
    resolved_cache = verify_cache(cache_path, definitions)
    for name, path in inputs.items():
        if not path.is_file() or digest(path) != input_hashes[name]:
            raise CellFailure("IDENTITY_MISMATCH", "identity", f"Build input changed: {name}")
    if digest(compiled) != compiled_hash:
        raise CellFailure("IDENTITY_MISMATCH", "identity", "Compiled model changed during build")
    for name, identity in tools.items():
        if executable_identity(settings.get(name, identity["path"])) != identity:
            raise CellFailure("IDENTITY_MISMATCH", "identity", f"Build executable changed: {name}")
    final_revision = command(["git", "-C", str(root), "rev-parse", "HEAD"], directory,
                             "mlek-revision-after", timeout).strip()
    final_dirty = command(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                          directory, "mlek-status-after", timeout)
    if final_revision != observed or final_dirty.strip():
        raise CellFailure("IDENTITY_MISMATCH", "identity", "MLEK source changed during build")
    deployable_hashes = {str(path.relative_to(axf.parent)): digest(path)
                         for path in sorted(axf.parent.rglob("*")) if path.is_file()}
    return {"axf": str(axf), "bin_dir": str(axf.parent),
            "hashes": {**input_hashes, "vela": compiled_hash, "axf": digest(axf)},
            "input_paths": {name: str(path.resolve()) for name, path in inputs.items()},
            "model_path": str(model.resolve()), "vela_path": str(compiled),
            "deployable_hashes": deployable_hashes,
            "resolved": {"cmake": definitions, "cache": resolved_cache,
                         "timing_adapter": target["timing_adapter"], "mlek_revision": observed,
                         "source_identity": "VERIFIED_GIT_SOURCE",
                         "versions": versions, "source_date_epoch": settings["epoch"]},
            "tools": tools,
            "cpu_operations": [line for line in vela_output.splitlines() if "CPU" in line]}
