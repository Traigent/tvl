from __future__ import annotations

from jsonschema import Draft202012Validator
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


def runtime_contract_validator() -> Draft202012Validator:
    return validator("tvl-runtime-contract.schema.json")


def runtime_local_validator() -> Draft202012Validator:
    return validator("tvl-runtime-local.schema.json")


def runtime_report_validator() -> Draft202012Validator:
    return validator("tvl-runtime-report.schema.json")
