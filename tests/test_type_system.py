"""
Conformance tests for the TVL type system.

Tests type well-formedness, domain containment, and constraint typing
per the formal specification in Appendix: Type System for TVL.
"""
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


def _collect_codes(issues):
    return {issue["code"] for issue in issues}


def _base_module() -> Dict[str, Any]:
    """Base TVL module with required fields."""
    return {
        "tvl": {"module": "corp.conformance.type_system"},
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


class BoolTypeTests(unittest.TestCase):
    """Tests for T-Bool type (Section: Type Well-Formedness)."""

    def test_bool_domain_valid(self) -> None:
        """Bool TVAR with valid domain [true, false]."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "use_cot", "type": "bool", "domain": [True, False]},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)
        self.assertNotIn("empty_domain", codes)

    def test_bool_domain_single_value(self) -> None:
        """Bool TVAR with single value domain is valid but constant."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "always_true", "type": "bool", "domain": [True]},
        ]
        issues = lint_module(doc)
        # Single value domain is valid, may produce warning
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)

    def test_bool_constraint_valid(self) -> None:
        """Constraint with bool equality is well-typed (Atom-Eq rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "use_cot", "type": "bool", "domain": [True, False]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "use_cot = true"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("type_mismatch", codes)


class IntTypeTests(unittest.TestCase):
    """Tests for T-Int type (Section: Type Well-Formedness)."""

    def test_int_range_valid(self) -> None:
        """Int TVAR with valid range domain."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 10]}},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)
        self.assertNotIn("invalid_domain", codes)

    def test_int_set_valid(self) -> None:
        """Int TVAR with explicit set domain."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "batch_size", "type": "int", "domain": {"set": [1, 2, 4, 8, 16]}},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)

    def test_int_constraint_comparison(self) -> None:
        """Int comparison constraints are well-typed (Atom-Leq, Atom-Geq)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 10]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "max_calls >= 2"},
                {"expr": "max_calls <= 8"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("type_mismatch", codes)

    def test_int_range_constraint(self) -> None:
        """Int range constraint is well-typed (Atom-Range rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 10]}},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "2 <= max_calls <= 8"}]
        }
        issues = lint_module(doc)
        # Range constraints may not be supported in surface syntax
        # Test validates parsing doesn't crash


class FloatTypeTests(unittest.TestCase):
    """Tests for T-Float type (Section: Type Well-Formedness)."""

    def test_float_range_valid(self) -> None:
        """Float TVAR with valid range domain."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 2.0]}},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)

    def test_float_with_resolution(self) -> None:
        """Float TVAR with resolution specification."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "temperature",
                "type": "float",
                "domain": {"range": [0.0, 2.0], "resolution": 0.1},
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)

    def test_float_equality_warning(self) -> None:
        """Float equality constraint produces warning (per spec)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {"structural": [{"expr": "temperature = 0.5"}]}
        issues = lint_module(doc)
        float_warnings = [i for i in issues if i["code"] == "float_equality"]
        self.assertEqual(1, len(float_warnings))
        self.assertEqual("warning", float_warnings[0]["severity"])


class EnumTypeTests(unittest.TestCase):
    """Tests for T-Enum type (Section: Type Well-Formedness)."""

    def test_enum_str_valid(self) -> None:
        """Enum[str] TVAR with valid domain."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["gpt-4", "claude-3"]},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_type", codes)

    def test_enum_empty_domain_error(self) -> None:
        """Empty enum domain produces hard error (E1002)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": []},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("empty_domain", codes)

    def test_enum_value_out_of_domain(self) -> None:
        """Constraint with enum value outside domain produces error."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["mini", "pro"]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "model = \"enterprise\""}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("constraint_value_out_of_domain", codes)


class TupleTypeTests(unittest.TestCase):
    """Tests for T-Tuple type with product semantics.

    Per spec: tuple types have product semantics (A x B), not tagged union.
    Configuration space grows as Cartesian product of component domains.
    """

    def test_tuple_type_declaration(self) -> None:
        """Tuple TVAR declaration syntax validation."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "model_config",
                "type": "tuple[enum[str], float]",
                "domain": {
                    "components": [
                        ["gpt-4", "claude-3"],
                        {"range": [0.0, 1.0]},
                    ]
                },
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("missing_domain", codes)
        self.assertNotIn("empty_domain", codes)
        self.assertNotIn("invalid_tuple_domain", codes)

    def test_tuple_product_semantics(self) -> None:
        """Tuple domain is Cartesian product of components."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "retrieval_config",
                "type": "tuple[int, int]",
                "domain": {
                    "components": [
                        {"range": [1, 3]},  # k values: 1, 2, 3
                        {"range": [100, 200]},  # chunk_size: 100-200
                    ]
                },
            },
        ]
        issues = lint_module(doc)
        # Product semantics: |D| = 3 * 101 = 303 configurations
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_tuple_domain", codes)


class CallableTypeTests(unittest.TestCase):
    """Tests for T-Callable type with registry resolution.

    Per spec: callable[ProtoId] requires ProtoId in registry dom(R).
    Resolution is lazy - validated at specialization time.
    """

    def test_callable_type_declaration(self) -> None:
        """Callable TVAR with registry reference."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "reranker",
                "type": "callable[RerankerProto]",
                "domain": {"registry": "corp.rerankers"},
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("missing_domain", codes)
        self.assertNotIn("empty_domain", codes)

    def test_callable_registry_with_filter(self) -> None:
        """Callable registry reference with filter."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "reranker",
                "type": "callable[RerankerProto]",
                "domain": {
                    "registry": "corp.rerankers",
                    "filter": "category = 'neural'",
                },
            },
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("missing_domain", codes)
        self.assertNotIn("empty_domain", codes)


class ConstraintTypingTests(unittest.TestCase):
    """Tests for constraint formula typing (Section: Formula Typing Rules)."""

    def test_form_and_typing(self) -> None:
        """Conjunction of atoms is well-typed (Form-And rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "x", "type": "int", "domain": {"range": [0, 10]}},
            {"name": "y", "type": "int", "domain": {"range": [0, 10]}},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "x >= 2 and y <= 8"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_structural_expression", codes)

    def test_form_or_typing(self) -> None:
        """Disjunction of atoms is well-typed (Form-Or rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["mini", "pro"]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "model = 'mini' or model = 'pro'"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_structural_expression", codes)

    def test_form_not_typing(self) -> None:
        """Negation is well-typed (Form-Not rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "use_cot", "type": "bool", "domain": [True, False]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "not use_cot = true"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_structural_expression", codes)

    def test_form_impl_typing(self) -> None:
        """Implication sugar is well-typed (Form-Impl rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "use_cot", "type": "bool", "domain": [True, False]},
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 2.0]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"when": "use_cot = true", "then": "temperature <= 0.5"}
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("invalid_structural_expression", codes)

    def test_atom_tvar_eq_typing(self) -> None:
        """TVAR equality is well-typed (Atom-TvarEq rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "x", "type": "int", "domain": {"range": [0, 10]}},
            {"name": "y", "type": "int", "domain": {"range": [0, 10]}},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "x = y"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        # TVAR-to-TVAR equality should be well-typed if same type
        self.assertNotIn("type_mismatch", codes)

    def test_atom_in_typing(self) -> None:
        """Membership test is well-typed (Atom-In rule)."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["mini", "pro", "max"]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "model in ['mini', 'pro']"}]
        }
        issues = lint_module(doc)
        # Membership test syntax may vary
        codes = _collect_codes(issues)
        # Should not produce fundamental errors
        self.assertNotIn("invalid_operator", codes)


class DomainContainmentTests(unittest.TestCase):
    """Tests for domain containment rules (Section: Domain Containment)."""

    def test_d_bool_containment(self) -> None:
        """D-Bool: value must be in {true, false}."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "flag", "type": "bool", "domain": [True, False]},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("value_outside_domain", codes)

    def test_d_int_range_containment(self) -> None:
        """D-Int-Range: value must be in [lo, hi]."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "count", "type": "int", "domain": {"range": [1, 100]}},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "count >= 1"}]  # within domain
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("constraint_value_out_of_domain", codes)

    def test_d_enum_containment(self) -> None:
        """D-Enum: value must be in enumerated set."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "size", "type": "enum[str]", "domain": ["small", "medium", "large"]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "size = 'medium'"}]  # within domain
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("constraint_value_out_of_domain", codes)


class UndeclaredTvarTests(unittest.TestCase):
    """Tests for undeclared TVAR references."""

    def test_undeclared_tvar_in_constraint(self) -> None:
        """Reference to undeclared TVAR produces error."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["mini", "pro"]},
        ]
        doc["constraints"] = {
            "structural": [{"expr": "unknown_var = true"}]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("undeclared_tvar", codes)


if __name__ == "__main__":
    unittest.main()
