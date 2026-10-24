"""Regressions for the fourth independent code review of the structural checker.

Each finding gets a failing-first test. Solver tests run on both backends (CP-SAT and the
fallback search). Resource-exhaustion and non-termination inputs run in a child process
under a time and memory bound so a regression fails the test instead of hanging or
OOM-killing the run.
"""

from __future__ import annotations

import resource
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON_DIR))

from tvl import structural_sat  # noqa: E402
from tvl.structural_sat import StructuralParseError, check_structural  # noqa: E402
from tvl.yaml_safe import safe_load  # noqa: E402

HAVE_CPSAT = structural_sat.cp_model is not None


@pytest.fixture(params=["cpsat", "fallback"])
def solver(request, monkeypatch):
    if request.param == "fallback":
        monkeypatch.setattr(structural_sat, "cp_model", None)
    elif not HAVE_CPSAT:
        pytest.skip("ortools missing")
    return request.param


def _check(text: str):
    return check_structural(safe_load(textwrap.dedent(text)))


def _codes(result) -> list:
    return [issue["code"] for issue in (getattr(result, "issues", None) or [])]


def _bounded_child(code: str, *, seconds: int = 30, memory_bytes: int | None = 2 << 30) -> subprocess.CompletedProcess:
    """Run ``code`` in a child interpreter capped at ``seconds`` wall time and, if given, ``memory_bytes`` of address space.

    ``memory_bytes=None`` applies only the wall-time bound. RLIMIT_AS is unsuitable for code that
    imports OR-Tools (CP-SAT): its worker threads reserve address space at start-up and fail with
    ``std::system_error`` under a tight cap, so tests that load that module pass ``None``.
    """

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


# 1. tuple literal components are exact --------------------------------------------------
_TUPLE = """
tvars:
  - name: t
    type: tuple[float,int]
    domain:
      components:
        - {set: [0.100000000000000001]}
        - {set: [1]}
constraints:
  structural:
    - expr: "t %s (0.100000000000000001, 1)"
"""


def test_tuple_exact_literal_inequality_is_unsat(solver):
    result = _check(_TUPLE % "!=")
    assert not getattr(result, "undecided", False), _codes(result)
    assert result.ok is False
    assert result.unsat_core


def test_tuple_exact_literal_equality_is_sat(solver):
    result = _check(_TUPLE % "==")
    assert result.ok is True


def test_tuple_literal_distinct_from_rounded_component(solver):
    # 0.1 (the binary64 neighbour) is NOT the declared 0.100000000000000001.
    result = _check((_TUPLE % "==").replace("(0.100000000000000001, 1)", "(0.1, 1)"))
    assert not getattr(result, "undecided", False), _codes(result)
    assert result.ok is False


def test_tuple_literal_component_out_of_bounds_is_a_parse_error(solver):
    text = (_TUPLE % "==").replace("(0.100000000000000001, 1)", "(1e-99999, 1)")
    with pytest.raises(StructuralParseError):
        _check(text)


def test_tuple_float_literal_with_int_component_still_matches(solver):
    result = _check(
        """
        tvars:
          - name: t
            type: tuple[float,int]
            domain:
              components:
                - {set: [0.5, 0.25]}
                - {set: [1, 2]}
        constraints:
          structural:
            - expr: "t == (0.25, 2)"
        """
    )
    assert result.ok is True
    assert tuple(result.assignment["t"]) == (0.25, 2)


# 2. duplicate enum members ----------------------------------------------------------------
@pytest.mark.parametrize("backend", ["cpsat", "fallback"])
def test_duplicate_enum_members_do_not_allocate_quadratic_pairs(backend):
    if backend == "cpsat" and not HAVE_CPSAT:
        pytest.skip("ortools missing")
    code = textwrap.dedent(
        f"""
        from tvl import structural_sat
        if {backend!r} == "fallback":
            structural_sat.cp_model = None
        module = {{
            "tvars": [
                {{"name": n, "type": "enum[int]", "domain": [1] * 20_000}} for n in ("a", "b")
            ],
            "constraints": {{"structural": [{{"expr": "a == b"}}]}},
        }}
        r = structural_sat.check_structural(module)
        print("OK", r.ok, r.assignment)
        """
    )
    # 2 GiB: CP-SAT's worker threads need address space; 4e8 Python pairs need ~25 GiB.
    proc = _bounded_child(code, seconds=30, memory_bytes=2 << 30)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "OK True {'a': 1, 'b': 1}" in proc.stdout


def test_duplicate_members_are_normalised_as_a_set(solver):
    result = _check(
        """
        tvars:
          - {name: a, type: "enum[str]", domain: ["x", "x", "y"]}
          - {name: b, type: "enum[str]", domain: ["y", "x", "x"]}
        constraints:
          structural:
            - expr: "a == b and a != \\"x\\""
        """
    )
    assert result.ok is True
    assert result.assignment == {"a": "y", "b": "y"}


def test_pair_table_bound_is_undecided_with_code(monkeypatch):
    if not HAVE_CPSAT:
        pytest.skip("ortools missing")
    monkeypatch.setattr(structural_sat, "_MAX_PAIR_TABLE", 2)
    result = _check(
        """
        tvars:
          - {name: a, type: "enum[int]", domain: [1, 2, 3]}
          - {name: b, type: "enum[int]", domain: [1, 2, 3]}
        constraints:
          structural: [{expr: "a == b"}]
        """
    )
    assert getattr(result, "undecided", False) is True
    assert result.ok is False
    assert _codes(result) == [structural_sat.PAIR_TABLE_TOO_LARGE_CODE]


# 3. cyclic aliases terminate in the non-finite scans --------------------------------------
_CYCLIC = '''
tvars:
  - name: x
    type: bool
    domain: &d [*d]
constraints:
  structural: [{expr: "x == true"}]
'''


@pytest.mark.parametrize("entry", ["check", "lint"])
def test_cyclic_alias_scans_terminate(entry):
    code = textwrap.dedent(
        f"""
        from tvl import structural_sat
        from tvl.lints import _first_non_finite, lint_module
        from tvl.structural_sat import _non_finite_issue
        from tvl.yaml_safe import safe_load
        doc = safe_load({_CYCLIC!r})
        if {entry!r} == "check":
            assert _non_finite_issue(doc["tvars"]) is None
            r = structural_sat.check_structural(doc)
            print("DONE", r.ok)
        else:
            assert _first_non_finite(doc["tvars"]) is None
            lint_module(doc)
            print("DONE")
        """
    )
    proc = _bounded_child(code, seconds=20, memory_bytes=None)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "DONE" in proc.stdout


def test_cyclic_alias_with_non_finite_value_is_still_found():
    code = textwrap.dedent(
        """
        from tvl import structural_sat
        from tvl.lints import _first_non_finite
        inner = [float("nan")]
        inner.append(inner)
        tvars = [{"name": "x", "type": "enum[float]", "domain": inner}]
        message = structural_sat._non_finite_issue(tvars)
        assert message is not None and "nan" in message, message
        found = _first_non_finite(tvars)
        assert found is not None and found[1] != found[1], found
        print("DONE")
        """
    )
    proc = _bounded_child(code, seconds=20, memory_bytes=None)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "DONE" in proc.stdout


def test_shared_non_cyclic_alias_is_scanned_on_every_path():
    shared = [1.0]
    tvars = [{"name": "a", "domain": shared}, {"name": "b", "domain": shared}]
    assert structural_sat._non_finite_issue(tvars) is None


# 4. registry status comes from declaration provenance ------------------------------------
def test_placeholder_prefixed_string_in_explicit_enum_is_decided(solver):
    result = _check(
        """
        tvars:
          - name: x
            type: enum[str]
            domain: ["__registry_unresolved_real"]
        constraints:
          structural:
            - expr: 'x == "__registry_unresolved_real"'
        """
    )
    assert not getattr(result, "undecided", False), _codes(result)
    assert result.ok is True
    assert result.assignment == {"x": "__registry_unresolved_real"}


def test_placeholder_prefixed_string_in_tuple_component_is_decided(solver):
    result = _check(
        """
        tvars:
          - name: t
            type: tuple[str,int]
            domain:
              components:
                - {set: ["__registry_unresolved_0__"]}
                - {set: [1]}
        constraints:
          structural:
            - expr: 't != ("__registry_unresolved_0__", 1)'
        """
    )
    assert not getattr(result, "undecided", False), _codes(result)
    assert result.ok is False


@pytest.mark.parametrize(
    "domain",
    [
        "{registry: models}",
        "{components: [{registry: models}, {set: [1]}]}",
    ],
)
def test_registry_backed_declarations_stay_unresolved(solver, domain):
    kind = "enum[str]" if "components" not in domain else "tuple[str,int]"
    result = _check(
        f"""
        tvars:
          - name: x
            type: {kind}
            domain: {domain}
        constraints:
          structural:
            - expr: 'x != "a"'
        """
    )
    assert getattr(result, "undecided", False) is True
    assert _codes(result) == [structural_sat.UNRESOLVED_DOMAIN_CODE]
