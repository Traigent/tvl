"""Issue #246: the flat config-validate parser splits on ``and``/``or`` outside quotes only.

A quoted string value containing `` and `` or `` or `` followed by comparison-shaped text was
split into two atoms (``mode != '"x'`` and ``y == '1"'``), silently rewriting the constraint.
"""

from __future__ import annotations

import pytest
from tvl.constraints import (
    Atom,
    compile_constraints,
    evaluate_assignment,
    parse_expression,
)


def _module(expr: str) -> dict:
    return {
        "tvars": [
            {"name": "mode", "type": "enum[str]", "domain": ["x and y == 1", "x or mode != c", "c"]},
            {"name": "y", "type": "int", "domain": {"range": [0, 5]}},
        ],
        "constraints": {"structural": [{"expr": expr}]},
    }


@pytest.mark.parametrize("value", ["x and y == 1", "x or mode != c", "x AND y == 1"])
def test_quoted_connective_stays_one_atom(value: str) -> None:
    for quote in ('"', "'"):
        text = f"mode != {quote}{value}{quote}"
        assert parse_expression(text, frozenset({"mode", "y"})) == [
            [Atom(path="mode", op="!=", value=value)]
        ]


def test_quoted_and_does_not_reject_a_satisfying_config() -> None:
    compiled = compile_constraints(_module('mode != "x and y == 1"'))
    assert compiled.parse_issues == []
    result = evaluate_assignment(compiled, {"mode": "c", "y": 1})
    assert result == {"domains": [], "constraints": []}


def test_quoted_or_does_not_accept_a_violating_config() -> None:
    # Split on the quoted ' or ', the tail ``mode != c"`` held for mode == "c".
    compiled = compile_constraints(_module('mode = "x or mode != c"'))
    assert compiled.parse_issues == []
    result = evaluate_assignment(compiled, {"mode": "c", "y": 1})
    assert [issue["code"] for issue in result["constraints"]] == ["constraint_failed"]


def test_unterminated_quote_is_a_parse_issue_not_a_literal() -> None:
    compiled = compile_constraints(_module('mode != "x and y == 1'))
    assert compiled.constraints == []
    assert len(compiled.parse_issues) == 1


def test_unquoted_connectives_still_split() -> None:
    assert parse_expression('mode = "c" and y = 1 or y = 2', frozenset({"mode", "y"})) == [
        [Atom(path="mode", op="==", value="c"), Atom(path="y", op="==", value=1)],
        [Atom(path="y", op="==", value=2)],
    ]
