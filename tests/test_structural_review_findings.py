"""Regressions for the 2026-10-24 independent code review (findings 1-5)."""

from __future__ import annotations

import sys
import tracemalloc
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402
from tvl.yaml_safe import DuplicateKeyError, safe_load  # noqa: E402

HAVE_CPSAT = structural_sat.cp_model is not None


@pytest.fixture(params=["cpsat", "fallback"])
def solver(request, monkeypatch):
    if request.param == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif not HAVE_CPSAT:
        pytest.skip("ortools missing")
    return request.param


def _mod(tvars, exprs):
    return {"tvars": tvars, "constraints": {"structural": [{"expr": e} for e in exprs]}}


def _exact(v):
    return v.exact if hasattr(v, "exact") else Fraction(repr(float(v))) if isinstance(v, float) else Fraction(v)


# 1. off-grid equality ----------------------------------------------------------
def test_offgrid_equality_is_never_sat(solver):
    module = _mod(
        [{"name": "x", "type": "float", "domain": {"range": [0.1, 1000.0], "resolution": 0.3}}],
        ["x == 0.40000000000001"],
    )
    result = check_structural(module)
    assert result.ok is False


def test_offgrid_inequality_holds_on_every_point(solver):
    module = _mod(
        [{"name": "x", "type": "float", "domain": {"range": [0.1, 1.0], "resolution": 0.3}}],
        ["x != 0.40000000000001"],
    )
    assert check_structural(module).ok is True


# 2. exact witnesses --------------------------------------------------------------
def test_exact_witness_not_lossy(solver):
    module = _mod(
        [
            {"name": "x", "type": "float", "domain": {"range": [1.0e-18, 1.0], "resolution": 0.1}},
            {"name": "y", "type": "float", "domain": {"range": [0.1, 0.1], "resolution": 0.001}},
        ],
        ["x > 0.05 and x < 0.15 and x != y"],
    )
    result = check_structural(module)
    assert result.ok is True
    x, y = _exact(result.assignment["x"]), _exact(result.assignment["y"])
    assert Fraction(5, 100) < x < Fraction(15, 100) and x != y


# 3. overflow / status ------------------------------------------------------------
def test_encoding_overflow_is_undecided_not_unsat():
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    module = _mod(
        [
            {"name": "x", "type": "float", "domain": {"range": [0.0000000001, 1.0], "resolution": 0.3}},
            {"name": "y", "type": "float", "domain": {"range": [0.0, 1000000000.0], "resolution": 1.0}},
        ],
        ["x != y"],
    )
    result = check_structural(module)
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert result.issues[0]["code"] == "structural_encoding_overflow"
    assert result.issues[0]["severity"] == "error"
    assert result.unsat_core is None


def test_only_infeasible_status_yields_unsat(monkeypatch):
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")

    class FakeSolver:
        def SolveWithAssumptions(self, model, lits):
            return structural_sat.cp_model.MODEL_INVALID

        def Solve(self, model):
            return structural_sat.cp_model.MODEL_INVALID

    monkeypatch.setattr(structural_sat.cp_model, "CpSolver", FakeSolver)
    module = _mod([{"name": "n", "type": "int", "domain": {"range": [0, 5]}}], ["n = 3"])
    result = check_structural(module)
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert result.unsat_core is None


# 4. exhaustiveness must not materialise ranges ----------------------------------
def test_exhaustiveness_check_does_not_allocate_range(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    module = _mod([{"name": "x", "type": "int", "domain": {"range": [0, 3_000_000]}}], ["x < 0"])
    tracemalloc.start()
    try:
        result = check_structural(module)
        _cur, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.ok is False and getattr(result, "undecided", False) is True
    assert peak < 20_000_000


# 5. duplicate keys inside merge sources -----------------------------------------
def test_duplicate_in_inline_merge_source_rejected():
    with pytest.raises(DuplicateKeyError):
        safe_load("promotion_policy:\n  <<: {alpha: 0.05, alpha: 0.1}\n")


def test_duplicate_in_inline_source_inside_merge_list_rejected():
    text = "base: &x {a: 1}\nd:\n  <<: [*x, {b: 1, b: 2}]\n"
    with pytest.raises(DuplicateKeyError):
        safe_load(text)


def test_explicit_key_overriding_merged_key_still_allowed():
    doc = safe_load("base: &b {x: 1, y: 2}\nd:\n  <<: *b\n  y: 3\n")
    assert doc["d"] == {"x": 1, "y": 3}


# Strict float comparisons must not exclude satisfying grid points (found while fixing 1-3;
# the double offset predates this branch).
def test_strict_float_comparison_keeps_satisfying_points():
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    module = _mod(
        [{"name": "t", "type": "float", "domain": {"range": [0, 1], "resolution": 0.1}}],
        ["t > 0.25", "t < 0.35"],
    )
    result = check_structural(module)
    assert result.ok is True
    assert _exact(result.assignment["t"]) == Fraction(3, 10)
