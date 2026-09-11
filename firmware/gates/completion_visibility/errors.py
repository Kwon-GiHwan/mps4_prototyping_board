"""Successor completion-visibility checker: errors."""

from __future__ import annotations



class GateError(Exception):
    """A stable, named contract rejection."""


def fail(message: str) -> GateError:
    return GateError(message)


# ---------------------------------------------------------------------------
# The linked image
#
# Everything above reads characters. This reads the instructions the CPU will
# execute, and it exists because the claims it makes cannot be made from text:
# dominance is a property of a control-flow graph, and the source has none.
#
# The parsing front end is the one V13 took to the board rather than a new one.
# V12's parse_functions keeps objdump's encoding column in ``text``, which is
# why V13 strips it in _split_code_and_literals; reusing both is what keeps this
# module's mnemonic classification independent of objdump's flags.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule identity
#
# A refusal has to be attributable. Two negative fixtures written here failed
# at a rule other than the one they were named for -- a QSIZE load inside the
# loop was caught by the read-order rule, and a grown record size by the size
# rule -- and both were green because the process exited non-zero. "The suite
# went red" is not evidence that the rule under test did anything.
#
# So every load-bearing refusal carries an identifier, and a negative fixture
# names the identifier it expects. A fixture that trips a different rule is a
# failed fixture, not a passing test.
# ---------------------------------------------------------------------------


def fail_rule(rule: str, message: str) -> GateError:
    return fail("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    """The identifier a refusal carries, or None for an unattributed one."""

    text = ("%s" % error).strip()
    if text.startswith("FAIL "):
        text = text[len("FAIL ") :].lstrip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]
