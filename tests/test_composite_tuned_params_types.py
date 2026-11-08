"""Issue #230: a non-string composite tuned_params entry is reported, not a crash."""

from pathlib import Path

import pytest
import yaml
from tvl.lints import lint_module

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "spec/examples/book/ch08/support-bot-gap.tvl.yml"


@pytest.mark.parametrize("bad", [["max_tool_calls"], {"x": 1}, 7], ids=["list", "mapping", "int"])
def test_non_string_tuned_param_is_invalid_tuned_param(bad):
    doc = yaml.safe_load(EXAMPLE.read_text())
    tuned = doc["composites"][0]["arms"][0]["tuned_params"]
    assert tuned[1] == "max_tool_calls", "fixture changed"
    tuned[1] = bad
    issues = [i for i in lint_module(doc) if i["code"] == "invalid_tuned_param"]
    assert [i["path"] for i in issues] == [["composites", 0, "arms", 0, "tuned_params", 1]], issues
