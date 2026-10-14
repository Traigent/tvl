"""Characterization tests for ``tvl_compose.cli._validate_safety_narrowing``.

Each case pins the exact error list (text and order) the checker returns, so a
behaviour-preserving refactor cannot reword, reorder, drop or add an error.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from tvl_tools.tvl_compose.cli import _validate_safety_narrowing


def _module(
    cc: Optional[List[Any]] = None,
    objectives: Optional[List[Any]] = None,
    structural: Optional[List[Any]] = None,
    derived: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    module: Dict[str, Any] = {}
    if cc is not None:
        module["promotion_policy"] = {"chance_constraints": cc}
    if objectives is not None:
        module["objectives"] = objectives
    if structural is not None or derived is not None:
        module["constraints"] = {}
        if structural is not None:
            module["constraints"]["structural"] = structural
        if derived is not None:
            module["constraints"]["derived"] = derived
    return module


def test_identical_modules_have_no_errors() -> None:
    base = _module(
        cc=[{"name": "safety", "threshold": 0.05, "confidence": 0.95}],
        objectives=[
            {"name": "q", "direction": "maximize"},
            {"name": "lat", "band": {"target": [0.1, 0.5], "alpha": 0.05}},
        ],
        structural=[{"expr": "a = 1"}, {"when": "a = 1", "then": "b = 2"}],
        derived=[{"require": "env.context.n >= 3000"}],
    )
    assert _validate_safety_narrowing(base, base) == []
    assert _validate_safety_narrowing({}, {}) == []
    assert _validate_safety_narrowing({}, {}, waives=None) == []
    assert _validate_safety_narrowing({}, {}, waives=[]) == []


# --- waives ---------------------------------------------------------------- #

def test_waiver_entry_validation_and_staleness() -> None:
    base = _module(structural=[{"expr": "a = 1"}])
    waives = [
        {"reason": "no clause"},
        {"clause": "", "reason": "empty clause"},
        {"clause": "a = 1"},
        "bare  string  clause",
        {"clause": "x  =  1", "reason": "stale"},
        {"clause": "  a   =   1 ", "reason": "dropped on purpose"},
    ]
    errors = _validate_safety_narrowing(base, _module(structural=[]), waives)
    assert errors == [
        "waives entry is missing 'clause'",
        "waives entry is missing 'clause'",
        "waives entry for 'a = 1' is missing 'reason'. A waiver must say why the clause was dropped.",
        "waives entry for 'bare string clause' is missing 'reason'. A waiver must say why the clause was dropped.",
        "waives entry 'x = 1' does not match any clause in the base module (stale waiver, or the clause text drifted)",
    ]


def test_waiver_with_dict_clause_and_sorted_stale_list() -> None:
    base = _module(structural=[{"when": "a = 1", "then": "b = 2"}], derived=[{"require": "n >= 1"}])
    composed = _module(structural=[], derived=[{"require": "n >= 1"}])
    waives = [
        {"clause": {"when": "a = 1", "then": "b = 2"}, "reason": "vacuous"},
        {"clause": "zeta", "reason": "r"},
        {"clause": "alpha", "reason": "r"},
    ]
    assert _validate_safety_narrowing(base, composed, waives) == [
        "waives entry 'alpha' does not match any clause in the base module (stale waiver, or the clause text drifted)",
        "waives entry 'zeta' does not match any clause in the base module (stale waiver, or the clause text drifted)",
    ]


def test_later_waiver_for_same_clause_wins_and_counts_once() -> None:
    base = _module(structural=[{"expr": "a = 1"}])
    waives = [{"clause": "a = 1", "reason": "one"}, {"clause": "a  = 1", "reason": "two"}]
    assert _validate_safety_narrowing(base, _module(structural=[]), waives) == []


# --- chance constraints ------------------------------------------------------ #

def test_chance_constraint_removed_loosened_and_tightened() -> None:
    base = _module(
        cc=[
            {"name": "gone", "threshold": 0.1},
            {"name": "loose", "threshold": 0.05, "confidence": 0.95},
            {"name": "tight", "threshold": 0.05, "confidence": 0.95},
            {"name": "nonnumeric", "threshold": "0.05", "confidence": "high"},
            {"threshold": 0.5},  # unnamed: ignored
            "not-a-dict",
        ]
    )
    composed = _module(
        cc=[
            {"name": "loose", "threshold": 0.06, "confidence": 0.9},
            {"name": "tight", "threshold": 0.04, "confidence": 0.99},
            {"name": "nonnumeric", "threshold": 0.9, "confidence": 0.1},
        ]
    )
    assert _validate_safety_narrowing(base, composed) == [
        "chance_constraint 'gone': removed in overlay (not allowed). Overlays may tighten a safety constraint, never drop it.",
        "chance_constraint 'loose': cannot raise threshold from 0.05 to 0.06 (threshold bounds a violation rate; raising it permits more violations)",
        "chance_constraint 'loose': cannot lower confidence from 0.95 to 0.9 (lower confidence is a weaker claim)",
    ]


def test_chance_constraints_missing_policy_or_list() -> None:
    base = {"promotion_policy": {"chance_constraints": [{"name": "a"}]}}
    assert _validate_safety_narrowing(base, {}) == [
        "chance_constraint 'a': removed in overlay (not allowed). Overlays may tighten a safety constraint, never drop it."
    ]
    assert _validate_safety_narrowing(base, {"promotion_policy": None}) == _validate_safety_narrowing(base, {})
    assert _validate_safety_narrowing(base, {"promotion_policy": {"chance_constraints": None}}) == _validate_safety_narrowing(base, {})


def test_chance_constraint_duplicate_names_last_wins() -> None:
    base = _module(cc=[{"name": "a", "threshold": 0.1}, {"name": "a", "threshold": 0.01}])
    composed = _module(cc=[{"name": "a", "threshold": 0.05}])
    assert _validate_safety_narrowing(base, composed) == [
        "chance_constraint 'a': cannot raise threshold from 0.01 to 0.05 (threshold bounds a violation rate; raising it permits more violations)"
    ]


def test_bool_threshold_counts_as_numeric() -> None:
    base = _module(cc=[{"name": "a", "threshold": False, "confidence": True}])
    composed = _module(cc=[{"name": "a", "threshold": True, "confidence": False}])
    assert _validate_safety_narrowing(base, composed) == [
        "chance_constraint 'a': cannot raise threshold from False to True (threshold bounds a violation rate; raising it permits more violations)",
        "chance_constraint 'a': cannot lower confidence from True to False (lower confidence is a weaker claim)",
    ]


# --- objectives -------------------------------------------------------------- #

def test_objective_removed_and_direction_flipped() -> None:
    base = _module(objectives=[
        {"name": "gone", "direction": "maximize"},
        {"name": "flip", "direction": "maximize"},
        {"name": "same", "direction": "minimize"},
        "not-a-dict",
    ])
    composed = _module(objectives=[
        {"name": "flip", "direction": "minimize"},
        {"name": "same", "direction": "minimize"},
    ])
    assert _validate_safety_narrowing(base, composed) == [
        "objective 'gone': removed in overlay (not allowed)",
        "objective 'flip': cannot change direction from 'maximize' to 'minimize'",
    ]


def test_objective_kind_changes() -> None:
    base = _module(objectives=[
        {"name": "to_band", "direction": "maximize"},
        {"name": "drop_dir", "direction": "maximize"},
        {"name": "empty_dir", "direction": "maximize"},
        {"name": "banded_dir", "direction": "maximize", "band": {"target": [0, 1]}},
    ])
    composed = _module(objectives=[
        {"name": "to_band", "band": {"target": [0, 1]}},
        {"name": "drop_dir"},
        {"name": "empty_dir", "direction": ""},
        {"name": "banded_dir", "band": {"target": [0, 1]}},
    ])
    assert _validate_safety_narrowing(base, composed) == [
        "objective 'to_band': cannot convert a directional objective into a banded one (that removes the non-inferiority test)",
        "objective 'drop_dir': cannot drop 'direction' from a directional objective",
        "objective 'empty_dir': cannot drop 'direction' from a directional objective",
    ]


def test_objective_band_direction_flip_also_reports_conversion() -> None:
    base = _module(objectives=[{"name": "o", "direction": "maximize"}])
    composed = _module(objectives=[{"name": "o", "direction": "minimize", "band": {"target": [0, 1]}}])
    assert _validate_safety_narrowing(base, composed) == [
        "objective 'o': cannot change direction from 'maximize' to 'minimize'",
        "objective 'o': cannot convert a directional objective into a banded one (that removes the non-inferiority test)",
    ]


def test_objective_band_checks() -> None:
    base = _module(objectives=[
        {"name": "removed", "band": {"target": [0.1, 0.5]}},
        {"name": "wider", "band": {"target": [0.1, 0.5], "alpha": 0.05}},
        {"name": "dict_eq", "band": {"target": {"center": 0.3, "tol": 0.2}}},
        {"name": "dict_wider", "band": {"target": [0.1, 0.5]}},
        {"name": "narrower", "band": {"target": [0.1, 0.5], "alpha": 0.05}},
        {"name": "bad_target", "band": {"target": [0.1]}},
        {"name": "alpha_only", "band": {"target": [0, 1], "alpha": 0.01}},
        {"name": "alpha_nonnum", "band": {"target": [0, 1], "alpha": "x"}},
        {"name": "empty_band", "band": {}},
    ])
    composed = _module(objectives=[
        {"name": "wider", "band": {"target": [0.05, 0.6], "alpha": 0.1}},
        {"name": "dict_eq", "band": {"target": [0.1, 0.5]}},
        {"name": "dict_wider", "band": {"target": {"center": 0.3, "tol": 0.3}}},
        {"name": "narrower", "band": {"target": [0.2, 0.4], "alpha": 0.01}},
        {"name": "bad_target", "band": {"target": [0.1, 0.2]}},
        {"name": "alpha_only", "band": {"target": [0, 1], "alpha": 0.02}},
        {"name": "alpha_nonnum", "band": {"target": [0, 1], "alpha": 0.5}},
        {"name": "empty_band", "band": {"target": [0, 1]}},
    ])
    assert _validate_safety_narrowing(base, composed) == [
        "objective 'removed': removed in overlay (not allowed)",
        "objective 'wider': cannot widen band from [0.1, 0.5] to [0.05, 0.6]",
        "objective 'wider': cannot raise band alpha from 0.05 to 0.1 (a larger alpha makes the equivalence test easier to pass)",
        "objective 'dict_wider': cannot widen band from [0.1, 0.5] to [0.0, 0.6]",
        "objective 'bad_target': band target is missing or not comparable (base=[0.1], composed=[0.1, 0.2]); cannot verify it was not widened",
        "objective 'alpha_only': cannot raise band alpha from 0.01 to 0.02 (a larger alpha makes the equivalence test easier to pass)",
        "objective 'empty_band': band target is missing or not comparable (base=None, composed=[0, 1]); cannot verify it was not widened",
    ]


def test_objective_band_removed_from_existing_objective() -> None:
    base = _module(objectives=[{"name": "o", "band": {"target": [0, 1]}}])
    composed = _module(objectives=[{"name": "o"}])
    assert _validate_safety_narrowing(base, composed) == ["objective 'o': cannot remove its band"]


def test_objective_band_eps_tolerance() -> None:
    base = _module(objectives=[{"name": "o", "band": {"target": [0.1, 0.5]}}])
    inside = _module(objectives=[{"name": "o", "band": {"target": [0.1 - 1e-10, 0.5 + 1e-10]}}])
    outside = _module(objectives=[{"name": "o", "band": {"target": [0.1 - 1e-8, 0.5]}}])
    assert _validate_safety_narrowing(base, inside) == []
    assert len(_validate_safety_narrowing(base, outside)) == 1


def test_objective_non_dict_band_raises_attribute_error() -> None:
    # A non-mapping band reaches the fail-closed message, whose `.get` fails.
    base = _module(objectives=[{"name": "o", "band": "wide"}])
    composed = _module(objectives=[{"name": "o", "band": "narrow"}])
    with pytest.raises(AttributeError):
        _validate_safety_narrowing(base, composed)


def test_objective_falsy_band_value_is_still_a_band_for_removal_check() -> None:
    # band: {} is falsy (so the directional checks treat the objective as
    # band-less) but not None (so the band checks run).
    base = _module(objectives=[{"name": "o", "direction": "maximize", "band": {}}])
    composed = _module(objectives=[{"name": "o", "direction": "maximize"}])
    assert _validate_safety_narrowing(base, composed) == ["objective 'o': cannot remove its band"]


# --- constraint clauses ------------------------------------------------------ #

def test_dropped_clauses_reported_per_kind_in_base_order() -> None:
    base = _module(
        structural=[{"expr": "b = 2"}, {"expr": "a = 1"}, {"when": "x = 1", "then": "y = 2"}],
        derived=[{"require": "env.context.n >= 3000"}, "plain derived"],
    )
    composed = _module(structural=[{"expr": "a   =   1"}], derived=[])
    assert _validate_safety_narrowing(base, composed) == [
        "constraints.structural: clause 'b = 2' was dropped by the overlay. If the narrowed domains make it vacuous, declare it under _tvl_overlay.waives with a reason; otherwise restate it (or replace it with a strictly tighter bound on the same symbol).",
        "constraints.structural: clause 'x = 1 => y = 2' was dropped by the overlay. If the narrowed domains make it vacuous, declare it under _tvl_overlay.waives with a reason; otherwise restate it (or replace it with a strictly tighter bound on the same symbol).",
        "constraints.derived: clause '{\"require\":\"env.context.n >= 3000\"}' was dropped by the overlay. If the narrowed domains make it vacuous, declare it under _tvl_overlay.waives with a reason; otherwise restate it (or replace it with a strictly tighter bound on the same symbol).",
        "constraints.derived: clause 'plain derived' was dropped by the overlay. If the narrowed domains make it vacuous, declare it under _tvl_overlay.waives with a reason; otherwise restate it (or replace it with a strictly tighter bound on the same symbol).",
    ]


@pytest.mark.parametrize(
    "base_clause,comp_clause,dropped",
    [
        ("env.context.n >= 3000", "env.context.n >= 5990", False),
        ("env.context.n >= 3000", "env.context.n > 3000", False),
        ("env.context.n > 3000", "env.context.n >= 3000", True),
        ("env.context.n >= 3000", "env.context.n >= 2000", True),
        ("env.context.n <= 10", "env.context.n < 10", False),
        ("env.context.n <= 10", "env.context.n <= 5", False),
        ("env.context.n < 10", "env.context.n <= 10", True),
        ("env.context.n <= 10", "env.context.n >= 10", True),
        ("env.context.n >= 3000", "env.context.m >= 9000", True),
        ("env.context.n >= 3000", "not a bound", True),
        ("not a bound", "env.context.n >= 3000", True),
    ],
)
def test_derived_bound_replacement(base_clause: str, comp_clause: str, dropped: bool) -> None:
    base = _module(derived=[{"require": base_clause}])
    composed = _module(derived=[{"require": comp_clause}])
    errors = _validate_safety_narrowing(base, composed)
    assert bool(errors) is dropped
    if dropped:
        # A dict clause is keyed by its compact JSON form.
        key = '{"require":"' + base_clause + '"}'
        assert errors[0].startswith(f"constraints.derived: clause {key!r} was dropped")


def test_structural_string_bounds_and_missing_sections() -> None:
    base = {"constraints": {"structural": ["n >= 1"], "derived": None}}
    composed = {"constraints": {"structural": ["n >= 2"]}}
    assert _validate_safety_narrowing(base, composed) == []
    assert _validate_safety_narrowing(base, {}) == [
        "constraints.structural: clause 'n >= 1' was dropped by the overlay. If the narrowed domains make it vacuous, declare it under _tvl_overlay.waives with a reason; otherwise restate it (or replace it with a strictly tighter bound on the same symbol)."
    ]
    assert _validate_safety_narrowing({"constraints": None}, {}) == []


def test_waived_clause_is_not_reported_and_quoting_is_preserved() -> None:
    base = _module(structural=[{"expr": 'x = "hipaa  strict"'}])
    decoy = _module(structural=[{"expr": 'x = "hipaa strict"'}])
    assert len(_validate_safety_narrowing(base, decoy)) == 1
    waived = [{"clause": 'x  = "hipaa  strict"', "reason": "domain narrowed"}]
    assert _validate_safety_narrowing(base, decoy, waived) == []


def test_all_sections_in_one_call_keep_section_order() -> None:
    base = _module(
        cc=[{"name": "c"}],
        objectives=[{"name": "o", "direction": "maximize"}],
        structural=[{"expr": "s = 1"}],
        derived=[{"require": "d >= 1"}],
    )
    errors = _validate_safety_narrowing(base, {}, waives=[{"reason": "x"}, {"clause": "z", "reason": "r"}])
    assert [e.split(" ")[0] for e in errors] == [
        "waives",
        "chance_constraint",
        "objective",
        "constraints.structural:",
        "constraints.derived:",
        "waives",
    ]
