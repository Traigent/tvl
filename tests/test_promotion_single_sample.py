"""Regression: sample-based objective test crashed on a single-sample arm.

`_test_from_samples` reached the Welch-Satterthwaite df computation
`(var/n)**2 / (n - 1)` with n == 1 whenever exactly one arm had a single
sample and the other had non-zero variance, raising ZeroDivisionError
(promotion.py). Its aggregated-stats sibling `_test_from_stats` already
guarded the identical degenerate input with `if n_inc < 2 or n_cand < 2:
return ... verdict='inconclusive'`. A single sample is schema-valid
(tvl-measurement.schema.json: samples minItems 1, n minimum 1) and passes
the readiness pre-gate, so the crash was reachable from valid input.

See Traigent/tvl#32.
"""

from __future__ import annotations

from tvl.promotion import ObjectiveSpec, _test_from_samples, _test_from_stats


def _spec() -> ObjectiveSpec:
    return ObjectiveSpec(
        name="quality", direction="maximize", epsilon=0.02, band=None, metric_ref=None
    )


def test_single_sample_incumbent_degrades_to_inconclusive():
    """n=1 vs n>=2 (non-zero variance) must not raise; it degrades gracefully."""
    result = _test_from_samples(_spec(), [0.90], [0.80, 0.85, 0.88], paired=False)
    assert result.verdict == "inconclusive"
    assert result.df is None
    assert result.p_value_noninf == 1.0
    assert result.p_value_super == 1.0


def test_single_sample_matches_aggregated_stats_sibling():
    """Identical n=1 evidence yields the same verdict from both code paths."""
    from_samples = _test_from_samples(_spec(), [0.90], [0.80, 0.85, 0.88], paired=False)
    from_stats = _test_from_stats(
        _spec(), {"mean": 0.90, "std": 0.0, "n": 1}, {"mean": 0.84, "std": 0.04, "n": 3}
    )
    assert from_samples.verdict == from_stats.verdict == "inconclusive"


def test_multi_sample_still_runs_welch():
    """The guard must not disturb the normal (n>=2 on both arms) path."""
    result = _test_from_samples(
        _spec(), [0.90, 0.91, 0.92], [0.80, 0.85, 0.88], paired=False
    )
    assert result.df is not None
    assert result.df > 0


# --- code-review-8 fixes -----------------------------------------------------

import math

import pytest

from tvl.promotion import SCIPY_AVAILABLE, _test_banded_objective, epsilon_pareto_gate

_BAND = {"target": [0.0, 1.0], "alpha": 0.05}


def _band_spec(target=(0.0, 1.0)) -> ObjectiveSpec:
    return ObjectiveSpec(
        name="b", direction="maximize", epsilon=0.0, band={"target": list(target), "alpha": 0.05}
    )


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
@pytest.mark.parametrize("bad_std", [math.nan, -1.0, -math.inf, math.inf])
def test_invalid_band_std_never_promotes(bad_std):
    objectives = [
        {"name": "quality", "direction": "maximize"},
        {"name": "b", "band": _BAND},
    ]
    policy = {"alpha": 0.05, "min_effect": {"quality": 0.0}, "adjust": "none"}
    inc = {"objective_values": {"quality": {"mean": 0.5, "std": 0.01, "n": 100}}}
    cand = {
        "objective_values": {
            "quality": {"mean": 0.9, "std": 0.01, "n": 100},
            "b": {"mean": 0.5, "std": bad_std, "n": 10},
        }
    }
    decision, evidence = epsilon_pareto_gate(inc, cand, policy, objectives)
    assert decision != "Promote"
    assert evidence["per_objective"]["b"]["verdict"] == "inconclusive"


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_zero_std_interior_mean_is_still_in_band():
    r = _test_banded_objective(_band_spec(), {"mean": 0.5, "std": 0.0, "n": 10}, 0.05)
    assert r.verdict == "in_band"


@pytest.mark.parametrize("n", [-1, 2.5, True, math.nan])
def test_invalid_band_n_is_inconclusive(n):
    r = _test_banded_objective(_band_spec(), {"mean": 0.5, "std": 0.1, "n": n}, 0.05)
    assert r.verdict == "inconclusive"


def test_singleton_samples_with_explicit_n_use_the_sample():
    spec = _band_spec((0.4, 0.6))
    # Definition 9.6 / section 9.5: on-target point estimate, insufficient evidence.
    assert _test_banded_objective(spec, {"samples": [0.5], "n": 1}, 0.05).verdict == "inconclusive"
    # An off-band lone sample is still a hard rejection.
    assert _test_banded_objective(spec, {"samples": [0.9], "n": 1}, 0.05).verdict == "out_of_band"
