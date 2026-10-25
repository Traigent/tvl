"""Definition 3.6: an int range with a resolution r denotes {a + i*r}, not every integer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.model import extract_domains  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402

TVARS = [{"name": "x", "type": "int", "domain": {"range": [0, 4], "resolution": 2}}]


def _module(exprs):
    return {"tvars": TVARS, "constraints": {"structural": [{"expr": e} for e in exprs]}}


def test_domain_membership_follows_the_resolution_grid():
    domain = extract_domains(TVARS)["x"]
    assert [v for v in range(-1, 6) if domain.contains(v)] == [0, 2, 4]


def test_int_range_without_resolution_is_unchanged():
    domain = extract_domains([{"name": "x", "type": "int", "domain": {"range": [0, 4]}}])["x"]
    assert [v for v in range(-1, 6) if domain.contains(v)] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("solver", ["cpsat", "fallback"])
def test_structural_sees_only_grid_points(monkeypatch, solver):
    if solver == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    assert check_structural(_module(["x == 1"])).ok is False
    assert check_structural(_module(["x > 2", "x < 4"])).ok is False
    sat = check_structural(_module(["x > 0", "x < 4"]))
    assert sat.ok and sat.assignment == {"x": 2}
    assert isinstance(sat.assignment["x"], int)
