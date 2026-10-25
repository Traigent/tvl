"""Regressions for the sixth independent code review of the structural checker.

Each finding gets a failing-first test. Solver tests run on both backends (CP-SAT and the
fallback search). The amplification input runs in a child process under a wall-time bound
only: it loads OR-Tools, whose threads cannot start under RLIMIT_AS.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON_DIR))

from tvl import structural_sat  # noqa: E402
from tvl.model import extract_domains  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402
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


def _bounded_child(code: str, *, seconds: int = 30) -> subprocess.CompletedProcess:
    """Run ``code`` in a child interpreter bounded by ``seconds`` of wall time (no RLIMIT_AS)."""
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=seconds,
        env={"PYTHONPATH": str(PYTHON_DIR), "PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
        check=False,
    )


# 1. reversed ranges are malformed (semantics §2.4: a <= b) ------------------------------------


_REVERSED_TUPLE = """
    tvars:
      - name: t
        type: tuple[{kind},int]
        domain:
          components:
            - {component}
            - {{set: [1]}}
    constraints:
      structural:
        - expr: "t == ({hi}, 1)"
"""


@pytest.mark.parametrize(
    "kind, component, hi",
    [
        ("float", "{range: [1.0, 0.0], resolution: 0.1}", "1.0"),  # the reviewer's input
        ("float", "{range: [1.0, 0.95], resolution: 0.1}", "1.0"),  # reversed by less than one step
        ("float", "{range: [1.0, 0.0]}", "1.0"),  # default resolution
        ("int", "{range: [3, 1]}", "3"),
        ("int", "{range: [3, 1], resolution: 1}", "3"),
    ],
)
def test_reversed_tuple_component_range_is_rejected(solver, kind, component, hi):
    module = _load(_REVERSED_TUPLE.format(kind=kind, component=component, hi=hi))
    with pytest.raises(ValueError, match=r"t: tuple component 0 has no 'values', 'set', valid 'range'"):
        check_structural(module)


def test_reversed_tuple_component_range_never_becomes_a_singleton():
    with pytest.raises(ValueError, match="valid 'range'"):
        extract_domains(
            [{"name": "t", "type": "tuple", "domain": {"components": [{"range": [1.0, 0.0], "resolution": 0.1}]}}]
        )


def test_equal_endpoints_remain_a_singleton(solver):
    module = _load(_REVERSED_TUPLE.format(kind="float", component="{range: [1.0, 1.0], resolution: 0.1}", hi="1.0"))
    result = check_structural(module)
    assert result.ok is True
    assert result.assignment == {"t": (1.0, 1)}


@pytest.mark.parametrize("kind, rng", [("float", "[1.0, 0.0]"), ("float", "[1.0, 0.0], resolution: 0.1"), ("int", "[3, 1]")])
def test_reversed_scalar_range_is_rejected(solver, kind, rng):
    module = _load(
        f"""
        tvars:
          - name: x
            type: {kind}
            domain: {{range: {rng}}}
        constraints:
          structural:
            - expr: "x >= 0"
        """
    )
    with pytest.raises(ValueError, match=r"x: range domain \[.*\] is empty"):
        check_structural(module)


def test_reversed_scalar_range_compares_exact_endpoints():
    # 0.1 and 0.100000000000000001 share a binary64 value; exactly, lo > hi.
    with pytest.raises(ValueError, match="is empty"):
        extract_domains([{"name": "x", "type": "float", "domain": {"range": ["0.100000000000000001", "0.1"]}}])
    # Equal endpoints stay a valid singleton.
    domains = extract_domains([{"name": "x", "type": "float", "domain": {"range": [0.5, 0.5]}}])
    assert domains["x"].minimum == domains["x"].maximum == 0.5


# 2. shared nested tuples are never expanded exponentially -------------------------------------


def test_shared_nested_tuple_is_bounded_and_undecided_on_cpsat():
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    code = textwrap.dedent(
        """
        import time
        from tvl.structural_sat import check_structural
        value = (0,)
        for _ in range(30):
            value = (value, value)
        module = {
            "tvars": [{"name": "t", "type": "tuple", "domain": {"components": [{"values": [value]}]}}],
            "constraints": {"structural": []},
        }
        start = time.monotonic()
        result = check_structural(module)
        print("ELAPSED", time.monotonic() - start)
        print("RESULT", result.ok, getattr(result, "undecided", False), [i["code"] for i in result.issues])
        """
    )
    proc = _bounded_child(code, seconds=20)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "RESULT False True ['structural_value_too_large']" in proc.stdout
    elapsed = float(proc.stdout.split("ELAPSED", 1)[1].split()[0])
    assert elapsed < 2.0, proc.stdout


def test_shared_nested_tuple_fallback_is_bounded():
    code = textwrap.dedent(
        """
        import sys
        sys.modules["ortools"] = None
        from tvl.structural_sat import check_structural
        value = (0,)
        for _ in range(30):
            value = (value, value)
        module = {
            "tvars": [{"name": "t", "type": "tuple", "domain": {"components": [{"values": [value]}]}}],
            "constraints": {"structural": []},
        }
        result = check_structural(module)
        print("RESULT", result.ok, getattr(result, "undecided", False), [i["code"] for i in result.issues])
        """
    )
    proc = _bounded_child(code, seconds=20)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "RESULT False True ['structural_value_too_large']" in proc.stdout


def test_repeated_large_member_counts_every_occurrence(solver):
    value = (0,)
    for _ in range(12):  # 8191 nodes per occurrence: one is fine, a thousand exceed the budget
        value = (value, value)
    module = {
        "tvars": [{"name": "t", "type": "tuple", "domain": {"components": [{"values": [value] * 1000}]}}],
        "constraints": {"structural": []},
    }
    result = check_structural(module)
    assert result.ok is False and result.undecided is True
    assert [i["code"] for i in result.issues] == [structural_sat.VALUE_TOO_LARGE_CODE]


def test_cyclic_list_member_is_undecided_not_a_recursion_error(solver):
    cyclic: list = [0]
    cyclic.append(cyclic)
    module = {"tvars": [{"name": "t", "type": "enum", "domain": [cyclic]}], "constraints": {"structural": []}}
    result = check_structural(module)
    assert result.undecided is True
    assert [i["code"] for i in result.issues] == [structural_sat.VALUE_TOO_LARGE_CODE]


def test_deep_unshared_nesting_is_undecided_not_a_recursion_error(solver):
    value: tuple = (0,)
    for _ in range(5000):
        value = (value,)
    module = {"tvars": [{"name": "t", "type": "enum", "domain": [value]}], "constraints": {"structural": []}}
    result = check_structural(module)
    assert result.undecided is True
    assert [i["code"] for i in result.issues] == [structural_sat.VALUE_TOO_LARGE_CODE]


def test_small_shared_tuple_still_solves_with_the_shared_witness(solver):
    value = (0,)
    for _ in range(4):
        value = (value, value)
    module = {
        "tvars": [{"name": "t", "type": "tuple", "domain": {"components": [{"values": [value, value]}]}}],
        "constraints": {"structural": []},
    }
    result = check_structural(module)
    assert result.ok is True
    assert result.assignment == {"t": (value,)}


def test_large_flat_enum_is_not_charged_against_the_value_budget(solver):
    module = {
        "tvars": [{"name": "x", "type": "enum[int]", "domain": list(range(20_000))}],
        "constraints": {"structural": [{"expr": "x == 19999"}]},
    }
    result = check_structural(module)
    assert result.ok is True
    assert result.assignment == {"x": 19999}
