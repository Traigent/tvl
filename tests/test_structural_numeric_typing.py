"""The structural checker types int and float apart, as the linter and T-TVarEq/T-Eq do."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.lints import lint_module  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402

INT_X = {"name": "i", "type": "int", "domain": {"range": [0, 5]}}
FLOAT_Y = {"name": "f", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": 0.5}}


def _module(tvars, expr):
    return {"tvars": tvars, "constraints": {"structural": [{"expr": expr}]}}


def _lint_codes(module):
    return {(i["code"] if isinstance(i, dict) else i.code) for i in lint_module(module)}


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
@pytest.mark.parametrize(
    "tvars, expr",
    [
        ([INT_X, FLOAT_Y], "i == f"),
        ([INT_X], "i == 2.5"),
        ([INT_X], "i < 2.5"),
    ],
)
def test_ill_typed_numeric_atoms_are_refused(monkeypatch, solver, tvars, expr):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    module = _module(tvars, expr)
    assert "constraint_type_mismatch" in _lint_codes(module)
    result = check_structural(module)
    assert getattr(result, "undecided", False)
    assert result.issues[0]["code"] == "structural_ill_typed_atom"


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_well_typed_numeric_atoms_still_decided(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    assert check_structural(_module([INT_X], "i == 2.0")).ok is True
    assert check_structural(_module([FLOAT_Y], "f == 1")).ok is True


def _enum(name, typ, values):
    return {"name": name, "type": typ, "domain": {"set": values}}


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_enum_element_types_come_from_the_declaration(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    ok = check_structural(_module([_enum("a", "enum[float]", [1]), _enum("b", "enum[float]", [1.0])], "a = b"))
    assert ok.ok is True
    bad = check_structural(_module([_enum("a", "enum[float]", [1]), _enum("b", "enum[int]", [1])], "a = b"))
    assert getattr(bad, "undecided", False)
    assert bad.issues[0]["code"] == "structural_ill_typed_atom"


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_interval_bounds_may_be_fractional_on_an_int_tvar(monkeypatch, solver):
    # T-Interval (semantics 4.6) types an interval only by a <= b; T-Cmp needs n : elem(int).
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    int_x = {"name": "x", "type": "int", "domain": {"range": [0, 5]}}
    sat = check_structural(_module([int_x], "0 <= x <= 2.5"))
    assert sat.ok is True and sat.assignment["x"] in (0, 1, 2)
    assert check_structural(_module([int_x], "0.5 <= x <= 0.9")).ok is False
    neg = check_structural(_module([int_x], "not (0.5 <= x <= 4.5) and x != 0"))
    assert neg.ok is True and neg.assignment == {"x": 5}
    # A direct comparison still needs an int literal (T-Cmp).
    direct = check_structural(_module([int_x], "x <= 2.5"))
    assert getattr(direct, "undecided", False)
    assert direct.issues[0]["code"] == "structural_ill_typed_atom"
