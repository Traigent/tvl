from __future__ import annotations

from pathlib import Path
from typing import Any

from tvl.errors import ParseError, SchemaError
from .schema import validator
from .yaml_safe import safe_load


def is_pack_document(doc: Any) -> bool:
    """True when ``doc`` is a TVL 1.3 pack mapping (has ``pack`` and not ``tvl``, RFC 0003 §11.2)."""
    return isinstance(doc, dict) and "pack" in doc and "tvl" not in doc


def load(path: Path | str) -> dict[str, Any]:
    """Load and schema-validate a TVL YAML file into a Python dict.

    Raises:
        ParseError: If YAML parsing fails.
        SchemaError: If schema validation fails or a tvl_pack is passed to a module loader.
    """
    p = Path(path)
    try:
        data = safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ParseError(str(e))

    if is_pack_document(data):
        err = SchemaError("unsupported_construct: tvl_pack")
        err.code = "unsupported_construct"  # type: ignore[attr-defined]
        err.construct = "tvl_pack"  # type: ignore[attr-defined]
        raise err

    v = validator()
    errs = list(v.iter_errors(data))
    if errs:
        first = errs[0]
        raise SchemaError(first.message)

    # TODO: type-checking, normalization, atomic TVAR read invariants
    return data

