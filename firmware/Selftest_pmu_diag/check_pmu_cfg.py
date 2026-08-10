"""Fail-closed gate and manifest for the schema-v8 CFG A/B/C characterization.

CHARACTERIZATION ONLY. Nothing here is latency, T_npu, a performance baseline,
a Production GO, Gate 7, or MLEK data, and the +514 offset observed in the
Gate 1 fixed-image campaign is NOT generalized to these images.

Design rule: this gate REUSES the pure analysis helpers of check_pmu_qual.py
rather than restating them. Every structural term -- vendor source/object
identity, the unique target callsite, caller/return/release ordering, the hook
snapshot -> disable -> DSB -> readback -> latch order, compiler flags, symbol
survival -- is evaluated by calling the SAME function the Q0/Q1 qualification
gate calls, in the same order. That is what makes "the common path is
identical" a fact rather than a claim: there is only one implementation of it.

check_pmu_qual.py is imported, never modified. The Q0/Q1 gate keeps its own
unconditional no-CFG-write rule; this file does not weaken or reach into it.

Exactly ONE term is substituted, because it is the experiment's single
variable: check_pmu_qual.check_no_cfg_write() asserts "zero PMCCNTR_CFG
writes" unconditionally, which is correct for Q0/Q1 and correct for case A but
false by design for B and C. It is replaced here by a case-aware contract that
is strictly stronger than the original for A (same zero-write assertion, via
the same helper) and exact for B and C.

  A  0 PMCCNTR_CFG writes, no value
  B  exactly 1 write of the generated START=CYCLE / STOP=NO_EVENT value
  C  exactly 1 write of the generated explicit zero

A and C are the load-bearing pair: both leave the final CFG value at zero, yet
the write counts differ 0 vs 1. A value comparison alone cannot separate
"never programmed" from "programmed to zero"; the write count can.

No CFG value is written as a literal here. Both are composed from the
GENERATED register header exactly as the C macros compose them, so this gate
and the firmware cannot drift apart without one of them failing.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_pmu_qual as q  # noqa: E402  (path set above)

GateError = q.GateError

CASES = ("A", "B", "C")

# The CFG images are Q1 H-PRINTF images in every structural respect: same
# callsite, same hook, same symbols. Reusing the Q1 mode string is what makes
# check_symbols() and check_hook_structure() apply their Q1 rules unchanged.
CFG_STRUCTURAL_MODE = "Q1"

CASE_ID = {"A": 1, "B": 2, "C": 3}

# Declared identity-only metadata. These MAY differ between cases; everything
# else in the manifest may not. Kept as one list so the matrix gate and the
# documentation cannot disagree about what "identity only" means.
IDENTITY_ONLY_KEYS = (
    "build_id",
    "cfg_case",
    "cfg_case_id",
    "cfg_expected_write_count",
    "cfg_expected_value",
    "artifact_sha256",
)

# compiler_flags is deliberately NOT in the list above. Exempting it wholesale
# would let an arbitrary -O level, a builtin/LTO change, an include-path edit
# or any unrelated -D drift between the three images and still pass, which
# would silently destroy the single-variable claim.
#
# It is instead compared NORMALIZED by check_compiler_flags_identity(): exactly
# two token kinds may vary, and every other token -- and the ORDER of all of
# them -- must be identical.
NORMALIZED_KEYS = ("compiler_flags",)

# The only flag tokens allowed to differ between cases, each collapsed to a
# placeholder before comparison. Anything else that differs fails closed.
CFG_VARIABLE_FLAGS = (
    (re.compile(r"^-DRUNNER_FIRMWARE_BUILD_ID=.+$"), "<BUILD_ID>"),
    (re.compile(r"^-DPMU_DIAG_CASE_[ABC]$"), "<CASE>"),
)

# Tokens every case must carry. These are the terms that make the image a
# schema-v8 Q1 H-PRINTF CFG-experiment image at all; if one goes missing the
# build is not the thing the experiment claims to vary.
# Matches any PMU_DIAG_CASE define, used to count them rather than merely
# look for the expected one.
CASE_MACRO_RE = re.compile(r"^-DPMU_DIAG_CASE_[ABC]$")

REQUIRED_FLAGS = (
    "-DPMU_QUAL_CFG_EXPERIMENT",
    "-DPMU_QUAL_SCHEMA_V8",
    "-DPMU_QUAL_MODE_Q1",
    "-DPMU_DIAG_SEAM_S1",
    "-fno-builtin-printf",
)


def normalize_compiler_flags(flags):
    """Token list with ONLY the two declared variable flags collapsed.

    Order is preserved and significant: a reordered command line can change
    macro precedence and include resolution, so it is treated as a difference.
    """
    out = []
    for token in flags.split():
        for pattern, placeholder in CFG_VARIABLE_FLAGS:
            if pattern.match(token):
                token = placeholder
                break
        out.append(token)
    return out


def check_compiler_flags_identity(docs):
    """Every compiler flag and its position identical, bar the two declared."""
    norm = {case: normalize_compiler_flags(doc.get("compiler_flags", ""))
            for case, doc in docs.items()}
    reference_case = sorted(norm)[0]
    reference = norm[reference_case]
    for case in sorted(norm):
        if norm[case] == reference:
            continue
        diff = [(n, a, b) for n, (a, b) in
                enumerate(zip(reference, norm[case])) if a != b]
        detail = ("first differing token #%d: %s has %r, %s has %r"
                  % (diff[0][0], reference_case, diff[0][1], case, diff[0][2])
                  if diff else
                  "token counts differ: %s has %d, %s has %d"
                  % (reference_case, len(reference), case, len(norm[case])))
        raise GateError(
            "compiler flags differ between cases beyond the two declared "
            "variable flags (build id and case macro); %s" % detail)

    for case in sorted(docs):
        tokens = docs[case].get("compiler_flags", "").split()

        # EXACTLY ONE case macro in the whole command line. "At least one of
        # mine" is not enough: a duplicated -DPMU_DIAG_CASE_B, or mine plus
        # another case's, leaves the effective case decided by compiler
        # precedence rather than by the build graph.
        case_tokens = [t for t in tokens
                       if CASE_MACRO_RE.match(t)]
        if len(case_tokens) != 1:
            raise GateError(
                "case %s must carry exactly ONE PMU_DIAG_CASE macro, found %d: %s"
                % (case, len(case_tokens), case_tokens))
        want_case = "-DPMU_DIAG_CASE_%s" % case
        if case_tokens[0] != want_case:
            raise GateError("case %s carries %s, expected %s"
                            % (case, case_tokens[0], want_case))

        # EXACTLY ONE build-id define, and it must AGREE with the manifest.
        # A second -D would silently win, and a compiler value that disagrees
        # with the manifest means the record identity and the image identity
        # describe different things.
        bid_tokens = [t for t in tokens
                      if t.startswith("-DRUNNER_FIRMWARE_BUILD_ID=")]
        if len(bid_tokens) != 1:
            raise GateError(
                "case %s must carry exactly ONE RUNNER_FIRMWARE_BUILD_ID "
                "define, found %d: %s" % (case, len(bid_tokens), bid_tokens))
        raw = bid_tokens[0].split("=", 1)[1]
        try:
            flag_build_id = int(raw, 0)
        except ValueError:
            raise GateError("case %s has an unparsable RUNNER_FIRMWARE_BUILD_ID "
                            "value %r" % (case, raw))
        try:
            manifest_build_id = int(docs[case]["build_id"], 16)
        except (KeyError, TypeError, ValueError):
            raise GateError("case %s has no parsable manifest build_id (%r)"
                            % (case, docs[case].get("build_id")))
        if flag_build_id != manifest_build_id:
            raise GateError(
                "case %s compiler build id 0x%08X does not match the manifest "
                "build id 0x%08X" % (case, flag_build_id, manifest_build_id))

        for required in REQUIRED_FLAGS:
            if required not in tokens:
                raise GateError("case %s is missing the required flag %s"
                                % (case, required))
        if re.search(r"(^|\s)-f(no-)?lto\b", docs[case].get("compiler_flags", "")) \
                and "-fno-lto" not in tokens:
            raise GateError("case %s enables LTO" % case)
    return reference

# Unavoidable LAYOUT consequence of the case action, kept separate from the
# metadata above and from the causal CFG operation itself.
#
# The hook function is byte-identical across A/B/C -- every address INSIDE it
# (cycle read, disable, DSB, PMCR readback, post-disable capture, latch,
# return) compares equal. What moves is where the wrapper CALLS it from: cases
# B and C emit one extra PMCCNTR_CFG write plus its readback earlier in the
# same translation unit, so everything after that point shifts by the size of
# those instructions.
#
# This is NOT waved through. The rule below is strictly stronger than "ignore
# it": case A performs no write, so its call address must be the LOWEST, and
# B and C must both sit strictly above it. A difference in the other direction
# would mean the shift did not come from the added write, and fails closed.
LAYOUT_SHIFT_KEYS = ("hook_wrapper_call_address",)


def _plain_define(header_text, name):
    """Read a plain integer #define from the GENERATED register header.

    check_pmu_qual._regs_header_offset only accepts hex, but the event numbers
    and shifts are decimal. Same no-second-source rule: the value comes from
    the generated header, never from a literal in this file.
    """
    hits = re.findall(r"^\s*#define\s+%s\s+(0x[0-9A-Fa-f]+|\d+)U?\s*$" % name,
                      header_text, re.M)
    if len(hits) != 1:
        raise GateError("%s: expected 1 definition in the generated register "
                        "header, found %d" % (name, len(hits)))
    return int(hits[0], 0)


def generated_cfg_values(cfg_header_text):
    """Compose the case B and case C values exactly as the C macros do.

    B mirrors NPU_PMU_CYCLE_CFG_VALUE (npu_pmu_regs.h); C mirrors
    NPU_PMU_DIAG_CFG_NO_EVENT (runner_pmu_diag_main.c). Both are built from
    the generated event numbers and the generated shift/mask macros, so a
    regenerated header moves this gate and the firmware together.
    """
    cycle = _plain_define(cfg_header_text, "NPU_PMU_EVENT_CYCLE")
    no_event = _plain_define(cfg_header_text, "NPU_PMU_EVENT_NO_EVENT")
    start_shift = _plain_define(cfg_header_text, "NPU_PMU_PMCCNTR_CFG_START_SHIFT")
    start_mask = _plain_define(cfg_header_text, "NPU_PMU_PMCCNTR_CFG_START_MASK")
    stop_shift = _plain_define(cfg_header_text, "NPU_PMU_PMCCNTR_CFG_STOP_SHIFT")
    stop_mask = _plain_define(cfg_header_text, "NPU_PMU_PMCCNTR_CFG_STOP_MASK")

    b_value = (((cycle << start_shift) & start_mask)
               | ((no_event << stop_shift) & stop_mask))
    c_value = (((no_event << start_shift) & start_mask)
               | ((no_event << stop_shift) & stop_mask))

    # C is the "explicit zero" case by construction. If the generated NO_EVENT
    # number ever stopped being zero this would stop being an explicit-zero
    # write, and the experiment's A/C pair would silently change meaning.
    if c_value != 0:
        raise GateError("case C is defined as an explicit ZERO write, but the "
                        "generated NO_EVENT encoding composes to 0x%X" % c_value)
    if b_value == 0:
        raise GateError("case B must program a non-zero cycle configuration, "
                        "but the generated encoding composes to zero")
    return b_value, c_value


def case_contract(case, cfg_header_text):
    """(expected write count, expected written value or None) for a case."""
    if case not in CASES:
        raise GateError("unknown CFG case %r, expected one of %s"
                        % (case, ", ".join(CASES)))
    b_value, c_value = generated_cfg_values(cfg_header_text)
    return {"A": (0, None), "B": (1, b_value), "C": (1, c_value)}[case]


def _cfg_writes(preprocessed_text, cfg_header_text):
    """Every PMCCNTR_CFG write in the preprocessed TU, as written values.

    Counted after #if resolution, so what is counted is what the compiler
    actually saw for THIS case -- the same rule check_diag_case.py uses.
    """
    offset = q._regs_header_offset(cfg_header_text, "NPU_REG_PMCCNTR_CFG")
    pattern = (r"pmu_reg_write\s*\(\s*0x0*%X[Uu]?\s*,\s*([^;]*?)\)\s*;" % offset)
    return [m.group(1).strip() for m in re.finditer(pattern, preprocessed_text)]


def _literal_value(expr):
    """Resolve a fully macro-expanded C integer expression to its value.

    The preprocessed text has already expanded every macro, so what remains is
    arithmetic over literals. Anything else is refused rather than guessed.
    """
    cleaned = re.sub(r"\b(\d+|0[xX][0-9a-fA-F]+)[uUlL]+\b",
                     lambda m: m.group(1), expr)
    if not re.fullmatch(r"[0-9xXa-fA-F()\s+|&<>*/~^-]+", cleaned or ""):
        raise GateError("refusing to evaluate a PMCCNTR_CFG write argument "
                        "that is not pure integer arithmetic: %r" % expr)
    try:
        return int(eval(cleaned, {"__builtins__": {}}, {}))  # noqa: S307
    except Exception as exc:
        raise GateError("could not resolve the PMCCNTR_CFG write argument %r: %s"
                        % (expr, exc))


def check_cfg_case_contract(case, preprocessed_text, cfg_header_text):
    """The ONE substituted term. Returns (count, value or None)."""
    want_count, want_value = case_contract(case, cfg_header_text)

    if case == "A":
        # Delegate to the ORIGINAL Q0/Q1 helper so case A is held to exactly
        # the qualification rule, by the same code, with no restatement.
        q.check_no_cfg_write(preprocessed_text, cfg_header_text)
        return 0, None

    writes = _cfg_writes(preprocessed_text, cfg_header_text)
    if len(writes) != want_count:
        raise GateError("case %s expects exactly %d PMCCNTR_CFG write(s) in the "
                        "preprocessed translation unit, found %d"
                        % (case, want_count, len(writes)))
    got_value = _literal_value(writes[0])
    if got_value != want_value:
        raise GateError("case %s writes PMCCNTR_CFG = 0x%X, but the generated "
                        "encoding requires 0x%X"
                        % (case, got_value, want_value))
    return want_count, want_value


def evaluate_cfg(case, disassembly_text, nm_text, strings_text,
                 relocation_text, object_disassembly_text,
                 object_sections_text, vendor_source_text,
                 interface_header_text, compiler_flags, preprocessed_text,
                 cfg_header_text):
    """Mirror check_pmu_qual.evaluate() term for term, substituting only CFG.

    Every call below is the qualification gate's own function. The ordering is
    deliberately identical so a future edit to the Q0/Q1 gate cannot leave this
    path silently behind.
    """
    test_cpm = q.check_test_cpm(vendor_source_text)
    q.check_single_terminal_release(vendor_source_text)
    q.check_compiler_flags(compiler_flags)

    cfg_count, cfg_value = check_cfg_case_contract(
        case, preprocessed_text, cfg_header_text)

    q.check_symbols(nm_text, CFG_STRUCTURAL_MODE)
    reg_offsets = {name: q._regs_header_offset(cfg_header_text, name)
                   for name in q.REGS_HEADER_OFFSETS}

    printf_relocs, puts_relocs = q.parse_relocations(relocation_text)
    if puts_relocs:
        raise GateError("the vendor object carries %d puts-family relocation(s); "
                        "no printf in it may be folded" % puts_relocs)

    object_evidence = q.check_object_target_relocation(
        q.parse_disassembly(object_disassembly_text),
        q.parse_section_dumps(object_sections_text))

    cmd_addr = q.npu_cmd_address(vendor_source_text, interface_header_text)
    funcs = q.parse_disassembly(disassembly_text).functions
    pool = q.literal_pool(funcs)
    data = q.parse_section_dump(strings_text)

    hits = q.find_target_callsites(funcs, pool, data)
    if len(hits) != 1:
        raise GateError("expected exactly 1 target callsite, found %d" % len(hits))
    fn, index = hits[0]
    if fn.name != q.CALLER_SYMBOL:
        raise GateError("the target callsite is in caller <%s>, expected <%s>"
                        % (fn.name, q.CALLER_SYMBOL))
    if fn.insns[index].callee != q.WRAP_PRINTF_SYMBOL:
        raise GateError("the target call resolves to <%s>, expected <%s>"
                        % (fn.insns[index].callee, q.WRAP_PRINTF_SYMBOL))

    stop_addr = q.check_stop_precedes(fn, index, pool, cmd_addr)
    return_addr, release_addr, release_index, release_imm = q.check_release_tail(
        fn, index, pool, cmd_addr)
    hook_evidence = q.check_hook_structure(funcs, pool, q.parse_nm(nm_text),
                                           CFG_STRUCTURAL_MODE, reg_offsets)
    stop_index = next(n for n, i in enumerate(fn.insns) if i.addr == stop_addr)
    digest, body = q.normalized_digest(fn, stop_index, release_index)

    result = {
        "ok": True,
        "qualification_mode": CFG_STRUCTURAL_MODE,
        "cfg_case": case,
        "cfg_case_id": CASE_ID[case],
        "cfg_expected_write_count": cfg_count,
        "cfg_expected_value": None if cfg_value is None else "0x%08X" % cfg_value,
        "caller_symbol": fn.name,
        "target_callsite_count": len(hits),
        "target_call_address": fn.insns[index].addr,
        "expected_return_address": return_addr,
        "release_store_address": release_addr,
        "release_immediate_address": release_imm[0],
        "release_immediate_value": release_imm[1],
        "stop_store_address": stop_addr,
        "npu_cmd_address": cmd_addr,
        "callsite_disassembly_sha256": digest,
        "callsite_disassembly": body,
        "test_cpm": test_cpm,
        "printf_relocations": printf_relocs,
        "puts_relocations": puts_relocs,
    }
    result.update(object_evidence)
    result.update(hook_evidence)
    return result


def manifest_document(result, build_id, vendor_source_sha256,
                      vendor_object_sha256, compiler_flags, artifacts):
    """CFG manifest: the qualification manifest plus explicit case identity."""
    doc = q.manifest_document(result, build_id, vendor_source_sha256,
                              vendor_object_sha256, compiler_flags, artifacts)
    doc["characterization_only"] = True
    doc["not_a_performance_baseline"] = True
    doc["cfg_case"] = result["cfg_case"]
    doc["cfg_case_id"] = result["cfg_case_id"]
    doc["cfg_expected_write_count"] = result["cfg_expected_write_count"]
    doc["cfg_expected_value"] = result["cfg_expected_value"]
    return doc


# ---------------------------------------------------------------------------
# Matrix gate: the three built variants compared against each other
# ---------------------------------------------------------------------------

# Everything a manifest carries that MUST be identical across A/B/C. Listed
# positively so a newly added manifest key fails closed as "unexpected
# difference" instead of being silently tolerated.
def _common_keys(docs):
    keys = set()
    for d in docs.values():
        keys |= set(d)
    exempt = (set(IDENTITY_ONLY_KEYS) | set(LAYOUT_SHIFT_KEYS)
              | set(NORMALIZED_KEYS))
    return sorted(k for k in keys if k not in exempt)


def check_layout_shift(docs):
    """Constrain the declared layout shift instead of ignoring it.

    Case A emits no PMCCNTR_CFG write, so the hook call site must sit BELOW
    both write-emitting cases. Every other hook address is a common term and
    is already required to be equal by the caller.
    """
    for key in LAYOUT_SHIFT_KEYS:
        values = {c: d.get(key) for c, d in docs.items()}
        if any(v is None for v in values.values()):
            raise GateError("%s missing from a manifest: %s" % (key, values))
        if not (values["A"] < values["B"] and values["A"] < values["C"]):
            raise GateError(
                "%s: case A performs no CFG write so it must have the lowest "
                "address, but got %s -- the shift did not come from the added "
                "write" % (key, values))
    return {k: {c: d[k] for c, d in docs.items()} for k in LAYOUT_SHIFT_KEYS}


def matrix_check(manifest_paths):
    docs = {}
    for case, path in manifest_paths.items():
        with open(path) as handle:
            docs[case] = json.load(handle)
        got = docs[case].get("cfg_case")
        if got != case:
            raise GateError("%s self-reports cfg_case %r, expected %r"
                            % (path, got, case))

    problems = []
    for key in _common_keys(docs):
        values = {case: json.dumps(doc.get(key), sort_keys=True)
                  for case, doc in docs.items()}
        if len(set(values.values())) != 1:
            problems.append("%s differs across cases: %s"
                            % (key, {c: v[:80] for c, v in values.items()}))
    if problems:
        raise GateError("unexpected non-identity differences between the CFG "
                        "variants:\n  " + "\n  ".join(problems))

    # The declared identity metadata MUST actually differ, otherwise two cases
    # are indistinguishable in the field and a record cannot be attributed.
    ids = {c: docs[c]["build_id"] for c in docs}
    if len(set(ids.values())) != len(ids):
        raise GateError("build ids are not unique across cases: %s" % ids)
    case_ids = {c: docs[c]["cfg_case_id"] for c in docs}
    if len(set(case_ids.values())) != len(case_ids):
        raise GateError("cfg_case_id values are not unique: %s" % case_ids)

    # The A/C pair: both final values zero, write counts 0 and 1.
    a, c = docs["A"], docs["C"]
    if a["cfg_expected_write_count"] != 0:
        raise GateError("case A must have 0 CFG writes, manifest says %d"
                        % a["cfg_expected_write_count"])
    if c["cfg_expected_write_count"] != 1:
        raise GateError("case C must have exactly 1 CFG write, manifest says %d"
                        % c["cfg_expected_write_count"])
    if a["cfg_expected_value"] is not None:
        raise GateError("case A must write no value, manifest says %r"
                        % a["cfg_expected_value"])
    if int(c["cfg_expected_value"], 16) != 0:
        raise GateError("case C must write an explicit ZERO, manifest says %s"
                        % c["cfg_expected_value"])
    b = docs["B"]
    if b["cfg_expected_write_count"] != 1 or int(b["cfg_expected_value"], 16) == 0:
        raise GateError("case B must write exactly one non-zero generated "
                        "configuration, manifest says count=%s value=%s"
                        % (b["cfg_expected_write_count"], b["cfg_expected_value"]))
    check_compiler_flags_identity(docs)
    check_layout_shift(docs)
    return docs


def _report_matrix(docs):
    any_doc = docs["A"]
    print("  PASS vendor object identical across A/B/C: %s"
          % any_doc["vendor_object_sha256"])
    print("  PASS vendor source identical across A/B/C: %s"
          % any_doc["vendor_source_sha256"])
    print("  PASS normalized callsite digest identical: %s"
          % any_doc["callsite_disassembly_sha256"])
    print("  PASS hook order digest identical: %s"
          % any_doc.get("hook_order_sha256"))
    print("  PASS caller/return/release ordering identical: STOP 0x%08X -> "
          "call 0x%08X -> return 0x%08X -> release 0x%08X (immediate #%d)"
          % (any_doc["stop_store_address"], any_doc["target_call_address"],
             any_doc["expected_return_address"], any_doc["release_store_address"],
             any_doc["release_immediate_value"]))
    print("  PASS TEST_CPM=%d identical across A/B/C" % any_doc["test_cpm"])
    print("  PASS only declared identity metadata differs: %s"
          % ", ".join(IDENTITY_ONLY_KEYS))
    print("  PASS compiler flags identical across A/B/C after collapsing ONLY "
          "the build id and the case macro (order significant; %d tokens "
          "compared)" % len(check_compiler_flags_identity(docs)))
    shifts = check_layout_shift(docs)
    for key, values in shifts.items():
        print("  DECLARED layout shift, separate from the causal CFG action: "
              "%s A=0x%08X B=0x%08X C=0x%08X (hook body identical; the write "
              "in B/C moves the call site, and A is correctly lowest)"
              % (key, values["A"], values["B"], values["C"]))
    for case in CASES:
        d = docs[case]
        print("  PASS case %s: build %s, cfg writes=%d, value=%s"
              % (case, d["build_id"], d["cfg_expected_write_count"],
                 d["cfg_expected_value"]))
    print("  PASS A/C pair: both final CFG value zero, write counts 0 vs 1 "
          "(a value comparison alone cannot separate these)")
    print("PASS CFG A/B/C matrix identity gate "
          "(CHARACTERIZATION ONLY -- not latency, not T_npu, not a "
          "performance baseline, not Production GO, not Gate 7, not MLEK)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", action="store_true",
                    help="compare three already-built variants")
    ap.add_argument("--manifest-a")
    ap.add_argument("--manifest-b")
    ap.add_argument("--manifest-c")
    ap.add_argument("--case", choices=CASES)
    ap.add_argument("--build-id")
    ap.add_argument("--vendor-source")
    ap.add_argument("--interface-header")
    ap.add_argument("--vendor-object")
    ap.add_argument("--regs-header")
    ap.add_argument("--preprocessed")
    ap.add_argument("--elf")
    ap.add_argument("--map")
    ap.add_argument("--app-bin")
    ap.add_argument("--vectors-bin")
    ap.add_argument("--ddr-bin")
    ap.add_argument("--objdump")
    ap.add_argument("--nm")
    ap.add_argument("--readelf")
    ap.add_argument("--cflags")
    ap.add_argument("--manifest-out")
    a = ap.parse_args()

    if a.matrix:
        missing = [n for n in ("manifest_a", "manifest_b", "manifest_c")
                   if not getattr(a, n)]
        if missing:
            raise SystemExit("--matrix requires --manifest-a/-b/-c")
        try:
            docs = matrix_check({"A": a.manifest_a, "B": a.manifest_b,
                                 "C": a.manifest_c})
        except GateError as exc:
            print("FAIL %s" % exc)
            sys.exit(1)
        _report_matrix(docs)
        return

    required = ("case", "build_id", "vendor_source", "interface_header",
                "vendor_object", "regs_header", "preprocessed", "elf", "map",
                "app_bin", "vectors_bin", "ddr_bin", "objdump", "nm",
                "readelf", "cflags", "manifest_out")
    missing = [n for n in required if getattr(a, n) is None]
    if missing:
        raise SystemExit("missing required arguments: %s" % ", ".join(missing))

    vendor_source = open(a.vendor_source, newline=None).read()
    interface_header = open(a.interface_header, newline=None).read()
    regs_header = open(a.regs_header, newline=None).read()
    preprocessed = open(a.preprocessed, newline=None).read()

    header = q._run([a.readelf, "-h", a.elf])
    if "Executable" not in header and "EXEC" not in header:
        raise SystemExit("FAIL %s is not an executable ELF" % a.elf)

    try:
        result = evaluate_cfg(
            case=a.case,
            disassembly_text=q._run([a.objdump, "-d", a.elf]),
            nm_text=q._run([a.nm, a.elf]),
            strings_text=q._run([a.objdump, "-s", a.elf]),
            relocation_text=q._run([a.objdump, "-r", a.vendor_object]),
            object_disassembly_text=q._run([
                a.objdump, "-drz", "--section=" + q.OBJECT_TEXT_SECTION,
                a.vendor_object]),
            object_sections_text=q._run([a.objdump, "-s", a.vendor_object]),
            vendor_source_text=vendor_source,
            interface_header_text=interface_header,
            compiler_flags=a.cflags,
            preprocessed_text=preprocessed,
            cfg_header_text=regs_header,
        )
    except GateError as exc:
        print("FAIL %s" % exc)
        sys.exit(1)

    manifest = manifest_document(
        result,
        build_id=int(a.build_id, 16),
        vendor_source_sha256=q._sha256(a.vendor_source),
        vendor_object_sha256=q._sha256(a.vendor_object),
        compiler_flags=a.cflags,
        artifacts={
            "APP.BIN": q._sha256(a.app_bin),
            "VECTORS.BIN": q._sha256(a.vectors_bin),
            "DDR.BIN": q._sha256(a.ddr_bin),
            "elf": q._sha256(a.elf),
            "map": q._sha256(a.map),
        },
    )
    with open(a.manifest_out, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print("  PASS TEST_CPM=%d, exactly one vendor terminal release"
          % result["test_cpm"])
    print("  PASS unique target callsite in <%s> -> <%s>"
          % (result["caller_symbol"], q.WRAP_PRINTF_SYMBOL))
    print("  PASS STOP 0x%08x -> call 0x%08x -> return 0x%08x -> immediate #%d "
          "0x%08x -> release 0x%08x, nothing in between"
          % (result["stop_store_address"], result["target_call_address"],
             result["expected_return_address"], result["release_immediate_value"],
             result["release_immediate_address"], result["release_store_address"]))
    print("  PASS hook order: wrapper 0x%08x -> cycle read 0x%08x -> disable "
          "0x%08x -> dsb 0x%08x -> PMCR readback 0x%08x -> post-disable capture "
          "0x%08x -> latch 0x%08x (last)"
          % (result["hook_wrapper_call_address"],
             result["hook_internal_pre_release_cycle_read_address"],
             result["hook_pmu_disable_address"], result["hook_dsb_address"],
             result["hook_pmcr_readback_address"],
             result["hook_internal_post_disable_capture_address"],
             result["hook_snapshot_valid_latch_address"]))
    if result["cfg_expected_write_count"] == 0:
        print("  PASS case A: no PMCCNTR_CFG write of any kind "
              "(same helper the Q0/Q1 gate uses)")
    else:
        print("  PASS case %s: exactly %d PMCCNTR_CFG write of the GENERATED "
              "value %s (composed from the register header, not a literal)"
              % (result["cfg_case"], result["cfg_expected_write_count"],
                 result["cfg_expected_value"]))
    print("  PASS -fno-builtin-printf set, no LTO")
    print("  PASS callsite digest %s" % result["callsite_disassembly_sha256"])
    print("  INFO whole-object relocation totals, NOT pinned: printf=%d, puts=%d"
          % (result["printf_relocations"], result["puts_relocations"]))
    print("PASS CFG case %s characterization manifest -> %s "
          "(CHARACTERIZATION ONLY)" % (a.case, a.manifest_out))


if __name__ == "__main__":
    main()
