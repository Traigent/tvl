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

from .model import literal_limit_violation

# Reject raw inputs larger than this before parsing. TVL specs are tiny; a few
# megabytes is a generous ceiling that still stops a pathological input early.
MAX_YAML_BYTES = 5 * 1024 * 1024

# Cap the number of resolved anchor aliases. A legitimate spec uses a handful;
# billion-laughs expansion produces exponentially many alias nodes at compose
# time, so bounding the count defeats the DoS before the expansion materializes.
MAX_YAML_ALIASES = 5000

# Cap the total number of key/value pairs merge keys (``<<``) copy into mappings. PyYAML's
# flattening materialises every inherited pair, so ``n_i: {<<: [*n_{i-1}, *n_{i-1}]}`` doubles
# per level: 30 levels request 2**30 pairs from only 60 aliases. Legitimate specs inherit a
# handful of pairs; the budget is counted BEFORE each copy, so the explosion never allocates.
MAX_YAML_MERGED_PAIRS = 100_000


class YAMLLimitError(yaml.YAMLError):
    """Raised when a YAML document exceeds a safety limit (size or alias budget)."""


class DuplicateKeyError(yaml.constructor.ConstructorError):
    """Raised when a YAML mapping repeats a key (RFC 0001 §3.5(4): MUST reject at parse time).

    Subclasses ``yaml.YAMLError`` via ``ConstructorError`` so existing handlers
    surface it as a normal parse failure. ``code`` is ``duplicate_key``.
    """

    code = "duplicate_key"


class ComplexKeyError(yaml.constructor.ConstructorError):
    """Raised for a mapping key that is itself a mapping or a sequence.

    TVL keys are scalars. A collection key is rejected outright rather than skipped: a tagged
    one such as ``? !!str {=: alpha}`` constructs to the plain string ``"alpha"`` and would
    otherwise silently overwrite (or be overwritten by) an explicit ``alpha`` key without
    tripping the duplicate-key check. ``code`` is ``complex_mapping_key``.
    """

    code = "complex_mapping_key"


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
        self._merged_pairs = 0

    def _charge_merge(self, pairs: list, node: Any) -> None:
        self._merged_pairs += len(pairs)
        if self._merged_pairs > MAX_YAML_MERGED_PAIRS:
            raise YAMLLimitError(
                f"YAML merge-key expansion budget exceeded ({MAX_YAML_MERGED_PAIRS} inherited "
                f"key/value pairs, line {node.start_mark.line + 1}); possible merge-expansion DoS"
            )

    def flatten_mapping(self, node: Any) -> None:
        """PyYAML 6.0 ``SafeConstructor.flatten_mapping`` with every inherited copy charged.

        Same algorithm and errors as upstream (MIT, PyYAML); the only change is that each
        ``merge.extend`` is charged against ``MAX_YAML_MERGED_PAIRS`` before it allocates.
        """
        merge: list = []
        index = 0
        while index < len(node.value):
            key_node, value_node = node.value[index]
            if key_node.tag == "tag:yaml.org,2002:merge":
                del node.value[index]
                if isinstance(value_node, yaml.MappingNode):
                    self.flatten_mapping(value_node)
                    self._charge_merge(value_node.value, node)
                    merge.extend(value_node.value)
                elif isinstance(value_node, yaml.SequenceNode):
                    submerge = []
                    for subnode in value_node.value:
                        if not isinstance(subnode, yaml.MappingNode):
                            raise yaml.constructor.ConstructorError(
                                "while constructing a mapping",
                                node.start_mark,
                                f"expected a mapping for merging, but found {subnode.id}",
                                subnode.start_mark,
                            )
                        self.flatten_mapping(subnode)
                        submerge.append(subnode.value)
                    submerge.reverse()
                    for value in submerge:
                        self._charge_merge(value, node)
                        merge.extend(value)
                else:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"expected a mapping or list of mappings for merging, but found {value_node.id}",
                        value_node.start_mark,
                    )
            elif key_node.tag == "tag:yaml.org,2002:value":
                key_node.tag = "tag:yaml.org,2002:str"
                index += 1
            else:
                index += 1
        if merge:
            self._charge_merge(node.value, node)
            node.value = merge + node.value

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.events.AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise YAMLLimitError(
                    "YAML alias-expansion budget exceeded "
                    f"({MAX_YAML_ALIASES}); possible entity-expansion DoS"
                )
        return super().compose_node(parent, index)

    def construct_document(self, node: Any) -> Any:
        # Validate the whole composed graph BEFORE any construction: PyYAML's merge-key
        # flattening mutates ``MappingNode.value`` in place, so duplicates must be judged on
        # the original pairs, captured here, never on a node a previous merge rewrote.
        self._check_duplicate_keys(node)
        return super().construct_document(node)

    def _check_duplicate_keys(self, root: Any) -> None:
        """Reject a mapping node that repeats one of its own keys (RFC 0001 section 3.5(4)).

        Every mapping node reachable from ``root`` is checked exactly once on its ORIGINAL
        pairs, merge sources included (they are mapping nodes of the same graph). An explicit
        key overriding a key inherited through ``<<`` is not a duplicate: merge entries are
        not keys of the node. The walk is iterative with a visited set keyed by node
        identity, so aliases cycles and shared sub-graphs cost O(nodes + edges) and there is
        no depth limit to exceed (nothing is ever skipped).
        """
        visited: set = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if id(node) in visited:
                continue
            visited.add(id(node))
            if isinstance(node, yaml.SequenceNode):
                stack.extend(node.value)
            elif isinstance(node, yaml.MappingNode):
                pairs = list(node.value)  # original pairs: nothing has been flattened yet
                self._check_pairs(node, pairs)
                for key_node, value_node in pairs:
                    stack.append(key_node)
                    stack.append(value_node)

    def _check_pairs(self, node: Any, pairs: list) -> None:
        seen: set = set()
        for key_node, _value_node in pairs:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            if not isinstance(key_node, yaml.ScalarNode):
                mark = key_node.start_mark
                raise ComplexKeyError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"complex_mapping_key: a mapping key must be a scalar, found a {key_node.id} "
                    f"(line {mark.line + 1}, column {mark.column + 1})",
                    mark,
                )
            if key_node.tag == "tag:yaml.org,2002:value":
                # PyYAML retags the '=' value indicator as a str key while flattening, so it
                # constructs to the string "=" and can collide with an explicit '=' key.
                key: Any = key_node.value
            else:
                try:
                    key = self.construct_object(key_node, deep=True)
                    hash(key)
                except Exception:  # noqa: BLE001 - malformed/unhashable keys are reported by the base class
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

    def construct_yaml_float(self, node: Any) -> Any:
        reason = literal_limit_violation(str(node.value))
        if reason is not None:
            # Fail closed at load: the exact rational of such a literal (kept below for
            # lexemes binary64 cannot hold) would cost 10**exponent to build.
            mark = node.start_mark
            raise YAMLLimitError(f"{reason} (line {mark.line + 1}, column {mark.column + 1})")
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

    try:
        return yaml.load(data, Loader=_BoundedSafeLoader)
    except RecursionError as exc:
        # PyYAML's composer and merge flattening recurse per nesting level; a pathologically
        # deep document is rejected as a YAML error rather than escaping as RecursionError.
        raise YAMLLimitError("YAML nesting too deep to parse safely") from exc
