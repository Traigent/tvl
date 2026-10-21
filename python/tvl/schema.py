from __future__ import annotations

from jsonschema import Draft202012Validator
from tvl.canonical import RuntimeClosedError
from pathlib import Path
import json


def _grammar_root() -> Path:
    here = Path(__file__).resolve()
    bundled = here.parent / "spec/grammar"
    if bundled.is_dir():
        return bundled
    return here.parents[2] / "spec/grammar"


def load_schema(name: str = "tvl.schema.json") -> dict:
    path = _grammar_root() / name
    return json.loads(path.read_text(encoding="utf-8"))


def validator(name: str = "tvl.schema.json") -> Draft202012Validator:
    return Draft202012Validator(load_schema(name))


def configuration_validator() -> Draft202012Validator:
    return validator("tvl-configuration.schema.json")


def measurement_validator() -> Draft202012Validator:
    return validator("tvl-measurement.schema.json")


def pack_validator() -> Draft202012Validator:
    return validator("tvl-pack.schema.json")


def runtime_contract_validator(format_tag: str = "tvl-runtime-contract/1") -> Draft202012Validator:
    """Select a closed schema by its exchange tag; unknown tags fail closed."""
    schemas = {
        "tvl-runtime-contract/1": "tvl-runtime-contract.schema.json",
        "tvl-runtime-contract/2": "tvl-runtime-contract-v2.schema.json",
    }
    if not isinstance(format_tag, str) or format_tag not in schemas:
        raise RuntimeClosedError("runtime_unsafe_egress")
    return validator(schemas[format_tag])


def runtime_local_validator(format_tag: str = "tvl-runtime-local/1") -> Draft202012Validator:
    schemas = {
        "tvl-runtime-local/1": "tvl-runtime-local.schema.json",
        "tvl-runtime-local/2": "tvl-runtime-local-v2.schema.json",
    }
    if not isinstance(format_tag, str) or format_tag not in schemas:
        raise RuntimeClosedError("runtime_invalid_profile")
    return validator(schemas[format_tag])


def runtime_report_validator() -> Draft202012Validator:
    return validator("tvl-runtime-report.schema.json")
