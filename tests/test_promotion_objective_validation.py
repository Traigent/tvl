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
