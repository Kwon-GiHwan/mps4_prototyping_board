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
            elif category not in CATEGORIES:
                raise AnalysisError("cell %r carries category %r" % (key, category))

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


def _stable_category(cells) -> str | None:
    """The one category a variant's cells agree on, or None."""

    categories = {sample["category"] for entry in cells for sample in entry["samples"]}
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

    return {
        "conclusion": conclusion,
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
