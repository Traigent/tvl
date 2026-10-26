"""An overlay may not add values to a ``{set: [...]}`` domain, as for a bare-list domain."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tvl_tools.tvl_compose.cli import compose


def _compose(tmp_path: Path, base_domain, overlay_domain, validate=True):
    base = {
        "tvl": {"module": "demo.compose"},
        "environment": {"snapshot_id": "2025-01-20T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/demo.jsonl"},
        "tvars": [{"name": "model", "type": "enum[str]", "domain": base_domain}],
        "constraints": {"structural": [], "derived": []},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"quality": 0.01}},
    }
    (tmp_path / "base.tvl.yml").write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    overlay = {
        "_tvl_overlay": {"extends": "base.tvl.yml"},
        "overrides": {"tvars": [{"name": "model", "domain": overlay_domain}]},
    }
    path = tmp_path / "o.overlay.yml"
    path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
    return compose(path, validate_narrowing=validate)


@pytest.mark.parametrize(
    "base_domain, overlay_domain",
    [
        ({"set": ["a", "b"]}, {"set": ["a", "b", "c"]}),
        (["a", "b"], {"set": ["a", "b", "c"]}),
        ({"set": ["a", "b"]}, ["a", "b", "c"]),
    ],
)
def test_adding_a_value_to_a_set_domain_is_rejected(tmp_path, base_domain, overlay_domain):
    with pytest.raises(ValueError, match="cannot add values"):
        _compose(tmp_path, base_domain, overlay_domain)


def test_narrowing_a_set_domain_is_accepted(tmp_path):
    composed = _compose(tmp_path, {"set": ["a", "b"]}, {"set": ["a"]})
    assert composed["tvars"][0]["domain"] == {"set": ["a"]}


def test_no_validate_flag_still_bypasses(tmp_path):
    composed = _compose(tmp_path, {"set": ["a", "b"]}, {"set": ["a", "b", "c"]}, validate=False)
    assert composed["tvars"][0]["domain"]["set"] == ["a", "b", "c"]
