"""Characterization tests for ``tvl.constraints._atom_literal``.

They pin the current behaviour of the config-validate SAT encoder for a single
atom: the truth table of the returned literal over every value of the
variable, the exceptions (type and message) raised for unsupported atoms, and
the literal names. A behaviour-preserving refactor must keep all of them.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

import pytest

cp_model = pytest.importorskip("ortools.sat.python.cp_model")

from tvl.constraints import Atom, _atom_literal, _create_variable  # noqa: E402
from tvl.model import Domain  # noqa: E402


def _enc_values(domain: Domain) -> range:
    if domain.kind == "bool":
        return range(0, 2)
    if domain.kind == "enum":
        values = domain.values or []
        return range(0, len(values) if values else 2)
    if domain.kind == "int":
        return range(int(domain.minimum), int(domain.maximum) + 1)
    return range(
        domain._encode_bound_lower(domain.minimum),
        domain._encode_bound_upper(domain.maximum) + 1,
    )


def _truth_table(domain: Domain, atom: Atom) -> Dict[int, Tuple[int, ...]]:
    table: Dict[int, Tuple[int, ...]] = {}
    for value in _enc_values(domain):
        allowed: List[int] = []
        for forced in (0, 1):
            model = cp_model.CpModel()
            var = _create_variable(model, domain)
            lit = _atom_literal(model, {domain.path: var}, {domain.path: domain}, atom)
            model.Add(var == value)
            model.AddBoolAnd([lit if forced else lit.Not()])
            status = cp_model.CpSolver().Solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                allowed.append(forced)
        table[value] = tuple(allowed)
    return table


def _expected(domain: Domain, predicate: Callable[[int], bool]) -> Dict[int, Tuple[int, ...]]:
    return {v: ((1,) if predicate(v) else (0,)) for v in _enc_values(domain)}


def _call(domain: Domain, atom: Atom) -> Any:
    model = cp_model.CpModel()
    var = _create_variable(model, domain)
    return _atom_literal(model, {domain.path: var}, {domain.path: domain}, atom)


BOOL = Domain(path="flag", kind="bool")
SYM = Domain(path="mode", kind="enum", values=["a", "b", "c"])
NUM = Domain(path="k", kind="enum", values=[3, 1, 2])  # deliberately unsorted
INT = Domain(path="n", kind="int", minimum=0, maximum=4)
FLT = Domain(path="t", kind="float", minimum=0.0, maximum=1.0, precision=10)


# --- lookup failures ---------------------------------------------------------- #

def test_unknown_path_raises() -> None:
    model = cp_model.CpModel()
    with pytest.raises(ValueError, match=r"^Unknown TVAR in constraint: ghost$"):
        _atom_literal(model, {}, {}, Atom("ghost", "==", 1))


def test_declared_domain_without_variable_raises_keyerror() -> None:
    model = cp_model.CpModel()
    with pytest.raises(KeyError, match="n"):
        _atom_literal(model, {}, {"n": INT}, Atom("n", "==", 1))


# --- bool --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", True, lambda v: v == 1),
        ("==", False, lambda v: v == 0),
        ("!=", True, lambda v: v == 0),
        ("!=", False, lambda v: v == 1),
        ("==", 1, lambda v: v == 1),
        ("==", 0, lambda v: v == 0),
        ("==", "yes", lambda v: v == 1),  # truthiness, not parsing
        ("==", "", lambda v: v == 0),
    ],
)
def test_bool_truth_table(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    assert _truth_table(BOOL, Atom("flag", op, value)) == _expected(BOOL, predicate)


def test_bool_returns_the_variable_or_its_negation_without_new_vars() -> None:
    model = cp_model.CpModel()
    var = _create_variable(model, BOOL)
    same = _atom_literal(model, {"flag": var}, {"flag": BOOL}, Atom("flag", "==", True))
    neg = _atom_literal(model, {"flag": var}, {"flag": BOOL}, Atom("flag", "!=", True))
    assert same is var
    assert neg.Index() == var.Not().Index()
    assert len(model.Proto().variables) == 1
    assert len(model.Proto().constraints) == 0


@pytest.mark.parametrize("op", ["<", "<=", ">", ">=", "~"])
def test_bool_ordering_raises(op: str) -> None:
    with pytest.raises(ValueError, match=rf"^Unsupported bool operator {op}$"):
        _call(BOOL, Atom("flag", op, True))


# --- symbolic enum ------------------------------------------------------------ #

@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", "b", lambda i: i == 1),
        ("!=", "b", lambda i: i != 1),
        ("==", "zz", lambda i: False),
        ("!=", "zz", lambda i: True),
    ],
)
def test_symbolic_enum_truth_table(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    assert _truth_table(SYM, Atom("mode", op, value)) == _expected(SYM, predicate)


@pytest.mark.parametrize("op", ["<", "<=", ">", ">=", "~"])
def test_symbolic_enum_ordering_raises(op: str) -> None:
    msg = (
        f"Unsupported ordering operator {op!r} on symbolic enum 'mode' "
        "(enum values are not ordered)"
    )
    with pytest.raises(ValueError) as exc:
        _call(SYM, Atom("mode", op, "b"))
    assert str(exc.value) == msg


def test_mixed_enum_is_symbolic() -> None:
    mixed = Domain(path="m", kind="enum", values=[1, "a"])
    with pytest.raises(ValueError, match="on symbolic enum 'm'"):
        _call(mixed, Atom("m", "<", 1))


@pytest.mark.parametrize(
    "op,predicate",
    [("==", lambda i: False), ("!=", lambda i: True)],
)
def test_empty_enum(op: str, predicate: Callable[[int], bool]) -> None:
    empty = Domain(path="e", kind="enum", values=[])
    assert _truth_table(empty, Atom("e", op, "a")) == _expected(empty, predicate)
    with pytest.raises(ValueError, match="on symbolic enum 'e'"):
        _call(empty, Atom("e", "<", 1))


def test_enum_with_none_values() -> None:
    none_enum = Domain(path="e", kind="enum", values=None)
    assert _truth_table(none_enum, Atom("e", "==", "a")) == _expected(none_enum, lambda i: False)


# --- numeric enum ------------------------------------------------------------- #

_ORDER = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


@pytest.mark.parametrize("op", sorted(_ORDER))
@pytest.mark.parametrize("threshold", [0, 1, 2, 2.5, 3, 4, "2"])
def test_numeric_enum_ordering_compares_values_not_indices(op: str, threshold: Any) -> None:
    values = NUM.values
    t = float(threshold)
    assert _truth_table(NUM, Atom("k", op, threshold)) == _expected(
        NUM, lambda i: _ORDER[op](values[i], t)
    )


@pytest.mark.parametrize(
    "op,value,predicate",
    [
        ("==", 2, lambda i: i == 2),
        ("!=", 2, lambda i: i != 2),
        ("==", 2.0, lambda i: i == 2),
        ("==", 5, lambda i: False),
        ("!=", 5, lambda i: True),
    ],
)
def test_numeric_enum_equality(op: str, value: Any, predicate: Callable[[int], bool]) -> None:
    assert _truth_table(NUM, Atom("k", op, value)) == _expected(NUM, predicate)


def test_numeric_enum_unknown_operator_raises_symbolic_message() -> None:
    with pytest.raises(ValueError) as exc:
        _call(NUM, Atom("k", "~", 2))
    assert str(exc.value) == (
        "Unsupported ordering operator '~' on symbolic enum 'k' (enum values are not ordered)"
    )


def test_numeric_enum_non_numeric_threshold_raises() -> None:
    with pytest.raises(ValueError, match="could not convert string to float"):
        _call(NUM, Atom("k", "<", "abc"))


def test_numeric_enum_all_and_none_shortcuts_add_single_constraint() -> None:
    model = cp_model.CpModel()
    var = _create_variable(model, NUM)
    _atom_literal(model, {"k": var}, {"k": NUM}, Atom("k", "<=", 100))
    _atom_literal(model, {"k": var}, {"k": NUM}, Atom("k", "<", 0))
    assert len(model.Proto().constraints) == 2


# --- int / float -------------------------------------------------------------- #

_ALL = dict(_ORDER, **{"==": lambda a, b: a == b, "!=": lambda a, b: a != b})


@pytest.mark.parametrize("op", sorted(_ALL))
@pytest.mark.parametrize("value", [0, 2, 4])
def test_int_truth_table(op: str, value: int) -> None:
    assert _truth_table(INT, Atom("n", op, value)) == _expected(
        INT, lambda v: _ALL[op](v, value)
    )


@pytest.mark.parametrize("op", sorted(_ALL))
def test_float_truth_table(op: str) -> None:
    assert _truth_table(FLT, Atom("t", op, 0.3)) == _expected(
        FLT, lambda e: _ALL[op](e, 3)
    )


def test_int_unknown_operator_raises_after_encoding() -> None:
    model = cp_model.CpModel()
    var = _create_variable(model, INT)
    with pytest.raises(ValueError, match=r"^Unsupported operator ~$"):
        _atom_literal(model, {"n": var}, {"n": INT}, Atom("n", "~", 2))
    # The literal is created before the operator is rejected.
    assert [v.name for v in model.Proto().variables] == ["n", "lit_n_~_2"]


def test_int_unencodable_value_raises_encode_error() -> None:
    with pytest.raises(ValueError, match=r"^n: expected int, got 'x'$"):
        _call(INT, Atom("n", "<", "x"))


def test_float_off_grid_threshold_is_encoded_not_rejected() -> None:
    # Definition 3.6: a threshold need not be a grid member; the encoder compares through
    # the exact grid index (commit f4f0821) instead of raising "not on the precision grid".
    assert _call(FLT, Atom("t", "<", 0.35)) is not None


def test_unsupported_domain_kind_raises_encode_error() -> None:
    weird = Domain(path="w", kind="string")
    model = cp_model.CpModel()
    var = model.NewIntVar(0, 1, "w")
    with pytest.raises(ValueError, match=r"^w: unsupported domain kind string$"):
        _atom_literal(model, {"w": var}, {"w": weird}, Atom("w", "==", "x"))


# --- literal names ------------------------------------------------------------ #

@pytest.mark.parametrize(
    "domain,atom,name",
    [
        (Domain(path="a.b", kind="enum", values=["x", "y"]), Atom("a.b", "==", "y"), "lit_a_b_==_y"),
        (Domain(path="a.b", kind="enum", values=[1, 2]), Atom("a.b", ">=", 2), "lit_a_b_>=_2"),
        (Domain(path="x.y", kind="int", minimum=0, maximum=3), Atom("x.y", "!=", 1), "lit_x_y_!=_1"),
    ],
)
def test_literal_names(domain: Domain, atom: Atom, name: str) -> None:
    assert _call(domain, atom).Name() == name
