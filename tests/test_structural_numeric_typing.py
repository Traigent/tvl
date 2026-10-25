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
