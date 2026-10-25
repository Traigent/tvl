"""Regressions for the third independent code review of the structural checker and loader.

Each finding gets a failing-first test. Solver tests run on both backends (CP-SAT and the
fallback search) because the bug class is "the two backends disagree" / "the encoder is
not the evaluator". Resource-exhaustion inputs run in a child process under a time and
memory bound so a regression fails the test instead of hanging or OOM-killing the run.
"""

from __future__ import annotations

import resource
import subprocess
import sys
import textwrap
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON_DIR))

from tvl import structural_sat  # noqa: E402
from tvl.lints import lint_module  # noqa: E402
from tvl.model import ExactFormatLimitError, exact_to_str  # noqa: E402
from tvl.structural_sat import StructuralParseError, check_structural  # noqa: E402
from tvl.yaml_safe import ComplexKeyError, DuplicateKeyError, YAMLLimitError, safe_load  # noqa: E402

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


def _bounded_child(code: str, *, seconds: int = 20, memory_bytes: int = 2 << 30) -> subprocess.CompletedProcess:
    """Run ``code`` in a child interpreter capped at ``seconds`` wall time and ``memory_bytes``."""

    def limit() -> None:  # pragma: no cover - runs in the child
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


# 1. enum pair encoding uses exact equality ------------------------------------------
_ENUM_PAIR = """
tvars:
  - {name: a, type: "enum[float]", domain: [0.1]}
  - {name: b, type: "enum[float]", domain: [0.100000000000000001]}
constraints:
  structural: [{expr: "a %s b"}]
"""


def test_enum_pair_distinct_exact_values_are_unequal(solver):
    result = _check(_ENUM_PAIR % "!=")
    assert result.ok is True
    assert result.exact_assignment == {"a": "0.1", "b": "0.100000000000000001"}


def test_enum_pair_distinct_exact_values_equality_is_unsat(solver):
    result = _check(_ENUM_PAIR % "==")
    assert result.ok is False
    assert not getattr(result, "undecided", False)


def test_enum_pair_int_and_float_members_are_ill_typed(solver):
    # T-TVarEq needs elem(enum[float]) = elem(enum[int]); there is no numeric widening, so the
    # checker refuses the atom as the linter does (it used to compare the members by value).
    result = check_structural(
        {
            "tvars": [
                {"name": "a", "type": "enum[float]", "domain": [1.0, 0.5]},
                {"name": "b", "type": "enum[int]", "domain": [1]},
            ],
            "constraints": {"structural": [{"expr": "a == b"}]},
        }
    )
    assert result.ok is False and getattr(result, "undecided", False)
    assert result.issues[0]["code"] == "structural_ill_typed_atom"


# 2. merge expansion is bounded ----------------------------------------------------------
def test_exponential_merge_chain_is_rejected_quickly():
    code = textwrap.dedent(
        """
        from tvl.yaml_safe import YAMLLimitError, safe_load
        text = "n0: &n0 {x: 1}\\n" + "".join(
            f"n{i}: &n{i} {{<<: [*n{i-1}, *n{i-1}]}}\\n" for i in range(1, 31)
        )
        try:
            safe_load(text)
        except YAMLLimitError as exc:
            print("LIMIT", exc)
        else:
            print("LOADED")
        """
    )
    proc = _bounded_child(code)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.startswith("LIMIT"), proc.stdout + proc.stderr[-2000:]
    assert "merge" in proc.stdout


def test_ordinary_merges_still_load():
    doc = safe_load("base: &b {x: 1, y: 2}\nover: {<<: *b, y: 3}\nmulti: {<<: [*b, {z: 4}]}\n")
    assert doc["over"] == {"x": 1, "y": 3}
    assert doc["multi"] == {"x": 1, "y": 2, "z": 4}


# 3. absent literals: equality false, inequality TRUE, ordering exact ----------------------
@pytest.mark.parametrize(
    "expr,ok",
    [("x != 0.2", True), ("x == 0.2", False), ("x < 0.2", True), ("x > 0.2", False)],
)
def test_absent_numeric_enum_literal_polarity(solver, expr, ok):
    result = _check(
        f"""
        tvars:
          - {{name: x, type: "enum[float]", domain: [0.1]}}
        constraints:
          structural: [{{expr: "{expr}"}}]
        """
    )
    assert result.ok is ok
    assert not getattr(result, "undecided", False)


@pytest.mark.parametrize("expr,ok", [("x != 'zz'", True), ("x == 'zz'", False), ("not (x == 'zz')", True)])
def test_absent_string_enum_literal_polarity(solver, expr, ok):
    result = _check(
        f"""
        tvars:
          - {{name: x, type: "enum[str]", domain: [a]}}
        constraints:
          structural: [{{expr: "{expr}"}}]
        """
    )
    assert result.ok is ok


@pytest.mark.parametrize(
    "expr,ok,witness",
    [("n != 2.5", True, None), ("n == 2.5", False, None), ("n > 2.5 and n < 3.5", True, 3)],
)
def test_int_domain_with_fractional_literal_is_ill_typed(solver, expr, ok, witness):
    # T-Eq/T-Cmp need n : elem(int) = int and 2.5 has type float; the linter rejects the atom
    # (constraint_type_mismatch), so the checker no longer decides it.
    result = _check(
        f"""
        tvars:
          - {{name: n, type: int, domain: {{range: [0, 4]}}}}
        constraints:
          structural: [{{expr: "{expr}"}}]
        """
    )
    assert result.ok is False and getattr(result, "undecided", False)
    assert result.issues[0]["code"] == "structural_ill_typed_atom"


@pytest.mark.parametrize("op,ok", [("!=", True), ("==", True)])
def test_numeric_enum_vs_int_identifier(solver, op, ok):
    result = _check(
        f"""
        tvars:
          - {{name: x, type: "enum[int]", domain: [1]}}
          - {{name: y, type: int, domain: {{range: [1, 2]}}}}
        constraints:
          structural: [{{expr: "x {op} y"}}]
        """
    )
    assert result.ok is ok
    assert (result.assignment["y"] == 1) is (op == "==")


@pytest.mark.parametrize(
    "tvars,expr",
    [
        ('[{name: x, type: int, domain: {range: [0, 3]}}]', "not (ghost == 1)"),
        ('[{name: x, type: int, domain: {range: [0, 3]}}, {name: b, type: bool}]', "x != b"),
        ('[{name: x, type: "enum[str]", domain: [a, b]}]', "x < 'b'"),
        ('[{name: x, type: int, domain: {range: [0, 3]}}]', "x == 'high'"),
    ],
    ids=["unknown-ident", "int-vs-bool", "string-ordering", "int-vs-string"],
)
def test_ill_typed_atoms_fail_closed_not_unsat(solver, tvars, expr):
    result = _check(f"tvars: {tvars}\nconstraints:\n  structural: [{{expr: \"{expr}\"}}]\n")
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert _codes(result) == ["structural_ill_typed_atom"]


# 4. collection keys are rejected; '=' keys are checked ---------------------------------------
def test_tagged_mapping_key_cannot_bypass_duplicate_check():
    with pytest.raises(ComplexKeyError) as caught:
        safe_load("promotion_policy:\n  ? !!str {=: alpha}\n  : 0.05\n  alpha: 0.1\n")
    assert isinstance(caught.value, yaml.YAMLError)
    assert caught.value.code == "complex_mapping_key"


def test_sequence_key_is_rejected():
    with pytest.raises(ComplexKeyError):
        safe_load("? [a, b]\n: 1\n")


def test_value_indicator_key_duplicate_is_rejected():
    with pytest.raises(DuplicateKeyError):
        safe_load("a: {=: 1, '=': 2}\n")


# 5. exact witness formatting never raises; absurd literals rejected at load -----------------
def test_huge_exponent_literal_rejected_at_load():
    text = textwrap.dedent(
        """
        tvars:
          - name: x
            type: float
            domain: {range: [1.0e-5000, 1.0], resolution: 0.1}
        constraints:
          structural: [{expr: "x > 0.05 and x < 0.15"}]
        """
    )
    with pytest.raises(YAMLLimitError) as caught:
        safe_load(text)
    assert "exponent" in str(caught.value)


def test_enormous_exponent_literal_does_not_hang_the_loader():
    code = textwrap.dedent(
        """
        from tvl.yaml_safe import YAMLLimitError, safe_load
        try:
            safe_load("a: 1.0e-99999999\\n")
        except YAMLLimitError:
            print("LIMIT")
        else:
            print("LOADED")
        """
    )
    proc = _bounded_child(code, seconds=20)
    assert proc.stdout.strip() == "LIMIT", proc.stdout + proc.stderr[-2000:]


def test_ordinary_small_exponents_still_load():
    doc = safe_load("a: 1.0e-300\nb: 0.100000000000000001\n")
    assert doc["a"] == 1e-300


def test_overlong_expression_literal_is_a_parse_error_not_silently_rounded(solver):
    # Expression numbers are digits and one dot (no exponent). A 5000-digit literal used to
    # exceed Python's int->str limit inside Fraction(), and the checker then fell back to the
    # binary64 value silently; it is now refused like any other malformed literal.
    literal = "0." + "0" * 4999 + "1"
    with pytest.raises(StructuralParseError):
        check_structural(
            {
                "tvars": [{"name": "x", "type": "float", "domain": {"range": [0.0, 1.0], "resolution": 0.1}}],
                "constraints": {"structural": [{"expr": f"x > {literal}"}]},
            }
        )


def test_exact_to_str_bounds_output():
    with pytest.raises(ExactFormatLimitError):
        exact_to_str(Fraction(10**4999 + 1, 10**5000))
    assert exact_to_str(Fraction(1, 10)) == "0.1"


def test_unformattable_witness_is_undecided_not_an_exception():
    expr = structural_sat.Expression(path=["constraints", "structural", 0], text="", dnf=None,  # type: ignore[arg-type]
                                     expanded_clauses=[[]], clause_strings=[])
    result = structural_sat._sat_result([expr], {"x": Fraction(10**4999 + 1, 10**5000)})
    assert result.ok is False
    assert _codes(result) == ["structural_witness_too_large"]


# 6. non-finite domain values fail closed -------------------------------------------------------
@pytest.mark.parametrize(
    "decl",
    [
        '{name: x, type: "enum[float]", domain: [.nan]}',
        '{name: x, type: float, domain: {range: [0, .inf]}}',
        '{name: x, type: float, domain: {range: [0, 1], resolution: .inf}}',
        '{name: x, type: "enum[float]", domain: [-.inf, 1.0]}',
    ],
    ids=["nan-enum", "inf-range", "inf-resolution", "neg-inf-enum"],
)
def test_non_finite_domain_values_are_rejected(solver, decl):
    text = f"tvars:\n  - {decl}\nconstraints:\n  structural: [{{expr: \"not (0 <= x <= 1)\"}}]\n"
    result = check_structural(safe_load(text))
    assert result.ok is False
    assert getattr(result, "undecided", False) is True
    assert _codes(result) == ["structural_non_finite_domain"]
    lint_codes = [issue["code"] for issue in lint_module(safe_load(text))]
    assert "non_finite_domain_value" in lint_codes


# 7. registry-backed (unresolved) domains are never decided from placeholders --------------
@pytest.mark.parametrize("expr", ["x == 1", "x != 1"])
def test_referenced_registry_domain_is_undecided(solver, expr):
    result = _check(
        f"""
        tvars:
          - {{name: x, type: int, domain: {{registry: foo}}}}
        constraints:
          structural: [{{expr: "{expr}"}}]
        """
    )
    assert result.ok is False
    assert _codes(result) == ["structural_unresolved_domain"]


def test_referenced_registry_enum_is_undecided(solver):
    result = _check(
        """
        tvars:
          - {name: m, type: "enum[str]", domain: {registry: models}}
        constraints:
          structural: [{expr: "m == 'gpt-4'"}]
        """
    )
    assert _codes(result) == ["structural_unresolved_domain"]


def test_unreferenced_registry_int_domain_does_not_block_a_witness(solver):
    result = _check(
        """
        tvars:
          - {name: x, type: int, domain: {registry: foo}}
          - {name: n, type: int, domain: {range: [0, 3]}}
        constraints:
          structural: [{expr: "n == 2"}]
        """
    )
    assert result.ok is True
    assert result.assignment["n"] == 2


# 8. the same unbounded-exponent hang in the runtime profile decimal parser -----------------
def test_runtime_to_fraction_rejects_enormous_exponent_quickly():
    code = textwrap.dedent(
        """
        from tvl.canonical import RuntimeClosedError, to_fraction
        try:
            to_fraction("1e-99999999")
        except RuntimeClosedError as exc:
            print("CLOSED", exc.code)
        else:
            print("PARSED")
        """
    )
    proc = _bounded_child(code, seconds=20)
    assert proc.stdout.strip() == "CLOSED runtime_invalid_profile", proc.stdout + proc.stderr[-2000:]
