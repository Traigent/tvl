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


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ('mode != "a\\" and b" and y == 1', 'a" and b'),
        ('mode != "a\\"b"', 'a"b'),
        ("mode != 'it\\'s'", "it's"),
        ('mode != "back\\\\slash"', "back\\slash"),
    ],
)
def test_escaped_quote_is_unescaped_like_the_structural_parser(text: str, value: str) -> None:
    from tvl.structural_parser import parse_expression as parse_structural

    atoms = parse_expression(text, frozenset({"mode", "y"}))[0]
    assert atoms[0] == Atom(path="mode", op="!=", value=value)
    structural = repr(parse_structural(text))
    assert repr(value) in structural or repr(value).replace("'", '"') in structural


@pytest.mark.parametrize("text", ['mode != "a\\"', "mode != 'a\\'", 'mode != "a"b'])
def test_escaped_or_early_closing_quote_is_a_parse_issue(text: str) -> None:
    compiled = compile_constraints(_module(text))
    assert compiled.constraints == []
    assert len(compiled.parse_issues) == 1


def test_unquoted_apostrophe_reports_the_quote_not_an_interval() -> None:
    compiled = compile_constraints(_module("mode == O'Brien and y >= 1"))
    assert compiled.constraints == []
    [issue] = compiled.parse_issues
    assert issue["code"] != "unsupported_interval"
    assert "quote" in issue["message"]


def test_config_validate_rejects_the_value_an_escaped_quote_forbids(tmp_path) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    module = tmp_path / "m.tvl.yml"
    module.write_text(
        "tvl: {module: example.quotes}\n"
        'environment: {snapshot_id: "2026-10-01T00:00:00Z"}\n'
        "evaluation_set: {dataset: example.eval}\n"
        "tvars:\n"
        "  - {name: mode, type: \"enum[str]\", domain: ['a\"b', \"c\"]}\n"
        "constraints:\n"
        "  structural:\n"
        "    - expr: 'mode != \"a\\\"b\"'\n"
        "objectives: [{name: quality, direction: maximize}]\n"
        "promotion_policy: {dominance: epsilon_pareto, alpha: 0.05, min_effect: {quality: 0.01}}\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    # The CLI subprocess must import the tree under test, not whatever tvl is installed.
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root / "python"), str(root)]))
    results = {}
    for value in ('a"b', "c"):
        config = tmp_path / f"config-{len(results)}.yml"
        config.write_text("assignments:\n  mode: " + ("'a\"b'" if value == 'a"b' else value) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "tvl_tools.tvl_config_validate.cli", str(module), str(config)],
            capture_output=True, text=True, cwd=root, check=False, env=env,
        )
        assert "Traceback" not in proc.stderr
        results[value] = proc.returncode
    assert results == {'a"b': 5, "c": 0}


def test_backslash_in_a_quoted_value_escapes_the_next_character() -> None:
    # Issue #246 behaviour change, pinned: "C:\path" reads as C:path, as the structural parser reads it.
    assert parse_expression(r'mode != "C:\path"', frozenset({"mode"})) == [
        [Atom(path="mode", op="!=", value="C:path")]
    ]


def test_unquoted_value_with_an_apostrophe_is_a_constraint_parse_error() -> None:
    # Issue #246 behaviour change, pinned: an unquoted value containing a quote character is rejected.
    compiled = compile_constraints(_module("mode != don't"))
    assert compiled.constraints == []
    [issue] = compiled.parse_issues
    assert issue["code"] == "constraint_parse_error"
    assert "quote" in issue["message"]


def test_unquoted_connectives_still_split() -> None:
    assert parse_expression('mode = "c" and y = 1 or y = 2', frozenset({"mode", "y"})) == [
        [Atom(path="mode", op="==", value="c"), Atom(path="y", op="==", value=1)],
        [Atom(path="y", op="==", value=2)],
    ]
