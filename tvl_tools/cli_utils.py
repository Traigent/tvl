import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from tvl.yaml_safe import safe_load


def blocking_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Issues that decide ok/exit status: everything except severity "info"."""
    return [i for i in issues if i.get("severity") != "info"]


def format_issue_line(issue: dict[str, Any]) -> str:
    """Format one diagnostic for text output, printing its location exactly once.

    Closed diagnostics already start their message with the field path, so the
    path is only prepended when the message does not carry it.
    """
    path = ".".join(str(p) for p in issue.get("path", [])) or "<root>"
    message = str(issue.get("message"))
    if message.startswith(f"{path}: "):
        return f"[{issue.get('code')}] {message}"
    return f"[{issue.get('code')}] {path}: {message}"


DISTRIBUTION = "tvl-spec"


class _VersionAction(argparse.Action):
    """Print ``<prog> <tvl-spec version>`` and exit 0.

    The version is read from the installed distribution metadata only when the
    flag is given, so it is correct for an editable install and for a wheel, and
    a missing installation fails on ``--version`` instead of on every run.
    """

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        version = importlib.metadata.version(DISTRIBUTION)
        print(f"{parser.prog} {version}")
        parser.exit(0)


def add_version_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--version``, reporting the installed tvl-spec version."""
    parser.add_argument(
        "--version",
        action=_VersionAction,
        help=f"Show the installed {DISTRIBUTION} version and exit",
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add standard arguments to the CLI parser."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--json",
        action="store_true",
        help="Deprecated: use --format json instead",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )


def get_format(args: argparse.Namespace) -> str:
    """Determine the output format from args."""
    if args.json:
        return "json"
    return args.format


def load_yaml_safely(path: Path) -> Any:
    """Load YAML file with friendly error handling."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return safe_load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {path}") from exc
    except yaml.YAMLError as exc:
        if hasattr(exc, "problem_mark"):
            mark = exc.problem_mark
            raise ValueError(
                f"YAML syntax error at line {mark.line + 1}, column {mark.column + 1}: {exc.problem}"
            ) from exc
        raise ValueError(f"YAML syntax error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Failed to read file: {exc}") from exc


def print_output(
    data: dict[str, Any],
    format_type: str,
    text_renderer: Optional[Callable[..., None]] = None,
) -> None:
    """Print output in the specified format."""
    if format_type == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    if text_renderer:
        text_renderer(data)
        return

    # Fallback for text if no renderer provided
    if not data.get("ok", True):
        print(f"Error: {data.get('error', 'Unknown error')}", file=sys.stderr)
    else:
        print("OK")


def handle_error(exc: Exception, args: argparse.Namespace) -> None:
    """Handle top-level exceptions with consistent formatting."""
    fmt = get_format(args)
    diag = {
        "ok": False,
        "file": str(args.file) if hasattr(args, "file") else None,
        "error": str(exc),
    }

    if fmt == "json":
        print(json.dumps(diag, indent=2))
    else:
        print(f"Error: {exc}", file=sys.stderr)

    sys.exit(2)
