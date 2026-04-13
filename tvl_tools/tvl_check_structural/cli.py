from __future__ import annotations

import argparse
import json
import hashlib
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional

import yaml

from tvl.loader import load
from tvl.structural_sat import check_structural


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_event(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload))


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _build_repair_candidates(
    unsat_core: Optional[List[Dict[str, Any]]],
    file_path: Path,
) -> List[Dict[str, Any]]:
    if not unsat_core:
        return []

    limit = 5
    ordered_core = sorted(
        (entry for entry in unsat_core if isinstance(entry, dict)),
        key=lambda entry: json.dumps(entry, sort_keys=True),
    )[:limit]

    candidates: List[Dict[str, Any]] = []
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

        symbols: List[str] = []
        intent = "delete_clause"
        edits: List[Dict[str, Any]] = []
        rationale: List[str] = []
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



def _apply_candidate_edits(original_text: str, candidate: Dict[str, Any]) -> str:
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


def _build_witness_id(assignment: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(assignment, dict):
        return None
    try:
        items = tuple(sorted(assignment.items()))
    except TypeError:
        return None
    return f"w-{abs(hash(items)) % 1_000_000:06d}"


def _load_module(path: Path) -> Dict[str, Any]:
    return load(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check structural satisfiability of a TVL module")
    parser.add_argument("file", type=Path, help="Path to TVL module YAML")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON diagnostics")
    parser.add_argument("--candidate-file", type=Path, help="Path to repair candidate JSON", default=None)
    args = parser.parse_args()

    original_text = None
    module_path = args.file
    temp_file: Optional[Path] = None

    candidate_payload: Optional[Dict[str, Any]] = None
    if args.candidate_file:
        candidate_payload = json.loads(args.candidate_file.read_text(encoding="utf-8"))
        original_text = args.file.read_text(encoding="utf-8")
        patched_text = _apply_candidate_edits(original_text, candidate_payload)
        module_path = args.file
        if patched_text != original_text:
            temp_file = _write_temp_file(patched_text, suffix=args.file.suffix)
            module_path = temp_file

    module = _load_module(module_path)
    start_time = time.perf_counter()
    result = check_structural(module)
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    if temp_file is not None:
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass

    if args.json:
        if candidate_payload is None:
            candidates = _build_repair_candidates(result.unsat_core, args.file)
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
        else:
            candidates = []
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

    if result.ok:
        print("Structural constraints satisfiable.")
        if result.assignment:
            for name, value in sorted(result.assignment.items()):
                print(f"  {name}: {value}")
        raise SystemExit(0)

    print("Structural constraints UNSAT.")
    if result.unsat_core:
        for entry in result.unsat_core:
            path_str = ".".join(str(p) for p in entry.get("path", []))
            print(f"- {path_str or '<root>'}")
            print(f"    expression: {entry.get('expression')}")
            clauses = entry.get("clauses") or []
            if clauses:
                for clause in clauses:
                    print(f"      clause: {clause}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
