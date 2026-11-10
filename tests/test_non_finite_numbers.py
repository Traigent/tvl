"""Issue #252: NaN and infinity are not valid bounds, budgets, effects or measurements.

Every comparison with NaN is false, so checks written in rejecting form
(``x < 0``, ``observed > high``) let NaN through as valid.
"""

import copy
import math
from pathlib import Path

import numpy as np
import pytest
import yaml
from tvl.lints import lint_module
from tvl.measurement import validate_measurement
from tvl.operational import check_operational

ROOT = Path(__file__).resolve().parents[1]
MODULE = yaml.safe_load((ROOT / "spec/examples/agent-router.tvl.yml").read_text())
CONFIG = yaml.safe_load((ROOT / "spec/configurations/agent-router.config.yml").read_text())
MEASUREMENT = yaml.safe_load((ROOT / "spec/measurements/agent-router.measure.yml").read_text())
NON_FINITE = [math.nan, math.inf, -math.inf]
IDS = ["nan", "inf", "-inf"]


def _banded(target):
    doc = copy.deepcopy(MODULE)
    for obj in doc["objectives"]:
        if obj["name"] == "routing_latency_ms":
            obj.pop("direction", None)
            obj["band"] = {"target": target, "test": "TOST", "alpha": 0.05}
            break
    else:  # pragma: no cover - fixture guard
        raise AssertionError("routing_latency_ms objective missing")
    doc["promotion_policy"]["min_effect"].pop("routing_latency_ms", None)
    return doc


def _errors(doc):
    return {i["code"] for i in lint_module(doc) if i["severity"] == "error"}


def test_finite_fixtures_are_clean():
    assert not _errors(MODULE)
    assert not _errors(_banded([100, 900]))
    assert not _errors(_banded({"center": 500, "tol": 400}))


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
@pytest.mark.parametrize(
    "target,code",
    [
        (lambda v: [100, v], "invalid_band_target"),
        (lambda v: [v, 900], "invalid_band_target"),
        (lambda v: {"center": v, "tol": 10}, "invalid_band_center_tol"),
        (lambda v: {"center": 500, "tol": v}, "invalid_band_center_tol"),
    ],
    ids=["high", "low", "center", "tol"],
)
def test_lint_rejects_non_finite_band(target, code, bad):
    assert code in _errors(_banded(target(bad)))


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
def test_lint_rejects_non_finite_min_effect(bad):
    doc = copy.deepcopy(MODULE)
    name = next(iter(doc["promotion_policy"]["min_effect"]))
    doc["promotion_policy"]["min_effect"][name] = bad
    assert "invalid_min_effect" in _errors(doc)


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
def test_lint_rejects_non_finite_convergence_threshold(bad):
    doc = copy.deepcopy(MODULE)
    doc["exploration"]["convergence"]["threshold"] = bad
    assert "invalid_convergence_threshold" in _errors(doc)


@pytest.mark.parametrize("bad", NON_FINITE + [-1], ids=IDS + ["negative"])
def test_lint_rejects_invalid_max_spend(bad):
    doc = copy.deepcopy(MODULE)
    doc["exploration"]["budgets"]["max_spend_usd"] = bad
    assert "invalid_budget_max_spend" in _errors(doc)


@pytest.mark.parametrize("ok", [0, 12.5])
def test_lint_accepts_finite_max_spend(ok):
    doc = copy.deepcopy(MODULE)
    doc["exploration"]["budgets"]["max_spend_usd"] = ok
    assert "invalid_budget_max_spend" not in _errors(doc)


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
def test_operational_rejects_non_finite_max_spend(bad):
    doc = copy.deepcopy(MODULE)
    doc["exploration"]["budgets"]["max_spend_usd"] = bad
    codes = {i["code"] for i in check_operational(doc).issues}
    assert "invalid_budget_max_spend" in codes


def _measure(module, mean):
    meas = copy.deepcopy(MEASUREMENT)
    meas["objective_values"]["routing_latency_ms"]["mean"] = mean
    return validate_measurement(module, CONFIG, meas)


def test_measurement_band_control():
    module = _banded([100, 900])
    assert _measure(module, 780)["ok"]
    assert not _measure(module, 5000)["ok"]


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
def test_measurement_rejects_non_finite_observed(bad):
    report = _measure(_banded([100, 900]), bad)
    assert not report["ok"]
    assert {"routing_latency_ms"} == {i["objective"] for i in report["operational"]}


@pytest.mark.parametrize("bad", NON_FINITE, ids=IDS)
def test_measurement_rejects_non_finite_samples(bad):
    meas = copy.deepcopy(MEASUREMENT)
    meas["objective_values"]["routing_latency_ms"] = {"samples": [700, bad, 800]}
    report = validate_measurement(_banded([100, 900]), CONFIG, meas)
    assert not report["ok"]


@pytest.mark.parametrize(
    "target",
    [[100, math.nan], [math.nan, 900], {"center": 500, "tol": math.nan}, {"center": math.nan, "tol": 400}],
    ids=["high", "low", "tol", "center"],
)
def test_measurement_band_with_nan_bound_is_not_satisfied(target):
    assert not _measure(_banded(target), 5000)["ok"]
    assert not _measure(_banded(target), 500)["ok"]


def test_measurement_band_with_numpy_float32_nan_bound_is_not_satisfied():
    # Control: a Python float NaN bound. Red case: a numpy scalar NaN bound, which is
    # not a float subclass; both must be reported as violations.
    assert not _measure(_banded([math.nan, 900]), 500)["ok"]
    assert not _measure(_banded([np.float32("nan"), 900]), 500)["ok"]
    assert not _measure(_banded([100, np.float32("nan")]), 500)["ok"]
