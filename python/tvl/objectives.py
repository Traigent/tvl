from __future__ import annotations

from typing import Iterable, Tuple


def mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / max(1, len(xs))


def quantile(xs: Iterable[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = max(0, min(len(xs) - 1, int(q * (len(xs) - 1))))
    return xs[k]


def distance_to_band(x: float, low: float, high: float) -> float:
    if x < low:
        return low - x
    if x > high:
        return x - high
    return 0.0

