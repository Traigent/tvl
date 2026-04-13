from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import yaml

from .constraints import compile_constraints, evaluate_assignment
from .errors import ParseError, SchemaError
from .model import flatten_assignments
from .schema import configuration_validator


def load_configuration(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ParseError(str(e))

    validator = configuration_validator()
    errors = list(validator.iter_errors(data))
    if errors:
        first = errors[0]
        raise SchemaError(first.message)
    return data


def validate_configuration(module: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    compiled = compile_constraints(module)
    assignments = config.get("assignments", {}) or {}
    flat_assignments = flatten_assignments(assignments)

    module_id = (module.get("tvl") or {}).get("module")
    config_module_id = config.get("module_id")
    module_mismatch: List[Dict[str, Any]] = []
    if module_id and config_module_id and module_id != config_module_id:
        module_mismatch.append({
            "code": "module_mismatch",
            "path": "module_id",
            "message": f"Configuration targets {config_module_id} but module is {module_id}",
        })

    unknown = [
        {
            "code": "unknown_assignment",
            "path": path,
            "message": f"Assignment provided for unknown TVAR '{path}'",
        }
        for path in flat_assignments.keys()
        if path not in compiled.domains
    ]

    evaluation = evaluate_assignment(compiled, assignments)
    domain_issues = evaluation["domains"] + unknown + module_mismatch
    constraint_issues = evaluation["constraints"]

    ok = not domain_issues and not constraint_issues
    return {
        "ok": ok,
        "domains": domain_issues,
        "constraints": constraint_issues,
    }
