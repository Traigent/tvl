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

package_name = "tvl"
package_path = PKG_ROOT / package_name
if package_name not in sys.modules:
    pkg = types.ModuleType(package_name)
    pkg.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    sys.modules[package_name] = pkg

import importlib.util

spec = importlib.util.spec_from_file_location(
    "tvl.operational",
    package_path / "operational.py",
    submodule_search_locations=[str(package_path)],
)
module = importlib.util.module_from_spec(spec)
sys.modules["tvl.operational"] = module
assert spec.loader is not None
spec.loader.exec_module(module)

check_operational = module.check_operational


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


class OperationalTests(unittest.TestCase):
    def test_operational_pass_default(self) -> None:
        doc = _base_module()
        result = check_operational(doc)
        self.assertTrue(result.ok)

    def test_operational_skip_budget(self) -> None:
        doc = _base_module()
        doc["tvl"]["validation"] = {"skip_budget_checks": True}
        result = check_operational(doc)
        self.assertTrue(result.ok)

    def test_operational_budget_invalid(self) -> None:
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_trials": 0}
        result = check_operational(doc)
        self.assertFalse(result.ok)
        self.assertEqual(result.binding_budget, "max_trials")
        codes = {issue["code"] for issue in result.issues}
        self.assertIn("invalid_budget_max_trials", codes)

    def test_operational_derived_violation(self) -> None:
        doc = _base_module()
        doc["environment"]["context"] = {"cost_usd": 10}
        doc.setdefault("constraints", {})["derived"] = [{"require": "env.context.cost_usd <= 5"}]
        result = check_operational(doc)
        self.assertFalse(result.ok)
        codes = {issue["code"] for issue in result.issues}
        self.assertIn("derived_constraint_violation", codes)

    def test_operational_derived_unknown_symbol_error(self) -> None:
        doc = _base_module()
        doc.setdefault("constraints", {})["derived"] = [
            {"require": "missing_metric <= 1"}
        ]
        result = check_operational(doc)
        self.assertFalse(result.ok)
        codes = {issue["code"] for issue in result.issues}
        self.assertIn("derived_invalid_symbol_reference", codes)

    def test_operational_context_symbol_passes(self) -> None:
        doc = _base_module()
        doc["environment"]["context"] = {"daily_request_budget": 5000}
        doc.setdefault("constraints", {})["derived"] = [
            {"require": "env.context.daily_request_budget >= 1000"},
        ]
        result = check_operational(doc)
        self.assertTrue(result.ok)

    def test_operational_bare_symbol_fails(self) -> None:
        doc = _base_module()
        doc["environment"]["context"] = {"daily_request_budget": 5000}
        doc.setdefault("constraints", {})["derived"] = [
            {"require": "daily_request_budget >= 1000"},
        ]
        result = check_operational(doc)
        self.assertFalse(result.ok)
        codes = {issue["code"] for issue in result.issues}
        self.assertIn("derived_invalid_symbol_reference", codes)


if __name__ == "__main__":
    unittest.main()
