import argparse
import re
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


# A failure of one of these keywords says only "no branch matched"; it carries
# no diagnosis of its own, so the lints inside its subtree are the real reasons.
# Every other keyword (``additionalProperties``, ``type``, ``required``, a bound)
# does name a specific defect and must never be replaced by a descendant's.
_BRANCH_KEYWORDS = frozenset({"oneOf", "anyOf", "allOf", "not"})

_REQUIRED_KEY_RE = re.compile(r"^'(?P<key>[^']+)' is a required property$")


def _schema_issues(doc: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return schema validation issues for the given document.

    Entries may carry the private ``_keyword`` key; ``_restore_lint_codes`` is
    what turns this into the public shape and strips it. Call it on the result.
    """
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
        if err.validator == "required":
            # Point at the key to add, as docs/reference/error-codes.md
            # promises, instead of at the object that is missing it. The key
            # comes from the message because ``validator_value`` is the whole
            # required list, while jsonschema raises one error per missing key.
            named = _REQUIRED_KEY_RE.match(err.message)
            if named is not None:
                field_path = [*field_path, named.group("key")]
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
                "_keyword": err.validator,
            }
        )
    return issues


def _lint_errors_by_path(
    doc: dict[str, Any], is_pack: bool, floor_provenance: Any = None
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """This document's error-severity lints, paired with the path they point at.

    A schema-invalid document can break a lint's shape assumptions, so a failure
    here returns nothing and leaves the schema diagnostics exactly as they were.
    That is the pre-fix behaviour, not a substituted default: the schema errors
    are still reported in full.
    """
    try:
        if is_pack:
            lint_issues = lint_pack(doc)
        elif floor_provenance is None:
            lint_issues = lint_module(doc)
        else:
            lint_issues = lint_module(doc, floor_provenance=floor_provenance)
    except Exception:  # noqa: BLE001
        return []
    return [
        (tuple(issue.get("path") or ()), issue)
        for issue in lint_issues
        if issue.get("severity", "error") == "error" and issue.get("path")
    ]


def _public(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip the private keys ``_schema_issues`` carries for this module's use."""
    return [{k: v for k, v in issue.items() if not k.startswith("_")} for issue in issues]


def _restore_lint_codes(
    issues: list[dict[str, Any]],
    doc: dict[str, Any],
    is_pack: bool,
    floor_provenance: Any = None,
) -> list[dict[str, Any]]:
    """Report the normative lint code where the schema now encodes a lint rule.

    Issues #156 and #157 moved shared bounds (chance threshold and confidence,
    band tolerance and alpha, convergence threshold and window, the required
    exploration strategy, enum element types) into the grammar. The schema runs
    first, so without this ``tvl-validate`` would answer ``schema_error`` for
    diagnostics that ``docs/reference/error-codes.md`` documents by their lint
    code and that ``tvl-lint`` and ``tvl-ci-gate`` still report by that code.

    Matching is on the diagnostic's own path, not a hand-maintained table of
    schema paths, so a future shared bound is covered with no second list to
    update. Two rules, and nothing else is substituted:

    * the longest lint path that is the schema error's path or an ancestor of it
      -- the lint names the same key, or the container the key sits in;
    * for a branch keyword (``oneOf`` and friends), which reports only the point
      where no branch matched and diagnoses nothing itself, every lint strictly
      inside that subtree.

    Two invariants keep this lossless. A schema error with no match is reported
    unchanged, so nothing is dropped; and each lint is consumed once, so two
    schema errors can never collapse into one diagnostic.
    """
    if not any(issue.get("code") == "schema_error" for issue in issues):
        return _public(issues)
    index = _lint_errors_by_path(doc, is_pack, floor_provenance)
    if not index:
        return _public(issues)

    consumed: set[int] = set()
    merged: list[dict[str, Any]] = []
    for issue in issues:
        if issue.get("code") != "schema_error":
            merged.append(issue)
            continue
        path = tuple(issue.get("path") or ())
        replacements: list[dict[str, Any]] = []
        for length in range(len(path), 0, -1):
            prefix = path[:length]
            match = next(
                (lint for lint_path, lint in index if lint_path == prefix and id(lint) not in consumed),
                None,
            )
            if match is not None:
                replacements = [match]
                break
        if not replacements and path and issue.get("_keyword") in _BRANCH_KEYWORDS:
            replacements = [
                lint
                for lint_path, lint in index
                if len(lint_path) > len(path) and lint_path[: len(path)] == path and id(lint) not in consumed
            ]
        if not replacements:
            merged.append(issue)
            continue
        for replacement in replacements:
            consumed.add(id(replacement))
            merged.append(dict(replacement))
    return _public(merged)


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
