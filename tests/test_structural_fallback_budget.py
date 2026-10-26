"""The fallback search (no OR-Tools) refuses, rather than runs unbounded, on a huge product."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402

CODE = "structural_undecided_without_solver"


def _bool_module(n: int, exprs):
    return {
        "tvars": [{"name": f"b{i}", "type": "bool", "domain": {"set": [True, False]}} for i in range(n)],
        "constraints": {"structural": [{"expr": e} for e in exprs]},
    }


def test_large_boolean_product_is_undecided_within_budget(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    # 2**30 assignments, and the module is UNSAT on b0 alone: an unbudgeted search never ends.
    module = _bool_module(30, ["b0 == true", "b0 == false"])
    start = time.monotonic()
    result = check_structural(module)
    assert time.monotonic() - start < 60
    assert result.ok is False and getattr(result, "undecided", False)
    assert result.issues[0]["code"] == CODE


def test_small_boolean_product_still_proves_unsat(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    result = check_structural(_bool_module(8, ["b0 == true", "b0 == false"]))
    assert result.ok is False and not getattr(result, "undecided", False)


def test_boolean_witness_found_within_budget_is_sat(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    result = check_structural(_bool_module(30, ["b29 == true"]))
    assert result.ok is True


def test_core_reduction_shares_the_budget(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    module = _bool_module(3, ["b0 == true", "b0 == false", "b1 == true"])
    full = check_structural(module)
    assert full.ok is False and full.unsat_core  # default budget: a core is reported

    # 8 leaves prove UNSAT; the core reduction then has no budget left.
    monkeypatch.setattr(structural_sat, "_MAX_FALLBACK_PRODUCT", 8)
    capped = check_structural(module)
    assert capped.ok is False and not getattr(capped, "undecided", False)
    assert capped.unsat_core is None
