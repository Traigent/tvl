"""Characterization tests for the structural SAT encoder helpers.

These pin the *current* observable behaviour of ``_encode_condition`` and
``_candidate_values`` so that a behaviour-preserving refactor of either
function cannot change results silently. They are not a statement that every
pinned behaviour is the intended one; where a case looks surprising it is
called out, and the expected value is still the current one.

``_encode_condition`` is pinned semantically: for every assignment of the
variables involved, the test records which values (0 and/or 1) the reified
literal can take, by solving the model with the variables and the literal
fixed. Any change to the emitted constraints that changes that truth table
turns a test red.
"""

from __future__ import annotations

import itertools
from fractions import Fraction
from typing import Any, Callable, Dict, List, Sequence, Tuple

import pytest

cp_model = pytest.importorskip("ortools.sat.python.cp_model")

from tvl.model import Domain  # noqa: E402
from tvl.structural_sat import (  # noqa: E402
    Condition,
    Expression,
    _candidate_values,
    _encode_condition,
)


# --------------------------------------------------------------------------- #
# _encode_condition
# --------------------------------------------------------------------------- #

def _enc_range(domain: Domain) -> range:
    if domain.kind == "bool":
        return range(0, 2)
    if domain.kind == "enum":
        return range(0, max(len(domain.values or []) - 1, 0) + 1)
    return range(
        domain._encode_bound_lower(domain.minimum),
        domain._encode_bound_upper(domain.maximum) + 1,
    )


def _new_var(model: Any, name: str, domain: Domain) -> Any:
    if domain.kind == "bool":
        return model.NewBoolVar(name)
    rng = _enc_range(domain)
    return model.NewIntVar(rng.start, rng.stop - 1, name)


def _truth_table(
    domains: Dict[str, Domain], condition: Condition, name: str = "c"
) -> Dict[Tuple[int, ...], Tuple[int, ...]]:
    """Map each encoded assignment to the feasible values of the literal."""
    names = list(domains)
    table: Dict[Tuple[int, ...], Tuple[int, ...]] = {}
    for combo in itertools.product(*(_enc_range(domains[n]) for n in names)):
        allowed: List[int] = []
        for forced in (0, 1):
            model = cp_model.CpModel()
            var_map = {n: _new_var(model, n, d) for n, d in domains.items()}
            lit = _encode_condition(model, var_map, domains, condition, name)
            assert lit.Name() == name
            for n, value in zip(names, combo):
                model.Add(var_map[n] == value)
            model.Add(lit == forced)
            status = cp_model.CpSolver().Solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                allowed.append(forced)
        table[combo] = tuple(allowed)
    return table


def _expected(
    domains: Dict[str, Domain], predicate: Callable[..., bool]
) -> Dict[Tuple[int, ...], Tuple[int, ...]]:
    names = list(domains)
    return {
        combo: ((1,) if predicate(*combo) else (0,))
        for combo in itertools.product(*(_enc_range(domains[n]) for n in names))
    }


def _const(domains: Dict[str, Domain], value: int) -> Dict[Tuple[int, ...], Tuple[int, ...]]:
    return _expected(domains, lambda *_: bool(value))


INT = Domain(path="n", kind="int", minimum=0, maximum=4)
FLT = Domain(path="t", kind="float", minimum=0.0, maximum=1.0, precision=10)
BOOL = Domain(path="b", kind="bool")
ENUM = Domain(path="e", kind="enum", values=["a", "b", "c"])


# --- unknown identifiers ---------------------------------------------------- #

def test_encode_condition_unknown_lhs_is_false() -> None:
    domains = {"n": INT}
    assert _truth_table(domains, Condition("missing", "==", 1)) == _const(domains, 0)


def test_encode_condition_lhs_domain_without_variable_is_false() -> None:
    # A domain the caller has no variable for behaves like an unknown ident.
    model = cp_model.CpModel()
    lit = _encode_condition(model, {}, {"n": INT}, Condition("n", "==", 1), "c")
    solver = cp_model.CpSolver()
    model.Add(lit == 1)
    assert solver.Solve(model) == cp_model.INFEASIBLE


# --- identifier-to-identifier comparisons ----------------------------------- #

def test_encode_condition_rhs_unknown_is_false() -> None:
    domains = {"n": INT}
    cond = Condition("n", "==", None, rhs_ident="ghost")
    assert _truth_table(domains, cond) == _const(domains, 0)


@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_encode_condition_rhs_ordering_ops_are_false(op: str) -> None:
    domains = {"n": INT, "m": Domain(path="m", kind="int", minimum=0, maximum=2)}
    cond = Condition("n", op, None, rhs_ident="m")
    assert _truth_table(domains, cond) == _const(domains, 0)


@pytest.mark.parametrize("op", ["==", "!="])
def test_encode_condition_enum_enum_shared_values(op: str) -> None:
    left = Domain(path="l", kind="enum", values=["a", "b", "c"])
    right = Domain(path="r", kind="enum", values=["b", "c", "d"])
    domains = {"l": left, "r": right}
    cond = Condition("l", op, None, rhs_ident="r")

    def pred(i: int, j: int) -> bool:
        same = left.values[i] == right.values[j]
        return same if op == "==" else not same

    assert _truth_table(domains, cond) == _expected(domains, pred)


@pytest.mark.parametrize("op,value", [("==", 0), ("!=", 1)])
def test_encode_condition_enum_enum_no_shared_values(op: str, value: int) -> None:
    domains = {
        "l": Domain(path="l", kind="enum", values=["a", "b"]),
        "r": Domain(path="r", kind="enum", values=["x", "y"]),
    }
    cond = Condition("l", op, None, rhs_ident="r")
    assert _truth_table(domains, cond) == _const(domains, value)


@pytest.mark.parametrize("op,value", [("==", 0), ("!=", 1)])
def test_encode_condition_enum_enum_empty_values(op: str, value: int) -> None:
    domains = {
        "l": Domain(path="l", kind="enum", values=[]),
        "r": Domain(path="r", kind="enum", values=["x"]),
    }
    cond = Condition("l", op, None, rhs_ident="r")
    assert _truth_table(domains, cond) == _const(domains, value)


def test_encode_condition_enum_enum_bool_int_hash_alias() -> None:
    # True and 1 hash equal, so they count as a shared value.
    left = Domain(path="l", kind="enum", values=[True, "x"])
    right = Domain(path="r", kind="enum", values=[1, "y"])
    domains = {"l": left, "r": right}
    cond = Condition("l", "==", None, rhs_ident="r")
    assert _truth_table(domains, cond) == _expected(domains, lambda i, j: (i, j) == (0, 0))


@pytest.mark.parametrize("op", ["==", "!="])
def test_encode_condition_bool_bool(op: str) -> None:
    domains = {"a": Domain(path="a", kind="bool"), "b": Domain(path="b", kind="bool")}
    cond = Condition("a", op, None, rhs_ident="b")
    pred = (lambda x, y: x == y) if op == "==" else (lambda x, y: x != y)
    assert _truth_table(domains, cond) == _expected(domains, pred)


@pytest.mark.parametrize("op", ["==", "!="])
@pytest.mark.parametrize(
    "left,right",
    [
        (Domain(path="x", kind="int", minimum=0, maximum=3), Domain(path="y", kind="int", minimum=1, maximum=4)),
        (Domain(path="x", kind="int", minimum=0, maximum=1), Domain(path="y", kind="float", minimum=0.0, maximum=1.0, precision=4)),
        (Domain(path="x", kind="float", minimum=0.0, maximum=1.0, precision=2), Domain(path="y", kind="float", minimum=0.0, maximum=1.0, precision=4)),
    ],
    ids=["int-int", "int-float", "float-float"],
)
def test_encode_condition_numeric_numeric(op: str, left: Domain, right: Domain) -> None:
    domains = {"x": left, "y": right}
    cond = Condition("x", op, None, rhs_ident="y")

    def value(domain: Domain, enc: int) -> Fraction:
        return Fraction(enc, domain.precision) if domain.kind == "float" else Fraction(enc)

    def pred(i: int, j: int) -> bool:
        same = value(left, i) == value(right, j)
        return same if op == "==" else not same

    assert _truth_table(domains, cond) == _expected(domains, pred)


@pytest.mark.parametrize(
    "left,right",
    [(ENUM, BOOL), (BOOL, INT), (INT, ENUM)],
    ids=["enum-bool", "bool-int", "int-enum"],
)
def test_encode_condition_mixed_kinds_are_false(left: Domain, right: Domain) -> None:
    domains = {"l": left, "r": right}
    cond = Condition("l", "==", None, rhs_ident="r")
    assert _truth_table(domains, cond) == _const(domains, 0)


# --- identifier-to-literal comparisons -------------------------------------- #

_INT_OPS: Dict[str, Callable[[int, int], bool]] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
}


@pytest.mark.parametrize("op", sorted(_INT_OPS))
def test_encode_condition_int_literal(op: str) -> None:
    domains = {"n": INT}
    assert _truth_table(domains, Condition("n", op, 2)) == _expected(
        domains, lambda v: _INT_OPS[op](v, 2)
    )


def test_encode_condition_int_literal_true_encodes_as_one() -> None:
    domains = {"n": INT}
    assert _truth_table(domains, Condition("n", "==", True)) == _expected(domains, lambda v: v == 1)


@pytest.mark.parametrize("value", ["x", 2.5, None])
def test_encode_condition_int_literal_unencodable_is_false(value: Any) -> None:
    domains = {"n": INT}
    assert _truth_table(domains, Condition("n", "==", value)) == _const(domains, 0)


def test_encode_condition_unknown_operator_is_false() -> None:
    domains = {"n": INT}
    assert _truth_table(domains, Condition("n", "~", 2)) == _const(domains, 0)


# Float domain: precision 10 over [0, 1] -> encoded 0..10.
# Strict operators: the literal bound is moved to the nearest admissible grid index and
# compared non-strictly, so `t > 0.3` admits encoded >= 4 and `t < 0.3` admits <= 2.
# (Previously the offset was applied twice, which wrongly excluded satisfying points:
# review finding 2026-10-24.)
@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", 0.3, lambda e: e == 3),
        ("!=", 0.3, lambda e: e != 3),
        ("==", 0.35, lambda e: False),
        ("!=", 0.35, lambda e: True),
        (">=", 0.3, lambda e: e >= 3),
        (">=", 0.35, lambda e: e >= 4),
        (">", 0.3, lambda e: e > 3),
        (">", 0.35, lambda e: e > 3),
        ("<=", 0.3, lambda e: e <= 3),
        ("<=", 0.35, lambda e: e <= 3),
        ("<", 0.3, lambda e: e < 3),
        ("<", 0.35, lambda e: e < 4),
        ("==", 1, lambda e: e == 10),
        (">=", 0, lambda e: True),
    ],
)
def test_encode_condition_float_literal(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    domains = {"t": FLT}
    assert _truth_table(domains, Condition("t", op, value)) == _expected(domains, predicate)


@pytest.mark.parametrize(
    "op,value",
    [("==", "high"), ("~", 0.3), ("~", 0.35), (">=", None)],
)
def test_encode_condition_float_literal_unencodable_or_unknown_op_is_false(op: str, value: Any) -> None:
    domains = {"t": FLT}
    assert _truth_table(domains, Condition("t", op, value)) == _const(domains, 0)


@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", True, lambda v: v == 1),
        ("==", False, lambda v: v == 0),
        ("!=", True, lambda v: v != 1),
        ("==", 1, lambda v: v == 1),
        ("<", True, lambda v: v < 1),
    ],
)
def test_encode_condition_bool_literal(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    domains = {"b": BOOL}
    assert _truth_table(domains, Condition("b", op, value)) == _expected(domains, predicate)


def test_encode_condition_bool_literal_unencodable_is_false() -> None:
    domains = {"b": BOOL}
    assert _truth_table(domains, Condition("b", "==", "yes")) == _const(domains, 0)


@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", "b", lambda i: i == 1),
        ("!=", "b", lambda i: i != 1),
        ("==", "zz", lambda i: False),
        ("!=", "zz", lambda i: False),
        # Ordering on an enum literal compares indices.
        ("<", "b", lambda i: i < 1),
        (">=", "c", lambda i: i >= 2),
    ],
)
def test_encode_condition_enum_literal(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    domains = {"e": ENUM}
    assert _truth_table(domains, Condition("e", op, value)) == _expected(domains, predicate)


def test_encode_condition_emits_named_literal_and_reuses_model() -> None:
    model = cp_model.CpModel()
    var = model.NewIntVar(0, 4, "n_val")
    lit = _encode_condition(model, {"n": var}, {"n": INT}, Condition("n", ">=", 2), "lit_7_0")
    assert lit.Name() == "lit_7_0"
    # Two reified half-constraints for an ordered comparison.
    assert len(model.Proto().constraints) == 2


# --------------------------------------------------------------------------- #
# _candidate_values
# --------------------------------------------------------------------------- #

def _expr(*clauses: Sequence[Condition]) -> Expression:
    return Expression(
        path=["constraints", "structural", 0],
        text="",
        dnf=None,  # type: ignore[arg-type]
        expanded_clauses=[list(c) for c in clauses],
        clause_strings=[],
    )


def test_candidate_values_bool_and_enum_ignore_conditions() -> None:
    domains = {
        "b": Domain(path="b", kind="bool"),
        "e": Domain(path="e", kind="enum", values=["z", "a", "m"]),
    }
    exprs = [_expr([Condition("b", "==", False), Condition("e", "==", "q")])]
    result = _candidate_values(domains, exprs)
    assert result == {"b": [True, False], "e": ["z", "a", "m"]}
    assert list(result) == ["b", "e"]


def test_candidate_values_empty_enum() -> None:
    assert _candidate_values({"e": Domain(path="e", kind="enum", values=None)}, []) == {"e": []}


def test_candidate_values_small_int_range_is_enumerated() -> None:
    domains = {"n": Domain(path="n", kind="int", minimum=2, maximum=12)}
    exprs = [_expr([Condition("n", ">=", 100)])]
    assert _candidate_values(domains, exprs) == {"n": list(range(2, 13))}


def test_candidate_values_large_int_range_uses_bounds_and_neighbours() -> None:
    domains = {"n": Domain(path="n", kind="int", minimum=0, maximum=100)}
    exprs = [
        _expr([Condition("n", ">=", 50)], [Condition("n", "<", 200)]),
        _expr([Condition("n", "==", 2.5), Condition("n", "!=", "x")]),
        _expr([Condition("n", "==", None, rhs_ident="m")]),
    ]
    # 2.5 contributes int(1.5), int(2.5), int(3.5); "x" and the rhs ident are ignored.
    assert _candidate_values(domains, exprs) == {"n": [0, 1, 2, 3, 49, 50, 51, 100]}


def test_candidate_values_int_bool_condition_value() -> None:
    domains = {"n": Domain(path="n", kind="int", minimum=-50, maximum=50)}
    exprs = [_expr([Condition("n", "==", True)])]
    assert _candidate_values(domains, exprs) == {"n": [-50, 0, 1, 2, 50]}


def test_candidate_values_unbounded_int_without_conditions() -> None:
    assert _candidate_values({"n": Domain(path="n", kind="int")}, []) == {"n": [0]}


def test_candidate_values_half_bounded_int() -> None:
    domains = {"n": Domain(path="n", kind="int", minimum=5)}
    exprs = [_expr([Condition("n", "<", 3)])]
    assert _candidate_values(domains, exprs) == {"n": [5]}
    domains = {"n": Domain(path="n", kind="int", maximum=5)}
    assert _candidate_values(domains, exprs) == {"n": [2, 3, 4, 5]}


def test_candidate_values_float_domain() -> None:
    domains = {"t": Domain(path="t", kind="float", minimum=0.0, maximum=1.0, precision=10)}
    exprs = [_expr([Condition("t", ">", 0.3), Condition("t", "<", 0.35)])]
    result = _candidate_values(domains, exprs)
    # Float candidates are exact grid points (Fraction): evaluation never sees binary64 rounding
    # (code-review-2 finding 2). Same points as before: 0.0, 0.3, 1.0.
    assert result == {"t": [Fraction(0), Fraction(3, 10), Fraction(1)]}
    assert all(isinstance(v, Fraction) for v in result["t"])


def test_candidate_values_unbounded_float_without_conditions() -> None:
    assert _candidate_values({"t": Domain(path="t", kind="float")}, []) == {"t": [0.0]}


def test_candidate_values_float_int_condition_values_become_exact_grid_points() -> None:
    domains = {"t": Domain(path="t", kind="float", minimum=0, maximum=10, precision=1)}
    exprs = [_expr([Condition("t", "==", 4)])]
    result = _candidate_values(domains, exprs)
    assert result == {"t": [Fraction(v) for v in (0, 3, 4, 5, 10)]}
    assert all(isinstance(v, Fraction) for v in result["t"])


def test_candidate_values_unknown_kind_uses_condition_values_or_none() -> None:
    domains = {
        "s": Domain(path="s", kind="string"),
        "u": Domain(path="u", kind="string"),
    }
    exprs = [_expr([Condition("s", "==", "hello")])]
    assert _candidate_values(domains, exprs) == {"s": ["hello"], "u": [None]}


def test_candidate_values_condition_on_undeclared_ident_raises_keyerror() -> None:
    domains = {"n": Domain(path="n", kind="int", minimum=0, maximum=3)}
    exprs = [_expr([Condition("ghost", "==", 1)])]
    with pytest.raises(KeyError, match="ghost"):
        _candidate_values(domains, exprs)


def test_candidate_values_key_order_follows_domains() -> None:
    domains = {
        "z": Domain(path="z", kind="bool"),
        "a": Domain(path="a", kind="int", minimum=0, maximum=1),
    }
    assert list(_candidate_values(domains, [])) == ["z", "a"]


def test_candidate_values_non_numeric_minimum_fallback() -> None:
    # A string minimum is not a numeric candidate, so the empty-candidates
    # fallback (minimum, then zero) runs and is filtered by the bounds.
    int_dom = Domain(path="n", kind="int", minimum="5")
    flt_dom = Domain(path="t", kind="float", minimum="0.5")
    assert _candidate_values({"n": int_dom, "t": flt_dom}, []) == {"n": [5], "t": [0.5]}
