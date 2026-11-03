import argparse
import json
from pathlib import Path
from typing import Any

from tvl.loader import is_pack_document

from tvl_tools.cli_utils import (
    add_common_args,
    get_format,
    handle_error,
    load_yaml_safely,
    print_output,
)


def text_renderer(data: dict[str, Any]) -> None:
    """Render the parsed AST in text mode."""
    print(json.dumps(data.get("ast"), indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse TVL YAML and print AST as JSON")
    parser.add_argument("file", type=Path, help="Path to TVL YAML file")
    add_common_args(parser)
    args = parser.parse_args()

    try:
        ast = load_yaml_safely(args.file)
        if not isinstance(ast, dict):
            raise TypeError("TVL module must be a mapping at the top level")
        output: dict[str, Any] = {
            "ok": True,
            "file": str(args.file),
            "ast": ast,
        }
        if is_pack_document(ast):
            output["document_kind"] = "pack"
        print_output(output, get_format(args), text_renderer)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
