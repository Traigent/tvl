from __future__ import annotations

import pathlib
import sys
import types
import unittest
from typing import Any, Dict
BASE = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = BASE / "python"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

import types
import importlib.util

package_name = "tvl"
package_path = PKG_ROOT / package_name

if package_name not in sys.modules:
    pkg = types.ModuleType(package_name)
    pkg.__path__ = [str(package_path)]
    sys.modules[package_name] = pkg

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


def _collect_codes(issues):
    return {issue["code"] for issue in issues}


def _base_module() -> Dict[str, Any]:
    return {
        "tvl": {"module": "corp.validation.test"},
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


class LintModuleTests(unittest.TestCase):
    def test_unknown_tvar_in_structural_constraint(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["mini", "pro"]},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "unknown = true"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("undeclared_tvar", codes)

    def test_enum_literal_outside_domain(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "agent", "type": "enum[str]", "domain": ["tools-mini", "tools-pro"]},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "agent = \"tools-legacy\""},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("constraint_value_out_of_domain", codes)

    def test_float_equality_warns(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {"structural": [{"expr": "temperature = 0.5"}]}
        issues = lint_module(doc)
        float_warnings = [issue for issue in issues if issue["code"] == "float_equality"]
        self.assertEqual(1, len(float_warnings))
        self.assertEqual("warning", float_warnings[0]["severity"])
        self.assertNotIn("empty_domain", _collect_codes(issues))

    def test_derived_constraint_rejects_tvar_reference(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"set": [1, 2, 3]}},
        ]
        doc["constraints"] = {
            "derived": [
                {"require": "max_calls <= 2"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("derived_references_tvar", codes)

    def test_empty_enum_domain_detected(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "strategy", "type": "enum[str]", "domain": []},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("empty_domain", codes)

    def test_structural_with_parentheses_and_not(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "agent", "type": "enum[str]", "domain": ["mini", "pro"]},
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 5]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "not (agent = 'pro') or (max_calls >= 1 and max_calls <= 3)"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_structural_expression", codes)
        self.assertNotIn("unsupported_structural_literal", codes)

    def test_clause_id_attached_to_literal_issue(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "agent", "type": "enum[str]", "domain": ["mini", "pro"]},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "agent = 'enterprise'"},
            ]
        }
        issues = lint_module(doc)
        offending = next(issue for issue in issues if issue["code"] == "constraint_value_out_of_domain")
        self.assertIn("clause_id", offending)
        self.assertRegex(offending["clause_id"], r"0#[0-9a-f]{8}")

    def test_when_then_implication_supported(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "use_examples", "type": "bool", "domain": [True, False]},
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 5]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"when": "use_examples = true", "then": "max_calls >= 2"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertFalse(codes)


class FormalVerificationScopeTests(unittest.TestCase):
    """Tests for formal verification scope warnings (W6xxx)."""

    def test_registry_domain_warns(self) -> None:
        """W6001: Registry domains are outside formal verification scope."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "model",
                "type": "enum[str]",
                "domain": {"registry": "model_catalog", "filter": "version >= 2.0"},
            },
        ]
        issues = lint_module(doc)
        registry_warnings = [i for i in issues if i["code"] == "unverifiable_registry_domain"]
        self.assertEqual(1, len(registry_warnings))
        self.assertEqual("warning", registry_warnings[0]["severity"])
        self.assertIn("Theorem 8.1", registry_warnings[0]["message"])

    def test_callable_type_warns(self) -> None:
        """W6002: Callable types are outside formal verification scope."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "scorer",
                "type": "callable[Scorer]",
                "domain": ["default_scorer", "custom_scorer"],
            },
        ]
        issues = lint_module(doc)
        callable_warnings = [i for i in issues if i["code"] == "unverifiable_callable_type"]
        self.assertEqual(1, len(callable_warnings))
        self.assertEqual("warning", callable_warnings[0]["severity"])
        self.assertIn("callable", callable_warnings[0]["message"])

    def test_inadequate_precision_with_colliding_values(self) -> None:
        """W6003: Float values that collide at default precision."""
        doc = _base_module()
        # Values 0.0001 and 0.0002 will both map to 0 at precision=1000
        doc["tvars"] = [
            {
                "name": "epsilon",
                "type": "float",
                "domain": [0.0001, 0.0002, 0.0003],
            },
        ]
        issues = lint_module(doc, precision=1000)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]
        self.assertEqual(1, len(precision_warnings))
        self.assertEqual("warning", precision_warnings[0]["severity"])
        self.assertIn("collide", precision_warnings[0]["message"])
        self.assertIn("minimum_precision", precision_warnings[0])

    def test_adequate_precision_no_warning(self) -> None:
        """Float values that don't collide should produce no warning."""
        doc = _base_module()
        # Values 0.1, 0.2, 0.3 map to 100, 200, 300 at precision=1000
        doc["tvars"] = [
            {
                "name": "temperature",
                "type": "float",
                "domain": [0.1, 0.2, 0.3],
            },
        ]
        issues = lint_module(doc, precision=1000)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]
        self.assertEqual(0, len(precision_warnings))

    def test_resolution_misalignment_warns(self) -> None:
        """W6003: Resolution that doesn't align with precision."""
        doc = _base_module()
        # Resolution 0.03 * precision=1000 = 30, which is fine
        # But resolution 0.0003 * precision=1000 = 0.3, not an integer
        doc["tvars"] = [
            {
                "name": "step",
                "type": "float",
                "domain": {"range": [0.0, 0.001], "resolution": 0.0003},
            },
        ]
        issues = lint_module(doc, precision=1000)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]
        self.assertEqual(1, len(precision_warnings))
        self.assertIn("resolution", precision_warnings[0]["message"])

    def test_high_precision_avoids_collision(self) -> None:
        """Higher precision factor prevents collisions."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "epsilon",
                "type": "float",
                "domain": [0.0001, 0.0002, 0.0003],
            },
        ]
        # At precision=100000, these map to 10, 20, 30 - no collision
        issues = lint_module(doc, precision=100000)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]
        self.assertEqual(0, len(precision_warnings))

    def test_range_with_aligned_resolution_no_warning(self) -> None:
        """Range domain with resolution aligned to precision."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "rate",
                "type": "float",
                "domain": {"range": [0.0, 1.0], "resolution": 0.1},
            },
        ]
        # Resolution 0.1 * precision=1000 = 100, which is an integer
        issues = lint_module(doc, precision=1000)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]
        self.assertEqual(0, len(precision_warnings))


if __name__ == "__main__":
    unittest.main()
