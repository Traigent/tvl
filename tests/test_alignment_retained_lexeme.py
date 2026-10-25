"""Definition 8.6 alignment reads the retained source lexeme, not str(value)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl.lints import lint_module  # noqa: E402
from tvl.yaml_safe import safe_load  # noqa: E402


def _codes(text: str) -> list[str]:
    doc = safe_load(text)
    return [i["code"] if isinstance(i, dict) else i.code for i in lint_module(doc)]


def test_set_value_with_unrepresentable_lexeme_is_misaligned():
    # binary64 rounds the literal to 0.1 (str: "0.1", aligned at P=1000), but the decimal
    # written is 0.100000000000000001, and 0.100000000000000001 * 1000 is not an integer.
    codes = _codes(
        "tvars:\n  - name: t\n    type: float\n    domain: {set: [0.100000000000000001]}\n"
    )
    assert "inadequate_precision" in codes


def test_range_bound_with_unrepresentable_lexeme_is_misaligned():
    codes = _codes(
        "tvars:\n  - name: t\n    type: float\n"
        "    domain: {range: [0.100000000000000001, 1.0], resolution: 0.1}\n"
    )
    assert "inadequate_precision" in codes


def test_aligned_value_is_still_accepted():
    codes = _codes("tvars:\n  - name: t\n    type: float\n    domain: {set: [0.1, 0.25]}\n")
    assert "inadequate_precision" not in codes
