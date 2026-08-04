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
