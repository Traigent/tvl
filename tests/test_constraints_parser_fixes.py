"""Regression tests for the config-validate / constraints parser bugs.

Covers Traigent/tvl issues #49, #50, #51, #52 — the regex DNF parser in
``constraints.py`` (used by ``tvl-config-validate``) diverging from the
normative grammar and the ``structural_parser`` tokenizer:

- #49: inline ``=>`` implication was swallowed (consequent never enforced =
  fail-open), interval atoms mis-parsed, ``not`` crashed with an uncaught error.
- #50: ``_coerce_numeric('-5', 'int')`` wrongly rejected negative int strings.
- #51: illegal identifiers (leading digit/'.'/'-', mid-ident hyphen) were
  accepted and turned into permanently-unsatisfiable phantom atoms.
- #52: a ``when`` referencing an undeclared TVAR silently voided the guard.

Each test reproduces the reported bug and asserts the fixed (fail-closed)
behaviour.
"""

from __future__ import annotations

import pytest

from tvl.constraints import (
    Atom,
    ConstraintParseError,
    compile_constraints,
    evaluate_assignment,
    parse_expression,
)
from tvl.configuration import validate_configuration
from tvl.lints import _coerce_numeric
from tvl.structural_parser import parse_expression as parse_structural_expression


# --------------------------------------------------------------------------- #
# #50 — _coerce_numeric signed-int strings
# --------------------------------------------------------------------------- #

def test_coerce_numeric_accepts_negative_int_string():
    """'-5' must coerce like '5' does (was rejected by str.isdigit())."""
    assert _coerce_numeric("-5", "int") == -5
    assert _coerce_numeric("5", "int") == 5
    assert _coerce_numeric("+3", "int") == 3


def test_coerce_numeric_rejects_fractional_int_string():
    """A fractional string is still not an int — no accidental truncation."""
    for bad in ("3.5", "5.0", "abc", ""):
        with pytest.raises(ValueError):
            _coerce_numeric(bad, "int")


def test_coerce_numeric_negative_float_string_still_ok():
    assert _coerce_numeric("-5", "float") == -5.0
    assert _coerce_numeric("-2.5", "float") == -2.5


# --------------------------------------------------------------------------- #
# #49 — inline implication / interval / not are fail-closed instead of
#        swallowed / mis-parsed / crashing
# --------------------------------------------------------------------------- #

def test_inline_implication_rejected_in_literal_position():
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression("x = 1 => y = 2")
    assert exc.value.code == "unsupported_implication"


def test_not_rejected_instead_of_uncaught_crash():
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression("not x = 5")
    assert exc.value.code == "unsupported_negation"


def test_interval_atom_rejected():
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression("lo <= x <= hi")
    assert exc.value.code == "unsupported_interval"


def test_quoted_value_containing_arrow_is_not_an_inline_implication():
    """A quoted string value containing '=>' (e.g. mode = "a=>b") must parse as
    a plain literal atom, not be mistaken for an inline implication by a naive
    substring check on the raw (unparsed-for-quotes) text."""
    dnf = parse_expression('mode = "a=>b"')
    assert dnf == [[Atom(path="mode", op="==", value="a=>b")]]


def test_expr_implication_consequent_is_enforced():
    """The core #49 fail-open: an ``expr`` implication's consequent must be
    enforced, not silently discarded."""
    module = {
        "tvars": [
            {"name": "x", "type": "int", "domain": {"range": [0, 5]}},
            {"name": "y", "type": "int", "domain": {"range": [0, 5]}},
        ],
        "constraints": {"structural": [{"expr": "x = 1 => y = 2"}]},
    }
    compiled = compile_constraints(module)
    assert compiled.parse_issues == []

    # antecedent holds + consequent holds -> satisfied
    assert evaluate_assignment(compiled, {"x": 1, "y": 2})["constraints"] == []
    # antecedent false -> vacuously satisfied
    assert evaluate_assignment(compiled, {"x": 0, "y": 3})["constraints"] == []
    # antecedent holds + consequent VIOLATED -> must be flagged (was fail-open)
    failed = evaluate_assignment(compiled, {"x": 1, "y": 3})["constraints"]
    assert any(i["code"] == "constraint_failed" for i in failed)


def test_config_validate_rejects_unparseable_constraint_fail_closed():
    """A constraint the regex parser cannot represent surfaces as an issue and
    makes validate_configuration fail closed (ok is False)."""
    module = {
        "tvars": [{"name": "x", "type": "int", "domain": {"range": [0, 5]}}],
        "constraints": {"structural": [{"expr": "not x = 5"}]},
    }
    result = validate_configuration(module, {"assignments": {"x": 1}})
    assert result["ok"] is False
    assert any(i["code"] == "unsupported_negation" for i in result["constraints"])


# --------------------------------------------------------------------------- #
# #51 — illegal identifiers rejected (leading digit/'.'/'-', mid-ident hyphen)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "expr",
    [".foo <= 5", "2x = 5", "-foo = 5", "foo-bar = 5"],
)
def test_illegal_identifier_rejected(expr):
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression(expr)
    assert exc.value.code == "illegal_ident"


def test_legal_dotted_identifier_still_parses():
    dnf = parse_expression("a.b.c = 1")
    assert dnf[0][0].path == "a.b.c"


def test_illegal_identifier_is_fail_closed_in_config_validate():
    """#51 CLI repro: ``3k <= 4`` no longer exits 0 with a phantom atom."""
    module = {
        "tvars": [{"name": "k", "type": "int", "domain": {"range": [0, 10]}}],
        "constraints": {"structural": [{"expr": "3k <= 4"}]},
    }
    result = validate_configuration(module, {"assignments": {"k": 1}})
    assert result["ok"] is False
    assert any(i["code"] == "illegal_ident" for i in result["constraints"])


# --------------------------------------------------------------------------- #
# #52 — undeclared TVAR referenced in a constraint is flagged (fail-closed)
# --------------------------------------------------------------------------- #

def test_undeclared_tvar_in_when_is_flagged():
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": ["x", "y"]}},
            {"name": "b", "type": "int", "domain": {"range": [0, 10]}},
        ],
        # 'c' is grammar-legal but never declared
        "constraints": {"structural": [{"when": "c = 1", "then": "b <= 5"}]},
    }
    result = validate_configuration(module, {"assignments": {"a": "x", "b": 9}})
    assert result["ok"] is False
    assert any(
        i["code"] == "unknown_reference" and i["path"] == "c"
        for i in result["domains"]
    )


def test_declared_antecedent_control_still_reports_constraint_failure():
    """Control: with a *declared* antecedent, the b<=5 clause is still enforced
    and b=9 is correctly reported (no false regression from the #52 fix)."""
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": ["x", "y"]}},
            {"name": "b", "type": "int", "domain": {"range": [0, 10]}},
        ],
        "constraints": {"structural": [{"when": "a = x", "then": "b <= 5"}]},
    }
    result = validate_configuration(module, {"assignments": {"a": "x", "b": 9}})
    assert result["ok"] is False
    assert any(i["code"] == "constraint_failed" for i in result["constraints"])


def test_all_declared_references_pass_clean():
    """A fully-declared, satisfiable constraint set stays ok (no spurious
    unknown_reference / illegal_ident issues)."""
    module = {
        "tvars": [
            {"name": "a", "type": "enum", "domain": {"set": ["x", "y"]}},
            {"name": "b", "type": "int", "domain": {"range": [0, 10]}},
        ],
        "constraints": {"structural": [{"when": "a = x", "then": "b <= 5"}]},
    }
    result = validate_configuration(module, {"assignments": {"a": "x", "b": 3}})
    assert result["ok"] is True
    assert result["domains"] == []
    assert result["constraints"] == []


# --------------------------------------------------------------------------- #
# #51 follow-up — structural_parser must still lex hyphenated bareword VALUES
# (e.g. ``model = gpt-4o``) after the mid-ident-hyphen fix for LHS identifiers.
# --------------------------------------------------------------------------- #

def test_structural_parser_accepts_hyphenated_bareword_value():
    dnf = parse_structural_expression("model = gpt-4o")
    literal = dnf.clauses[0][0]
    assert literal.ident == "model"
    assert literal.operator == "=="
    assert literal.values == ("gpt-4o",)
