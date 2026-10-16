"""Characterise Domain encoding before changing its conversion dispatch.

These assertions retain the existing acceptance and failure behavior, including
Python equality/coercion edge cases. They do not propose stricter validation.
"""

from __future__ import annotations

from typing import Any

import pytest
from tvl.model import Domain


@pytest.mark.parametrize(
    ("kind", "value", "expected", "expected_type"),
    [
        ("bool", False, 0, int),
        ("bool", True, 1, int),
        ("bool", 0, 0, int),
        ("bool", 1, 1, int),
        ("int", -3, -3, int),
        ("int", 0, 0, int),
        ("int", 10**30, 10**30, int),
        ("int", False, False, bool),
        ("int", True, True, bool),
        ("float", 0, 0, int),
        ("float", 1, 1000, int),
        ("float", -0.125, -125, int),
        ("float", -0.0, 0, int),
        ("float", False, 0, int),
        ("float", True, 1000, int),
    ],
)
def test_encode_values_and_return_types(
    kind: str, value: Any, expected: Any, expected_type: type[Any]
) -> None:
    result = Domain(path="control", kind=kind).encode(value)
    assert result == expected
    assert type(result) is expected_type


@pytest.mark.parametrize("value", [-1, 2, 0.0, 1.0, "true", None, [], {}])
def test_bool_rejects_non_boolean_and_non_binary_integer_values(value: Any) -> None:
    domain = Domain(path="controls.enabled", kind="bool")
    with pytest.raises(ValueError) as caught:
        domain.encode(value)
    assert str(caught.value) == f"controls.enabled: expected bool, got {value!r}"


@pytest.mark.parametrize("value", [1.0, "1", None, [], {}])
def test_int_rejects_non_integer_values(value: Any) -> None:
    domain = Domain(path="controls.count", kind="int")
    with pytest.raises(ValueError) as caught:
        domain.encode(value)
    assert str(caught.value) == f"controls.count: expected int, got {value!r}"


@pytest.mark.parametrize("value", ["1.0", None, [], {}])
def test_float_rejects_non_numeric_values(value: Any) -> None:
    domain = Domain(path="controls.rate", kind="float")
    with pytest.raises(ValueError) as caught:
        domain.encode(value)
    assert str(caught.value) == f"controls.rate: expected float, got {value!r}"


@pytest.mark.parametrize(
    ("values", "value", "expected"),
    [
        (["strong", "cheap", "strong"], "strong", 0),
        (["strong", "cheap", "strong"], "cheap", 1),
        ([1.0, 0.0, 0.5], 0.5, 2),
        ([False, 0, True, 1], 0, 0),
        ([False, 0, True, 1], 1, 2),
        ([1, 2], True, 0),
        ([{"name": "a"}, {"name": "b"}], {"name": "b"}, 1),
        ([[1], [2]], [2], 1),
    ],
)
def test_enum_retains_declaration_order_duplicates_and_python_equality(
    values: list[Any], value: Any, expected: int
) -> None:
    domain = Domain(path="controls.model", kind="enum", values=values)
    assert domain.encode(value) == expected
    assert domain.values is values


@pytest.mark.parametrize("values", [[], ["cheap", "strong"]])
def test_enum_missing_value_error_contains_original_value_order(
    values: list[Any],
) -> None:
    domain = Domain(path="controls.model", kind="enum", values=values)
    with pytest.raises(ValueError) as caught:
        domain.encode("other")
    assert str(caught.value) == f"controls.model: value 'other' not in enum {values}"


def test_enum_without_values_has_distinct_error() -> None:
    domain = Domain(path="controls.model", kind="enum")
    with pytest.raises(ValueError) as caught:
        domain.encode("other")
    assert str(caught.value) == "controls.model: enum domain is missing values"


def test_enum_nan_lookup_retains_identity_sensitive_list_membership() -> None:
    value = float("nan")
    domain = Domain(path="controls.model", kind="enum", values=[value])
    assert domain.encode(value) == 0
    other_nan = float("nan")
    with pytest.raises(ValueError) as caught:
        domain.encode(other_nan)
    assert str(caught.value) == "controls.model: value nan not in enum [nan]"


@pytest.mark.parametrize(
    ("value", "precision", "expected"),
    [(0.125, 8, 1), (-0.125, 8, -1), (2, -10, -20), (2, 0, 0), (2, 0.5, 1)],
)
def test_float_keeps_current_non_default_precision_behavior(
    value: float, precision: Any, expected: int
) -> None:
    assert (
        Domain(path="controls.rate", kind="float", precision=precision).encode(value)
        == expected
    )


@pytest.mark.parametrize("value", [1 + 1e-10, 1 - 1e-10])
def test_float_accepts_existing_grid_tolerance(value: float) -> None:
    assert Domain(path="controls.rate", kind="float", precision=1).encode(value) == 1


@pytest.mark.parametrize("value", [0.5, 1 + 2e-9, 1 - 2e-9])
def test_float_off_grid_error_retains_precision_and_resolution(value: float) -> None:
    domain = Domain(path="controls.rate", kind="float", precision=1)
    with pytest.raises(ValueError) as caught:
        domain.encode(value)
    assert str(caught.value) == (
        f"controls.rate: value {value!r} is not on the precision grid "
        "(precision=1, resolution=1.0)"
    )


@pytest.mark.parametrize(
    ("value", "exception", "message"),
    [
        (float("nan"), ValueError, "cannot convert float NaN to integer"),
        (float("inf"), OverflowError, "cannot convert float infinity to integer"),
        (float("-inf"), OverflowError, "cannot convert float infinity to integer"),
    ],
)
def test_float_nonfinite_failures_retain_exception_class_and_message(
    value: float, exception: type[Exception], message: str
) -> None:
    domain = Domain(path="controls.rate", kind="float")
    with pytest.raises(exception) as caught:
        domain.encode(value)
    assert str(caught.value) == message


@pytest.mark.parametrize("kind", ["unsupported", "BOOL", "", None])
def test_unsupported_kind_retains_failure(kind: Any) -> None:
    domain = Domain(path="controls.rate", kind=kind)
    with pytest.raises(ValueError) as caught:
        domain.encode(1)
    assert str(caught.value) == f"controls.rate: unsupported domain kind {kind}"


def test_encode_preserves_integer_subclass_identity() -> None:
    class IntegerValue(int):
        pass

    value = IntegerValue(1)
    assert Domain(path="control", kind="bool").encode(value) is value
    assert Domain(path="control", kind="int").encode(value) is value


def test_encode_does_not_enforce_domain_bounds() -> None:
    domain = Domain(path="control", kind="int", minimum=0, maximum=1)
    assert domain.encode(-1) == -1
    assert domain.contains(-1) is False


def test_contains_consumes_encoding_failures_without_swallowing_overflow() -> None:
    domain = Domain(path="control", kind="float")
    assert domain.contains(float("nan")) is False
    infinity = float("inf")
    with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
        domain.contains(infinity)


def test_existing_subclass_private_names_do_not_participate_in_conversion() -> None:
    class ExtendedDomain(Domain):
        def _encode_bool(self, value: Any) -> int:
            raise AssertionError("unrelated subclass method")

        def _encode_enum(self, value: Any) -> int:
            raise AssertionError("unrelated subclass method")

        def _encode_float(self, value: Any) -> int:
            raise AssertionError("unrelated subclass method")

    assert ExtendedDomain(path="control", kind="bool").encode(True) == 1
    assert ExtendedDomain(path="control", kind="enum", values=["a"]).encode("a") == 0
    assert ExtendedDomain(path="control", kind="float").encode(0.125) == 125
