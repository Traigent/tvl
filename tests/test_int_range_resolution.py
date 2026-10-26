"""Definition 3.6: an int range with a resolution r denotes {a + i*r}, not every integer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.model import extract_domains  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402

TVARS = [{"name": "x", "type": "int", "domain": {"range": [0, 4], "resolution": 2}}]


def _module(exprs):
    return {"tvars": TVARS, "constraints": {"structural": [{"expr": e} for e in exprs]}}


def test_domain_membership_follows_the_resolution_grid():
    domain = extract_domains(TVARS)["x"]
    assert [v for v in range(-1, 6) if domain.contains(v)] == [0, 2, 4]


def test_int_range_without_resolution_is_unchanged():
    domain = extract_domains([{"name": "x", "type": "int", "domain": {"range": [0, 4]}}])["x"]
    assert [v for v in range(-1, 6) if domain.contains(v)] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_structural_sees_only_grid_points(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    assert check_structural(_module(["x == 1"])).ok is False
    assert check_structural(_module(["x > 2", "x < 4"])).ok is False
    sat = check_structural(_module(["x > 0", "x < 4"]))
    assert sat.ok and sat.assignment == {"x": 2}
    assert isinstance(sat.assignment["x"], int)


def test_satisfiability_encoder_handles_off_grid_thresholds():
    from tvl.constraints import check_structural_satisfiable, compile_constraints

    def solve(expr):
        return check_structural_satisfiable(compile_constraints(_module([expr])))

    sat = solve("x < 3")
    assert sat["ok"] and sat["assignment"]["x"] in (0, 2)
    assert solve("x == 3")["ok"] is False
    assert solve("x != 3")["ok"] is True
    assert solve("x > 3")["assignment"] == {"x": 4}
    assert solve("x == 2")["assignment"] == {"x": 2}


def test_satisfiability_encoder_uses_the_exact_literal():
    from tvl.constraints import check_structural_satisfiable, compile_constraints

    module = {
        "tvars": [{"name": "x", "type": "int", "domain": {"range": [0, 2]}}],
        "constraints": {
            "structural": [{"expr": "0 <= x <= 0.999999999999999999"}, {"expr": "x = 1"}]
        },
    }
    assert check_structural_satisfiable(compile_constraints(module))["ok"] is False
    module["constraints"]["structural"][0]["expr"] = "0 <= x <= 1.000000000000000001"
    assert check_structural_satisfiable(compile_constraints(module))["assignment"] == {"x": 1}


def test_legacy_int_tvars_use_the_unit_grid_in_satisfiability():
    # Legacy ``tvars: {x: {type: int, min, max}}`` has no resolution: its grid is the unit grid,
    # not the float default 1/precision, so no integer lies strictly between 0 and 1.
    from tvl.constraints import check_structural_satisfiable, compile_constraints

    module = {
        "tvars": {"x": {"type": "int", "min": 0, "max": 2}},
        "constraints": {"structural": [{"expr": "x > 0 and x < 1"}]},
    }
    assert check_structural_satisfiable(compile_constraints(module))["ok"] is False
    module["constraints"]["structural"] = [{"expr": "x > 0 and x < 2"}]
    result = check_structural_satisfiable(compile_constraints(module))
    assert result["ok"] is True and result["assignment"] == {"x": 1}
