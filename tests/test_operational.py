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

    def test_infinite_literal_coefficient_is_blamed_on_the_literal_not_the_symbol(self) -> None:
        # The infinite coefficient is the literal 1e400; the finite symbol x is not the cause, for
        # x = 1 (inf * 1) or x = 0 (inf * 0 is NaN). The expression is unsupported.
        for value in (1, 0):
            with self.subTest(x=value):
                doc = _base_module()
                doc["environment"]["context"] = {"x": value}
                doc.setdefault("constraints", {})["derived"] = [
                    {"require": "env.context.x * 1e400 <= 5"},
                ]
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual([i["code"] for i in result.issues], ["unsupported_derived_expression"])

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

    def test_operational_infinite_trial_and_wallclock_budget_is_invalid_not_crash(self) -> None:
        # Issue #245: an infinite count (YAML `.inf`) cannot be converted to int and must be a coded issue.
        cases = (
            ("max_trials", float("inf"), "invalid_budget_max_trials"),
            ("max_trials", float("-inf"), "invalid_budget_max_trials"),
            ("max_wallclock_s", float("inf"), "invalid_budget_max_wallclock"),
            ("max_wallclock_s", float("-inf"), "invalid_budget_max_wallclock"),
        )
        for key, value, code in cases:
            with self.subTest(key=key, value=value):
                doc = _base_module()
                doc["exploration"]["budgets"] = {key: value}
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual([i["code"] for i in result.issues], [code])

    def test_operational_huge_integer_budget_counts_stay_valid(self) -> None:
        # A huge but finite integer count is still a positive integer; only infinities are rejected.
        for key in ("max_trials", "max_wallclock_s"):
            with self.subTest(key=key):
                doc = _base_module()
                doc["exploration"]["budgets"] = {key: 10**400}
                self.assertTrue(check_operational(doc).ok)

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

    def test_derived_integer_literal_too_large_for_float_is_coded_not_crashing(self) -> None:
        # Issue #245: a derived require whose integer literal exceeds the float range
        # must yield a coded error, never an OverflowError traceback.
        big = 10**400
        shapes = (
            f"env.context.x <= {big}",
            f"env.context.x + {big} <= 5",
            f"env.context.x * {big} <= 5",
            f"-{big} * env.context.x <= 5",
            f"env.context.x <= -{big}",
        )
        for expression in shapes:
            with self.subTest(expression=expression[:40]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                result = check_operational(doc)
                self.assertFalse(result.ok)
                self.assertEqual([i["code"] for i in result.issues], ["unsupported_derived_expression"])

    def test_cli_derived_integer_literal_too_large_exits_2_without_traceback(self) -> None:
        import subprocess
        import tempfile

        source = (BASE / "spec" / "examples" / "cost-optimization.tvl.yml").read_text(encoding="utf-8")
        original = "    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05\n"
        text = source.replace(
            original,
            original + f"    - require: env.context.provider_input_price_usd_per_1k_tokens * {10**400} <= 5\n",
        )
        self.assertNotEqual(text, source)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "derived_huge.tvl.yml"
            path.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "tvl_tools.tvl_check_operational.cli", str(path), "--json"],
                capture_output=True, text=True, cwd=BASE, check=False,
            )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("unsupported_derived_expression", proc.stdout)

    def test_operational_finite_context_value_still_decides(self) -> None:
        for value, ok in ((180, True), (900, False), (180.5, True)):
            with self.subTest(value=value):
                doc = _base_module()
                doc["environment"]["context"] = {"gateway_baseline_latency_ms": value}
                doc.setdefault("constraints", {})["derived"] = [
                    {"require": "env.context.gateway_baseline_latency_ms <= 250"},
                ]
                self.assertEqual(check_operational(doc).ok, ok)

    def test_operational_max_spend_beyond_float_range_names_the_float_range(self) -> None:
        # Issue #224: a positive integer float() cannot hold is not a finite budget; say so, do not say "must be >= 0".
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_spend_usd": 10**400 - 1}
        result = check_operational(doc)
        self.assertFalse(result.ok)
        self.assertEqual(result.binding_budget, "max_spend_usd")
        issues = [i for i in result.issues if i["code"] == "invalid_budget_max_spend"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(
            issues[0]["message"],
            "exploration.budgets.max_spend_usd must be a finite number >= 0 within the float range",
        )

    def test_operational_max_spend_negative_beyond_float_range_keeps_the_sign_message(self) -> None:
        doc = _base_module()
        doc["exploration"]["budgets"] = {"max_spend_usd": -(10**400)}
        result = check_operational(doc)
        self.assertFalse(result.ok)
        issues = [i for i in result.issues if i["code"] == "invalid_budget_max_spend"]
        self.assertEqual(issues[0]["message"], "exploration.budgets.max_spend_usd must be >= 0")

    def test_operational_max_spend_nan_and_infinity_keep_the_plain_message(self) -> None:
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                doc = _base_module()
                doc["exploration"]["budgets"] = {"max_spend_usd": value}
                result = check_operational(doc)
                self.assertFalse(result.ok)
                issues = [i for i in result.issues if i["code"] == "invalid_budget_max_spend"]
                self.assertEqual(issues[0]["message"], "exploration.budgets.max_spend_usd must be >= 0")

    def test_cli_max_spend_beyond_float_range_exits_2_with_the_float_range_message(self) -> None:
        import json
        import subprocess
        import tempfile

        doc = _base_module()
        doc["tvars"] = [{"name": "x", "type": "int", "domain": {"range": [1, 3]}}]
        doc["exploration"]["budgets"] = {"max_spend_usd": 10**400 - 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "max_spend_huge.tvl.yml"
            path.write_text(json.dumps(doc), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "tvl_tools.tvl_check_operational.cli", str(path), "--json"],
                capture_output=True, text=True, cwd=BASE, check=False,
            )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn(
            "exploration.budgets.max_spend_usd must be a finite number >= 0 within the float range",
            proc.stdout,
        )

    def test_derived_literal_beyond_float_range_message_names_the_float_range(self) -> None:
        # The expression is already of the form symbol OP value; the literal is the problem, so say that.
        for expression in (f"env.context.x <= {10**400}", f"env.context.x >= -{10**400}"):
            with self.subTest(expression=expression[-12:]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                issues = [i for i in check_operational(doc).issues if i["code"] == "unsupported_derived_expression"]
                self.assertEqual(len(issues), 1)
                self.assertEqual(
                    issues[0]["message"],
                    f"Derived constraint '{expression}' has a numeric literal beyond the float range",
                )

    def test_derived_other_unsupported_expressions_keep_the_form_message(self) -> None:
        # Controls: neither a beyond-range literal on the left (a coefficient) nor a plain unsupported shape changes.
        for expression in (f"env.context.x * {10**400} <= 5", "env.context.x != 5"):
            with self.subTest(expression=expression[:24]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                issues = [i for i in check_operational(doc).issues if i["code"] == "unsupported_derived_expression"]
                self.assertEqual(len(issues), 1)
                self.assertIn("must be of the form symbol OP value", issues[0]["message"])

    def test_derived_huge_literal_in_unsupported_form_keeps_the_form_message(self) -> None:
        # A beyond-range literal does not make an unsupported form supported: the operator, the
        # left side and the shape still decide, so the form message stays.
        big = 10**400
        for expression in (
            f"env.context.x != {big}",
            f"env.context.x is {big}",
            f"'abc' <= {big}",
            f"foo(env.context.x) <= {big}",
            f"1 <= {big}",
        ):
            with self.subTest(expression=expression[:24]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                issues = [i for i in check_operational(doc).issues if i["code"] == "unsupported_derived_expression"]
                self.assertEqual(len(issues), 1)
                self.assertIn("must be of the form symbol OP value", issues[0]["message"])

    def test_derived_supported_form_with_huge_right_hand_literal_names_the_float_range(self) -> None:
        big = 10**400
        for expression in (
            f"env.context.x <= {big}",
            f"env.context.x * 2 <= {big}",
            f"env.context.x >= -{big}",
            f"env.context.x == {big}",
        ):
            with self.subTest(expression=expression[:24]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                issues = [i for i in check_operational(doc).issues if i["code"] == "unsupported_derived_expression"]
                self.assertEqual(len(issues), 1)
                self.assertEqual(
                    issues[0]["message"],
                    f"Derived constraint '{expression}' has a numeric literal beyond the float range",
                )

    def test_derived_long_chain_with_huge_literal_never_raises(self) -> None:
        # Long left-nested sums compared with an integer beyond the float range must yield a coded
        # issue. The old helper unparsed the tree and re-parsed it, which exhausted the stack at ~330 terms.
        big = 10**400
        for terms in (300, 330, 400, 600, 1000):
            chain = " + ".join(["env.context.x"] * terms)
            for literal in (big, 5):
                with self.subTest(terms=terms, literal=str(literal)[:8]):
                    doc = _base_module()
                    doc["environment"]["context"] = {"x": 1}
                    doc.setdefault("constraints", {})["derived"] = [{"require": f"{chain} <= {literal}"}]
                    result = check_operational(doc)
                    self.assertFalse(result.ok)
                    self.assertEqual(len(result.issues), 1)
                    self.assertIn(result.issues[0]["code"], ("unsupported_derived_expression", "derived_constraint_violation"))

    def test_cli_derived_long_chain_with_huge_literal_exits_2_without_traceback(self) -> None:
        import subprocess
        import tempfile

        source = (BASE / "spec" / "examples" / "cost-optimization.tvl.yml").read_text(encoding="utf-8")
        original = "    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05\n"
        for terms in (300, 330, 400, 600, 1000):
            chain = " + ".join(["env.context.provider_input_price_usd_per_1k_tokens"] * terms)
            text = source.replace(original, original + f"    - require: {chain} <= {10**400}\n")
            self.assertNotEqual(text, source)
            with self.subTest(terms=terms), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "chain_huge.tvl.yml"
                path.write_text(text, encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, "-m", "tvl_tools.tvl_check_operational.cli", str(path), "--json"],
                    capture_output=True, text=True, cwd=BASE, check=False,
                )
                self.assertEqual(proc.returncode, 2, proc.stderr[-2000:])
                self.assertNotIn("Traceback", proc.stderr)

    def test_derived_ordinary_issue_outranks_the_float_range_message(self) -> None:
        # With the huge literal replaced by 0, an ordinary error (shape, symbol, finiteness) is what the
        # user would see with a small literal; that issue is reported instead of the float-range message.
        big = 10**400
        cases = (
            (f"x <= {big}", "x <= 5"),
            (f"env.other.x <= {big}", "env.other.x <= 5"),
            (f"env.context.x*1e400 <= {big}", "env.context.x*1e400 <= 5"),
            (f"env.context.zz <= {big}", "env.context.zz <= 5"),
        )
        for huge, small in cases:
            with self.subTest(expression=huge[:24]):
                doc_huge = _base_module()
                doc_huge["environment"]["context"] = {"x": 1}
                doc_huge["constraints"] = {"derived": [{"require": huge}]}
                doc_small = _base_module()
                doc_small["environment"]["context"] = {"x": 1}
                doc_small["constraints"] = {"derived": [{"require": small}]}
                issues_huge = check_operational(doc_huge).issues
                issues_small = check_operational(doc_small).issues
                self.assertEqual([i["code"] for i in issues_huge], [i["code"] for i in issues_small])
                self.assertNotIn("beyond the float range", issues_huge[0]["message"])
                self.assertEqual(
                    [i["message"].replace(str(big), "5") for i in issues_huge],
                    [i["message"] for i in issues_small],
                )

    def test_derived_supported_forms_with_huge_literal_keep_the_float_range_message(self) -> None:
        big = 10**400
        for expression in (
            f"env.context.x <= {big}",
            f"env.context.x < {big}",
            f"env.context.x > -{big}",
            f"env.context.x * 2 <= {big}",
            f"2 * env.context.x <= {big}",
            f"env.context.x + env.context.y <= {big}",
            f"-env.context.x <= {big}",
            f"env.context.x <= -{big}",
            f"env.context.x == {big}",
            f"env.context.x = {big}",
        ):
            with self.subTest(expression=expression[:30]):
                doc = _base_module()
                doc["environment"]["context"] = {"x": 1, "y": 2}
                doc.setdefault("constraints", {})["derived"] = [{"require": expression}]
                issues = check_operational(doc).issues
                self.assertEqual([i["code"] for i in issues], ["unsupported_derived_expression"])
                self.assertEqual(
                    issues[0]["message"],
                    f"Derived constraint '{expression}' has a numeric literal beyond the float range",
                )


if __name__ == "__main__":
    unittest.main()
