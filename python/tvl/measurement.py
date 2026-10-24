from __future__ import annotations

from pathlib import Path
from typing import Any

from .configuration import validate_configuration
from tvl.errors import ParseError, SchemaError
from .promotion import SCIPY_AVAILABLE, evaluate_chance_constraint
from .schema import measurement_validator
from .yaml_safe import safe_load


def load_measurement(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    try:
        data = safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ParseError(str(e))

    if isinstance(data, dict) and data.get("format") == "tvl-runtime-report/1":
        err = SchemaError("unsupported_construct: runtime_report")
        err.code = "unsupported_construct"  # type: ignore[attr-defined]
        err.construct = "runtime_report"  # type: ignore[attr-defined]
        raise err

    validator = measurement_validator()
    errors = list(validator.iter_errors(data))
    if errors:
        first = errors[0]
        raise SchemaError(first.message)
    return data


def normalize_measurement_bundle(measurement: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized: dict[str, Any] = {}
    for key in ("bundle_id", "config_id", "module_id", "summary"):
        if key in measurement:
            normalized[key] = measurement[key]

    warnings: list[dict[str, Any]] = []
    normalized["objective_values"] = measurement.get("objective_values") or {}
    normalized["chance_outcomes"] = measurement.get("chance_outcomes") or {}

    if "monitor_outcomes" in measurement and isinstance(measurement.get("monitor_outcomes"), dict):
        norm_monitors: dict[str, dict[str, Any]] = {}
        for m_name, m_data in measurement["monitor_outcomes"].items():
            if not isinstance(m_data, dict):
                continue
            entry: dict[str, Any] = {
                "n": int(m_data.get("n", 0)) if m_data.get("n") is not None else 0,
                "k": int(m_data.get("k", 0)) if m_data.get("k") is not None else 0,
                "u": int(m_data.get("u", 0)) if m_data.get("u") is not None else 0,
                "pl": int(m_data.get("pl", 0)) if m_data.get("pl") is not None else 0,
            }
            if "complete" in m_data and isinstance(m_data["complete"], bool):
                entry["complete"] = m_data["complete"]
            norm_monitors[m_name] = entry
        normalized["monitor_outcomes"] = norm_monitors

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
        _normalize_legacy_chance(measurement, legacy_chance, normalized, warnings)

    return normalized, warnings


def _normalize_legacy_chance(
    measurement: dict[str, Any],
    legacy_chance: dict[str, Any],
    normalized: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> None:
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


def prepare_measurement_bundle(
    module: dict[str, Any],
    measurement: dict[str, Any],
    *,
    role: str = "candidate",
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized, warnings = normalize_measurement_bundle(measurement)
    readiness_issues = _evaluate_promotion_readiness(module, normalized, role=role)
    return normalized, warnings, readiness_issues


def validate_measurement(
    module: dict[str, Any],
    config: dict[str, Any],
    measurement: dict[str, Any],
) -> dict[str, Any]:
    config_report = validate_configuration(module, config)
    normalized, warnings, readiness_issues = prepare_measurement_bundle(module, measurement, role="candidate")

    objectives_report = _evaluate_objectives(module, normalized)
    chance_report = _evaluate_chance(module, normalized)
    promotion_monitors = [
        m for m in (module.get("monitors") or [])
        if isinstance(m, dict) and m.get("phase") == "promotion"
    ]

    ok = config_report["ok"] and not objectives_report and not chance_report

    result: dict[str, Any] = {
        "ok": ok,
        "promotion_ready": not readiness_issues,
        "warnings": warnings,
        "promotion_readiness": readiness_issues,
        "structural": config_report,
        "operational": objectives_report,
        "chance": chance_report,
    }
    if promotion_monitors:
        from .promotion_monitor import evaluate_promotion_monitor

        reqs_by_name = {
            r["name"]: r for r in (module.get("requirements") or [])
            if isinstance(r, dict) and isinstance(r.get("name"), str)
        }
        mon_outcomes = normalized.get("monitor_outcomes") or {}
        monitors_report: dict[str, Any] = {}
        for mon in promotion_monitors:
            m_name = mon.get("name")
            req = reqs_by_name.get(mon.get("requirement", ""))
            if isinstance(m_name, str) and req is not None and m_name in mon_outcomes:
                outcome = mon_outcomes[m_name]
                if 0 <= int(outcome.get("k", 0)) <= int(outcome.get("n", 0)):
                    monitors_report[m_name] = evaluate_promotion_monitor(req, mon, outcome)
        result["monitors"] = monitors_report
    return result


def _evaluate_objectives(module: dict[str, Any], measurement: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    objective_entries = module.get("objectives") or []
    objectives = {
        obj.get("name"): obj for obj in objective_entries
        if isinstance(obj, dict) and obj.get("name")
    }
    canonical = measurement.get("objective_values", {}) or {}
    legacy = measurement.get("legacy_objectives", {}) or {}

    for name, spec in objectives.items():
        issues.extend(_objective_issues(name, spec, canonical.get(name), legacy.get(name)))

    return issues


def _objective_issue(name: Any, code: str, message: str) -> dict[str, Any]:
    return {"objective": name, "code": code, "message": message}


def _objective_issues(
    name: Any,
    spec: dict[str, Any],
    data: Any,
    legacy_data: Any,
) -> list[dict[str, Any]]:
    if data is None and legacy_data is None:
        return [_objective_issue(name, "missing_measurement", "Measurement missing")]

    observed = _objective_observed_value(data, legacy_data)
    if observed is None:
        return [
            _objective_issue(name, "missing_observed", "Observed value required for objective checks")
        ]

    band = spec.get("band")
    slo = spec.get("slo")
    direction = (spec.get("direction") or "maximize").lower()

    issues: list[dict[str, Any]] = []
    if band is not None:
        issues.extend(_band_issues(name, band, observed))
    if slo is not None:
        issues.extend(_slo_issues(name, slo, direction, observed))
    return issues


def _band_bounds(band: dict[str, Any]) -> tuple[Any, Any]:
    target = band.get("target")
    if isinstance(target, list) and len(target) == 2:
        return target[0], target[1]
    if isinstance(target, dict):
        center = target.get("center")
        tol = target.get("tol")
        if center is not None and tol is not None:
            return center - tol, center + tol
    return None, None


def _band_issues(name: Any, band: dict[str, Any], observed: float) -> list[dict[str, Any]]:
    low, high = _band_bounds(band)
    if (low is not None and observed < low) or (high is not None and observed > high):
        return [_objective_issue(name, "band_violation", f"Value {observed} outside band [{low}, {high}]")]
    return []


def _slo_issues(name: Any, slo: dict[str, Any], direction: str, observed: float) -> list[dict[str, Any]]:
    threshold = slo.get("threshold")
    if threshold is None:
        return []
    issues: list[dict[str, Any]] = []
    if direction == "minimize" and observed > threshold:
        issues.append(_objective_issue(name, "slo_violation", f"{observed} > threshold {threshold}"))
    if direction == "maximize" and observed < threshold:
        issues.append(_objective_issue(name, "slo_violation", f"{observed} < threshold {threshold}"))
    return issues


def _evaluate_chance(module: dict[str, Any], measurement: dict[str, Any]) -> list[dict[str, Any]]:
    chance_policy = _named_chance_constraints(module)
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

    issues: list[dict[str, Any]] = []
    for constraint in chance_policy:
        issue = _chance_issue(constraint, chance_outcomes)
        if issue is not None:
            issues.append(issue)
    return issues


def _named_chance_constraints(module: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in (module.get("promotion_policy", {}) or {}).get("chance_constraints", []) or []
        if isinstance(item, dict) and item.get("name")
    ]


def _chance_issue(constraint: dict[str, Any], chance_outcomes: dict[str, Any]) -> dict[str, Any] | None:
    name = constraint.get("name")
    if not name:
        return None
    data = chance_outcomes.get(name)
    if data is None:
        return {
            "constraint": name,
            "code": "missing_measurement",
            "message": "Chance outcome missing",
        }

    result = evaluate_chance_constraint(
        name=name,
        outcome=data,
        threshold=constraint.get("threshold", 0.0),
        confidence=constraint.get("confidence", 0.95),
    )
    if result.verdict == "error":
        return {
            "constraint": name,
            "code": result.code or "chance_error",
            "message": result.reason or "Chance constraint check is undefined",
        }
    if result.verdict != "pass":
        return {
            "constraint": name,
            "code": "chance_violation",
            "message": result.reason or "Chance constraint failed",
        }
    return None


def _evaluate_promotion_readiness(
    module: dict[str, Any],
    measurement: dict[str, Any],
    *,
    role: str = "candidate",
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(_calibration_issues(module))
    issues.extend(_module_mismatch_issues(module, measurement))
    objective_values = measurement.get("objective_values", {}) or {}
    chance_outcomes = measurement.get("chance_outcomes", {}) or {}
    issues.extend(_objective_evidence_issues(module, objective_values))
    issues.extend(_chance_count_issues(module, chance_outcomes))
    issues.extend(_monitor_count_issues(module, measurement, role=role))
    return issues


def _calibration_issues(module: dict[str, Any]) -> list[dict[str, Any]]:
    """Refuse promotion under every strict-mode trigger (fail closed).

    The tools cannot validate calibration certificates, so any module that is
    in the strict evidence mode of RFC 0001 section 3.6 (and RFC 0002 section 5
    for composites) is refused. Triggers, with the RFC clause they implement:

    * ``require_calibration_enabled``: promotion_policy.require_calibration.enabled
    * ``chance_constraints``: promotion_policy.chance_constraints is non-empty
      AND the module has something to certify (a cvar or a calibrated
      composite member); with nothing to certify, CalibrationPass holds
      vacuously and the chapter 6 style module still gets a decision
    * ``cvar_governance``: a cvar has governance.require_calibration
    * ``certificate_backed_cvar``: a cvar is declared; every cvar carries a
      calibration block, so its certificate has a TargetProperty. The RFC
      limits this to cvars the candidate consumes; v1 treats every declared
      cvar as consumed, which can only over-refuse.
    * ``composite_calibrated_member``: a composite has a calibrated member
      (gate threshold, signal_accept stop, accept threshold, cvar cardinality,
      or a judge/arm that references a composite with one).

    The guaranteed-selection trigger belongs to the operational profile, which
    the gate does not receive; it has no module field to inspect.
    """
    if not _strict_calibration_triggers(module):
        return []
    return [
        {
            "code": "calibration_evidence_unsupported",
            "message": (
                "This module requires calibration certificates, but the current "
                "measurement bundle and tvl-ci-gate contract cannot validate them."
            ),
        }
    ]


def _strict_calibration_triggers(module: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    policy = module.get("promotion_policy") or {}
    strict_policy = policy.get("require_calibration") or {}
    if bool(strict_policy.get("enabled")):
        triggers.append("require_calibration_enabled")
    has_chance = bool(policy.get("chance_constraints"))
    cvars = [cvar for cvar in (module.get("cvars") or []) if isinstance(cvar, dict)]
    if any(bool((cvar.get("governance") or {}).get("require_calibration")) for cvar in cvars):
        triggers.append("cvar_governance")
    if cvars:
        triggers.append("certificate_backed_cvar")
    has_composite_member = _has_calibrated_composite_member(module)
    if has_chance and (cvars or has_composite_member):
        triggers.append("chance_constraints")
    if has_composite_member:
        triggers.append("composite_calibrated_member")
    return triggers


def _has_calibrated_composite_member(module: dict[str, Any]) -> bool:
    """RFC 0002 section 3.6 ``Cal``: does any declared composite have a calibrated member?

    Only grammar-defined composite fields are read (arms, gates, aggregate,
    body, stop, cardinality); operational metadata such as ``parameters`` is
    skipped. A judge or nested arm counts only through the calibrated members of
    the composite it references (``Cal(stage) = {}``).
    """
    declared = {
        decl["name"]: decl
        for decl in (module.get("composites") or [])
        if isinstance(decl, dict) and isinstance(decl.get("name"), str)
    }
    cvar_names = {
        cvar["name"]
        for cvar in (module.get("cvars") or [])
        if isinstance(cvar, dict) and isinstance(cvar.get("name"), str)
    }

    def arm_calibrated(arm: Any, seen: frozenset[str]) -> bool:
        if not isinstance(arm, dict):
            return False
        ref = arm.get("composite")
        return isinstance(ref, str) and ref in declared and decl_calibrated(ref, seen)

    def decl_calibrated(name: str, seen: frozenset[str]) -> bool:
        if name in seen:
            return False
        seen = seen | {name}
        decl = declared[name]
        arms = decl.get("arms")
        if isinstance(arms, list) and any(arm_calibrated(arm, seen) for arm in arms):
            return True
        if arm_calibrated(decl.get("body"), seen):
            return True
        gates = decl.get("gates")
        if isinstance(gates, list) and any(isinstance(gate, dict) for gate in gates):
            return True
        stop = decl.get("stop")
        if isinstance(stop, dict) and stop.get("kind") == "signal_accept":
            return True
        aggregate = decl.get("aggregate")
        if isinstance(aggregate, dict):
            if arm_calibrated(aggregate.get("judge"), seen):
                return True
            if isinstance(aggregate.get("accept"), dict) and aggregate["accept"].get("threshold"):
                return True
        return decl.get("cardinality") in cvar_names

    return any(decl_calibrated(name, frozenset()) for name in declared)


def _module_mismatch_issues(module: dict[str, Any], measurement: dict[str, Any]) -> list[dict[str, Any]]:
    expected_module_id = (module.get("tvl") or {}).get("module")
    measured_module_id = measurement.get("module_id")
    if measured_module_id and expected_module_id and measured_module_id != expected_module_id:
        return [
            {
                "code": "measurement_module_mismatch",
                "message": (
                    f"Measurement targets module {measured_module_id} but the gate uses "
                    f"module {expected_module_id}."
                ),
            }
        ]
    return []


def _objective_evidence_issues(module: dict[str, Any], objective_values: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for objective in module.get("objectives") or []:
        if not isinstance(objective, dict):
            continue
        name = objective.get("name")
        if not name:
            continue
        if not _has_statistical_objective_evidence(objective_values.get(name)):
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
    return issues


def _chance_count_issues(module: dict[str, Any], chance_outcomes: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for constraint in (module.get("promotion_policy", {}) or {}).get("chance_constraints", []) or []:
        if not isinstance(constraint, dict):
            continue
        name = constraint.get("name")
        if not name:
            continue
        if not _has_canonical_chance_outcome(chance_outcomes.get(name)):
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


def _monitor_count_issues(
    module: dict[str, Any],
    measurement: dict[str, Any],
    *,
    role: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if role == "candidate":
        monitor_outcomes = measurement.get("monitor_outcomes") or {}
        for mon in module.get("monitors") or []:
            if not isinstance(mon, dict) or mon.get("phase") != "promotion":
                continue
            m_name = mon.get("name")
            if not isinstance(m_name, str):
                continue
            m_data = monitor_outcomes.get(m_name)
            if (
                not isinstance(m_data, dict)
                or m_data.get("n") is None
                or m_data.get("k") is None
                or int(m_data["n"]) < 0
                or int(m_data["k"]) < 0
                or int(m_data["k"]) > int(m_data["n"])
            ):
                issues.append(
                    {
                        "monitor": m_name,
                        "code": "missing_monitor_counts",
                        "message": (
                            f"Promotion gate requires candidate monitor_outcomes.{m_name} "
                            "with 0 <= k <= n."
                        ),
                    }
                )

    return issues


def _convert_legacy_chance_outcomes(
    legacy_chance: dict[str, Any],
    summary: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]]]:
    converted: dict[str, dict[str, int]] = {}
    warnings: list[dict[str, Any]] = []
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
    canonical: dict[str, Any] | None,
    legacy: dict[str, Any] | None,
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


def _has_statistical_objective_evidence(data: dict[str, Any] | None) -> bool:
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


def _has_canonical_chance_outcome(data: dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    return data.get("violations") is not None and data.get("trials") is not None
