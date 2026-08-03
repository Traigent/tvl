from __future__ import annotations

from pathlib import Path

import pytest
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


def test_compose_rejects_absolute_extends_path(tmp_path: Path) -> None:
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = tmp_path / "overlay.tvl.yml"
    _write_yaml(base_path, {"tvl": {"module": "demo.compose"}})
    _write_yaml(
        overlay_path,
        {"_tvl_overlay": {"extends": str(base_path)}, "overrides": {}},
    )

    with pytest.raises(ValueError, match="must be a relative path"):
        compose(overlay_path)


def test_compose_rejects_extends_path_outside_overlay_root(tmp_path: Path) -> None:
    overlay_root = tmp_path / "overlays"
    overlay_root.mkdir()
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = overlay_root / "overlay.tvl.yml"
    _write_yaml(base_path, {"tvl": {"module": "demo.compose"}})
    _write_yaml(
        overlay_path,
        {"_tvl_overlay": {"extends": "../base.tvl.yml"}, "overrides": {}},
    )

    with pytest.raises(ValueError, match="must stay within the overlay root"):
        compose(overlay_path)


def test_compose_rejects_symlinked_extends_path_outside_overlay_root(
    tmp_path: Path,
) -> None:
    overlay_root = tmp_path / "overlays"
    external_root = tmp_path / "external"
    overlay_root.mkdir()
    external_root.mkdir()
    (overlay_root / "external").symlink_to(external_root, target_is_directory=True)
    _write_yaml(external_root / "base.tvl.yml", {"tvl": {"module": "demo.compose"}})
    overlay_path = overlay_root / "overlay.tvl.yml"
    _write_yaml(
        overlay_path,
        {"_tvl_overlay": {"extends": "external/base.tvl.yml"}, "overrides": {}},
    )

    with pytest.raises(ValueError, match="must stay within the overlay root"):
        compose(overlay_path)


def test_compose_allows_nested_relative_extends_within_overlay_root(
    tmp_path: Path,
) -> None:
    overlay_root = tmp_path / "overlays"
    nested_root = overlay_root / "nested"
    nested_root.mkdir(parents=True)
    module_path = overlay_root / "base.tvl.yml"
    nested_overlay_path = nested_root / "shared.overlay.yml"
    overlay_path = overlay_root / "production.overlay.yml"
    _write_yaml(module_path, {"tvl": {"module": "demo.compose"}, "value": "base"})
    _write_yaml(
        nested_overlay_path,
        {
            "_tvl_overlay": {"extends": "../base.tvl.yml"},
            "overrides": {"value": "shared"},
        },
    )
    _write_yaml(
        overlay_path,
        {
            "_tvl_overlay": {"extends": "nested/shared.overlay.yml"},
            "overrides": {"value": "production"},
        },
    )

    assert compose(overlay_path)["value"] == "production"


def _write_overlay_chain(
    tmp_path: Path, overlay_count: int, cycle_to_initial: bool = False
) -> Path:
    base_path = tmp_path / "base.tvl.yml"
    _write_yaml(base_path, {"tvl": {"module": "demo.compose"}})

    for index in reversed(range(overlay_count)):
        if cycle_to_initial and index == overlay_count - 1:
            extends = "overlay-0.tvl.yml"
        else:
            extends = (
                "base.tvl.yml"
                if index == overlay_count - 1
                else f"overlay-{index + 1}.tvl.yml"
            )
        _write_yaml(
            tmp_path / f"overlay-{index}.tvl.yml",
            {"_tvl_overlay": {"extends": extends}, "overrides": {}},
        )

    return tmp_path / "overlay-0.tvl.yml"


def test_compose_allows_64_overlay_chain(tmp_path: Path) -> None:
    assert (
        compose(_write_overlay_chain(tmp_path, overlay_count=64))["tvl"]["module"]
        == "demo.compose"
    )


def test_compose_rejects_65_overlay_chain_before_recursion_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError, match="Overlay extends chain exceeds maximum depth of 64"
    ):
        compose(_write_overlay_chain(tmp_path, overlay_count=65))


def test_compose_prioritizes_cycle_errors_over_chain_depth(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Overlay extends cycle detected"):
        compose(_write_overlay_chain(tmp_path, overlay_count=64, cycle_to_initial=True))


@pytest.mark.parametrize(
    ("overlays", "expected_cycle"),
    [
        (
            {"self.overlay.yml": "self.overlay.yml"},
            "self.overlay.yml -> self.overlay.yml",
        ),
        (
            {
                "first.overlay.yml": "second.overlay.yml",
                "second.overlay.yml": "first.overlay.yml",
            },
            "first.overlay.yml -> second.overlay.yml -> first.overlay.yml",
        ),
    ],
)
def test_compose_rejects_overlay_cycles_deterministically(
    tmp_path: Path, overlays: dict[str, str], expected_cycle: str
) -> None:
    for name, extends in overlays.items():
        _write_yaml(
            tmp_path / name,
            {"_tvl_overlay": {"extends": extends}, "overrides": {}},
        )

    first_overlay = tmp_path / next(iter(overlays))
    with pytest.raises(
        ValueError, match=f"Overlay extends cycle detected: {expected_cycle}"
    ):
        compose(first_overlay)
