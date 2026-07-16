"""Regression tests for fail-open defects in the assignment-constraint path.

Covers three divergences between the shipped ``tvl-config-validate`` path
(``compile_constraints`` / ``evaluate_assignment`` / ``_atom_literal``) and the
intended constraint semantics:

- #37 — the ``==`` equality operator was truncated to ``=`` by the regex literal
  parser, swallowing the sign into the value string so ``==`` constraints were
  never enforced (fail-open).
- #38 — a disjunctive antecedent (``when: "a = 1 or b = 1"``) short-circuited to
  satisfied on the first false disjunct, so OR-antecedent constraints were never
  enforced (fail-open).
- #40 — an ordering comparison on a symbolic (non-numeric) enum was encoded as
  unconditionally satisfied in the CP-SAT encoder (fail-open); it must be
  rejected instead.
"""

from __future__ import annotations

import pytest

from tvl.constraints import (
    compile_constraints,
    evaluate_assignment,
    parse_expression,
)


# --- #37: `==` equality operator ------------------------------------------


def test_double_equals_parses_as_equality_with_typed_value():
    disjuncts = parse_expression("a == 1")
    assert len(disjuncts) == 1
    (atom,) = disjuncts[0]
    assert atom.path == "a"
    assert atom.op == "=="
    # The value must be the typed int 1 — not the swallowed string "= 1".
    assert atom.value == 1
    assert isinstance(atom.value, int)


def test_double_equals_constraint_reports_violation():
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": [0, 1]}},
            {"name": "c", "type": "enum", "domain": {"set": [0, 1]}},
        ],
        "constraints": {"structural": [{"when": "a == 1", "then": "c == 1"}]},
    }
    compiled = compile_constraints(module)
    result = evaluate_assignment(compiled, {"a": 1, "c": 0})
    # a==1 holds, c==1 fails → the constraint must be reported violated.
    assert any(i["code"] == "constraint_failed" for i in result["constraints"])

    ok = evaluate_assignment(compiled, {"a": 1, "c": 1})
    assert ok["constraints"] == []


# --- #38: disjunctive antecedent ------------------------------------------


@pytest.mark.parametrize("a,b", [(0, 1), (1, 0)])
def test_or_antecedent_violation_is_reported(a, b):
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": [0, 1]}},
            {"name": "b", "type": "enum", "domain": {"set": [0, 1]}},
            {"name": "c", "type": "enum", "domain": {"set": [0, 1]}},
        ],
        "constraints": {
            "structural": [{"when": "a = 1 or b = 1", "then": "c = 1"}]
        },
    }
    compiled = compile_constraints(module)
    # (a or b) holds but c != 1 → antecedent true, consequent false → violation.
    result = evaluate_assignment(compiled, {"a": a, "b": b, "c": 0})
    assert any(i["code"] == "constraint_failed" for i in result["constraints"])


def test_or_antecedent_vacuously_true_when_all_disjuncts_false():
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": [0, 1]}},
            {"name": "b", "type": "enum", "domain": {"set": [0, 1]}},
            {"name": "c", "type": "enum", "domain": {"set": [0, 1]}},
        ],
        "constraints": {
            "structural": [{"when": "a = 1 or b = 1", "then": "c = 1"}]
        },
    }
    compiled = compile_constraints(module)
    # Neither disjunct holds → antecedent false → vacuously satisfied.
    result = evaluate_assignment(compiled, {"a": 0, "b": 0, "c": 0})
    assert result["constraints"] == []


# --- #40: ordering comparison on a symbolic enum --------------------------


def test_symbolic_enum_ordering_is_rejected_not_fail_open():
    pytest.importorskip("ortools")
    from tvl.constraints import check_structural_satisfiable

    module = {
        "tvars": [
            {
                "name": "model",
                "type": "enum",
                "domain": {"set": ["gpt-3.5", "gpt-4", "claude"]},
            }
        ],
        "constraints": {"structural": [{"expr": 'model < "gpt-4"'}]},
    }
    compiled = compile_constraints(module)
    with pytest.raises(ValueError, match="symbolic enum"):
        check_structural_satisfiable(compiled)
