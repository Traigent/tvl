from __future__ import annotations

import importlib.util
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

    def test_operational_max_spend_zero_is_valid(self) -> None:
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_spend_usd": 0}
        result = check_operational(doc)
        codes = {issue["code"] for issue in result.issues}
        self.assertNotIn("invalid_budget_max_spend", codes)
        self.assertTrue(result.ok)

    def test_operational_max_spend_fraction_is_valid(self) -> None:
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_spend_usd": 0.5}
        self.assertTrue(check_operational(doc).ok)

    def test_operational_max_spend_negative_is_invalid(self) -> None:
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_spend_usd": -1}
        result = check_operational(doc)
        self.assertFalse(result.ok)
        self.assertEqual(result.binding_budget, "max_spend_usd")
        issues = [i for i in result.issues if i["code"] == "invalid_budget_max_spend"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["message"], "exploration.budgets.max_spend_usd must be >= 0")

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

    def test_operational_non_finite_or_bool_context_value_is_non_numeric(self) -> None:
        # Issue #245: NaN makes every negated inequality false, so it used to pass.
        for value in (float("nan"), "nan", float("inf"), "-inf", True, False):
            for op in ("<=", ">=", "<", ">", "="):
                with self.subTest(value=value, op=op):
                    doc = _base_module()
                    doc["environment"]["context"] = {"gateway_baseline_latency_ms": value}
                    doc.setdefault("constraints", {})["derived"] = [
                        {"require": f"env.context.gateway_baseline_latency_ms {op} 250"},
                    ]
                    result = check_operational(doc)
                    self.assertFalse(result.ok)
                    codes = [issue["code"] for issue in result.issues]
                    self.assertEqual(codes, ["non_numeric_derived_symbol"])

    def test_operational_overflowing_sum_is_non_numeric(self) -> None:
        # Issue #245: finite terms whose weighted sum overflows to inf - inf = NaN.
        for op in ("<=", ">=", "<", ">"):
            with self.subTest(op=op):
                doc = _base_module()
                doc["environment"]["context"] = {"a": 1e308, "b": 1e308}
                doc.setdefault("constraints", {})["derived"] = [
                    {"require": f"2 * env.context.a - 2 * env.context.b {op} 5"},
                ]
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual([i["code"] for i in result.issues], ["non_numeric_derived_symbol"])

    def test_operational_huge_integer_context_value_is_non_numeric(self) -> None:
        # Issue #245: float(10**400) raises OverflowError; it must be a coded issue, not a crash.
        for value in (10**400, -(10**400)):
            with self.subTest(value=value):
                doc = _base_module()
                doc["environment"]["context"] = {"lat": value}
                doc.setdefault("constraints", {})["derived"] = [{"require": "env.context.lat <= 5"}]
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual([i["code"] for i in result.issues], ["non_numeric_derived_symbol"])

    def test_operational_huge_integer_max_spend_is_invalid_budget(self) -> None:
        # Issue #245: an integer too large for a float is not a finite budget.
        for value in (10**400, -(10**400)):
            with self.subTest(value=value):
                doc = _base_module()
                doc["exploration"]["budgets"] = {"max_spend_usd": value}
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual(result.binding_budget, "max_spend_usd")
                self.assertEqual([i["code"] for i in result.issues], ["invalid_budget_max_spend"])

    def test_cli_huge_integer_context_value_exits_2_without_traceback(self) -> None:
        import subprocess
        import tempfile

        source = (BASE / "spec" / "examples" / "cost-optimization.tvl.yml").read_text(encoding="utf-8")
        text = source.replace(
            "provider_input_price_usd_per_1k_tokens: 0.03",
            f"provider_input_price_usd_per_1k_tokens: {10**400}",
        )
        self.assertNotEqual(text, source)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "huge.tvl.yml"
            path.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "tvl_tools.tvl_check_operational.cli", str(path), "--json"],
                capture_output=True, text=True, cwd=BASE, check=False,
            )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("non_numeric_derived_symbol", proc.stdout)

    def test_operational_finite_context_value_still_decides(self) -> None:
        for value, ok in ((180, True), (900, False), (180.5, True)):
            with self.subTest(value=value):
                doc = _base_module()
                doc["environment"]["context"] = {"gateway_baseline_latency_ms": value}
                doc.setdefault("constraints", {})["derived"] = [
                    {"require": "env.context.gateway_baseline_latency_ms <= 250"},
                ]
                self.assertEqual(check_operational(doc).ok, ok)


if __name__ == "__main__":
    unittest.main()
