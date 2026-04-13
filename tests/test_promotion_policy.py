"""
Conformance tests for TVL promotion policy.

Tests promotion policy configuration including:
- Stochastic epsilon-Pareto dominance
- Benjamini-Hochberg adjustment
- Banded objectives with TOST
- Chance constraints with Clopper-Pearson

Per the formal specification in Appendix: Statistical Procedures for Promotion.
"""
from __future__ import annotations

import pathlib
import sys
import types
import unittest
from typing import Any, Dict, List

BASE = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = BASE / "python"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

package_name = "tvl"
package_path = PKG_ROOT / package_name

if package_name not in sys.modules:
    pkg = types.ModuleType(package_name)
    pkg.__path__ = [str(package_path)]
    sys.modules[package_name] = pkg

import importlib.util

spec = importlib.util.spec_from_file_location(
    "tvl.lints",
    package_path / "lints.py",
    submodule_search_locations=[str(package_path)],
)
module = importlib.util.module_from_spec(spec)
sys.modules["tvl.lints"] = module
assert spec.loader is not None
spec.loader.exec_module(module)
lint_module = module.lint_module


def _collect_codes(issues: List[Dict[str, Any]]) -> set:
    return {issue["code"] for issue in issues}


def _base_module() -> Dict[str, Any]:
    """Base TVL module with required fields."""
    return {
        "tvl": {"module": "corp.conformance.promotion_policy"},
        "tvl_version": "1.0",
        "environment": {"snapshot_id": "2025-01-01T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/dev.parquet"},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {
            "dominance": "epsilon_pareto",
            "alpha": 0.05,
            "min_effect": {"quality": 0.0},
        },
        "exploration": {"strategy": {"type": "grid"}},
    }


class AlphaValidationTests(unittest.TestCase):
    """Tests for alpha parameter validation.

    Per spec: alpha must be in (0, 1) exclusive.
    """

    def test_alpha_valid_range(self) -> None:
        """Alpha in valid range (0, 1) is accepted."""
        doc = _base_module()
        doc["promotion_policy"]["alpha"] = 0.05
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_alpha", codes)

    def test_alpha_at_zero_invalid(self) -> None:
        """Alpha = 0 is invalid (exclusive lower bound)."""
        doc = _base_module()
        doc["promotion_policy"]["alpha"] = 0.0
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        # Should produce error for alpha out of bounds
        self.assertIn("invalid_alpha", codes)

    def test_alpha_at_one_invalid(self) -> None:
        """Alpha = 1 is invalid (exclusive upper bound)."""
        doc = _base_module()
        doc["promotion_policy"]["alpha"] = 1.0
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_alpha", codes)

    def test_alpha_negative_invalid(self) -> None:
        """Negative alpha is invalid."""
        doc = _base_module()
        doc["promotion_policy"]["alpha"] = -0.05
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_alpha", codes)


class MinEffectValidationTests(unittest.TestCase):
    """Tests for min_effect (epsilon) validation.

    Per spec: epsilon_j >= 0 for each objective.
    """

    def test_min_effect_zero_valid(self) -> None:
        """Epsilon = 0 (exact comparison) is valid."""
        doc = _base_module()
        doc["promotion_policy"]["min_effect"] = {"quality": 0.0}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_min_effect", codes)

    def test_min_effect_positive_valid(self) -> None:
        """Positive epsilon is valid."""
        doc = _base_module()
        doc["promotion_policy"]["min_effect"] = {"quality": 0.01}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_min_effect", codes)

    def test_min_effect_missing_objective(self) -> None:
        """Missing epsilon for declared objective produces error."""
        doc = _base_module()
        doc["objectives"] = [
            {"name": "quality", "direction": "maximize"},
            {"name": "latency", "direction": "minimize"},
        ]
        doc["promotion_policy"]["min_effect"] = {"quality": 0.01}  # missing latency
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        # Should warn about missing min_effect entry
        self.assertIn("missing_min_effect", codes)

    def test_min_effect_negative_invalid(self) -> None:
        """Negative epsilon is invalid."""
        doc = _base_module()
        doc["promotion_policy"]["min_effect"] = {"quality": -0.01}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_min_effect", codes)


class BHAdjustmentTests(unittest.TestCase):
    """Tests for Benjamini-Hochberg adjustment configuration.

    Per spec: adjust field can be 'none' or 'BH'.
    """

    def test_adjust_bh_valid(self) -> None:
        """BH adjustment is valid."""
        doc = _base_module()
        doc["promotion_policy"]["adjust"] = "BH"
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_adjust", codes)

    def test_adjust_none_valid(self) -> None:
        """No adjustment is valid."""
        doc = _base_module()
        doc["promotion_policy"]["adjust"] = "none"
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_adjust", codes)

    def test_adjust_omitted_defaults_to_none(self) -> None:
        """Omitted adjust field defaults to 'none'."""
        doc = _base_module()
        # adjust field not present
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("missing_adjust", codes)


class BandedObjectiveTests(unittest.TestCase):
    """Tests for banded objectives with TOST.

    Per spec: band objectives use Two One-Sided Tests for equivalence.
    """

    def test_band_target_interval_valid(self) -> None:
        """Band with target interval [L, U] is valid."""
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "response_length",
                "band": {
                    "target": [100, 200],  # [L, U] interval
                    "test": "TOST",
                    "alpha": 0.05,
                },
            },
        ]
        doc["promotion_policy"]["min_effect"] = {}  # bands don't need min_effect
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)
        self.assertNotIn("invalid_band", codes)


class MetricRefTests(unittest.TestCase):
    """Tests for optional declarative metric references on objectives."""

    def test_metric_ref_is_accepted_on_standard_objective(self) -> None:
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "quality",
                "metric_ref": "metrics.quality.v1",
                "direction": "maximize",
            }
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)

    def test_metric_ref_is_accepted_on_banded_objective(self) -> None:
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "response_length",
                "metric_ref": "metrics.response_length.v1",
                "band": {
                    "target": [100, 200],
                    "test": "TOST",
                    "alpha": 0.05,
                },
            },
        ]
        doc["promotion_policy"]["min_effect"] = {}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_band", codes)

    def test_band_center_tolerance_valid(self) -> None:
        """Band with center and tolerance is valid."""
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "response_length",
                "band": {
                    "target": {"center": 150, "tol": 50},  # center +/- tolerance
                    "test": "TOST",
                    "alpha": 0.05,
                },
            },
        ]
        doc["promotion_policy"]["min_effect"] = {}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)
        self.assertNotIn("invalid_band", codes)

    def test_band_inconsistent_bounds_invalid(self) -> None:
        """Band with L >= U is invalid."""
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "response_length",
                "band": {
                    "target": [200, 100],  # L > U is invalid
                    "test": "TOST",
                    "alpha": 0.05,
                },
            },
        ]
        doc["promotion_policy"]["min_effect"] = {}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)
        self.assertIn("invalid_band_bounds", codes)

    def test_band_negative_tolerance_invalid(self) -> None:
        """Band with negative tolerance is invalid."""
        doc = _base_module()
        doc["objectives"] = [
            {
                "name": "response_length",
                "band": {
                    "target": {"center": 150, "tol": -50},  # tol must be > 0
                    "test": "TOST",
                    "alpha": 0.05,
                },
            },
        ]
        doc["promotion_policy"]["min_effect"] = {}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)
        self.assertIn("invalid_band_tolerance", codes)


class ChanceConstraintTests(unittest.TestCase):
    """Tests for chance constraints with Clopper-Pearson CIs.

    Per spec: chance constraints pass iff the one-sided upper confidence
    bound on the violation rate is at or below the threshold.
    """

    def test_chance_constraint_valid(self) -> None:
        """Valid chance constraint configuration."""
        doc = _base_module()
        doc["promotion_policy"]["chance_constraints"] = [
            {
                "name": "safety_violation_rate",
                "threshold": 0.02,  # max 2% violation rate
                "confidence": 0.95,  # 95% confidence
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_chance_constraint", codes)

    def test_chance_constraint_threshold_range(self) -> None:
        """Threshold must be in [0, 1]."""
        doc = _base_module()
        doc["promotion_policy"]["chance_constraints"] = [
            {
                "name": "safety_rate",
                "threshold": 1.5,  # > 1 is invalid
                "confidence": 0.95,
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_chance_threshold", codes)

    def test_chance_constraint_confidence_range(self) -> None:
        """Confidence must be in (0, 1)."""
        doc = _base_module()
        doc["promotion_policy"]["chance_constraints"] = [
            {
                "name": "safety_rate",
                "threshold": 0.02,
                "confidence": 0.0,  # = 0 is invalid
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_chance_confidence", codes)

    def test_multiple_chance_constraints(self) -> None:
        """Multiple chance constraints are allowed."""
        doc = _base_module()
        doc["promotion_policy"]["chance_constraints"] = [
            {"name": "safety_violation", "threshold": 0.02, "confidence": 0.95},
            {"name": "hallucination_rate", "threshold": 0.05, "confidence": 0.90},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_chance_constraint", codes)


class ObjectiveDirectionTests(unittest.TestCase):
    """Tests for objective direction validation."""

    def test_maximize_valid(self) -> None:
        """Maximize direction is valid."""
        doc = _base_module()
        doc["objectives"] = [{"name": "quality", "direction": "maximize"}]
        doc["promotion_policy"]["min_effect"] = {"quality": 0.0}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)

    def test_minimize_valid(self) -> None:
        """Minimize direction is valid."""
        doc = _base_module()
        doc["objectives"] = [{"name": "latency", "direction": "minimize"}]
        doc["promotion_policy"]["min_effect"] = {"latency": 0.0}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_direction", codes)

    def test_invalid_direction_rejected(self) -> None:
        """Invalid direction produces error."""
        doc = _base_module()
        doc["objectives"] = [{"name": "score", "direction": "increase"}]  # invalid
        doc["promotion_policy"]["min_effect"] = {"score": 0.0}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_direction", codes)


class MultiObjectiveTests(unittest.TestCase):
    """Tests for multi-objective configuration."""

    def test_multiple_objectives_valid(self) -> None:
        """Multiple objectives with epsilon-Pareto is valid."""
        doc = _base_module()
        doc["objectives"] = [
            {"name": "quality", "direction": "maximize"},
            {"name": "latency_p95_ms", "direction": "minimize"},
            {"name": "cost_usd", "direction": "minimize"},
        ]
        doc["promotion_policy"]["min_effect"] = {
            "quality": 0.01,
            "latency_p95_ms": 20,
            "cost_usd": 0.001,
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_objectives", codes)

    def test_empty_objectives_invalid(self) -> None:
        """Empty objectives list is invalid."""
        doc = _base_module()
        doc["objectives"] = []
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("empty_objectives", codes)

    def test_duplicate_objective_names_invalid(self) -> None:
        """Duplicate objective names are invalid."""
        doc = _base_module()
        doc["objectives"] = [
            {"name": "quality", "direction": "maximize"},
            {"name": "quality", "direction": "minimize"},  # duplicate
        ]
        doc["promotion_policy"]["min_effect"] = {"quality": 0.0}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("duplicate_objective", codes)


class DominanceTypeTests(unittest.TestCase):
    """Tests for dominance type validation."""

    def test_epsilon_pareto_valid(self) -> None:
        """epsilon_pareto dominance is valid."""
        doc = _base_module()
        doc["promotion_policy"]["dominance"] = "epsilon_pareto"
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_dominance", codes)

    def test_invalid_dominance_rejected(self) -> None:
        """Invalid dominance type produces error."""
        doc = _base_module()
        doc["promotion_policy"]["dominance"] = "pareto"  # should be epsilon_pareto
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("invalid_dominance", codes)


# -----------------------------------------------------------------------------
# Promotion Gate Statistical Tests
# -----------------------------------------------------------------------------

# Import promotion module
spec_promo = importlib.util.spec_from_file_location(
    "tvl.promotion",
    package_path / "promotion.py",
    submodule_search_locations=[str(package_path)],
)
module_promo = importlib.util.module_from_spec(spec_promo)
sys.modules["tvl.promotion"] = module_promo
assert spec_promo.loader is not None
spec_promo.loader.exec_module(module_promo)
epsilon_pareto_gate = module_promo.epsilon_pareto_gate
SCIPY_AVAILABLE = module_promo.SCIPY_AVAILABLE


@unittest.skipUnless(SCIPY_AVAILABLE, "scipy not available")
class PromotionGateTests(unittest.TestCase):
    """Tests for the epsilon-Pareto promotion gate statistical logic."""

    def test_clear_dominance_promotes(self) -> None:
        """Candidate clearly better on all objectives -> Promote."""
        incumbent = {
            "objective_values": {
                "quality": {"samples": [0.80, 0.82, 0.81, 0.79, 0.80, 0.81, 0.82, 0.80, 0.79, 0.81]},
            },
        }
        candidate = {
            "objective_values": {
                "quality": {"samples": [0.92, 0.91, 0.93, 0.90, 0.92, 0.91, 0.90, 0.92, 0.91, 0.93]},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02},
            "adjust": "none",
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("Promote", decision)
        self.assertTrue(evidence["summary"]["all_noninferior"])
        self.assertTrue(evidence["summary"]["any_superior"])

    def test_clear_inferiority_rejects(self) -> None:
        """Candidate clearly worse on objective -> Reject."""
        incumbent = {
            "objective_values": {
                "quality": {"samples": [0.92, 0.91, 0.93, 0.90, 0.92, 0.91, 0.90, 0.92, 0.91, 0.93]},
            },
        }
        candidate = {
            "objective_values": {
                "quality": {"samples": [0.70, 0.72, 0.71, 0.69, 0.70, 0.71, 0.72, 0.70, 0.69, 0.71]},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02},
            "adjust": "none",
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("Reject", decision)

    def test_within_noise_no_decision(self) -> None:
        """Candidate within noise of incumbent -> NoDecision."""
        incumbent = {
            "objective_values": {
                "quality": {"samples": [0.85, 0.86, 0.84, 0.85, 0.86, 0.84, 0.85, 0.86, 0.84, 0.85]},
            },
        }
        candidate = {
            "objective_values": {
                "quality": {"samples": [0.86, 0.85, 0.85, 0.86, 0.85, 0.85, 0.86, 0.85, 0.86, 0.85]},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.05},  # Large epsilon
            "adjust": "none",
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("NoDecision", decision)

    def test_minimize_direction(self) -> None:
        """For minimize objectives, lower is better."""
        incumbent = {
            "objective_values": {
                "latency": {"samples": [150, 152, 148, 151, 149, 150, 152, 148, 151, 149]},
            },
        }
        candidate = {
            "objective_values": {
                "latency": {"samples": [120, 122, 118, 121, 119, 120, 122, 118, 121, 119]},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"latency": 10},
            "adjust": "none",
        }
        objectives = [{"name": "latency", "direction": "minimize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("Promote", decision)

    def test_bh_adjustment(self) -> None:
        """BH adjustment is applied to superiority p-values."""
        incumbent = {
            "objective_values": {
                "quality": {"samples": [0.85, 0.86, 0.84, 0.85, 0.86] * 2},
                "speed": {"samples": [100, 102, 98, 101, 99] * 2},
            },
        }
        candidate = {
            "objective_values": {
                "quality": {"samples": [0.90, 0.91, 0.89, 0.90, 0.91] * 2},
                "speed": {"samples": [95, 97, 93, 96, 94] * 2},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.01, "speed": 5},
            "adjust": "BH",
        }
        objectives = [
            {"name": "quality", "direction": "maximize"},
            {"name": "speed", "direction": "minimize"},
        ]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("BH", evidence["summary"]["adjustment_method"])
        # Superiority p-values are adjusted; non-inferiority remains unadjusted (IUT).
        self.assertIn("adjusted_p_super", evidence["per_objective"]["quality"])

    def test_chance_constraint_pass(self) -> None:
        """Chance constraint with a low enough violation rate passes."""
        incumbent = {"objective_values": {"quality": {"samples": [0.9] * 10}}}
        candidate = {
            "objective_values": {"quality": {"samples": [0.92] * 10}},
            "chance_outcomes": {"safety": {"violations": 1, "trials": 100}},
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.01},
            "adjust": "none",
            "chance_constraints": [
                {"name": "safety", "threshold": 0.05, "confidence": 0.95},
            ],
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("pass", evidence["chance_constraints"]["safety"]["verdict"])

    def test_chance_constraint_fail(self) -> None:
        """Chance constraint with too many violations fails."""
        incumbent = {"objective_values": {"quality": {"samples": [0.9] * 10}}}
        candidate = {
            "objective_values": {"quality": {"samples": [0.92] * 10}},
            "chance_outcomes": {"safety": {"violations": 8, "trials": 100}},
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.01},
            "adjust": "none",
            "chance_constraints": [
                {"name": "safety", "threshold": 0.05, "confidence": 0.95},
            ],
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("Reject", decision)
        self.assertEqual("fail", evidence["chance_constraints"]["safety"]["verdict"])

    def test_banded_objective_in_band(self) -> None:
        """Banded objective with mean in target band passes TOST."""
        incumbent = {"objective_values": {}}
        candidate = {
            "objective_values": {
                "length": {"samples": [100, 102, 98, 101, 99, 100, 102, 98, 101, 99] * 5},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {},
            "adjust": "none",
        }
        objectives = [
            {
                "name": "length",
                "band": {"target": [95, 105], "alpha": 0.05},
            },
        ]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("in_band", evidence["per_objective"]["length"]["verdict"])

    def test_banded_objective_out_of_band(self) -> None:
        """Banded objective with mean outside target band fails."""
        incumbent = {"objective_values": {}}
        candidate = {
            "objective_values": {
                "length": {"samples": [120, 122, 118, 121, 119] * 10},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {},
            "adjust": "none",
        }
        objectives = [
            {
                "name": "length",
                "band": {"target": [95, 105], "alpha": 0.05},
            },
        ]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertIn(evidence["per_objective"]["length"]["verdict"], ["out_of_band", "inconclusive"])

    def test_aggregated_stats_input(self) -> None:
        """Promotion gate accepts aggregated statistics."""
        incumbent = {
            "objective_values": {
                "quality": {"mean": 0.80, "std": 0.05, "n": 50},
            },
        }
        candidate = {
            "objective_values": {
                "quality": {"mean": 0.90, "std": 0.04, "n": 50},
            },
        }
        policy = {
            "alpha": 0.05,
            "min_effect": {"quality": 0.02},
            "adjust": "none",
        }
        objectives = [{"name": "quality", "direction": "maximize"}]

        decision, evidence = epsilon_pareto_gate(incumbent, candidate, policy, objectives)
        self.assertEqual("Promote", decision)
        self.assertEqual("welch", evidence["per_objective"]["quality"]["test_type"])


if __name__ == "__main__":
    unittest.main()
