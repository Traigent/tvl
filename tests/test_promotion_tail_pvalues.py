"""Regression: one-sided p-values computed as ``1 - cdf(t)`` lost the upper tail.

Once ``scipy.stats.t.cdf`` rounds to 1.0 the subtraction is exactly 0.0 and the
clip reports 1e-300, although the true tail probability is a finite number far
above it (for example 2e-21). The survival function ``t.sf`` returns it. Spec
§7.3 keeps the 1e-300 clip for genuinely underflowing values.

See Traigent/tvl#263.
"""

from __future__ import annotations

import pytest
from scipy import stats
from tvl.promotion import (
    ObjectiveSpec,
    _test_banded_objective,
    _test_from_samples,
    _test_objective,
)


def _spec(epsilon: float = 0.0, band=None) -> ObjectiveSpec:
    return ObjectiveSpec(name="a", direction="maximize", epsilon=epsilon, band=band)


def test_aggregated_stats_strong_effect_reports_the_tail_value():
    r = _test_objective(_spec(), {"mean": 0.0, "std": 1, "n": 100}, {"mean": 1.5, "std": 1, "n": 100})

    expected = stats.t.sf(r.t_statistic, r.df)
    assert expected > 1e-25
    assert r.p_value_noninf == pytest.approx(expected, rel=1e-9, abs=0.0)
    assert r.p_value_super == pytest.approx(expected, rel=1e-9, abs=0.0)


def test_aggregated_stats_moderate_tail_is_accurate():
    """Below ~1e-11, 1 - cdf already carried 1e-5 relative error."""
    r = _test_objective(_spec(), {"mean": 0.0, "std": 1, "n": 100}, {"mean": 1.0, "std": 1, "n": 100})

    assert r.p_value_noninf == pytest.approx(stats.t.sf(r.t_statistic, r.df), rel=1e-12, abs=0.0)


def test_samples_strong_effect_reports_the_tail_value():
    inc = [0.0, 0.1, -0.1, 0.05, -0.05, 0.0, 0.02, -0.02]
    cand = [x + 3.0 for x in inc]
    r = _test_from_samples(_spec(), inc, cand, paired=False)

    expected = stats.t.sf(r.t_statistic, r.df)
    assert 1e-300 < expected < 1e-16
    assert r.p_value_noninf == pytest.approx(expected, rel=1e-9, abs=0.0)


def test_paired_samples_strong_effect_reports_the_tail_value():
    inc = [0.0, 0.1, -0.1, 0.05, -0.05, 0.0, 0.02, -0.02, 0.03, 0.01]
    cand = [x + 1.0 + 0.001 * i for i, x in enumerate(inc)]
    r = _test_from_samples(_spec(), inc, cand, paired=True)

    expected = stats.t.sf(r.t_statistic, r.df)
    assert 1e-300 < expected < 1e-16
    assert r.p_value_noninf == pytest.approx(expected, rel=1e-9, abs=0.0)


def test_tost_reports_the_tail_value_for_the_spec_example():
    """spec/promotion-gate-io.md §2: mean 100, std 2.5, n 50, band [95, 105]."""
    r = _test_banded_objective(
        _spec(band={"target": [95, 105], "test": "TOST", "alpha": 0.05}),
        {"mean": 100.0, "std": 2.5, "n": 50},
        0.05,
    )

    se = 2.5 / 50 ** 0.5
    expected = stats.t.sf(5 / se, 49)
    assert expected > 1e-20
    assert r.p_value_lower == pytest.approx(expected, rel=1e-9, abs=0.0)
    assert r.p_value_upper == pytest.approx(expected, rel=1e-9, abs=0.0)
    assert r.verdict == "in_band"


def test_underflowing_tail_still_clips_to_1e_300():
    r = _test_objective(_spec(), {"mean": 0.0, "std": 1, "n": 1000}, {"mean": 100.0, "std": 1, "n": 1000})

    assert r.p_value_noninf == 1e-300
