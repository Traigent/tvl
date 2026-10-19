"""Schema and lint agree on the numeric validation boundaries."""

import copy
from pathlib import Path

import pytest
import yaml
from tvl.lints import lint_module
from tvl.schema import validator

ROOT = Path(__file__).resolve().parents[1]
BASE = yaml.safe_load((ROOT / "spec/examples/rag-support-bot.tvl.yml").read_text())


@pytest.mark.parametrize("field,value", [
    ("threshold", -0.1), ("threshold", 5),
    ("confidence", 0), ("confidence", 1),
])
def test_chance_bounds_reject_in_schema_and_lint(field, value):
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["chance_constraints"][0][field] = value
    assert list(validator().iter_errors(doc))
    assert f"invalid_chance_{field}" in {i["code"] for i in lint_module(doc)}


@pytest.mark.parametrize("field,value", [("threshold", 0), ("threshold", 1), ("confidence", 0.5)])
def test_chance_bound_controls(field, value):
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["chance_constraints"][0][field] = value
    assert not list(validator().iter_errors(doc))
    assert not [i for i in lint_module(doc) if i.get("severity") == "error"]


@pytest.mark.parametrize("field", ["tol", "alpha"])
def test_banded_objective_zero_rejected(field):
    doc = copy.deepcopy(BASE)
    band = {"target": {"center": 1, "tol": 0.1}, "test": "TOST", "alpha": 0.05}
    if field == "tol":
        band["target"]["tol"] = 0
    else:
        band["alpha"] = 0
    doc["objectives"] = [{"name": "quality", "band": band}]
    assert list(validator().iter_errors(doc))
    assert [i for i in lint_module(doc) if i.get("severity") == "error"]


@pytest.mark.parametrize("missing", ["strategy", "window", "threshold"])
def test_exploration_required_fields(missing):
    doc = copy.deepcopy(BASE)
    if missing == "strategy":
        doc["exploration"].pop(missing)
    else:
        doc["exploration"]["convergence"].pop(missing)
    assert list(validator().iter_errors(doc))
    assert [i for i in lint_module(doc) if i.get("severity") == "error"]


def test_hypervolume_zero_threshold_rejected():
    doc = copy.deepcopy(BASE)
    doc["exploration"]["convergence"]["threshold"] = 0
    assert list(validator().iter_errors(doc))
    assert "invalid_convergence_threshold" in {i["code"] for i in lint_module(doc)}


def test_absent_and_null_exploration_stay_valid():
    for value in (None, "absent"):
        doc = copy.deepcopy(BASE)
        if value == "absent":
            doc.pop("exploration")
        else:
            doc["exploration"] = value
        assert not list(validator().iter_errors(doc))


def test_missing_min_effect_remains_a_documented_lint_boundary():
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["min_effect"].pop("quality")
    assert not list(validator().iter_errors(doc))
    assert "missing_min_effect" in {i["code"] for i in lint_module(doc)}
