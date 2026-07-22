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

Also covers the PR #53 capstone-review follow-ups (same fail-closed charter):

- an ``expr`` implication split with an empty antecedent/consequent (e.g.
  ``"x = 1 =>"``) must be rejected, not silently compiled to a vacuous or
  unconditional constraint.
- an empty/whitespace formula reaching ``parse_expression`` must be rejected,
  not mapped to ``[[]]`` (vacuous truth).
- the numeric domain lint accepts exactly the normative ``-?[0-9]+`` integer
  grammar, not everything Python's ``int()`` parses.
- ``tvl-config-validate`` text-mode output prints the parse-issue code and
  message instead of ``[constraint #None] {dict}`` / a misleading generic
  "Structural constraint violated".

Each test reproduces the reported bug and asserts the fixed (fail-closed)
behaviour.
"""

from __future__ import annotations

import sys

import pytest
import yaml

from tvl.constraints import (
    Atom,
    ConstraintParseError,
    compile_constraints,
    evaluate_assignment,
    parse_expression,
)
from tvl.configuration import validate_configuration
from tvl.lints import _coerce_numeric, lint_module
from tvl.structural_parser import parse_expression as parse_structural_expression
from tvl_tools.tvl_config_validate.cli import _normalize_failures, main as cli_main


def _base_tvl_module() -> dict:
    return {
        "tvl": {"module": "corp.validation.test"},
        "environment": {"snapshot_id": "2025-01-01T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/dev.parquet"},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {
            "dominance": "epsilon_pareto",
            "alpha": 0.05,
            "min_effect": {"quality": 0.0},
        },
        "exploration": {"strategy": {"type": "grid"}},
    }


# --------------------------------------------------------------------------- #
# #50 — _coerce_numeric signed-int strings
# --------------------------------------------------------------------------- #

def test_coerce_numeric_accepts_negative_int_string():
    """'-5' must coerce like '5' does (was rejected by str.isdigit())."""
    assert _coerce_numeric("-5", "int") == -5
    assert _coerce_numeric("5", "int") == 5


def test_coerce_numeric_rejects_fractional_int_string():
    """A fractional string is still not an int — no accidental truncation."""
    for bad in ("3.5", "5.0", "abc", ""):
        with pytest.raises(ValueError):
            _coerce_numeric(bad, "int")


def test_coerce_numeric_rejects_non_normative_int_strings():
    """Only the normative integer grammar ``-?[0-9]+`` (tvl.ebnf:258) is
    accepted — not everything Python's bare ``int()`` parses. A leading '+',
    underscore-grouping, and surrounding whitespace are all int()-legal but
    grammar-invalid, so ``int("1_000") == 1000`` must NOT make it through."""
    for bad in ("+3", "1_000", " 5 ", "5 ", " 5", "1__0"):
        with pytest.raises(ValueError):
            _coerce_numeric(bad, "int")


def test_lint_module_rejects_underscore_grouped_int_domain_value():
    """End-to-end: a set-domain int TVAR with '1_000' must lint as
    invalid_numeric_domain, not silently accept a non-normative literal."""
    doc = _base_tvl_module()
    doc["tvars"] = [{"name": "x", "type": "int", "domain": {"set": ["1_000", "5"]}}]
    issues = lint_module(doc)
    assert any(issue["code"] == "invalid_numeric_domain" for issue in issues)


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
# PR #53 capstone follow-up — '=>' split with an empty antecedent/consequent
# must be rejected, not compiled to a vacuous-true or unconditional constraint.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expr", ["x = 1 =>", "=> y = 2", "=>"])
def test_empty_side_implication_rejected(expr):
    """A truncated implication (either side empty/whitespace) must surface as
    a malformed_implication parse issue, not silently compile to True."""
    module = {
        "tvars": [
            {"name": "x", "type": "int", "domain": {"range": [0, 5]}},
            {"name": "y", "type": "int", "domain": {"range": [0, 5]}},
        ],
        "constraints": {"structural": [{"expr": expr}]},
    }
    compiled = compile_constraints(module)
    assert compiled.constraints == []
    assert any(i["code"] == "malformed_implication" for i in compiled.parse_issues)

    result = validate_configuration(module, {"assignments": {"x": 1, "y": 1}})
    assert result["ok"] is False
    assert any(i["code"] == "malformed_implication" for i in result["constraints"])


# --------------------------------------------------------------------------- #
# PR #53 capstone follow-up — an empty/whitespace formula must be rejected,
# not mapped to [[]] (vacuous truth).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", ["", "   "])
def test_empty_formula_rejected(text):
    with pytest.raises(ConstraintParseError) as exc:
        parse_expression(text)
    assert exc.value.code == "empty_formula"


def test_empty_then_expr_fails_closed_in_compile_constraints():
    """A schema-valid ``then: ""`` must not silently void the constraint."""
    module = {
        "tvars": [{"name": "x", "type": "int", "domain": {"range": [0, 5]}}],
        "constraints": {"structural": [{"when": "x = 1", "then": ""}]},
    }
    compiled = compile_constraints(module)
    assert compiled.constraints == []
    assert any(i["code"] == "empty_formula" for i in compiled.parse_issues)

    result = validate_configuration(module, {"assignments": {"x": 1}})
    assert result["ok"] is False
    assert any(i["code"] == "empty_formula" for i in result["constraints"])


def test_empty_expr_fails_closed_in_compile_constraints():
    """A schema-valid ``expr: ""`` (no top-level '=>') must not silently void
    the constraint either."""
    module = {
        "tvars": [{"name": "x", "type": "int", "domain": {"range": [0, 5]}}],
        "constraints": {"structural": [{"expr": ""}]},
    }
    compiled = compile_constraints(module)
    assert compiled.constraints == []
    assert any(i["code"] == "empty_formula" for i in compiled.parse_issues)


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


@pytest.mark.parametrize(
    "expr",
    [
        "foo-bar = 5",
        "foo-bar in {gpt-4o}",
        "0 <= foo-bar <= 10",
    ],
)
def test_structural_parser_rejects_hyphenated_lhs_identifier(expr):
    """Bareword values may contain hyphens, but identifier positions may not."""
    with pytest.raises(ValueError, match="Illegal identifier 'foo-bar'"):
        parse_structural_expression(expr)


# --------------------------------------------------------------------------- #
# PR #53 capstone follow-up — tvl-config-validate text-mode diagnostics must
# print the parse-issue code+message (not "[constraint #None] {dict}"), and
# _normalize_failures must not mislabel a parse rejection as
# "Structural constraint violated".
# --------------------------------------------------------------------------- #

def test_normalize_failures_uses_parse_issue_message_not_generic_violation():
    report = {
        "domains": [],
        "constraints": [
            {
                "code": "unsupported_negation",
                "message": "Negation ('not') is not supported by config-validate: 'not x = 5'",
                "raw": {"expr": "not x = 5"},
                "constraint_index": 0,
            },
            {"code": "constraint_failed", "constraint_index": 1, "raw": {"expr": "x = 1"}},
        ],
    }
    failures = _normalize_failures(report)

    parse_failure = next(f for f in failures if f["code"] == "unsupported_negation")
    assert parse_failure["clauseId"] == 0
    assert "Negation" in parse_failure["message"]
    assert parse_failure["message"] != "Structural constraint violated"

    eval_failure = next(f for f in failures if f["code"] == "constraint_failed")
    assert eval_failure["clauseId"] == 1
    assert eval_failure["message"] == "Structural constraint violated"


def test_config_validate_cli_text_mode_prints_parse_issue_code_and_message(tmp_path, capsys):
    module = _base_tvl_module()
    module["tvars"] = [{"name": "x", "type": "int", "domain": {"range": [0, 5]}}]
    module["constraints"] = {"structural": [{"expr": "not x = 5"}]}
    module_path = tmp_path / "mod.tvl.yml"
    module_path.write_text(yaml.safe_dump(module))

    config = {"module_id": "corp.validation.test", "assignments": {"x": 1}}
    config_path = tmp_path / "cfg.yml"
    config_path.write_text(yaml.safe_dump(config))

    argv = ["tvl-config-validate", str(module_path), str(config_path)]
    monkeypatch_argv = sys.argv
    sys.argv = argv
    try:
        with pytest.raises(SystemExit) as exc:
            cli_main()
    finally:
        sys.argv = monkeypatch_argv

    assert exc.value.code == 5
    out = capsys.readouterr().out
    assert "[constraint #None]" not in out
    assert "unsupported_negation" in out
    assert "Negation ('not') is not supported by config-validate: 'not x = 5'" in out
    assert "{'expr': 'not x = 5'}" not in out
