from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from tvl.loader import load
from tvl.operational import check_operational


def _load_module(path: Path) -> Dict[str, Any]:
    return load(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check operational feasibility of a TVL module")
    parser.add_argument("file", type=Path, help="Path to TVL module YAML")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON diagnostics")
    args = parser.parse_args()

    module = _load_module(args.file)
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
