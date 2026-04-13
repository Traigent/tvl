from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .configuration import validate_configuration
from .errors import ParseError, SchemaError
from .promotion import SCIPY_AVAILABLE, evaluate_chance_constraint
from .schema import measurement_validator


def load_measurement(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ParseError(str(e))

    validator = measurement_validator()
    errors = list(validator.iter_errors(data))
    if errors:
        first = errors[0]
        raise SchemaError(first.message)
    return data


def normalize_measurement_bundle(measurement: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    normalized: Dict[str, Any] = {}
    for key in ("bundle_id", "config_id", "module_id", "summary"):
        if key in measurement:
            normalized[key] = measurement[key]

    warnings: List[Dict[str, Any]] = []
    normalized["objective_values"] = measurement.get("objective_values") or {}
    normalized["chance_outcomes"] = measurement.get("chance_outcomes") or {}

    legacy_objectives = measurement.get("objectives") or {}
    if legacy_objectives:
        normalized["legacy_objectives"] = legacy_objectives
        warnings.append(
            {
                "code": "deprecated_measurement_objectives",
                "message": (
                    "Top-level 'objectives' is deprecated. "
                    "Use 'objective_values.<name>.samples' or 'objective_values.<name>.mean/std/n'."
                ),
            }
        )

    legacy_chance = measurement.get("chance") or {}
    if legacy_chance:
        normalized["legacy_chance"] = legacy_chance
        warnings.append(
            {
                "code": "deprecated_measurement_chance",
                "message": (
                    "Top-level 'chance' is deprecated. "
                    "Use 'chance_outcomes.<name>.violations' and 'chance_outcomes.<name>.trials'."
                ),
            }
        )
        if not normalized["chance_outcomes"]:
            converted, conversion_warnings = _convert_legacy_chance_outcomes(
                legacy_chance,
                measurement.get("summary") or {},
            )
            normalized["chance_outcomes"] = converted
            warnings.extend(conversion_warnings)

    return normalized, warnings


def prepare_measurement_bundle(
    module: Dict[str, Any],
    measurement: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized, warnings = normalize_measurement_bundle(measurement)
    readiness_issues = _evaluate_promotion_readiness(module, normalized)
    return normalized, warnings, readiness_issues


def validate_measurement(
    module: Dict[str, Any],
    config: Dict[str, Any],
    measurement: Dict[str, Any],
) -> Dict[str, Any]:
    config_report = validate_configuration(module, config)
    normalized, warnings, readiness_issues = prepare_measurement_bundle(module, measurement)

    objectives_report = _evaluate_objectives(module, normalized)
    chance_report = _evaluate_chance(module, normalized)

    ok = config_report["ok"] and not objectives_report and not chance_report

    return {
        "ok": ok,
        "promotion_ready": not readiness_issues,
        "warnings": warnings,
        "promotion_readiness": readiness_issues,
        "structural": config_report,
        "operational": objectives_report,
        "chance": chance_report,
    }


def _evaluate_objectives(module: Dict[str, Any], measurement: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    objective_entries = module.get("objectives") or []
    objectives = {
        obj.get("name"): obj for obj in objective_entries
        if isinstance(obj, dict) and obj.get("name")
    }
    canonical = measurement.get("objective_values", {}) or {}
    legacy = measurement.get("legacy_objectives", {}) or {}

    for name, spec in objectives.items():
        data = canonical.get(name)
        legacy_data = legacy.get(name)
        if data is None and legacy_data is None:
            issues.append(
                {
                    "objective": name,
                    "code": "missing_measurement",
                    "message": "Measurement missing",
                }
            )
            continue

        observed = _objective_observed_value(data, legacy_data)
        if observed is None:
            issues.append(
                {
                    "objective": name,
                    "code": "missing_observed",
                    "message": "Observed value required for objective checks",
                }
            )
            continue

        band = spec.get("band")
        slo = spec.get("slo")
        direction = (spec.get("direction") or "maximize").lower()

        if band is not None:
            target = band.get("target")
            low, high = None, None
            if isinstance(target, list) and len(target) == 2:
                low, high = target[0], target[1]
            elif isinstance(target, dict):
                center = target.get("center")
                tol = target.get("tol")
                if center is not None and tol is not None:
                    low, high = center - tol, center + tol
            if (low is not None and observed < low) or (high is not None and observed > high):
                issues.append(
                    {
                        "objective": name,
                        "code": "band_violation",
                        "message": f"Value {observed} outside band [{low}, {high}]",
                    }
                )

        if slo is not None:
            threshold = slo.get("threshold")
            if threshold is not None:
                if direction == "minimize" and observed > threshold:
                    issues.append(
                        {
                            "objective": name,
                            "code": "slo_violation",
                            "message": f"{observed} > threshold {threshold}",
                        }
                    )
                if direction == "maximize" and observed < threshold:
                    issues.append(
                        {
                            "objective": name,
                            "code": "slo_violation",
                            "message": f"{observed} < threshold {threshold}",
                        }
                    )

    return issues


def _evaluate_chance(module: Dict[str, Any], measurement: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    chance_policy = [
        item for item in (module.get("promotion_policy", {}) or {}).get("chance_constraints", []) or []
        if isinstance(item, dict) and item.get("name")
    ]
    chance_outcomes = measurement.get("chance_outcomes", {}) or {}

    if chance_policy and not SCIPY_AVAILABLE:
        return [
            {
                "code": "missing_statistical_runtime",
                "message": (
                    "scipy is required to evaluate chance constraints from violation counts. "
                    "Install the runtime dependencies before using this command."
                ),
            }
        ]

    for constraint in chance_policy:
        name = constraint.get("name")
        if not name:
            continue
        data = chance_outcomes.get(name)
        if data is None:
            issues.append(
                {
                    "constraint": name,
                    "code": "missing_measurement",
                    "message": "Chance outcome missing",
                }
            )
            continue

        result = evaluate_chance_constraint(
            name=name,
            outcome=data,
            threshold=constraint.get("threshold", 0.0),
            confidence=constraint.get("confidence", 0.95),
        )
        if result.verdict != "pass":
            issues.append(
                {
                    "constraint": name,
                    "code": "chance_violation",
                    "message": result.reason or "Chance constraint failed",
                }
            )

    return issues


def _evaluate_promotion_readiness(module: Dict[str, Any], measurement: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    objective_values = measurement.get("objective_values", {}) or {}
    chance_outcomes = measurement.get("chance_outcomes", {}) or {}

    for objective in module.get("objectives") or []:
        if not isinstance(objective, dict):
            continue
        name = objective.get("name")
        if not name:
            continue
        data = objective_values.get(name)
        if not _has_statistical_objective_evidence(data):
            issues.append(
                {
                    "objective": name,
                    "code": "missing_statistical_evidence",
                    "message": (
                        f"Promotion gate requires objective_values.{name} to provide "
                        "samples or mean/std/n."
                    ),
                }
            )

    for constraint in (module.get("promotion_policy", {}) or {}).get("chance_constraints", []) or []:
        if not isinstance(constraint, dict):
            continue
        name = constraint.get("name")
        if not name:
            continue
        data = chance_outcomes.get(name)
        if not _has_canonical_chance_outcome(data):
            issues.append(
                {
                    "constraint": name,
                    "code": "missing_chance_counts",
                    "message": (
                        f"Promotion gate requires chance_outcomes.{name} to provide "
                        "'violations' and 'trials'."
                    ),
                }
            )

    return issues


def _convert_legacy_chance_outcomes(
    legacy_chance: Dict[str, Any],
    summary: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, int]], List[Dict[str, Any]]]:
    converted: Dict[str, Dict[str, int]] = {}
    warnings: List[Dict[str, Any]] = []
    default_trials = summary.get("trials")

    for name, data in legacy_chance.items():
        if not isinstance(data, dict):
            continue
        observed = data.get("observed")
        trials = data.get("trials", default_trials)
        if observed is None or trials is None:
            warnings.append(
                {
                    "code": "legacy_chance_not_convertible",
                    "message": (
                        f"Could not convert legacy chance summary '{name}' to canonical counts. "
                        "Provide 'violations' and 'trials' explicitly."
                    ),
                }
            )
            continue
        try:
            trials_int = int(trials)
            observed_float = float(observed)
        except (TypeError, ValueError):
            warnings.append(
                {
                    "code": "legacy_chance_not_convertible",
                    "message": (
                        f"Could not convert legacy chance summary '{name}' to canonical counts. "
                        "Provide integer trials and a numeric observed rate."
                    ),
                }
            )
            continue
        raw_violations = observed_float * trials_int
        violations_int = int(round(raw_violations))
        if abs(raw_violations - violations_int) > 1e-9:
            warnings.append(
                {
                    "code": "legacy_chance_not_convertible",
                    "message": (
                        f"Legacy chance summary '{name}' does not map cleanly to integer counts. "
                        "Provide canonical 'violations' and 'trials'."
                    ),
                }
            )
            continue
        converted[name] = {"violations": violations_int, "trials": trials_int}

    return converted, warnings


def _objective_observed_value(
    canonical: Dict[str, Any] | None,
    legacy: Dict[str, Any] | None,
) -> float | None:
    if canonical and isinstance(canonical, dict):
        samples = canonical.get("samples")
        if isinstance(samples, list) and samples:
            return sum(float(sample) for sample in samples) / len(samples)
        if canonical.get("mean") is not None:
            return float(canonical["mean"])

    if legacy and isinstance(legacy, dict) and legacy.get("observed") is not None:
        return float(legacy["observed"])

    return None


def _has_statistical_objective_evidence(data: Dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    samples = data.get("samples")
    if isinstance(samples, list) and samples:
        return True
    return (
        data.get("mean") is not None
        and data.get("std") is not None
        and data.get("n") is not None
    )


def _has_canonical_chance_outcome(data: Dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    return data.get("violations") is not None and data.get("trials") is not None
