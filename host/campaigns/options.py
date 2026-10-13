"""Validate extension options without permitting measurement-contract overrides."""
import re

from .errors import CellFailure


_VELA_FLAGS = {"--verbose-all", "--show-cpu-operations"}
_VELA_INTS = {"--arena-cache-size": 0, "--hillclimb-max-iterations": 0,
              "--max-block-dependency": 0, "--cpu-tensor-alignment": 1,
              "--recursion-limit": 1}
_BUILD_TYPES = {"Debug", "Release", "RelWithDebInfo", "MinSizeRel"}


def _reject(detail):
    raise CellFailure("UNSUPPORTED_CONFIGURATION", "configuration", detail)


def validate_options(target, options):
    """Accept only exact Vela tokens, supported CMake extras and literal FVP keys."""
    argv = options.get("vela_options", [])
    if not isinstance(argv, list) or any(not isinstance(v, str) for v in argv):
        _reject("vela_options must be a list of string arguments")
    seen = set()
    index = 0
    while index < len(argv):
        token = argv[index]
        name, equal, value = token.partition("=")
        if name in seen:
            _reject("Duplicate Vela option: " + name)
        seen.add(name)
        if name in _VELA_FLAGS:
            if equal:
                _reject("Vela flag takes no value: " + name)
        elif name in _VELA_INTS or name == "--tensor-allocator":
            if not equal:
                index += 1
                if index == len(argv):
                    _reject("Missing Vela option value: " + name)
                value = argv[index]
            if name == "--tensor-allocator":
                if value not in ("Greedy", "HillClimb"):
                    _reject("Invalid Vela tensor allocator")
            elif not re.fullmatch(r"[0-9]+", value) or int(value) < _VELA_INTS[name]:
                _reject("Invalid Vela integer: " + name)
            elif name == "--cpu-tensor-alignment" and int(value) & (int(value) - 1):
                _reject("CPU tensor alignment must be a power of two")
        else:
            _reject("Reserved or unknown Vela option: " + name)
        index += 1
    for additions in (target.get("cmake_options", {}), options.get("cmake_options", {})):
        if not isinstance(additions, dict):
            _reject("cmake_options must be an object")
        for key, value in additions.items():
            if key != "CMAKE_BUILD_TYPE" or not isinstance(value, str) or value not in _BUILD_TYPES:
                _reject("Reserved or unsupported CMake option: " + str(key))
    parameters = options.get("fvp_parameters", {})
    if not isinstance(parameters, dict):
        _reject("fvp_parameters must be an object")
    for key, value in parameters.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]+(?:[.][A-Za-z0-9_-]+)*", key)
                or key.endswith(".num_macs") or re.search(r"(?:^|\.)uart[0-9]+\.", key)
                or ".telnetterminal" in key or ".visualisation." in key):
            _reject("Reserved or nonliteral FVP parameter: " + str(key))
        if type(value) not in (str, int, bool) or (isinstance(value, str) and any(c in value for c in "\r\n\x00")):
            _reject("FVP parameter values must be scalar strings, integers or booleans")
