"""Generic exact binomial tails, without a runtime verdict procedure."""
from fractions import Fraction
from functools import cache
from math import comb
from typing import List, Tuple

@cache
def binomial_cdf_exact(n: int, p: Fraction) -> Tuple[Fraction, ...]:
    """Exact common-denominator binomial cumulative sums T^-(n, p, j) for j = 0..n."""
    if n < 0:
        raise ValueError("n must be >= 0")
    a, b = p.numerator, p.denominator
    denominator = b**n
    cumulative = 0
    values: List[Fraction] = []
    for i in range(n + 1):
        cumulative += comb(n, i) * (a**i) * ((b - a) ** (n - i))
        values.append(Fraction(cumulative, denominator))
    return tuple(values)


def binomial_tails_exact(n: int, p: Fraction, k: int) -> Tuple[Fraction, Fraction]:
    """Return (T^+(n, p, k), T^-(n, p, k)) in exact rational arithmetic."""
    values = binomial_cdf_exact(n, p)
    upper = Fraction(1) - values[k - 1] if k > 0 else Fraction(1)
    lower = values[k] if k <= n else Fraction(1)
    return upper, lower
