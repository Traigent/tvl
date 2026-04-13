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
    "tvl.structural_sat",
    package_path / "structural_sat.py",
    submodule_search_locations=[str(package_path)],
)
module = importlib.util.module_from_spec(spec)
sys.modules["tvl.structural_sat"] = module
assert spec.loader is not None
spec.loader.exec_module(module)

check_structural = module.check_structural


def _base_module() -> Dict[str, Any]:
    return {
        "tvl": {"module": "corp.validation.test"},
        "tvl_version": "1.0",
        "environment": {"snapshot_id": "2025-01-01T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/dev.parquet"},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"quality": 0.0}},
        "exploration": {"strategy": {"type": "grid"}},
    }


class StructuralSatTests(unittest.TestCase):
    def test_structural_satisfiable(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 5]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "max_calls >= 2"},
                {"expr": "max_calls <= 4"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.assignment)
        self.assertGreaterEqual(result.assignment["max_calls"], 2)
        self.assertLessEqual(result.assignment["max_calls"], 4)

    def test_structural_unsat_core(self) -> None:
        doc = _base_module()
        doc["tvars"] = [
            {"name": "max_calls", "type": "int", "domain": {"range": [0, 5]}},
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "max_calls >= 3"},
                {"expr": "max_calls <= 1"},
            ]
        }

        result = check_structural(doc)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.unsat_core)
        paths = {".".join(str(p) for p in entry["path"]) for entry in result.unsat_core or []}
        self.assertEqual(paths, {"constraints.structural.0", "constraints.structural.1"})


    def test_tuple_equality_with_components(self) -> None:
        """Tuple constraint with component-product domain is satisfiable."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "config",
                "type": "tuple[int, int]",
                "domain": {
                    "components": [
                        {"values": [1, 2, 3]},
                        {"values": [10, 20]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "config == (2, 20)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["config"], (2, 20))

    def test_tuple_equality_unsat(self) -> None:
        """Tuple constraint with value outside domain is unsatisfiable."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "config",
                "type": "tuple[int, int]",
                "domain": {
                    "components": [
                        {"values": [1, 2]},
                        {"values": [10, 20]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "config == (3, 10)"},
            ]
        }

        result = check_structural(doc)
        self.assertFalse(result.ok)

    def test_tuple_range_components(self) -> None:
        """Tuple domain with range-based components enumerates correctly."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "pair",
                "type": "tuple[int, int]",
                "domain": {
                    "components": [
                        {"range": [1, 3]},
                        {"range": [10, 11]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "pair == (2, 11)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["pair"], (2, 11))

    def test_float_non_grid_equality_unsat(self) -> None:
        """Float equality with non-grid value should be statically false."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "temp",
                "type": "float",
                "domain": {"range": [0.0, 1.0], "resolution": 0.1},
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "temp == 0.15"},
            ]
        }

        result = check_structural(doc)
        self.assertFalse(result.ok)

    def test_float_grid_equality_sat(self) -> None:
        """Float equality with grid-aligned value should be satisfiable."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "temp",
                "type": "float",
                "domain": {"range": [0.0, 1.0], "resolution": 0.1},
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "temp == 0.5"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.assignment["temp"], 0.5, places=5)


    def test_tuple_boolean_components(self) -> None:
        """Tuple containing boolean values parses and matches correctly."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "flags",
                "type": "tuple[bool, int]",
                "domain": {
                    "components": [
                        {"values": [True, False]},
                        {"values": [1, 2]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "flags == (true, 2)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["flags"], (True, 2))

    def test_tuple_nested(self) -> None:
        """Nested tuple literal like ((1, 2), 5) is parsed correctly."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "nested",
                "type": "tuple",
                "domain": {
                    "components": [
                        {"values": [(1, 2), (3, 4)]},
                        {"values": [5, 6]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "nested == ((1, 2), 5)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["nested"], ((1, 2), 5))

    def test_tuple_float_range_components(self) -> None:
        """Tuple with float range + resolution enumerates grid points."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "mixed",
                "type": "tuple[float, int]",
                "domain": {
                    "components": [
                        {"range": [0.1, 0.3], "resolution": 0.1},
                        {"values": [10, 20]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "mixed == (0.2, 20)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["mixed"], (0.2, 20))

    def test_tuple_float_range_no_resolution_raises(self) -> None:
        """Float range without resolution on tuple component raises ValueError."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "bad",
                "type": "tuple[float, int]",
                "domain": {
                    "components": [
                        {"range": [0.1, 0.5]},
                        {"values": [1]},
                    ]
                },
            },
        ]
        with self.assertRaises(ValueError) as ctx:
            check_structural(doc)
        self.assertIn("resolution", str(ctx.exception))

    def test_tuple_string_true_not_coerced_to_bool(self) -> None:
        """Quoted string 'true' in a tuple stays a string, not boolean True."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple[str, int]",
                "domain": {
                    "components": [
                        {"values": ["true", "false", "maybe"]},
                        {"values": [1, 2]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("true", 1)'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ("true", 1))

    def test_tuple_string_number_not_coerced_to_int(self) -> None:
        """Quoted string '1' in a tuple stays a string, not int 1."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple[str, str]",
                "domain": {
                    "components": [
                        {"values": ["1", "2", "3"]},
                        {"values": ["a", "b"]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("1", "b")'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ("1", "b"))

    def test_tuple_string_with_comma_preserved(self) -> None:
        """Quoted string containing a comma is not split into two elements."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple[str, int]",
                "domain": {
                    "components": [
                        {"values": ["a,b", "c"]},
                        {"values": [1]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("a,b", 1)'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ("a,b", 1))

    def test_tuple_string_with_escaped_quote(self) -> None:
        """Quoted string containing an escaped quote round-trips correctly."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple[str, int]",
                "domain": {
                    "components": [
                        {"values": ['a"b', "c"]},
                        {"values": [1]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("a\\"b", 1)'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ('a"b', 1))

    def test_tuple_string_with_escaped_backslash(self) -> None:
        """Quoted string containing a literal backslash round-trips correctly."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple[str, int]",
                "domain": {
                    "components": [
                        {"values": ["a\\b", "c"]},
                        {"values": [1]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("a\\\\b", 1)'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ("a\\b", 1))

    def test_tuple_nested_component_domain_spec(self) -> None:
        """Nested `components` inside a tuple component are enumerated recursively."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple",
                "domain": {
                    "components": [
                        {
                            "components": [
                                {"values": [1, 2]},
                                {"values": [10]},
                            ]
                        },
                        {"values": [5]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": "cfg == ((2, 10), 5)"},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ((2, 10), 5))

    def test_tuple_registry_component_placeholder_value(self) -> None:
        """Registry-backed tuple components remain representable via placeholders."""
        doc = _base_module()
        doc["tvars"] = [
            {
                "name": "cfg",
                "type": "tuple",
                "domain": {
                    "components": [
                        {"registry": "corp.models"},
                        {"values": [1]},
                    ]
                },
            },
        ]
        doc["constraints"] = {
            "structural": [
                {"expr": 'cfg == ("__registry_unresolved_0__", 1)'},
            ]
        }

        result = check_structural(doc)
        self.assertTrue(result.ok)
        self.assertEqual(result.assignment["cfg"], ("__registry_unresolved_0__", 1))


if __name__ == "__main__":
    unittest.main()
