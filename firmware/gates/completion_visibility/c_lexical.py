"""Successor completion-visibility checker: c lexical."""

from __future__ import annotations

import functools
import hashlib
import re

from .constants import (
    NPU_BASE_SYMBOLS,
    _BLOCK_COMMENT_RE,
    _CHAR_LITERAL_RE,
    _CONTRACT_DEFINE_PREFIXES,
    _C_TOKEN_RE,
    _DEFINE_RE,
    _DIGRAPH_PRIMARY,
    _DIGRAPH_RE,
    _LINE_COMMENT_RE,
    _LINE_SPLICE_RE,
    _MAX_SOURCE_BYTES,
    _NAME_CHARACTER_RE,
    _STRING_LITERAL_RE,
    _TRIGRAPH_RE,
    _UNDEF_RE,
)

from .errors import (
    fail,
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _blank_span(out: list[str], text: str, start: int, stop: int) -> None:
    for index in range(start, stop):
        out[index] = "\n" if text[index] == "\n" else " "


def _mask_one_pass(text: str) -> str:
    """The single left-to-right comment/literal sweep, over already-spliced text."""

    out = list(text)
    index = 0
    length = len(text)
    # An unterminated ``/*`` proves there is no ``*/`` at or after it, so every
    # later opener is unterminated too. Remembering that is what keeps the sweep
    # linear: without it each of n openers rescans the whole tail, and a source
    # made of nothing but openers turns a verdict into minutes of scanning.
    unterminated_block_from: int | None = None
    while index < length:
        character = text[index]
        if character == "/" and index + 1 < length and text[index + 1] in "/*":
            if text[index + 1] == "/":
                pattern = _LINE_COMMENT_RE
            else:
                if unterminated_block_from is not None and index >= unterminated_block_from:
                    index += 1
                    continue
                pattern = _BLOCK_COMMENT_RE
        elif character == '"':
            pattern = _STRING_LITERAL_RE
        elif character == "'":
            pattern = _CHAR_LITERAL_RE
        else:
            index += 1
            continue
        match = pattern.match(text, index)
        if match is None:
            if pattern is _BLOCK_COMMENT_RE:
                unterminated_block_from = index
            index += 1
            continue
        _blank_span(out, text, index, match.end())
        index = match.end()
    return "".join(out)


def _splice_lines(text: str) -> tuple[str, list[int]]:
    """The phase-2 spliced text, with the origin offset of each surviving byte."""

    parts: list[str] = []
    origins: list[int] = []
    index = 0
    for match in _LINE_SPLICE_RE.finditer(text):
        parts.append(text[index : match.start()])
        origins.extend(range(index, match.start()))
        index = match.end()
    parts.append(text[index:])
    origins.extend(range(index, len(text)))
    return "".join(parts), origins


def require_no_token_splice(text: str) -> None:
    """Refuse a splice that joins two token characters.

    Splicing is undone here by deleting bytes and mapping the mask back onto the
    original offsets, which every offset-comparing rule in this file depends on.
    That mapping is faithful for a splice between tokens and cannot be for one
    *inside* a token: ``write_re\\<newline>g`` is one identifier to the compiler
    and two to any scan that keeps the original offsets. Rather than analyse a
    source under a tokenisation the built image does not share, it is refused.
    """

    for match in _LINE_SPLICE_RE.finditer(text):
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        if _NAME_CHARACTER_RE.match(before) and _NAME_CHARACTER_RE.match(after):
            raise fail(
                "source splices a line inside a token at offset %d: the built image and this "
                "gate would not tokenize it alike" % match.start()
            )


def mask_c_lexical(text: str) -> str:
    """Blank comments and literals while preserving every byte offset.

    Line splicing runs first, because C does: translation phase 2 deletes every
    ``\\<newline>`` before phase 3 recognises a comment, so ``/`` ``\\`` newline
    ``*`` opens a block comment in the built image. A masker that does not
    splice never sees that opener and keeps crediting the enclosed text as
    code -- code the compiler deleted. The sweep therefore runs over the spliced
    text and its result is mapped back onto the original offsets, so every
    offset-comparing rule downstream still holds while the *lexical* answer is
    the one the compiler gives.

    The sweep itself is the single left-to-right pass the frozen V13 gate
    already uses, because the construct that opens first is the construct that
    wins. Masking each kind with its own sweep does not hold that rule: a ``/*``
    written *inside* a string literal opens a block comment for the sweep that
    runs first, and everything up to the next ``*/`` -- real executable code
    included -- is blanked before the string sweep ever gets to see that the
    ``/*`` was only text. One pass cannot be talked into that, because reaching
    the ``/`` means the enclosing string was already recognised and skipped.

    Each construct is recognised by a pattern that must close: an unterminated
    block comment or literal simply does not match, and its opening character
    is then left as ordinary code. That is the fail-closed direction -- the
    scan may look at something that is really comment text, but it can never be
    talked out of looking at real code by an unbalanced quote.
    """

    if len(text) > _MAX_SOURCE_BYTES:
        raise fail(
            "source is larger than the %d-byte bound this gate scans: %d bytes"
            % (_MAX_SOURCE_BYTES, len(text))
        )
    spliced, origins = _splice_lines(text)
    if len(spliced) == len(text):
        return _mask_one_pass(text)
    require_no_token_splice(text)
    masked = _mask_one_pass(spliced)
    out = ["\n" if character == "\n" else " " for character in text]
    for position, origin in enumerate(origins):
        out[origin] = masked[position]
    # The splice itself is put back as the one byte that shows where a logical
    # line continues. Blanking it entirely would leave a continued preprocessor
    # directive looking like a directive line followed by an ordinary one, and
    # ``blank_directives`` would then blank half of a macro -- taking its open
    # parentheses with it and unbalancing every depth-tracking scan below.
    for match in _LINE_SPLICE_RE.finditer(text):
        out[match.start()] = "\\"
    return "".join(out)


def require_primary_token_spelling(text: str, what: str) -> None:
    """Refuse a source that spells a punctuator as a trigraph or a digraph."""

    # Phase 1, so it is read over the raw text: a trigraph inside what looks
    # like a comment or a literal is still replaced, and ``??/`` is what would
    # decide where the comment or the literal ends.
    match = _TRIGRAPH_RE.search(text)
    if match is not None:
        raise fail(
            "%s writes the trigraph %s at offset %d: it is replaced before this gate's "
            "lexical scan runs, so the tokens here are not the ones the compiler sees"
            % (what, match.group(0), match.start())
        )
    # Phase 3, so it is read over the spliced and masked text: a digraph is a
    # token, which makes it code rather than the text of a comment or a string,
    # and a splice between its two characters still spells it.
    spliced, origins = _splice_lines(text)
    match = _DIGRAPH_RE.search(_mask_one_pass(spliced))
    if match is not None:
        offset = origins[match.start()] if match.start() < len(origins) else match.start()
        raise fail(
            "%s writes the digraph %s at offset %d: it is an alternate spelling of %s that "
            "this gate does not model, so every rule here reads a token the compiler does not"
            % (what, match.group(0), offset, _DIGRAPH_PRIMARY[match.group(0)])
        )


def _matching_brace(text: str, open_index: int, what: str) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise fail("%s: unbalanced braces" % what)


def extract_function_body(masked: str, name: str, what: str) -> tuple[int, int]:
    """Return the ``(start, stop)`` span of ``name``'s body, braces excluded."""

    definitions = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])%s\s*\(" % re.escape(name), masked):
        close = masked.find(")", match.end() - 1)
        if close < 0:
            continue
        tail = masked[close + 1 :]
        stripped = tail.lstrip()
        if not stripped.startswith("{"):
            continue
        open_index = close + 1 + (len(tail) - len(stripped))
        definitions.append((open_index, _matching_brace(masked, open_index, what)))
    if len(definitions) != 1:
        raise fail("%s: expected exactly one definition, found %d" % (what, len(definitions)))
    open_index, close_index = definitions[0]
    return open_index + 1, close_index


def function_text(masked: str, name: str, what: str) -> str:
    start, stop = extract_function_body(masked, name, what)
    return masked[start:stop]


def normalized_digest(text: str) -> str:
    """Digest of ``text`` after collapsing all whitespace runs to one space."""

    return _sha256_text(re.sub(r"\s+", " ", text).strip())


@functools.lru_cache(maxsize=4)
def directive_view(masked: str) -> str:
    """``masked`` with every logical line joined, byte offsets preserved.

    A preprocessor directive is a *logical* line. Translation phase 2 deletes
    each ``\\``-newline before phase 4 recognises the ``#``, so
    ``#\\``-newline-``undef X`` *is* ``#undef X`` to the compiler --  and
    ``mask_c_lexical`` deliberately puts the backslash and the newline back at
    their original offsets, because every offset-comparing rule below depends on
    that. The two requirements are answered separately rather than traded off:
    the mask keeps the offsets, and this view keeps the *lines*. Blanking the
    splice to as many spaces as it occupied leaves the logical line reading as
    one physical line at the source's own offsets, which is what the directive
    patterns below are written over.

    Without it a directive split by a splice is invisible to every ``(?m)^``
    anchored scan while ``blank_directives`` still removes it from the statement
    stream -- so a source can undefine and redefine a contract macro at a single
    use site, in conforming warning-free C, and this gate models the macro at a
    value the compiler never uses there.
    """

    return _LINE_SPLICE_RE.sub(lambda match: " " * (match.end() - match.start()), masked)


def parse_define_values(masked: str) -> dict[str, list[int]]:
    """Return every integer value each object-like macro is given, in order.

    A macro this contract owns -- anything in the ``V14_`` namespace -- has to
    parse. Dropping a malformed one and reporting the macro as *undefined*
    names the wrong defect, and a reader chasing "is not defined" against a
    source that plainly defines it learns nothing. Macros outside the namespace
    are the vendor's and are skipped when they are not integers.
    """

    values: dict[str, list[int]] = {}
    for match in _DEFINE_RE.finditer(directive_view(masked)):
        name = match.group(1)
        raw = match.group(2).rstrip("uU")
        try:
            parsed = int(raw, 0)
        except ValueError:
            if name.startswith("V14_"):
                raise fail(
                    "malformed numeric define: %s is %r, which is not an integer literal"
                    % (name, match.group(2))
                )
            continue
        values.setdefault(name, []).append(parsed)
    return values


def parse_defines(masked: str) -> dict[str, int]:
    """Return the integer-valued object-like macros of a translation unit."""

    return {name: seen[-1] for name, seen in parse_define_values(masked).items()}


def _is_contract_define(name: str) -> bool:
    return name.startswith(_CONTRACT_DEFINE_PREFIXES) or name in NPU_BASE_SYMBOLS


def require_stable_contract_defines(masked: str, what: str) -> None:
    """Refuse a source whose contract macros do not hold one value throughout.

    Every rule in this file reads a macro's value once and then reasons about
    the store, offset or address that used it. That is only sound while the
    macro has one value for the whole translation unit. ``#undef`` breaks it
    exactly, and warning-free: writing

        #undef V14_MBOX_VARIANT_ID
        #define V14_MBOX_VARIANT_ID 7U
        pmu_completion_visibility_v14_mailbox[V14_MBOX_VARIANT_ID] = V14_VARIANT_ID;
        #undef V14_MBOX_VARIANT_ID
        #define V14_MBOX_VARIANT_ID 0U

    is conforming C11 (6.10.3.5), leaves the frozen spelling untouched, and
    builds an image that publishes the variant id into appendix word 7 while
    this gate reports word 0 -- the mis-attributed frame ``verify_variant_identity``
    exists to prevent. This gate does not expand macros, so it cannot model a
    value that changes between use sites; the fail-closed answer is to refuse
    the source rather than to model it wrongly.
    """

    for match in _UNDEF_RE.finditer(directive_view(masked)):
        if _is_contract_define(match.group(1)):
            raise fail(
                "%s undefines a contract macro at offset %d: %s -- its value at a use site is "
                "not the value this gate reads" % (what, match.start(), match.group(1))
            )
    for name, seen in parse_define_values(masked).items():
        if _is_contract_define(name) and len(set(seen)) > 1:
            raise fail(
                "%s defines the contract macro %s with more than one value: %s -- its value at "
                "a use site is not the value this gate reads"
                % (what, name, ", ".join("0x%X" % value for value in sorted(set(seen))))
            )


def require_define(defines: dict[str, int], name: str, expected: int, what: str) -> None:
    if name not in defines:
        raise fail("%s: %s is not defined" % (what, name))
    if defines[name] != expected:
        raise fail("%s: %s is 0x%X, expected 0x%X" % (what, name, defines[name], expected))


def _token_atom(token: str, open_end: bool) -> str:
    """One token, boundary-anchored on whichever side carries a name character."""

    head = r"(?<![A-Za-z0-9_])" if (token[0].isalnum() or token[0] == "_") else ""
    if open_end or not (token[-1].isalnum() or token[-1] == "_"):
        tail = ""
    else:
        tail = r"(?![A-Za-z0-9_])"
    return head + re.escape(token) + tail


@functools.lru_cache(maxsize=None)
def code_pattern(snippet: str, open_end: bool = False) -> re.Pattern[str]:
    """Compile ``snippet`` into a whitespace-insensitive token matcher.

    ``open_end`` leaves the final token unanchored on its right, which is what
    a register *family* prefix such as ``write_reg(NPU_REG_QBASE`` needs: the
    frozen vendor source spells that register ``NPU_REG_QBASE_LSB``, so the
    prefix has to keep matching the longer name.
    """

    tokens = _C_TOKEN_RE.findall(snippet)
    if not tokens:
        raise fail("empty code pattern %r" % snippet)
    last = len(tokens) - 1
    parts = [_token_atom(tokens[0], open_end and last == 0)]
    for index in range(1, len(tokens)):
        parts.append(r"\s*")
        parts.append(_token_atom(tokens[index], open_end and index == last))
    return re.compile("".join(parts))


def code_positions(text: str, snippet: str, open_end: bool = False) -> tuple[int, ...]:
    """Every offset in ``text`` where ``snippet``'s token sequence starts."""

    return tuple(match.start() for match in code_pattern(snippet, open_end).finditer(text))


def code_find(text: str, snippet: str, open_end: bool = False) -> int:
    """The first offset of ``snippet``'s token sequence, or ``-1``."""

    match = code_pattern(snippet, open_end).search(text)
    return -1 if match is None else match.start()


def code_contains(text: str, snippet: str, open_end: bool = False) -> bool:
    return code_pattern(snippet, open_end).search(text) is not None


def names_identifier(text: str, name: str) -> bool:
    """Whether ``name`` occurs in ``text`` as a whole identifier."""

    return re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name), text) is not None


def function_span(masked: str, name: str, what: str) -> tuple[int, int]:
    return extract_function_body(masked, name, what)
