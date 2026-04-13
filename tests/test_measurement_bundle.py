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


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        package_path / relative_path,
        submodule_search_locations=[str(package_path)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


measurement_module = _load_module("tvl.measurement", "measurement.py")

prepare_measurement_bundle = measurement_module.prepare_measurement_bundle
validate_measurement = measurement_module.validate_measurement


def _base_module() -> Dict[str, Any]:
    return {
        "tvl": {"module": "corp.validation.measurement"},
        "tvl_version": "1.0",
        "environment": {"snapshot_id": "2025-01-01T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/dev.parquet"},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {
            "dominance": "epsilon_pareto",
            "alpha": 0.05,
            "min_effect": {"quality": 0.0},
            "chance_constraints": [
                {"name": "latency_slo", "threshold": 0.05, "confidence": 0.95},
            ],
        },
        "exploration": {"strategy": {"type": "grid"}},
    }


def _base_config() -> Dict[str, Any]:
    return {
        "module_id": "corp.validation.measurement",
        "assignments": {},
    }


class MeasurementBundleTests(unittest.TestCase):
    def test_prepare_measurement_bundle_canonical_ready(self) -> None:
        module = _base_module()
        measurement = {
            "objective_values": {
                "quality": {"mean": 0.82, "std": 0.04, "n": 100},
            },
            "chance_outcomes": {
                "latency_slo": {"violations": 1, "trials": 100},
            },
        }

        normalized, warnings, readiness = prepare_measurement_bundle(module, measurement)
        self.assertEqual({}, normalized.get("legacy_objectives", {}))
        self.assertFalse(warnings)
        self.assertFalse(readiness)

    def test_prepare_measurement_bundle_legacy_warns(self) -> None:
        module = _base_module()
        measurement = {
            "objectives": {
                "quality": {"observed": 0.82, "delta": 0.02, "p_value": 0.01},
            },
            "chance": {
                "latency_slo": {"observed": 0.01, "trials": 100},
            },
            "summary": {"trials": 100},
        }

        normalized, warnings, readiness = prepare_measurement_bundle(module, measurement)
        warning_codes = {warning["code"] for warning in warnings}
        readiness_codes = {issue["code"] for issue in readiness}

        self.assertIn("deprecated_measurement_objectives", warning_codes)
        self.assertIn("deprecated_measurement_chance", warning_codes)
        self.assertEqual({"violations": 1, "trials": 100}, normalized["chance_outcomes"]["latency_slo"])
        self.assertIn("missing_statistical_evidence", readiness_codes)
        self.assertNotIn("missing_chance_counts", readiness_codes)

    @unittest.skipUnless(measurement_module.SCIPY_AVAILABLE, "scipy not available")
    def test_validate_measurement_uses_violation_rate_gate(self) -> None:
        module = _base_module()
        config = _base_config()
        measurement = {
            "objective_values": {
                "quality": {"mean": 0.82, "std": 0.04, "n": 100},
            },
            "chance_outcomes": {
                "latency_slo": {"violations": 8, "trials": 100},
            },
        }

        report = validate_measurement(module, config, measurement)
        self.assertFalse(report["ok"])
        self.assertFalse(report["chance"] == [])
        self.assertEqual("chance_violation", report["chance"][0]["code"])


if __name__ == "__main__":
    unittest.main()
