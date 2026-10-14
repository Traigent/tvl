"""Compare conversion behavior with the immutable pre-refactor method."""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Callable
from pathlib import Path
from types import CodeType, FunctionType
from typing import Any

import pytest
from tvl.model import Domain

REFERENCE_SHA256 = "b1106fdcacfb105ea955e5a23196220c664ebca8b9ac6af8f8b2cb076802a292"


@pytest.fixture(scope="module")
def reference_encode() -> Callable[[Domain, Any], int]:
    path = Path(__file__).parent / "data/domain_encode_before.py.txt"
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != REFERENCE_SHA256:
        raise RuntimeError("historical encoding reference integrity mismatch")
    namespace: dict[str, Any] = {"Any": Any, "__name__": "_domain_encode_reference"}
    compiled = compile(source, str(path), "exec")
    functions = [item for item in compiled.co_consts if isinstance(item, CodeType)]
    if len(functions) != 1 or functions[0].co_name != "encode":
        raise RuntimeError("historical encoding reference structure mismatch")
    return FunctionType(functions[0], namespace)


class IntegerValue(int):
    pass


def _values() -> list[Any]:
    return [
        False,
        True,
        -2,
        -1,
        0,
        1,
        2,
        IntegerValue(1),
        0.0,
        -0.0,
        1.0,
        0.125,
        0.5,
        1 + 1e-10,
        1 + 2e-9,
        float("nan"),
        float("inf"),
        float("-inf"),
        "a",
        "1",
        None,
        [],
        [1],
        {},
        {"x": 2},
    ]


def _outcome(
    encode: Callable[[Domain, Any], int], domain: Domain, value: Any
) -> tuple[Any, ...]:
    try:
        result = encode(domain, value)
    except (ValueError, TypeError, OverflowError) as error:
        return "raise", type(error), str(error)
    return "return", type(result), repr(result), result is value


def test_encode_matches_reference_across_domain_inputs(
    reference_encode: Callable[[Domain, Any], int],
) -> None:
    values = _values()
    kinds = ["bool", "int", "float", "enum", "unsupported", "BOOL", "", None, [], {}]
    precisions = [1000, 8, 1, 0, -1, 0.5, "1", None]
    enums = [
        None,
        [],
        ["a", "b", "a"],
        [1.0, 0.0, 0.5],
        [False, 0, True, 1],
        [[1], {"x": 2}],
        [values[15]],
    ]
    for kind, value, precision, enum in itertools.product(
        kinds, values, precisions, enums
    ):
        arguments = {
            "path": "control.path",
            "kind": kind,
            "values": enum,
            "precision": precision,
            "minimum": 0,
            "maximum": 1,
        }
        expected = _outcome(reference_encode, Domain(**arguments), value)
        actual = _outcome(Domain.encode, Domain(**arguments), value)
        assert actual == expected, (arguments, value, expected, actual)


class TracedDomain(Domain):
    def __getattribute__(self, name: str) -> Any:
        if name in {"kind", "path", "values", "precision"}:
            object.__getattribute__(self, "_trace").append(name)
        if name == "kind":
            sequence = object.__getattribute__(self, "_kinds")
            if sequence:
                return sequence.pop(0)
        return object.__getattribute__(self, name)


def test_encode_preserves_attribute_read_order_and_changing_kind_values(
    reference_encode: Callable[[Domain, Any], int],
) -> None:
    sequences = [
        ["bool"],
        ["enum"],
        ["int"],
        ["float"],
        ["float", "enum"],
        ["float", "int", "int"],
        ["float", "float", "float", "float"],
        ["bad", "bad", "bad", "bad"],
    ]
    for sequence, value in itertools.product(sequences, _values()):
        pair = []
        for encode in (reference_encode, Domain.encode):
            domain = TracedDomain(
                path="control.path", kind="float", values=["a", 1], precision=8
            )
            object.__setattr__(domain, "_trace", [])
            object.__setattr__(domain, "_kinds", list(sequence))
            outcome = _outcome(encode, domain, value)
            pair.append((outcome, object.__getattribute__(domain, "_trace")))
        assert pair[0] == pair[1], (sequence, value, pair)


class _ObservedInteger(int):
    events: list[tuple[Any, ...]]

    def __eq__(self, other: object) -> Any:
        self.events.append(("eq", repr(other)))
        return int.__eq__(self, other)

    def __int__(self) -> int:
        self.events.append(("int",))
        return int.__int__(self)

    def __float__(self) -> float:
        self.events.append(("float",))
        return float(int.__int__(self))


class _ObservedValues(list[Any]):
    def __init__(self, values: list[Any], events: list[tuple[Any, ...]]) -> None:
        super().__init__(values)
        self.events = events

    def __contains__(self, value: object) -> bool:
        self.events.append(("contains", repr(value)))
        return list.__contains__(self, value)

    def index(self, value: Any, *bounds: int) -> int:
        self.events.append(("index", repr(value)))
        return list.index(self, value, *bounds)


def test_encode_preserves_integer_and_enum_container_observations(
    reference_encode: Callable[[Domain, Any], int],
) -> None:
    for kind, raw in itertools.product(["bool", "int", "float"], [-1, 0, 1, 2]):
        pairs = []
        for encode in (reference_encode, Domain.encode):
            events: list[tuple[Any, ...]] = []
            value = _ObservedInteger(raw)
            value.events = events
            outcome = _outcome(encode, Domain(path="control", kind=kind), value)
            pairs.append((outcome, events))
        assert pairs[0] == pairs[1], (kind, raw, pairs)

    observations = []
    for encode in (reference_encode, Domain.encode):
        events = []
        enum = _ObservedValues([{"x": 1}, {"x": 2}], events)
        outcome = _outcome(
            encode, Domain(path="control", kind="enum", values=enum), {"x": 2}
        )
        observations.append((outcome, events))
    assert observations[0] == observations[1]
    assert observations[0][1] == [("contains", "{'x': 2}"), ("index", "{'x': 2}")]
