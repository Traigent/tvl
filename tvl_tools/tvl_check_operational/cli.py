from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from tvl.errors import TVLError
from tvl.loader import load
from tvl.operational import check_operational


def _load_module(path: Path) -> Dict[str, Any]:
    return load(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check operational feasibility of a TVL module")
    parser.add_argument("file", type=Path, help="Path to TVL module YAML")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON diagnostics")
    args = parser.parse_args()

    try:
        module = _load_module(args.file)
    except (TVLError, yaml.YAMLError, FileNotFoundError, ValueError) as exc:
        # A missing or malformed module file used to propagate as a raw
        # traceback and exit 1, with no JSON emitted even under --json. Mirror
        # the graceful degradation tvl-check-structural already provides:
        # emit a structured diagnostic and exit 2 (issue #20).
        error_msg = str(exc)
        if args.json:
            error_payload = {
                "schemaVersion": "1.0",
                "kind": "PhaseResult",
                "phase": "operational",
                "ok": False,
                "status": "error",
                "error": error_msg,
            }
            print(json.dumps(error_payload, indent=2))
        else:
            print(f"Error loading module: {error_msg}", file=sys.stderr)
        raise SystemExit(2)

    result = check_operational(module)

    if args.json:
        payload = {
            "ok": result.ok,
            "binding_budget": result.binding_budget,
            "issues": result.issues,
        }
        print(json.dumps(payload, indent=2))
        raise SystemExit(0 if result.ok else 2)

    if result.ok:
        print("Operational feasibility checks passed (budgets respected or skipped).")
        raise SystemExit(0)

    print("Operational feasibility failed.")
    if result.binding_budget:
        print(f"Binding budget: {result.binding_budget}")
    for issue in result.issues:
        path = issue.get("path")
        print(f"- {issue.get('code')}: {issue.get('message')} ({path})")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
