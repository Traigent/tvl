"""CLI for tvl-compose: Flatten overlay files into valid TVL 1.0 modules.

Usage:
    tvl-compose overlay.yml -o output.tvl.yml
    tvl-compose overlay.yml --validate  # compose and validate in one step
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tvl_tools.cli_utils import add_common_args, get_format, handle_error, load_yaml_safely, print_output


def _resolve_base_path(overlay_path: Path, base_ref: str) -> Path:
    """Resolve the base file path relative to the overlay file."""
    if Path(base_ref).is_absolute():
        return Path(base_ref)
    return overlay_path.parent / base_ref


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge override into base, with override taking precedence."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            # Only TVAR lists are merged by name. Other lists, such as enum domains
            # or numeric ranges, should be replaced by the overlay value.
            if key == "tvars":
                result[key] = _merge_tvar_lists(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _merge_tvar_lists(base_tvars: List[Dict], override_tvars: List[Dict]) -> List[Dict]:
    """Merge TVAR lists by name, with overrides taking precedence."""
    result = copy.deepcopy(base_tvars)
    base_by_name = {t.get("name"): i for i, t in enumerate(result)}

    for override_tvar in override_tvars:
        name = override_tvar.get("name")
        if name and name in base_by_name:
            # Merge into existing TVAR
            idx = base_by_name[name]
            result[idx] = _deep_merge(result[idx], override_tvar)
        else:
            # This is an error - can't add new TVARs in overlay
            raise ValueError(f"Cannot add new TVAR '{name}' in overlay. Overlays can only narrow existing TVARs.")

    return result


def _validate_narrowing(base: Dict[str, Any], composed: Dict[str, Any]) -> List[str]:
    """Validate that the composed spec only narrows (doesn't widen) the base."""
    errors = []

    # Check TVARs
    base_tvars = {t["name"]: t for t in base.get("tvars", [])}
    composed_tvars = {t["name"]: t for t in composed.get("tvars", [])}

    for name, composed_tvar in composed_tvars.items():
        if name not in base_tvars:
            errors.append(f"TVAR '{name}' added in overlay (not allowed)")
            continue

        base_tvar = base_tvars[name]
        base_domain = base_tvar.get("domain")
        composed_domain = composed_tvar.get("domain")

        # Check enum domains
        if isinstance(base_domain, list) and isinstance(composed_domain, list):
            base_set = set(str(v) for v in base_domain)
            composed_set = set(str(v) for v in composed_domain)
            added = composed_set - base_set
            if added:
                errors.append(f"TVAR '{name}': cannot add values {added} in overlay")

        # Check range domains
        if isinstance(base_domain, dict) and isinstance(composed_domain, dict):
            if "range" in base_domain and "range" in composed_domain:
                base_range = base_domain["range"]
                composed_range = composed_domain["range"]
                if composed_range[0] < base_range[0]:
                    errors.append(f"TVAR '{name}': cannot widen range minimum from {base_range[0]} to {composed_range[0]}")
                if composed_range[1] > base_range[1]:
                    errors.append(f"TVAR '{name}': cannot widen range maximum from {base_range[1]} to {composed_range[1]}")

    # Check budgets (can only decrease)
    base_budgets = base.get("exploration", {}).get("budgets", {})
    composed_budgets = composed.get("exploration", {}).get("budgets", {})

    for key in ["max_trials", "max_spend_usd", "max_wallclock_s"]:
        if key in base_budgets and key in composed_budgets:
            if composed_budgets[key] > base_budgets[key]:
                errors.append(f"Budget '{key}': cannot increase from {base_budgets[key]} to {composed_budgets[key]}")

    return errors


def compose(overlay_path: Path, validate_narrowing: bool = True) -> Dict[str, Any]:
    """Compose an overlay file into a valid TVL 1.0 module.

    Args:
        overlay_path: Path to the overlay YAML file
        validate_narrowing: If True, validate that overlay only narrows base

    Returns:
        Composed TVL 1.0 module as a dict
    """
    overlay = load_yaml_safely(overlay_path)

    if not isinstance(overlay, dict):
        raise TypeError("Overlay must be a YAML mapping")

    # Check for overlay marker
    overlay_meta = overlay.get("_tvl_overlay")
    if not overlay_meta:
        raise ValueError("File is not a TVL overlay (missing _tvl_overlay key)")

    extends = overlay_meta.get("extends")
    if not extends:
        raise ValueError("Overlay must specify 'extends' in _tvl_overlay")

    # Load base module
    base_path = _resolve_base_path(overlay_path, extends)
    base = load_yaml_safely(base_path)

    if not isinstance(base, dict):
        raise TypeError(f"Base module {base_path} must be a YAML mapping")

    # Recursively resolve if base is also an overlay
    if "_tvl_overlay" in base:
        base = compose(base_path, validate_narrowing=False)

    # Get overrides
    overrides = overlay.get("overrides", {})

    # Compose by merging
    composed = _deep_merge(base, overrides)

    # Remove overlay-specific keys from output
    composed.pop("_tvl_overlay", None)

    # Validate narrowing if requested
    if validate_narrowing:
        errors = _validate_narrowing(base, composed)
        if errors:
            raise ValueError("Overlay validation failed:\n  " + "\n  ".join(errors))

    return composed


def text_renderer(data: Dict[str, Any]) -> None:
    """Render compose result as text."""
    if data.get("ok"):
        if data.get("output_file"):
            print(f"Composed: {data['output_file']}")
        else:
            # Print the composed YAML to stdout
            print(yaml.dump(data["composed"], default_flow_style=False, sort_keys=False))
    else:
        print(f"Error: {data.get('error')}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compose TVL overlay files into valid TVL 1.0 modules",
    )
    parser.add_argument("file", type=Path, help="Path to overlay YAML file")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip narrowing validation",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Also run tvl-validate on the composed output",
    )
    add_common_args(parser)
    args = parser.parse_args()

    try:
        composed = compose(args.file, validate_narrowing=not args.no_validate)

        result: Dict[str, Any] = {
            "ok": True,
            "file": str(args.file),
            "composed": composed,
        }

        # Write to output file if specified
        if args.output:
            with args.output.open("w", encoding="utf-8") as handle:
                yaml.dump(composed, handle, default_flow_style=False, sort_keys=False)
            result["output_file"] = str(args.output)

            # Optionally validate the output
            if args.validate:
                from tvl_tools.tvl_validate.cli import _load_schema, _schema_issues
                from tvl.lints import lint_module

                schema = _load_schema(Path(__file__))
                issues = _schema_issues(composed, schema)
                if not issues:
                    issues = lint_module(composed)

                result["validation"] = {
                    "ok": len(issues) == 0,
                    "issues": issues,
                }

                if issues:
                    result["ok"] = False

        print_output(result, get_format(args), text_renderer)

        if not result["ok"]:
            sys.exit(2)

    except Exception as exc:  # noqa: BLE001
        handle_error(exc, args)


if __name__ == "__main__":
    main()
