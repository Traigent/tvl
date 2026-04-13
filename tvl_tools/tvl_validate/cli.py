import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator

from tvl.lints import lint_module
from tvl_tools.cli_utils import add_common_args, get_format, handle_error, load_yaml_safely, print_output


def _load_schema(tool_file: Path) -> Dict[str, Any]:
    """Load the TVL JSON Schema relative to this CLI module."""
    project_root = tool_file.resolve().parents[2]
    schema_path = project_root / "spec/grammar/tvl.schema.json"
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _schema_issues(doc: Dict[str, Any], schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return schema validation issues for the given document."""
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    issues: List[Dict[str, Any]] = []
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


def text_renderer(data: Dict[str, Any]) -> None:
    issues = data.get("issues", [])
    if issues:
        for issue in issues:
            path = ".".join(str(p) for p in issue.get("path", [])) or "<root>"
            print(f"[{issue.get('code')}] {path}: {issue.get('message')}")
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

        schema = _load_schema(Path(__file__))
        issues = _schema_issues(doc, schema)

        if not issues:
            issues = lint_module(doc)

        result = {
            "ok": len(issues) == 0,
            "file": str(args.file),
            "schema_ok": all(issue.get("code") != "schema_error" for issue in issues),
            "issues": issues,
        }

        print_output(result, get_format(args), text_renderer)

        if issues:
            sys.exit(2)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
