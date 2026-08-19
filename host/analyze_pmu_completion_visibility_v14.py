"""What the V14 campaign showed, and everything it may not say.

This analyzer is mostly refusal. It is handed nine cells of ten runs and asked
what was observed, and almost every interesting answer is one the design
forbids: a latency, a comparison of cycle counts between variants, a claim that
two registers changed at the same instant. None of those follow from what the
campaign measures, which is the order in which software *saw* two registers
change while sampling them itself.

So the conclusions are five, and they are all of them:

  READ_ORDER_BIAS_DOMINATES  the winner follows the read order, so the order of
                             sampling explains the result and hardware need not
  CONTROL_REQUIRED           both dual variants prefer the same register, or Q
                             and the dual variants disagree qualitatively about
                             floor/excursion structure; either way a fresh
                             bit5-only S5 control comes before any ordering claim
  NO_GAP_RESOLVED            both saw the two events in the same iteration, which
                             is a statement about resolution and not about time
  UNRESOLVED                 the cells do not agree with each other
"""

from __future__ import annotations

from collections import Counter

READ_ORDER_BIAS_DOMINATES = "READ_ORDER_BIAS_DOMINATES"
CONTROL_REQUIRED = "CONTROL_REQUIRED_NO_FINAL_ORDERING"
NO_GAP_RESOLVED = "NO_GAP_RESOLVED"
UNRESOLVED = "UNRESOLVED"

REPRODUCED = "REPRODUCED"
NOT_REPRODUCED = "NOT_REPRODUCED"

CATEGORY_Q_FIRST = "Q_FIRST"
CATEGORY_S5_FIRST = "S5_FIRST"
CATEGORY_SAME_ITERATION = "SAME_ITERATION"
CATEGORIES = (CATEGORY_Q_FIRST, CATEGORY_S5_FIRST, CATEGORY_SAME_ITERATION)

VARIANTS = ("Q", "QS", "SQ")
RUNS_PER_CELL = 10
ROUNDS = 3
POSITIONS = 3

# What the two dual variants were observed to do, kept apart from what may be
# concluded from it. Both variants preferring one register is an observation;
# "that register is visible first" is a claim, and it is not available until a
# fresh bit5-only S5 control has been run. Recording the direction here means
# the observation survives without being promoted.
FOLLOWS_READ_ORDER = "FOLLOWS_READ_ORDER"
QREAD_FIRST_IN_BOTH_ORDERS = "QREAD_FIRST_IN_BOTH_ORDERS"
STATUS_FIRST_IN_BOTH_ORDERS = "STATUS_FIRST_IN_BOTH_ORDERS"
SAME_ITERATION_IN_BOTH_ORDERS = "SAME_ITERATION_IN_BOTH_ORDERS"
MIXED_ACROSS_CELLS = "MIXED_ACROSS_CELLS"

FRESH_CONTROL = "FRESH_STATUS_BIT5_ONLY_CONTROL"


def _dual_order_pattern(qs_category, sq_category) -> str:
    """What the two dual variants did, named without deciding anything."""

    if qs_category is None or sq_category is None:
        return MIXED_ACROSS_CELLS
    if qs_category == CATEGORY_Q_FIRST and sq_category == CATEGORY_S5_FIRST:
        return FOLLOWS_READ_ORDER
    if qs_category == sq_category == CATEGORY_Q_FIRST:
        return QREAD_FIRST_IN_BOTH_ORDERS
    if qs_category == sq_category == CATEGORY_S5_FIRST:
        return STATUS_FIRST_IN_BOTH_ORDERS
    if qs_category == sq_category == CATEGORY_SAME_ITERATION:
        return SAME_ITERATION_IN_BOTH_ORDERS
    return MIXED_ACROSS_CELLS


CONTROL_TEXT = (
    "a fresh V14-family bit5-only S5 control is required before any visibility-order claim; "
    "historical V13 bit1 data never satisfies it"
)


class AnalysisError(RuntimeError):
    """A campaign this analyzer will not draw a conclusion from."""


def _validate(campaign: dict) -> list:
    cells = campaign.get("cells")
    if not isinstance(cells, list):
        raise AnalysisError("campaign carries no cells")
    if len(cells) != ROUNDS * POSITIONS:
        raise AnalysisError(
            "campaign carries %d cells: the balanced matrix is %d" % (len(cells), ROUNDS * POSITIONS)
        )

    seen = set()
    positions = {variant: set() for variant in VARIANTS}
    for entry in cells:
        variant = entry.get("variant")
        if variant not in VARIANTS:
            raise AnalysisError("cell carries variant %r" % (variant,))
        key = (entry.get("round"), entry.get("position"))
        if key in seen:
            raise AnalysisError("two cells share round/position %r" % (key,))
        seen.add(key)
        positions[variant].add(entry.get("position"))

        samples = entry.get("samples") or []
        if len(samples) != RUNS_PER_CELL:
            raise AnalysisError(
                "cell %r carries %d runs, the cell is %d" % (key, len(samples), RUNS_PER_CELL)
            )
        if sorted(sample.get("run_id") for sample in samples) != list(range(1, RUNS_PER_CELL + 1)):
            raise AnalysisError("cell %r does not carry run ids 1..%d" % (key, RUNS_PER_CELL))
        boots = {sample.get("boot_id") for sample in samples}
        if len(boots) != 1:
            raise AnalysisError("cell %r spans %d boots" % (key, len(boots)))
        if any(not sample.get("sample_valid") for sample in samples):
            raise AnalysisError("cell %r carries an invalid sample" % (key,))
        for sample in samples:
            category = sample.get("category")
            if variant == "Q":
                # Q observes one register. A category from Q would be a read
                # order it never had.
                if category is not None:
                    raise AnalysisError("a Q cell carries category %r" % (category,))
                continue
            if category not in CATEGORIES:
                raise AnalysisError("cell %r carries category %r" % (key, category))
            # And the label has to be the one the record's own fields produce.
            # A campaign whose labels were rewritten -- by a bug upstream or by
            # a hand that edited the file -- is refused here rather than
            # believed all the way to a conclusion.
            derived = _derive_category(sample)
            if derived != category:
                raise AnalysisError(
                    "cell %r run %r is labelled %s and its own fields say %s"
                    % (key, sample.get("run_id"), category, derived)
                )

    # Nine cells, nine boots. A floor reproduced across three cells that share
    # one boot is a floor reproduced once: the design asks for independence
    # between the boots, and pooling is exactly what the rule exists to refuse.
    boots = [next(iter({sample["boot_id"] for sample in entry["samples"]})) for entry in cells]
    if len(set(boots)) != len(cells):
        raise AnalysisError(
            "the campaign spans %d boots across %d cells: each cell is its own boot"
            % (len(set(boots)), len(cells))
        )

    # Balance: each variant occupies each position exactly once across rounds.
    for variant in VARIANTS:
        if positions[variant] != {1, 2, 3}:
            raise AnalysisError(
                "variant %s does not occupy every position: %s"
                % (variant, sorted(positions[variant]))
            )
    return cells


def _floor_status(cells) -> dict:
    """Whether the Q boots reproduce one floor, and structure above it."""

    per_boot = []
    for entry in cells:
        values = [sample["q_observation_cycles"] for sample in entry["samples"]]
        per_boot.append({"boot_id": entry["boot_id"], "minimum": min(values), "values": values})
    minima = {boot["minimum"] for boot in per_boot}
    # Pooling would hide a boot that never reached the others' minimum, so the
    # same value has to appear as the minimum of every boot separately.
    floor = NOT_REPRODUCED if len(minima) != 1 else REPRODUCED
    common = next(iter(minima)) if len(minima) == 1 else None
    above = sum(1 for boot in per_boot if any(value > boot["minimum"] for value in boot["values"]))
    return {
        "status": floor,
        "floor": common,
        "boots": len(per_boot),
        "boots_with_values_above_their_minimum": above,
        "excursion": REPRODUCED if floor == REPRODUCED and above >= 2 else NOT_REPRODUCED,
    }


# The bit the firmware sets when the command stream reached its end. Named here
# because this analyzer re-derives from the raw word rather than reading a flag.
STATUS_CMD_END = 0x020


def _derive_category(sample: dict) -> str:
    """The read-order category, computed from the record's own raw fields.

    Not read from ``sample["category"]``. That field is produced upstream, and a
    verdict that trusts it is a verdict about the classifier rather than about
    the run: relabel every sample and the conclusion follows the label. The
    authoritative fields are the ones the firmware wrote -- the queue cursor it
    read, the queue size it was told to expect, and the STATUS word it sampled
    in the same iteration -- and the category follows from those or from nothing.
    """

    for field in ("first_qread", "qsize_expected", "first_status"):
        if sample.get(field) is None:
            raise AnalysisError(
                "a sample carries no %s: the category cannot be re-derived from it" % field
            )
    q_done = sample["first_qread"] == sample["qsize_expected"]
    cmd_end = bool(sample["first_status"] & STATUS_CMD_END)
    if q_done and cmd_end:
        return CATEGORY_SAME_ITERATION
    if q_done:
        return CATEGORY_Q_FIRST
    if cmd_end:
        return CATEGORY_S5_FIRST
    raise AnalysisError(
        "a sample observed neither register in its first tuple: it is not a sample"
    )


def _stable_category(cells) -> str | None:
    """The one category a variant's cells agree on, or None.

    The categories are the re-derived ones. ``_validate`` has already refused any
    sample whose recorded label disagreed with them, so by here the two are the
    same -- which is the point: they were checked, not assumed.
    """

    categories = {_derive_category(sample) for entry in cells for sample in entry["samples"]}
    return categories.pop() if len(categories) == 1 else None


def analyze(campaign: dict) -> dict:
    """The campaign's verdict, with the claims it is not allowed to make."""

    cells = _validate(campaign)
    by_variant = {variant: [entry for entry in cells if entry["variant"] == variant]
                  for variant in VARIANTS}

    q_structure = _floor_status(by_variant["Q"])
    dual_structure = {
        variant: _floor_status(by_variant[variant]) for variant in ("QS", "SQ")
    }

    qs_category = _stable_category(by_variant["QS"])
    sq_category = _stable_category(by_variant["SQ"])

    # A deterministic qualitative disagreement between Q and either dual variant
    # is the dual-read-perturbation trigger: the difference cannot be the
    # hardware, because Q and the dual variants ran the same workload.
    # Both statuses, not just the excursion. The plan names "floor/excursion",
    # and comparing excursion alone hides a floor disagreement behind two
    # matching NOT_REPRODUCED excursions -- which is how a campaign that must
    # ask for the S5 control instead published read-order bias as a finding.
    disagreement = [
        variant
        for variant, structure in dual_structure.items()
        if (structure["status"], structure["excursion"])
        != (q_structure["status"], q_structure["excursion"])
    ]

    if qs_category is None or sq_category is None:
        conclusion = UNRESOLVED
    elif qs_category == CATEGORY_SAME_ITERATION and sq_category == CATEGORY_SAME_ITERATION:
        conclusion = NO_GAP_RESOLVED
    elif qs_category == CATEGORY_Q_FIRST and sq_category == CATEGORY_S5_FIRST:
        # The winner followed the read order in both directions.
        conclusion = READ_ORDER_BIAS_DOMINATES
    elif qs_category == sq_category:
        conclusion = CONTROL_REQUIRED
    else:
        conclusion = UNRESOLVED

    if disagreement and conclusion != UNRESOLVED:
        conclusion = CONTROL_REQUIRED

    per_boot = {}
    for variant in ("QS", "SQ"):
        for entry in by_variant[variant]:
            per_boot["%s/%s" % (variant, entry["boot_id"])] = dict(
                Counter(sample["category"] for sample in entry["samples"])
            )

    pattern = _dual_order_pattern(qs_category, sq_category)
    return {
        "conclusion": conclusion,
        # The observation, beside the conclusion and never instead of it. Both
        # variants preferring QREAD is a thing that happened; "QREAD is visible
        # first" is a thing that would need the control below to be true.
        "dual_order_pattern": pattern,
        "required_followup": FRESH_CONTROL if conclusion == CONTROL_REQUIRED else None,
        "qs_category": qs_category,
        "sq_category": sq_category,
        "q_floor": q_structure,
        "dual_structure": dual_structure,
        "qualitative_disagreement_with_q": disagreement,
        "per_boot_categories": per_boot,
        "convergence_tail": {
            "iterations_seen": sorted(
                {sample.get("convergence_iterations") for entry in cells
                 for sample in entry["samples"]}
            ),
            "timeouts": sum(
                sample.get("convergence_timeout", 0) for entry in cells
                for sample in entry["samples"]
            ),
        },
        "control_required": CONTROL_TEXT,
        # The three truths, and the two claims this analyzer structurally cannot
        # make, stated rather than left to the reader's trust.
        "perturbed_by_convergence_tail": True,
        "not_comparable_to_v13": True,
        "not_performance_metric": True,
        "cross_variant_cycle_comparison": False,
        "physical_simultaneity_claimed": False,
    }
