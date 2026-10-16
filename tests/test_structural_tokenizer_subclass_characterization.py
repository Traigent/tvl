"""Compatibility of structural tokenization for strings with overridden methods."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tvl.structural_parser import StructuralParseError, _tokenize


class TracedString(str):
    def __new__(cls, value, behavior):
        instance = super().__new__(cls, value)
        instance.behavior = behavior
        instance.events = []
        return instance

    def __len__(self):
        self.events.append(["len"])
        return self.behavior.get("length", super().__len__())

    def __getitem__(self, key):
        event_key = ["slice", key.start, key.stop, key.step] if isinstance(key, slice) else key
        self.events.append(["getitem", event_key])
        if not isinstance(key, slice) and str(key) in self.behavior.get("characters", {}):
            return self.behavior["characters"][str(key)]
        return super().__getitem__(key)

    def startswith(self, prefix, start=0, end=None):
        self.events.append(["startswith", prefix, start, end])
        overrides = self.behavior.get("startswith", {})
        if prefix in overrides:
            return overrides[prefix]
        return super().startswith(prefix, start) if end is None else super().startswith(prefix, start, end)


def observe(case):
    text = TracedString(case["text"], case["behavior"])
    try:
        result = {"tokens": [[token.type, token.value] for token in _tokenize(text)]}
    except StructuralParseError as exc:
        result = {"error_type": type(exc).__name__, "message": str(exc)}
    return {"result": result, "events": text.events}


FIXTURE = Path(__file__).parent / "data" / "structural_tokenizer_subclass_before.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_string_subclass_callback_behavior_is_preserved(case):
    assert observe(case) == case["expected"]


def test_disabled_pair_operator_matching_changes_tokens():
    text = TracedString("<=", {"startswith": {"=>": False, "<=": False, ">=": False, "==": False, "!=": False}})
    assert [[token.type, token.value] for token in _tokenize(text)] == [["LT", "<"], ["EQ", "="], ["EOF", ""]]


def test_forced_first_pair_operator_matching_takes_precedence():
    text = TracedString("xy", {"startswith": {"=>": True}})
    assert [[token.type, token.value] for token in _tokenize(text)] == [["IMPLIES", "=>"], ["EOF", ""]]
    assert text.events == [["len"], ["getitem", 0], ["startswith", "=>", 0, None]]


def test_overridden_length_bounds_scanning():
    text = TracedString("x = 1 @", {"length": 1})
    assert [[token.type, token.value] for token in _tokenize(text)] == [["IDENT", "x"], ["EOF", ""]]


def test_overridden_character_affects_dispatch():
    text = TracedString("x", {"characters": {"0": "="}})
    assert [[token.type, token.value] for token in _tokenize(text)] == [["EQ", "="], ["EOF", ""]]
