from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import yaml

from .errors import ParseError, SchemaError
from .schema import validator


def load(path: Path | str) -> Dict[str, Any]:
    """Load and schema-validate a TVL YAML file into a Python dict.

    Raises:
        ParseError: If YAML parsing fails.
        SchemaError: If schema validation fails.
    """
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ParseError(str(e))

    v = validator()
    errs = list(v.iter_errors(data))
    if errs:
        first = errs[0]
        raise SchemaError(first.message)

    # TODO: type-checking, normalization, atomic TVAR read invariants
    return data

