from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .bridge import build_presets, dump_presets


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a TVL spec into Orientation RAG MicroSim presets.",
    )
    parser.add_argument(
        "spec",
        type=Path,
        help="Path to the TVL specification (YAML).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("tvl_book/website_content/microsims/orientation-rag-circuit/microsim_presets.json"),
        help="Destination JSON file (defaults to the book's MicroSim location).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload instead of writing it to disk.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    payload: dict[str, Any] = build_presets(args.spec)
    if args.dry_run:
        import json

        print(json.dumps(payload, indent=2))
        return

    dump_presets(payload, args.output)
    print(f"✅ wrote presets to {args.output}")


if __name__ == "__main__":
    main()
