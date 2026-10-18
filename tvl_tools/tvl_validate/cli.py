import argparse
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tvl.lints import lint_module, lint_pack
from tvl.loader import is_pack_document
from tvl_tools.cli_utils import add_common_args, format_issue_line, get_format, handle_error, load_yaml_safely, print_output


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
        issues.append(
            {
                "code": "schema_error",
                "message": err.message,
                "path": list(err.path),
                "severity": "error",
            }
        )
    return issues


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

        if not issues:
            issues = lint_pack(doc) if is_pack else lint_module(doc)

        result: dict[str, Any] = {
            "ok": len(issues) == 0,
            "file": str(args.file),
            "schema_ok": all(issue.get("code") != "schema_error" for issue in issues),
            "issues": issues,
        }
        if is_pack:
            result["document_kind"] = "pack"

        print_output(result, get_format(args), text_renderer)

        if issues:
            sys.exit(2)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
