"""Successor completion-visibility checker: image contracts."""

from __future__ import annotations

import re

from .constants import (
    APPENDIX_FIELDS,
    APPENDIX_WORDS,
    BODY_WORDS,
    BOUND_ON_LINKED_IMAGE,
    BUILD_ID,
    CONVERGE_SYMBOL,
    ENTRY_SYMBOL,
    ITERATION_BOUND,
    MAILBOX_PUBLISH_SYMBOL,
    MAILBOX_SYMBOL,
    MAILBOX_VALID,
    MAILBOX_VALID_WORD,
    MAILBOX_WRITER_SYMBOLS,
    NPU_IRQ_NUMBER,
    NVIC_ISER_BASE,
    NVIC_ISER_WORDS,
    PAYLOAD_BYTES,
    PRE_PROGRAM_MAILBOX_WORD,
    PRIMARY_SYMBOL,
    QUEUE_PROGRAMMING_ROLES,
    RECORD_TYPEDEF,
    RETIRED_CLAIMS,
    RULE_DWARF_MEMBER_READABLE,
    RULE_DWARF_NM_AGREE,
    RULE_DWARF_RECORD_PRESENT,
    RULE_DWARF_SIZE_PRESENT,
    RULE_MAILBOX_PUBLISHED_ONCE,
    RULE_MAILBOX_PUBLISHER_IDENTITY,
    RULE_MAILBOX_PUBLISH_ADDRESS,
    RULE_MAILBOX_PUBLISH_FENCED,
    RULE_NO_TRANSITION_BEFORE_PROGRAMMING,
    RULE_NPU_IRQ_NEVER_ENABLED,
    RULE_NPU_IRQ_UNRESOLVED_WRITE,
    RULE_PRE_PROGRAM_DOMINANCE,
    RULE_PRIMARY_FAULT_PRIORITY,
    RULE_PRIMARY_IRQ_NOT_AN_EXIT,
    RULE_PRIMARY_NO_PER_ITERATION_EFFECT,
    RULE_PRIMARY_NO_QSIZE,
    RULE_PRIMARY_READ_ORDER,
    RULE_READ_ORDER_EQUIVALENCE,
    RULE_RECORD_APPENDIX_CONTIGUOUS,
    RULE_RECORD_APPENDIX_ENDS_RECORD,
    RULE_RECORD_APPENDIX_ORDER,
    RULE_RECORD_SIZE,
    RULE_RUNNER_MAILBOX_GATED,
    RULE_RUNNER_MAILBOX_ONE_CHECK,
    RULE_RUNNER_MAILBOX_READONLY,
    RULE_RUNNER_TUPLE_COMPLETE,
    RULE_SERIALIZATION_COUNTABLE,
    RULE_SERIALIZATION_LENGTH,
    RULE_SERIALIZATION_NAMED_CALLEES,
    RULE_STORE_FORM_UNREADABLE,
    RULE_TAIL_BOUND,
    RULE_TAIL_FOUR_CONDITIONS,
    RULE_TAIL_NO_PER_ITERATION_EFFECT,
    RULE_TAIL_READ_ORDER,
    RULE_TAIL_SHARED,
    RUNNER_DISPATCH_SYMBOL,
    SCHEMA_VERSION,
    SERIALIZER_SYMBOL,
    STATUS_CMD_END,
    STATUS_FAULT_MASK,
    STATUS_IRQ_RAISED,
    STATUS_RESET,
    STATUS_STATE,
    TOTAL_WORDS,
    VARIANTS,
    WORD_WRITER_SYMBOL,
    _DWARF_ADDR,
    _DWARF_BYTE_SIZE,
    _DWARF_DIE,
    _DWARF_MEMBER_OFFSET,
    _DWARF_NAME,
    _DWARF_TYPE_REF,
    _ELF_ANNOTATION,
    _ELF_CALL,
    _ELF_CALLEE,
    _ELF_COMPARE_REGISTERS,
    _ELF_MEMORY,
    _ELF_MOVW,
    _ELF_MOV_IMM,
    _ELF_TEST_MASK,
    _GATE_MASKS,
)

from .errors import (
    GateError,
    fail,
    fail_rule,
)

from .c_lexical import (
    _sha256_text,
)

from .elf_analysis import (
    _elf_can_materialise,
    _elf_data_bytes,
    _elf_front_end,
    _elf_is_store,
    _elf_mask_test,
    _elf_store_may_carry,
    _elf_unresolved_store,
    _elf_written_register,
    elf_cfg,
    elf_dominators,
    elf_function,
    elf_in_modelled_region,
    elf_mmio_accesses,
    elf_natural_loop,
    elf_predicated,
    elf_reaches,
    elf_register_values,
)

from .source_contracts import (
    unbound_claims,
)


def elf_symbol_address(nm_text: str, symbol: str) -> int:
    """The one address ``nm`` gives this symbol, or a refusal."""

    hits = [
        int(parts[0], 16)
        for parts in (line.split() for line in nm_text.splitlines())
        if len(parts) == 3 and parts[2] == symbol
    ]
    if len(hits) != 1:
        raise fail("nm gives %s %d addresses: expected exactly one" % (symbol, len(hits)))
    return hits[0]


def _elf_gate_index(code, states, accesses, mailbox_address: int) -> int:
    """The pre-program gate, found by what it does rather than by where it is.

    A STATUS load is the gate when its value is published to the pre-program
    mailbox word and then tested against the three masks the design gates on.
    Taking the first STATUS load instead would have picked the frozen vendor's
    reset spin, which reads STATUS in a loop of its own a few instructions
    later.

    The publication is checked against the address ``nm`` gives the mailbox, not
    against a displacement. A store at offset 8 of some unresolved pointer is
    not evidence that the pre-program word was written, and reading it as such
    let a mutated image keep its gate by losing the mailbox base.
    """

    candidates = []
    for index, role, is_write in accesses:
        if role != "STATUS" or is_write:
            continue
        register = _elf_written_register(code[index].text)
        if register is None:
            continue
        published = False
        masks = set()
        for step in range(index + 1, min(index + 24, len(code))):
            text = code[step].text
            store = _ELF_MEMORY.match(text)
            if store is not None and store.group(1) == "str" and store.group(2) == register:
                base = states[step].get(store.group(3))
                if (
                    base is not None
                    and base + int(store.group(4) or 0)
                    == mailbox_address + 4 * PRE_PROGRAM_MAILBOX_WORD
                ):
                    published = True
            test = _ELF_TEST_MASK.match(text)
            if test is not None and test.group(1) == register:
                masks.add(int(test.group(2)))
            if _elf_written_register(text) == register:
                break  # the loaded value is gone; anything after tests something else
        if published and set(_GATE_MASKS) <= masks:
            candidates.append(index)
    if len(candidates) != 1:
        raise fail(
            "linked image does not carry exactly one pre-program gate: %d STATUS loads publish "
            "the pre-program mailbox word and test all of state, reset and fault"
            % len(candidates)
        )
    return candidates[0]


def verify_pre_run_dominance(
    disassembly_text: str, nm_text: str, entry_symbol: str | None = None
) -> dict:
    """Bind the two claims the source gate deliberately does not make.

    The source gate proves the gate exists and is shaped right. This proves it
    runs before the queue is programmed on *every* path, which is what the
    design asked for and what character order cannot decide -- the frozen
    vendor's eU85_TEST0 branch writes QBASE_LSB earlier in the file than the
    design's programming and never on the measured path.
    """

    # Resolved here because the symbol constant is declared with the source
    # contract further down; the default is not a second opinion about it.
    entry_symbol = entry_symbol or ENTRY_SYMBOL
    code, literals, data = elf_function(disassembly_text, entry_symbol)
    successors = elf_cfg(code, data)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)
    dominators = elf_dominators(successors)
    predicated = elf_predicated(code)

    mailbox_address = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
    gate = _elf_gate_index(code, states, accesses, mailbox_address)
    if gate in predicated:
        raise fail("the pre-program gate is predicated: it may not run at all")

    for index, insn in enumerate(code):
        unresolved = _elf_unresolved_store(code, states, index)
        if unresolved is None:
            continue
        base = states[index].get(unresolved[1])
        if unresolved[1] in ("sp", "pc"):
            continue
        if base is None or elf_in_modelled_region(base):
            # A store this gate cannot place, through a base that could be the
            # NPU, is a queue write it cannot rule out -- and the whole claim
            # below is about which writes exist.
            raise fail_rule(
            RULE_STORE_FORM_UNREADABLE,

                "%s stores through an addressing form this gate cannot resolve at 0x%08x: %s"
                % (entry_symbol, insn.addr, insn.text)
            )

    programming = [
        index for index, role, is_write in accesses if is_write and role in QUEUE_PROGRAMMING_ROLES
    ]
    if not programming:
        raise fail("linked image programs no queue register in %s" % entry_symbol)
    undominated = [index for index in programming if gate not in dominators[index]]
    if undominated:
        raise fail_rule(
            RULE_PRE_PROGRAM_DOMINANCE,

            "the pre-program gate does not dominate queue programming: %d of %d writes are "
            "reachable without it, first at 0x%08x"
            % (len(undominated), len(programming), code[undominated[0]].addr)
        )

    # And nothing may start the NPU in between. A CMD write only transitions the
    # state when it sets bit 0, so the value is read rather than the register.
    starts = []
    for index, role, is_write in accesses:
        if role != "CMD" or not is_write:
            continue
        if gate not in dominators[index]:
            continue
        # Reachability, not dominance. The design forbids a state transition
        # between the gate and the programming writes on *any* path; asking
        # instead whether the CMD write dominates a programming write skips
        # every one written on a branch arm, which is where anyone putting one
        # there would put it.
        if not (elf_reaches(successors, index) & set(programming)):
            continue
        source = _ELF_MEMORY.match(code[index].text).group(2)
        value = states[index].get(source)
        if value is None or value & 1:
            starts.append((index, value))
    if starts:
        index, value = starts[0]
        raise fail_rule(
            RULE_NO_TRANSITION_BEFORE_PROGRAMMING,

            "a CMD write between the pre-program gate and queue programming may start the NPU: "
            "0x%08x writes %s"
            % (code[index].addr, "an unresolved value" if value is None else "0x%08X" % value)
        )

    return {
        "entry_symbol": entry_symbol,
        "mailbox_address": "0x%08X" % mailbox_address,
        "gate_address": "0x%08X" % code[gate].addr,
        "queue_programming_writes": len(programming),
        "queue_programming_addresses": ["0x%08X" % code[i].addr for i in programming],
        "pre_program_gate_dominates_queue_programming": True,
        "no_state_transition_between_gate_and_programming": True,
    }


def verify_primary_loop_image(disassembly_text: str, variant: str) -> dict:
    """What the measured loop actually does, per iteration, in the built image."""

    helper = PRIMARY_SYMBOL[variant]
    code, literals, data = elf_function(disassembly_text, helper)
    successors = elf_cfg(code, data)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)

    # A back edge is one whose target dominates its source, not merely one that
    # points at a lower address: these helpers end with a shared epilogue, and
    # the branches into it go backwards through the listing without looping.
    dominators = elf_dominators(successors)
    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail(
            "the %s primary helper does not carry exactly one loop: %d back edges"
            % (variant, len(back_edges))
        )
    latch, head = back_edges[0]
    body = elf_natural_loop(successors, latch, head)

    in_loop = [(index, role, is_write) for index, role, is_write in accesses if index in body]
    expected = {"Q": ("QREAD",), "QS": ("QREAD", "STATUS"), "SQ": ("STATUS", "QREAD")}[variant]
    order = tuple(role for _index, role, is_write in in_loop if not is_write)
    if order != expected:
        raise fail_rule(
            RULE_PRIMARY_READ_ORDER,

            "the %s primary loop reads %s per iteration: the variant is defined as %s"
            % (variant, " then ".join(order) or "nothing", " then ".join(expected))
        )
    if any(is_write for _index, _role, is_write in in_loop):
        raise fail_rule(
            RULE_PRIMARY_NO_PER_ITERATION_EFFECT,
            "the %s primary loop writes MMIO per iteration" % variant)
    for index in body:
        text = code[index].text
        if _ELF_CALL.match(text):
            raise fail_rule(
            RULE_PRIMARY_NO_PER_ITERATION_EFFECT,
            "the %s primary loop calls out per iteration: %s" % (variant, text))
        # Any store, in any addressing form. Matching only [rB, #imm] meant a
        # register-indexed, predicated or multiple store was not refused here --
        # it was not seen.
        if _elf_is_store(code[index]):
            raise fail_rule(
            RULE_PRIMARY_NO_PER_ITERATION_EFFECT,
            "the %s primary loop stores per iteration: %s" % (variant, text))

    # Which register each of the loop's loads landed in, so the tests below are
    # tied to the load this iteration took rather than to any register that
    # happens to hold the right number.
    load_register = {}
    for index, role, is_write in in_loop:
        if not is_write:
            load_register[role] = _elf_written_register(code[index].text)

    fault_priority = {}
    if variant != "Q":
        status_register = load_register.get("STATUS")
        qread_register = load_register.get("QREAD")
        tests = {}
        for index in body:
            test = _elf_mask_test(code[index].text)
            if test is not None and test[0] == status_register:
                tests.setdefault(test[1], index)
        for mask, label in ((STATUS_RESET, "reset"), (STATUS_FAULT_MASK, "fault")):
            if mask not in tests:
                raise fail_rule(
            RULE_PRIMARY_FAULT_PRIORITY,

                    "the %s primary loop does not test %s (0x%03X) on the STATUS it loaded"
                    % (variant, label, mask)
                )
        # Completion is decided by the queue cursor and by cmd_end, and both have
        # to sit downstream of the reset and fault exits -- a run that faulted
        # must not be reported as a completion first.
        completion = [
            index
            for index in body
            if (
                _elf_mask_test(code[index].text) == (status_register, STATUS_CMD_END)
                or re.match(r"^cmp(?:\.[nw])?\s+%s\s*," % re.escape(qread_register or "\0"), code[index].text)
            )
        ]
        if not completion:
            raise fail("the %s primary loop decides completion on neither QREAD nor cmd_end" % variant)
        for mask, label in ((STATUS_RESET, "reset"), (STATUS_FAULT_MASK, "fault")):
            guard = tests[mask]
            late = [index for index in completion if guard not in dominators[index]]
            if late:
                raise fail_rule(
            RULE_PRIMARY_FAULT_PRIORITY,

                    "the %s primary loop decides completion without the %s check: 0x%08x is "
                    "reachable without 0x%08x"
                    % (variant, label, code[late[0]].addr, code[guard].addr)
                )
        # irq_raised is recorded, never an exit. Letting it end the loop would
        # measure the interrupt rather than the completion.
        for index in body:
            test = _elf_mask_test(code[index].text)
            if test == (status_register, STATUS_IRQ_RAISED):
                raise fail_rule(
            RULE_PRIMARY_IRQ_NOT_AN_EXIT,

                    "the %s primary loop tests irq_raised at 0x%08x: bit 1 is observed, not an exit"
                    % (variant, code[index].addr)
                )
        fault_priority = {
            "reset_test": "0x%08X" % code[tests[STATUS_RESET]].addr,
            "fault_test": "0x%08X" % code[tests[STATUS_FAULT_MASK]].addr,
            "completion_tests": ["0x%08X" % code[i].addr for i in completion],
        }

    qsize = [index for index, role, _w in accesses if role == "QSIZE"]
    if qsize:
        raise fail_rule(
            RULE_PRIMARY_NO_QSIZE,

            "the %s primary helper accesses QSIZE at 0x%08x: the snapshot is taken before submit"
            % (variant, code[qsize[0]].addr)
        )
    timestamps = [index for index, role, _w in accesses if role == "DWT_CYCCNT"]
    if any(index in body for index in timestamps):
        raise fail_rule(
            RULE_PRIMARY_NO_PER_ITERATION_EFFECT,
            "the %s primary loop timestamps per iteration" % variant)

    return {
        "helper": helper,
        "loop_reads_in_order": list(order),
        "loop_instruction_count": len(body),
        "loop_mmio_reads_per_iteration": len(order),
        "qsize_accesses": 0,
        "timestamp_reads_outside_the_loop": len(timestamps),
        # Empty for Q, which has no STATUS in its loop to order anything against.
        "fault_priority": fault_priority,
        # Checked where there is a STATUS load in the loop to check it on. Q has
        # none, so the claim is vacuous there and says so rather than reading as
        # a proof somebody made.
        "irq_raised_exit_scope": (
            "no STATUS in the loop" if variant == "Q" else "checked: irq_raised drives no exit"
        ),
    }


def _elf_normalized(insn) -> str:
    """One instruction with objdump's commentary removed.

    The commentary is where the helper's own name appears, so leaving it in
    would make QS and SQ differ on every branch simply for being called
    different things.
    """

    return re.sub(r"\s+", " ", _ELF_ANNOTATION.sub("", insn.text)).strip()


def _elf_relocatable(code) -> tuple[str, ...]:
    """Each instruction with branch targets read as positions, not addresses.

    The convergence helper is linked at a different address in each variant --
    Q's primary helper is shorter, so everything after it shifts -- and every
    branch inside it then differs by that shift. Comparing raw text would call
    three identical tails three different programs; comparing a raw object
    digest would do the same. What has to match is the instruction and, where it
    branches, which instruction it branches to.
    """

    index_of = {insn.addr: index for index, insn in enumerate(code)}
    rendered = []
    for insn in code:
        text = _elf_normalized(insn)
        if insn.target is not None and insn.target in index_of:
            text = "%s ->#%d" % (text.split()[0], index_of[insn.target])
        rendered.append(text)
    return tuple(rendered)


def _elf_status_bits_tested(code, body, status_register) -> set:
    """Every STATUS bit the loop body decides on, however GCC spelled the test.

    ``-O1`` merges ``cmd_end`` and ``irq_raised`` into one ``and rD, rS, #0x22``
    followed by ``cmp rD, #0x22``, so a rule that only counted single-bit tests
    would report the design's four-condition predicate as two conditions.
    """

    bits = 0
    merged = re.compile(r"^and(?:s)?(?:\.[nw])?\s+(\w+),\s*(\w+),\s*#(\d+)")
    for index in body:
        test = _elf_mask_test(code[index].text)
        if test is not None and test[0] == status_register:
            bits |= test[1]
            continue
        hit = merged.match(code[index].text)
        if hit is not None and hit.group(2) == status_register:
            destination, mask = hit.group(1), int(hit.group(3))
            for step in range(index + 1, min(index + 4, len(code))):
                compare = re.match(
                    r"^cmp(?:\.[nw])?\s+%s\s*,\s*#(\d+)" % re.escape(destination),
                    code[step].text,
                )
                if compare is not None:
                    bits |= mask
                    break
    return bits


def verify_convergence_tail_image(objdump_text: str) -> dict:
    """The common tail, as the image runs it.

    The design joins every variant to one bounded tail whose iteration reads
    QREAD then STATUS and declares convergence only when a single tuple carries
    all four conditions. Accumulating them across iterations would report a
    convergence that never happened at one instant, which is the thing the tail
    exists to avoid.
    """

    code, literals, data = elf_function(objdump_text, CONVERGE_SYMBOL)
    successors = elf_cfg(code, data)
    states = elf_register_values(code, literals, successors)
    accesses = elf_mmio_accesses(code, states)
    dominators = elf_dominators(successors)

    back_edges = [
        (index, out)
        for index, outs in enumerate(successors)
        for out in outs
        if out in dominators[index]
    ]
    if len(back_edges) != 1:
        raise fail(
            "the convergence tail does not carry exactly one loop: %d back edges" % len(back_edges)
        )
    latch, head = back_edges[0]
    body = elf_natural_loop(successors, latch, head)

    in_loop = [(index, role, is_write) for index, role, is_write in accesses if index in body]
    order = tuple(role for _index, role, is_write in in_loop if not is_write)
    if order != ("QREAD", "STATUS"):
        raise fail_rule(
            RULE_TAIL_READ_ORDER,

            "the convergence tail reads %s per iteration: the tail order is fixed as QREAD then "
            "STATUS for every variant" % (" then ".join(order) or "nothing")
        )
    if any(is_write for _index, _role, is_write in in_loop):
        raise fail_rule(
            RULE_TAIL_NO_PER_ITERATION_EFFECT,
            "the convergence tail writes MMIO per iteration")
    for index in body:
        text = code[index].text
        if _ELF_CALL.match(text):
            raise fail_rule(
            RULE_TAIL_NO_PER_ITERATION_EFFECT,
            "the convergence tail calls out per iteration: %s" % text)
        if _elf_is_store(code[index]):
            raise fail_rule(
            RULE_TAIL_NO_PER_ITERATION_EFFECT,
            "the convergence tail stores per iteration: %s" % text)
    if any(role in ("QSIZE", "DWT_CYCCNT") for _index, role, _w in in_loop):
        raise fail_rule(
            RULE_TAIL_NO_PER_ITERATION_EFFECT,
            "the convergence tail reaches QSIZE or the cycle counter per iteration")

    status_register = next(
        _elf_written_register(code[index].text)
        for index, role, is_write in in_loop
        if role == "STATUS" and not is_write
    )
    bits = _elf_status_bits_tested(code, body, status_register)
    required = {
        "cmd_end_reached": STATUS_CMD_END,
        "irq_raised": STATUS_IRQ_RAISED,
        "state": STATUS_STATE,
        "reset_status": STATUS_RESET,
    }
    for label, mask in required.items():
        if not bits & mask:
            raise fail_rule(
            RULE_TAIL_FOUR_CONDITIONS,

                "the convergence tail never decides on %s (0x%03X): the tail requires all four "
                "conditions in one tuple" % (label, mask)
            )
    if not bits & STATUS_FAULT_MASK:
        raise fail_rule(
            RULE_TAIL_FOUR_CONDITIONS,
            "the convergence tail never decides on the vendor fault mask")

    bound = [
        int(hit.group(2))
        for index in range(len(code))
        if index not in body
        for hit in (_ELF_MOVW.match(code[index].text) or _ELF_MOV_IMM.match(code[index].text),)
        if hit is not None
    ]
    if ITERATION_BOUND not in bound:
        raise fail_rule(
            RULE_TAIL_BOUND,

            "the convergence tail does not materialise the %d iteration bound outside its loop"
            % ITERATION_BOUND
        )

    return {
        "helper": CONVERGE_SYMBOL,
        "loop_reads_in_order": list(order),
        "loop_instruction_count": len(body),
        "status_bits_decided": "0x%03X" % bits,
        "iteration_bound": ITERATION_BOUND,
        "per_iteration_stores": 0,
    }


def verify_common_tail_is_shared(images: dict) -> dict:
    """One tail, three variants, differing only by where it was linked."""

    rendered = {}
    for variant, text in sorted(images.items()):
        code, _literals, _data = elf_function(text, CONVERGE_SYMBOL)
        rendered[variant] = _elf_relocatable(code)
    shapes = {variant: _sha256_text("\n".join(rows)) for variant, rows in rendered.items()}
    if len(set(shapes.values())) != 1:
        first = sorted(rendered)[0]
        for variant in sorted(rendered):
            if rendered[variant] == rendered[first]:
                continue
            difference = next(
                (
                    "#%d %s against %s" % (index, left, right)
                    for index, (left, right) in enumerate(zip(rendered[first], rendered[variant]))
                    if left != right
                ),
                "a different instruction count",
            )
            raise fail_rule(
            RULE_TAIL_SHARED,

                "the convergence tail is not shared: %s and %s differ at %s"
                % (first, variant, difference)
            )
    return {
        "helper": CONVERGE_SYMBOL,
        "variants": sorted(rendered),
        "instructions": len(next(iter(rendered.values()))),
        "relocation_invariant_sha256": next(iter(shapes.values())),
        "shared_by_every_variant": True,
    }


def _dwarf_attributes(lines, start):
    """The attribute lines of the DIE beginning at ``start``."""

    for index in range(start + 1, len(lines)):
        if _DWARF_DIE.match(lines[index]):
            return
        yield lines[index]


def dwarf_record_layout(dwarf_text: str) -> dict:
    """``{name: byte offset}`` for the diagnostic record, plus its size.

    Read off the typedef rather than off a struct name, because the contract
    names the typedef and a struct tag is not required to exist.
    """

    lines = dwarf_text.splitlines()
    structure = None
    for index, line in enumerate(lines):
        if "DW_AT_name" not in line or RECORD_TYPEDEF not in line:
            continue
        for attribute in _dwarf_attributes(lines, index - 1):
            hit = _DWARF_TYPE_REF.search(attribute)
            if hit is not None:
                structure = hit.group(1)
                break
        if structure is not None:
            break
    if structure is None:
        raise fail_rule(
            RULE_DWARF_RECORD_PRESENT,
            "DWARF carries no %s typedef pointing at a structure" % RECORD_TYPEDEF)

    members: list[tuple[int, str]] = []
    size = None
    depth = None
    for index, line in enumerate(lines):
        die = _DWARF_DIE.match(line)
        if die is None:
            continue
        level, offset, tag = int(die.group(1)), die.group(2), die.group(3)
        if offset == structure:
            depth = level
            for attribute in _dwarf_attributes(lines, index):
                hit = _DWARF_BYTE_SIZE.search(attribute)
                if hit is not None:
                    size = int(hit.group(1))
                    break
            continue
        if depth is None:
            continue
        if level <= depth:
            break
        if tag != "DW_TAG_member" or level != depth + 1:
            continue
        name = member_offset = None
        for attribute in _dwarf_attributes(lines, index):
            named = _DWARF_NAME.search(attribute)
            located = _DWARF_MEMBER_OFFSET.search(attribute)
            if named is not None:
                name = named.group(1)
            if located is not None:
                member_offset = int(located.group(1))
        if name is None or member_offset is None:
            raise fail_rule(
            RULE_DWARF_MEMBER_READABLE,
            "DWARF member of %s carries no name or no offset" % RECORD_TYPEDEF)
        members.append((member_offset, name))

    if size is None:
        raise fail_rule(
            RULE_DWARF_SIZE_PRESENT,
            "DWARF gives %s no byte size" % RECORD_TYPEDEF)
    return {"byte_size": size, "members": tuple(members)}


def dwarf_static_address(dwarf_text: str, symbol: str) -> int:
    """The absolute address DWARF gives a file-static object."""

    lines = dwarf_text.splitlines()
    found = []
    for index, line in enumerate(lines):
        if "DW_AT_name" not in line or not line.rstrip().endswith(symbol):
            continue
        for attribute in _dwarf_attributes(lines, index - 1):
            hit = _DWARF_ADDR.search(attribute)
            if hit is not None:
                found.append(int(hit.group(1), 16))
    if len(found) != 1:
        raise fail(
            "DWARF gives %s %d absolute locations: expected exactly one" % (symbol, len(found))
        )
    return found[0]


def verify_record_layout_image(dwarf_text: str, nm_text: str | None = None) -> dict:
    """The laid-out record is the table the host indexes, not a hopeful reading.

    The appendix has to be the *last* thirty-four words, in wire order, four
    bytes apart, with nothing padded in between -- because the host reads it by
    index from the end of the frozen body, and a hole would shift every field
    after it while every source rule stayed satisfied.
    """

    layout = dwarf_record_layout(dwarf_text)
    members = layout["members"]
    if layout["byte_size"] != BODY_WORDS * 4:
        raise fail_rule(
            RULE_RECORD_SIZE,

            "the laid-out record is %d bytes: the body is %d words, so it is %d"
            % (layout["byte_size"], BODY_WORDS, BODY_WORDS * 4)
        )
    # Not "every member is one word": the record nests the four snapshots as
    # structures of their own, so it has fewer members than it has words. What
    # the host indexes is the appendix, and that is what is held to the layout.
    appendix = members[-APPENDIX_WORDS:]
    if len(appendix) != APPENDIX_WORDS:
        raise fail(
            "the laid-out record has %d members: fewer than the %d appendix words"
            % (len(members), APPENDIX_WORDS)
        )
    for position in range(1, len(appendix)):
        if appendix[position][0] - appendix[position - 1][0] != 4:
            raise fail_rule(
            RULE_RECORD_APPENDIX_CONTIGUOUS,

                "the laid-out appendix pads before %s: it sits %d bytes after %s rather than 4"
                % (
                    appendix[position][1],
                    appendix[position][0] - appendix[position - 1][0],
                    appendix[position - 1][1],
                )
            )
    if appendix[-1][0] + 4 != layout["byte_size"]:
        raise fail_rule(
            RULE_RECORD_APPENDIX_ENDS_RECORD,

            "the laid-out appendix does not end the record: %s ends at byte %d of %d"
            % (appendix[-1][1], appendix[-1][0] + 4, layout["byte_size"])
        )

    if [name for _offset, name in appendix] != list(APPENDIX_FIELDS):
        raise fail_rule(
            RULE_RECORD_APPENDIX_ORDER,

            "the laid-out appendix is not the contract's table in wire order: %s"
            % ", ".join(
                "%s!=%s" % (name, expected)
                for (_offset, name), expected in zip(appendix, APPENDIX_FIELDS)
                if name != expected
            )
        )
    agreement = None
    if nm_text is not None:
        # Two independent records of where the mailbox is. They are produced by
        # different parts of the toolchain, so agreement is evidence and
        # disagreement means one of them is describing a different build.
        from_dwarf = dwarf_static_address(dwarf_text, MAILBOX_SYMBOL)
        from_nm = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
        if from_dwarf != from_nm:
            raise fail_rule(
            RULE_DWARF_NM_AGREE,

                "DWARF and nm disagree about %s: 0x%08X against 0x%08X"
                % (MAILBOX_SYMBOL, from_dwarf, from_nm)
            )
        agreement = "0x%08X" % from_dwarf

    return {
        "record_typedef": RECORD_TYPEDEF,
        "mailbox_address_agreed_by_dwarf_and_nm": agreement,
        "record_bytes": layout["byte_size"],
        "record_members": len(members),
        "body_words": BODY_WORDS,
        "appendix_first_field": appendix[0][1],
        "appendix_first_byte_offset": appendix[0][0],
        "appendix_last_field": appendix[-1][1],
        "appendix_last_byte_offset": appendix[-1][0],
        "wire_words": TOTAL_WORDS,
        "wire_bytes": PAYLOAD_BYTES,
        "appendix_offsets_bound_by_dwarf": True,
    }


def verify_runner_mailbox_gate_image(objdump_text: str, nm_text: str) -> dict:
    """The runner reads the tuple only where the magic said there is one.

    The mailbox is written by the firmware between runs and read by the runner
    after them, so the magic word is the only thing standing between a stale
    frame and a diagnostic record the host believes. This proves the standing
    happens on every path.

    It also happens to be the clearest case for doing this on a graph rather
    than on positions: the compiler lays the copy *earlier* in the function than
    the check it is guarded by, so index order says the runner reads first and
    asks afterwards. Dominance says otherwise, and dominance is what runs.
    """

    mailbox = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
    code, literals, data = elf_function(objdump_text, RUNNER_DISPATCH_SYMBOL)
    successors = elf_cfg(code, data)
    states = elf_register_values(code, literals, successors)
    dominators = elf_dominators(successors)

    accesses = []
    for index, insn in enumerate(code):
        hit = _ELF_MEMORY.match(insn.text)
        if hit is None:
            continue
        base = states[index].get(hit.group(3))
        if base is None:
            continue
        word, remainder = divmod(base + int(hit.group(4) or 0) - mailbox, 4)
        if remainder or not 0 <= word < APPENDIX_WORDS:
            continue
        accesses.append((index, word, hit.group(1) == "str"))

    for index, insn in enumerate(code):
        unresolved = _elf_unresolved_store(code, states, index)
        if unresolved is None or unresolved[1] in ("sp", "pc"):
            continue
        base = states[index].get(unresolved[1])
        if base is not None and mailbox <= base < mailbox + 4 * APPENDIX_WORDS:
            raise fail_rule(
            RULE_RUNNER_MAILBOX_READONLY,

                "the runner stores into the mailbox at 0x%08x through an addressing form this "
                "gate cannot resolve: %s" % (insn.addr, insn.text)
            )

    written = [(index, word) for index, word, is_write in accesses if is_write]
    if written:
        raise fail_rule(
            RULE_RUNNER_MAILBOX_READONLY,

            "the runner writes mailbox word %d at 0x%08x: the mailbox is the firmware's to fill"
            % (written[0][1], code[written[0][0]].addr)
        )

    compares = []
    for index, insn in enumerate(code):
        hit = _ELF_COMPARE_REGISTERS.match(insn.text)
        if hit is None:
            continue
        values = (states[index].get(hit.group(1)), states[index].get(hit.group(2)))
        if MAILBOX_VALID in values:
            compares.append(index)
    if len(compares) != 1:
        raise fail_rule(
            RULE_RUNNER_MAILBOX_ONE_CHECK,

            "the runner compares against the mailbox magic %d times: it gates the copy once"
            % len(compares)
        )
    gate = compares[0]

    tuple_words = sorted({word for _index, word, _w in accesses if word != MAILBOX_VALID_WORD})
    if tuple_words != list(range(APPENDIX_WORDS - 1)):
        raise fail_rule(
            RULE_RUNNER_TUPLE_COMPLETE,

            "the runner reads %d of the %d appendix words before the validity word: the record "
            "it publishes would carry fields it never copied"
            % (len(tuple_words), APPENDIX_WORDS - 1)
        )
    ungated = [
        index
        for index, word, is_write in accesses
        if word != MAILBOX_VALID_WORD and gate not in dominators[index]
    ]
    if ungated:
        raise fail_rule(
            RULE_RUNNER_MAILBOX_GATED,
            "the runner reads the mailbox tuple without the magic check: 0x%08x is reachable "
            "without 0x%08x" % (code[ungated[0]].addr, code[gate].addr)
        )

    return {
        "dispatcher": RUNNER_DISPATCH_SYMBOL,
        "magic_check_address": "0x%08X" % code[gate].addr,
        "tuple_words_read": len(tuple_words),
        "mailbox_writes_by_the_runner": 0,
        "every_tuple_read_dominated_by_the_magic_check": not ungated,
        # Recorded because it is the reason this proof is a graph and not a scan.
        "copy_precedes_the_check_in_listing_order": min(
            index for index, word, _w in accesses if word != MAILBOX_VALID_WORD
        )
        < gate,
    }


def _elf_word_writes(objdump_text: str, name: str, seen: frozenset) -> int:
    """How many frame words a call to ``name`` writes, counted on the image.

    Counting calls is only counting words while the counting path is straight
    line: a loop or a recursion would make the number depend on data this gate
    cannot see, so both are refused rather than assumed to run once.
    """

    if name == WORD_WRITER_SYMBOL:
        return 1
    if name in seen:
        raise fail_rule(
            RULE_SERIALIZATION_COUNTABLE,
            "the serializer recurses through %s: its word count is not a constant" % name)
    code, _literals, data = elf_function(objdump_text, name)
    successors = elf_cfg(code, data)
    dominators = elf_dominators(successors)
    # Reachability first, and everything after it is asked of reachable code
    # only. A call the entry cannot reach is written and never runs, so counting
    # it counts the source rather than any execution -- which is why this is
    # taken over the CFG and not over the address range, a distinction a linear
    # scan cannot make. Dominance over unreachable nodes is vacuous besides, so
    # asking the loop question about them reports back edges that do not exist.
    reachable = elf_reaches(successors, 0) | {0}
    if any(
        out in dominators[index]
        for index in reachable
        for out in successors[index]
    ):
        raise fail_rule(
            RULE_SERIALIZATION_COUNTABLE,

            "%s loops: the number of words it writes is not something this gate can count" % name
        )
    # Counting the calls that are *written* only counts the calls that *run*
    # while every one of them runs. Refusing loops leaves the other half open:
    # a call under a forward branch is written once and executed on some paths
    # and not others, and the count this returns would be a count of the source
    # rather than of any execution. With no loops left, a call runs on every
    # path exactly when it dominates every exit.
    exits = [index for index in reachable if not successors[index]]
    if not exits:
        raise fail_rule(
            RULE_SERIALIZATION_COUNTABLE,
            "%s has no path that returns: this gate cannot count what it writes" % name
        )
    total = 0
    for index, insn in enumerate(code):
        if index not in reachable or not _ELF_CALL.match(insn.text):
            continue
        # Reachable is not the same as always: a call under a forward branch
        # runs on some paths and not others, so the number of words it accounts
        # for is a property of the path rather than of the function. Refused
        # rather than counted-or-not, because either answer would be wrong on
        # half the executions.
        if any(index not in dominators[exit] for exit in exits):
            raise fail_rule(
                RULE_SERIALIZATION_COUNTABLE,
                "%s makes a call at 0x%08x that some path through it skips: how many words "
                "it writes depends on which path runs" % (name, insn.addr)
            )
        callee = _ELF_CALLEE.match(insn.text)
        if callee is None:
            raise fail_rule(
            RULE_SERIALIZATION_NAMED_CALLEES,

                "%s makes a call this gate cannot name at 0x%08x: it may write frame words"
                % (name, insn.addr)
            )
        total += _elf_word_writes(objdump_text, callee.group(1), seen | {name})
    return total


def verify_serialization_image(objdump_text: str) -> dict:
    """The frame the runner sends is exactly the frame the contract declares.

    Field order and record layout are proven elsewhere; this is the length.
    A serializer that emits one word too few leaves the host reading a field
    short for the rest of the frame, and every rule about *which* field goes
    where stays satisfied while it does.
    """

    words = _elf_word_writes(objdump_text, SERIALIZER_SYMBOL, frozenset())
    if words != TOTAL_WORDS:
        raise fail_rule(
            RULE_SERIALIZATION_LENGTH,

            "the serializer writes %d frame words: the contract's frame is %d words of %d bytes"
            % (words, TOTAL_WORDS, PAYLOAD_BYTES)
        )
    code, _literals, data = elf_function(objdump_text, SERIALIZER_SYMBOL)
    successors = elf_cfg(code, data)
    stores = [
        insn
        for insn in code
        if (hit := _ELF_MEMORY.match(insn.text)) is not None and hit.group(1) == "str"
    ]
    return {
        "serializer": SERIALIZER_SYMBOL,
        "word_writer": WORD_WRITER_SYMBOL,
        "frame_words_written": words,
        "frame_bytes": words * 4,
        "contract_words": TOTAL_WORDS,
        "contract_bytes": PAYLOAD_BYTES,
        "serializer_is_straight_line": True,
        "serializer_direct_stores": len(stores),
    }


def verify_npu_irq_never_enabled_image(objdump_text: str) -> dict:
    """The V12 hard bypass, retained and -- for the first time -- executed.

    V12 established that the NPU interrupt is never enabled, and V13 carried a
    whole-image rule for it that was never wired to anything: running it against
    V13's own board-qualified image refuses it. It is also broader than the
    claim, refusing *any* write into the NVIC enable bank, and the runner
    restores an unrelated interrupt through one.

    So the claim is made about the bit that matters. NPU0_IRQn is 16, which is
    bit 16 of ISER[0]; a write that sets it -- or any write to ISER[0] whose
    value this gate cannot resolve -- is refused, and writes to the other banks
    are recorded rather than refused because they cannot reach the NPU.
    """

    parse_functions, split_code_and_literals = _elf_front_end()
    npu_word, npu_bit = divmod(NPU_IRQ_NUMBER, 32)
    npu_address = NVIC_ISER_BASE + 4 * npu_word
    unrelated = []
    for name, rows in parse_functions(objdump_text).items():
        code, literals = split_code_and_literals(rows)
        if not code:
            continue
        try:
            successors = elf_cfg(code, _elf_data_bytes(objdump_text, name))
        except GateError:
            continue
        states = elf_register_values(code, literals, successors)
        for index, insn in enumerate(code):
            unresolved = _elf_unresolved_store(code, states, index)
            if unresolved is not None:
                # A store into the enable bank through an index register reaches
                # a word this gate cannot name, and one of those words is the
                # NPU's. Refused rather than skipped.
                base = states[index].get(unresolved[1])
                if base is not None and (
                    NVIC_ISER_BASE <= base < NVIC_ISER_BASE + 4 * NVIC_ISER_WORDS
                ):
                    raise fail_rule(
            RULE_NPU_IRQ_UNRESOLVED_WRITE,

                        "%s writes the interrupt-enable bank at 0x%08x through an addressing "
                        "form this gate cannot resolve: %s" % (name, insn.addr, insn.text)
                    )
                continue
            hit = _ELF_MEMORY.match(insn.text)
            if hit is None or hit.group(1) != "str":
                continue
            base = states[index].get(hit.group(3))
            if base is None:
                continue
            address = base + int(hit.group(4) or 0)
            if not NVIC_ISER_BASE <= address < NVIC_ISER_BASE + 4 * NVIC_ISER_WORDS:
                continue
            value = states[index].get(hit.group(2))
            if address != npu_address:
                unrelated.append(
                    "%s writes 0x%08X" % (name, address)
                    if value is None
                    else "%s writes 0x%08X <- 0x%08X" % (name, address, value)
                )
                continue
            if value is None:
                raise fail_rule(
            RULE_NPU_IRQ_UNRESOLVED_WRITE,

                    "%s writes the NPU's own interrupt-enable word at 0x%08x with a value this "
                    "gate cannot resolve: the bypass is not provable" % (name, insn.addr)
                )
            if value & (1 << npu_bit):
                raise fail_rule(
            RULE_NPU_IRQ_NEVER_ENABLED,

                    "%s enables the NPU interrupt at 0x%08x: 0x%08X sets bit %d of ISER[%d]"
                    % (name, insn.addr, value, npu_bit, npu_word)
                )
    return {
        "npu_irq": NPU_IRQ_NUMBER,
        "npu_enable_word": "0x%08X" % npu_address,
        "npu_enable_bit": npu_bit,
        "npu_interrupt_never_enabled": True,
        # Recorded, not refused: these cannot reach the NPU, and refusing them is
        # what made the inherited rule unable to pass its own image.
        "writes_to_other_enable_words": sorted(set(unrelated)),
    }


def verify_read_order_equivalence(qs_text: str, sq_text: str) -> dict:
    """QS and SQ differ in read order and in nothing else the image can show.

    This is the claim the campaign rests on. If the two helpers differed
    anywhere else -- a bound, a predicate, an exit, an extra effect -- then a
    difference in what they observe would have a second explanation, and the
    read-order result would not be a read-order result.
    """

    qs, _qsp, qs_data = elf_function(qs_text, PRIMARY_SYMBOL["QS"])
    sq, _sqp, sq_data = elf_function(sq_text, PRIMARY_SYMBOL["SQ"])
    if len(qs) != len(sq):
        raise fail_rule(
            RULE_READ_ORDER_EQUIVALENCE,

            "the QS and SQ helpers are not the same length: %d against %d instructions"
            % (len(qs), len(sq))
        )
    if elf_cfg(qs, qs_data) != elf_cfg(sq, sq_data):
        raise fail_rule(
            RULE_READ_ORDER_EQUIVALENCE,
            "the QS and SQ helpers do not share one control-flow graph")

    differing = [
        index
        for index, (left, right) in enumerate(zip(qs, sq))
        if _elf_normalized(left) != _elf_normalized(right)
    ]
    if len(differing) != 2:
        raise fail_rule(
            RULE_READ_ORDER_EQUIVALENCE,

            "the QS and SQ helpers differ at %d instructions: the variants are defined to "
            "differ at exactly the two loads" % len(differing)
        )
    first, second = differing
    if second != first + 1:
        raise fail_rule(
            RULE_READ_ORDER_EQUIVALENCE,
            "the QS and SQ helpers differ at non-adjacent instructions")
    if not (
        _elf_normalized(qs[first]) == _elf_normalized(sq[second])
        and _elf_normalized(qs[second]) == _elf_normalized(sq[first])
    ):
        raise fail_rule(
            RULE_READ_ORDER_EQUIVALENCE,

            "the two instructions QS and SQ differ at are not each other's swap: %s / %s "
            "against %s / %s"
            % (
                _elf_normalized(qs[first]),
                _elf_normalized(qs[second]),
                _elf_normalized(sq[first]),
                _elf_normalized(sq[second]),
            )
        )
    return {
        "instructions": len(qs),
        "differing_instructions": len(differing),
        "swapped_at": ["0x%08X" % qs[first].addr, "0x%08X" % qs[second].addr],
        "qs_reads_first": _elf_normalized(qs[first]),
        "sq_reads_first": _elf_normalized(sq[first]),
        "differ_only_in_read_order": True,
    }


def verify_mailbox_publication_image(objdump_text: str, nm_text: str) -> dict:
    """The verdict channel cannot be forged: one store of the magic, in one place.

    This is the claim that matters about integrity, and it replaces one this
    contract used to state about the vendor's return code. The runner reads the
    appendix only when the magic word is present, so a second store of the magic
    anywhere in the image -- on a path that never filled the tuple -- would hand
    the host a record it never wrote. The return code is not that channel: the
    frozen vendor rewrites it after the command function returns, by design, and
    it only raises a telemetry flag on the host.
    """

    parse_functions, split_code_and_literals = _elf_front_end()
    mailbox = elf_symbol_address(nm_text, MAILBOX_SYMBOL)
    target = mailbox + 4 * MAILBOX_VALID_WORD
    stores = []
    unmodelled = []
    for name, rows in parse_functions(objdump_text).items():
        code, literals = split_code_and_literals(rows)
        if not code:
            continue
        try:
            successors = elf_cfg(code, _elf_data_bytes(objdump_text, name))
        except GateError:
            # A function this gate cannot model is one it cannot clear either,
            # so where such a function names the magic the scope is recorded
            # rather than argued away. With the two switch tables decoded there
            # is nothing left in this list, but the list stays: the next image
            # may hold a form this gate has not met.
            if any(word == MAILBOX_VALID for _addr, word in literals):
                unmodelled.append(name)
            continue
        states = elf_register_values(code, literals, successors)
        reachable_magic = _elf_can_materialise(code, literals, MAILBOX_VALID)
        for index, insn in enumerate(code):
            unresolved = _elf_unresolved_store(code, states, index)
            if unresolved is not None:
                # The attacker's move is to get the magic into a register and
                # store it through an addressing form the gate skips. So a store
                # carrying the magic is refused whenever its destination cannot
                # be read, whatever shape it is written in.
                # A store can only reach the mailbox through a base that could
                # be the mailbox. The stack pointer never is, and a base that
                # resolves elsewhere is elsewhere; what is left is a base this
                # gate cannot read, and that one is refused.
                # Scoped to the design's own mailbox writers. The runner
                # legitimately moves the magic -- it copies mailbox word 33 into
                # its record through `stmia ip!, {r0-r3}` with an unresolved
                # base -- so refusing every unreadable store that could carry
                # the magic refuses the real image. That the runner never writes
                # the mailbox is a separate claim, proven by
                # verify_runner_mailbox_gate_image over resolved addresses.
                base = states[index].get(unresolved[1])
                could_reach_mailbox = unresolved[1] not in ("sp", "pc") and (
                    base is None
                    or mailbox <= base < mailbox + 4 * APPENDIX_WORDS
                )
                if (
                    name in MAILBOX_WRITER_SYMBOLS
                    and reachable_magic
                    and could_reach_mailbox
                    and _elf_store_may_carry(states, index, unresolved[0], MAILBOX_VALID)
                ):
                    raise fail_rule(
            RULE_STORE_FORM_UNREADABLE,

                        "%s may store the mailbox magic at 0x%08x through an addressing form "
                        "this gate cannot resolve: %s" % (name, insn.addr, insn.text)
                    )
                continue
            hit = _ELF_MEMORY.match(insn.text)
            if hit is None or not hit.group(1).startswith("str"):
                continue
            stored = states[index].get(hit.group(2))
            if stored is None:
                # An unreadable value into a readable address is the same gap
                # from the other side, so it is refused rather than skipped.
                base = states[index].get(hit.group(3))
                if base is not None and base + int(hit.group(4) or 0) == target:
                    raise fail_rule(
            RULE_STORE_FORM_UNREADABLE,

                        "%s stores a value this gate cannot read into the mailbox validity word "
                        "at 0x%08x: %s" % (name, insn.addr, insn.text)
                    )
                continue
            if stored != MAILBOX_VALID:
                continue
            base = states[index].get(hit.group(3))
            address = None if base is None else base + int(hit.group(4) or 0)
            stores.append((name, insn, address))

    if len(stores) != 1:
        raise fail_rule(
            RULE_MAILBOX_PUBLISHED_ONCE,

            "the modelled functions store the mailbox magic %d times: it is published once, by %s"
            % (len(stores), MAILBOX_PUBLISH_SYMBOL)
        )
    name, insn, address = stores[0]
    if name != MAILBOX_PUBLISH_SYMBOL:
        raise fail_rule(
            RULE_MAILBOX_PUBLISHER_IDENTITY,

            "the mailbox magic is stored by %s rather than %s" % (name, MAILBOX_PUBLISH_SYMBOL)
        )
    if address != target:
        raise fail_rule(
            RULE_MAILBOX_PUBLISH_ADDRESS,

            "the mailbox magic is stored to %s rather than the mailbox validity word 0x%08X"
            % ("an unresolved address" if address is None else "0x%08X" % address, target)
        )

    # The tuple has to be visible before the word that says it is there.
    code, literals, data = elf_function(objdump_text, MAILBOX_PUBLISH_SYMBOL)
    publish = next(i for i, row in enumerate(code) if row.addr == insn.addr)
    if not any(row.mnemonic == "dsb" for row in code[:publish]):
        raise fail_rule(
            RULE_MAILBOX_PUBLISH_FENCED,
            "the mailbox magic is published without a barrier before it")
    if not any(row.mnemonic == "dsb" for row in code[publish + 1 :]):
        raise fail_rule(
            RULE_MAILBOX_PUBLISH_FENCED,
            "the mailbox magic is published without a barrier after it")

    return {
        "publisher": name,
        "magic_store_address": "0x%08X" % insn.addr,
        "mailbox_validity_word_address": "0x%08X" % target,
        "magic_stores_in_the_modelled_functions": len(stores),
        "fenced_both_sides": True,
        # Named for the scope it is taken over, and the scope is the list below.
        "scope": (
            "every function in the image"
            if not unmodelled
            else "functions this gate can build a control-flow graph for"
        ),
        "names_the_magic_but_is_not_modelled": sorted(unmodelled),
        # The one way a magic store could still hide: a function that never
        # names the constant, storing a value it received from memory through an
        # address this gate cannot read. Stated rather than left implicit.
        "writer_scope": sorted(MAILBOX_WRITER_SYMBOLS),
        "residual": (
            "the unreadable-store refusal is scoped to the design's mailbox writers; a magic "
            "arriving from memory into one of them, or a write from outside that set through an "
            "address this gate cannot read, is outside it"
        ),
    }


def verify_linked_image(
    objdump_text: str, nm_text: str, variant: str, dwarf_text: str | None = None
) -> dict:
    """Every claim this contract makes about the built image, in one document."""

    dominance = verify_pre_run_dominance(objdump_text, nm_text)
    loop = verify_primary_loop_image(objdump_text, variant)
    publication = verify_mailbox_publication_image(objdump_text, nm_text)
    runner_gate = verify_runner_mailbox_gate_image(objdump_text, nm_text)
    serialization = verify_serialization_image(objdump_text)
    retained = verify_npu_irq_never_enabled_image(objdump_text)
    tail = verify_convergence_tail_image(objdump_text)
    layout = (
        verify_record_layout_image(dwarf_text, nm_text)
        if dwarf_text is not None
        else {
            "appendix_offsets_bound_by_dwarf": False,
            "scope": "not checked: --dwarf-text was not given",
        }
    )
    return {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "proof_scope": "linked_image",
        "pre_run": dominance,
        "primary_loop": loop,
        "convergence_tail": tail,
        "record_layout": layout,
        "mailbox_publication": publication,
        "runner_mailbox_gate": runner_gate,
        "serialization": serialization,
        "retained_v12_hard_bypass": retained,
        "claims_bound_here": list(BOUND_ON_LINKED_IMAGE),
        "retired_claims": list(RETIRED_CLAIMS),
        # Still owed by nobody. The source gate does not make these and this one
        # does not either, so a reader is told rather than left to infer it.
        "unbound_claims": list(unbound_claims()),
    }
