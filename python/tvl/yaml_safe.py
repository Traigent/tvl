"""Hardened YAML loading for TVL.

``yaml.safe_load`` blocks arbitrary-object construction but still fully resolves
YAML anchors/aliases, and PyYAML ships no default limit on alias expansion. A
small "billion-laughs" document therefore expands exponentially and can OOM the
parsing process (CWE-776 / CWE-400). Every TVL loader routes through
:func:`safe_load` here so that a single guard bounds both raw input size and the
number of resolved aliases, turning an OOM into a fast, catchable error.
"""

from __future__ import annotations

from fractions import Fraction
import math
from typing import Any

import yaml

# Reject raw inputs larger than this before parsing. TVL specs are tiny; a few
# megabytes is a generous ceiling that still stops a pathological input early.
MAX_YAML_BYTES = 5 * 1024 * 1024

# Cap the number of resolved anchor aliases. A legitimate spec uses a handful;
# billion-laughs expansion produces exponentially many alias nodes at compose
# time, so bounding the count defeats the DoS before the expansion materializes.
MAX_YAML_ALIASES = 5000


class YAMLLimitError(yaml.YAMLError):
    """Raised when a YAML document exceeds a safety limit (size or alias budget)."""


class DuplicateKeyError(yaml.constructor.ConstructorError):
    """Raised when a YAML mapping repeats a key (RFC 0001 §3.5(4): MUST reject at parse time).

    Subclasses ``yaml.YAMLError`` via ``ConstructorError`` so existing handlers
    surface it as a normal parse failure. ``code`` is ``duplicate_key``.
    """

    code = "duplicate_key"


class _YAMLFloat(float):
    """Float subclass retaining original YAML decimal lexeme when precision was lost in binary64."""

    __slots__ = ("_raw_lexeme", "_unrecoverable_decimal")
    _raw_lexeme: str
    _unrecoverable_decimal: bool

    def __new__(cls, value: float, raw_lexeme: str, *, unrecoverable: bool = True) -> "_YAMLFloat":
        obj = super().__new__(cls, value)
        obj._raw_lexeme = raw_lexeme
        obj._unrecoverable_decimal = unrecoverable
        return obj

    def __copy__(self) -> "_YAMLFloat":
        return _YAMLFloat(float(self), self._raw_lexeme, unrecoverable=self._unrecoverable_decimal)

    def __deepcopy__(self, memo: Any) -> "_YAMLFloat":
        return _YAMLFloat(float(self), self._raw_lexeme, unrecoverable=self._unrecoverable_decimal)


yaml.SafeDumper.add_representer(_YAMLFloat, yaml.SafeDumper.represent_float)
yaml.Dumper.add_representer(_YAMLFloat, yaml.Dumper.represent_float)


class _BoundedSafeLoader(yaml.SafeLoader):
    """SafeLoader that also bounds anchor/alias expansion and retains unrecoverable decimal lexemes.

    This is the standard PyYAML billion-laughs mitigation: count alias
    resolutions during composition and raise once the budget is exceeded,
    before the exponential expansion can complete.
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._alias_count = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.events.AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise YAMLLimitError(
                    "YAML alias-expansion budget exceeded "
                    f"({MAX_YAML_ALIASES}); possible entity-expansion DoS"
                )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> Any:
        # Check the ORIGINAL pairs, before merge-key flattening: an explicit key
        # legitimately overrides a key inherited through ``<<``, which is not a duplicate.
        if isinstance(node, yaml.MappingNode):
            seen: set = set()
            for key_node, _value_node in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    continue
                try:
                    key = self.construct_object(key_node, deep=True)
                    hash(key)
                except Exception:  # noqa: BLE001 - unhashable keys are reported by the base class
                    continue
                if key in seen:
                    mark = key_node.start_mark
                    raise DuplicateKeyError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"duplicate_key: duplicate mapping key {key!r} "
                        f"(line {mark.line + 1}, column {mark.column + 1})",
                        mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_float(self, node: Any) -> Any:
        val = super().construct_yaml_float(node)
        if isinstance(val, float) and math.isfinite(val):
            raw = str(node.value).replace("_", "").strip()
            try:
                raw_frac = Fraction(raw)
                rep_frac = Fraction(repr(val))
                if raw_frac != rep_frac:
                    return _YAMLFloat(val, raw, unrecoverable=True)
            except (ValueError, ZeroDivisionError):
                return _YAMLFloat(val, raw, unrecoverable=True)
        return val


_BoundedSafeLoader.add_constructor(
    "tag:yaml.org,2002:float",
    _BoundedSafeLoader.construct_yaml_float,
)


def safe_load(source: Any) -> Any:
    """Safely parse YAML from a string, bytes, or readable stream.

    Enforces a raw-size ceiling and an alias-expansion budget, then parses with
    a SafeLoader. Raises :class:`YAMLLimitError` (a ``yaml.YAMLError``) when a
    limit is exceeded, so existing ``except yaml.YAMLError`` / ``except
    Exception`` handlers surface it as a normal parse failure instead of OOM.
    """
    data = source.read() if hasattr(source, "read") else source

    if isinstance(data, (bytes, bytearray)):
        size = len(data)
    else:
        size = len(str(data).encode("utf-8"))

    if size > MAX_YAML_BYTES:
        raise YAMLLimitError(
            f"YAML input too large ({size} bytes > {MAX_YAML_BYTES} byte limit)"
        )

    return yaml.load(data, Loader=_BoundedSafeLoader)
