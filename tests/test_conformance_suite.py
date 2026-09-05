from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tvl.configuration import load_configuration, validate_configuration
from tvl.loader import load
from tvl.measurement import load_measurement, validate_measurement
from tvl.promotion import SCIPY_AVAILABLE, epsilon_pareto_gate
from tvl.structural_sat import check_structural


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "conformance" / "cases"
EXPECTED = json.loads((ROOT / "conformance" / "expected" / "results.json").read_text())


@pytest.mark.parametrize(
    "relative_path",
    [
        "satisfiable/minimal.yml",
        "satisfiable/banded-target.yml",
        "unsatisfiable/conflicting-implications.yml",
    ],
)
def test_module_conformance(relative_path: str) -> None:
    module = load(CASES / relative_path)

    assert check_structural(module).ok is EXPECTED[relative_path]["structural_ok"]


def _resolve_case_paths(relative_path: str) -> tuple[dict, Path]:
    case_path = CASES / relative_path
    case = yaml.safe_load(case_path.read_text())
    return case, case_path.parent


def test_configuration_conformance() -> None:
    relative_path = "configurations/valid.yml"
    case, base = _resolve_case_paths(relative_path)
    module = load((base / case["module"]).resolve())
    config = load_configuration((base / case["config"]).resolve())

    assert validate_configuration(module, config)["ok"] is EXPECTED[relative_path]["config_ok"]


def test_measurement_conformance() -> None:
    relative_path = "measurements/valid.yml"
    case, base = _resolve_case_paths(relative_path)
    module = load((base / case["module"]).resolve())
    config = load_configuration((base / case["config"]).resolve())
    measurement = load_measurement((base / case["measurement"]).resolve())

    assert validate_measurement(module, config, measurement)["ok"] is EXPECTED[relative_path]["measurement_ok"]


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy not available")
def test_chance_constraint_gate_conformance() -> None:
    relative_path = "gate/chance-constraint-pass-fail.yml"
    case = yaml.safe_load((CASES / relative_path).read_text())
    module = case["module"]

    for candidate_name in ("passing_candidate", "failing_candidate"):
        decision, _evidence = epsilon_pareto_gate(
            case["incumbent"],
            case[candidate_name],
            module["promotion_policy"],
            module["objectives"],
        )
        assert decision == EXPECTED[relative_path][candidate_name]
