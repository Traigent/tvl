from __future__ import annotations

import pytest

from tvl.measurement import prepare_measurement_bundle
from tvl.promotion import SCIPY_AVAILABLE, epsilon_pareto_gate


def _module() -> dict:
    return {
        "tvl": {"module": "corp.support.agent"},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02},
            "adjust": "none",
        },
    }


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_failure_to_establish_noninferiority_is_no_decision() -> None:
    incumbent = {"objective_values": {"quality": {"mean": 0.80, "std": 0.20, "n": 4}}}
    candidate = {"objective_values": {"quality": {"mean": 0.77, "std": 0.20, "n": 4}}}

    decision, evidence = epsilon_pareto_gate(
        incumbent,
        candidate,
        _module()["promotion_policy"],
        _module()["objectives"],
    )

    assert decision == "NoDecision"
    assert evidence["per_objective"]["quality"]["verdict"] == "inconclusive"


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_clear_regression_is_rejected() -> None:
    incumbent = {"objective_values": {"quality": {"mean": 0.90, "std": 0.02, "n": 50}}}
    candidate = {"objective_values": {"quality": {"mean": 0.70, "std": 0.02, "n": 50}}}

    decision, evidence = epsilon_pareto_gate(
        incumbent,
        candidate,
        _module()["promotion_policy"],
        _module()["objectives"],
    )

    assert decision == "Reject"
    assert evidence["per_objective"]["quality"]["p_value_inferior"] < 0.05


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_inferiority_family_uses_configured_adjustment() -> None:
    module = {
        "objectives": [
            {"name": "quality", "direction": "maximize"},
            {"name": "groundedness", "direction": "maximize"},
        ],
        "promotion_policy": {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02, "groundedness": 0.02},
            "adjust": "bonferroni",
        },
    }
    incumbent = {
        "objective_values": {
            "quality": {"mean": 0.80, "std": 0.10, "n": 100},
            "groundedness": {"mean": 0.80, "std": 0.10, "n": 100},
        }
    }
    candidate = {
        "objective_values": {
            "quality": {"mean": 0.755, "std": 0.10, "n": 100},
            "groundedness": {"mean": 0.80, "std": 0.10, "n": 100},
        }
    }

    decision, evidence = epsilon_pareto_gate(
        incumbent,
        candidate,
        module["promotion_policy"],
        module["objectives"],
    )

    quality = evidence["per_objective"]["quality"]
    assert quality["adjusted_p_inferior"] == pytest.approx(
        min(1.0, 2 * quality["p_value_inferior"])
    )
    assert quality["p_value_inferior"] < 0.05
    assert quality["adjusted_p_inferior"] >= 0.05
    assert decision == "NoDecision"


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_inferiority_family_uses_holm_adjustment() -> None:
    module = {
        "objectives": [
            {"name": "quality", "direction": "maximize"},
            {"name": "groundedness", "direction": "maximize"},
        ],
        "promotion_policy": {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02, "groundedness": 0.02},
            "adjust": "holm",
        },
    }
    incumbent = {
        "objective_values": {
            "quality": {"mean": 0.80, "std": 0.10, "n": 100},
            "groundedness": {"mean": 0.80, "std": 0.10, "n": 100},
        }
    }
    candidate = {
        "objective_values": {
            "quality": {"mean": 0.755, "std": 0.10, "n": 100},
            "groundedness": {"mean": 0.80, "std": 0.10, "n": 100},
        }
    }

    decision, evidence = epsilon_pareto_gate(
        incumbent,
        candidate,
        module["promotion_policy"],
        module["objectives"],
    )

    results = evidence["per_objective"]
    raw = [results[name]["p_value_inferior"] for name in ("quality", "groundedness")]
    adjusted = [results[name]["adjusted_p_inferior"] for name in ("quality", "groundedness")]
    smaller = min(range(2), key=raw.__getitem__)
    larger = 1 - smaller
    assert adjusted[smaller] == pytest.approx(min(1.0, 2 * raw[smaller]))
    assert adjusted[larger] == pytest.approx(max(adjusted[smaller], raw[larger]))
    assert evidence["summary"]["adjustment_method"] == "holm"
    assert decision == "NoDecision"


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_demonstrated_inferiority_precedes_inconclusive_band() -> None:
    module = {
        "objectives": [
            {"name": "quality", "direction": "maximize"},
            {"name": "length", "band": {"target": [95, 105], "alpha": 0.05}},
        ],
        "promotion_policy": {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02},
            "adjust": "none",
        },
    }
    incumbent = {
        "objective_values": {
            "quality": {"mean": 0.90, "std": 0.02, "n": 50},
        }
    }
    candidate = {
        "objective_values": {
            "quality": {"mean": 0.70, "std": 0.02, "n": 50},
            "length": {"mean": 100.0, "std": 8.0, "n": 5},
        }
    }

    decision, evidence = epsilon_pareto_gate(
        incumbent,
        candidate,
        module["promotion_policy"],
        module["objectives"],
    )

    assert evidence["per_objective"]["quality"]["verdict"] == "inferior"
    assert evidence["per_objective"]["length"]["verdict"] == "inconclusive"
    assert decision == "Reject"


def test_measurement_for_another_module_is_not_promotion_ready() -> None:
    measurement = {
        "module_id": "corp.other.agent",
        "objective_values": {"quality": {"mean": 0.82, "std": 0.04, "n": 100}},
    }

    _normalized, _warnings, readiness = prepare_measurement_bundle(_module(), measurement)

    assert "measurement_module_mismatch" in {issue["code"] for issue in readiness}


def test_strict_calibration_cannot_silently_become_promotion_ready() -> None:
    module = _module()
    module["promotion_policy"]["require_calibration"] = {"enabled": True}
    measurement = {
        "module_id": "corp.support.agent",
        "objective_values": {"quality": {"mean": 0.82, "std": 0.04, "n": 100}},
    }

    _normalized, _warnings, readiness = prepare_measurement_bundle(module, measurement)

    assert "calibration_evidence_unsupported" in {issue["code"] for issue in readiness}
