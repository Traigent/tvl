import argparse
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from tvl.lints import lint_module, lint_pack
from tvl.loader import is_pack_document

from tvl_tools.cli_utils import (
    add_common_args,
    format_issue_line,
    get_format,
    handle_error,
    load_yaml_safely,
    print_output,
)


def _load_schema(tool_file: Path, schema_name: str = "tvl.schema.json") -> dict[str, Any]:
    """Load the authored schema from the public package or editable checkout."""
    from tvl.schema import load_schema

    return load_schema(schema_name)


def _schema_issues(doc: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return schema validation issues for the given document."""
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    from tvl.diagnostics import closed_schema_issues, runtime_syntax_issues
    from tvl.lints import _uses_13_constructs

    if _uses_13_constructs(doc) or is_pack_document(doc):
        return runtime_syntax_issues(doc) or closed_schema_issues(errors)
    issues: list[dict[str, Any]] = []
    for err in errors:
        code, message = "schema_error", err.message
        field_path = list(err.path)
        if err.validator == "required" and isinstance(err.instance, dict):
            # Point at the key to add, as docs/reference/error-codes.md promises,
            # instead of at the object that is missing it. Only when the error
            # names a single key, so the path stays unambiguous.
            missing = [p for p in (err.validator_value or []) if p not in err.instance]
            if len(missing) == 1:
                field_path = [*field_path, missing[0]]
        tvars = doc.get("tvars")
        if (
            err.validator == "type"
            and len(field_path) in {4, 5}
            and field_path[0] == "tvars"
            and isinstance(field_path[1], int)
            and field_path[2] == "domain"
            and isinstance(field_path[-1], int)
            and (len(field_path) == 4 or field_path[3] == "set")
            and isinstance(tvars, list)
            and 0 <= field_path[1] < len(tvars)
        ):
            tvar = tvars[field_path[1]]
            if isinstance(tvar, dict) and tvar.get("type") in ("enum[int]", "enum[float]", "enum[str]"):
                code = "invalid_enum_domain"
                message = f"TVAR {tvar.get('name', '<unnamed>')}: {message}"
        issues.append(
            {
                "code": code,
                "message": message,
                "path": field_path,
                "severity": "error",
            }
        )
    return issues


def _lint_errors_by_path(doc: dict[str, Any], is_pack: bool) -> dict[tuple[Any, ...], dict[str, Any]]:
    """Index this document's error-severity lints by the path they point at.

    A schema-invalid document can break a lint's shape assumptions, so a failure
    here returns nothing and leaves the schema diagnostics exactly as they were.
    """
    try:
        lint_issues = lint_pack(doc) if is_pack else lint_module(doc)
    except Exception:  # noqa: BLE001
        return {}
    index: dict[tuple[Any, ...], dict[str, Any]] = {}
    for issue in lint_issues:
        if issue.get("severity", "error") != "error":
            continue
        path = tuple(issue.get("path") or ())
        if path:
            index.setdefault(path, issue)
    return index


def _restore_lint_codes(
    issues: list[dict[str, Any]], doc: dict[str, Any], is_pack: bool
) -> list[dict[str, Any]]:
    """Report the normative lint code where the schema now encodes a lint rule.

    Issues #156 and #157 moved shared bounds (chance threshold and confidence,
    band tolerance and alpha, convergence threshold and window, the required
    exploration strategy, enum element types) into the grammar. The schema runs
    first, so without this ``tvl-validate`` would answer ``schema_error`` for
    diagnostics that ``docs/reference/error-codes.md`` documents by their lint
    code and that ``tvl-lint`` and ``tvl-ci-gate`` still report by that code.

    Matching is on the diagnostic's own path rather than a hand-maintained table
    of schema paths, so any future shared bound is covered with no second list to
    update: first the longest lint path that prefixes the schema error's path,
    then -- for a ``oneOf`` failure, which reports only the branch point -- the
    single lint error inside that subtree. Several candidates in one subtree are
    ambiguous, so the generic ``schema_error`` is kept rather than guessed at.
    """
    if not any(issue.get("code") == "schema_error" for issue in issues):
        return issues
    index = _lint_errors_by_path(doc, is_pack)
    if not index:
        return issues
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        replacement: dict[str, Any] | None = None
        if issue.get("code") == "schema_error":
            path = tuple(issue.get("path") or ())
            for length in range(len(path), 0, -1):
                replacement = index.get(path[:length])
                if replacement is not None:
                    break
            if replacement is None and path:
                inside = [v for k, v in index.items() if k[: len(path)] == path]
                if len(inside) == 1:
                    replacement = inside[0]
        chosen = issue if replacement is None else dict(replacement)
        identity = (chosen.get("code"), tuple(chosen.get("path") or ()))
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(chosen)
    return merged


def text_renderer(data: dict[str, Any]) -> None:
    issues = data.get("issues", [])
    if issues:
        for issue in issues:
            print(format_issue_line(issue))
    else:
        print("Schema + lint checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a TVL module against the JSON Schema and normative lints",
    )
    parser.add_argument("file", type=Path, help="Path to TVL module YAML")
    add_common_args(parser)
    args = parser.parse_args()

    try:
        doc = load_yaml_safely(args.file)
        if not isinstance(doc, dict):
            raise TypeError("TVL module must be a mapping at the top level")

        is_pack = is_pack_document(doc)
        schema = _load_schema(
            Path(__file__),
            "tvl-pack.schema.json" if is_pack else "tvl.schema.json",
        )
        issues = _schema_issues(doc, schema)
        schema_ok = not issues

        if not issues:
            issues = lint_pack(doc) if is_pack else lint_module(doc)
        else:
            issues = _restore_lint_codes(issues, doc, is_pack)

        has_errors = any(issue.get("severity", "error") == "error" for issue in issues)
        result: dict[str, Any] = {
            "ok": not has_errors,
            "file": str(args.file),
            "schema_ok": schema_ok,
            "issues": issues,
        }
        if is_pack:
            result["document_kind"] = "pack"

        print_output(result, get_format(args), text_renderer)

        if has_errors:
            sys.exit(2)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
