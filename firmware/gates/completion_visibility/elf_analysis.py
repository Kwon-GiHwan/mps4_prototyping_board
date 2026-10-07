"""Successor completion-visibility checker: elf analysis."""

from __future__ import annotations

import re

from .constants import (
    DWT_BASE_ADDRESS,
    DWT_CYCCNT_ADDRESS,
    MMIO_REGION_SIZE,
    NPU_REGISTER_AT_OFFSET,
    U85_BASE_ADDRESS,
    _ELF_CALL,
    _ELF_CALL_CLOBBERED,
    _ELF_CBZ,
    _ELF_CONDITION_SUFFIX,
    _ELF_COND_BRANCH,
    _ELF_DATA_ROW,
    _ELF_DATA_WIDTH,
    _ELF_DESTINATION,
    _ELF_INDIRECT,
    _ELF_IT,
    _ELF_LOAD_LITERAL,
    _ELF_MASK_TEST,
    _ELF_MEMORY,
    _ELF_MOVT,
    _ELF_MOVW,
    _ELF_MOV_IMM,
    _ELF_MOV_REG,
    _ELF_MULTI_LOAD,
    _ELF_NON_WRITING,
    _ELF_PUSH,
    _ELF_REGISTER_LIST,
    _ELF_RETURN,
    _ELF_STORE_BASE,
    _ELF_STORE_OPERANDS,
    _ELF_TABLE_BRANCH,
    _ELF_TABLE_DEFAULT,
    _ELF_TABLE_GUARD,
    _ELF_UNCOND_BRANCH,
    _ELF_WRITEBACK,
)

from .errors import (
    fail,
)


def _elf_is_store(insn) -> bool:
    return _ELF_CONDITION_SUFFIX.match(insn.mnemonic) is not None


def _elf_store_registers(text: str) -> tuple[tuple[str, ...], str]:
    """``(value registers, base register)`` for any store form.

    Every register that could carry the stored value counts, because the rules
    above ask "is the magic in there" and the forms differ in where they put it:
    ``strd`` puts two registers before the bracket, ``stm`` puts a whole list
    after the base, and ``push`` names no base at all. Reading only the first
    operand is what let ``strd r5, r2, [r3, #132]`` through.
    """

    operands = _ELF_STORE_OPERANDS.match(text)
    if operands is None:
        return ((), "")
    body = operands.group(1)

    listed = _ELF_REGISTER_LIST.search(body)
    if listed is not None:
        # ``stm rB!, {rs}`` / ``push {rs}``: the list is the values, and
        # whatever precedes it is the base -- sp when nothing precedes it.
        values = [name.strip() for name in listed.group(1).split(",") if name.strip()]
        head = body[: listed.start()].strip().rstrip(",").strip()
        base = head.rstrip("!").strip() if head else "sp"
        return (tuple(dict.fromkeys(values)), base)

    base_hit = _ELF_STORE_BASE.search(body)
    base = base_hit.group(1) if base_hit is not None else ""
    head = body[: base_hit.start()] if base_hit is not None else body
    values = [name.strip().rstrip("!") for name in head.split(",") if name.strip()]
    return (tuple(dict.fromkeys(name for name in values if name)), base)


def _elf_unresolved_store(code, states, index):
    """``(value registers, base register)`` when a store's address is unreadable.

    Returns ``None`` only when ``_ELF_MEMORY`` can resolve the store, which is
    the one case the address-based rules are entitled to reason about.
    """

    insn = code[index]
    if not _elf_is_store(insn):
        return None
    if _ELF_MEMORY.match(insn.text) and not _ELF_REGISTER_LIST.search(insn.text):
        return None
    return _elf_store_registers(insn.text)


def _elf_can_materialise(code, literals, value: int) -> bool:
    """Whether this function can produce ``value`` at all.

    A store cannot carry a constant the function has no way to make. Bounding
    the fail-closed rule this way is what keeps it from refusing the whole C
    runtime: every function has stores whose value this gate cannot read, and
    refusing all of them refuses the image rather than an attack.

    What it does not cover, and what the manifest says so: a value that arrives
    from memory into a function that never names it.
    """

    if any(word == value for _address, word in literals):
        return True
    low, high = value & 0xFFFF, (value >> 16) & 0xFFFF
    halves = set()
    for insn in code:
        for pattern in (_ELF_MOVW, _ELF_MOVT, _ELF_MOV_IMM):
            hit = pattern.match(insn.text)
            if hit is not None:
                halves.add(int(hit.group(2)))
    return value in halves or (low in halves and high in halves)


def _elf_store_may_carry(states, index, registers, value: int) -> bool:
    """Whether any of ``registers`` could hold ``value`` here.

    A register the analysis cannot read counts as "could", because the
    alternative is to skip it -- and skipping is how a magic assembled with
    ``mov``+``orr`` walked past a rule that only refused registers it could
    read as the magic.
    """

    for register in registers:
        if register not in states[index] or states[index][register] == value:
            return True
    return not registers


def _elf_mask_test(text: str):
    """``(tested register, mask)`` for a flag-setting mask test, or ``None``."""

    hit = _ELF_MASK_TEST.match(text)
    if hit is None:
        return None
    # ``tst rS, #m`` tests rS; ``ands rD, rS, #m`` tests rS and writes rD.
    return (hit.group(2), int(hit.group(3)))


def _elf_written_register(text: str) -> str | None:
    hit = _ELF_DESTINATION.match(text)
    if hit is None or hit.group(1).lower() in _ELF_NON_WRITING:
        return None
    return hit.group(2)

def _elf_front_end():
    """V12's row parser and V13's encoding-column strip, imported on demand.

    Imported here rather than at module scope so the source-fixture contract
    keeps working in a tree that has only this file.
    """

    from ..identity import IdentityError, load_frozen_helpers

    try:
        v12, v13 = load_frozen_helpers()
    except (IdentityError, ImportError, OSError, ValueError) as exc:
        raise fail("linked-image analysis needs the frozen V12/V13 gates: %s" % exc)
    return v12.parse_functions, v13._split_code_and_literals



def elf_function(disassembly_text: str, name: str):
    """``(instructions, literal pool)`` for one function of the linked image."""

    parse_functions, split_code_and_literals = _elf_front_end()
    headers = re.findall(
        r"(?m)^[0-9a-fA-F]+\s+<%s>:\s*$" % re.escape(name), disassembly_text
    )
    if len(headers) != 1:
        raise fail(
            "linked image carries %d definitions of %s: expected exactly one"
            % (len(headers), name)
        )
    functions = parse_functions(disassembly_text)
    if name not in functions:
        raise fail("linked image has no %s to analyse" % name)
    code, literals = split_code_and_literals(functions[name])
    if not code:
        raise fail("linked image function %s disassembled to nothing" % name)
    return code, literals, _elf_data_bytes(disassembly_text, name)


def _elf_data_bytes(disassembly_text: str, name: str) -> dict:
    """Address -> byte, for the data objdump printed inside this function.

    A jump table's tail is emitted as ``.byte`` rows, and the frozen V13 splitter
    keeps only ``.word`` ones, so reading the table from the literal pool alone
    lost its last entries. This reads whatever width objdump chose.
    """

    section = _function_body_text(disassembly_text, name)
    data: dict[int, int] = {}
    for line in section.splitlines():
        hit = _ELF_DATA_ROW.match(line)
        if hit is None:
            continue
        address = int(hit.group(1), 16)
        width = _ELF_DATA_WIDTH[hit.group(2)]
        value = int(hit.group(3), 16)
        for offset in range(width):
            data[address + offset] = (value >> (8 * offset)) & 0xFF
    return data


def _function_body_text(disassembly_text: str, name: str) -> str:
    start = re.search(r"(?m)^[0-9a-fA-F]+\s+<%s>:\s*$" % re.escape(name), disassembly_text)
    if start is None:
        raise fail("linked image has no %s section" % name)
    # Past the header's own newline first: a blank-line search that starts on it
    # ends the section before it begins, and an empty section reads as a
    # function with no data in it rather than as a bug.
    rest = disassembly_text[start.end() :].lstrip("\n")
    end = rest.find("\n\n")
    return rest if end < 0 else rest[:end]


def _elf_table_targets(code, data, index) -> tuple[int, ...]:
    """Every case a ``tbb``/``tbh`` can reach, or a refusal.

    The table is only decodable because the compiler guards it the same way
    every time: ``cmp rIndex, #N`` then ``bhi default`` then the table branch on
    that same register, so it has exactly N+1 entries. Anything else is refused
    rather than guessed at -- a table read one entry too long invents an edge,
    and one entry too short hides one, and a dominance proof believes both.
    """

    insn = code[index]
    hit = _ELF_TABLE_BRANCH.match(insn.text)
    if hit is None:
        raise fail("table branch at 0x%08x is not a form this gate reads" % insn.addr)
    halfword = hit.group(1) == "tbh"
    register = hit.group(2)
    if index < 2:
        raise fail("table branch at 0x%08x has no room for its bound" % insn.addr)
    guard = _ELF_TABLE_GUARD.match(code[index - 2].text)
    if guard is None or guard.group(1) != register:
        raise fail(
            "table branch at 0x%08x is not bounded by a compare on %s" % (insn.addr, register)
        )
    if not _ELF_TABLE_DEFAULT.match(code[index - 1].text):
        raise fail(
            "table branch at 0x%08x is not guarded by an unsigned-higher branch" % insn.addr
        )
    count = int(guard.group(2)) + 1
    base = insn.addr + 4
    targets = []
    for entry in range(count):
        at = base + (2 * entry if halfword else entry)
        width = 2 if halfword else 1
        octets = [data.get(at + offset) for offset in range(width)]
        if any(octet is None for octet in octets):
            raise fail(
                "table branch at 0x%08x reads entry %d outside the data objdump printed"
                % (insn.addr, entry)
            )
        value = sum(octet << (8 * offset) for offset, octet in enumerate(octets))
        targets.append(base + 2 * value)
    return tuple(targets)


def elf_cfg(code, data=None) -> tuple[tuple[int, ...], ...]:
    """Successor indices, refusing every control transfer this gate cannot model.

    A predicated instruction is not a branch. It either takes effect or does
    not, and control falls through either way, so an IT block is straight line
    here -- and predication is refused separately, at the instructions a proof
    actually depends on running.
    """

    index_of = {insn.addr: index for index, insn in enumerate(code)}
    successors: list[tuple[int, ...]] = []
    for index, insn in enumerate(code):
        text = insn.text
        fallthrough = (index + 1,) if index + 1 < len(code) else ()
        if _ELF_TABLE_BRANCH.match(text):
            targets = _elf_table_targets(code, data or {}, index)
            unknown = [target for target in targets if target not in index_of]
            if unknown:
                raise fail(
                    "table branch at 0x%08x reaches 0x%08x outside the function"
                    % (insn.addr, unknown[0])
                )
            # The default arm is the guard's own branch, already an edge of its
            # own, so the table contributes its cases and nothing else.
            successors.append(tuple(sorted({index_of[target] for target in targets})))
            continue
        if _ELF_INDIRECT.match(text):
            raise fail(
                "indirect control transfer at 0x%08x is not modelled: %s" % (insn.addr, text)
            )
        if _ELF_RETURN.match(text):
            successors.append(())
        elif _ELF_CALL.match(text):
            successors.append(fallthrough)
        elif _ELF_COND_BRANCH.match(text) or _ELF_CBZ.match(text):
            if insn.target is None or insn.target not in index_of:
                raise fail(
                    "conditional branch at 0x%08x leaves the function: %s" % (insn.addr, text)
                )
            successors.append((index_of[insn.target],) + fallthrough)
        elif _ELF_UNCOND_BRANCH.match(text):
            if insn.target is None or insn.target not in index_of:
                raise fail(
                    "branch at 0x%08x leaves the function: %s" % (insn.addr, text)
                )
            successors.append((index_of[insn.target],))
        else:
            successors.append(fallthrough)
    return tuple(successors)


def elf_reaches(successors, start: int) -> frozenset:
    """Every index reachable from ``start`` by following control flow."""

    seen = {start}
    pending = [start]
    while pending:
        node = pending.pop()
        for out in successors[node]:
            if out not in seen:
                seen.add(out)
                pending.append(out)
    return frozenset(seen)


def _predecessors(successors) -> list[list[int]]:
    preds: list[list[int]] = [[] for _ in successors]
    for index, outs in enumerate(successors):
        for out in outs:
            preds[out].append(index)
    return preds


def elf_dominators(successors, entry: int = 0) -> tuple[frozenset, ...]:
    """``dom[i]`` is every index that lies on all paths from entry to ``i``.

    An index no path reaches keeps the full set, which makes it dominated by
    everything and therefore evidence for nothing -- the reachability question
    is asked separately by whoever cares about it.
    """

    count = len(successors)
    preds = _predecessors(successors)
    everything = frozenset(range(count))
    dominators = [everything] * count
    dominators[entry] = frozenset((entry,))
    changed = True
    while changed:
        changed = False
        for index in range(count):
            if index == entry or not preds[index]:
                continue
            updated = frozenset.intersection(
                *(dominators[pred] for pred in preds[index])
            ) | {index}
            if updated != dominators[index]:
                dominators[index] = updated
                changed = True
    return tuple(dominators)


def elf_natural_loop(successors, latch: int, head: int) -> frozenset:
    """The body of the loop closed by ``latch -> head``.

    Not ``range(head, latch + 1)``: at -O1 the convergence tail is rotated, so
    its entry jumps into the middle and the increment block sits at a *lower*
    index than the header. Reading the body as an address range made it empty,
    and an empty body satisfies every per-iteration rule there is.
    """

    preds = _predecessors(successors)
    loop = {head, latch}
    pending = [latch]
    while pending:
        node = pending.pop()
        for pred in preds[node]:
            if pred not in loop:
                loop.add(pred)
                pending.append(pred)
    return frozenset(loop)


def elf_predicated(code) -> frozenset:
    """Indices an IT block makes conditional."""

    covered: set[int] = set()
    for index, insn in enumerate(code):
        hit = _ELF_IT.match(insn.text)
        if hit is None:
            continue
        for step in range(1, len(hit.group(1))):
            if index + step < len(code):
                covered.add(index + step)
    return frozenset(covered)


def elf_register_values(code, literals, successors) -> list[dict]:
    """Register values known on entry to each instruction, by fixpoint.

    A value survives a merge only when every predecessor agrees on it, so a
    base materialised on one path and left alone on another is unknown here
    rather than assumed to be the one this gate would like it to be.
    """

    pool = {address: word for address, word in literals}
    count = len(code)
    preds = _predecessors(successors)
    entry_state: list[dict | None] = [None] * count
    exit_state: list[dict | None] = [None] * count
    changed = True
    while changed:
        changed = False
        for index in range(count):
            if not preds[index]:
                state: dict = {}
            else:
                known = [exit_state[pred] for pred in preds[index] if exit_state[pred] is not None]
                if not known:
                    continue
                state = dict(known[0])
                for other in known[1:]:
                    state = {
                        name: value for name, value in state.items() if other.get(name) == value
                    }
            if entry_state[index] != state:
                entry_state[index] = state
                changed = True
            updated = _elf_transfer(dict(state), code[index], pool)
            if exit_state[index] != updated:
                exit_state[index] = updated
                changed = True
    return [state if state is not None else {} for state in entry_state]


def _elf_transfer(state: dict, insn, pool: dict) -> dict:
    text = insn.text
    if _ELF_CALL.match(text) is not None:
        for register in _ELF_CALL_CLOBBERED:
            state.pop(register, None)
        return state
    multi = _ELF_MULTI_LOAD.match(text)
    if multi is not None:
        for register in multi.group(4).split(","):
            state.pop(register.strip(), None)
        if multi.group(2) and multi.group(3):
            state.pop(multi.group(2), None)
        state.pop("sp", None)
        return state
    if _ELF_PUSH.match(text) is not None:
        state.pop("sp", None)
        return state
    literal = _ELF_LOAD_LITERAL.match(text)
    if literal is not None:
        word = pool.get(insn.target) if insn.target is not None else None
        if word is None:
            state.pop(literal.group(1), None)
        else:
            state[literal.group(1)] = word
        return state
    for pattern, combine in (
        (_ELF_MOVW, lambda old, imm: imm),
        (_ELF_MOVT, lambda old, imm: ((old or 0) & 0xFFFF) | (imm << 16)),
        (_ELF_MOV_IMM, lambda old, imm: imm),
    ):
        hit = pattern.match(text)
        if hit is not None:
            state[hit.group(1)] = combine(state.get(hit.group(1)), int(hit.group(2)))
            return state
    copy = _ELF_MOV_REG.match(text)
    if copy is not None:
        source = state.get(copy.group(2))
        if source is None:
            state.pop(copy.group(1), None)
        else:
            state[copy.group(1)] = source
        return state
    memory = _ELF_MEMORY.match(text)
    written = _elf_written_register(text)
    if written is not None:
        state.pop(written, None)
    if memory is not None and _ELF_WRITEBACK.search(text):
        state.pop(memory.group(3), None)  # the base moved; it is no longer that value
    return state


def elf_in_modelled_region(address: int) -> bool:
    return (
        U85_BASE_ADDRESS <= address < U85_BASE_ADDRESS + MMIO_REGION_SIZE
        or DWT_BASE_ADDRESS <= address < DWT_BASE_ADDRESS + MMIO_REGION_SIZE
    )


def elf_mmio_accesses(code, states) -> tuple[tuple[int, str, bool], ...]:
    """``(index, role, is_write)`` for every access this gate can name.

    An access whose base is unresolved reaches nothing nameable and is not
    counted. It is not refused here either: whether an unresolved access may
    exist where it does is a confinement question, asked by the rules that own
    the region rather than by the decoder.
    """

    found: list[tuple[int, str, bool]] = []
    for index, insn in enumerate(code):
        hit = _ELF_MEMORY.match(insn.text)
        if hit is None:
            continue
        base = states[index].get(hit.group(3))
        if base is None:
            continue
        address = base + int(hit.group(4) or 0)
        if not elf_in_modelled_region(address):
            continue
        if _ELF_WRITEBACK.search(insn.text):
            raise fail(
                "writeback addressing over the modelled region at 0x%08x is not modelled: %s"
                % (insn.addr, insn.text)
            )
        if U85_BASE_ADDRESS <= address < U85_BASE_ADDRESS + MMIO_REGION_SIZE:
            offset = address - U85_BASE_ADDRESS
            role = NPU_REGISTER_AT_OFFSET.get(offset, "NPU+0x%02X" % offset)
        elif address == DWT_CYCCNT_ADDRESS:
            role = "DWT_CYCCNT"
        else:
            role = "DWT+0x%02X" % (address - DWT_BASE_ADDRESS)
        found.append((index, role, hit.group(1) == "str"))
    return tuple(found)
