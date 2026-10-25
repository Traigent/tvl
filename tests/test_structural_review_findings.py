"""Regressions for the 2026-10-24 independent code review (findings 1-5)."""

from __future__ import annotations

import sys
import tracemalloc
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from tvl import structural_sat  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402
from tvl.yaml_safe import DuplicateKeyError, safe_load  # noqa: E402

HAVE_CPSAT = structural_sat.cp_model is not None


@pytest.fixture(params=["cpsat", "fallback"])
def solver(request, monkeypatch):
    if request.param == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif not HAVE_CPSAT:
        pytest.skip("ortools missing")
    return request.param


def _mod(tvars, exprs):
    return {"tvars": tvars, "constraints": {"structural": [{"expr": e} for e in exprs]}}


# 1. off-grid equality ----------------------------------------------------------
def test_offgrid_equality_is_never_sat(solver):
    module = _mod(
        [{"name": "x", "type": "float", "domain": {"range": [0.1, 1000.0], "resolution": 0.3}}],
        ["x == 0.40000000000001"],
    )
    result = check_structural(module)
    assert result.ok is False


def test_offgrid_inequality_holds_on_every_point(solver):
    module = _mod(
        [{"name": "x", "type": "float", "domain": {"range": [0.1, 1.0], "resolution": 0.3}}],
        ["x != 0.40000000000001"],
    )
    assert check_structural(module).ok is True


# 2. exact witnesses --------------------------------------------------------------
def test_exact_witness_not_lossy(solver):
    module = _mod(
        [
            {"name": "x", "type": "float", "domain": {"range": [1.0e-18, 1.0], "resolution": 0.1}},
            {"name": "y", "type": "float", "domain": {"range": [0.1, 0.1], "resolution": 0.001}},
        ],
        ["x > 0.05 and x < 0.15 and x != y"],
    )
    result = check_structural(module)
    assert result.ok is True
    x, y = Fraction(result.exact_assignment["x"]), Fraction(result.exact_assignment["y"])
    assert Fraction(5, 100) < x < Fraction(15, 100) and x != y


# 3. overflow / status ------------------------------------------------------------
def test_encoding_overflow_is_undecided_not_unsat():
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    module = _mod(
        [
            {"name": "x", "type": "float", "domain": {"range": [0.0000000001, 1.0], "resolution": 0.3}},
            {"name": "y", "type": "float", "domain": {"range": [0.0, 1000000000.0], "resolution": 1.0}},
        ],
        ["x != y"],
    )
    result = check_structural(module)
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert result.issues[0]["code"] == "structural_encoding_overflow"
    assert result.issues[0]["severity"] == "error"
    assert result.unsat_core is None


def test_only_infeasible_status_yields_unsat(monkeypatch):
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")

    class FakeSolver:
        def SolveWithAssumptions(self, model, lits):
            return structural_sat.cp_model.MODEL_INVALID

        def Solve(self, model):
            return structural_sat.cp_model.MODEL_INVALID

    monkeypatch.setattr(structural_sat.cp_model, "CpSolver", FakeSolver)
    module = _mod([{"name": "n", "type": "int", "domain": {"range": [0, 5]}}], ["n = 3"])
    result = check_structural(module)
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert result.unsat_core is None


# 4. exhaustiveness must not materialise ranges ----------------------------------
def test_exhaustiveness_check_does_not_allocate_range(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)
    module = _mod([{"name": "x", "type": "int", "domain": {"range": [0, 3_000_000]}}], ["x < 0"])
    tracemalloc.start()
    try:
        result = check_structural(module)
        _cur, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.ok is False and getattr(result, "undecided", False) is True
    assert peak < 20_000_000


# 5. duplicate keys inside merge sources -----------------------------------------
def test_duplicate_in_inline_merge_source_rejected():
    with pytest.raises(DuplicateKeyError):
        safe_load("promotion_policy:\n  <<: {alpha: 0.05, alpha: 0.1}\n")


def test_duplicate_in_inline_source_inside_merge_list_rejected():
    text = "base: &x {a: 1}\nd:\n  <<: [*x, {b: 1, b: 2}]\n"
    with pytest.raises(DuplicateKeyError):
        safe_load(text)


def test_explicit_key_overriding_merged_key_still_allowed():
    doc = safe_load("base: &b {x: 1, y: 2}\nd:\n  <<: *b\n  y: 3\n")
    assert doc["d"] == {"x": 1, "y": 3}


# Strict float comparisons must not exclude satisfying grid points (found while fixing 1-3;
# the double offset predates this branch).
def test_strict_float_comparison_keeps_satisfying_points():
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    module = _mod(
        [{"name": "t", "type": "float", "domain": {"range": [0, 1], "resolution": 0.1}}],
        ["t > 0.25", "t < 0.35"],
    )
    result = check_structural(module)
    assert result.ok is True
    assert Fraction(result.exact_assignment["t"]) == Fraction(3, 10)


# ---------------------------------------------------------------------------------
# Regressions for the second independent review (code-review-2, findings R2-1..R2-5).
# ---------------------------------------------------------------------------------
import json  # noqa: E402

import yaml  # noqa: E402

LEGACY_X = {"x": {"type": "float", "min": 0.0, "max": 1.0, "precision": 100}}


# R2-1: strict comparisons are decided exactly in the legacy precision path and the grid path.
@pytest.mark.parametrize("expr", ["x == 0.29 and x > 0.29", "x == 0.07 and x < 0.07"])
def test_r2_1_legacy_strict_comparison_against_equal_literal_is_unsat(solver, expr):
    result = check_structural(_mod(LEGACY_X, [expr]))
    assert result.ok is False
    assert getattr(result, "undecided", False) is False


@pytest.mark.parametrize("expr", ["x == 0.29 and x >= 0.29", "x == 0.07 and x <= 0.07"])
def test_r2_1_legacy_non_strict_comparison_against_equal_literal_is_sat(solver, expr):
    result = check_structural(_mod(LEGACY_X, [expr]))
    assert result.ok is True
    assert result.exact_assignment["x"] in {"0.29", "0.07"}


def test_r2_1_legacy_upper_bound_is_exact(solver):
    tvars = {"x": {"type": "float", "min": 0.0, "max": 0.29, "precision": 100}}
    result = check_structural(_mod(tvars, ["x == 0.29"]))
    assert result.ok is True and result.exact_assignment["x"] == "0.29"


@pytest.mark.parametrize("expr", ["x == 0.29 and x > 0.29", "x == 0.07 and x < 0.07"])
def test_r2_1_grid_strict_comparison_against_equal_literal_is_unsat(solver, expr):
    tvars = [{"name": "x", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": 0.01}}]
    result = check_structural(_mod(tvars, [expr]))
    assert result.ok is False
    assert getattr(result, "undecided", False) is False


# R2-2: the public witness carries an exact representation that satisfies the constraints.
XY = [
    {"name": "x", "type": "float", "domain": {"range": [1.0e-18, 1.0], "resolution": 0.1}},
    {"name": "y", "type": "float", "domain": {"range": [0.1, 0.1], "resolution": 0.001}},
]
XY_EXPR = ["x > 0.05 and x < 0.15 and x != y"]


def test_r2_2_exact_assignment_distinguishes_offgrid_witness(solver):
    result = check_structural(_mod(XY, XY_EXPR))
    assert result.ok is True
    exact = result.exact_assignment
    assert exact == {"x": "0.100000000000000001", "y": "0.1"}
    x, y = Fraction(exact["x"]), Fraction(exact["y"])
    assert Fraction(5, 100) < x < Fraction(15, 100) and x != y
    # The compatibility assignment holds plain floats: no float subclass with hidden payloads.
    assert all(type(v) is float for v in result.assignment.values())


def test_r2_2_cli_json_includes_exact_assignment(tmp_path, monkeypatch, capsys):
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    from tvl_tools.tvl_check_structural import cli

    path = tmp_path / "m.tvl.yml"
    module = {
        "tvl": {"module": "demo.exact_witness"},
        "environment": {"snapshot_id": "2025-01-20T00:00:00Z"},
        "evaluation_set": {"dataset": "s3://datasets/demo/dev.jsonl", "seed": 2025},
        **_mod(XY, XY_EXPR),
        "objectives": [{"name": "acc", "metric_ref": "metrics.acc.v1", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "adjust": "holm", "min_effect": {"acc": 0.01}},
        "exploration": {"strategy": {"type": "grid"}, "budgets": {"max_trials": 24, "max_wallclock_s": 900}},
    }
    path.write_text(yaml.safe_dump(module), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["tvl-check-structural", str(path), "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    decoder = json.JSONDecoder()
    docs, idx = [], 0
    while idx < len(out):
        if out[idx].isspace():
            idx += 1
            continue
        doc, idx = decoder.raw_decode(out, idx)
        docs.append(doc)
    phase = [d for d in docs if d.get("kind") == "PhaseResult"][0]
    assert phase["exact_assignment"] == {"x": "0.100000000000000001", "y": "0.1"}


# R2-3: a self-referential merge must not cause exponential (or infinite) traversal.
def test_r2_3_recursive_merge_alias_terminates_fast():
    # Run in a child process so the pre-fix exponential traversal fails the test instead of hanging it.
    import subprocess

    code = (
        "import sys, time, yaml; sys.path.insert(0, sys.argv[1]);"
        "from tvl.yaml_safe import safe_load;"
        "t = time.monotonic()\n"
        "try:\n    safe_load('d: &d {<<: [*d, *d]}\\n')\n"
        "except yaml.YAMLError:\n    pass\n"
        "print(time.monotonic() - t)"
    )
    python_dir = str(Path(__file__).resolve().parents[1] / "python")
    proc = None
    try:
        proc = subprocess.run([sys.executable, "-c", code, python_dir], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        pytest.fail("recursive merge alias did not terminate within 20 s")
    assert proc is not None
    assert proc.returncode == 0, proc.stderr
    assert float(proc.stdout.strip()) < 2.0


# R2-4: reusing an overridden merge source is not a duplicate.
def test_r2_4_reused_overridden_merge_source_is_not_duplicate():
    doc = safe_load("base: &b {x: 1}\noverride: &o {<<: *b, x: 2}\ncopy: {<<: *o}\n")
    assert doc["override"]["x"] == 2 and doc["copy"]["x"] == 2


# R2-5: duplicates past any depth are rejected, never silently flattened.
@pytest.mark.parametrize("depth", [65, 120])
def test_r2_5_deep_merge_source_duplicate_rejected(depth):
    text = "promotion_policy: " + "{<<: " * depth + "{alpha: 0.05, alpha: 0.1}" + "}" * depth
    with pytest.raises(DuplicateKeyError):
        safe_load(text)


def test_r2_5_excessive_nesting_is_a_yaml_error_not_recursion_error():
    depth = 5000
    text = "a: " + "{<<: " * depth + "{b: 1}" + "}" * depth
    with pytest.raises(yaml.YAMLError):
        safe_load(text)


# Found while fixing R2-1: negating a STRICT interval must keep its endpoints.
def test_negated_strict_interval_keeps_endpoints(solver):
    tvars = [{"name": "n", "type": "int", "domain": {"range": [2, 4]}}]
    result = check_structural(_mod(tvars, ["not (2 < n < 4)", "n == 2"]))
    assert result.ok is True and result.exact_assignment == {"n": "2"}


# Exact evaluation must not crash on non-finite numbers (NaN/inf keep IEEE semantics).
def test_exact_evaluation_rejects_non_finite_enum_members(solver):
    # Superseded by review 3 finding 6: float domains are rationals (formal semantics
    # Definitions 3.1-3.2), so a non-finite member fails closed instead of being decided.
    tvars = [{"name": "t", "type": "enum[float]", "domain": [float("inf"), 0.5]}]
    result = check_structural(_mod(tvars, ["t > 0.7"]))
    assert result.ok is False and getattr(result, "undecided", False) is True
    assert [i["code"] for i in result.issues] == ["structural_non_finite_domain"]
