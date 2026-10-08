"""Regression tests for issue #15.

A structurally malformed ``constraints.structural[*]`` entry — one that does
not match the schema's ``oneOf`` shape (``{when, then}`` or ``{expr}``,
``additionalProperties: false``) — was silently unenforced instead of
rejected: ``compile_constraints`` compiled it to zero constraints and
``tvl-lint`` stayed clean. This covers the ``compile_constraints`` /
``validate_configuration`` arm; ``tests/test_structural_sat.py`` covers the
SAT-compiler arm and ``tests/test_lints.py`` covers the linter arm.
"""

from __future__ import annotations

import pytest

from tvl.configuration import validate_configuration
from tvl.constraints import ConstraintParseError, compile_constraints, parse_expression


def _module_with_structural(entry):
    return {
        "tvl": {"module": "demo"},
        "environment": {"snapshot_id": "x"},
        "evaluation_set": {"dataset": "d", "seed": 1},
        "tvars": [{"name": "temperature", "type": "float", "domain": {"range": [0.0, 1.0]}}],
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "constraints": {"structural": [entry]},
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"when": "temperature > 0.5"},  # one-sided when, no then, no expr
        {"then": "temperature < 1.0"},  # one-sided then, no when, no expr
        {"cond": "temperature > 0.5"},  # neither shape: unrecognised key only
        {"when": "temperature > 0.5", "then": "temperature < 1.0", "expr": "temperature != 0.9"},  # both shapes
        "temperature > 0.5",  # non-dict entry
    ],
)
def test_compile_constraints_raises_on_malformed_entry(entry):
    module = _module_with_structural(entry)
    compiled = compile_constraints(module)
    # The entry must not silently compile to zero constraints with no trace:
    # it must surface as a parse issue instead.
    assert compiled.constraints == []
    assert len(compiled.parse_issues) == 1
    assert compiled.parse_issues[0]["code"] == "malformed_structural_constraint"


def test_validate_configuration_reports_not_ok_on_malformed_entry():
    """The public, un-schema-gated `validate_configuration` SDK entrypoint
    must not report `ok: true` for a module with a malformed structural
    constraint (issue #15's Arm 1 reachability proof)."""
    module = _module_with_structural({"cond": "temperature > 0.5"})
    config = {"module_id": "demo", "assignments": {"temperature": 0.6}}
    report = validate_configuration(module, config)
    assert report["ok"] is False
    codes = {issue["code"] for issue in report["constraints"]}
    assert "malformed_structural_constraint" in codes


def test_well_formed_when_then_still_compiles():
    module = _module_with_structural({"when": "temperature > 0.5", "then": "temperature < 1.0"})
    compiled = compile_constraints(module)
    assert len(compiled.constraints) == 1
    assert compiled.parse_issues == []


def test_well_formed_expr_still_compiles():
    module = _module_with_structural({"expr": "temperature != 0.9"})
    compiled = compile_constraints(module)
    assert len(compiled.constraints) == 1
    assert compiled.parse_issues == []


@pytest.mark.parametrize(
    "entry",
    [
        {"when": "temperature > 0.5", "expr": "temperature < 0.2"},  # when + expr, no then
        {"then": "temperature < 0.2", "expr": "temperature > 0.5"},  # then + expr, no when
    ],
)
def test_partial_overlap_shape_is_accepted_and_enforces_expr_only(entry):
    """Round-2 review (issue #15): a {when, expr} or {then, expr} entry (one
    side of when/then plus expr) matches the grammar's
    oneOf({when,then} | {expr}) via the {expr} branch alone
    (required: [expr]) and additionalProperties:false still holds (when/then/
    expr are all recognised keys), so it is schema-valid and must be
    accepted with no parse issue — but only `expr` may be enforced; `when`/
    `then` must be silently ignored, not folded into a vacuous constraint
    that enforces neither side (the pre-fix behaviour: the old code took
    `if when_expr is not None or then_expr is not None` and, missing the
    other side, compiled a `when => True`/`True => then` implication whose
    empty branch is vacuously true)."""
    module = _module_with_structural(entry)
    compiled = compile_constraints(module)
    assert compiled.parse_issues == []
    assert len(compiled.constraints) == 1
    constraint = compiled.constraints[0]
    assert constraint.antecedent == [[]]
    assert constraint.consequent == parse_expression(entry["expr"])
