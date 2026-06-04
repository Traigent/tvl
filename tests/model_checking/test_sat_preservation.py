"""P5 — SAT preservation, checked against the REAL tvl encoder.

For any module M and its cvar/policy-stripped projection M⁻:
compile_constraints(M) and compile_constraints(M⁻) must produce identical
variable sets (= N_T) and identical satisfiability. This runs the actual
python/tvl encoder (compile_constraints / check_structural_satisfiable) on
dict-level modules — the encoder reads only `tvars`, and this suite LOCKS
that fact before the Phase 4 schema admits the new blocks.
"""

from __future__ import annotations

import copy
import itertools

import pytest

from tvl.constraints import check_structural_satisfiable, compile_constraints

CVARS_BLOCK = [
    {
        "name": "router.margin_threshold",
        "type": "float",
        "domain": {"range": [0.0, 1.0]},
        "calibration": {"source": "margin_eval_pool", "depends_on": ["model"]},
        "governance": {"require_calibration": True},
    }
]

POLICIES_BLOCK = [
    {
        "name": "cheap_strong_cascade",
        "kind": "policy",
        "strategy": "cascade",
        "stages": ["cheap", "strong"],
        "gates": [{"kind": "margin_below", "threshold": "router.margin_threshold"}],
    }
]


def _base_module(constraints=None) -> dict:
    return {
        "tvars": [
            {"name": "model", "type": "enum[str]", "domain": ["m1", "m2"]},
            {"name": "zero_shot", "type": "bool", "domain": [True, False]},
            {"name": "retriever.k", "type": "int", "domain": {"range": [0, 4]}},
        ],
        "constraints": {"structural": constraints or []},
    }


SAT_CASES = [
    [],  # unconstrained
    [{"when": "zero_shot = true", "then": "retriever.k = 0"}],  # satisfiable
    [  # unsatisfiable: k must be both 0 and >= 1
        {"when": "zero_shot = true", "then": "retriever.k = 0"},
        {"when": "zero_shot = true", "then": "retriever.k != 0"},
        {"when": "zero_shot = false", "then": "zero_shot = true"},
    ],
]


@pytest.mark.parametrize("constraints", SAT_CASES)
@pytest.mark.parametrize(
    "extra_blocks",
    list(
        itertools.chain.from_iterable(
            itertools.combinations(["cvars", "policies"], r) for r in range(1, 3)
        )
    ),
)
def test_p5_encoding_identical_with_and_without_new_blocks(constraints, extra_blocks):
    base = _base_module(constraints)
    extended = copy.deepcopy(base)
    if "cvars" in extra_blocks:
        extended["cvars"] = copy.deepcopy(CVARS_BLOCK)
    if "policies" in extra_blocks:
        extended["policies"] = copy.deepcopy(POLICIES_BLOCK)

    compiled_base = compile_constraints(base)
    compiled_ext = compile_constraints(extended)

    # Identical variable universe — solver sees exactly N_T.
    assert set(compiled_base.domains) == set(compiled_ext.domains)
    assert set(compiled_ext.domains) == {"model", "zero_shot", "retriever.k"}
    assert compiled_base.domains == compiled_ext.domains
    # Identical CLAUSE sets (P5's strongest form, not just the verdict).
    assert compiled_base.constraints == compiled_ext.constraints

    # Identical satisfiability verdict.
    sat_base = check_structural_satisfiable(compiled_base)
    sat_ext = check_structural_satisfiable(compiled_ext)
    assert sat_base.get("ok") == sat_ext.get("ok")
    assert sat_base.get("ok") is not None


def test_p5_cvar_name_never_becomes_a_solver_variable():
    extended = _base_module()
    extended["cvars"] = copy.deepcopy(CVARS_BLOCK)
    compiled = compile_constraints(extended)
    assert "router.margin_threshold" not in compiled.domains


def test_float_domain_variable_solves_regression():
    """Regression for a pre-existing canonical-repo bug found by this packet's
    P1 corpus sweep: float-domain TVARs crashed check_structural_satisfiable
    with AttributeError ('Domain' object has no attribute '_encode_bound') —
    python/tvl/constraints.py was missed in the _encode_bound_lower/_upper
    rename (structural_sat.py was updated; constraints.py was not; no
    existing test exercised a float domain through this path)."""
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
