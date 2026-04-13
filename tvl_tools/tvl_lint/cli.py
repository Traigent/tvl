import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from tvl.lints import lint_module
from tvl_tools.cli_utils import add_common_args, get_format, handle_error, load_yaml_safely, print_output


def lint(doc: Dict[str, Any], precision: int = 1000) -> List[Dict[str, Any]]:
    """Run lint checks against a parsed TVL document."""
    return lint_module(doc, precision=precision)


def text_renderer(data: Dict[str, Any]) -> None:
    """Render lint issues in a human-friendly format."""
    issues = data.get("issues", [])
    if issues:
        for issue in issues:
            path = ".".join(str(p) for p in issue.get("path", [])) or "<root>"
            print(f"[{issue.get('code')}] {path}: {issue.get('message')}")
    else:
        print("Lint checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint TVL YAML for common issues")
    parser.add_argument("file", type=Path, help="Path to TVL YAML file")
    parser.add_argument(
        "--precision",
        type=int,
        default=1000,
        help="Float precision factor P for SMT encoding (default: 1000). "
        "Higher values allow finer float distinctions but may increase solver time.",
    )
    add_common_args(parser)
    args = parser.parse_args()

    try:
        doc: Dict[str, Any] = load_yaml_safely(args.file)
        issues = lint(doc if isinstance(doc, dict) else {}, precision=args.precision)

        out = {
            "ok": len(issues) == 0,
            "file": str(args.file),
            "issues": issues,
        }

        print_output(out, get_format(args), text_renderer)

        if issues:
            sys.exit(2)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
