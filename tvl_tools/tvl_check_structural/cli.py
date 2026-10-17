from __future__ import annotations

import argparse
import json
import hashlib
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional

import yaml

from tvl.errors import TVLError
from tvl.loader import load
from tvl.structural_parser import StructuralParseError
from tvl.structural_sat import check_structural


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_event(payload: dict[str, Any]) -> None:
    print(json.dumps(payload))


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _build_repair_candidates(
    unsat_core: Optional[list[dict[str, Any]]],
    file_path: Path,
) -> list[dict[str, Any]]:
    if not unsat_core:
        return []

    limit = 5
    ordered_core = sorted(
        (entry for entry in unsat_core if isinstance(entry, dict)),
        key=lambda entry: json.dumps(entry, sort_keys=True),
    )[:limit]

    candidates: list[dict[str, Any]] = []
    for index, entry in enumerate(ordered_core):
        expression = entry.get("expression")
        if not isinstance(expression, str):
            continue

        path_segments = entry.get("path") if isinstance(entry.get("path"), list) else []
        clause_id = entry.get("clause_id") or entry.get("id")
        summary = entry.get("summary") or expression
        core_key = json.dumps({"path": path_segments, "expr": expression}, sort_keys=True)
        core_hash = hashlib.sha1(core_key.encode("utf-8")).hexdigest()[:8]
        core_id = f"core-{core_hash}"

        numeric_match = re.match(
            r"\s*([A-Za-z0-9_.]+)\s*(<=|>=|<|>|==|!=)\s*([-+]?[0-9]*\.?[0-9]+)\s*",
            expression,
        )

        symbols: list[str] = []
        intent = "delete_clause"
        edits: list[dict[str, Any]] = []
        rationale: list[str] = []
        confidence = 0.35

        if numeric_match:
            symbol, operator, value_str = numeric_match.groups()
            symbols = [symbol]
            try:
                numeric_value = float(value_str)
            except ValueError:
                numeric_value = None
            if numeric_value is not None and math.isfinite(numeric_value):
                delta = max(1.0, abs(numeric_value) * 0.1)
                if operator in {"<=", "<"}:
                    new_value = numeric_value + delta
                    new_expr = expression.replace(value_str, _format_number(new_value), 1)
                    intent = "relax_bound"
                    rationale.append(
                        f"Relax upper bound: {symbol} from {value_str} → {_format_number(new_value)}"
                    )
                elif operator in {">=", ">"}:
                    new_value = numeric_value - delta
                    new_expr = expression.replace(value_str, _format_number(new_value), 1)
                    intent = "relax_bound"
                    rationale.append(
                        f"Relax lower bound: {symbol} from {value_str} → {_format_number(new_value)}"
                    )
                else:
                    new_expr = expression
                    rationale.append("Consider widening equality or removing clause.")
                edits.append(
                    {
                        "file": str(file_path),
                        "before": expression,
                        "after": new_expr,
                    }
                )
                confidence = 0.6
            else:
                rationale.append("Unable to parse numeric bound; review clause manually.")

        if not edits:
            edits.append(
                {
                    "file": str(file_path),
                    "before": expression,
                    "after": f"# REVIEW: disable {expression}",
                }
            )
            rationale.append("Disable or rewrite the conflicting clause.")

        candidate = {
            "id": f"rc-{index + 1}",
            "intent": intent,
            "confidence": round(confidence, 2),
            "blastRadius": {
                "files": 1,
                "clauses": 1,
                "symbols": symbols,
            },
            "edits": edits,
            "rationale": rationale or ["Candidate derived from unsat core."],
            "proofHint": "not-checked",
            "path": path_segments,
            "clauseId": clause_id,
            "coreId": core_id,
            "coreSummary": summary,
            "variables": symbols,
        }
        candidates.append(candidate)
    return candidates



def _apply_candidate_edits(original_text: str, candidate: dict[str, Any]) -> str:
    edits = candidate.get("edits")
    if not isinstance(edits, list):
        return original_text
    text = original_text
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        before = edit.get("before")
        after = edit.get("after")
        if not isinstance(before, str) or after is None:
            continue
        after_str = str(after)
        if before in text:
            text = text.replace(before, after_str, 1)
    return text


def _write_temp_file(content: str, suffix: str = "") -> Path:
    with NamedTemporaryFile("w", delete=False, suffix=suffix, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp.flush()
        return Path(tmp.name)


def _build_witness_id(assignment: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(assignment, dict):
        return None
    try:
        items = tuple(sorted(assignment.items()))
    except TypeError:
        return None
    return f"w-{abs(hash(items)) % 1_000_000:06d}"


def _load_module(path: Path) -> dict[str, Any]:
    return load(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check structural satisfiability of a TVL module")
    parser.add_argument("file", type=Path, help="Path to TVL module YAML")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON diagnostics")
    parser.add_argument("--candidate-file", type=Path, help="Path to repair candidate JSON", default=None)
    return parser.parse_args()


def _prepare_module_path(
    args: argparse.Namespace,
) -> tuple[Path, Optional[Path], Optional[dict[str, Any]]]:
    """Return the module path to check, any temp file holding a patched copy, and the candidate.

    With ``--candidate-file`` the candidate's edits are applied to a temporary
    copy of the module; the original file is never modified.
    """
    if not args.candidate_file:
        return args.file, None, None
    candidate_payload = json.loads(args.candidate_file.read_text(encoding="utf-8"))
    original_text = args.file.read_text(encoding="utf-8")
    patched_text = _apply_candidate_edits(original_text, candidate_payload)
    if patched_text == original_text:
        return args.file, None, candidate_payload
    temp_file = _write_temp_file(patched_text, suffix=args.file.suffix)
    return temp_file, temp_file, candidate_payload


def _remove_temp_file(temp_file: Optional[Path]) -> None:
    if temp_file is None:
        return
    try:
        temp_file.unlink(missing_ok=True)
    except OSError:
        pass


def _load_module_or_exit(module_path: Path, args: argparse.Namespace, temp_file: Optional[Path]) -> dict[str, Any]:
    try:
        return _load_module(module_path)
    except (TVLError, yaml.YAMLError, FileNotFoundError, ValueError) as exc:
        error_msg = str(exc)
        if args.json:
            error_payload: dict[str, Any] = {
                "schemaVersion": "1.0",
                "kind": "PhaseResult",
                "phase": "structural",
                "ok": False,
                "status": "error",
                "error": error_msg,
                "timestamp": _current_timestamp(),
                "durationMs": 0,
            }
            if getattr(exc, "code", None) == "unsupported_construct":
                error_payload["code"] = "unsupported_construct"
                error_payload["construct"] = getattr(exc, "construct", None)
            print(json.dumps(error_payload, indent=2))
        else:
            if getattr(exc, "code", None) == "unsupported_construct":
                print(f"unsupported_construct: {getattr(exc, 'construct', '')}", file=sys.stderr)
            else:
                print(f"Error loading module: {error_msg}", file=sys.stderr)
        _remove_temp_file(temp_file)
        raise SystemExit(2)


def _check_module_or_exit(
    module: dict[str, Any], args: argparse.Namespace, temp_file: Optional[Path]
) -> tuple[Any, int]:
    """Run the structural check; return the result and its duration in ms."""
    start_time = time.perf_counter()
    try:
        result = check_structural(module)
    except StructuralParseError as exc:
        # A well-shaped structural entry whose expression string is malformed (a
        # user typo) or over-complex (deep nesting / DNF blowup). Mirror the
        # graceful degradation the lint sibling already provides: emit a
        # structured diagnostic and exit 2, never a raw traceback.
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        _remove_temp_file(temp_file)
        if args.json:
            payload = {
                "schemaVersion": "1.0",
                "kind": "PhaseResult",
                "phase": "structural",
                "ok": False,
                "status": "error",
                "error": f"invalid structural constraint: {exc}",
                "assignment": None,
                "unsat_core": None,
                "repair_candidates": [],
                "timestamp": _current_timestamp(),
                "durationMs": duration_ms,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(f"Error: invalid structural constraint: {exc}", file=sys.stderr)
        raise SystemExit(2)
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _remove_temp_file(temp_file)
    return result, duration_ms


def _emit_repair_candidates(result: Any, file_path: Path) -> list[dict[str, Any]]:
    """Build repair candidates; on UNSAT, emit one RepairCandidateProduced event each."""
    candidates = _build_repair_candidates(result.unsat_core, file_path)
    if not result.ok:
        for core_index, candidate in enumerate(candidates):
            event = {
                "schemaVersion": "1.0",
                "kind": "RepairCandidateProduced",
                "coreId": candidate.get("coreId") or f"core-{core_index + 1}",
                "candidate": candidate,
                "timestamp": _current_timestamp(),
            }
            _emit_event(event)
    return candidates


def _emit_candidate_validation(result: Any, candidate_payload: dict[str, Any], duration_ms: int) -> None:
    status = "sat" if result.ok else "unsat"
    validation_event = {
        "schemaVersion": "1.0",
        "kind": "RepairCandidateValidated",
        "candidateId": candidate_payload.get("id") or "candidate",
        "status": status,
        "durationMs": duration_ms,
        "witnessId": _build_witness_id(result.assignment) if result.ok else None,
        "timestamp": _current_timestamp(),
    }
    _emit_event(validation_event)


def _report_json(
    result: Any,
    args: argparse.Namespace,
    candidate_payload: Optional[dict[str, Any]],
    duration_ms: int,
) -> None:
    if candidate_payload is None:
        candidates = _emit_repair_candidates(result, args.file)
    else:
        candidates = []
        _emit_candidate_validation(result, candidate_payload, duration_ms)

    payload = {
        "schemaVersion": "1.0",
        "kind": "PhaseResult",
        "phase": "structural",
        "ok": result.ok,
        "status": "passed" if result.ok else "unsat",
        "assignment": result.assignment,
        "unsat_core": result.unsat_core,
        "repair_candidates": candidates,
        "timestamp": _current_timestamp(),
        "durationMs": duration_ms,
    }
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if result.ok else 2)


def _report_text(result: Any) -> None:
    if result.ok:
        print("Structural constraints satisfiable.")
        for name, value in sorted((result.assignment or {}).items()):
            print(f"  {name}: {value}")
        raise SystemExit(0)

    print("Structural constraints UNSAT.")
    for entry in result.unsat_core or []:
        path_str = ".".join(str(p) for p in entry.get("path", []))
        print(f"- {path_str or '<root>'}")
        print(f"    expression: {entry.get('expression')}")
        for clause in entry.get("clauses") or []:
            print(f"      clause: {clause}")
    raise SystemExit(2)


def main() -> None:
    args = _parse_args()
    module_path, temp_file, candidate_payload = _prepare_module_path(args)
    module = _load_module_or_exit(module_path, args, temp_file)
    result, duration_ms = _check_module_or_exit(module, args, temp_file)
    if args.json:
        _report_json(result, args, candidate_payload, duration_ms)
    _report_text(result)


if __name__ == "__main__":
    main()
