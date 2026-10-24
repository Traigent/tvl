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


# ---- interval on numeric enums -------------------------------------------------

def test_lint_allows_interval_on_numeric_enum_rejects_string():
    assert "constraint_operator_type_mismatch" not in _codes(_module(NUM_ENUM, ["0.1 <= t <= 0.9"]))
    assert "constraint_operator_type_mismatch" in _codes(_module(STR_ENUM, ["1 <= m <= 2"]))


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_structural_encodes_numeric_enum_interval(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif structural_sat.cp_model is None:
        pytest.skip("ortools missing")
    sat = check_structural(_module(NUM_ENUM, ["0.1 <= t <= 0.9"]))
    assert sat.ok and sat.assignment == {"t": 0.5}
    unsat = check_structural(_module(NUM_ENUM, ["0.6 <= t <= 0.9"]))
    assert unsat.ok is False


# ---- tuple equality typing -----------------------------------------------------

def _tuple_module(t1, t2):
    return {
        "tvars": [
            {"name": "a", "type": t1, "domain": {"components": [{"values": [1]}] * (t1.count(",") + 1)}},
            {"name": "b", "type": t2, "domain": {"components": [{"values": [1]}] * (t2.count(",") + 1)}},
        ],
        "constraints": {"structural": [{"expr": "a = b"}]},
    }


def test_tuple_equality_arity_mismatch_rejected():
    assert "constraint_type_mismatch" in _codes(_tuple_module("tuple[int, int]", "tuple[int, int, int]"))


def test_tuple_equality_component_mismatch_rejected():
    assert "constraint_type_mismatch" in _codes(_tuple_module("tuple[int, str]", "tuple[int, bool]"))


def test_tuple_equality_matching_accepted():
    assert "constraint_type_mismatch" not in _codes(_tuple_module("tuple[int, str]", "tuple[int, str]"))
    assert "constraint_type_mismatch" not in _codes(_tuple_module("tuple[int, str]", "tuple[ int,str ]"))


def test_tuple_equality_int_float_component_rejected():
    """T-TupleVarEq: both sides have type tuple[τ₁,...,τₙ]; int and float components differ."""
    assert "constraint_type_mismatch" in _codes(_tuple_module("tuple[int, str]", "tuple[float, str]"))
    assert "constraint_type_mismatch" in _codes(_tuple_module("tuple[int]", "tuple[float]"))


def _scalar_eq_module(t1, d1, t2, d2):
    return _module([{"name": "a", "type": t1, "domain": d1}, {"name": "b", "type": t2, "domain": d2}], ["a = b"])


@pytest.mark.parametrize(
    "t1,d1,t2,d2",
    [
        ("int", [1, 2], "float", [1.0, 2.0]),
        ("enum[str]", ["x", "y"], "enum[int]", [1, 2]),
        ("enum[int]", [1, 2], "enum[float]", [1.0, 2.0]),
        ("int", [1, 2], "enum[float]", [1.0, 2.0]),
    ],
)
def test_scalar_tvar_equality_requires_equal_element_types(t1, d1, t2, d2):
    """T-TVarEq: x = y is well-typed only when elem(τ) = elem(τ') (semantics §4.6)."""
    assert "constraint_type_mismatch" in _codes(_scalar_eq_module(t1, d1, t2, d2))


@pytest.mark.parametrize(
    "t1,d1,t2,d2",
    [
        ("int", [1, 2], "int", [2, 3]),
        ("int", [1, 2], "enum[int]", [1, 2]),
        ("enum[str]", ["x", "y"], "enum[str]", ["y", "z"]),
        ("float", [0.1, 0.2], "enum[float]", [0.1]),
    ],
)
def test_scalar_tvar_equality_with_equal_element_types_accepted(t1, d1, t2, d2):
    assert "constraint_type_mismatch" not in _codes(_scalar_eq_module(t1, d1, t2, d2))


# ---- exact Definition 3.6 float grid -------------------------------------------

def _fmod(lo, hi, res, exprs):
    return _module(
        [{"name": "t", "type": "float", "domain": {"range": [lo, hi], "resolution": res}}], exprs
    )


GRID_CASES = [
    # (lo, hi, res, exprs, expected_ok, expected_assignment_or_None)
    (0, 1, 0.3, ["t >= 0.95"], False, None),          # grid {0, .3, .6, .9}
    (0, 1, 0.3, ["t >= 0.85"], True, 0.9),
    (0, 1, 0.25, ["t > 0.75", "t < 1.0"], False, None),
    (0, 1, 0.25, ["t >= 0.75", "t <= 0.75"], True, 0.75),
    (0, 1, 0.1, ["t >= 1.0"], True, 1.0),
]


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
@pytest.mark.parametrize("lo,hi,res,exprs,ok,val", GRID_CASES)
def test_exact_float_grid(monkeypatch, solver, lo, hi, res, exprs, ok, val):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif structural_sat.cp_model is None:
        pytest.skip("ortools missing")
    result = check_structural(_fmod(lo, hi, res, exprs))
    assert result.ok is ok
    assert not getattr(result, "undecided", False)
    if ok and val is not None:
        assert result.assignment["t"] == pytest.approx(val)


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_exact_float_grid_nonzero_origin(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif structural_sat.cp_model is None:
        pytest.skip("ortools missing")
    # grid {0.15, 0.35, 0.55, 0.75, 0.95}: 0.5 <= t <= 0.6 -> 0.55; t >= 0.96 -> UNSAT
    sat = check_structural(_fmod(0.15, 1.0, 0.2, ["t >= 0.5", "t <= 0.6"]))
    assert sat.ok and sat.assignment["t"] == pytest.approx(0.55)
    assert check_structural(_fmod(0.15, 1.0, 0.2, ["t >= 0.96"])).ok is False
