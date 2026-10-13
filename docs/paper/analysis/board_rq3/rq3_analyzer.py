"""Preregistered RQ3 analysis. Every prohibition is a rejection, not a convention."""
import math

WORKLOADS = ["rnnoise_INT8", "kws_micronet_m", "ad_medium_int8", "vww4_128_128_INT8",
             "yolo-fastest_192_face_v4", "mobilenet_v2_1.0_224_INT8",
             "wav2letter_pruned_int8"]
FVP_CELL = ("SSE-320", "ethos-u85", 1024)
NOT_EVALUABLE = ["SRAM_RD_DATA_BEAT_RECEIVED", "SRAM_WR_DATA_BEAT_WRITTEN",
                 "EXT_RD_DATA_BEAT_RECEIVED", "EXT_WR_DATA_BEAT_WRITTEN"]


class RQ3Rejection(Exception):
    """A preregistered rule was violated. Never downgraded to a warning."""


def board_canonical(rec):
    """median(B1,B2,B3). All three must be present and valid."""
    if rec.get("source") == "qualification":
        raise RQ3Rejection("qualification sample is not analysis input: %s" % rec.get("workload"))
    trip = [rec.get("B1"), rec.get("B2"), rec.get("B3")]
    if any(t is None for t in trip):
        raise RQ3Rejection("incomplete board triplet for %s" % rec.get("workload"))
    for k, t in zip(("B1", "B2", "B3"), trip):
        if not t.get("valid", True):
            raise RQ3Rejection("%s %s is not a valid formal observation" % (rec.get("workload"), k))
    return sorted(t["total"] for t in trip)[1]


def assert_board_canonical_is_median(rec, claimed):
    if claimed != board_canonical(rec):
        raise RQ3Rejection("canonical board cost is not median(B1,B2,B3) for %s"
                           % rec.get("workload"))
    return True


def fvp_canonical(rec):
    """M1, only after M1 == M2 == M3, and only from the preregistered cell."""
    cell = (rec.get("platform"), rec.get("npu"), rec.get("mac_config"))
    if cell != FVP_CELL:
        raise RQ3Rejection("FVP cell %r is not the preregistered %r" % (cell, FVP_CELL))
    if not rec.get("M1_eq_M2_eq_M3"):
        raise RQ3Rejection("FVP determinism precondition not met for %s" % rec.get("workload"))
    return rec["canonical_cycles"]


def assert_full_workload_set(names):
    if sorted(names) != sorted(WORKLOADS):
        raise RQ3Rejection("workload set reduced or altered: %r" % sorted(names))
    return True


def assert_paired(fvp_names, board_names):
    """Ranking joined on a mismatched order yields a plausible, wrong result."""
    if list(fvp_names) != list(board_names):
        raise RQ3Rejection("workload pairing mismatch: %r vs %r"
                           % (list(fvp_names), list(board_names)))
    return True


def geomean(values, domain):
    if not values or any(v <= 0 for v in values):
        raise RQ3Rejection("geomean requires positive values (%s)" % domain)
    return math.exp(sum(math.log(v) for v in values) / len(values))


def normalized_costs(totals_by_workload, domain):
    """Normalized within ONE domain. Mixing domains is rejected."""
    if domain not in ("FVP", "BOARD"):
        raise RQ3Rejection("normalization domain must be exactly one of FVP / BOARD")
    vals = [totals_by_workload[w] for w in WORKLOADS]
    g = geomean(vals, domain)
    return {w: totals_by_workload[w] / g for w in WORKLOADS}, g


def assert_not_combined_domain(domain_labels):
    if len(set(domain_labels)) > 1:
        raise RQ3Rejection("combined FVP+board geometric mean is prohibited")
    return True


def ranks(totals_by_workload):
    order = sorted(WORKLOADS, key=lambda w: totals_by_workload[w])
    return {w: i + 1 for i, w in enumerate(order)}


def spearman(a_rank, b_rank):
    n = len(WORKLOADS)
    d2 = sum((a_rank[w] - b_rank[w]) ** 2 for w in WORKLOADS)
    return 1 - (6 * d2) / (n * (n * n - 1))


def rank_inversions(a_rank, b_rank):
    """Explicitly named pairs whose relative order differs between domains."""
    out = []
    for i in range(len(WORKLOADS)):
        for j in range(i + 1, len(WORKLOADS)):
            x, y = WORKLOADS[i], WORKLOADS[j]
            if (a_rank[x] < a_rank[y]) != (b_rank[x] < b_rank[y]):
                first_fvp = x if a_rank[x] < a_rank[y] else y
                first_board = x if b_rank[x] < b_rank[y] else y
                out.append({"pair": [x, y],
                            "fvp_first": first_fvp, "board_first": first_board})
    return out


# --- prohibitions, enforced -------------------------------------------------

def absolute_difference(*_a, **_k):
    raise RQ3Rejection("absolute FVP-board difference is prohibited")


def absolute_ratio(*_a, **_k):
    raise RQ3Rejection("absolute FVP-board ratio is prohibited")


def percent_error(*_a, **_k):
    raise RQ3Rejection("percent error against FVP is prohibited")


def assert_no_shape_distance(metric_name):
    raise RQ3Rejection("aggregate shape-distance metric %r was not preregistered"
                       % metric_name)


def assert_no_new_repeatability_metric(name):
    raise RQ3Rejection("repeatability metric %r was not preregistered; "
                       "raw triplet and median only" % name)


def assert_pmu_cross_target(event):
    if event in NOT_EVALUABLE:
        raise RQ3Rejection("%s cross-target comparison is NOT_EVALUABLE "
                           "(absent from frozen FVP formal records)" % event)
    raise RQ3Rejection("quantitative PMU cross-target comparison was not preregistered")
