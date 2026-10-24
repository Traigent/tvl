"""Definition 3.6 range enumeration (floor) and T-Cmp ordering on numeric enums."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.lints import lint_module  # noqa: E402
from tvl.model import _resolve_range_values  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402


def test_range_floor_not_round():
    assert _resolve_range_values("t", 0, {"range": [0, 1], "resolution": 0.6}) == [0.0, 0.6]


def test_range_float_tolerance_keeps_endpoint():
    vals = _resolve_range_values("t", 0, {"range": [0, 1], "resolution": 0.1})
    assert len(vals) == 11 and vals[0] == 0.0 and vals[-1] == 1.0


def test_integer_range_unchanged():
    assert _resolve_range_values("t", 0, {"range": [2, 5]}) == [2, 3, 4, 5]


def _module(tvars, exprs):
    return {"tvars": tvars, "constraints": {"structural": [{"expr": e} for e in exprs]}}


def _codes(module):
    out = []
    for i in lint_module(module):
        out.append(i["code"] if isinstance(i, dict) else i.code)
    return out


NUM_ENUM = [{"name": "t", "type": "enum[float]", "domain": {"set": [0.0, 0.5, 1.0]}}]
INT_ENUM = [{"name": "k", "type": "enum[int]", "domain": {"set": [1, 2, 3]}}]
STR_ENUM = [{"name": "m", "type": "enum[str]", "domain": {"set": ["a", "b"]}}]


@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_lint_allows_ordering_on_numeric_enums(op):
    assert "constraint_operator_type_mismatch" not in _codes(_module(NUM_ENUM, [f"t {op} 0.5"]))
    assert "constraint_operator_type_mismatch" not in _codes(_module(INT_ENUM, [f"k {op} 2"]))


def test_lint_rejects_ordering_on_string_enum():
    assert "constraint_operator_type_mismatch" in _codes(_module(STR_ENUM, ["m < 'b'"]))


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_structural_encodes_numeric_enum_ordering(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif structural_sat.cp_model is None:
        pytest.skip("ortools missing")
    sat = check_structural(_module(NUM_ENUM, ["t > 0.2", "t < 0.8"]))
    assert sat.ok and sat.assignment == {"t": 0.5}
    unsat = check_structural(_module(NUM_ENUM, ["t > 0.5", "t < 1.0"]))
    assert unsat.ok is False
    isat = check_structural(_module(INT_ENUM, ["k >= 2", "k <= 2"]))
    assert isat.ok and isat.assignment == {"k": 2}


def test_tuple_float_range_defaults_to_0_001_resolution():
    vals = _resolve_range_values("t", 0, {"range": [0.0, 0.01]})
    assert vals == [0.0, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.01]


def test_tuple_int_range_steps_by_one_without_resolution():
    assert _resolve_range_values("t", 0, {"range": [0, 3]}) == [0, 1, 2, 3]
