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

    def test_malformed_structural_constraint_missing_then_is_flagged(self) -> None:
        """Issue #15: a one-sided `when` (no `then`, no `expr`) must not stay
        lint-clean — it is unenforceable and previously compiled to zero
        constraints while `tvl-lint` reported nothing."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {"structural": [{"when": "temperature = 0.5"}]}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("malformed_structural_constraint", codes)

    def test_malformed_structural_constraint_unknown_key_is_flagged(self) -> None:
        """Issue #15: neither `when`/`then` nor `expr` present (only an
        unrecognised key) must be flagged, not silently skipped."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {"structural": [{"cond": "temperature = 0.5"}]}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("malformed_structural_constraint", codes)

    def test_malformed_structural_constraint_both_shapes_is_flagged(self) -> None:
        """Issue #15: `when`+`then` AND `expr` together violate the schema's
        oneOf and must be flagged, not silently accepted as one of the two."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"when": "temperature > 0.5", "then": "temperature < 1.0", "expr": "temperature != 0.9"},
            ]
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("malformed_structural_constraint", codes)

    def test_wellformed_structural_constraint_not_flagged(self) -> None:
        """Sanity: a well-formed {when, then} entry is not flagged."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}},
        ]
        doc["constraints"] = {
            "structural": [{"when": "temperature > 0.5", "then": "temperature < 1.0"}],
        }
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("malformed_structural_constraint", codes)

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

    def test_duplicate_enum_domain_value_is_flagged(self) -> None:
        """Issue #24 (1/3): a repeated enum domain member must not silently
        collapse into one arm with no diagnostic."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["gpt-4o", "gpt-4o", "llama3.1"]},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("duplicate_domain_value", codes)

    def test_duplicate_numeric_set_domain_value_is_flagged(self) -> None:
        """Issue #24 (1/3), numeric 'set' form of the same duplicate-member gap."""
        doc = _base_module()
        doc["tvars"] = [
            {"name": "batch_size", "type": "int", "domain": {"set": [1, 2, 2, 4]}},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("duplicate_domain_value", codes)

    def test_no_duplicate_domain_value_when_unique(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "model", "type": "enum[str]", "domain": ["gpt-4o", "llama3.1"]},
        ]
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("duplicate_domain_value", codes)

    def _lint_tvar(self, tvar: Dict[str, Any]):
        doc = _base_module()
        doc["tvars"] = [tvar]
        return lint_module(doc)

    def test_duplicate_bare_list_numeric_domain_is_flagged(self) -> None:
        """Issue #202: bare-list int/float domains need the same duplicate check as 'set'."""
        for tvar in (
            {"name": "k", "type": "int", "domain": [0, 1, 1]},
            {"name": "t", "type": "float", "domain": [0.1, 0.1, 0.5]},
            {"name": "k", "type": "int", "domain": [3, 3.0, 4]},
        ):
            with self.subTest(tvar=tvar):
                self.assertIn("duplicate_domain_value", _collect_codes(self._lint_tvar(tvar)))

    def test_duplicate_tuple_component_member_is_flagged(self) -> None:
        """Issue #202: each tuple component list is checked for repeated members."""
        for comp in ({"values": [256, 256, 512]}, {"set": [256, 256]}, [1, 1]):
            with self.subTest(comp=comp):
                issues = self._lint_tvar(
                    {"name": "shape", "type": "tuple[int,int]", "domain": {"components": [comp, {"values": [0, 64]}]}}
                )
                self.assertIn("duplicate_domain_value", _collect_codes(issues))

    def test_unique_numeric_and_tuple_domains_have_no_duplicate_finding(self) -> None:
        for tvar in (
            {"name": "k", "type": "int", "domain": [0, 1, 2]},
            {"name": "t", "type": "float", "domain": {"set": [0.1, 0.5]}},
            {
                "name": "shape",
                "type": "tuple[int,int]",
                "domain": {"components": [{"values": [256, 512]}, {"range": [0, 64]}]},
            },
        ):
            with self.subTest(tvar=tvar):
                codes = _collect_codes(self._lint_tvar(tvar))
                self.assertFalse(codes & {"duplicate_domain_value", "empty_domain", "invalid_range_domain"}, codes)

    def test_int_range_without_an_integer_is_flagged(self) -> None:
        """Issue #203: [1.2, 1.8] holds no integer; tvl-check-structural calls it UNSAT."""
        for bounds in ([1.2, 1.8], [1.5, 1.9]):
            with self.subTest(bounds=bounds):
                issues = self._lint_tvar({"name": "k", "type": "int", "domain": {"range": bounds}})
                self.assertIn("empty_domain", _collect_codes(issues))

    def test_int_range_with_an_integer_is_accepted(self) -> None:
        for bounds in ([1.5, 8], [1, 1], [0, 10], [0.5, 1.5]):
            with self.subTest(bounds=bounds):
                issues = self._lint_tvar({"name": "k", "type": "int", "domain": {"range": bounds}})
                self.assertNotIn("empty_domain", _collect_codes(issues))

    def test_bad_tuple_components_are_flagged(self) -> None:
        """Issue #203: reversed range and empty set components crash tvl-check-structural."""
        cases = {
            "invalid_range_domain": {"range": [64, 0]},
            "empty_domain": {"set": []},
        }
        for code, comp in cases.items():
            with self.subTest(comp=comp):
                issues = self._lint_tvar(
                    {"name": "c", "type": "tuple[int,int]", "domain": {"components": [{"values": [1, 2]}, comp]}}
                )
                matching = [i for i in issues if i["code"] == code]
                self.assertTrue(matching, issues)
                self.assertIn(1, matching[0]["path"])

    def test_nested_tuple_component_is_linted(self) -> None:
        issues = self._lint_tvar(
            {
                "name": "c",
                "type": "tuple[int,int]",
                "domain": {"components": [{"components": [{"values": [1, 1]}]}, {"values": [2]}]},
            }
        )
        self.assertIn("duplicate_domain_value", _collect_codes(issues))

    def test_malformed_tuple_component_range_and_nesting_are_flagged(self) -> None:
        """Shapes check-structural cannot resolve: null/non-numeric/short range, empty nested components."""
        cases = (
            ("invalid_range_domain", {"range": [None, 3]}),
            ("invalid_range_domain", {"range": ["a", 1]}),
            ("invalid_range_domain", {"range": [1]}),
            ("invalid_tuple_domain", {"components": []}),
        )
        for code, comp in cases:
            with self.subTest(comp=comp):
                issues = self._lint_tvar(
                    {"name": "c", "type": "tuple[int,int]", "domain": {"components": [[1, 2], comp]}}
                )
                self.assertIn(code, _collect_codes(issues))

    def test_unusable_range_with_bad_nested_components_reports_both(self) -> None:
        """A reversed range falls through to ``components`` in the model, so both are reported."""
        issues = self._lint_tvar(
            {
                "name": "c",
                "type": "tuple[int,int]",
                "domain": {"components": [[1, 2], {"range": [9, 1], "components": [{"values": [4, 4]}]}]},
            }
        )
        codes = _collect_codes(issues)
        self.assertIn("invalid_range_domain", codes)
        self.assertIn("duplicate_domain_value", codes)

    def test_valid_range_ignores_sibling_components(self) -> None:
        """A usable range wins over ``components`` (model precedence), so nothing is reported."""
        issues = self._lint_tvar(
            {
                "name": "c",
                "type": "tuple[int,int]",
                "domain": {"components": [[1, 2], {"range": [1, 3], "components": [{"values": [4, 4]}]}]},
            }
        )
        self.assertFalse(_collect_codes(issues) & {"duplicate_domain_value", "invalid_range_domain"})

    def test_tuple_component_range_without_an_integer_is_not_empty(self) -> None:
        """The component grid starts at ``lo``, so [1.2, 1.8] is a one-point (or finer) grid, not empty."""
        for comp in ({"range": [1.2, 1.8]}, {"range": [1.2, 1.8], "resolution": 1}):
            with self.subTest(comp=comp):
                issues = self._lint_tvar(
                    {"name": "c", "type": "tuple[int,float]", "domain": {"components": [[1, 2], comp]}}
                )
                self.assertFalse(_collect_codes(issues) & {"empty_domain", "invalid_range_domain"})

    def test_cyclic_tuple_components_terminate(self) -> None:
        """A YAML alias cycle in nested components must not recurse without bound."""
        cyc: Dict[str, Any] = {}
        cyc["components"] = [cyc, {"values": [1, 1]}]
        issues = self._lint_tvar({"name": "c", "type": "tuple[int,int]", "domain": cyc})
        self.assertIn("duplicate_domain_value", _collect_codes(issues))

    def test_deeply_nested_tuple_components_do_not_exhaust_the_stack(self) -> None:
        node: Dict[str, Any] = {"values": [1, 1]}
        for _ in range(5000):
            node = {"components": [node]}
        issues = self._lint_tvar({"name": "c", "type": "tuple[int]", "domain": node})
        self.assertIn("duplicate_domain_value", _collect_codes(issues))

    def test_shared_tuple_components_are_linted_once(self) -> None:
        """An alias DAG (``x: &a [*a_prev, *a_prev]``) must not be walked once per path (2**60 here)."""
        node: Dict[str, Any] = {"values": [1, 1]}
        for _ in range(60):
            node = {"components": [node, node]}
        issues = self._lint_tvar({"name": "c", "type": "tuple[int]", "domain": node})
        found = sum(1 for i in issues if i["code"] == "duplicate_domain_value")
        self.assertTrue(1 <= found <= 2, found)

    def test_orphan_min_effect_key_is_flagged(self) -> None:
        """Issue #24 (3/3): a min_effect key that names no declared objective
        must not be silently accepted (a stale/renamed/typo'd entry)."""
        doc = _base_module()
        doc["objectives"] = [{"name": "quality", "direction": "maximize"}]
        doc["promotion_policy"]["min_effect"] = {"quality": 0.01, "ghost_typo": 0.5}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertIn("unknown_min_effect_objective", codes)

    def test_min_effect_keys_matching_objectives_not_flagged(self) -> None:
        doc = _base_module()
        doc["objectives"] = [{"name": "quality", "direction": "maximize"}]
        doc["promotion_policy"]["min_effect"] = {"quality": 0.01}
        issues = lint_module(doc)
        codes = _collect_codes(issues)
        self.assertNotIn("unknown_min_effect_objective", codes)


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

    def _outside(self, doc):
        return [i for i in lint_module(doc) if i["code"] == "outside_proved_subset"]

    def test_outside_proved_subset_one_warning_per_family(self) -> None:
        for key, decl in (
            ("cvars", {"name": "c1", "type": "float"}),
            ("policies", {"name": "p1", "kind": "cascade"}),
            ("composites", {"name": "k1", "kind": "ensemble"}),
        ):
            doc = _base_module()
            doc[key] = [dict(decl), dict(decl, name=decl["name"] + "b")]
            warns = self._outside(doc)
            self.assertEqual(1, len(warns), key)
            self.assertEqual("info", warns[0]["severity"])
            self.assertEqual(key, warns[0]["construct"])
            self.assertIn(key, warns[0]["message"])
            self.assertIn("proofs/PROOF_SUMMARY.md", warns[0]["message"])

    def test_outside_proved_subset_all_families_three_warnings(self) -> None:
        doc = _base_module()
        doc["cvars"] = [{"name": "c1"}]
        doc["policies"] = [{"name": "p1"}]
        doc["composites"] = [{"name": "k1"}]
        warns = self._outside(doc)
        self.assertEqual(["cvars", "policies", "composites"], [w["construct"] for w in warns])

    def test_outside_proved_subset_not_emitted_for_proved_subset(self) -> None:
        doc = _base_module()
        doc["tvars"] = [{"name": "t", "type": "enum[str]", "domain": ["a", "b"]}]
        self.assertEqual([], self._outside(doc))
        # Empty sections declare no constructs.
        doc["cvars"] = []
        doc["policies"] = []
        doc["composites"] = []
        self.assertEqual([], self._outside(doc))

    def test_callable_domain_not_double_warned(self) -> None:
        doc = _base_module()
        doc["tvars"] = [{"name": "s", "type": "callable[Scorer]", "domain": ["a"]}]
        issues = lint_module(doc)
        self.assertEqual([], [i for i in issues if i["code"] == "outside_proved_subset"])
        self.assertEqual(1, len([i for i in issues if i["code"] == "unverifiable_callable_type"]))

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
        self.assertEqual(10000, precision_warnings[0]["minimum_precision"])
        self.assertEqual(10000, precision_warnings[0]["suggested_precision"])

    def test_precision_suggestion_aligns_values_instead_of_only_separating_them(self) -> None:
        """The suggestion must align decimals exactly, not use ceil(1/min_gap)."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "mixture",
                "type": "float",
                "domain": [0.1, 0.25],
            },
        ]

        issues = lint_module(doc, precision=1)
        precision_warnings = [i for i in issues if i["code"] == "inadequate_precision"]

        self.assertEqual(1, len(precision_warnings))
        self.assertEqual(20, precision_warnings[0]["minimum_precision"])
        self.assertIn("P=20", precision_warnings[0]["message"])

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
        self.assertEqual(10000, precision_warnings[0]["minimum_precision"])

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

    def _precision_warnings(self, domain: Any, precision: int) -> list[Dict[str, Any]]:
        doc = _base_module()
        doc["tvars"] = [{"name": "x", "type": "float", "domain": domain}]
        return [i for i in lint_module(doc, precision=precision) if i["code"] == "inadequate_precision"]

    def test_single_unaligned_value_warns_per_definition_8_6(self) -> None:
        """Definition 8.6: aligned iff v·P ∈ ℤ for every v; 0.0001·1000 = 0.1 is not."""
        warnings = self._precision_warnings([0.0001], 1000)
        self.assertEqual(1, len(warnings))
        self.assertIn("Definition 8.6", warnings[0]["formal_property"])
        self.assertEqual(10000, warnings[0]["suggested_precision"])

    def test_collision_free_but_unaligned_set_warns(self) -> None:
        """{0.1, 0.25} at P=10 scales to {1, 2.5}: no collision, but 2.5 ∉ ℤ."""
        self.assertEqual(1, len(self._precision_warnings({"set": [0.1, 0.25]}, 10)))

    def test_alignment_uses_exact_decimal_arithmetic(self) -> None:
        """0.3·10 is 3.0000000000000004 in binary floating point but 3 exactly."""
        self.assertEqual([], self._precision_warnings([0.1, 0.2, 0.3], 10))
        self.assertEqual([], self._precision_warnings({"range": [0.0, 0.9], "resolution": 0.3}, 10))

    def test_range_with_unaligned_lower_bound_warns(self) -> None:
        """Range values are a + k·r; an aligned r does not align an unaligned a."""
        warnings = self._precision_warnings({"range": [0.05, 1.0], "resolution": 0.1}, 10)
        self.assertEqual(1, len(warnings))

    def test_range_without_resolution_uses_effective_resolution(self) -> None:
        """Semantics §2.4: an omitted float resolution is 0.001, which P=100 does not align."""
        self.assertEqual(1, len(self._precision_warnings({"range": [0.0, 1.0]}, 100)))
        self.assertEqual([], self._precision_warnings({"range": [0.0, 1.0]}, 1000))


if __name__ == "__main__":
    unittest.main()
