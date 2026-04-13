from __future__ import annotations

from pathlib import Path

import yaml

from tvl_tools.tvl_compose.cli import compose


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_compose_replaces_numeric_range_lists_in_nested_domains(tmp_path: Path) -> None:
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = tmp_path / "staging.overlay.yml"

    _write_yaml(
        base_path,
        {
            "tvl": {"module": "demo.compose"},
            "environment": {"snapshot_id": "2025-01-20T00:00:00Z"},
            "evaluation_set": {"dataset": "s3://datasets/demo.jsonl"},
            "tvars": [
                {
                    "name": "temperature",
                    "type": "float",
                    "domain": {"range": [0.0, 1.0], "resolution": 0.05},
                }
            ],
            "constraints": {"structural": [], "derived": []},
            "objectives": [{"name": "quality", "direction": "maximize"}],
            "promotion_policy": {
                "dominance": "epsilon_pareto",
                "alpha": 0.05,
                "min_effect": {"quality": 0.01},
            },
        },
    )
    _write_yaml(
        overlay_path,
        {
            "_tvl_overlay": {"extends": "base.tvl.yml"},
            "overrides": {
                "tvars": [
                    {
                        "name": "temperature",
                        "domain": {"range": [0.0, 0.6], "resolution": 0.05},
                    }
                ]
            },
        },
    )

    composed = compose(overlay_path)

    assert composed["tvars"][0]["domain"]["range"] == [0.0, 0.6]


def test_compose_replaces_enum_domain_lists_in_nested_domains(tmp_path: Path) -> None:
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = tmp_path / "production.overlay.yml"

    _write_yaml(
        base_path,
        {
            "tvl": {"module": "demo.compose"},
            "environment": {"snapshot_id": "2025-01-20T00:00:00Z"},
            "evaluation_set": {"dataset": "s3://datasets/demo.jsonl"},
            "tvars": [
                {
                    "name": "model",
                    "type": "enum[str]",
                    "domain": ["gpt-4o-mini", "gpt-4o", "claude-3-haiku"],
                }
            ],
            "constraints": {"structural": [], "derived": []},
            "objectives": [{"name": "quality", "direction": "maximize"}],
            "promotion_policy": {
                "dominance": "epsilon_pareto",
                "alpha": 0.05,
                "min_effect": {"quality": 0.01},
            },
        },
    )
    _write_yaml(
        overlay_path,
        {
            "_tvl_overlay": {"extends": "base.tvl.yml"},
            "overrides": {
                "tvars": [
                    {
                        "name": "model",
                        "domain": ["gpt-4o-mini", "claude-3-haiku"],
                    }
                ]
            },
        },
    )

    composed = compose(overlay_path)

    assert composed["tvars"][0]["domain"] == ["gpt-4o-mini", "claude-3-haiku"]
