#!/usr/bin/env python3
"""The ten gates of the P0-E2 two-workload extension, as refusals.

Contract: docs/superpowers/plans/2026-09-16-p0e2-two-workload-extension-plan.md
section 3. Each gate here is the executable form of one row of that table, and
it refuses by name so a negative fixture can assert which rule it tripped.

Two of the ten deserve a note on why they are shaped the way they are.

RULE_P0E2_SUM_COHERENT: the contract says the per-op sum agrees with the clean
whole "within the instrumentation residual constant". There is no such
constant. Measured over the fifteen frozen cells of the September campaign the
residual runs from -2873 to +2272 cycles (-2.14% to +1.96%), because the IRQ
handler loses the cycles between its PMU snapshot and its PMU reset once per
service window, so the residual grows with the number of windows. The bound
below is therefore an envelope derived from those fifteen cells and recorded
before any P0-E2 measurement existed, not a constant read out of the contract.

RULE_P0E2_IDENTITY_JOIN: the contract forbids joining the two sides of a
binding pair by row order. Row order is exactly what a careless join would use,
and it would silently succeed whenever the two sides happened to have the same
length. So the gate refuses a join key that is not the declared identity tuple,
and refuses positionally-paired input even when the lengths agree.
"""

from __future__ import annotations

RULE_P0E2_MODEL_SHA = "RULE_P0E2_MODEL_SHA"
RULE_P0E2_TOOLCHAIN = "RULE_P0E2_TOOLCHAIN"
RULE_P0E2_PATCH_IDENTITY = "RULE_P0E2_PATCH_IDENTITY"
RULE_P0E2_IRQ_VALID = "RULE_P0E2_IRQ_VALID"
RULE_P0E2_LAYER_CAP = "RULE_P0E2_LAYER_CAP"
RULE_P0E2_REPS_EXACT = "RULE_P0E2_REPS_EXACT"
RULE_P0E2_SUM_COHERENT = "RULE_P0E2_SUM_COHERENT"
RULE_P0E2_OUTPUT_CRC = "RULE_P0E2_OUTPUT_CRC"
RULE_P0E2_IDENTITY_JOIN = "RULE_P0E2_IDENTITY_JOIN"
RULE_P0E2_RESTORE = "RULE_P0E2_RESTORE"

RULES = (
    "RULE_P0E2_MODEL_SHA",
    "RULE_P0E2_TOOLCHAIN",
    "RULE_P0E2_PATCH_IDENTITY",
    "RULE_P0E2_IRQ_VALID",
    "RULE_P0E2_LAYER_CAP",
    "RULE_P0E2_REPS_EXACT",
    "RULE_P0E2_SUM_COHERENT",
    "RULE_P0E2_OUTPUT_CRC",
    "RULE_P0E2_IDENTITY_JOIN",
    "RULE_P0E2_RESTORE",
)

# Section 1 of the contract, copied rather than referred to.
FROZEN_MODEL_SHA = {
    "wav2letter_pruned_int8":
        "e0814a0e586f2f2881f7fe96e6bc0b8e4cfecc8d64ced56d8f7ca85b9b7ab257",
    "mobilenet_v2_1.0_224_INT8":
        "bd8d56b80557a5fca7acf14f61e5339285c02810f7d7afa714b9763fc4b86e95",
}

# U85_BASELINE_BINDING.md, "Frozen sweep identity".
SEPTEMBER_TOOLCHAIN = {
    "vela": "5.0.0",
    "mlek": "26.03-8-gb2c0bb2",
    "core_driver": "25.11",
    "fvp": "11.27.25",
}

# The September campaign's tools, by digest. Authority: the EVIDENCE.sha256
# manifests of the two frozen evidence trees.
SEPTEMBER_PATCH_SHA = {
    "insert_irq.py":
        "2a6a02a75687c1ee1573af524c68e00fdabacfff08b87d91e183f30d89661375",
    "patch_app.py":
        "e337c388cc9afc2d8051bff975479be220d03e7f6643c313f175bcb5ca26de09",
    "patch_driver_u85_v3.py":
        "c875f2b5ad906d3243d267cd0f7309c9eadc6e34e9949a9a143e261cd99441a3",
}

# patch_driver_u85_v3.py: PLPROF_MAX_LAYERS. The contract cites 256, which is
# the constant of the exploration tool /workspace/per-layer-profiling/
# patch-driver.py; the campaign path this extension is bound to uses 512. Both
# are checked, and the tighter one is the one that refuses.
PROFILING_MAX_LAYERS = 512
CONTRACT_CITED_MAX_LAYERS = 256

# The metric vector that must be identical across the three processes. Widening
# this tuple weakens the gate, so it is written here and asserted by a test.
REPLICATE_FIELDS = ("total", "active", "idle", "crc", "plprof", "pl_count")

# The declared join key. Row position is not in it and may not be added.
IDENTITY_JOIN_KEY = ("workload", "op_index", "op_type", "ifm_shape", "ofm_shape")

# Envelope over the fifteen frozen September cells; see the module docstring.
# Both bounds must hold: a large model may not hide a large absolute residual
# behind a small ratio, and a small one may not hide a large ratio behind a
# small absolute count.
SUM_COHERENCE_MAX_ABS_CYCLES = 3000
SUM_COHERENCE_MAX_RATIO = 0.030


class GateError(RuntimeError):
    """A P0-E2 result this campaign will not record."""


def fail_rule(rule: str, message: str) -> GateError:
    return GateError("[%s] %s" % (rule, message))


def refusal_rule(error) -> str | None:
    text = ("%s" % error).strip()
    if not text.startswith("[") or "]" not in text:
        return None
    return text[1 : text.index("]")]


def check_model_sha(observed):
    """observed: {model_name: sha256}. Every frozen model must be present and
    equal; an unknown model name is a refusal too, because a cell whose model
    is not in the closed set has no frozen value to be checked against."""
    for model, frozen in sorted(FROZEN_MODEL_SHA.items()):
        if model not in observed:
            raise fail_rule(RULE_P0E2_MODEL_SHA, "model absent: %s" % model)
        if observed[model] != frozen:
            raise fail_rule(
                RULE_P0E2_MODEL_SHA,
                "%s sha256 %s != frozen %s" % (model, observed[model], frozen))
    for model in sorted(observed):
        if model not in FROZEN_MODEL_SHA:
            raise fail_rule(RULE_P0E2_MODEL_SHA,
                            "model outside the closed set: %s" % model)
    return True


def check_toolchain(observed):
    """observed: {component: identifier} for the four September components."""
    for name, frozen in sorted(SEPTEMBER_TOOLCHAIN.items()):
        if name not in observed:
            raise fail_rule(RULE_P0E2_TOOLCHAIN, "component absent: %s" % name)
        if observed[name] != frozen:
            raise fail_rule(
                RULE_P0E2_TOOLCHAIN,
                "%s is %s, September campaign was %s"
                % (name, observed[name], frozen))
    return True


def check_patch_identity(observed):
    """observed: {tool filename: sha256} of the patch tools as actually run."""
    for name, frozen in sorted(SEPTEMBER_PATCH_SHA.items()):
        if name not in observed:
            raise fail_rule(RULE_P0E2_PATCH_IDENTITY, "tool absent: %s" % name)
        if observed[name] != frozen:
            raise fail_rule(
                RULE_P0E2_PATCH_IDENTITY,
                "%s sha256 %s != September %s"
                % (name, observed[name], frozen))
    return True


def check_irq_valid(cell):
    """The command stream accepted the inserted IRQs and the target serviced
    exactly them.

    cell carries: irq_count (inserted by insert_irq.py), stream_irq_count
    (NPU_OP_IRQ opcodes decoded back out of the written command stream), and
    serviced_launches (launches accounted for by the decoded history windows,
    the tail window included). A run that produced no PLPROF records at all is
    a refusal, not an empty pass.
    """
    inserted = cell.get("irq_count")
    in_stream = cell.get("stream_irq_count")
    serviced = cell.get("serviced_launches")
    if inserted is None or in_stream is None or serviced is None:
        raise fail_rule(RULE_P0E2_IRQ_VALID,
                        "%s: incomplete IRQ evidence" % cell.get("cell"))
    if inserted <= 0:
        raise fail_rule(RULE_P0E2_IRQ_VALID,
                        "%s: no IRQ inserted" % cell.get("cell"))
    if in_stream != inserted:
        raise fail_rule(
            RULE_P0E2_IRQ_VALID,
            "%s: command stream carries %d NPU_OP_IRQ, %d were inserted"
            % (cell.get("cell"), in_stream, inserted))
    if serviced != inserted:
        raise fail_rule(
            RULE_P0E2_IRQ_VALID,
            "%s: %d launches serviced, %d IRQ inserted"
            % (cell.get("cell"), serviced, inserted))
    return True


def check_layer_cap(cell):
    """Operation count within the profiling buffer. Splitting a cell into
    batches to get under the cap is prohibited by contract section 5, so a cell
    that declares a batch split is refused here rather than measured."""
    n = cell.get("irq_count")
    if n is None:
        raise fail_rule(RULE_P0E2_LAYER_CAP,
                        "%s: no operation count" % cell.get("cell"))
    if cell.get("batches", 1) != 1:
        raise fail_rule(
            RULE_P0E2_LAYER_CAP,
            "%s: split into %d batches; the cap is a STOP, not a split"
            % (cell.get("cell"), cell.get("batches")))
    cap = min(PROFILING_MAX_LAYERS, CONTRACT_CITED_MAX_LAYERS)
    if n > cap:
        raise fail_rule(
            RULE_P0E2_LAYER_CAP,
            "%s: %d operations exceeds the cap %d" % (cell.get("cell"), n, cap))
    return True


def check_reps_exact(runs):
    """The three processes' whole metric vectors, exactly equal. No mean, no
    tolerance: a disagreement is a STOP. A field missing from a run is a
    refusal, so that dropping a field cannot pass as agreement."""
    if len(runs) != 3:
        raise fail_rule(RULE_P0E2_REPS_EXACT,
                        "%d runs, the contract registers 3" % len(runs))
    for field in REPLICATE_FIELDS:
        seen = []
        for index, run in enumerate(runs):
            if field not in run:
                raise fail_rule(RULE_P0E2_REPS_EXACT,
                                "run %d has no %s" % (index + 1, field))
            seen.append(run[field])
        if not (seen[0] == seen[1] == seen[2]):
            raise fail_rule(
                RULE_P0E2_REPS_EXACT,
                "%s differs across the three processes: %r" % (field, seen))
    return True


def check_sum_coherent(cell):
    """Per-unit cycles sum to the clean whole within the September envelope."""
    unit_sum = cell.get("unit_ccnt_sum")
    clean_total = cell.get("clean_total")
    if unit_sum is None or clean_total is None:
        raise fail_rule(RULE_P0E2_SUM_COHERENT,
                        "%s: incomplete sum evidence" % cell.get("cell"))
    if clean_total <= 0:
        raise fail_rule(RULE_P0E2_SUM_COHERENT,
                        "%s: clean total %r" % (cell.get("cell"), clean_total))
    residual = unit_sum - clean_total
    if abs(residual) > SUM_COHERENCE_MAX_ABS_CYCLES:
        raise fail_rule(
            RULE_P0E2_SUM_COHERENT,
            "%s: residual %d cycles exceeds %d"
            % (cell.get("cell"), residual, SUM_COHERENCE_MAX_ABS_CYCLES))
    ratio = abs(residual) / clean_total
    if ratio > SUM_COHERENCE_MAX_RATIO:
        raise fail_rule(
            RULE_P0E2_SUM_COHERENT,
            "%s: residual ratio %.4f exceeds %.4f"
            % (cell.get("cell"), ratio, SUM_COHERENCE_MAX_RATIO))
    return True


def check_output_crc(cell):
    """The instrumented image computed what the clean image computed. An empty
    CRC on either side is a refusal: two absent outputs are not a match."""
    clean = cell.get("clean_crc")
    prof = cell.get("prof_crc")
    if not clean or not prof:
        raise fail_rule(RULE_P0E2_OUTPUT_CRC,
                        "%s: missing output CRC" % cell.get("cell"))
    if clean != prof:
        raise fail_rule(
            RULE_P0E2_OUTPUT_CRC,
            "%s: clean %s != profiled %s" % (cell.get("cell"), clean, prof))
    return True


def check_identity_join(join):
    """The 256/512 join is by declared identity, never by row order.

    join carries: key (the tuple actually used), left and right (lists of
    identity dicts). The gate refuses a key that is not IDENTITY_JOIN_KEY, an
    identity that does not carry every key field, and any left/right pair whose
    identities do not correspond as sets -- which is what a positional join
    would let through whenever the two sides happen to be the same length.
    """
    key = tuple(join.get("key", ()))
    if key != IDENTITY_JOIN_KEY:
        raise fail_rule(
            RULE_P0E2_IDENTITY_JOIN,
            "join key %r is not the declared identity %r"
            % (key, IDENTITY_JOIN_KEY))
    left, right = join.get("left"), join.get("right")
    if left is None or right is None:
        raise fail_rule(RULE_P0E2_IDENTITY_JOIN, "join side absent")

    def identities(rows, side):
        out = []
        for index, row in enumerate(rows):
            missing = [f for f in IDENTITY_JOIN_KEY if f not in row]
            if missing:
                raise fail_rule(
                    RULE_P0E2_IDENTITY_JOIN,
                    "%s row %d lacks %s" % (side, index, ",".join(missing)))
            out.append(tuple(row[f] for f in IDENTITY_JOIN_KEY))
        return out

    li, ri = identities(left, "left"), identities(right, "right")
    if len(set(li)) != len(li):
        raise fail_rule(RULE_P0E2_IDENTITY_JOIN,
                        "left identities are not unique")
    if len(set(ri)) != len(ri):
        raise fail_rule(RULE_P0E2_IDENTITY_JOIN,
                        "right identities are not unique")
    if set(li) != set(ri):
        only_left = sorted(set(li) - set(ri))
        only_right = sorted(set(ri) - set(li))
        raise fail_rule(
            RULE_P0E2_IDENTITY_JOIN,
            "identity sets differ: %d only-256, %d only-512 (first: %r %r)"
            % (len(only_left), len(only_right),
               only_left[:1], only_right[:1]))
    return True


def check_restore(prestate, poststate):
    """Every patched file is back, by digest. A file that disappeared between
    the two states is a refusal, and so is one that appeared: a leftover patched
    copy is not a restored tree."""
    for path in sorted(prestate):
        if path not in poststate:
            raise fail_rule(RULE_P0E2_RESTORE, "absent after restore: %s" % path)
        if poststate[path] != prestate[path]:
            raise fail_rule(
                RULE_P0E2_RESTORE,
                "%s is %s, pre-state was %s"
                % (path, poststate[path], prestate[path]))
    for path in sorted(poststate):
        if path not in prestate:
            raise fail_rule(RULE_P0E2_RESTORE,
                            "appeared after restore: %s" % path)
    return True
