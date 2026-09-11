"""Descriptive statistics shared by the V9, V10 and V11A interval reports.

Quartiles include the median in both halves for odd-length samples. CV uses
sample standard deviation; a zero mean is represented by None.
"""

from __future__ import annotations

import statistics


def _median(values: list[int]) -> float:
    return float(statistics.median(values))


def _inclusive_quartiles(values: list[int]) -> tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        one = float(ordered[0])
        return one, one
    mid = n // 2
    if n % 2:
        lower = ordered[: mid + 1]
        upper = ordered[mid:]
    else:
        lower = ordered[:mid]
        upper = ordered[mid:]
    return float(statistics.median(lower)), float(statistics.median(upper))


def _mad(values: list[int]) -> float:
    med = statistics.median(values)
    return float(statistics.median([abs(v - med) for v in values]))


def _cv(values: list[int]) -> float | None:
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    if len(values) == 1:
        return 0.0
    return float(statistics.stdev(values) / mean)


def series_stats(values: list[int]) -> dict:
    q1, q3 = _inclusive_quartiles(values)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "median": _median(values),
        "mad": _mad(values),
        "q1_inclusive": q1,
        "q3_inclusive": q3,
        "iqr_inclusive": q3 - q1,
        "cv": _cv(values),
    }
