import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List

from tvl.configuration import load_configuration, validate_configuration
from tvl.errors import TVLError
from tvl.loader import load


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_event(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload))


def _read_config(path: Path | str) -> Dict[str, Any]:
    if str(path) == "-":
        data = sys.stdin.read()
        with NamedTemporaryFile("w", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp.write(data)
            tmp.flush()
            temp_path = Path(tmp.name)
        try:
            return load_configuration(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
    return load_configuration(path)


def _normalize_failures(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for issue in report.get("domains", []):
        failures.append(
            {
                "phase": "schema",
                "code": issue.get("code"),
                "path": issue.get("path"),
                "message": issue.get("message"),
                "remediation": _default_remediation(issue.get("code")),
            }
        )
    for issue in report.get("constraints", []):
        failures.append(
            {
                "phase": "structural",
                "code": issue.get("code"),
                "clauseId": issue.get("constraint_index"),
                "raw": issue.get("raw"),
                "message": "Structural constraint violated",
                "remediation": ["Adjust assignments or relax clause"],
            }
        )
    return failures


def _default_remediation(code: Any) -> List[str]:
    if code == "missing_assignment":
        return ["Provide an assignment for the missing TVAR"]
    if code == "domain_violation":
        return ["Change the value to fall within the domain", "Relax the domain in the module"]
    if code == "module_mismatch":
        return ["Align configuration module_id with TVL module"]
    if code == "unknown_assignment":
        return ["Remove or rename the unknown assignment"]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a configuration against a TVL module")
    parser.add_argument("module", type=Path, help="TVL module YAML")
    parser.add_argument("config", help="Configuration YAML or '-' for stdin")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        module = load(args.module)
        config = _read_config(args.config)
        started = time.perf_counter()
        report = validate_configuration(module, config)
        duration_ms = int((time.perf_counter() - started) * 1000)
        report.update({"module": str(args.module), "config": str(args.config)})
        failures = _normalize_failures(report)
        status = "valid" if report["ok"] else "invalid"

        if args.json:
            event = {
                "schemaVersion": "1.0",
                "kind": "AssignmentChecked",
                "module": str(args.module),
                "assignmentFile": str(args.config),
                "status": status,
                "failures": failures,
                "durationMs": duration_ms,
                "timestamp": _current_timestamp(),
                "backend": "static",
            }
            _emit_event(event)
            payload = {
                **report,
                "module": str(args.module),
                "status": status,
                "failures": failures,
                "durationMs": duration_ms,
                "backend": "static",
            }
            print(json.dumps(payload, indent=2))
        else:
            if report["ok"]:
                print("Configuration is structurally valid.")
            else:
                print("Configuration validation failed:")
                for issue in report["domains"]:
                    print(f"[domain] {issue['path']}: {issue['message']}")
                for issue in report["constraints"]:
                    idx = issue.get("constraint_index")
                    print(f"[constraint #{idx}] {issue.get('raw')}")
        if not report["ok"]:
            raise SystemExit(5)
    except TVLError as exc:
        diag = {"ok": False, "error": str(exc), "module": str(args.module), "config": str(args.config)}
        if args.json:
            event = {
                "schemaVersion": "1.0",
                "kind": "AssignmentChecked",
                "assignmentFile": str(args.config),
                "module": str(args.module),
                "status": "invalid",
                "failures": [{"phase": "schema", "message": str(exc)}],
                "timestamp": _current_timestamp(),
                "durationMs": 0,
                "backend": "static",
            }
            _emit_event(event)
            diag.update(event)
            print(json.dumps(diag, indent=2))
        else:
            print(json.dumps(diag, indent=2))
        raise SystemExit(5)


if __name__ == "__main__":
    main()
