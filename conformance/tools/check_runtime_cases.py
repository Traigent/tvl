#!/usr/bin/env python3
"""Check the DRAFT public language fixture corpus.

This checks fixture integrity, not runtime conformance or enablement. The
implementation under test must compute every expected assertion separately.
Run: .venv/bin/python -B conformance/tools/check_runtime_cases.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from tvl.yaml_safe import safe_load
from tvl.runtime_conformance import (
    LANGUAGE_FAMILY_GLOBS as FAMILIES,
    _ALLOWED_EXPECTED_KEYS_BY_KIND,
)


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "conformance/cases/runtime"

# RFC 13's case locations, extended by the probes added during Appendix A
# alignment. A case's family field remains its directory name (Appendix A14).

INPUT_KEYS = {'compose': 'operation post_validate_without_provenance', 'lint': 'operation', 'projection': 'token_map checker_labels local_artifacts requested_fields', 'roundtrip': 'operation monitor backend_profile', 'toolchain': 'entrypoint reader arguments document_yaml measurement_role monitor_outcomes measurement_format', 'measurement': 'role monitor_outcomes legacy_decision', 'join': 'legacy_decision monitor_verdicts', 'schema': 'instance'}
EXPECTED_KEYS = set().union(*_ALLOWED_EXPECTED_KEYS_BY_KIND.values())
ENVELOPE_KEYS = set("case_format family description spec_refs module pack base overlay input expected".split())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def string_keys(value, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            require(isinstance(key, str), f"non-string key at {path}: {key!r}")
            string_keys(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            string_keys(child, f"{path}/{index}")


def unique_yaml_keys(node) -> None:
    """Supplement safe_load: its loader does not reject duplicate YAML keys."""
    if isinstance(node, yaml.MappingNode):
        keys = [(key.tag, key.value) for key, _ in node.value]
        require(len(keys) == len(set(keys)), "duplicate YAML key")
        for _, child in node.value:
            unique_yaml_keys(child)
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            unique_yaml_keys(child)


def asserted_codes(expected: dict) -> set[str]:
    codes = set(expected.get("absent_diagnostics", []))
    codes.update(expected.get("readiness_issues", []))
    codes.update(issue["code"] for issue in expected.get("diagnostics", []))
    if "error" in expected:
        codes.add(expected["error"])
    return codes


def check_case(path: Path, known_codes: set[str]) -> dict:
    source = path.read_text()
    case = safe_load(source)
    require(isinstance(case, dict), "case is not a mapping")
    string_keys(case)
    unique_yaml_keys(yaml.compose(source, Loader=yaml.SafeLoader))
    require(set(case) <= ENVELOPE_KEYS, "unknown envelope key")
    require(case.get("case_format") == "tvl-runtime-case/1", "wrong format")
    require(case.get("family") == path.parent.name, "family differs from directory")
    require(bool(case.get("description")) and bool(case.get("spec_refs")), "missing description/spec_refs")
    payload = set(case) & {"module", "pack", "base", "overlay"}
    require(payload in ({"module"}, {"pack"}, {"base", "overlay"}), "invalid payload alternative")
    inp, expected = case["input"], case["expected"]
    require(inp.get("kind") in INPUT_KEYS, "unknown input kind")
    require(set(inp) <= {"kind", *INPUT_KEYS[inp["kind"]].split()}, "unknown input key")
    require(bool(expected) and set(expected) <= EXPECTED_KEYS, "empty/unknown assertion key")
    require(not (asserted_codes(expected) - known_codes), f"codes outside RFC 5: {asserted_codes(expected) - known_codes}")
    for issue in expected.get("diagnostics", []):
        require(set(issue) == {"code", "severity"}, "diagnostic shape")
        require(issue["severity"] in {"error", "warning"}, "unknown diagnostic severity")
    relative = path.relative_to(CASES)
    require(any(relative.match(glob) for globs in FAMILIES.values() for glob in globs), "unmapped enablement family")
    for pointer in expected.get("projected_fields", {}):
        require(pointer.startswith("/declarations/"), "projection pointer outside hosted declarations")
    for key in payload:
        doc = case[key]
        for response in doc.get("responses", []):
            require(all("trigger" in rule and "on" not in rule for rule in response["rules"]), "obsolete rule key")
        for req in doc.get("requirements", []):
            for pred in (req.get("violation", {}), req.get("among", {})):
                for transition in pred.get("transitions", []):
                    require("when" in transition and "on" not in transition, "obsolete transition key")
        for monitor in doc.get("monitors", []):
            decision = monitor["decision"]
            if "threshold_factor" in decision:
                require("confidence" not in decision, "burn confidence forbidden by RFC 4.5")
    return case


def main() -> int:
    known_codes = {'runtime_version_required', 'runtime_min_samples_out_of_range', 'runtime_window_out_of_range', 'runtime_content_on_backend_source', 'runtime_repeat_after_hours_out_of_range', 'runtime_max_stale_windows_out_of_range', 'runtime_invalid_ladder', 'runtime_unresolved_fraction_out_of_range', 'runtime_overlay_weakens', 'runtime_within_ms_out_of_range', 'runtime_max_tracked_correlations_out_of_range', 'recovery_deadline_impossible', 'runtime_sampling_rate_out_of_range', 'requirement_weaker_than_floor', 'runtime_max_count_out_of_range', 'runtime_duplicate_key', 'runtime_unresolved_alias', 'runtime_incompatible_replacement', 'runtime_tool_not_code_identifier', 'runtime_confidence_out_of_range', 'missing_monitor_counts', 'runtime_invalid_profile', 'runtime_unknown_kind', 'response_irreversible_without_approval', 'response_suspend_without_human', 'runtime_met_unreachable_at_min_samples', 'declared_version_below_constructs', 'runtime_closure_windows_out_of_range', 'runtime_max_active_obligations_out_of_range', 'runtime_ref_kind_mismatch', 'response_unknown_action', 'closure_unreachable', 'runtime_dependency_cycle', 'runtime_horizon_out_of_range', 'runtime_within_hours_out_of_range', 'tenant_floor_outside_pack', 'runtime_burn_out_of_range', 'response_suspend_unconfirmed', 'runtime_unsupported_capability', 'runtime_legacy_profile_override', 'response_rollback_target_uncertified', 'runtime_liveness_missing', 'runtime_name_collision', 'runtime_breach_unreachable_at_min_samples', 'runtime_grace_out_of_range', 'response_on_check_error_missing', 'schema_error', 'runtime_rate_floor_out_of_range', 'response_rule_repeat_unbounded', 'runtime_unsafe_egress', 'runtime_false_alarm_budget_out_of_range', 'evaluation_schedule_mismatch', 'chance_constraint_shadowed', 'runtime_closure_age_out_of_range', 'response_rule_id_duplicate', 'runtime_protocol_nondeterministic', 'unsupported_construct', 'runtime_max_repeats_out_of_range', 'runtime_missing_ref', 'runtime_exceeds_out_of_range', 'runtime_zero_tolerance_incomplete', 'runtime_rate_out_of_range', 'response_action_unsupported', 'runtime_report_conservation', 'response_guard_not_enforceable', 'runtime_zero_tolerance_inexact', 'runtime_trigger_hours_out_of_range', 'response_deploy_without_promotion_monitor'}
    paths = sorted(CASES.rglob("*.yml"))
    cases = {}
    used_codes = set()
    for path in paths:
        try:
            case = check_case(path, known_codes)
        except (ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
            raise ValueError(f"{path.relative_to(ROOT)}: {exc}") from exc
        cases[path.relative_to(CASES).as_posix()] = case
        used_codes.update(asserted_codes(case["expected"]))
    print(f"SAFE_LOAD / STRING_KEYS / UNIQUE_KEYS OK: {len(paths)} cases")
    print(f"RFC 5 CODES OK: {len(used_codes)} asserted of {len(known_codes)} canonical codes")
    print(f"LANGUAGE MAPPING OK: {len(paths)} cases, {len(FAMILIES)} language families")
    print("CASE LOCATIONS: " + ", ".join(f"{key}={count}" for key, count in sorted(Counter(c["family"] for c in cases.values()).items())))
    print("CHECK OK — fixture integrity only; language fixtures only; engine enablement is separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
