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
        help="Destination JSON file (defaults to the bundled Orientation RAG MicroSim presets file).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload instead of writing it to disk.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    import json
    import sys
    from tvl.loader import is_pack_document
    from tvl.yaml_safe import safe_load

    parser = _build_parser()
    args = parser.parse_args(argv)

    raw_doc = safe_load(args.spec.read_text(encoding="utf-8"))
    if isinstance(raw_doc, dict):
        refuse_construct: str | None = None
        if is_pack_document(raw_doc):
            refuse_construct = "tvl_pack"
        else:
            for blk in ("requirements", "monitors", "responses"):
                if blk in raw_doc:
                    refuse_construct = blk
                    break
        if refuse_construct is not None:
            print(f"unsupported_construct: {refuse_construct}", file=sys.stderr)
            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "code": "unsupported_construct",
                            "construct": refuse_construct,
                        },
                        indent=2,
                    )
                )
            raise SystemExit(2)

    payload: dict[str, Any] = build_presets(args.spec)
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return

    dump_presets(payload, args.output)
    print(f"✅ wrote presets to {args.output}")


if __name__ == "__main__":
    main()
