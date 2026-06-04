"""Regression: float-domain TVARs crashed check_structural_satisfiable.

`Domain` was refactored to `_encode_bound_lower`/`_encode_bound_upper`
(model.py) and structural_sat.py was updated, but constraints.py kept calling
the removed `_encode_bound` — any module with a float-domain TVAR raised
AttributeError in the OR-Tools variable builder. Found by the RFC 0001
model-checking corpus sweep (17/35 canonical spec/examples modules crashed).
"""

from __future__ import annotations

from tvl.constraints import check_structural_satisfiable, compile_constraints


def test_float_domain_variable_solves():
    module = {
        "tvars": [
            {
                "name": "temperature",
                "type": "float",
                "domain": {"range": [0.0, 1.0], "resolution": 0.1},
            }
        ],
        "constraints": {"structural": []},
    }
    compiled = compile_constraints(module)
    result = check_structural_satisfiable(compiled)
    assert result.get("ok") is True


def test_float_domain_bounds_use_inner_grid_points():
    """ceil for the lower bound, floor for the upper — the integer relaxation
    only contains grid points INSIDE the real interval."""
    module = {
        "tvars": [
            {
                "name": "t",
                "type": "float",
                "domain": {"range": [0.05, 0.95], "resolution": 0.1},
            }
        ],
        "constraints": {"structural": []},
    }
    result = check_structural_satisfiable(compile_constraints(module))
    assert result.get("ok") is True
    value = result["assignment"]["t"]
    assert 0.05 <= value <= 0.95
