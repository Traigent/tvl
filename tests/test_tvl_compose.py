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


# ---------------------------------------------------------------------------
# Safety monotonicity (issue #70)
#
# The narrowing check historically covered TVAR domains and exploration budgets only,
# so an overlay could delete every structural guardrail and gut every chance constraint
# and still compose with exit 0.
# ---------------------------------------------------------------------------


def _safety_base(path: Path) -> None:
    _write_yaml(
        path,
        {
            "tvl": {"module": "demo.safety"},
            "environment": {"snapshot_id": "2026-01-01T00:00:00Z"},
            "evaluation_set": {"dataset": "s3://datasets/demo.jsonl"},
            "tvars": [
                {
                    "name": "temperature",
                    "type": "float",
                    "domain": {"range": [0.0, 1.0], "resolution": 0.05},
                },
                {"name": "pii_redaction", "type": "bool", "domain": [True, False]},
            ],
            "constraints": {
                "structural": [
                    {"expr": "pii_redaction = true"},
                    {"when": "temperature > 0.7", "then": "pii_redaction = true"},
                ],
                "derived": [],
            },
            "objectives": [
                {"name": "quality", "direction": "maximize"},
                {"name": "toxic_rate", "direction": "minimize"},
            ],
            "promotion_policy": {
                "dominance": "epsilon_pareto",
                "alpha": 0.05,
                "min_effect": {"quality": 0.01, "toxic_rate": 0.001},
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.01, "confidence": 0.95}
                ],
            },
        },
    )


def _overlay(path: Path, overrides: dict, meta_extra: dict | None = None) -> None:
    meta = {"extends": "base.tvl.yml"}
    meta.update(meta_extra or {})
    _write_yaml(path, {"_tvl_overlay": meta, "overrides": overrides})


def test_compose_rejects_raising_a_chance_constraint_threshold(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "weaken.overlay.yml",
        {
            "promotion_policy": {
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.50, "confidence": 0.95}
                ]
            }
        },
    )

    with pytest.raises(ValueError, match="cannot raise threshold from 0.01 to 0.5"):
        compose(tmp_path / "weaken.overlay.yml")


def test_compose_rejects_lowering_confidence(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "weaken.overlay.yml",
        {
            "promotion_policy": {
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.01, "confidence": 0.50}
                ]
            }
        },
    )

    with pytest.raises(ValueError, match="cannot lower confidence from 0.95 to 0.5"):
        compose(tmp_path / "weaken.overlay.yml")


def test_compose_rejects_dropping_a_chance_constraint(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(tmp_path / "drop.overlay.yml", {"promotion_policy": {"chance_constraints": []}})

    with pytest.raises(ValueError, match="chance_constraint 'toxic_rate_slo': removed"):
        compose(tmp_path / "drop.overlay.yml")


def test_compose_allows_tightening(tmp_path: Path) -> None:
    """The check must not block legitimate hardening - only weakening."""
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "tighten.overlay.yml",
        {
            "tvars": [
                {"name": "temperature", "domain": {"range": [0.0, 0.9], "resolution": 0.05}}
            ],
            "promotion_policy": {
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.001, "confidence": 0.99}
                ]
            },
        },
    )

    composed = compose(tmp_path / "tighten.overlay.yml")
    cc = composed["promotion_policy"]["chance_constraints"][0]
    assert cc["threshold"] == 0.001
    assert cc["confidence"] == 0.99


def test_compose_rejects_dropping_a_structural_clause(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(tmp_path / "strip.overlay.yml", {"constraints": {"structural": []}})

    with pytest.raises(ValueError, match="pii_redaction = true.*was dropped"):
        compose(tmp_path / "strip.overlay.yml")


def test_compose_rejects_dropping_an_objective(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "drop-obj.overlay.yml",
        {"objectives": [{"name": "quality", "direction": "maximize"}]},
    )

    with pytest.raises(ValueError, match="objective 'toxic_rate': removed"):
        compose(tmp_path / "drop-obj.overlay.yml")


def test_compose_rejects_flipping_objective_direction(tmp_path: Path) -> None:
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "flip.overlay.yml",
        {
            "objectives": [
                {"name": "quality", "direction": "maximize"},
                {"name": "toxic_rate", "direction": "maximize"},
            ]
        },
    )

    with pytest.raises(ValueError, match="cannot change direction"):
        compose(tmp_path / "flip.overlay.yml")


def test_waiver_permits_a_clause_the_narrowing_made_vacuous(tmp_path: Path) -> None:
    """The motivating case for waivers.

    Narrowing temperature to [0.0, 0.3] makes an inherited `temperature > 0.7` guard
    vacuous, and keeping it is a hard lint error on the composed module. Without the
    waiver mechanism this checker would reject a legitimate overlay.
    """
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "narrow.overlay.yml",
        {
            "tvars": [
                {"name": "temperature", "domain": {"range": [0.0, 0.3], "resolution": 0.05}}
            ],
            "constraints": {"structural": [{"expr": "pii_redaction = true"}]},
        },
        meta_extra={
            "waives": [
                {
                    "clause": "temperature > 0.7 => pii_redaction = true",
                    "reason": "vacuous: temperature narrowed to [0.0, 0.3]",
                }
            ]
        },
    )

    composed = compose(tmp_path / "narrow.overlay.yml")
    assert composed["tvars"][0]["domain"]["range"] == [0.0, 0.3]
    assert len(composed["constraints"]["structural"]) == 1


def test_waiver_without_a_reason_is_rejected(tmp_path: Path) -> None:
    """A waiver's whole purpose is to make a removal declared, so a reason is mandatory."""
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "bad-waiver.overlay.yml",
        {"constraints": {"structural": [{"expr": "pii_redaction = true"}]}},
        meta_extra={"waives": [{"clause": "temperature > 0.7 => pii_redaction = true"}]},
    )

    with pytest.raises(ValueError, match="is missing 'reason'"):
        compose(tmp_path / "bad-waiver.overlay.yml")


def test_stale_waiver_is_rejected(tmp_path: Path) -> None:
    """A waiver that matches nothing is a sign the clause text drifted - fail loudly."""
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "stale.overlay.yml",
        {},
        meta_extra={"waives": [{"clause": "no_such_clause = true", "reason": "typo"}]},
    )

    with pytest.raises(ValueError, match="does not match any clause in the base module"):
        compose(tmp_path / "stale.overlay.yml")


def test_clause_identity_ignores_whitespace(tmp_path: Path) -> None:
    """Reformatting a restated clause must not read as dropping it."""
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "reformat.overlay.yml",
        {
            "constraints": {
                "structural": [
                    {"expr": "pii_redaction   =    true"},
                    {"when": "temperature  > 0.7", "then": "pii_redaction = true"},
                ]
            }
        },
    )

    composed = compose(tmp_path / "reformat.overlay.yml")
    assert len(composed["constraints"]["structural"]) == 2


def test_derived_clause_replaced_by_a_tighter_bound_is_not_a_drop(tmp_path: Path) -> None:
    """Hardening a bound must not read as removing the clause.

    Found by dogfooding: a healthcare profile replaced `safety_eval_samples >= 3000`
    with `>= 5990`, which is precisely what a stricter profile should do. Demanding the
    looser clause be restated alongside the tighter one would be nonsense.
    """
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["derived"] = [{"require": "env.context.eval_samples >= 3000"}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "tighter.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.eval_samples >= 5990"}]}},
    )

    composed = compose(tmp_path / "tighter.overlay.yml")
    assert composed["constraints"]["derived"][0]["require"].endswith("5990")


def test_derived_clause_replaced_by_a_looser_bound_is_rejected(tmp_path: Path) -> None:
    """The mirror image: relaxing a bound is a weakening and must fail."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["derived"] = [{"require": "env.context.eval_samples >= 3000"}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "looser.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.eval_samples >= 500"}]}},
    )

    with pytest.raises(ValueError, match="was dropped by the overlay"):
        compose(tmp_path / "looser.overlay.yml")


def test_upper_bound_tightens_downward(tmp_path: Path) -> None:
    """`<=` tightens as the number FALLS - the opposite direction from `>=`."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["derived"] = [{"require": "env.context.timeout_ms <= 30000"}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "tighter.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.timeout_ms <= 5000"}]}},
    )
    assert compose(tmp_path / "tighter.overlay.yml")

    _overlay(
        tmp_path / "looser.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.timeout_ms <= 60000"}]}},
    )
    with pytest.raises(ValueError, match="was dropped by the overlay"):
        compose(tmp_path / "looser.overlay.yml")


def test_bound_comparison_requires_the_same_symbol(tmp_path: Path) -> None:
    """A tighter bound on a DIFFERENT symbol does not excuse dropping this one."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["derived"] = [{"require": "env.context.eval_samples >= 3000"}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "other.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.other_symbol >= 999999"}]}},
    )

    with pytest.raises(ValueError, match="eval_samples >= 3000.*was dropped"):
        compose(tmp_path / "other.overlay.yml")


# ---------------------------------------------------------------------------
# Bypasses found by adversarial review of the first cut (see PR #72 discussion).
# Each of these composed cleanly before the follow-up fix.
# ---------------------------------------------------------------------------


def test_a_pass_through_overlay_cannot_launder_a_weakening(tmp_path: Path) -> None:
    """The whole chain is validated, not just its last edge.

    Resolving intermediate overlays with validation disabled meant `final -> weaken -> base`
    checked `final` against the ALREADY-WEAKENED `weaken`, which trivially passes. One extra
    empty file defeated every other rule in this module.
    """
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "weaken.overlay.yml",
        {
            "constraints": {"structural": []},
            "promotion_policy": {
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.50, "confidence": 0.50}
                ]
            },
        },
    )
    _write_yaml(
        tmp_path / "final.overlay.yml",
        {"_tvl_overlay": {"extends": "weaken.overlay.yml"}, "overrides": {}},
    )

    # The direct overlay is rejected...
    with pytest.raises(ValueError):
        compose(tmp_path / "weaken.overlay.yml")
    # ...and so is the pass-through wrapping it.
    with pytest.raises(ValueError, match="cannot raise threshold"):
        compose(tmp_path / "final.overlay.yml")


def test_a_valid_chain_still_composes(tmp_path: Path) -> None:
    """Chain validation must not break legitimate multi-level overlays."""
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "mid.overlay.yml",
        {
            "promotion_policy": {
                "chance_constraints": [
                    {"name": "toxic_rate_slo", "threshold": 0.005, "confidence": 0.95}
                ]
            }
        },
    )
    _write_yaml(
        tmp_path / "leaf.overlay.yml",
        {
            "_tvl_overlay": {"extends": "mid.overlay.yml"},
            "overrides": {
                "promotion_policy": {
                    "chance_constraints": [
                        {"name": "toxic_rate_slo", "threshold": 0.001, "confidence": 0.99}
                    ]
                }
            },
        },
    )

    composed = compose(tmp_path / "leaf.overlay.yml")
    assert composed["promotion_policy"]["chance_constraints"][0]["threshold"] == 0.001


def test_ge_does_not_tighten_gt_at_the_same_value(tmp_path: Path) -> None:
    """`x >= 3000` admits 3000; `x > 3000` does not. Same number, strictly wider."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["derived"] = [{"require": "env.context.eval_samples > 3000"}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "loosen.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.eval_samples >= 3000"}]}},
    )
    with pytest.raises(ValueError, match="was dropped by the overlay"):
        compose(tmp_path / "loosen.overlay.yml")

    # The reverse direction IS a tightening and must still be accepted.
    _overlay(
        tmp_path / "tighten.overlay.yml",
        {"constraints": {"derived": [{"require": "env.context.eval_samples > 3000"}]}},
    )
    assert compose(tmp_path / "tighten.overlay.yml")


def test_clause_identity_preserves_whitespace_inside_quoted_literals(tmp_path: Path) -> None:
    """A decoy differing only inside a string literal must not satisfy retention."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["constraints"]["structural"] = [{"expr": 'profile = "hipaa  strict"'}]
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "decoy.overlay.yml",
        {"constraints": {"structural": [{"expr": 'profile = "hipaa strict"'}]}},
    )

    with pytest.raises(ValueError, match="was dropped by the overlay"):
        compose(tmp_path / "decoy.overlay.yml")


def test_compose_rejects_widening_an_objective_band(tmp_path: Path) -> None:
    """A band is a gate input, so widening it loosens the gate."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["objectives"][0]["band"] = {"target": [95, 105], "test": "TOST", "alpha": 0.05}
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "widen.overlay.yml",
        {
            "objectives": [
                {
                    "name": "quality",
                    "direction": "maximize",
                    "band": {"target": [0, 1000000], "test": "TOST", "alpha": 0.05},
                },
                {"name": "toxic_rate", "direction": "minimize"},
            ]
        },
    )

    with pytest.raises(ValueError, match="cannot widen band"):
        compose(tmp_path / "widen.overlay.yml")


# --- second adversarial pass: band forms and objective kind -----------------


def test_compose_rejects_widening_a_center_tol_band(tmp_path: Path) -> None:
    """The schema allows `target: {center, tol}` as well as `[low, high]`.

    Comparing only the list form let the dict form widen untouched: tol 5 -> 500 is a
    100x wider equivalence region on the same objective.
    """
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["objectives"][0] = {
        "name": "quality",
        "band": {"target": {"center": 100, "tol": 5}, "test": "TOST", "alpha": 0.05},
    }
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "widen.overlay.yml",
        {
            "objectives": [
                {
                    "name": "quality",
                    "band": {
                        "target": {"center": 100, "tol": 500},
                        "test": "TOST",
                        "alpha": 0.05,
                    },
                },
                {"name": "toxic_rate", "direction": "minimize"},
            ]
        },
    )

    with pytest.raises(ValueError, match="cannot widen band"):
        compose(tmp_path / "widen.overlay.yml")


def test_compose_rejects_raising_band_alpha(tmp_path: Path) -> None:
    """A larger alpha makes the equivalence test easier to pass."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["objectives"][0] = {
        "name": "quality",
        "band": {"target": [95, 105], "test": "TOST", "alpha": 0.05},
    }
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "alpha.overlay.yml",
        {
            "objectives": [
                {
                    "name": "quality",
                    "band": {"target": [95, 105], "test": "TOST", "alpha": 0.99},
                },
                {"name": "toxic_rate", "direction": "minimize"},
            ]
        },
    )

    with pytest.raises(ValueError, match="cannot raise band alpha"):
        compose(tmp_path / "alpha.overlay.yml")


def test_compose_rejects_converting_a_directional_objective_to_banded(tmp_path: Path) -> None:
    """Same name, different gate.

    Name-retention passes and the direction check never fires (the replacement has no
    `direction`), so the non-inferiority test was silently deleted.
    """
    _safety_base(tmp_path / "base.tvl.yml")
    _overlay(
        tmp_path / "convert.overlay.yml",
        {
            "objectives": [
                {"name": "quality", "direction": "maximize"},
                {
                    "name": "toxic_rate",
                    "band": {"target": [0, 1], "test": "TOST", "alpha": 0.99},
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="cannot convert a directional objective"):
        compose(tmp_path / "convert.overlay.yml")


def test_compose_fails_closed_on_an_uncomparable_band(tmp_path: Path) -> None:
    """If the band cannot be normalised, it cannot be shown not to widen - so reject."""
    _safety_base(tmp_path / "base.tvl.yml")
    base = yaml.safe_load((tmp_path / "base.tvl.yml").read_text())
    base["objectives"][0] = {
        "name": "quality",
        "band": {"target": [95, 105], "test": "TOST", "alpha": 0.05},
    }
    _write_yaml(tmp_path / "base.tvl.yml", base)

    _overlay(
        tmp_path / "junk.overlay.yml",
        {
            "objectives": [
                {"name": "quality", "band": {"test": "TOST", "alpha": 0.05}},
                {"name": "toxic_rate", "direction": "minimize"},
            ]
        },
    )

    with pytest.raises(ValueError, match="not comparable"):
        compose(tmp_path / "junk.overlay.yml")


def test_clause_key_handles_escaped_quotes(tmp_path: Path) -> None:
    """An escaped quote must not terminate the literal early."""
    from tvl_tools.tvl_compose.cli import _clause_key

    a = _clause_key({"expr": 'note = "say \\" now"'})
    b = _clause_key({"expr": 'note   =   "say \\" now"'})
    c = _clause_key({"expr": 'note = "say \\"  now"'})
    assert a == b, "whitespace outside quotes should still normalise"
    assert a != c, "whitespace inside the literal must remain significant"
