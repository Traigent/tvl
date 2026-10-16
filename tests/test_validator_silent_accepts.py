"""Regression tests for issue #24.

Three non-happy-path inputs were silently accepted by the entire TVL
validator stack instead of being rejected/flagged:

1. A float-domain `resolution: 0` was schema-valid, and the declared
   discretisation was then silently dropped by `model.py` (falls back to
   the default `precision=1000`).
2. Duplicate enum/set domain values were accepted with no diagnostic.
3. An orphan `promotion_policy.min_effect` key (naming no declared
   objective) was accepted with no diagnostic.
"""

from __future__ import annotations

import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = BASE / "python"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from tvl.lints import lint_module  # noqa: E402
from tvl.schema import validator  # noqa: E402


def _base_module():
    return {
        "tvl": {"module": "demo"},
        "environment": {"snapshot_id": "x"},
        "evaluation_set": {"dataset": "d", "seed": 1},
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"quality": 0.0}},
    }


def _schema_errors(doc):
    return list(validator().iter_errors(doc))


# --- 1. resolution: 0 -------------------------------------------------------


def test_float_resolution_zero_rejected_by_schema():
    doc = _base_module()
    doc["tvars"] = [{"name": "t", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": 0}}]
    errors = _schema_errors(doc)
    assert errors, "resolution: 0 must be rejected by the schema (parity with TupleRange)"


def test_float_resolution_positive_still_accepted_by_schema():
    doc = _base_module()
    doc["tvars"] = [{"name": "t", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": 0.1}}]
    assert _schema_errors(doc) == []


def test_float_resolution_negative_still_rejected_by_schema():
    doc = _base_module()
    doc["tvars"] = [{"name": "t", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": -0.1}}]
    assert _schema_errors(doc)


# --- 2. duplicate enum/set domain values ------------------------------------


def test_duplicate_enum_domain_value_flagged_by_lint():
    doc = _base_module()
    doc["tvars"] = [{"name": "model", "type": "enum[str]", "domain": ["gpt-4o", "gpt-4o", "llama3.1"]}]
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "duplicate_domain_value" in codes


def test_duplicate_numeric_set_domain_value_flagged_by_lint():
    doc = _base_module()
    doc["tvars"] = [{"name": "batch_size", "type": "int", "domain": {"set": [1, 2, 2, 4]}}]
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "duplicate_domain_value" in codes


def test_unique_domain_values_not_flagged_by_lint():
    doc = _base_module()
    doc["tvars"] = [{"name": "model", "type": "enum[str]", "domain": ["gpt-4o", "llama3.1"]}]
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "duplicate_domain_value" not in codes


# --- 3. orphan promotion_policy.min_effect keys -----------------------------


def test_orphan_min_effect_key_flagged_by_lint():
    doc = _base_module()
    doc["promotion_policy"]["min_effect"] = {"quality": 0.01, "ghost_typo": 0.5}
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "unknown_min_effect_objective" in codes


def test_min_effect_keys_matching_declared_objectives_not_flagged():
    doc = _base_module()
    doc["promotion_policy"]["min_effect"] = {"quality": 0.01}
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "unknown_min_effect_objective" not in codes


def test_min_effect_key_for_banded_objective_not_flagged():
    """A banded objective's `direction` is not a plain string, so it is
    exempt from the forward `missing_min_effect` check — but it IS a
    declared objective, so a min_effect entry naming it is not an orphan."""
    doc = _base_module()
    doc["objectives"] = [
        {"name": "quality", "direction": "maximize"},
        {"name": "latency", "band": {"target": 1.0, "tolerance": 0.2}},
    ]
    doc["promotion_policy"]["min_effect"] = {"quality": 0.0, "latency": 0.0}
    codes = {issue["code"] for issue in lint_module(doc)}
    assert "unknown_min_effect_objective" not in codes
