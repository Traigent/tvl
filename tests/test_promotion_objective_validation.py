"""Regression tests for issue #16: a typo'd or missing objective ``direction``
must be rejected, not silently coerced to ``maximize`` (which can invert the
promotion verdict on the un-schema-gated ``epsilon_pareto_gate`` entrypoint).
"""
from __future__ import annotations

import pytest

from tvl.errors import ParseError
from tvl.promotion import SCIPY_AVAILABLE, epsilon_pareto_gate


def _policy() -> dict:
    return {"alpha": 0.05, "min_effect": {"quality": 0.02}, "adjust": "none"}


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_typo_direction_is_rejected_not_coerced() -> None:
    """A candidate that is clearly WORSE on a 'minimize'-typo'd objective must
    not be silently promoted because the typo was coerced to 'maximize'."""
    incumbent = {"objective_values": {"quality": {"mean": 0.20, "std": 0.02, "n": 50}}}
    candidate = {"objective_values": {"quality": {"mean": 0.90, "std": 0.02, "n": 50}}}
    objectives = [{"name": "quality", "direction": "maximise"}]  # typo, not "maximize"

    with pytest.raises(ParseError):
        epsilon_pareto_gate(incumbent, candidate, _policy(), objectives)


def test_missing_direction_is_rejected_not_defaulted() -> None:
    objectives = [{"name": "quality"}]  # no "direction" key at all

    with pytest.raises(ParseError):
        epsilon_pareto_gate({}, {}, _policy(), objectives)


def test_missing_name_is_rejected_not_defaulted() -> None:
    objectives = [{"direction": "maximize"}]  # no "name" key at all

    with pytest.raises(ParseError):
        epsilon_pareto_gate({}, {}, _policy(), objectives)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_valid_objective_still_parses() -> None:
    objectives = [{"name": "quality", "direction": "minimize"}]
    incumbent = {"objective_values": {"quality": {"mean": 0.90, "std": 0.02, "n": 50}}}
    candidate = {"objective_values": {"quality": {"mean": 0.70, "std": 0.02, "n": 50}}}

    decision, evidence = epsilon_pareto_gate(incumbent, candidate, _policy(), objectives)

    assert decision in {"Promote", "NoDecision", "Reject"}
    assert "quality" in evidence["per_objective"]


# --- Traigent/tvl#161: min_effect is required, never defaulted to 0.0 --------

_OBJECTIVES = [
    {"name": "quality", "direction": "maximize"},
    {"name": "cost", "direction": "minimize"},
]


@pytest.mark.parametrize(
    "min_effect",
    [
        {},  # empty
        {"quality": 0.02},  # one objective missing
        {"Quality": 0.02, "cost": 0.0},  # wrong case
        {"qualty": 0.02, "cost": 0.0},  # misspelt
        None,  # null mapping
        [],  # wrong type
    ],
)
def test_missing_min_effect_is_rejected_not_defaulted(min_effect) -> None:
    policy = {"alpha": 0.05, "adjust": "none", "min_effect": min_effect}

    with pytest.raises(ParseError):
        epsilon_pareto_gate({}, {}, policy, _OBJECTIVES)


def test_absent_min_effect_key_is_rejected() -> None:
    with pytest.raises(ParseError, match="not treated as 0.0"):
        epsilon_pareto_gate({}, {}, {"alpha": 0.05}, _OBJECTIVES)


@pytest.mark.parametrize("value", [None, "0.1", True, -0.01, float("nan"), float("inf")])
def test_invalid_min_effect_value_is_rejected(value) -> None:
    policy = {"min_effect": {"quality": value, "cost": 0.0}}

    with pytest.raises(ParseError):
        epsilon_pareto_gate({}, {}, policy, _OBJECTIVES)


def test_error_names_the_missing_objective() -> None:
    with pytest.raises(ParseError) as exc:
        epsilon_pareto_gate({}, {}, {"min_effect": {"quality": 0.02}}, _OBJECTIVES)

    assert "['cost']" in str(exc.value)


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_explicit_zero_min_effect_is_allowed() -> None:
    incumbent = {"objective_values": {"quality": {"mean": 0.70, "std": 0.02, "n": 50}}}
    candidate = {"objective_values": {"quality": {"mean": 0.90, "std": 0.02, "n": 50}}}
    objectives = [{"name": "quality", "direction": "maximize"}]

    decision, evidence = epsilon_pareto_gate(
        incumbent, candidate, {"min_effect": {"quality": 0}, "adjust": "none"}, objectives
    )

    assert decision == "Promote"
    assert evidence["per_objective"]["quality"]["epsilon"] == 0.0


def test_banded_objective_does_not_need_min_effect() -> None:
    objectives = [
        {"name": "quality", "direction": "maximize"},
        {"name": "length", "band": {"target": {"low": 1, "high": 2}, "alpha": 0.05}},
    ]
    # Only the standard objective is required; no ParseError for the band.
    from tvl.promotion import _parse_objectives

    specs = _parse_objectives(objectives, {"quality": 0.02})

    assert [s.name for s in specs] == ["quality", "length"]
