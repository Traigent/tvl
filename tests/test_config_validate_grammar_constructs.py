"""validate_configuration evaluates grammar-valid chained comparisons, ``not`` and ``in {...}``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl.configuration import validate_configuration  # noqa: E402

TVARS = [
    {"name": "x", "type": "int", "domain": {"range": [0, 10]}},
    {"name": "m", "type": "enum[str]", "domain": {"set": ["a", "b"]}},
    {"name": "b", "type": "bool", "domain": {"set": [True, False]}},
]
CONFIG = {"assignments": {"x": 2, "m": "a", "b": True}}


def _result(expr):
    module = {"tvars": TVARS, "constraints": {"structural": [{"expr": expr}]}}
    return validate_configuration(module, CONFIG)


@pytest.mark.parametrize(
    "expr, holds",
    [
        ("1 <= x <= 5", True),
        ("3 <= x <= 5", False),
        ("1 < x < 2", False),
        ("not (x > 5)", True),
        ("not(x > 5)", True),
        ("not (x > 1)", False),
        ("not (1 <= x <= 3)", False),
        ("not (3 <= x <= 5)", True),
        ("x in {1,2,3}", True),
        ("x in {5,6}", False),
        ("m in {'a','b'}", True),
        ("m in {'b'}", False),
        ("not (x in {2})", False),
        ("x >= 1 and (x < 3 or b == true)", True),
    ],
)
def test_grammar_valid_constructs_are_evaluated(expr, holds):
    result = _result(expr)
    codes = [i["code"] for i in result["constraints"]]
    assert result["ok"] is holds, codes
    assert codes == ([] if holds else ["constraint_failed"])


@pytest.mark.parametrize("expr", ["x in []", "foo-bar in {1}", "0 <= foo-bar <= 10"])
def test_non_representable_text_still_fails_closed(expr):
    result = _result(expr)
    assert result["ok"] is False
    assert result["constraints"] and result["constraints"][0]["code"] != "constraint_failed"
