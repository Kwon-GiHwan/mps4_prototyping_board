#!/usr/bin/env python3
"""
measure_denylist_check.py -- Contract 3 build gate for RUNNER_V1_MEASURE.

Fails the build (non-zero exit) if any denylisted logging/transmit symbol is
reachable from the MEASURED PATH of the linked ELF.

Why over the linked ELF and not the sources:
  --wrap is a LINK-time redirection. Whether printf ends up as __wrap_printf
  or as newlib's printf is only decided at link. Source-level grepping cannot
  answer the question; a call graph over the final ELF can.

Method:
  1. `objdump -d` the ELF, split into functions on `<addr> <name>:` headers.
  2. Collect DIRECT branch/call edges -- any operand annotated `<target>`.
     This covers bl, blx <label>, and tail calls via b/b.w/bne.w etc.
  3. BFS from the measured-path roots.
  4. Fail if any reached symbol is on the denylist.

DOCUMENTED LIMITATION -- read before trusting a PASS:
  Indirect calls through function pointers CANNOT be resolved statically.
  In this project that specifically includes `Driver_USART0.Send(...)`, since
  Driver_USART0 is a struct of function pointers. A pure symbol/relocation
  check will never catch that route. Every reachable indirect call site is
  therefore REPORTED as a residual risk, and the real proof that no such call
  fires is the runtime counter uart_bytes_during_measurement == 0.
  A PASS from this script means "no direct call reaches a denylisted symbol",
  not "no UART traffic is possible".

FOUR GATES, all reported, all enforced:
  1. DENYLIST reachability from the measured path (advisory in the wrapped
     profile only -- see the banner it prints).
  2. .sec_noinit allowlist: the blanket poison is only safe against a known
     layout and a known contributing object set.
  3. INJECTION gate: no runner_inject_* marker in a normal artifact, and
     apU85Conv_TEST reachable from the measured path.
  4. TEST-ONLY HOOK reachability: no test-only command handler present in, or
     reachable from the dispatcher of, a normal artifact.
Gates 2, 3 and 4 are enforced in BOTH profiles; --advisory excuses gate 1 only.
"""

import argparse
import re
import subprocess
import sys
from collections import deque

# Symbols that must never be reachable from the measured path.
DENYLIST = {
    "printf", "vprintf", "fprintf", "vfprintf", "sprintf", "snprintf",
    "vsprintf", "vsnprintf",
    "puts", "putchar", "fwrite", "fputc", "fputs",
    "_write", "_write_r", "write",
    "serial_print", "serial_write", "serial_putc",
    # newlib-nano integer-only stdio variants; printf often aliases to these.
    "iprintf", "viprintf", "fiprintf", "vfiprintf", "siprintf", "sniprintf",
    # the un-wrapped originals: reaching these means something bypassed --wrap
    "__real_printf", "__real_vprintf", "__real_puts", "__real_putchar",
    "__real__write", "__real__write_r", "__real_fputc", "__real_fwrite",
    "__real_fprintf", "__real_vfprintf", "__real_serial_print",
}

# Any CMSIS USART driver entry point that transmits.
DENY_PATTERNS = [
    re.compile(r"^ARM_USART\w*_Send$"),
    re.compile(r"^Driver_USART\d*_Send$"),
    re.compile(r"^USART\d*_Send$"),
]

# Indirect call sites that are EXPECTED and understood. Narrow by design:
# each entry is a function whose indirect call is a known, reviewed dispatch,
# not a potential transmit. Anything NOT listed here makes the result
# INCOMPLETE, because an unexpected function-pointer call could be a
# Driver_USART0.Send in disguise.
#
#   runner_u85_irq_wrapper -- calls original_u85_handler(), the NPU vector it
#   captured before the window. Chaining REQUIRES an indirect call; the target
#   is the stock u85_irq_handler and is verified at runtime by
#   npu_vector_hijack_survived.
KNOWN_INDIRECT_SITES = {
    "runner_u85_irq_wrapper",
}

# Roots of the measured path: everything executed between
# measurement_active = 1 and measurement_active = 0.
MEASURED_ROOTS = [
    "run_fixed_inference",
    "runner_u85_irq_wrapper",
]

# ---------------------------------------------------------------------------
# .sec_noinit allowlist gate.
#
# WHY THIS EXISTS: handle_run() blanket-poisons the NPU output region before
# every run. That is only safe while .sec_noinit holds NOTHING but u85 output
# and scratch data. If any persistent runner/driver state ever lands there, a
# blanket poison would destroy it, so the build must FAIL rather than let the
# poison run against an unknown layout.
#
# Both halves matter:
#   - the contributing object set must be exactly the six u85 test objects;
#   - the base/size must not have moved.
# A layout shift with an unchanged object set is still a reason to stop and
# re-derive the poison bounds by hand.
# ---------------------------------------------------------------------------
SEC_NOINIT_EXPECTED_BASE = 0x90020000
SEC_NOINIT_EXPECTED_SIZE = 0xF90

SEC_NOINIT_ALLOWED_OBJECTS = {
    "u85_AXIBus.o",
    "u85_Convolution.o",
    "u85_MaxPooling.o",
    "u85_PowerIndicative.o",
    "u85_PowerIndicativeMax.o",
    "u85_RegConfig.o",
}

# Symbols that must NEVER exist in a normal artifact. Each is defined only
# under a test-only injection macro, so its presence proves the macro leaked.
INJECT_MARKER_PREFIX = "runner_inject_"

# The NPU entry point. Its absence from the measured path means the run does
# not actually run anything -- which is exactly what INJECT_SKIP_NPU_EXECUTION
# does, and must never be true of a shipped build.
NPU_ENTRY_SYMBOL = "apU85Conv_TEST"

# ---------------------------------------------------------------------------
# TEST-ONLY COMMAND HOOK reachability gate.
#
# WHY THIS EXISTS: CMD_TEST_SKIP_NEXT_NPU (0x7E) lets a HOST make the next run
# skip the NPU. That is exactly the capability an attacker -- or a careless
# operator -- would use to make a failed run look like a successful one, and it
# is the single most dangerous thing in this firmware to ship by accident. It
# is compiled only under -DRUNNER_TEST_ONLY_HOOKS; this gate is what makes that
# a guarantee rather than a convention, exactly as the INJECT_SKIP_NPU marker
# gate already does for the compile-time skip.
#
# TWO conditions, both required, because either alone is defeatable:
#   - the handler symbol must not EXIST in the ELF (nm), and
#   - it must not be REACHABLE from the command dispatcher (call graph).
# Symbol-absence alone would miss a handler that got renamed or inlined into
# dispatch(); reachability alone would miss a handler that is present but only
# reached through a path this checker cannot see. Requiring both closes the
# gap that a single check leaves.
#
# FAILS CLOSED: if the dispatch root is not in the ELF, the check cannot prove
# anything and reports FAIL rather than a vacuous PASS. dispatch() is marked
# __attribute__((noinline)) in the firmware precisely so this root is always
# findable; see the comment on it there.
TEST_HOOK_SYMBOLS = {
    "handle_test_skip_next_npu",
}

# Root for the test-hook reachability question. This is a DIFFERENT root set
# from MEASURED_ROOTS on purpose: a command handler is reached from the frame
# dispatcher, never from inside the measurement window.
COMMAND_DISPATCH_ROOTS = ["dispatch"]

MAP_SECTION_HEADER = re.compile(
    r"^\.sec_noinit\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)")
MAP_OBJECT = re.compile(r"(\S+\.o)\)?\s*$")

FUNC_HEADER = re.compile(r"^([0-9a-fA-F]+)\s+<([^>]+)>:\s*$")
# Operand annotation produced by objdump for a resolved direct branch target.
CALL_TARGET = re.compile(r"<([^>+]+)(?:\+0x[0-9a-fA-F]+)?>")
# Indirect call through a register.
INDIRECT = re.compile(r"\b(blx?)\s+(r\d+|ip|lr|sl|fp)\b")


def is_denied(name):
    if name in DENYLIST:
        return True
    return any(p.match(name) for p in DENY_PATTERNS)


def build_graph(objdump, elf):
    out = subprocess.run(
        [objdump, "-d", "--no-show-raw-insn", elf],
        capture_output=True, text=True, check=True,
    ).stdout

    graph = {}
    indirect_sites = {}
    current = None

    for line in out.splitlines():
        header = FUNC_HEADER.match(line)
        if header:
            current = header.group(2)
            graph.setdefault(current, set())
            indirect_sites.setdefault(current, 0)
            continue
        if current is None:
            continue
        # Only instruction lines have a tab after the address.
        if "\t" not in line:
            continue
        mnemonic_and_ops = line.split("\t", 1)[1]
        if INDIRECT.search(mnemonic_and_ops):
            indirect_sites[current] += 1
        for target in CALL_TARGET.findall(mnemonic_and_ops):
            graph[current].add(target)

    return graph, indirect_sites


def reachable(graph, roots):
    seen = set()
    queue = deque()
    missing_roots = []

    for r in roots:
        if r in graph:
            seen.add(r)
            queue.append(r)
        else:
            missing_roots.append(r)

    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)

    return seen, order, missing_roots


def shortest_path(graph, roots, target):
    prev = {}
    seen = set()
    queue = deque()
    for r in roots:
        if r in graph:
            seen.add(r)
            queue.append(r)
    while queue:
        node = queue.popleft()
        if node == target:
            path = [node]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return list(reversed(path))
        for nxt in sorted(graph.get(node, ())):
            if nxt not in seen:
                seen.add(nxt)
                prev[nxt] = node
                queue.append(nxt)
    return [target]


def check_sec_noinit(map_path):
    """Return (ok, lines). Fails closed: an unparseable map is a FAIL."""
    log = []
    try:
        with open(map_path, "r", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return False, ["FAIL: cannot read map file %s: %s" % (map_path, exc)]

    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if MAP_SECTION_HEADER.match(line):
            start = i
            break
    if start is None:
        return False, [
            "FAIL: no .sec_noinit output section found in %s" % map_path,
            "      The poison bounds cannot be validated, so the build stops.",
        ]

    header = MAP_SECTION_HEADER.match(lines[start])
    base = int(header.group(1), 16)
    size = int(header.group(2), 16)

    # Collect contributing objects until the next output section. Input-section
    # lines are indented; a new output section starts at column 0 with '.'.
    objects = set()
    for line in lines[start + 1:]:
        if line and not line[0].isspace():
            if line.startswith("."):
                break
            if not line.startswith(" "):
                break
        m = MAP_OBJECT.search(line)
        if m:
            objects.add(m.group(1).split("/")[-1])

    ok = True
    log.append("base/size : 0x%08x / 0x%x" % (base, size))
    if base != SEC_NOINIT_EXPECTED_BASE or size != SEC_NOINIT_EXPECTED_SIZE:
        ok = False
        log.append("FAIL: .sec_noinit moved. expected 0x%08x / 0x%x"
                   % (SEC_NOINIT_EXPECTED_BASE, SEC_NOINIT_EXPECTED_SIZE))
        log.append("      The poison bounds were derived against the expected")
        log.append("      layout. Re-derive them before allowing a poison.")

    log.append("objects   : %s" % (", ".join(sorted(objects)) or "(none)"))
    unexpected = sorted(objects - SEC_NOINIT_ALLOWED_OBJECTS)
    if unexpected:
        ok = False
        log.append("FAIL: object(s) outside the .sec_noinit allowlist: %s"
                   % ", ".join(unexpected))
        log.append("      handle_run() blanket-poisons this region before every")
        log.append("      run. Anything here that is NOT u85 output/scratch")
        log.append("      would be destroyed. Narrow the poison range or move")
        log.append("      the data out of .sec_noinit -- do not widen this list")
        log.append("      without proving the object holds no persistent state.")
    missing = sorted(SEC_NOINIT_ALLOWED_OBJECTS - objects)
    if missing:
        log.append("NOTE: allowlisted object(s) contributed nothing this build:"
                   " %s" % ", ".join(missing))

    return ok, log


def nm_symbols(nm, elf):
    """Every symbol NAME defined or referenced in the ELF, as a set."""
    out = subprocess.run([nm, elf], capture_output=True, text=True,
                         check=True).stdout
    names = set()
    for line in out.splitlines():
        fields = line.split()
        if fields:
            names.add(fields[-1])
    return names


def check_injections(symbols, reached, expect_skip, expect_hooks):
    """Injection markers must be absent, and the NPU call edge must exist."""
    log = []
    ok = True

    markers = sorted(s for s in symbols if s.startswith(INJECT_MARKER_PREFIX))

    npu_reached = NPU_ENTRY_SYMBOL in reached

    if expect_hooks:
        # Test-hooks mode. The marker IS expected -- but unlike the
        # compile-time skip, the NPU must STILL be statically reachable,
        # because CMD_TEST_SKIP_NEXT_NPU skips at RUNTIME for ONE run. If
        # apU85Conv_TEST vanished from the measured path here, the hook would
        # be behaving like INJECT_SKIP_NPU and would prove nothing about a
        # success-then-failure sequence.
        log.append("expect-test-hooks: asserting the hook build is ACTIVE")
        if not markers:
            ok = False
            log.append("FAIL: no %s* marker present -- the test-hook build did"
                       % INJECT_MARKER_PREFIX)
            log.append("      NOT take effect, so this artifact proves nothing.")
        else:
            log.append("  marker(s) present : %s" % ", ".join(markers))
        if not npu_reached:
            ok = False
            log.append("FAIL: %s is NOT reachable from the measured path."
                       % NPU_ENTRY_SYMBOL)
            log.append("      A test-hooks build must still be able to run the")
            log.append("      NPU -- the skip is a RUNTIME one-shot, not a")
            log.append("      compile-time removal. This build cannot produce")
            log.append("      the success-then-failure pair it exists for.")
        else:
            log.append("  %s still reachable : runtime one-shot, not a"
                       % NPU_ENTRY_SYMBOL)
            log.append("      compile-time removal")
        return ok, log

    if expect_skip:
        # Negative-control mode: assert the injection really did take effect,
        # so a "control" that silently did nothing cannot be mistaken for proof.
        log.append("expect-injected-skip: asserting the control is ACTIVE")
        if not markers:
            ok = False
            log.append("FAIL: no %s* marker present -- the injection did NOT"
                       % INJECT_MARKER_PREFIX)
            log.append("      take effect, so this artifact proves nothing.")
        else:
            log.append("  marker(s) present : %s" % ", ".join(markers))
        if npu_reached:
            ok = False
            log.append("FAIL: %s is STILL reachable from the measured path;"
                       % NPU_ENTRY_SYMBOL)
            log.append("      the NPU was not actually skipped.")
        else:
            log.append("  %s unreachable : NPU genuinely skipped"
                       % NPU_ENTRY_SYMBOL)
        return ok, log

    if markers:
        ok = False
        log.append("FAIL: test-only injection marker(s) present in a normal")
        log.append("      artifact: %s" % ", ".join(markers))
        log.append("      An injection macro leaked into a shipped build.")
    else:
        log.append("no %s* markers  : PASS" % INJECT_MARKER_PREFIX)

    if not npu_reached:
        ok = False
        log.append("FAIL: %s is NOT reachable from the measured path."
                   % NPU_ENTRY_SYMBOL)
        log.append("      This build does not run the NPU at all. That is the")
        log.append("      INJECT_SKIP_NPU_EXECUTION signature and must never")
        log.append("      appear in a normal artifact.")
    else:
        log.append("%s reachable : PASS" % NPU_ENTRY_SYMBOL)

    return ok, log


def check_test_hooks(symbols, graph, expect_hooks):
    """Test-only command handlers must be absent AND unreachable from dispatch.

    Returns (ok, lines). Fails CLOSED: a missing dispatch root means the
    reachability question cannot be answered, which is a FAIL, not a PASS.
    """
    log = []
    ok = True

    present = sorted(TEST_HOOK_SYMBOLS & symbols)

    dispatch_seen, _, missing_roots = reachable(graph, COMMAND_DISPATCH_ROOTS)
    if missing_roots:
        log.append("FAIL: dispatch root(s) not found in the ELF: %s"
                   % ", ".join(missing_roots))
        log.append("      Reachability of a test-only command handler cannot be")
        log.append("      decided without the dispatcher. Mark it noinline or")
        log.append("      update COMMAND_DISPATCH_ROOTS -- do NOT relax this to")
        log.append("      a pass, which would verify nothing.")
        return False, log

    log.append("dispatch root(s)  : %s" % ", ".join(COMMAND_DISPATCH_ROOTS))
    log.append("reachable from it : %d function(s)" % len(dispatch_seen))

    reachable_hooks = sorted(TEST_HOOK_SYMBOLS & dispatch_seen)

    if expect_hooks:
        # Negative control for THIS gate. Asserting the hook is genuinely
        # present AND genuinely reachable is what stops a silently inert gate
        # from being mistaken for a passing one -- the exact failure mode that
        # bit the __attribute__((used, retain)) marker previously.
        log.append("expect-test-hooks: asserting the gate has something to see")
        if not present:
            ok = False
            log.append("FAIL: no test-only hook symbol in the ELF: expected one"
                       " of %s" % ", ".join(sorted(TEST_HOOK_SYMBOLS)))
            log.append("      The hook did not compile in, so a PASS from the")
            log.append("      normal-mode gate would prove nothing.")
        else:
            log.append("  present   : %s" % ", ".join(present))
        if not reachable_hooks:
            ok = False
            if present:
                log.append("FAIL: test-only hook(s) present but NOT reachable"
                           " from %s."
                           % ", ".join(COMMAND_DISPATCH_ROOTS))
                log.append("      The gate's reachability arm is therefore")
                log.append("      untested and may be inert.")
            else:
                log.append("FAIL: no test-only hook is reachable from %s"
                           % ", ".join(COMMAND_DISPATCH_ROOTS))
                log.append("      (nothing was present to reach). The")
                log.append("      reachability arm proved nothing here.")
        else:
            log.append("  reachable : %s" % ", ".join(reachable_hooks))
            for h in reachable_hooks:
                path = shortest_path(graph, COMMAND_DISPATCH_ROOTS, h)
                log.append("    via: %s" % " -> ".join(path))
        return ok, log

    if present:
        ok = False
        log.append("FAIL: test-only command handler(s) present in a normal")
        log.append("      artifact: %s" % ", ".join(present))
        log.append("      RUNNER_TEST_ONLY_HOOKS leaked into a shipped build.")
    else:
        log.append("no test-only handler symbols : PASS")

    if reachable_hooks:
        ok = False
        log.append("FAIL: test-only command handler(s) REACHABLE from the")
        log.append("      command dispatcher: %s" % ", ".join(reachable_hooks))
        for h in reachable_hooks:
            path = shortest_path(graph, COMMAND_DISPATCH_ROOTS, h)
            log.append("        via: %s" % " -> ".join(path))
        log.append("      A host could then make the next run skip the NPU and")
        log.append("      fail, which is precisely the capability that must")
        log.append("      never exist in a normal MEASURE artifact.")
    else:
        log.append("no test-only handler reachable from dispatch : PASS")

    return ok, log


def denylist_verdict(args, graph, indirect_sites, seen, missing_roots):
    print("=" * 72)
    print("DENYLIST CHECK  profile=%s  elf=%s" % (args.profile, args.elf))
    print("=" * 72)

    if missing_roots:
        # A root that is not in the ELF means the measured path was inlined,
        # renamed or garbage-collected. Refusing to pass is the safe answer:
        # a check that silently verifies nothing is worse than no check.
        print("FAIL: measured-path root(s) not found in the ELF: %s"
              % ", ".join(missing_roots))
        print("      The check cannot prove anything about a path it cannot")
        print("      locate. Mark the root noinline or update MEASURED_ROOTS.")
        return 2

    print("measured-path roots : %s" % ", ".join(MEASURED_ROOTS))
    print("functions reachable : %d" % len(seen))

    violations = sorted(s for s in seen if is_denied(s))

    indirect_total = sum(indirect_sites.get(f, 0) for f in seen)
    indirect_funcs = sorted(f for f in seen if indirect_sites.get(f, 0))

    print("indirect call sites : %d in %d reachable function(s)"
          % (indirect_total, len(indirect_funcs)))
    if indirect_funcs:
        print("  UNRESOLVABLE STATICALLY (residual risk, incl. any")
        print("  Driver_USART0.Send through the driver struct):")
        for f in indirect_funcs[:20]:
            print("    %-40s %d site(s)" % (f, indirect_sites[f]))
        if len(indirect_funcs) > 20:
            print("    ... and %d more" % (len(indirect_funcs) - 20))

    # An indirect call site inside the measured path means the static answer is
    # INCOMPLETE, not PASS: a transmit through Driver_USART0's function-pointer
    # struct references no denylisted symbol and is invisible here.
    unexpected_indirect = sorted(f for f in indirect_funcs
                                 if f not in KNOWN_INDIRECT_SITES)
    incomplete = bool(unexpected_indirect)

    if violations:
        print("")
        print("FAIL: %d denylisted symbol(s) reachable from the measured path:"
              % len(violations))
        for v in violations:
            path = shortest_path(graph, MEASURED_ROOTS, v)
            print("  %s" % v)
            print("    via: %s" % " -> ".join(path))
        print("")
        print("The only permitted transmit path is the explicit result-frame")
        print("send invoked AFTER the measurement window closes.")
        if args.advisory:
            print("")
            print("ADVISORY MODE (wrapped profile): exiting 0.")
            print("  The wrapped profile CANNOT pass a static reachability")
            print("  check by construction: __wrap_printf deliberately")
            print("  forwards to __real_vprintf so that logging still works")
            print("  OUTSIDE the window. The call edge therefore exists in the")
            print("  binary and is suppressed only at RUNTIME by the")
            print("  measurement_active guard.")
            print("  Static proof of no-logging is the CLEAN profile's job,")
            print("  and it is enforced there. For this profile the evidence")
            print("  is runtime: uart_bytes_during_measurement == 0 and")
            print("  suppressed_printf_calls > 0.")
            return 0
        return 1

    print("")
    if incomplete:
        print("INCOMPLETE: no denylisted symbol is reachable by a DIRECT call,")
        print("      but these measured-path functions make UNEXPECTED")
        print("      indirect calls: %s" % ", ".join(unexpected_indirect))
        print("      A transmit through Driver_USART0's function-pointer struct")
        print("      references no denylisted symbol and is INVISIBLE to this")
        print("      check. Static analysis cannot settle it either way.")
        print("      The runtime UART gate decides: the counter at the single")
        print("      function that writes the CMSDK UART DATA register must")
        print("      read uart_bytes_during_measurement == 0, and the host must")
        print("      observe 0 bytes in the measurement window.")
        print("      Exit 0: INCOMPLETE is not a build failure, but it is NOT")
        print("      a clean bill of health either.")
        return 0
    print("PASS: no denylisted symbol is reachable from the measured path.")
    if indirect_funcs:
        print("      The only indirect call sites are known and reviewed: %s"
              % ", ".join(sorted(indirect_funcs)))
    print("      Runtime UART gate must still confirm")
    print("      uart_bytes_during_measurement == 0.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--nm", required=True)
    ap.add_argument("--profile", default="?")
    ap.add_argument("--advisory", action="store_true",
                    help="report violations but exit 0 (wrapped profile only)")
    ap.add_argument("--expect-injected-skip", action="store_true",
                    help="negative-control mode: REQUIRE the "
                         "INJECT_SKIP_NPU_EXECUTION control to be active")
    ap.add_argument("--expect-test-hooks", action="store_true",
                    help="negative-control mode: REQUIRE the "
                         "RUNNER_TEST_ONLY_HOOKS build to be active, i.e. the "
                         "test-only command handler present AND reachable from "
                         "dispatch. Without this the same build FAILS.")
    args = ap.parse_args()

    graph, indirect_sites = build_graph(args.objdump, args.elf)
    seen, order, missing_roots = reachable(graph, MEASURED_ROOTS)
    symbols = nm_symbols(args.nm, args.elf)

    deny_rc = denylist_verdict(args, graph, indirect_sites, seen, missing_roots)

    print("")
    print("=" * 72)
    print("SEC_NOINIT ALLOWLIST GATE  map=%s" % args.map)
    print("=" * 72)
    noinit_ok, noinit_log = check_sec_noinit(args.map)
    for line in noinit_log:
        print(line)
    print("VERDICT: %s" % ("PASS" if noinit_ok else "FAIL"))

    print("")
    print("=" * 72)
    print("INJECTION GATE")
    print("=" * 72)
    inj_ok, inj_log = check_injections(symbols, seen,
                                       args.expect_injected_skip,
                                       args.expect_test_hooks)
    for line in inj_log:
        print(line)
    print("VERDICT: %s" % ("PASS" if inj_ok else "FAIL"))

    print("")
    print("=" * 72)
    print("TEST-ONLY HOOK REACHABILITY GATE")
    print("=" * 72)
    hooks_ok, hooks_log = check_test_hooks(symbols, graph,
                                           args.expect_test_hooks)
    for line in hooks_log:
        print(line)
    print("VERDICT: %s" % ("PASS" if hooks_ok else "FAIL"))

    # These three gates are enforced in BOTH profiles. --advisory excuses only
    # the denylist reachability result, which the wrapped profile cannot pass by
    # construction; it does not excuse a poison-unsafe layout, a leaked
    # injection, or a reachable test-only command handler.
    if not noinit_ok or not inj_ok or not hooks_ok:
        return 1
    return deny_rc


if __name__ == "__main__":
    sys.exit(main())
