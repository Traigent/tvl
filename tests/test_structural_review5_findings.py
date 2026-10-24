"""Regressions for the fifth independent code review of the structural checker.

Each finding gets a failing-first test. Solver tests run on both backends (CP-SAT and the
fallback search). Resource-exhaustion inputs run in a child process under a time bound (and,
when OR-Tools is kept out of the child, a memory bound) so a regression fails the test
instead of hanging or OOM-killing the run.
"""

from __future__ import annotations

import json
import resource
import subprocess
import sys
import textwrap
from fractions import Fraction
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON_DIR))

from tvl import structural_sat  # noqa: E402
from tvl.model import _resolve_range_values, extract_domains  # noqa: E402
from tvl.structural_sat import build_structural_model, check_structural  # noqa: E402
from tvl.yaml_safe import safe_load  # noqa: E402

HAVE_CPSAT = structural_sat.cp_model is not None


@pytest.fixture(params=["cpsat", "fallback"])
def solver(request, monkeypatch):
    if request.param == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif not HAVE_CPSAT:
        pytest.skip("ortools missing")
    return request.param


def _load(text: str):
    return safe_load(textwrap.dedent(text))


def _check(text: str):
    return check_structural(_load(text))


def _codes(result) -> list:
    return [issue["code"] for issue in (getattr(result, "issues", None) or [])]


def _decided_unsat(result) -> bool:
    return not result.ok and not getattr(result, "undecided", False)


# Keeps OR-Tools out of the child so an address-space cap is safe (its threads cannot start
# under RLIMIT_AS); the code under test runs before any solver call.
_NO_ORTOOLS = "import sys; sys.modules['ortools'] = None\n"


def _bounded_child(code: str, *, seconds: int = 30, memory_bytes: int | None = 2 << 30) -> subprocess.CompletedProcess:
    """Run ``code`` in a child capped at ``seconds`` wall time and, if given, ``memory_bytes``."""

    def limit() -> None:  # pragma: no cover - runs in the child
        if memory_bytes is not None:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=seconds,
        preexec_fn=limit,
        env={"PYTHONPATH": str(PYTHON_DIR), "PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
        check=False,
    )


# 1. scalar range endpoints are exact ----------------------------------------------------
_SCALAR = """
tvars:
  - name: x
    type: float
    domain:
      range: [0.100000000000000001, 0.100000000000000001]
      resolution: 1.0e-18
constraints:
  structural: [{expr: "x == %s"}]
"""


def test_scalar_exact_singleton_excludes_binary64_neighbour(solver):
    result = _check(_SCALAR % "0.1")
    assert _decided_unsat(result), (result, _codes(result))


def test_scalar_exact_singleton_matches_its_lexeme(solver):
    result = _check(_SCALAR % "0.100000000000000001")
    assert result.ok, (result, _codes(result))
    assert result.exact_assignment == {"x": "0.100000000000000001"}


def test_scalar_exact_endpoints_bound_the_grid():
    domain = build_structural_model(_load(_SCALAR % "0.1")).domains["x"]
    assert (domain.index_lower(), domain.index_upper()) == (0, 0)
    assert domain.grid_count() == 1
    assert not domain.contains(0.1)


def test_witness_outside_the_declared_domain_is_not_reported_sat():
    structural = build_structural_model(_load(_SCALAR % "0.1"))
    # The expression holds for 0.1, but 0.1 is not a member of the declared singleton.
    result = structural_sat._sat_result(structural.expressions, {"x": Fraction(1, 10)}, structural.domains)
    assert not result.ok
    assert _codes(result) == [structural_sat.WITNESS_UNVERIFIED_CODE]


def test_witness_membership_checks_enum_members_exactly():
    structural = build_structural_model(
        _load(
            """
            tvars:
              - {name: e, type: "enum[float]", domain: [0.100000000000000001]}
            constraints:
              structural: [{expr: "e != 7"}]
            """
        )
    )
    bad = structural_sat._sat_result(structural.expressions, {"e": 0.1}, structural.domains)
    assert _codes(bad) == [structural_sat.WITNESS_UNVERIFIED_CODE]
    good = structural_sat._sat_result(structural.expressions, {"e": structural.domains["e"].values[0]}, structural.domains)
    assert good.ok and good.exact_assignment == {"e": "0.100000000000000001"}


# 2. tuple range grids are generated exactly ----------------------------------------------
_TUPLE_RANGE = """
tvars:
  - name: t
    type: tuple[float,int]
    domain:
      components:
        - {range: [0.0000000000001, 0.0000000000001], resolution: 0.1}
        - {set: [1]}
constraints:
  structural: [{expr: "t == %s"}]
"""


def test_tuple_range_grid_is_not_rounded(solver):
    result = _check(_TUPLE_RANGE % "(0.0, 1)")
    assert _decided_unsat(result), (result, _codes(result))


def test_tuple_range_grid_matches_its_exact_value(solver):
    result = _check(_TUPLE_RANGE % "(0.0000000000001, 1)")
    assert result.ok, (result, _codes(result))
    assert result.exact_assignment == {"t": ("0.0000000000001", "1")}


def test_tuple_range_grid_values_are_exact_and_stay_plain_floats_when_binary64_holds_them():
    vals = _resolve_range_values("t", 0, {"range": [0, 1], "resolution": 0.1})
    assert all(type(v) is float for v in vals)
    assert [Fraction(repr(v)) for v in vals] == [Fraction(i, 10) for i in range(11)]
    # A grid point binary64 cannot hold is kept exact (and is not a float).
    fine = _resolve_range_values(
        "t", 0, {"range": [Fraction("0.1"), Fraction("0.1000000000000000011")], "resolution": 1e-18}
    )
    assert len(fine) == 2 and not isinstance(fine[1], float)
    assert fine[1] == Fraction(1, 10) + Fraction(1, 10**18)


# 3. exact_assignment formats tuple components --------------------------------------------
_TUPLE_SET = """
tvars:
  - name: t
    type: tuple[float,int]
    domain:
      components:
        - {set: [0.100000000000000001]}
        - {set: [1]}
constraints:
  structural:
    - expr: "t == (0.100000000000000001, 1)"
"""


def test_exact_assignment_formats_tuple_leaves(solver):
    result = _check(_TUPLE_SET)
    assert result.ok, (result, _codes(result))
    assert result.exact_assignment == {"t": ("0.100000000000000001", "1")}
    # The compatibility field stays plain binary64, with no subclass leaking through.
    assert [type(v) for v in result.assignment["t"]] == [float, int]


_CLI_HEADER = """\
tvl:
  module: demo.review5
environment:
  snapshot_id: "2025-01-20T00:00:00Z"
evaluation_set:
  dataset: s3://datasets/demo/dev.jsonl
  seed: 2025
objectives:
  - name: answer_accuracy
    metric_ref: metrics.answer_accuracy.v1
    direction: maximize
promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    answer_accuracy: 0.01
"""


def test_cli_json_exact_assignment_carries_tuple_strings(monkeypatch, capsys, tmp_path):
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    from tvl_tools.tvl_check_structural import cli

    path = tmp_path / "m.tvl.yml"
    path.write_text(_CLI_HEADER + textwrap.dedent(_TUPLE_SET))
    monkeypatch.setattr(sys, "argv", ["tvl-check-structural", "--json", str(path)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    # The final PhaseResult is the last JSON document printed.
    doc = json.loads(out[out.rindex('{\n  "schemaVersion"'):])
    assert doc["exact_assignment"] == {"t": ["0.100000000000000001", "1"]}


# 4. membership / negated-interval expansion is budgeted ------------------------------------
def _module(expr: str) -> dict:
    return {
        "tvars": [{"name": "x", "type": "enum[int]", "domain": [0, 1]}],
        "constraints": {"structural": [{"expr": expr}]},
    }


def test_membership_expansion_over_budget_is_undecided(solver):
    result = check_structural(_module(" and ".join(["x in {0,1}"] * 15)))
    assert not result.ok and getattr(result, "undecided", False)
    assert _codes(result) == [structural_sat.EXPANSION_TOO_LARGE_CODE]


def test_negated_interval_expansion_over_budget_is_undecided(solver):
    result = check_structural(_module(" and ".join(["not (0 <= x <= 1)"] * 15)))
    assert _codes(result) == [structural_sat.EXPANSION_TOO_LARGE_CODE]


def test_membership_expansion_within_budget_is_still_decided(solver):
    result = check_structural(_module(" and ".join(["x in {0,1}"] * 10)))
    assert result.ok


def test_exponential_membership_expansion_is_refused_before_materialising():
    code = _NO_ORTOOLS + textwrap.dedent(
        """
        from tvl.structural_sat import check_structural
        module = {
            "tvars": [{"name": "x", "type": "enum[int]", "domain": [0, 1]}],
            "constraints": {"structural": [{"expr": " and ".join(["x in {0,1}"] * 30)}]},
        }
        print([i["code"] for i in check_structural(module).issues])
        """
    )
    proc = _bounded_child(code)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "structural_expansion_too_large" in proc.stdout


# 5. tuple component ranges are counted before allocation ---------------------------------
def test_tuple_component_range_cardinality_checked_before_allocation():
    code = _NO_ORTOOLS + textwrap.dedent(
        """
        from tvl.structural_sat import check_structural
        module = {"tvars": [{"name": "t", "type": "tuple[float,int]", "domain": {"components": [
            {"range": [0.0, 1000000000.0], "resolution": 0.001}, {"set": [1]}]}}]}
        try:
            check_structural(module)
        except ValueError as exc:
            print("REFUSED", exc)
        """
    )
    proc = _bounded_child(code)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "REFUSED" in proc.stdout and "exceeds limit" in proc.stdout


def test_int_tuple_component_range_cardinality_checked_before_allocation():
    code = _NO_ORTOOLS + textwrap.dedent(
        """
        from tvl.model import extract_domains
        try:
            extract_domains([{"name": "t", "type": "tuple[int]", "domain": {"components": [
                {"range": [0, 10**15]}]}}])
        except ValueError as exc:
            print("REFUSED", exc)
        """
    )
    proc = _bounded_child(code)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "REFUSED" in proc.stdout and "exceeds limit" in proc.stdout


# P2a. numeric enum ordering builds the allowed set once -------------------------------------
@pytest.mark.skipif(not HAVE_CPSAT, reason="ortools missing")
def test_numeric_enum_ordering_is_not_quadratic():
    code = textwrap.dedent(
        """
        from tvl.structural_sat import check_structural
        module = {"tvars": [{"name": "x", "type": "enum[int]", "domain": list(range(100_000))}],
                  "constraints": {"structural": [{"expr": "x >= 0"}]}}
        print(check_structural(module).ok)
        """
    )
    proc = _bounded_child(code, seconds=60, memory_bytes=None)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() == "True"


# P2b. tiny resolutions -------------------------------------------------------------------
_TINY = """
tvars:
  - name: x
    type: float
    domain: {range: [0.0, 1.0], resolution: %s}
constraints:
  structural: [{expr: "x == 0.0005"}]
"""


def test_subnormal_resolution_does_not_raise_overflow(solver):
    result = _check(_TINY % "1.0e-309")
    if solver == "cpsat":
        assert _codes(result) == [structural_sat.ENCODING_OVERFLOW_CODE]
    else:
        assert result.ok and result.exact_assignment == {"x": "0.0005"}


def test_underflowed_resolution_is_not_replaced_by_the_default_step(solver):
    # 1e-400 rounds to binary64 0.0; its exact value is positive, so 0.0005 IS on the grid.
    # The default 0.001 step would wrongly report UNSAT.
    result = _check(_TINY % "1.0e-400")
    assert not _decided_unsat(result), (result, _codes(result))


def test_precision_is_computed_exactly():
    domain = extract_domains(_load(_TINY % "1.0e-309")["tvars"])["x"]
    assert domain.step == Fraction(1, 10**309)
    assert domain.precision == 10**309


# _ExactFloat replacement --------------------------------------------------------------------
def test_tuple_literal_components_are_not_floats_when_binary64_cannot_hold_them():
    value = structural_sat._parse_tuple_literal("(0.100000000000000001, 0.5, 1)")
    assert not isinstance(value[0], float)
    assert value[0] == Fraction("0.100000000000000001")
    assert repr(value[0]) == "0.100000000000000001"
    assert type(value[1]) is float and type(value[2]) is int
