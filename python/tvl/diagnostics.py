"""Closed, field-addressed diagnostics for TVL 1.3 authoring tools."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence


@lru_cache(maxsize=1)
def _schema_fields() -> frozenset[str]:
    from .schema import load_schema

    fields: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            fields.update(node.get("properties", {}))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(load_schema())
    visit(load_schema("tvl-pack.schema.json"))
    return frozenset(fields)


def field_path(path: Sequence[Any]) -> str:
    return ".".join(str(part) for part in path) or "<root>"


def closed_issue(code: str, path: Sequence[Any], message: str) -> dict[str, Any]:
    return {"code": code, "path": list(path), "message": f"{field_path(path)}: {message}", "severity": "error"}


def closed_lint_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Keep runtime explanations; older lint messages may contain customer values."""
    path = [part if type(part) is int or part in _schema_fields() else "<entry>" for part in issue.get("path", [])]
    if path and path[0] in {"requirements", "monitors", "responses", "tvl_version", "pack"}:
        return dict(issue)
    return closed_issue(issue["code"], path, issue["code"])


def runtime_syntax_issues(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Catch YAML boolean spellings without running the schema in tvl-lint."""
    issues: list[dict[str, Any]] = []

    def check_on(obj: Any, path: list[Any], expected: str) -> None:
        if isinstance(obj, Mapping) and (True in obj or "on" in obj):
            issues.append(closed_issue("schema_error", path + [expected], "unquoted on: is a YAML boolean key; use `trigger:` / `when:`"))

    responses = doc.get("responses")
    for idx, resp in enumerate(responses if isinstance(responses, list) else []):
        if not isinstance(resp, Mapping) or not isinstance(resp.get("rules"), list):
            continue
        for ridx, rule in enumerate(resp["rules"]):
            check_on(rule, ["responses", idx, "rules", ridx], "trigger")
    requirements = doc.get("requirements")
    for idx, req in enumerate(requirements if isinstance(requirements, list) else []):
        if not isinstance(req, Mapping):
            continue
        for key in ("among", "violation"):
            pred = req.get(key)
            if not isinstance(pred, Mapping) or pred.get("pattern") != "protocol":
                continue
            path = ["requirements", idx, key]
            state_fields: list[tuple[list[Any], Any]] = [(path + ["start"], pred.get("start"))]
            for array in ("states", "accepting", "rejecting"):
                if isinstance(pred.get(array), list):
                    state_fields.extend((path + [array, j], value) for j, value in enumerate(pred[array]))
            if isinstance(pred.get("transitions"), list):
                for j, tr in enumerate(pred["transitions"]):
                    tpath = path + ["transitions", j]
                    check_on(tr, tpath, "when")
                    if isinstance(tr, Mapping):
                        state_fields.extend((tpath + [key], tr.get(key)) for key in ("from", "to"))
            for spath, value in state_fields:
                if isinstance(value, bool):
                    issues.append(closed_issue("schema_error", spath, 'expected a string identifier; quote YAML yes/no as "yes" / "no"'))
    return issues


def closed_schema_issues(errors: Iterable[Any]) -> list[dict[str, Any]]:
    """Describe schema constraints, never the rejected value or unknown keys."""
    issues: list[dict[str, Any]] = []
    for err in errors:
        path = [part if type(part) is int or part in _schema_fields() else "<entry>" for part in err.absolute_path]
        if err.validator == "required":
            for key in err.validator_value:
                if key not in err.instance:
                    issue = closed_issue("schema_error", path + [key], "required field is missing")
                    if issue not in issues:
                        issues.append(issue)
            continue
        if err.validator == "type":
            message = f"expected type: {err.validator_value}"
        elif err.validator == "additionalProperties":
            message = "only schema-defined fields are allowed"
        elif err.validator == "pattern":
            message = f"expected pattern: {err.validator_value}"
        else:
            message = "field does not satisfy its schema constraint"
        issues.append(closed_issue("schema_error", path, message))
    return issues
