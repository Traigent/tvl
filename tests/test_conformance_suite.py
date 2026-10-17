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


RUNTIME_CASES_DIR = CASES / "runtime"
RUNTIME_CASE_PATHS = [p.relative_to(RUNTIME_CASES_DIR).as_posix() for p in sorted(RUNTIME_CASES_DIR.rglob("*.yml"))]

@pytest.mark.parametrize("relative_case_path", RUNTIME_CASE_PATHS)
def test_runtime_conformance_case(relative_case_path):
    from tvl.runtime_conformance import run_runtime_conformance_case
    from tvl.yaml_safe import safe_load
    case = RUNTIME_CASES_DIR / relative_case_path
    run_runtime_conformance_case(safe_load(case.read_text()), case_path=case)


def test_language_families_present_and_all_cases_mapped():
    from tvl.runtime_conformance import LANGUAGE_FAMILY_GLOBS
    for family, globs in LANGUAGE_FAMILY_GLOBS.items():
        assert any(any(Path(p).match(g) for g in globs) for p in RUNTIME_CASE_PATHS), family
    for p in RUNTIME_CASE_PATHS:
        assert any(Path(p).match(g) for globs in LANGUAGE_FAMILY_GLOBS.values() for g in globs), p


def test_runtime_fixture_checker():
    import importlib.util
    path = ROOT / "conformance/tools/check_runtime_cases.py"
    spec = importlib.util.spec_from_file_location("public_fixture_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
