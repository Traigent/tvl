"""RFC 0001 §3.5(4): duplicate mapping keys are rejected at parse time."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl.yaml_safe import DuplicateKeyError, safe_load  # noqa: E402


def test_top_level_duplicate_rejected():
    with pytest.raises(DuplicateKeyError) as exc:
        safe_load("a: 1\nb: 2\na: 3\n")
    msg = str(exc.value)
    assert "duplicate_key" in msg and "'a'" in msg and "line 3" in msg
    assert isinstance(exc.value, yaml.YAMLError)
    assert exc.value.code == "duplicate_key"


def test_nested_duplicate_rejected():
    with pytest.raises(DuplicateKeyError) as exc:
        safe_load("outer:\n  inner:\n    k: 1\n    k: 2\n")
    assert "'k'" in str(exc.value) and "line 4" in str(exc.value)


def test_duplicate_inside_list_item_rejected():
    with pytest.raises(DuplicateKeyError):
        safe_load("xs:\n  - n: 1\n    n: 2\n")


def test_same_key_in_sibling_mappings_ok():
    assert safe_load("a:\n  k: 1\nb:\n  k: 2\nxs:\n  - k: 1\n  - k: 2\n") == {
        "a": {"k": 1}, "b": {"k": 2}, "xs": [{"k": 1}, {"k": 2}],
    }


def test_merge_key_behaviour_unchanged():
    doc = safe_load("base: &b {x: 1, y: 2}\nd:\n  <<: *b\n  y: 3\n")
    assert doc["d"] == {"x": 1, "y": 3}
