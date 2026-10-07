"""Attack the RQ3 rules with synthetic fixtures before the frozen evidence."""
import sys, copy
sys.path.insert(0, "/tmp/rq3")
import rq3_analyzer as A

R = {}
def ok(n, c): R[n] = bool(c)
def rejects(fn, *a, **k):
    try:
        fn(*a, **k); return False
    except A.RQ3Rejection:
        return True

W = A.WORKLOADS
def brec(w, t1, t2, t3, valid=True, source="formal"):
    return {"workload": w, "source": source,
            "B1": {"total": t1, "valid": valid},
            "B2": {"total": t2, "valid": valid},
            "B3": {"total": t3, "valid": valid}}
def frec(w, total, cell=A.FVP_CELL, det=True):
    return {"workload": w, "platform": cell[0], "npu": cell[1], "mac_config": cell[2],
            "M1_eq_M2_eq_M3": det, "canonical_cycles": total}

# positives
ok("P1_board_median_middle", A.board_canonical(brec("x", 10, 30, 20)) == 20)
ok("P2_fvp_canonical", A.fvp_canonical(frec("x", 123)) == 123)
ok("P3_full_set_accepted", A.assert_full_workload_set(W))
ok("P4_pairing_accepted", A.assert_paired(W, W))

# M1 qualification sample must not enter
ok("N1_qualification_sample_rejected",
   rejects(A.board_canonical, brec("x", 1, 2, 3, source="qualification")))
# missing triplet member
bad = brec("x", 1, 2, 3); bad["B2"] = None
ok("N2_incomplete_triplet_rejected", rejects(A.board_canonical, bad))
# invalid observation
ok("N2b_invalid_observation_rejected",
   rejects(A.board_canonical, brec("x", 1, 2, 3, valid=False)))
# canonical != median
ok("N3_non_median_canonical_rejected",
   rejects(A.assert_board_canonical_is_median, brec("x", 10, 30, 20), 30))
ok("N3b_median_accepted", A.assert_board_canonical_is_median(brec("x", 10, 30, 20), 20))
# wrong FVP cell
ok("N4_wrong_fvp_cell_rejected",
   rejects(A.fvp_canonical, frec("x", 1, cell=("SSE-300", "ethos-u55", 32))))
ok("N4b_fvp_determinism_required",
   rejects(A.fvp_canonical, frec("x", 1, det=False)))
# subset reduction
ok("N5_subset_rejected", rejects(A.assert_full_workload_set, W[:6]))
# combined domain geomean
ok("N6_combined_geomean_rejected",
   rejects(A.assert_not_combined_domain, ["FVP", "BOARD"]))
ok("N6b_single_domain_accepted", A.assert_not_combined_domain(["FVP", "FVP"]))
ok("N6c_bad_domain_label_rejected",
   rejects(A.normalized_costs, {w: 1.0 for w in W}, "MIXED"))
# absolute comparisons
ok("N7_absolute_difference_rejected", rejects(A.absolute_difference, 1, 2))
ok("N8_absolute_ratio_rejected", rejects(A.absolute_ratio, 1, 2))
ok("N8b_percent_error_rejected", rejects(A.percent_error, 1, 2))
ok("N8c_shape_distance_rejected", rejects(A.assert_no_shape_distance, "L2"))
# new repeatability metric
ok("N9_new_repeatability_metric_rejected",
   rejects(A.assert_no_new_repeatability_metric, "relative_spread"))
# SRAM/EXT cross-target
ok("N10_sram_ext_rejected", rejects(A.assert_pmu_cross_target, "SRAM_RD_DATA_BEAT_RECEIVED"))
ok("N10b_ext_rejected", rejects(A.assert_pmu_cross_target, "EXT_WR_DATA_BEAT_WRITTEN"))
ok("N10c_total_quantitative_rejected", rejects(A.assert_pmu_cross_target, "TOTAL"))
# wrong workload pairing - the silent one
shuffled = [W[1], W[0]] + W[2:]
ok("N11_wrong_pairing_rejected", rejects(A.assert_paired, W, shuffled))

# ranking sanity: a deliberate single swap must surface as exactly one inversion
base = {w: float(i + 1) for i, w in enumerate(W)}
swapped = dict(base); swapped[W[0]], swapped[W[1]] = base[W[1]], base[W[0]]
ra, rb = A.ranks(base), A.ranks(swapped)
inv = A.rank_inversions(ra, rb)
ok("P5_single_swap_one_inversion", len(inv) == 1)
ok("P5b_inversion_names_the_pair", set(inv[0]["pair"]) == {W[0], W[1]})
ok("P6_identical_rho_is_one", abs(A.spearman(ra, ra) - 1.0) < 1e-12)
# normalization is scale-invariant: doubling every value leaves shape unchanged
n1, _ = A.normalized_costs({w: base[w] for w in W}, "FVP")
n2, _ = A.normalized_costs({w: base[w] * 2 for w in W}, "FVP")
ok("P7_normalization_scale_invariant",
   all(abs(n1[w] - n2[w]) < 1e-12 for w in W))

for k in sorted(R): print("  %-46s %s" % (k, "PASS" if R[k] else "FAIL"))
print("ALL_PASS" if all(R.values()) else "SOME_FAILED")
