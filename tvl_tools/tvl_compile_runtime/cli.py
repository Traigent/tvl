"""CLI for tvl-compile-runtime (RFC 0003 §11.5).

Usage:
    tvl-compile-runtime DOCUMENT --token-map TOKENS.json --out-dir DIR
                        [--pack PACK.yml]... [--checkers REGISTRY.json]
                        [--format text|json]
    tvl-compile-runtime DOCUMENT [--pack PACK.yml]... --emit-token-map-template
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import sys
from tempfile import mkdtemp
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tvl.runtime import (
    RuntimeClosedError,
    canonical_json_digest,
    canonical_json_str,
    compile_runtime_document,
)
from tvl_tools.cli_utils import add_common_args, format_issue_line, get_format, load_yaml_safely, print_output
from tvl.diagnostics import closed_lint_issue, closed_schema_issues, runtime_syntax_issues
from tvl.lints import lint_module, lint_pack
from tvl.runtime_projection import token_map_template
from tvl.schema import pack_validator, validator


def text_renderer(data: Dict[str, Any]) -> None:
    if data.get("ok"):
        print(f"Compiled runtime contract: {data.get('contract_digest')}")
    for issue in data.get("issues") or []:
        print(
            format_issue_line(issue),
            file=sys.stdout if data.get("ok") else sys.stderr,
        )


def _load_json_or_yaml(path: Path, default_code: str) -> Any:
    field = "tokens" if default_code == "runtime_unresolved_alias" else "checkers"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeClosedError(default_code, path=[field], message="Cannot read the required local mapping document") from exc
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        try:
            return load_yaml_safely(path)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeClosedError(default_code, path=[field], message="Expected a JSON or YAML mapping document") from exc


def _write_artifact_pair(out_dir: Path, contract: Dict[str, Any], local_prog: Dict[str, Any]) -> None:
    artifacts = (
        ("runtime-contract.json", canonical_json_str(contract)),
        ("runtime-local.json", canonical_json_str(local_prog)),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as cleanup:
        temp_dir = mkdtemp(prefix=".tvl-compile-", dir=out_dir)
        cleanup.callback(shutil.rmtree, temp_dir)
        staging = Path(temp_dir)
        backups = {}
        for name, content in artifacts:
            (staging / name).write_text(content, encoding="utf-8")
        for name, _ in artifacts:
            target = out_dir / name
            if target.exists() or target.is_symlink():
                backup = staging / f"previous-{name}"
                shutil.copy2(target, backup, follow_symlinks=False)
                backups[name] = backup
                if not target.is_symlink():
                    shutil.copymode(target, staging / name)

        published = []
        try:
            for name, _ in artifacts:
                (staging / name).replace(out_dir / name)
                published.append(name)
        except OSError:
            for name in reversed(published):
                target = out_dir / name
                if name in backups:
                    backups[name].replace(target)
                else:
                    target.unlink()
            raise


def run_cli(
    argv: Optional[Sequence[str]] = None,
) -> Tuple[int, Dict[str, Any]]:
    parser = argparse.ArgumentParser(
        description="Compile a TVL module or pack into version-tagged runtime contract and local artifacts"
    )
    parser.add_argument("file", type=Path, help="Path to TVL 1.3, 1.4 or 1.5 module or pack YAML")
    parser.add_argument("--token-map", type=Path, help="Path to tvl-token-map/1 JSON")
    parser.add_argument("--out-dir", type=Path, help="Output directory for compiled artifacts")
    parser.add_argument("--emit-token-map-template", action="store_true",
                        help="Print local-only tvl-token-map/1 JSON with empty hosted placeholders; mints no tokens")
    parser.add_argument("--pack", action="append", type=Path, default=[], help="Optional tvl_pack YAML(s)")
    parser.add_argument("--checkers", type=Path, default=None, help="Optional tvl-checker-registry/1 JSON")
    add_common_args(parser)
    args = parser.parse_args(argv)
    if not args.emit_token_map_template and (args.token_map is None or args.out_dir is None):
        parser.error("--token-map and --out-dir are required for compilation")
    if args.emit_token_map_template and (args.token_map is not None or args.out_dir is not None):
        parser.error("--emit-token-map-template cannot be combined with --token-map or --out-dir")

    try:
        doc = load_yaml_safely(args.file)
        if not isinstance(doc, dict):
            raise RuntimeClosedError("schema_error")

        pack_docs: List[Dict[str, Any]] = []
        for p_path in args.pack or []:
            p_doc = load_yaml_safely(p_path)
            if not isinstance(p_doc, dict):
                raise RuntimeClosedError("schema_error")
            pack_docs.append(p_doc)

        # RFC 0003 §11.5 steps in order: schema validation and lints come before the
        # token map and checker registry are read.
        for document in [doc, *pack_docs]:
            is_pack = "pack" in document and "tvl" not in document
            v = pack_validator() if is_pack else validator()
            issues = runtime_syntax_issues(document) or closed_schema_issues(v.iter_errors(document))
            if not issues:
                issues = lint_pack(document) if is_pack else lint_module(document)
            errors = [issue for issue in issues if issue.get("severity") == "error"]
            if errors:
                issue = closed_lint_issue(errors[0])
                raise RuntimeClosedError(issue["code"], path=issue["path"], message=issue["message"])

        if args.emit_token_map_template:
            result = token_map_template([doc, *pack_docs])
            print(json.dumps(result, indent=2))
            return 0, result

        token_map_doc = _load_json_or_yaml(args.token_map, "runtime_unresolved_alias")
        checker_doc = (
            _load_json_or_yaml(args.checkers, "runtime_unknown_kind")
            if args.checkers is not None
            else None
        )
        contract, local_prog, issues = compile_runtime_document(
            doc,
            token_map_doc=token_map_doc,
            packs=pack_docs if pack_docs else None,
            checker_registry_doc=checker_doc,
        )

        _write_artifact_pair(args.out_dir, contract, local_prog)

        digest = canonical_json_digest(contract)
        result = {
            "ok": True,
            "file": str(args.file),
            "contract_digest": digest,
            "issues": issues,
        }
        print_output(result, get_format(args), text_renderer)
        return 0, result

    except RuntimeClosedError as exc:
        issue = {
            "code": exc.code,
            "message": exc.message,
            "path": exc.path,
            "severity": "error",
        }
        result = {
            "ok": False,
            "file": str(args.file),
            "contract_digest": None,
            "issues": [issue],
        }
        print_output(result, get_format(args), text_renderer)
        return 2, result
    except Exception:  # noqa: BLE001
        issue = {
            "code": "schema_error",
            "message": "schema_error",
            "path": [],
            "severity": "error",
        }
        result = {
            "ok": False,
            "file": str(args.file),
            "contract_digest": None,
            "issues": [issue],
        }
        print_output(result, get_format(args), text_renderer)
        return 2, result


def main() -> None:
    code, _ = run_cli()
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
