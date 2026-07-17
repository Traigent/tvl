"""Hardened YAML loading for TVL.

``yaml.safe_load`` blocks arbitrary-object construction but still fully resolves
YAML anchors/aliases, and PyYAML ships no default limit on alias expansion. A
small "billion-laughs" document therefore expands exponentially and can OOM the
parsing process (CWE-776 / CWE-400). Every TVL loader routes through
:func:`safe_load` here so that a single guard bounds both raw input size and the
number of resolved aliases, turning an OOM into a fast, catchable error.
"""

from __future__ import annotations

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


class _BoundedSafeLoader(yaml.SafeLoader):
    """SafeLoader that also bounds anchor/alias expansion.

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
