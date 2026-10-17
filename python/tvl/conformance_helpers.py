"""Apply declared projection mutations to language conformance fixtures."""

from __future__ import annotations

from typing import Any


def _set_json_pointer(doc: Any, pointer: str, value: Any) -> None:
    """Mutate doc at RFC 6901 JSON pointer (used to test schema rejection of injected fields)."""
    if not pointer or pointer == "/" or not pointer.startswith("/"):
        if isinstance(doc, dict):
            doc[str(pointer)] = value
        return
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    curr = doc
    for part in parts[:-1]:
        if isinstance(curr, list):
            curr = curr[int(part)]
        elif isinstance(curr, dict):
            curr = curr.setdefault(part, {})
        else:
            return
    last = parts[-1]
    if isinstance(curr, list):
        curr[int(last)] = value
    elif isinstance(curr, dict):
        curr[last] = value


def inject_projection_fields(hosted_decls, fields):
    """Inject a fixture mutation outside the production projection API."""
    for pointer, value in (fields or {}).items():
        if isinstance(pointer, str):
            _set_json_pointer(hosted_decls, pointer.removeprefix("/declarations"), value)
