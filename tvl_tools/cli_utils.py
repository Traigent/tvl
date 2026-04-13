import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml


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
            return yaml.safe_load(handle)
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
    data: Dict[str, Any],
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
