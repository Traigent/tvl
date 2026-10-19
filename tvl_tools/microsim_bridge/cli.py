from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, NoReturn

from .bridge import MICROSIM_CONTROLS, dump_presets, presets_from_spec


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
        help="Destination JSON file. Required unless --dry-run is given.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payload instead of writing it to disk.",
    )
    return parser


def _fail(message: str, dry_run: bool) -> NoReturn:
    import json
    import sys

    print(f"Error: {message}", file=sys.stderr)
    if dry_run:
        print(json.dumps({"ok": False, "error": message}, indent=2))
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    import json
    import sys

    from tvl.loader import is_pack_document
    from tvl_tools.cli_utils import load_yaml_safely

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.output is None and not args.dry_run:
        parser.error("-o/--output is required unless --dry-run is given")

    try:
        raw_doc = load_yaml_safely(args.spec)
    except (OSError, ValueError) as exc:
        _fail(str(exc), args.dry_run)
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
    else:
        _fail(f"{args.spec} is not a TVL module (expected a YAML mapping)", args.dry_run)

    warnings: list[str] = []
    try:
        payload: dict[str, Any] = presets_from_spec(raw_doc, warnings)
        serialized = json.dumps(payload, indent=2, allow_nan=False)
    except (ValueError, TypeError, ArithmeticError) as exc:
        _fail(str(exc), args.dry_run)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not payload["defaults"] and not payload["sliders"]:
        _fail(f"no exportable tvars found in {args.spec}", args.dry_run)
    if not set(payload["sliders"]) & set(MICROSIM_CONTROLS):
        print(
            "warning: no exported TVAR matches a MicroSim control "
            f"({', '.join(MICROSIM_CONTROLS)}); the MicroSim ignores the exported values",
            file=sys.stderr,
        )

    if args.dry_run:
        print(serialized)
        return

    try:
        dump_presets(payload, args.output)
    except (OSError, ValueError) as exc:
        _fail(f"cannot write {args.output}: {exc}", False)
    print(f"✅ wrote presets to {args.output}")


if __name__ == "__main__":
    main()
