"""Closed diagnostics, declaration constants and exact canonical serialization."""

from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from tvl.errors import TVLError
from tvl.lints import _to_exact_fraction
from typing import Any, Optional, Sequence


RATIONAL_METHOD = "clopper_pearson_rational_v2"


FLOAT_METHOD = "clopper_pearson_exact_v1"


EXACT_COUNT_METHOD = "exact_count_v1"


TERMINAL_STATUSES = {"completed", "failed", "rejected"}


ALL_STATUSES = {"running", "completed", "failed", "rejected"}


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


SEVERITY_BY_RANK = {0: "info", 1: "warning", 2: "critical"}


APPROVAL_ORDER = {"none": 0, "standing": 1, "human": 2}


APPROVAL_BY_RANK = {0: "none", 1: "standing", 2: "human"}


# RFC 0003 §9.3: higher rank is stricter; an absent optimize deploy is "never".
DEPLOY_ORDER = {"if_promoted": 0, "never": 1}


DEPLOY_BY_RANK = {0: "if_promoted", 1: "never"}


# Lexical types of RFC 0003 §4.2.1 (public; shared with evaluator profiles).
REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


HOSTED_CHECKER_RE = re.compile(r"^customer:[0-9a-f]{64}$")


DECIMAL_STR_RE = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")


class RuntimeClosedError(TVLError):
    """A runtime error with a code and optional closed schema-field diagnostic.

    Callers must pass only schema paths and static explanations, never customer values.
    """

    def __init__(self, code: str, *, construct: Optional[str] = None,
                 path: Sequence[Any] = (), message: Optional[str] = None) -> None:
        super().__init__(code)
        self.code = code
        self.construct = construct
        self.path = list(path)
        self.message = message or code


def to_fraction(value: Any) -> Fraction:
    """Convert an exact decimal number, decimal string, or ratio string to Fraction."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise RuntimeClosedError("runtime_invalid_profile")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        frac = _to_exact_fraction(value)
        if frac is None:
            raise RuntimeClosedError("runtime_invalid_profile")
        return frac
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise RuntimeClosedError("runtime_invalid_profile") from exc
    raise RuntimeClosedError("runtime_invalid_profile")


def minimal_decimal_str(value: Any) -> str:
    """Convert an exact decimal value to a minimal decimal string without trailing zeros or exponent."""
    frac = to_fraction(value)
    if frac < 0:
        sign = "-"
        frac = -frac
    else:
        sign = ""
    num, den = frac.numerator, frac.denominator
    if den == 1:
        return f"{sign}{num}"
    # Factor out 2s and 5s from denominator
    d = den
    twos = 0
    fives = 0
    while d % 2 == 0:
        d //= 2
        twos += 1
    while d % 5 == 0:
        d //= 5
        fives += 1
    if d != 1:
        raise RuntimeClosedError("runtime_invalid_profile")
    scale = max(twos, fives)
    scaled_num = num * (5 ** (scale - fives)) * (2 ** (scale - twos))
    digits = str(scaled_num).rjust(scale + 1, "0")
    int_part = digits[:-scale]
    frac_part = digits[-scale:].rstrip("0")
    if not frac_part:
        return f"{sign}{int_part}"
    return f"{sign}{int_part}.{frac_part}"


def canonical_json_str(value: Any) -> str:
    """Return canonical JSON string with trailing LF (RFC 0003 §11.4)."""
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_str(value).encode("utf-8")


def canonical_json_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_guards(guards: Any) -> list[dict[str, Any]]:
    """RFC 0004 §2.6: guard order and duplicates have no semantic significance."""
    by_key = {canonical_json_str(guard): dict(guard) for guard in guards}
    return [by_key[key] for key in sorted(by_key)]
