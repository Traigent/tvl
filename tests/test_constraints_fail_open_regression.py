"""Regression tests for fail-open defects in the assignment-constraint path.

Re-cut of PR #42 (IsraelTraigent, ``cl/b4-tvl-bugs-37``) on top of the #51
identifier-hardening fix (PR #53 / commit 805f557), which landed on ``main``
after #42 was opened and tightened the same ``_LITERAL_RE`` line #42 touches.
#42's diff re-loosened the identifier group back to the pre-#51 permissive
pattern as a side effect of adding ``==`` support; this file (and the
matching fix in ``constraints.py``) reproduces #42's three fixes against the
*hardened* regex (``_IDENT_RE`` / ``_LITERAL_RE`` with ``_IDENT_PATTERN``)
instead, and adds an explicit test proving the #51 hardening survives.

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

Plus a guard test (``test_hardened_identifier_regex_still_rejects_hyphen_...``)
proving the #51 identifier hardening is not undone by the ``==`` fix: an
identifier the *old* permissive regex would have accepted (a mid-token hyphen)
must still be rejected, with or without ``==``.
"""

from __future__ import annotations

import pytest

from tvl.constraints import (
    ConstraintParseError,
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


# --- #51 hardening must survive the #37 fix --------------------------------


def test_hardened_identifier_regex_still_rejects_hyphen_with_double_equals():
    """Guard: the #51 identifier hardening (mid-ident hyphen forbidden) must
    still apply to literals using the new ``==`` operator. The *old*
    permissive regex (``[A-Za-z0-9_.-]+``) would have accepted ``foo-bar`` as
    an identifier; the hardened ``_IDENT_PATTERN`` must not, regardless of
    which equality spelling triggers the parse."""
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression("foo-bar == 5")
    assert exc.value.code == "illegal_ident"

    # Same illegal identifier is rejected with the pre-existing single '='
    # spelling too, proving #37's fix didn't change identifier handling.
    with pytest.raises(ConstraintParseError) as exc_single:
        parse_expression("foo-bar = 5")
    assert exc_single.value.code == "illegal_ident"


@pytest.mark.parametrize("expr", [".foo == 5", "2x == 5", "-foo == 5", "foo-bar == 5"])
def test_hardened_identifier_regex_rejects_all_51_shapes_with_double_equals(expr):
    """The full #51 parametrized illegal-identifier matrix (leading digit/'.'/'-',
    mid-ident hyphen), replayed with the ``==`` operator #37 adds."""
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression(expr)
    assert exc.value.code == "illegal_ident"


def test_legal_dotted_identifier_still_parses_with_double_equals():
    dnf = parse_expression("a.b.c == 1")
    assert dnf[0][0].path == "a.b.c"
    assert dnf[0][0].op == "=="
